"""Backend-neutral scene descriptions produced by LithoSynth generators."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TerrainSpec:
    """Known parameters describing generated terrain."""

    kind: str
    size: float
    base_height: float
    base_color: tuple[float, float, float, float]
    roughness: float

    def height_at(self, _x: float, _y: float) -> float:
        if self.kind != "flat":
            raise NotImplementedError(f"Terrain height queries are not implemented for kind={self.kind!r}")
        return self.base_height

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SceneSpec:
    """Complete generated scene content independent of a rendering engine."""

    seed: int
    terrain: TerrainSpec
    rocks: tuple[RockSpec, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "terrain": self.terrain.to_dict(),
            "rocks": [rock.to_dict() for rock in self.rocks],
        }
