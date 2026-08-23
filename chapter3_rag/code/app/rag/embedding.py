"""文本向量化：读取 .env 中的 embedding 配置生成向量。

使用 OpenAI 兼容的 /embeddings 接口，可连接 Qwen、OpenAI 等服务。
"""
from dataclasses import dataclass

from openai import OpenAI

from .. import config

DEFAULT_BATCH_SIZE = config.DEFAULT_BATCH_SIZE


@dataclass
class EmbeddingConfig:
    """OpenAI-compatible embedding 模型配置。"""

    api_key: str
    base_url: str
    model_name: str
    dimensions: int | None = None


def get_embedding_config() -> EmbeddingConfig | None:
    """读取 .env 中的 embedding 配置；缺少关键字段则返回 None。"""
    if not config.EMBEDDING_API_KEY or not config.EMBEDDING_BASE_URL or not config.EMBEDDING_MODEL_NAME:
        return None
    return EmbeddingConfig(
        api_key=config.EMBEDDING_API_KEY,
        base_url=config.EMBEDDING_BASE_URL,
        model_name=config.EMBEDDING_MODEL_NAME,
        dimensions=config.EMBEDDING_DIMENSIONS,
    )


def embed_texts(cfg: EmbeddingConfig, texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[float]]:
    """批量把文本转换为向量。失败时抛出异常，由调用方决定降级。"""
    if not texts:
        return []
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        kwargs = {"model": cfg.model_name, "input": batch}
        if cfg.dimensions:
            kwargs["dimensions"] = cfg.dimensions
        resp = client.embeddings.create(**kwargs)
        # 按 index 排序，避免服务端返回乱序。
        items = sorted(resp.data, key=lambda d: d.index)
        vectors.extend(item.embedding for item in items)
    return vectors


def embed_query(cfg: EmbeddingConfig, query: str) -> list[float]:
    """把单个查询转换为向量。"""
    vectors = embed_texts(cfg, [query])
    return vectors[0] if vectors else []
