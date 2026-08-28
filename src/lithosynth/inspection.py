"""Validation and visualization helpers for generated scene outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import matplotlib.pyplot as plt
import numpy as np

REQUIRED_DATASETS = {
    "colors",
    "depth",
    "instance_attribute_maps",
    "instance_segmaps",
    "rock_id_segmaps",
}


class OutputValidationError(ValueError):
    """Raised when generated output is missing or internally inconsistent."""


@dataclass(frozen=True)
class InspectionData:
    """Validated arrays and metadata required by the inspection view."""

    colors: np.ndarray
    depth: np.ndarray
    instance_segmap: np.ndarray
    rock_id_segmap: np.ndarray
    instance_attributes: list[dict[str, Any]]
    metadata: dict[str, Any]


def load_and_validate_output(output_dir: str | Path, frame: int = 0) -> InspectionData:
    """Load one generated frame and validate its minimum output contract."""
    directory = Path(output_dir)
    hdf5_path = directory / f"{frame}.hdf5"
    metadata_path = directory / "scene_metadata.json"
    missing_files = [str(path) for path in (hdf5_path, metadata_path) if not path.is_file()]
    if missing_files:
        raise OutputValidationError(f"Missing output files: {', '.join(missing_files)}")

    with metadata_path.open(encoding="utf-8") as metadata_file:
        metadata = json.load(metadata_file)

    with h5py.File(hdf5_path) as hdf5_file:
        missing_datasets = sorted(REQUIRED_DATASETS.difference(hdf5_file.keys()))
        if missing_datasets:
            raise OutputValidationError(f"Missing HDF5 datasets: {', '.join(missing_datasets)}")

        colors = hdf5_file["colors"][()]
        depth = hdf5_file["depth"][()]
        instance_segmap = hdf5_file["instance_segmaps"][()]
        rock_id_segmap = hdf5_file["rock_id_segmaps"][()]
        instance_attributes = _decode_json_dataset(hdf5_file["instance_attribute_maps"][()])

    _validate_image_shapes(colors, depth, instance_segmap, rock_id_segmap, metadata)
    _validate_rock_ids(rock_id_segmap, instance_attributes, metadata)
    return InspectionData(
        colors=colors,
        depth=depth,
        instance_segmap=instance_segmap,
        rock_id_segmap=rock_id_segmap,
        instance_attributes=instance_attributes,
        metadata=metadata,
    )


def save_inspection_figure(
    data: InspectionData,
    destination: str | Path,
    *,
    show: bool = False,
) -> Path:
    """Save a compact view of render channels and known rock properties."""
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    figure, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    axes[0, 0].imshow(data.colors)
    axes[0, 0].set_title("RGB")
    axes[0, 1].imshow(data.depth, cmap="viridis")
    axes[0, 1].set_title("Depth")
    axes[1, 0].imshow(data.instance_segmap, cmap="tab20", interpolation="nearest")
    axes[1, 0].set_title("Instance segmentation")
    _plot_rock_properties(axes[1, 1], data.metadata)

    for axis in axes.flat[:3]:
        axis.set_axis_off()

    rocks = data.metadata["rocks"]
    visible_ids = set(np.unique(data.rock_id_segmap).tolist()).difference({0})
    figure.suptitle(f"LithoSynth output inspection — {len(rocks)} rocks, {len(visible_ids)} visible", fontsize=15)
    figure.savefig(destination_path, dpi=150)
    if show:
        plt.show()
    plt.close(figure)
    return destination_path


def _decode_json_dataset(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    try:
        decoded = json.loads(value)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OutputValidationError("instance_attribute_maps is not valid JSON") from error
    if not isinstance(decoded, list):
        raise OutputValidationError("instance_attribute_maps must contain a JSON list")
    return decoded


def _validate_image_shapes(
    colors: np.ndarray,
    depth: np.ndarray,
    instance_segmap: np.ndarray,
    rock_id_segmap: np.ndarray,
    metadata: dict[str, Any],
) -> None:
    if colors.ndim != 3 or colors.shape[2] not in (3, 4):
        raise OutputValidationError("colors must have shape (height, width, 3|4)")

    image_shape = colors.shape[:2]
    for name, array in (
        ("depth", depth),
        ("instance_segmaps", instance_segmap),
        ("rock_id_segmaps", rock_id_segmap),
    ):
        if array.shape != image_shape:
            raise OutputValidationError(f"{name} shape {array.shape} does not match RGB shape {image_shape}")

    try:
        width, height = metadata["camera"]["resolution"]
    except (KeyError, TypeError, ValueError) as error:
        raise OutputValidationError("metadata camera resolution is missing or invalid") from error
    if image_shape != (height, width):
        raise OutputValidationError(
            f"render shape {image_shape} does not match metadata resolution {(width, height)}"
        )
    if not np.isfinite(depth).all() or np.any(depth < 0):
        raise OutputValidationError("depth contains negative or non-finite values")


def _validate_rock_ids(
    rock_id_segmap: np.ndarray,
    instance_attributes: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> None:
    rocks = metadata.get("rocks")
    if not isinstance(rocks, list) or not rocks:
        raise OutputValidationError("metadata must contain at least one rock")

    try:
        metadata_ids = [int(rock["rock_id"]) for rock in rocks]
        attribute_ids = {
            int(item["rock_id"])
            for item in instance_attributes
            if int(item.get("rock_id", 0)) > 0
        }
    except (KeyError, TypeError, ValueError) as error:
        raise OutputValidationError("rock IDs in metadata or instance attributes are invalid") from error

    if len(metadata_ids) != len(set(metadata_ids)) or any(rock_id <= 0 for rock_id in metadata_ids):
        raise OutputValidationError("metadata rock IDs must be unique positive integers")
    if attribute_ids != set(metadata_ids):
        raise OutputValidationError("instance attributes and metadata contain different rock IDs")

    visible_ids = {int(value) for value in np.unique(rock_id_segmap) if int(value) > 0}
    unknown_ids = visible_ids.difference(metadata_ids)
    if unknown_ids:
        raise OutputValidationError(f"rock_id_segmaps contains unknown rock IDs: {sorted(unknown_ids)}")


def _plot_rock_properties(axis: Any, metadata: dict[str, Any]) -> None:
    rocks = metadata["rocks"]
    for rock in rocks:
        x, y, _ = rock["location"]
        width, length, _ = rock["dimensions"]
        size = max(80.0, width * length * 500.0)
        axis.scatter(
            x,
            y,
            s=size,
            color=rock["base_color"][:3],
            edgecolor="white",
            linewidth=1.0,
        )
        axis.annotate(
            f'{rock["rock_id"]}\nr={rock["roughness"]:.2f}',
            (x, y),
            ha="center",
            va="center",
            fontsize=7,
        )

    terrain_size = float(metadata["terrain"]["size"])
    limit = terrain_size / 2.0
    axis.set(xlim=(-limit, limit), ylim=(-limit, limit), aspect="equal")
    axis.set_title("Known rock properties\n(position, footprint, base color, roughness)")
    axis.set_xlabel("x")
    axis.set_ylabel("y")
    axis.grid(alpha=0.2)
