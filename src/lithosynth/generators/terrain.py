"""Terrain parameter generators."""

from __future__ import annotations

import json
from pathlib import Path
from random import Random
from typing import Any

import numpy as np

from lithosynth.core.spec import HeightFieldSpec, MaterialSpec, TerrainSpec


def generate_terrain(config: dict[str, Any], seed: int) -> TerrainSpec:
    """Generate deterministic multi-scale dry terrain."""
    rng = Random(seed)
    gray = rng.uniform(*config["gray_range"])
    roughness = rng.uniform(*config["roughness_range"])
    heights = _generate_height_field(config, seed)
    material_config = config["material"]
    prepared = _load_prepared_material(material_config.get("prepared_metadata"))
    tile_size_m = float(prepared.get("tile_size_m", material_config["tile_size_m"]))
    material = MaterialSpec(
        material_id=material_config["material_id"],
        base_color=(gray, gray * 0.88, gray * 0.72, 1.0),
        roughness=roughness,
        texture_scale=float(config["size"]) / tile_size_m,
        base_color_path=prepared.get("basecolor", material_config.get("base_color_path")),
        roughness_path=prepared.get("roughness", material_config.get("roughness_path")),
        normal_path=prepared.get("normal", material_config.get("normal_path")),
        displacement_path=prepared.get("displacement", material_config.get("displacement_path")),
    )
    height_field = HeightFieldSpec(
        size=float(config["size"]),
        resolution=int(config["resolution"]),
        base_height=float(config.get("base_height", 0.0)),
        heights=tuple(float(value) for value in heights.flat),
    )

    return TerrainSpec(
        kind=config["kind"],
        size=config["size"],
        base_height=config.get("base_height", 0.0),
        base_color=material.base_color,
        roughness=roughness,
        material=material,
        height_field=height_field,
    )


def _generate_height_field(config: dict[str, Any], seed: int) -> np.ndarray:
    resolution = int(config["resolution"])
    octaves = int(config["octaves"])
    persistence = float(config.get("persistence", 0.52))
    generator = np.random.default_rng(seed)
    field = np.zeros((resolution, resolution), dtype=np.float64)
    total_weight = 0.0

    for octave in range(octaves):
        grid_size = 2 ** (octave + 1) + 1
        coarse = generator.normal(size=(grid_size, grid_size))
        weight = persistence**octave
        field += _resize_bilinear(coarse, resolution) * weight
        total_weight += weight

    field /= total_weight
    field -= field.mean()
    standard_deviation = field.std()
    if standard_deviation > 0:
        field /= standard_deviation

    ridge_strength = float(config.get("ridge_strength", 0.25))
    ridges = 1.0 - np.minimum(np.abs(field), 1.0)
    ridges -= ridges.mean()
    field = (1.0 - ridge_strength) * field + ridge_strength * ridges

    slope = config.get("slope", [0.0, 0.0])
    coordinates = np.linspace(-0.5, 0.5, resolution)
    field += float(slope[0]) * coordinates[np.newaxis, :]
    field += float(slope[1]) * coordinates[:, np.newaxis]
    field = _thermal_relaxation(
        field,
        iterations=int(config.get("erosion_iterations", 0)),
        talus=float(config.get("talus", 0.12)),
        rate=float(config.get("erosion_rate", 0.18)),
    )

    field -= field.mean()
    maximum = np.max(np.abs(field))
    if maximum > 0:
        field *= float(config["height_amplitude"]) / maximum
    return field


def _resize_bilinear(values: np.ndarray, resolution: int) -> np.ndarray:
    source_coordinates = np.linspace(0.0, 1.0, values.shape[0])
    target_coordinates = np.linspace(0.0, 1.0, resolution)
    horizontal = np.asarray(
        [np.interp(target_coordinates, source_coordinates, row) for row in values],
        dtype=np.float64,
    )
    return np.asarray(
        [np.interp(target_coordinates, source_coordinates, horizontal[:, column]) for column in range(resolution)],
        dtype=np.float64,
    ).T


def _thermal_relaxation(field: np.ndarray, iterations: int, talus: float, rate: float) -> np.ndarray:
    relaxed = field.copy()
    for _ in range(iterations):
        padded = np.pad(relaxed, 1, mode="edge")
        neighbor_average = (
            padded[:-2, :-2]
            + padded[:-2, 1:-1]
            + padded[:-2, 2:]
            + padded[1:-1, :-2]
            + padded[1:-1, 2:]
            + padded[2:, :-2]
            + padded[2:, 1:-1]
            + padded[2:, 2:]
        ) / 8.0
        excess = np.maximum(np.abs(relaxed - neighbor_average) - talus, 0.0)
        relaxed += np.sign(neighbor_average - relaxed) * excess * rate
    return relaxed


def _load_prepared_material(metadata_path: str | None) -> dict[str, Any]:
    if not metadata_path:
        return {}
    path = Path(metadata_path)
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)
    maps = metadata.get("maps", {})
    prepared: dict[str, Any] = {
        channel: str(value)
        for channel, value in maps.items()
        if isinstance(channel, str) and isinstance(value, str) and Path(value).is_file()
    }
    tile_size = metadata.get("tile_size_m")
    if isinstance(tile_size, list) and tile_size:
        prepared["tile_size_m"] = float(tile_size[0])
    return prepared
