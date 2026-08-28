"""Terrain parameter generators."""

from __future__ import annotations

from random import Random
from typing import Any

from lithosynth.core.spec import TerrainSpec


def generate_terrain(config: dict[str, Any], seed: int) -> TerrainSpec:
    """Generate a terrain specification from configured distributions."""
    rng = Random(seed)
    gray = rng.uniform(*config["gray_range"])
    roughness = rng.uniform(*config["roughness_range"])

    return TerrainSpec(
        kind=config["kind"],
        size=config["size"],
        base_height=config.get("base_height", 0.0),
        base_color=(gray, gray * 0.9, gray * 0.8, 1.0),
        roughness=roughness,
    )
