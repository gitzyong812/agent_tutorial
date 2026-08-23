"""受控技能注册表。"""

from .registry import SkillDefinition, SkillRegistry, get_skill_registry
from .service import (
    finish_skill_deletion,
    install_skill,
    normalize_upload_paths,
    restore_skill_deletion,
    stage_skill_deletion,
    update_created_skill,
)

__all__ = [
    "SkillDefinition",
    "SkillRegistry",
    "get_skill_registry",
    "finish_skill_deletion",
    "install_skill",
    "normalize_upload_paths",
    "restore_skill_deletion",
    "stage_skill_deletion",
    "update_created_skill",
]
