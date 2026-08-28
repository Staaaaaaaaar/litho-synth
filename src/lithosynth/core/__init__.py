"""Shared configuration and scene contracts."""

from lithosynth.core.config import ConfigError, load_scene_config
from lithosynth.core.spec import RockSpec, SceneSpec, TerrainSpec

__all__ = ["ConfigError", "RockSpec", "SceneSpec", "TerrainSpec", "load_scene_config"]
