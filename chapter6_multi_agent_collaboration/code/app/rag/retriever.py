"""知识检索模块：输入 query + 标签范围 + top_k，输出排序好的知识片段。

内置三种可插拔检索器：
- vector：内存 numpy 余弦相似度（默认，零外部服务）。
- keyword：BM25 词面匹配（rank_bm25，可选依赖）；预留 ElasticSearch 后端接口。
- hybrid：RRF 融合向量 + 关键词，再做简单去重重排。

任何检索器在依赖或数据缺失时都会自动降级，保证最小可跑。
"""
import logging
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from sqlalchemy.orm import contains_eager

from .. import models
from . import embedding

logger = logging.getLogger("uvicorn.error")


@dataclass
class Passage:
    """检索结果片段：内容 + 来源 + 分数。"""

    document_id: int
    document_name: str
    source_title: str
    embedding_model_name: str
    content: str
    score: float


def _load_candidate_chunks(db, tag_ids: list[int]) -> list[models.KnowledgeChunk]:
    """加载候选片段：命中指定标签、且文档未过期。

    tag_ids 为空时不限制标签（用于检索调试的全库检索）。
    """
    now = datetime.now()
    query = (
        db.query(models.KnowledgeChunk)
        .join(models.KnowledgeDocument)
        .options(contains_eager(models.KnowledgeChunk.document))
    )
    # 1. 过期过滤：expires_at 为空（长期有效）或晚于当前时间
    query = query.filter(
        (models.KnowledgeDocument.expires_at.is_(None))
        | (models.KnowledgeDocument.expires_at > now)
    )
    # 2. 标签过滤：文档需关联到任一指定标签
    if tag_ids:
        query = query.join(models.KnowledgeDocument.tags).filter(
            models.KnowledgeTag.id.in_(tag_ids)
        )
    return query.all()


def _tokenize(text: str) -> list[str]:
    """简单分词：英文按空白，中文按单字，兼顾教学场景下的中英文混排。"""
    import re

    tokens: list[str] = []
    for token in re.findall(r"[a-zA-Z0-9]+|[一-鿿]", text.lower()):
        tokens.append(token)
    return tokens


def _passage_from_chunk(
    chunk: models.KnowledgeChunk,
    score: float,
) -> Passage:
    """把片段 ORM 对象包装为检索结果。"""
    return Passage(
        document_id=chunk.document_id,
        document_name=chunk.document.name if chunk.document else "",
        source_title=chunk.source_title,
        embedding_model_name=chunk.embedding_model_name,
        content=chunk.content,
        score=round(float(score), 4),
    )


def _vector_search(
    db,
    query: str,
    chunks: list[models.KnowledgeChunk],
    top_k: int,
) -> list[Passage] | None:
    """向量检索：query 向量与候选片段向量做余弦相似度。

    无嵌入配置、无可用向量或调用失败时返回 None，交由调用方降级。
    """
    cfg = embedding.get_embedding_config()
    if cfg is None:
        logger.warning("vector search skipped: embedding config missing")
        return None
    vectored = [c for c in chunks if c.embedding]
    if not vectored:
        logger.warning("vector search skipped: no embedded chunks")
        return None
    try:
        query_vec = embedding.embed_query(cfg, query)
    except Exception:
        logger.exception("vector search failed while embedding query")
        return None
    if not query_vec:
        return None

    matrix = np.asarray([c.embedding for c in vectored], dtype="float32")
    q = np.asarray(query_vec, dtype="float32")
    # 余弦相似度 = 归一化后的内积
    matrix_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8)
    q_norm = q / (np.linalg.norm(q) + 1e-8)
    scores = matrix_norm @ q_norm
    order = np.argsort(scores)[::-1][:top_k]
    return [_passage_from_chunk(vectored[i], scores[i]) for i in order]


def _keyword_search(
    query: str,
    chunks: list[models.KnowledgeChunk],
    top_k: int,
) -> list[Passage]:
    """关键词检索：优先用 BM25，缺依赖时降级为词项命中计数。

    预留 ElasticSearch 后端：生产环境可把本函数替换为对 ES 的查询。
    """
    if not chunks:
        return []
    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    try:
        from rank_bm25 import BM25Okapi

        corpus = [_tokenize(c.content + " " + c.source_title) for c in chunks]
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)
    except Exception:
        logger.info("BM25 unavailable or failed, using simple keyword count fallback")
        # 降级：统计查询词在片段中的命中次数
        scores = []
        for c in chunks:
            text_tokens = _tokenize(c.content + " " + c.source_title)
            scores.append(float(sum(text_tokens.count(t) for t in query_tokens)))
        scores = np.asarray(scores, dtype="float32")

    scores = np.asarray(scores, dtype="float32")
    order = np.argsort(scores)[::-1][:top_k]
    return [_passage_from_chunk(chunks[i], scores[i]) for i in order if scores[i] > 0]


def _rrf_merge(rankings: list[list[Passage]], top_k: int, k: int = 60) -> list[Passage]:
    """倒数排名融合（RRF）：综合多路检索结果，并按片段去重。"""
    fused: dict[tuple[int, str], list] = {}
    for passages in rankings:
        for rank, p in enumerate(passages):
            key = (p.document_id, p.content)
            if key not in fused:
                fused[key] = [p, 0.0]
            fused[key][1] += 1.0 / (k + rank + 1)
    merged = []
    for (_, _), (passage, score) in fused.items():
        passage.score = round(score, 4)
        merged.append(passage)
    merged.sort(key=lambda x: x.score, reverse=True)
    return merged[:top_k]


def search(db, query: str, tag_ids: list[int], top_k: int = 3, retriever_type: str = "vector") -> list[Passage]:
    """统一检索入口：按 retriever_type 选择检索器，带自动降级。

    1. 先按标签 + 过期时间过滤候选片段。
    2. 按检索器类型召回；向量不可用时回退关键词。
    """
    query = (query or "").strip()
    if not query:
        logger.info("retrieval skipped: empty query")
        return []
    chunks = _load_candidate_chunks(db, tag_ids)
    logger.info(
        "retrieval candidates loaded: retriever=%s tag_ids=%s candidates=%s top_k=%s",
        retriever_type,
        tag_ids,
        len(chunks),
        top_k,
    )
    if not chunks:
        logger.warning("retrieval returned no candidates: tag_ids=%s", tag_ids)
        return []

    if retriever_type == "keyword":
        hits = _keyword_search(query, chunks, top_k)
        logger.info("keyword retrieval finished: hits=%s", len(hits))
        return hits

    if retriever_type == "hybrid":
        vector_hits = _vector_search(db, query, chunks, top_k * 2) or []
        keyword_hits = _keyword_search(query, chunks, top_k * 2)
        if vector_hits and keyword_hits:
            hits = _rrf_merge([vector_hits, keyword_hits], top_k)
        else:
            hits = (vector_hits or keyword_hits)[:top_k]
        logger.info(
            "hybrid retrieval finished: vector_hits=%s keyword_hits=%s hits=%s",
            len(vector_hits),
            len(keyword_hits),
            len(hits),
        )
        return hits

    # 默认向量检索；不可用时降级关键词。
    vector_hits = _vector_search(db, query, chunks, top_k)
    if vector_hits is None:
        hits = _keyword_search(query, chunks, top_k)
        logger.info("vector retrieval fell back to keyword: hits=%s", len(hits))
        return hits
    logger.info("vector retrieval finished: hits=%s", len(vector_hits))
    return vector_hits
