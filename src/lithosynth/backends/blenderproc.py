"""BlenderProc implementation of the LithoSynth minimal scene."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from lithosynth.core.spec import RockSpec, SceneSpec, TerrainSpec


def render_scene(bproc: Any, config: dict[str, Any], scene: SceneSpec, output_dir: Path) -> None:
    """Build, render, and export one configured scene."""
    bproc.init()

    _create_terrain(bproc, scene.terrain)
    for rock in scene.rocks:
        _create_rock(bproc, rock)

    _configure_light(bproc, config["light"])
    _configure_camera(bproc, config["camera"])

    bproc.renderer.set_max_amount_of_samples(config["render"]["samples"])
    bproc.renderer.set_noise_threshold(config["render"]["noise_threshold"])
    bproc.renderer.enable_depth_output(activate_antialiasing=False)
    bproc.renderer.enable_segmentation_output(
        map_by=["instance", "name", "category_id", "rock_id"],
        default_values={"category_id": 0, "rock_id": 0},
    )

    data = bproc.renderer.render()
    output_dir.mkdir(parents=True, exist_ok=True)
    bproc.writer.write_hdf5(str(output_dir), data, append_to_existing_output=False)
    _write_metadata(config, scene, output_dir)


def _create_terrain(bproc: Any, terrain: TerrainSpec) -> None:
    if terrain.kind != "flat":
        raise NotImplementedError(f"BlenderProc backend does not support terrain kind={terrain.kind!r}")

    terrain_object = bproc.object.create_primitive(
        "PLANE", size=terrain.size, location=[0.0, 0.0, terrain.base_height]
    )
    terrain_object.set_name("terrain")
    terrain_object.set_cp("category_id", 0)
    terrain_object.set_cp("rock_id", 0)
    material = terrain_object.new_material("terrain_material")
    material.set_principled_shader_value("Base Color", terrain.base_color)
    material.set_principled_shader_value("Roughness", terrain.roughness)


def _create_rock(bproc: Any, rock: RockSpec) -> None:
    obj = bproc.object.create_primitive("SPHERE", segments=32, ring_count=16)
    obj.set_name(rock.name)
    obj.set_location(rock.location)
    obj.set_rotation_euler(rock.rotation_euler)
    obj.set_scale(rock.scale)
    obj.set_cp("category_id", 1)
    obj.set_cp("rock_id", rock.rock_id)

    material = obj.new_material(f"{rock.name}_material")
    material.set_principled_shader_value("Base Color", rock.base_color)
    material.set_principled_shader_value("Roughness", rock.roughness)


def _configure_light(bproc: Any, config: dict[str, Any]) -> None:
    light = bproc.types.Light(light_type=config["type"], name="sun")
    light.set_rotation_euler(config["rotation_euler"])
    light.set_energy(config["energy"])
    light.set_color(config["color"])


def _configure_camera(bproc: Any, config: dict[str, Any]) -> None:
    location = np.asarray(config["location"], dtype=float)
    target = np.asarray(config["look_at"], dtype=float)
    rotation = bproc.camera.rotation_from_forward_vec(target - location)
    camera_pose = bproc.math.build_transformation_mat(location, rotation)
    bproc.camera.add_camera_pose(camera_pose)
    bproc.camera.set_resolution(*config["resolution"])


def _write_metadata(config: dict[str, Any], scene: SceneSpec, output_dir: Path) -> None:
    metadata = scene.to_dict() | {
        "format_version": "0.1",
        "backend": {"name": "blenderproc", "version": "2.8.0"},
        "camera": config["camera"],
    }
    with (output_dir / "scene_metadata.json").open("w", encoding="utf-8") as output_file:
        json.dump(metadata, output_file, indent=2)
        output_file.write("\n")
