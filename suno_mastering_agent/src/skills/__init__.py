"""Suno Studio automation skills - atomic, repeatable browser actions."""
from .base import Skill, SkillResult
from .navigate import NavigateSkill
from .modal import ModalSkill
from .studio import StudioSkill
from .eq import EQSkill
from .mixing import MixingSkill
from .create import CreateSkill

__all__ = [
    "Skill", "SkillResult",
    "NavigateSkill", "ModalSkill", "StudioSkill",
    "EQSkill", "MixingSkill", "CreateSkill",
]
