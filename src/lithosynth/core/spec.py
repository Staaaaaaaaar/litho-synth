"""Backend-neutral scene descriptions produced by LithoSynth generators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from math import floor
from typing import Any


@dataclass(frozen=True)
class MaterialSpec:
    """Physically based material parameters and optional texture maps."""

    material_id: str
    base_color: tuple[float, float, float, float]
    roughness: float
    texture_scale: float
    base_color_path: str | None = None
    roughness_path: str | None = None
    normal_path: str | None = None
    displacement_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HeightFieldSpec:
    """Regular square height field with world-space sampling."""

    size: float
    resolution: int
    base_height: float
    heights: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.resolution < 2 or len(self.heights) != self.resolution**2:
            raise ValueError("height field data does not match its resolution")

    @property
    def digest(self) -> str:
        payload = ",".join(f"{value:.9g}" for value in self.heights)
        return sha256(payload.encode()).hexdigest()

    def height_at(self, x: float, y: float) -> float:
        """Bilinearly interpolate the height field in world coordinates."""
        half_size = self.size / 2.0
        normalized_x = (x + half_size) / self.size
        normalized_y = (y + half_size) / self.size
        column = min(max(normalized_x * (self.resolution - 1), 0.0), self.resolution - 1)
        row = min(max(normalized_y * (self.resolution - 1), 0.0), self.resolution - 1)
        column0 = floor(column)
        row0 = floor(row)
        column1 = min(column0 + 1, self.resolution - 1)
        row1 = min(row0 + 1, self.resolution - 1)
        tx = column - column0
        ty = row - row0

        def value(sample_row: int, sample_column: int) -> float:
            return self.heights[sample_row * self.resolution + sample_column]

        lower = value(row0, column0) * (1.0 - tx) + value(row0, column1) * tx
        upper = value(row1, column0) * (1.0 - tx) + value(row1, column1) * tx
        return self.base_height + lower * (1.0 - ty) + upper * ty

    def to_dict(self) -> dict[str, Any]:
        return {
            "size": self.size,
            "resolution": self.resolution,
            "base_height": self.base_height,
            "minimum": min(self.heights),
            "maximum": max(self.heights),
            "sha256": self.digest,
        }


@dataclass(frozen=True)
class TerrainSpec:
    """Known parameters describing generated terrain."""

    kind: str
    size: float
    base_height: float
    base_color: tuple[float, float, float, float]
    roughness: float
    material: MaterialSpec
    height_field: HeightFieldSpec

    def height_at(self, x: float, y: float) -> float:
        return self.height_field.height_at(x, y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "size": self.size,
            "base_height": self.base_height,
            "base_color": self.base_color,
            "roughness": self.roughness,
            "material": self.material.to_dict(),
            "height_field": self.height_field.to_dict(),
        }


@dataclass(frozen=True)
class RockAssetSpec:
    """Normalized source asset used by a rock instance."""

    asset_id: str
    source: str
    mesh_path: str
    native_dimensions: tuple[float, float, float]
    native_surface_area: float
    native_volume: float
    license: str
    sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RockSpec:
    """Known parameters describing one generated rock."""

    rock_id: int
    name: str
    location: tuple[float, float, float]
    rotation_euler: tuple[float, float, float]
    scale: tuple[float, float, float]
    dimensions: tuple[float, float, float]
    base_color: tuple[float, float, float, float]
    roughness: float
    asset: RockAssetSpec
    surface_area: float
    volume: float
    bury_fraction: float

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["asset"] = self.asset.to_dict()
        return data


@dataclass(frozen=True)
class CameraSpec:
    """One calibrated camera pose with an allowed sky/background budget."""

    camera_id: str
    rig_id: str
    location: tuple[float, float, float]
    look_at: tuple[float, float, float]
    resolution: tuple[int, int]
    intrinsics: tuple[float, float, float, float]
    clip_start: float
    clip_end: float
    max_background_fraction: float

    def to_dict(self) -> dict[str, Any]:
        fx, fy, cx, cy = self.intrinsics
        return asdict(self) | {
            "K": ((fx, 0.0, cx), (0.0, fy, cy), (0.0, 0.0, 1.0)),
        }


@dataclass(frozen=True)
class CameraRigSpec:
    """A calibrated collection of near-ground camera poses."""

    rig_id: str
    cameras: tuple[CameraSpec, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rig_id": self.rig_id,
            "cameras": [camera.to_dict() for camera in self.cameras],
        }


@dataclass(frozen=True)
class SceneSpec:
    """Complete generated scene content independent of a rendering engine."""

    seed: int
    terrain: TerrainSpec
    rocks: tuple[RockSpec, ...]
    camera_rig: CameraRigSpec

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "terrain": self.terrain.to_dict(),
            "rocks": [rock.to_dict() for rock in self.rocks],
            "camera_rig": self.camera_rig.to_dict(),
        }
