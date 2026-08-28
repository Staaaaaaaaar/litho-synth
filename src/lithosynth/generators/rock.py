"""Rock geometry and appearance parameter generators."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from random import Random
from typing import Any

from lithosynth.core.spec import RockSpec, TerrainSpec
from lithosynth.generators.placement import sample_non_overlapping_positions


@dataclass(frozen=True)
class _RockParameters:
    scale: tuple[float, float, float]
    rotation_z: float
    base_color: tuple[float, float, float, float]
    roughness: float


def generate_rocks(config: dict[str, Any], terrain: TerrainSpec, seed: int) -> tuple[RockSpec, ...]:
    """Generate rock properties, then place them on the generated terrain."""
    rng = Random(seed)
    parameters = [_sample_parameters(config, rng) for _ in range(config["count"])]
    footprints = [max(item.scale[0], item.scale[1]) for item in parameters]
    positions = sample_non_overlapping_positions(
        footprints,
        placement_radius=config["placement_radius"],
        minimum_gap=config["minimum_gap"],
        rng=rng,
    )

    rocks = []
    for rock_id, (item, position) in enumerate(zip(parameters, positions, strict=True), start=1):
        x, y = position
        z = terrain.height_at(x, y) + item.scale[2]
        rocks.append(
            RockSpec(
                rock_id=rock_id,
                name=f"rock_{rock_id:03d}",
                location=(x, y, z),
                rotation_euler=(0.0, 0.0, item.rotation_z),
                scale=item.scale,
                dimensions=tuple(value * 2.0 for value in item.scale),
                base_color=item.base_color,
                roughness=item.roughness,
            )
        )

    return tuple(rocks)


def _sample_parameters(config: dict[str, Any], rng: Random) -> _RockParameters:
    horizontal = rng.uniform(*config["horizontal_scale_range"])
    scale = (
        horizontal * rng.uniform(0.8, 1.2),
        horizontal * rng.uniform(0.8, 1.2),
        rng.uniform(*config["vertical_scale_range"]),
    )
    gray = rng.uniform(*config["gray_range"])
    return _RockParameters(
        scale=scale,
        rotation_z=rng.uniform(0.0, 2.0 * pi),
        base_color=(gray, gray * rng.uniform(0.9, 1.0), gray * rng.uniform(0.8, 0.95), 1.0),
        roughness=rng.uniform(*config["roughness_range"]),
    )
