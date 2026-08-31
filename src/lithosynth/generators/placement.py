"""Reusable spatial placement algorithms."""

from __future__ import annotations

from math import cos, hypot, pi, sin
from random import Random


def sample_non_overlapping_positions(
    footprints: list[float],
    placement_radius: float,
    minimum_gap: float,
    rng: Random,
    clustering: float = 0.0,
) -> list[tuple[float, float]]:
    """Place circular footprints with optional natural-looking clustering."""
    positions: list[tuple[float, float]] = []
    max_attempts = max(1000, len(footprints) * 200)
    cluster_count = max(1, round(len(footprints) ** 0.5 / 2.0))
    cluster_centers = [_sample_disk(placement_radius * 0.65, rng) for _ in range(cluster_count)]

    for footprint in footprints:
        for _ in range(max_attempts):
            if clustering > 0 and rng.random() < clustering:
                center = rng.choice(cluster_centers)
                spread = placement_radius * (0.08 + 0.22 * (1.0 - clustering))
                candidate = (rng.gauss(center[0], spread), rng.gauss(center[1], spread))
            else:
                candidate = _sample_disk(placement_radius, rng)
            if hypot(*candidate) + footprint > placement_radius:
                continue
            if _has_clearance(candidate, footprint, positions, footprints[: len(positions)], minimum_gap):
                positions.append(candidate)
                break
        else:
            raise ValueError(
                "Could not place all rocks without overlap; enlarge placement_radius or reduce rock count/size"
            )

    return positions


def _sample_disk(radius: float, rng: Random) -> tuple[float, float]:
    angle = rng.uniform(0.0, 2.0 * pi)
    radial_distance = radius * rng.random() ** 0.5
    return radial_distance * cos(angle), radial_distance * sin(angle)


def _has_clearance(
    candidate: tuple[float, float],
    footprint: float,
    positions: list[tuple[float, float]],
    placed_footprints: list[float],
    minimum_gap: float,
) -> bool:
    return all(
        hypot(candidate[0] - position[0], candidate[1] - position[1])
        >= footprint + other_footprint + minimum_gap
        for position, other_footprint in zip(positions, placed_footprints, strict=True)
    )
