"""文本分块：把清洗后的文本切成带来源标题的知识片段。

提供两种策略，对应正文「比较两种分块」的实践任务：
- structure（默认）：按 Markdown 标题/段落切分，过长再按长度细分，相邻块少量重叠。
- fixed：固定字数 + 重叠，结构不明显时兜底。
"""
import re
from dataclasses import dataclass

from .. import config


@dataclass
class Chunk:
    """一个知识片段：文本内容 + 所属标题（用于展示依据）。"""

    content: str
    source_title: str


# 默认分块参数：中文按字符计长。
DEFAULT_CHUNK_SIZE = config.DEFAULT_CHUNK_SIZE
DEFAULT_OVERLAP = config.DEFAULT_CHUNK_OVERLAP


def split_text(
    text: str,
    strategy: str = "structure",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    """按指定策略分块，返回 Chunk 列表。"""
    if strategy == "fixed":
        return _split_fixed(text, chunk_size, overlap)
    return _split_structure(text, chunk_size, overlap)


def _split_fixed(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """固定长度分块：按字数切分并设置重叠，标题统一为空。"""
    body = text.strip()
    if not body:
        return []
    step = max(1, chunk_size - overlap)
    chunks: list[Chunk] = []
    for start in range(0, len(body), step):
        piece = body[start : start + chunk_size].strip()
        if piece:
            chunks.append(Chunk(content=piece, source_title=""))
        if start + chunk_size >= len(body):
            break
    return chunks


def _split_structure(text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    """结构优先分块：先按 Markdown 标题分段，过长段落再按长度细分。"""
    sections = _split_by_heading(text)
    chunks: list[Chunk] = []
    for title, body in sections:
        body = body.strip()
        if not body:
            continue
        if len(body) <= chunk_size:
            chunks.append(Chunk(content=body, source_title=title))
            continue
        # 段落过长：按长度细分，每个子块都挂同一标题，便于追溯。
        for piece in _split_fixed(body, chunk_size, overlap):
            chunks.append(Chunk(content=piece.content, source_title=title))
    return chunks


def _split_by_heading(text: str) -> list[tuple[str, str]]:
    """按 Markdown 标题（# 开头）切分为 (标题, 正文) 段落列表。

    无标题时整体作为一个无标题段落返回。
    """
    lines = text.split("\n")
    sections: list[tuple[str, str]] = []
    current_title = ""
    current_lines: list[str] = []

    def flush():
        if current_lines:
            sections.append((current_title, "\n".join(current_lines).strip()))

    for line in lines:
        heading = re.match(r"^#{1,6}\s+(.*)$", line.strip())
        if heading:
            flush()
            current_title = heading.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    flush()
    return sections or [("", text.strip())]
