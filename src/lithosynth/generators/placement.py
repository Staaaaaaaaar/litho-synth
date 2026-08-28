"""Reusable spatial placement algorithms."""

from __future__ import annotations

from math import cos, hypot, pi, sin
from random import Random


def sample_non_overlapping_positions(
    footprints: list[float], placement_radius: float, minimum_gap: float, rng: Random
) -> list[tuple[float, float]]:
    """Place circular footprints inside a disk using rejection sampling."""
    positions: list[tuple[float, float]] = []
    max_attempts = max(1000, len(footprints) * 200)

    for footprint in footprints:
        for _ in range(max_attempts):
            angle = rng.uniform(0.0, 2.0 * pi)
            radius = placement_radius * rng.random() ** 0.5
            candidate = (radius * cos(angle), radius * sin(angle))
            if _has_clearance(candidate, footprint, positions, footprints[: len(positions)], minimum_gap):
                positions.append(candidate)
                break
        else:
            raise ValueError(
                "Could not place all rocks without overlap; enlarge placement_radius or reduce rock count/size"
            )

    return positions


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
