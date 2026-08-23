"""按来源扫描 SKILL.md，并按需读取完整技能说明。"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

import yaml


SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"
SKILL_SOURCES = ("builtin", "imported", "created")
_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    version: str
    required_tools: tuple[str, ...]
    source: str
    path: Path
    content: str = ""

    def metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "required_tools": list(self.required_tools),
            "source": self.source,
        }


class SkillRegistry:
    """教学版技能注册表，区分内置、外部导入和对话创建三种来源。"""

    def __init__(self, root: Path = SKILLS_DIR):
        self.root = root.resolve()
        self.skills: dict[str, SkillDefinition] = {}
        self.diagnostics: list[str] = []
        self.refresh()

    def refresh(self) -> None:
        self.skills = {}
        self.diagnostics = []
        if not self.root.is_dir():
            self.diagnostics.append(f"技能目录不存在：{self.root}")
            return
        for source in SKILL_SOURCES:
            for path in sorted((self.root / source).glob("*/SKILL.md")):
                try:
                    skill = self._load(path, source, include_content=False)
                    if skill.name in self.skills:
                        existing = self.skills[skill.name]
                        raise ValueError(
                            f"技能名称重复，已优先使用 {existing.source}/{existing.name}"
                        )
                    self.skills[skill.name] = skill
                except Exception as exc:
                    self.diagnostics.append(f"{source}/{path.parent.name}: {exc}")

    def list(self) -> list[SkillDefinition]:
        return list(self.skills.values())

    def get(self, name: str, include_content: bool = False) -> SkillDefinition | None:
        found = self.skills.get(name)
        if found is None or not include_content:
            return found
        return self._load(found.path, found.source, include_content=True)

    def _load(self, path: Path, source: str, include_content: bool) -> SkillDefinition:
        if source not in SKILL_SOURCES:
            raise ValueError("技能来源无效")
        resolved = path.resolve()
        source_root = (self.root / source).resolve()
        if source_root not in resolved.parents:
            raise ValueError("技能文件不在受控目录中")
        if include_content:
            text = resolved.read_text(encoding="utf-8")
            metadata, body = parse_skill_document(text)
        else:
            metadata = _read_frontmatter(resolved)
            body = ""
        return build_skill_definition(
            metadata,
            source=source,
            path=resolved,
            content=body.strip() if include_content else "",
        )


def build_skill_definition(
    metadata: dict,
    *,
    source: str,
    path: Path,
    content: str = "",
) -> SkillDefinition:
    name = str(metadata.get("name", "")).strip()
    description = str(metadata.get("description", "")).strip()
    version = str(metadata.get("version", "1.0")).strip() or "1.0"
    if "allowed-tools" in metadata:
        raise ValueError("allowed-tools 已停用，请使用非授权性的 required-tools")
    required_tools = metadata.get("required-tools", [])
    if not _NAME_RE.fullmatch(name):
        raise ValueError("name 格式无效")
    if not description:
        raise ValueError("缺少 description")
    if not isinstance(required_tools, list) or not all(
        isinstance(item, str) and _NAME_RE.fullmatch(item) for item in required_tools
    ):
        raise ValueError("required-tools 必须是合法工具名列表")
    return SkillDefinition(
        name=name,
        description=description,
        version=version,
        required_tools=tuple(required_tools),
        source=source,
        path=path,
        content=content,
    )


def parse_skill_document(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("缺少 YAML frontmatter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("YAML frontmatter 未闭合")
    metadata = yaml.safe_load(text[4:end]) or {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter 必须是对象")
    body = text[end + 5 :].strip()
    if not body:
        raise ValueError("技能正文不能为空")
    return metadata, body


def _read_frontmatter(path: Path) -> dict:
    """发现阶段读到第二个分隔线即停止，不加载技能正文。"""
    with path.open("r", encoding="utf-8") as file:
        if file.readline().rstrip("\n") != "---":
            raise ValueError("缺少 YAML frontmatter")
        lines = []
        for line in file:
            if line.rstrip("\n") == "---":
                metadata = yaml.safe_load("".join(lines)) or {}
                if not isinstance(metadata, dict):
                    raise ValueError("frontmatter 必须是对象")
                return metadata
            lines.append(line)
    raise ValueError("YAML frontmatter 未闭合")


@lru_cache(maxsize=1)
def get_skill_registry() -> SkillRegistry:
    return SkillRegistry()
