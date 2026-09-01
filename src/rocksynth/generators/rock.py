"""Rock geometry and appearance parameter generators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import cos, exp, log, pi, sin
from pathlib import Path
from random import Random
from typing import Any

from rocksynth.core.spec import RockAssetSpec, RockSpec, TerrainSpec
from rocksynth.generators.placement import sample_non_overlapping_positions


@dataclass(frozen=True)
class _RockParameters:
    asset: RockAssetSpec
    scale: tuple[float, float, float]
    dimensions: tuple[float, float, float]
    rotation_z: float
    base_color: tuple[float, float, float, float]
    roughness: float
    surface_area: float
    volume: float
    bury_fraction: float


def generate_rocks(config: dict[str, Any], terrain: TerrainSpec, seed: int) -> tuple[RockSpec, ...]:
    """Instantiate prepared rock assets, then place them on the terrain."""
    rng = Random(seed)
    scanned_assets = _load_prepared_assets(config["asset_manifest"])
    if not scanned_assets:
        raise FileNotFoundError(
            "No prepared scanned rocks are available; run the asset download and preprocessing steps"
        )
    parameters = [_sample_parameters(config, scanned_assets, rng) for _ in range(config["count"])]
    footprints = [max(item.dimensions[0], item.dimensions[1]) / 2.0 for item in parameters]
    positions = sample_non_overlapping_positions(
        footprints,
        placement_radius=config["placement_radius"],
        minimum_gap=config["minimum_gap"],
        rng=rng,
        clustering=float(config.get("clustering", 0.0)),
    )

    rocks = []
    for rock_id, (item, position) in enumerate(zip(parameters, positions, strict=True), start=1):
        x, y = position
        support_height = _terrain_support_height(
            terrain,
            position,
            item.dimensions,
            item.rotation_z,
            int(config.get("support_samples", 5)),
        )
        z = support_height + item.dimensions[2] / 2.0 + float(config.get("drop_height", 0.08))
        rocks.append(
            RockSpec(
                rock_id=rock_id,
                name=f"rock_{rock_id:03d}",
                location=(x, y, z),
                rotation_euler=(0.0, 0.0, item.rotation_z),
                scale=item.scale,
                dimensions=item.dimensions,
                base_color=item.base_color,
                roughness=item.roughness,
                asset=item.asset,
                surface_area=item.surface_area,
                volume=item.volume,
                bury_fraction=item.bury_fraction,
            )
        )

    return tuple(rocks)


def _terrain_support_height(
    terrain: TerrainSpec,
    position: tuple[float, float],
    dimensions: tuple[float, float, float],
    rotation_z: float,
    samples_per_axis: int,
) -> float:
    """Find the highest terrain point under a rotated rock footprint."""
    half_x = dimensions[0] / 2.0
    half_y = dimensions[1] / 2.0
    denominator = samples_per_axis - 1
    cosine = cos(rotation_z)
    sine = sin(rotation_z)
    heights = []
    for row in range(samples_per_axis):
        local_y = -half_y + 2.0 * half_y * row / denominator
        for column in range(samples_per_axis):
            local_x = -half_x + 2.0 * half_x * column / denominator
            world_x = position[0] + local_x * cosine - local_y * sine
            world_y = position[1] + local_x * sine + local_y * cosine
            heights.append(terrain.height_at(world_x, world_y))
    return max(heights)


def _sample_parameters(
    config: dict[str, Any],
    scanned_assets: tuple[RockAssetSpec, ...],
    rng: Random,
) -> _RockParameters:
    asset = rng.choice(scanned_assets)
    diameter = exp(rng.uniform(log(config["diameter_range"][0]), log(config["diameter_range"][1])))
    native_diameter = max(asset.native_dimensions[0], asset.native_dimensions[1])
    uniform_scale = diameter / native_diameter
    scale = (uniform_scale, uniform_scale, uniform_scale)
    dimensions = tuple(value * uniform_scale for value in asset.native_dimensions)
    volume = asset.native_volume * uniform_scale**3
    surface_area = asset.native_surface_area * uniform_scale**2

    gray = rng.uniform(*config["gray_range"])
    return _RockParameters(
        asset=asset,
        scale=scale,
        dimensions=dimensions,
        rotation_z=rng.uniform(0.0, 2.0 * pi),
        base_color=(gray, gray * rng.uniform(0.9, 1.0), gray * rng.uniform(0.8, 0.95), 1.0),
        roughness=rng.uniform(*config["roughness_range"]),
        surface_area=surface_area,
        volume=volume,
        bury_fraction=rng.uniform(*config["bury_fraction_range"]),
    )

def _load_prepared_assets(manifest_path: str) -> tuple[RockAssetSpec, ...]:
    path = Path(manifest_path)
    if not path.is_file():
        return ()
    with path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    records = manifest.get("assets", manifest if isinstance(manifest, list) else [])
    assets_root = path.parent.parent
    assets = []
    for record in records:
        prepared_directory = assets_root / "prepared" / record["provider"] / record["asset_id"]
        prepared_path = Path(record.get("prepared_path", prepared_directory / "prepared.blend"))
        metadata_path = Path(record.get("prepared_metadata", prepared_directory / "metadata.json"))
        if not prepared_path.is_file() or not metadata_path.is_file():
            continue
        with metadata_path.open(encoding="utf-8") as metadata_file:
            metadata = json.load(metadata_file)
        inspection = metadata.get("inspection", metadata)
        watertight = inspection.get("non_manifold_edge_count", 1) == 0
        volume = float(inspection.get("volume_m3", inspection.get("volume", 0.0)))
        if not watertight or volume <= 0:
            continue
        dimensions = inspection.get("dimensions_m") or inspection.get("dimensions")
        surface_area = inspection.get("surface_area_m2", inspection.get("surface_area"))
        if dimensions is None or surface_area is None:
            continue
        assets.append(
            RockAssetSpec(
                asset_id=str(record["asset_id"]),
                source=str(record.get("provider", "scan")),
                mesh_path=str(prepared_path),
                native_dimensions=tuple(float(value) for value in dimensions),
                native_surface_area=float(surface_area),
                native_volume=volume,
                license=str(record.get("license", "unknown")),
                sha256=metadata.get("source_sha256", record.get("sha256")),
            )
        )
    return tuple(assets)
