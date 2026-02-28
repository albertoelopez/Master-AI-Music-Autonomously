"""Configuration settings for Suno AI Studio mastering agent."""
from pydantic import BaseModel
from typing import Optional


class SunoConfig(BaseModel):
    """Suno AI Studio configuration."""
    base_url: str = "https://suno.com"
    studio_url: str = "https://suno.com/studio"
    chrome_debug_port: int = 9222
    timeout_ms: int = 30000


class MasteringPreset(BaseModel):
    """Audio mastering preset configuration."""
    name: str
    description: Optional[str] = None
    # Add Suno-specific mastering parameters as we discover them
    loudness: Optional[float] = None
    clarity: Optional[float] = None
    warmth: Optional[float] = None


# Default configuration
DEFAULT_CONFIG = SunoConfig()

# Preset templates - these will be populated based on Suno's actual interface
MASTERING_PRESETS = {
    "default": MasteringPreset(
        name="default", description="Balanced mastering",
        loudness=0.5, clarity=0.5, warmth=0.5
    ),
    "loud": MasteringPreset(
        name="loud", description="Maximized loudness",
        loudness=0.9, clarity=0.6, warmth=0.4
    ),
    "warm": MasteringPreset(
        name="warm", description="Warm, analog-style mastering",
        loudness=0.5, clarity=0.4, warmth=0.8
    ),
    "bright": MasteringPreset(
        name="bright", description="Bright, clear mastering",
        loudness=0.5, clarity=0.8, warmth=0.3
    ),
}
