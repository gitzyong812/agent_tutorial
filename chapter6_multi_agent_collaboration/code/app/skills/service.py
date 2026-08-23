"""本地技能目录导入，负责路径校验和安全落盘。"""
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
import os
import shutil
import tempfile

from ..config import MAX_SKILL_BYTES, MAX_SKILL_FILES
from .registry import (
    SkillDefinition,
    SkillRegistry,
    build_skill_definition,
    parse_skill_document,
)


WRITABLE_SOURCES = {"imported", "created"}
DELETABLE_SOURCES = {"imported", "created"}


@dataclass(frozen=True)
class StagedSkillDeletion:
    name: str
    source: str
    original: Path
    staged: Path


def normalize_upload_paths(paths: list[str]) -> list[Path]:
    normalized: list[PurePosixPath] = []
    for raw in paths:
        value = raw.replace("\\", "/").strip()
        path = PurePosixPath(value)
        if (
            not value
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError(f"非法相对路径：{raw}")
        normalized.append(path)
    if not normalized:
        raise ValueError("技能目录不能为空")

    first_parts = {path.parts[0] for path in normalized}
    if len(first_parts) == 1 and all(len(path.parts) > 1 for path in normalized):
        normalized = [PurePosixPath(*path.parts[1:]) for path in normalized]
    if len(set(normalized)) != len(normalized):
        raise ValueError("技能目录包含重复路径")
    return [Path(*path.parts) for path in normalized]


def install_skill(
    registry: SkillRegistry,
    paths: list[Path],
    contents: list[bytes],
    *,
    source: str,
    overwrite: bool = False,
) -> SkillDefinition:
    if source not in WRITABLE_SOURCES:
        raise ValueError("只能写入外部导入或对话创建目录")
    if len(paths) != len(contents):
        raise ValueError("文件与路径数量不一致")
    if not paths or len(paths) > MAX_SKILL_FILES:
        raise ValueError(f"一个技能最多包含 {MAX_SKILL_FILES} 个文件")
    if sum(len(item) for item in contents) > MAX_SKILL_BYTES:
        raise ValueError("技能目录总大小不能超过 10 MB")
    try:
        skill_index = paths.index(Path("SKILL.md"))
    except ValueError as exc:
        raise ValueError("技能目录根部缺少 SKILL.md") from exc
    try:
        document = contents[skill_index].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("SKILL.md 必须使用 UTF-8 编码") from exc
    document = document.replace("\r\n", "\n").replace("\r", "\n")
    contents[skill_index] = document.encode("utf-8")

    metadata, body = parse_skill_document(document)
    skill = build_skill_definition(
        metadata,
        source=source,
        path=registry.root / source / "pending" / "SKILL.md",
        content=body,
    )
    registry.refresh()
    existing = registry.get(skill.name)
    if existing is not None:
        if existing.source != source:
            raise FileExistsError(f"技能名称已被 {existing.source} 类型占用")
        if not overwrite:
            raise FileExistsError("同名技能已存在")

    parent = registry.root / source
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / skill.name
    temp = Path(tempfile.mkdtemp(prefix=f".{skill.name}-", dir=parent))
    backup: Path | None = None
    try:
        for path, content in zip(paths, contents, strict=True):
            destination = temp / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        if target.exists():
            backup = Path(tempfile.mkdtemp(prefix=f".{skill.name}-backup-", dir=parent))
            backup.rmdir()
            os.replace(target, backup)
        os.replace(temp, target)
        if backup is not None:
            shutil.rmtree(backup, ignore_errors=True)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise

    registry.refresh()
    installed = registry.get(skill.name)
    if installed is None:
        raise ValueError("技能写入后未能加载")
    return installed


def update_created_skill(
    registry: SkillRegistry,
    name: str,
    document: str,
) -> SkillDefinition:
    registry.refresh()
    existing = registry.get(name)
    if existing is None:
        raise FileNotFoundError("技能不存在")
    if existing.source != "created":
        raise PermissionError("只能编辑对话创建技能")
    normalized = document.replace("\r\n", "\n").replace("\r", "\n")
    metadata, body = parse_skill_document(normalized)
    updated = build_skill_definition(
        metadata,
        source="created",
        path=existing.path,
        content=body,
    )
    if updated.name != name:
        raise ValueError("技能名称不可修改")
    target = _controlled_skill_directory(registry, existing) / "SKILL.md"
    descriptor, temp_name = tempfile.mkstemp(prefix=".SKILL-", suffix=".md", dir=target.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(normalized.encode("utf-8"))
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    registry.refresh()
    result = registry.get(name)
    if result is None:
        raise ValueError("技能更新后未能加载")
    return result


def stage_skill_deletion(registry: SkillRegistry, name: str) -> StagedSkillDeletion:
    registry.refresh()
    skill = registry.get(name)
    if skill is None:
        raise FileNotFoundError("技能不存在")
    if skill.source not in DELETABLE_SOURCES:
        raise PermissionError("内置技能不可删除")
    original = _controlled_skill_directory(registry, skill)
    staged = Path(tempfile.mkdtemp(prefix=f".{name}-delete-", dir=original.parent))
    staged.rmdir()
    os.replace(original, staged)
    registry.refresh()
    return StagedSkillDeletion(name, skill.source, original, staged)


def restore_skill_deletion(
    registry: SkillRegistry,
    deletion: StagedSkillDeletion,
) -> None:
    if deletion.staged.exists() and not deletion.original.exists():
        os.replace(deletion.staged, deletion.original)
    registry.refresh()


def finish_skill_deletion(
    registry: SkillRegistry,
    deletion: StagedSkillDeletion,
) -> None:
    shutil.rmtree(deletion.staged)
    registry.refresh()


def _controlled_skill_directory(
    registry: SkillRegistry,
    skill: SkillDefinition,
) -> Path:
    source_root = (registry.root / skill.source).resolve()
    directory = skill.path.resolve().parent
    if directory.parent != source_root or directory.name != skill.name:
        raise ValueError("技能目录不在受控来源目录中")
    return directory
