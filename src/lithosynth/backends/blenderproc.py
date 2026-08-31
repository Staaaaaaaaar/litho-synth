"""BlenderProc implementation of the LithoSynth minimal scene."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from lithosynth.core.spec import CameraSpec, MaterialSpec, RockSpec, SceneSpec, TerrainSpec


def render_scene(bproc: Any, config: dict[str, Any], scene: SceneSpec, output_dir: Path) -> None:
    """Build, physically settle, render, and export one configured scene."""
    bproc.init()

    terrain_object = _create_terrain(bproc, scene.terrain)
    rock_objects = {}
    for rock in scene.rocks:
        rock_objects[rock.rock_id] = _create_rock(bproc, rock)
    _validate_scene_meshes(rock_objects)
    _validate_initial_bvh_clearance(rock_objects)

    if config["render"].get("physics", True):
        _settle_rocks(bproc, terrain_object, rock_objects, config["render"])
    else:
        _apply_burial(rock_objects, scene)
    _resolve_terrain_penetration(
        rock_objects,
        scene,
        float(config["render"].get("max_terrain_penetration", 0.02)),
    )
    _validate_final_clearance(
        rock_objects,
        scene,
        float(config["render"].get("max_terrain_penetration", 0.02)),
    )

    _configure_lighting(bproc, config["light"], config["render"])
    camera_poses = _configure_cameras(bproc, scene.camera_rig.cameras)

    bproc.renderer.set_max_amount_of_samples(config["render"]["samples"])
    bproc.renderer.set_noise_threshold(config["render"]["noise_threshold"])
    bproc.renderer.enable_depth_output(activate_antialiasing=False)
    bproc.renderer.enable_segmentation_output(
        map_by=["instance", "name", "category_id", "rock_id"],
        default_values={"category_id": 0, "rock_id": 0},
    )

    data = bproc.renderer.render()
    background_fractions = _validate_camera_framing(data, scene.camera_rig.cameras)
    output_dir.mkdir(parents=True, exist_ok=True)
    bproc.writer.write_hdf5(str(output_dir), data, append_to_existing_output=False)
    np.save(
        output_dir / "terrain_height.npy",
        np.asarray(scene.terrain.height_field.heights).reshape(
            scene.terrain.height_field.resolution,
            scene.terrain.height_field.resolution,
        ),
    )
    _write_metadata(scene, rock_objects, camera_poses, background_fractions, data, output_dir)


def _create_terrain(bproc: Any, terrain: TerrainSpec) -> Any:
    if terrain.kind != "heightfield":
        raise NotImplementedError(f"BlenderProc backend does not support terrain kind={terrain.kind!r}")

    import bpy

    resolution = terrain.height_field.resolution
    coordinates = np.linspace(-terrain.size / 2.0, terrain.size / 2.0, resolution)
    heights = np.asarray(terrain.height_field.heights).reshape(resolution, resolution)
    vertices = [
        (float(x), float(y), terrain.base_height + float(heights[row, column]))
        for row, y in enumerate(coordinates)
        for column, x in enumerate(coordinates)
    ]
    faces = [
        (
            row * resolution + column,
            row * resolution + column + 1,
            (row + 1) * resolution + column + 1,
            (row + 1) * resolution + column,
        )
        for row in range(resolution - 1)
        for column in range(resolution - 1)
    ]
    mesh = bpy.data.meshes.new("terrain_heightfield_mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    terrain_object = bproc.object.create_from_blender_mesh(mesh, "terrain")
    terrain_object.set_name("terrain")
    terrain_object.set_cp("category_id", 0)
    terrain_object.set_cp("rock_id", 0)
    material = terrain_object.new_material("terrain_material")
    _configure_material(material, terrain.material)
    terrain_object.enable_rigidbody(
        active=False,
        collision_shape="MESH",
        collision_margin=0.002,
        friction=0.85,
    )
    return terrain_object


def _create_rock(bproc: Any, rock: RockSpec) -> Any:
    import bpy

    loaded = bproc.loader.load_blend(rock.asset.mesh_path, obj_types="mesh")
    if not loaded:
        raise RuntimeError(f"Rock asset contains no mesh objects: {rock.asset.mesh_path}")
    render_objects = [item for item in loaded if not item.get_name().startswith("COLLIDER_")]
    if not render_objects:
        raise RuntimeError(f"Rock asset contains no render mesh: {rock.asset.mesh_path}")
    obj = next(
        (item for item in render_objects if "LOD1" in item.get_name()),
        next((item for item in render_objects if "LOD0" in item.get_name()), render_objects[0]),
    )
    for extra_object in loaded:
        if extra_object is obj:
            continue
        # Entity.hide() only sets hide_render. Delete unused LODs and
        # colliders so Blender's debug viewport does not show an
        # unscaled pile of source meshes at the world origin.
        bpy.data.objects.remove(extra_object.blender_obj, do_unlink=True)

    obj.set_name(rock.name)
    obj.set_location(rock.location)
    obj.set_rotation_euler(rock.rotation_euler)
    obj.set_scale(rock.scale)
    obj.set_cp("category_id", 1)
    obj.set_cp("rock_id", rock.rock_id)
    obj.set_cp("asset_id", rock.asset.asset_id)

    if not obj.get_materials():
        raise RuntimeError(f"Rock asset has no material: {rock.asset.mesh_path}")
    obj.enable_rigidbody(
        active=True,
        collision_shape="CONVEX_HULL",
        collision_margin=0.003,
        mass=max(0.05, rock.volume * 2600.0),
        friction=0.78,
        angular_damping=0.65,
        linear_damping=0.35,
    )
    obj.blender_obj.rigid_body.use_deactivation = True
    obj.blender_obj.rigid_body.deactivate_linear_velocity = 0.03
    obj.blender_obj.rigid_body.deactivate_angular_velocity = 0.03
    return obj


def _configure_material(material: Any, spec: MaterialSpec) -> None:
    material.set_principled_shader_value("Base Color", spec.base_color)
    material.set_principled_shader_value("Roughness", spec.roughness)
    material.set_principled_shader_value("Metallic", 0.0)
    texture_paths = {
        "Base Color": spec.base_color_path,
        "Roughness": spec.roughness_path,
    }
    if not any(path and Path(path).is_file() for path in texture_paths.values()) and not (
        spec.normal_path and Path(spec.normal_path).is_file()
    ):
        _configure_fallback_ground_material(material, spec)
        return

    nodes = material.blender_obj.node_tree.nodes
    links = material.blender_obj.node_tree.links
    shader = nodes.get("Principled BSDF")
    texture_coordinate = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (spec.texture_scale, spec.texture_scale, spec.texture_scale)
    links.new(texture_coordinate.outputs["Generated"], mapping.inputs["Vector"])

    for shader_input, path in texture_paths.items():
        if not path or not Path(path).is_file():
            continue
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = __import__("bpy").data.images.load(str(Path(path).resolve()), check_existing=True)
        if shader_input != "Base Color":
            image_node.image.colorspace_settings.name = "Non-Color"
        links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
        links.new(image_node.outputs["Color"], shader.inputs[shader_input])

    normal_output = None
    if spec.normal_path and Path(spec.normal_path).is_file():
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = __import__("bpy").data.images.load(
            str(Path(spec.normal_path).resolve()),
            check_existing=True,
        )
        image_node.image.colorspace_settings.name = "Non-Color"
        normal_map = nodes.new("ShaderNodeNormalMap")
        links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
        links.new(image_node.outputs["Color"], normal_map.inputs["Color"])
        normal_output = normal_map.outputs["Normal"]

    if spec.displacement_path and Path(spec.displacement_path).is_file():
        image_node = nodes.new("ShaderNodeTexImage")
        image_node.image = __import__("bpy").data.images.load(
            str(Path(spec.displacement_path).resolve()),
            check_existing=True,
        )
        image_node.image.colorspace_settings.name = "Non-Color"
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.22
        bump.inputs["Distance"].default_value = 0.035
        links.new(mapping.outputs["Vector"], image_node.inputs["Vector"])
        links.new(image_node.outputs["Color"], bump.inputs["Height"])
        if normal_output is not None:
            links.new(normal_output, bump.inputs["Normal"])
        normal_output = bump.outputs["Normal"]

    if normal_output is not None:
        links.new(normal_output, shader.inputs["Normal"])


def _configure_fallback_ground_material(material: Any, spec: MaterialSpec) -> None:
    nodes = material.blender_obj.node_tree.nodes
    links = material.blender_obj.node_tree.links
    shader = nodes.get("Principled BSDF")
    texture_coordinate = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 7.0 * spec.texture_scale
    noise.inputs["Detail"].default_value = 7.0
    noise.inputs["Roughness"].default_value = 0.72
    color_ramp = nodes.new("ShaderNodeValToRGB")
    dark = tuple(max(0.0, channel * 0.62) for channel in spec.base_color[:3]) + (1.0,)
    light = tuple(min(1.0, channel * 1.35) for channel in spec.base_color[:3]) + (1.0,)
    color_ramp.color_ramp.elements[0].color = dark
    color_ramp.color_ramp.elements[1].color = light
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.32
    bump.inputs["Distance"].default_value = 0.12
    links.new(texture_coordinate.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])


def _settle_rocks(
    bproc: Any,
    terrain_object: Any,
    rock_objects: dict[int, Any],
    render_config: dict[str, Any],
) -> None:
    import bpy

    rigid_body_world = bpy.context.scene.rigidbody_world
    if rigid_body_world is not None:
        rigid_body_world.substeps_per_frame = int(render_config.get("physics_substeps", 10))
        rigid_body_world.solver_iterations = int(render_config.get("physics_solver_iterations", 20))
    bproc.object.simulate_physics_and_fix_final_poses(
        min_simulation_time=float(render_config.get("physics_min_time", 2.0)),
        max_simulation_time=float(render_config.get("physics_max_time", 10.0)),
        check_object_interval=1.0,
    )
    terrain_object.disable_rigidbody()
    for rock_object in rock_objects.values():
        rock_object.disable_rigidbody()


def _validate_initial_bvh_clearance(rock_objects: dict[int, Any]) -> None:
    from blenderproc.python.utility.CollisionUtility import CollisionUtility

    cache = {}
    objects = list(rock_objects.items())
    for index, (rock_id, obj) in enumerate(objects):
        for other_id, other in objects[index + 1 :]:
            intersects, cache = CollisionUtility.check_mesh_intersection(
                obj,
                other,
                skip_inside_check=True,
                bvh_cache=cache,
            )
            if intersects:
                raise RuntimeError(f"Initial BVH overlap between rocks {rock_id} and {other_id}")


def _validate_scene_meshes(rock_objects: dict[int, Any]) -> None:
    """Ensure imported source LODs cannot leak into rendering or the GUI."""
    import bpy

    expected_names = {"terrain"} | {obj.get_name() for obj in rock_objects.values()}
    unexpected = sorted(
        obj.name
        for obj in bpy.context.scene.objects
        if obj.type == "MESH" and obj.name not in expected_names
    )
    if unexpected:
        raise RuntimeError(f"Unexpected source meshes remain in scene: {unexpected}")


def _validate_final_clearance(
    rock_objects: dict[int, Any],
    scene: SceneSpec,
    max_terrain_penetration: float,
) -> None:
    """Reject rock-rock intersections and terrain penetration after settling."""
    from blenderproc.python.utility.CollisionUtility import CollisionUtility

    cache = {}
    objects = list(rock_objects.items())
    for index, (rock_id, obj) in enumerate(objects):
        for other_id, other in objects[index + 1 :]:
            intersects, cache = CollisionUtility.check_mesh_intersection(
                obj,
                other,
                # Scanned assets are not guaranteed watertight; triangle
                # intersection remains reliable while inside tests do not.
                skip_inside_check=True,
                bvh_cache=cache,
            )
            if intersects:
                raise RuntimeError(f"Settled rock overlap between rocks {rock_id} and {other_id}")

        max_penetration = _terrain_penetration(obj, scene.terrain)
        if max_penetration > max_terrain_penetration:
            raise RuntimeError(
                f"rock {rock_id} penetrates terrain by {max_penetration:.4f} m "
                f"(limit {max_terrain_penetration:.4f} m)"
            )


def _resolve_terrain_penetration(
    rock_objects: dict[int, Any],
    scene: SceneSpec,
    max_terrain_penetration: float,
) -> None:
    """Lift each settled rock only enough to satisfy the exact terrain mesh."""
    for obj in rock_objects.values():
        penetration = _terrain_penetration(obj, scene.terrain)
        correction = max(0.0, penetration - max_terrain_penetration)
        if correction > 0:
            location = obj.get_location()
            location[2] += correction + 1e-4
            obj.set_location(location)


def _terrain_penetration(obj: Any, terrain: TerrainSpec) -> float:
    import bpy

    evaluated = obj.blender_obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    try:
        world_matrix = obj.blender_obj.matrix_world
        penetrations = []
        for vertex in mesh.vertices:
            world_vertex = world_matrix @ vertex.co
            penetrations.append(
                terrain.height_at(float(world_vertex.x), float(world_vertex.y))
                - float(world_vertex.z)
            )
        return max(penetrations, default=0.0)
    finally:
        evaluated.to_mesh_clear()


def _apply_burial(rock_objects: dict[int, Any], scene: SceneSpec) -> None:
    for rock in scene.rocks:
        obj = rock_objects[rock.rock_id]
        location = obj.get_location()
        location[2] -= rock.dimensions[2] * rock.bury_fraction
        obj.set_location(location)
        terrain_height = scene.terrain.height_at(float(location[0]), float(location[1]))
        if location[2] - terrain_height > rock.dimensions[2] * 1.25 + 0.1:
            raise RuntimeError(f"{rock.name} remains suspended above the terrain")
        if terrain_height - location[2] > rock.dimensions[2]:
            raise RuntimeError(f"{rock.name} penetrates too deeply into the terrain")


def _configure_lighting(bproc: Any, config: dict[str, Any], render_config: dict[str, Any]) -> None:
    import bpy

    light = bproc.types.Light(light_type=config["type"], name="sun")
    light.set_rotation_euler(config["rotation_euler"])
    light.set_energy(config["energy"])
    light.set_color(config["color"])
    light.blender_obj.data.angle = float(config["sun_angle"])

    world = bpy.context.scene.world or bpy.data.worlds.new("LithoSynth World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = float(config["world"].get("sun_elevation", 0.6))
    sky.sun_rotation = float(config["world"].get("sun_rotation", 2.4))
    sky.altitude = float(config["world"].get("altitude", 0.0))
    sky.air_density = float(config["world"].get("air_density", 1.0))
    sky.dust_density = float(config["world"].get("dust_density", 1.0))
    background = nodes.new("ShaderNodeBackground")
    background.inputs["Strength"].default_value = float(config["world"]["strength"])
    output = nodes.new("ShaderNodeOutputWorld")
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])

    view_settings = bpy.context.scene.view_settings
    view_settings.view_transform = str(render_config.get("view_transform", "AgX"))
    view_settings.look = str(render_config.get("look", "AgX - Medium High Contrast"))
    view_settings.exposure = float(render_config.get("exposure", 0.0))


def _configure_cameras(bproc: Any, cameras: tuple[CameraSpec, ...]) -> list[np.ndarray]:
    first = cameras[0]
    fx, fy, cx, cy = first.intrinsics
    intrinsics = np.asarray(((fx, 0.0, cx), (0.0, fy, cy), (0.0, 0.0, 1.0)))
    bproc.camera.set_intrinsics_from_K_matrix(
        intrinsics,
        *first.resolution,
        clip_start=first.clip_start,
        clip_end=first.clip_end,
    )

    poses = []
    for camera in cameras:
        if camera.resolution != first.resolution or camera.intrinsics != first.intrinsics:
            raise ValueError("All cameras in one render batch must share intrinsics and resolution")
        location = np.asarray(camera.location, dtype=float)
        target = np.asarray(camera.look_at, dtype=float)
        rotation = bproc.camera.rotation_from_forward_vec(target - location)
        camera_pose = bproc.math.build_transformation_mat(location, rotation)
        bproc.camera.add_camera_pose(camera_pose)
        poses.append(camera_pose)
    return poses


def _write_metadata(
    scene: SceneSpec,
    rock_objects: dict[int, Any],
    camera_poses: list[np.ndarray],
    background_fractions: list[float],
    render_data: dict[str, Any],
    output_dir: Path,
) -> None:
    scene_data = scene.to_dict()
    rock_records = []
    for rock in scene.rocks:
        record = rock.to_dict()
        obj = rock_objects[rock.rock_id]
        record["location"] = obj.get_location().tolist()
        record["rotation_euler"] = obj.get_rotation_euler().tolist()
        measured = _measure_object(obj)
        if measured is not None:
            record.update(measured)
        rock_records.append(record)
    scene_data["rocks"] = rock_records

    frames = []
    segmentation_frames = render_data["rock_id_segmaps"]
    for frame_index, (camera, camera_pose, background_fraction, segmentation) in enumerate(
        zip(
            scene.camera_rig.cameras,
            camera_poses,
            background_fractions,
            segmentation_frames,
            strict=True,
        )
    ):
        frames.append(
            {
                "frame_index": frame_index,
                "camera_id": camera.camera_id,
                "camera": camera.to_dict(),
                "T_world_camera": np.asarray(camera_pose).tolist(),
                "background_fraction": background_fraction,
                "visible_rocks": _visible_rock_records(np.asarray(segmentation)),
            }
        )

    metadata = scene_data | {
        "format_version": "0.1.1",
        "backend": {"name": "blenderproc", "version": "2.8.0"},
        "terrain_height_file": "terrain_height.npy",
        "frames": frames,
    }
    with (output_dir / "scene_metadata.json").open("w", encoding="utf-8") as output_file:
        json.dump(metadata, output_file, indent=2)
        output_file.write("\n")


def _validate_camera_framing(
    render_data: dict[str, Any],
    cameras: tuple[CameraSpec, ...],
) -> list[float]:
    fractions = []
    for camera, depth in zip(cameras, render_data["depth"], strict=True):
        depth_array = np.asarray(depth)
        background_fraction = float(
            np.count_nonzero(~np.isfinite(depth_array) | (depth_array >= camera.clip_end))
            / depth_array.size
        )
        if background_fraction > camera.max_background_fraction:
            raise RuntimeError(
                f"{camera.camera_id} contains {background_fraction:.2%} background "
                f"(limit {camera.max_background_fraction:.2%})"
            )
        fractions.append(background_fraction)
    return fractions


def _measure_object(obj: Any) -> dict[str, Any] | None:
    try:
        import bmesh
        import bpy

        evaluated = obj.blender_obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        bmesh_data = bmesh.new()
        bmesh_data.from_mesh(mesh)
        bmesh_data.transform(obj.blender_obj.matrix_world)
        volume = abs(float(bmesh_data.calc_volume(signed=False)))
        surface_area = float(sum(face.calc_area() for face in bmesh_data.faces))
        dimensions = tuple(float(value) for value in obj.blender_obj.dimensions)
        bmesh_data.free()
        evaluated.to_mesh_clear()
        if volume <= 0:
            return None
        return {"dimensions": dimensions, "surface_area": surface_area, "volume": volume}
    except (AttributeError, RuntimeError, ValueError):
        return None


def _visible_rock_records(segmentation: np.ndarray) -> list[dict[str, Any]]:
    records = []
    image_pixels = int(segmentation.size)
    for rock_id in (int(value) for value in np.unique(segmentation) if int(value) > 0):
        rows, columns = np.where(segmentation == rock_id)
        x_min, x_max = int(columns.min()), int(columns.max())
        y_min, y_max = int(rows.min()), int(rows.max())
        visible_pixels = int(rows.size)
        records.append(
            {
                "rock_id": rock_id,
                "visible_pixels": visible_pixels,
                "image_fraction": visible_pixels / image_pixels,
                "bbox_xywh": [x_min, y_min, x_max - x_min + 1, y_max - y_min + 1],
            }
        )
    return records
