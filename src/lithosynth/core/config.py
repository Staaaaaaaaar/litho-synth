"""Configuration loading and validation for LithoSynth scenes."""

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

    required_sections = ("terrain", "rocks", "camera", "light", "render")
    missing = [section for section in required_sections if section not in config]
    if missing:
        raise ConfigError(f"Missing configuration sections: {', '.join(missing)}")

    if not isinstance(config.get("seed"), int):
        raise ConfigError("seed must be an integer")
    if config["terrain"].get("kind") != "flat":
        raise ConfigError("terrain.kind currently supports only 'flat'")
    if config["terrain"].get("size", 0) <= 0:
        raise ConfigError("terrain.size must be positive")
    if config["rocks"].get("count", 0) < 1:
        raise ConfigError("rocks.count must be at least 1")

    resolution = config["camera"].get("resolution", [])
    if len(resolution) != 2 or any(value < 1 for value in resolution):
        raise ConfigError("camera.resolution must contain two positive integers")

    for key in ("horizontal_scale_range", "vertical_scale_range", "gray_range", "roughness_range"):
        _validate_range(config["rocks"].get(key), f"rocks.{key}")
    for key in ("gray_range", "roughness_range"):
        _validate_range(config["terrain"].get(key), f"terrain.{key}")

    return config


def _validate_range(value: Any, name: str) -> None:
    if not isinstance(value, list) or len(value) != 2 or value[0] > value[1]:
        raise ConfigError(f"{name} must be an ascending two-value list")
