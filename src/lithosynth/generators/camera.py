"""Near-ground calibrated camera rig generation."""

from __future__ import annotations

from typing import Any

from lithosynth.core.spec import CameraRigSpec, CameraSpec, TerrainSpec


def generate_camera_rig(config: dict[str, Any], terrain: TerrainSpec) -> CameraRigSpec:
    """Resolve local overhead poses and keep them away from terrain edges."""
    rig_id = str(config.get("rig_id", "local_overhead"))
    width, height = config["resolution"]
    intrinsics_config = config["intrinsics"]
    intrinsics = (
        float(intrinsics_config["fx"]),
        float(intrinsics_config["fy"]),
        float(intrinsics_config["cx"]),
        float(intrinsics_config["cy"]),
    )
    edge_limit = terrain.size / 2.0 - float(config.get("edge_margin", 0.0))

    cameras = []
    for index, pose in enumerate(config["poses"]):
        x, y = (float(value) for value in pose["position_xy"])
        target_x, target_y = (float(value) for value in pose["target_xy"])
        if max(abs(x), abs(y), abs(target_x), abs(target_y)) > edge_limit:
            raise ValueError(
                f"camera pose {index} violates camera_rig.edge_margin; "
                "increase terrain.size or move the local view inward"
            )
        location = (x, y, terrain.height_at(x, y) + float(pose["height"]))
        look_at = (
            target_x,
            target_y,
            terrain.height_at(target_x, target_y) + float(pose.get("target_height", 0.15)),
        )
        cameras.append(
            CameraSpec(
                camera_id=str(pose.get("camera_id", f"camera_{index:03d}")),
                rig_id=rig_id,
                location=location,
                look_at=look_at,
                resolution=(int(width), int(height)),
                intrinsics=intrinsics,
                clip_start=float(config["clip_start"]),
                clip_end=float(config["clip_end"]),
                max_background_fraction=float(config.get("max_background_fraction", 0.01)),
            )
        )

    return CameraRigSpec(rig_id=rig_id, cameras=tuple(cameras))
