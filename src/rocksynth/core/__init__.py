"""Shared configuration and scene contracts."""

from rocksynth.core.config import ConfigError, load_scene_config
from rocksynth.core.spec import (
    CameraRigSpec,
    CameraSpec,
    HeightFieldSpec,
    MaterialSpec,
    RockAssetSpec,
    RockSpec,
    SceneSpec,
    TerrainSpec,
)

__all__ = [
    "CameraRigSpec",
    "CameraSpec",
    "ConfigError",
    "HeightFieldSpec",
    "MaterialSpec",
    "RockAssetSpec",
    "RockSpec",
    "SceneSpec",
    "TerrainSpec",
    "load_scene_config",
]
