"""团队共享文本文件的配额与路径处理。"""
import re

from fastapi import HTTPException

from .. import models

MAX_SHARED_FILES = 12
MAX_SHARED_FILE_BYTES = 256 * 1024
MAX_SHARED_TOTAL_BYTES = 1024 * 1024


def ensure_file_quota(group: models.GroupConversation, new_size: int) -> None:
    if new_size > MAX_SHARED_FILE_BYTES:
        raise HTTPException(status_code=400, detail="group_file_single_size_limit")
    if len(group.files or []) >= MAX_SHARED_FILES:
        raise HTTPException(status_code=400, detail="group_file_count_limit")
    current_size = sum(item.size or 0 for item in group.files or [])
    if current_size + new_size > MAX_SHARED_TOTAL_BYTES:
        raise HTTPException(status_code=400, detail="group_file_size_limit")


def workspace_path(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1].strip() or "untitled.txt"
    name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._ -]+", "_", name)
    return f"/workspace/{name}"
