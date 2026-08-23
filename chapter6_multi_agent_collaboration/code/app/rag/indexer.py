"""离线索引编排：文档 → 清洗 → 分块 → 嵌入 → 写入片段，并更新文档状态。"""
import logging

from sqlalchemy.orm import Session

from .. import models
from . import chunker, embedding, parser

logger = logging.getLogger("uvicorn.error")


def reindex_document(
    db: Session,
    document: models.KnowledgeDocument,
    strategy: str = "structure",
    chunk_size: int = chunker.DEFAULT_CHUNK_SIZE,
    overlap: int = chunker.DEFAULT_OVERLAP,
) -> models.KnowledgeDocument:
    """重建单个文档的索引：先分块、嵌入，再短事务替换旧片段。

    嵌入失败或无嵌入配置时，片段仍写入（向量为空），文档标记 failed，
    检索阶段会自动降级为关键词匹配，保证最小可跑。
    """
    # 1. 清洗 + 分块。此阶段不写库，避免长时间占用 SQLite 写锁。
    text = parser.clean_text(document.content)
    chunks = chunker.split_text(text, strategy=strategy, chunk_size=chunk_size, overlap=overlap)
    logger.info(
        "document reindex started: document_id=%s name=%s chunks=%s strategy=%s",
        document.id,
        document.name,
        len(chunks),
        strategy,
    )

    # 2. 嵌入（失败则向量留空，状态置 failed）。远端调用放在写库前完成。
    vectors: list[list[float]] = []
    status = "indexed"
    cfg = embedding.get_embedding_config()
    embedding_model_name = cfg.model_name if cfg is not None else ""
    if chunks and cfg is not None:
        try:
            vectors = embedding.embed_texts(cfg, [c.content for c in chunks])
        except Exception:
            logger.exception("embedding failed, keyword fallback will be used: document_id=%s", document.id)
            vectors = []
            status = "failed"
    elif chunks:
        # 没有可用嵌入配置：允许入库，但提示需要配置嵌入模型才能向量检索。
        logger.warning("embedding config missing, keyword fallback will be used: document_id=%s", document.id)
        status = "failed"

    # 3. 短事务替换旧片段并更新文档状态。
    db.query(models.KnowledgeChunk).filter(
        models.KnowledgeChunk.document_id == document.id
    ).delete()

    for index, chunk in enumerate(chunks):
        vector = vectors[index] if index < len(vectors) else None
        db.add(
            models.KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                content=chunk.content,
                source_title=chunk.source_title,
                embedding=vector,
                embedding_model_name=embedding_model_name,
            )
        )

    document.chunk_count = len(chunks)
    document.status = status
    db.commit()
    db.refresh(document)
    logger.info(
        "document reindex finished: document_id=%s status=%s chunk_count=%s",
        document.id,
        document.status,
        document.chunk_count,
    )
    return document
