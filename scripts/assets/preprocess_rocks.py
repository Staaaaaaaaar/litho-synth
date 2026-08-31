#!/usr/bin/env python3
"""Prepare a locked rock asset with Blender 4.2's stable bpy API.

Run with:
    blender --background --python scripts/assets/preprocess_rocks.py -- --asset polyhaven:rock_09
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from download_assets import (
    DEFAULT_LOCK_FILE,
    DEFAULT_MANIFEST_DIR,
    AssetError,
    asset_key,
    load_assets,
    load_lock,
    select_assets,
    sha256_file,
)

DEFAULT_CACHE_DIR = REPO_ROOT / "assets" / "cache"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "assets" / "prepared"


def blender_arguments(argv: list[str]) -> list[str]:
    return argv[argv.index("--") + 1 :] if "--" in argv else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True, help="rock asset_id or provider:asset_id")
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--collider",
        choices=("convex-hull", "none"),
        default="convex-hull",
        help="collision geometry to create",
    )
    return parser


def _import_source(bpy: Any, source: Path) -> list[Any]:
    before = set(bpy.data.objects)
    suffix = source.suffix.lower()
    if suffix == ".blend":
        with bpy.data.libraries.load(str(source), link=False) as (data_from, data_to):
            data_to.objects = [name for name in data_from.objects]
        for obj in data_to.objects:
            if obj is not None:
                bpy.context.collection.objects.link(obj)
    elif suffix in {".gltf", ".glb"}:
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        raise AssetError(
            f"unsupported rock source {source.name}; extract archives and lock a .blend/.gltf/.glb/.fbx/.obj file"
        )
    return [obj for obj in bpy.data.objects if obj not in before and obj.type == "MESH"]


def _clear_scene(bpy: Any) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def _normalize_meshes(bpy: Any, meshes: list[Any], source_unit_meters: float) -> None:
    from mathutils import Vector

    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    for obj in meshes:
        obj.scale = tuple(component * source_unit_meters for component in obj.scale)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        obj.select_set(False)

    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    center = sum(corners, corners[0].copy() * 0.0) / len(corners)
    for obj in meshes:
        obj.location -= center
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        obj.select_set(False)


def _inspect_meshes(bmesh: Any, meshes: list[Any]) -> dict[str, Any]:
    from mathutils import Vector

    all_corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    minimum = [min(point[index] for point in all_corners) for index in range(3)]
    maximum = [max(point[index] for point in all_corners) for index in range(3)]
    dimensions = [maximum[index] - minimum[index] for index in range(3)]
    area = 0.0
    volume = 0.0
    vertices = 0
    faces = 0
    non_manifold_edges = 0
    degenerate_faces = 0
    for obj in meshes:
        mesh = obj.data
        vertices += len(mesh.vertices)
        faces += len(mesh.polygons)
        area += sum(polygon.area for polygon in mesh.polygons)
        degenerate_faces += sum(1 for polygon in mesh.polygons if polygon.area <= 1e-12)
        bm = bmesh.new()
        bm.from_mesh(mesh)
        non_manifold_edges += sum(1 for edge in bm.edges if not edge.is_manifold)
        if bm.faces:
            try:
                volume += abs(bm.calc_volume(signed=True))
            except ValueError:
                pass
        bm.free()
    return {
        "dimensions_m": dimensions,
        "surface_area_m2": area,
        "volume_m3": volume,
        "mesh_count": len(meshes),
        "vertex_count": vertices,
        "face_count": faces,
        "non_manifold_edge_count": non_manifold_edges,
        "degenerate_face_count": degenerate_faces,
    }


def _create_convex_collider(bpy: Any, bmesh: Any, meshes: list[Any]) -> Any:
    bpy.ops.object.select_all(action="DESELECT")
    duplicates = []
    for obj in meshes:
        duplicate = obj.copy()
        duplicate.data = obj.data.copy()
        bpy.context.collection.objects.link(duplicate)
        duplicate.select_set(True)
        duplicates.append(duplicate)
    bpy.context.view_layer.objects.active = duplicates[0]
    if len(duplicates) > 1:
        bpy.ops.object.join()
    collider = bpy.context.object
    collider.name = "COLLIDER_convex_hull"
    collider.data.name = "COLLIDER_convex_hull_mesh"
    collider.data.materials.clear()

    bm = bmesh.new()
    bm.from_mesh(collider.data)
    result = bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
    unused = list(result.get("geom_unused", [])) + list(result.get("geom_interior", []))
    if unused:
        bmesh.ops.delete(bm, geom=unused, context="VERTS")
    bm.to_mesh(collider.data)
    bm.free()
    collider.data.update()
    collider.display_type = "WIRE"
    collider.hide_render = True
    bpy.context.view_layer.objects.active = collider
    bpy.ops.rigidbody.object_add()
    collider.rigid_body.type = "PASSIVE"
    collider.rigid_body.collision_shape = "CONVEX_HULL"
    return collider


def _validate_expected_size(asset: dict[str, Any], dimensions: list[float]) -> None:
    expected = asset["real_scale"].get("expected_longest_dimension_m")
    longest = max(dimensions)
    if expected and not (float(expected[0]) <= longest <= float(expected[1])):
        raise AssetError(
            f"{asset_key(asset)} longest dimension is {longest:.4g} m, "
            f"outside expected range {expected} m; check source_unit_meters"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(blender_arguments(sys.argv) if argv is None else argv)
    try:
        import bmesh
        import bpy

        matches = select_assets(load_assets(args.manifest_dir), [args.asset])
        asset = matches[0]
        if asset["type"] != "rock":
            raise AssetError(f"{asset_key(asset)} is not a rock")

        lock = load_lock(args.lock_file)
        entry = lock["assets"].get(asset_key(asset))
        if not entry:
            raise AssetError(f"{asset_key(asset)} is not locked; download it first")
        source = args.cache_dir / entry["cache_path"]
        if not source.is_file():
            raise AssetError(f"locked source is missing: {source}")
        actual_hash = sha256_file(source)
        if actual_hash != entry.get("sha256"):
            raise AssetError(f"locked source sha256 mismatch: expected {entry.get('sha256')}, got {actual_hash}")

        _clear_scene(bpy)
        meshes = _import_source(bpy, source)
        if not meshes:
            raise AssetError(f"{source} contains no mesh objects")
        scale = float(asset["real_scale"]["source_unit_meters"])
        if not math.isfinite(scale) or scale <= 0:
            raise AssetError(f"{asset_key(asset)} has invalid source_unit_meters")
        _normalize_meshes(bpy, meshes, scale)
        render_mesh = max(meshes, key=lambda obj: len(obj.data.polygons))
        collision_mesh = min(meshes, key=lambda obj: len(obj.data.polygons))
        inspection = _inspect_meshes(bmesh, [render_mesh])
        _validate_expected_size(asset, inspection["dimensions_m"])
        collider = None
        if args.collider == "convex-hull":
            collider = _create_convex_collider(bpy, bmesh, [collision_mesh])

        target_dir = args.output_dir / asset["provider"] / asset["asset_id"]
        target_dir.mkdir(parents=True, exist_ok=True)
        blend_path = target_dir / "prepared.blend"
        metadata_path = target_dir / "metadata.json"
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)
        metadata = {
            "schema_version": 1,
            "asset": asset_key(asset),
            "source_sha256": actual_hash,
            "source_cache_path": entry["cache_path"],
            "coordinate_system": {"unit": "meter", "up_axis": "Z"},
            "transforms_applied": True,
            "inspection": inspection,
            "lods": [
                {"object": obj.name, "face_count": len(obj.data.polygons)}
                for obj in sorted(meshes, key=lambda item: len(item.data.polygons), reverse=True)
            ],
            "collider": {
                "kind": args.collider,
                "object": collider.name if collider else None,
            },
            "prepared_blend": blend_path.name,
            "blender_version": ".".join(str(part) for part in bpy.app.version),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"prepared {asset_key(asset)} -> {blend_path}")
        return 0
    except (AssetError, KeyError, TypeError, ValueError) as exc:
        print(f"asset preparation error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
