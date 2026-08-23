"""文档解析与清洗：把原始资料转换为规范化文本。

v1 支持纯文本与 Markdown；PDF / Word / OCR 留作后续扩展。
"""
import re


# 受支持的文件类型（与文档 file_type 对应）。
SUPPORTED_TYPES = {"markdown", "txt"}


def detect_file_type(filename: str) -> str:
    """根据文件名后缀判断类型，默认按 markdown 处理。"""
    name = (filename or "").lower()
    if name.endswith(".md") or name.endswith(".markdown"):
        return "markdown"
    if name.endswith(".txt"):
        return "txt"
    # 预留：.pdf / .docx 等后续在此扩展。
    return "markdown"


def clean_text(raw_text: str) -> str:
    """清洗文本：统一换行、去除多余空白与连续空行。

    清洗不是润色，只去掉会干扰分块和检索的噪声，保留正文与标题结构。
    """
    # 1. 统一换行符，去掉零宽字符
    text = (raw_text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    # 2. 逐行去除行尾空白
    lines = [line.rstrip() for line in text.split("\n")]
    # 3. 把 3 个以上连续空行压缩为 1 个空行
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
