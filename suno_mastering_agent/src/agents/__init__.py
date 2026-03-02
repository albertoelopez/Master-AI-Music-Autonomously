"""Suno Studio agents - compose skills into high-level workflows."""
from .mastering import MasteringAgent
from .batch_create import BatchCreateAgent
from .autonomous_create import AutoCreateAgent, AutoCreateConfig
from .autopilot import AutopilotAgent, AutopilotConfig

__all__ = [
    "MasteringAgent",
    "BatchCreateAgent",
    "AutoCreateAgent",
    "AutoCreateConfig",
    "AutopilotAgent",
    "AutopilotConfig",
]
