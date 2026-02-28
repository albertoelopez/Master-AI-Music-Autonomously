"""Configuration settings for Suno AI Studio automation."""
from pydantic import BaseModel
from typing import Optional, Dict, Any


class SunoConfig(BaseModel):
    """Suno AI Studio configuration."""
    base_url: str = "https://suno.com"
    studio_url: str = "https://suno.com/studio"
    create_url: str = "https://suno.com/create"
    library_url: str = "https://suno.com/me"
    api_base: str = "https://studio-api.prod.suno.com"
    timeout_ms: int = 30000
    viewport_width: int = 1280
    viewport_height: int = 900


# Default configuration
DEFAULT_CONFIG = SunoConfig()

# EQ presets available in Suno Studio (built-in)
SUNO_EQ_PRESETS = [
    "Flat (Reset)", "High-pass", "Vocal", "Warm", "Presence",
    "Bass Boost", "Air", "Clarity", "Fullness", "Lo-fi", "Modern"
]
