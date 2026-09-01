"""Composition of terrain, rock, and placement generators."""

from __future__ import annotations

from random import Random
from typing import Any

from rocksynth.core.spec import SceneSpec
from rocksynth.generators.camera import generate_camera_rig
from rocksynth.generators.rock import generate_rocks
from rocksynth.generators.terrain import generate_terrain


def generate_scene(config: dict[str, Any]) -> SceneSpec:
    """Generate a backend-neutral scene specification."""
    seed_source = Random(config["seed"])
    terrain_seed = seed_source.getrandbits(64)
    rocks_seed = seed_source.getrandbits(64)

    terrain = generate_terrain(config["terrain"], terrain_seed)
    rocks = generate_rocks(config["rocks"], terrain, rocks_seed)
    camera_rig = generate_camera_rig(config["camera_rig"], terrain)
    return SceneSpec(seed=config["seed"], terrain=terrain, rocks=rocks, camera_rig=camera_rig)
