"""Configuration loading and validation for RockSynth scenes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised when a scene configuration is incomplete or invalid."""


def load_scene_config(path: str | Path) -> dict[str, Any]:
    """Load a JSON scene configuration and validate its minimum contract."""
    config_path = Path(path)
    with config_path.open(encoding="utf-8") as config_file:
        config = json.load(config_file)

    required_sections = ("terrain", "rocks", "camera_rig", "light", "render")
    missing = [section for section in required_sections if section not in config]
    if missing:
        raise ConfigError(f"Missing configuration sections: {', '.join(missing)}")

    if not isinstance(config.get("seed"), int):
        raise ConfigError("seed must be an integer")
    _validate_terrain(config["terrain"])
    _validate_rocks(config["rocks"])
    _validate_camera_rig(config["camera_rig"])
    _validate_light(config["light"])
    _validate_render(config["render"])
    if config["render"].get("physics", True) and any(config["rocks"]["bury_fraction_range"]):
        raise ConfigError("rocks.bury_fraction_range must be [0, 0] when render.physics is enabled")

    return config


def _validate_range(value: Any, name: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, (int, float)) for item in value)
        or value[0] > value[1]
    ):
        raise ConfigError(f"{name} must be an ascending two-value list")


def _validate_terrain(terrain: dict[str, Any]) -> None:
    if terrain.get("kind") != "heightfield":
        raise ConfigError("terrain.kind currently supports only 'heightfield'")
    if terrain.get("size", 0) <= 0:
        raise ConfigError("terrain.size must be positive")
    resolution = terrain.get("resolution", 0)
    if not isinstance(resolution, int) or resolution < 17:
        raise ConfigError("terrain.resolution must be an integer of at least 17")
    if terrain.get("height_amplitude", -1) < 0:
        raise ConfigError("terrain.height_amplitude must be non-negative")
    if terrain.get("octaves", 0) < 1:
        raise ConfigError("terrain.octaves must be at least 1")
    for key in ("gray_range", "roughness_range"):
        _validate_range(terrain.get(key), f"terrain.{key}")

    material = terrain.get("material")
    if not isinstance(material, dict) or not isinstance(material.get("material_id"), str):
        raise ConfigError("terrain.material.material_id must be a string")
    if material.get("tile_size_m", 0) <= 0:
        raise ConfigError("terrain.material.tile_size_m must be positive")


def _validate_rocks(rocks: dict[str, Any]) -> None:
    allowed_options = {
        "count",
        "placement_radius",
        "minimum_gap",
        "support_samples",
        "diameter_range",
        "gray_range",
        "roughness_range",
        "bury_fraction_range",
        "clustering",
        "drop_height",
        "asset_manifest",
    }
    unsupported = sorted(set(rocks).difference(allowed_options))
    if unsupported:
        raise ConfigError(f"Unsupported rock options: {', '.join(unsupported)}")
    if rocks.get("count", 0) < 1:
        raise ConfigError("rocks.count must be at least 1")
    if rocks.get("placement_radius", 0) <= 0:
        raise ConfigError("rocks.placement_radius must be positive")
    if rocks.get("minimum_gap", -1) < 0:
        raise ConfigError("rocks.minimum_gap must be non-negative")
    support_samples = rocks.get("support_samples", 0)
    if not isinstance(support_samples, int) or support_samples < 3 or support_samples % 2 == 0:
        raise ConfigError("rocks.support_samples must be an odd integer of at least 3")
    for key in ("diameter_range", "gray_range", "roughness_range", "bury_fraction_range"):
        _validate_range(rocks.get(key), f"rocks.{key}")
    clustering = rocks.get("clustering", -1)
    if not 0 <= clustering <= 1:
        raise ConfigError("rocks.clustering must be between 0 and 1")
    if not isinstance(rocks.get("asset_manifest"), str):
        raise ConfigError("rocks.asset_manifest must be a string")


def _validate_camera_rig(camera_rig: dict[str, Any]) -> None:
    resolution = camera_rig.get("resolution", [])
    if (
        not isinstance(resolution, list)
        or len(resolution) != 2
        or not all(isinstance(value, int) and value > 0 for value in resolution)
    ):
        raise ConfigError("camera_rig.resolution must contain two positive integers")

    intrinsics = camera_rig.get("intrinsics", {})
    if any(intrinsics.get(key, 0) <= 0 for key in ("fx", "fy")):
        raise ConfigError("camera_rig intrinsics fx and fy must be positive")
    if any(key not in intrinsics for key in ("cx", "cy")):
        raise ConfigError("camera_rig intrinsics must include cx and cy")
    if camera_rig.get("clip_start", 0) <= 0 or camera_rig.get("clip_end", 0) <= camera_rig.get("clip_start", 0):
        raise ConfigError("camera_rig clipping range is invalid")
    if camera_rig.get("edge_margin", -1) < 0:
        raise ConfigError("camera_rig.edge_margin must be non-negative")
    max_background_fraction = camera_rig.get("max_background_fraction", -1)
    if not 0 <= max_background_fraction <= 1:
        raise ConfigError("camera_rig.max_background_fraction must be between 0 and 1")

    poses = camera_rig.get("poses")
    if not isinstance(poses, list) or not poses:
        raise ConfigError("camera_rig.poses must contain at least one pose")
    for index, pose in enumerate(poses):
        for key in ("position_xy", "target_xy"):
            value = pose.get(key, [])
            if not isinstance(value, list) or len(value) != 2:
                raise ConfigError(f"camera_rig.poses[{index}].{key} must contain two values")
        if pose.get("height", 0) <= 0:
            raise ConfigError(f"camera_rig.poses[{index}].height must be positive")


def _validate_light(light: dict[str, Any]) -> None:
    if light.get("type") != "SUN":
        raise ConfigError("light.type currently supports only 'SUN'")
    if light.get("energy", 0) <= 0:
        raise ConfigError("light.energy must be positive")
    if light.get("sun_angle", 0) <= 0:
        raise ConfigError("light.sun_angle must be positive")
    world = light.get("world")
    if not isinstance(world, dict) or world.get("strength", 0) < 0:
        raise ConfigError("light.world.strength must be non-negative")


def _validate_render(render: dict[str, Any]) -> None:
    if render.get("samples", 0) < 1:
        raise ConfigError("render.samples must be positive")
    if render.get("max_terrain_penetration", -1) < 0:
        raise ConfigError("render.max_terrain_penetration must be non-negative")
