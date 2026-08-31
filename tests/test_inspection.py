import json
from hashlib import sha256

import h5py
import numpy as np
import pytest

from lithosynth.inspection import (
    OutputValidationError,
    load_and_validate_output,
    save_inspection_figure,
    validate_all_outputs,
)


def _write_output(
    tmp_path,
    *,
    rock_id: int = 1,
    include_depth: bool = True,
    modern: bool = False,
    background_fraction: float = 0.0,
) -> None:
    metadata = {
        "terrain": {"size": 4.0},
        "rocks": [
            {
                "rock_id": 1,
                "location": [0.0, 0.0, 0.5],
                "dimensions": [1.0, 1.0, 1.0],
                "surface_area": 3.14,
                "volume": 0.52,
                "base_color": [0.3, 0.3, 0.3, 1.0],
                "roughness": 0.8,
            }
        ],
        "camera": {"resolution": [4, 3]},
    }
    if modern:
        metadata.pop("camera")
        heights = np.zeros((3, 3), dtype=np.float64)
        payload = ",".join(f"{float(value):.9g}" for value in heights.flat)
        np.save(tmp_path / "terrain_height.npy", heights)
        metadata["format_version"] = "0.1.1"
        metadata["terrain"]["height_field"] = {
            "resolution": 3,
            "sha256": sha256(payload.encode()).hexdigest(),
        }
        metadata["terrain_height_file"] = "terrain_height.npy"
        metadata["frames"] = [
            {
                "frame_index": 0,
                "camera_id": "camera_000",
                "camera": {"resolution": [4, 3], "max_background_fraction": 0.01},
                "background_fraction": background_fraction,
                "visible_rocks": [{"rock_id": rock_id}],
            }
        ]
    (tmp_path / "scene_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with h5py.File(tmp_path / "0.hdf5", "w") as output_file:
        output_file.create_dataset("colors", data=np.zeros((3, 4, 3), dtype=np.uint8))
        if include_depth:
            output_file.create_dataset("depth", data=np.ones((3, 4), dtype=np.float32))
        output_file.create_dataset("instance_segmaps", data=np.ones((3, 4), dtype=np.int64))
        output_file.create_dataset("rock_id_segmaps", data=np.full((3, 4), rock_id, dtype=np.int64))
        attributes = [{"idx": 1, "name": "rock_001", "category_id": 1, "rock_id": 1}]
        output_file.create_dataset("instance_attribute_maps", data=json.dumps(attributes).encode())


def test_valid_output_can_be_visualized(tmp_path) -> None:
    _write_output(tmp_path)

    data = load_and_validate_output(tmp_path)
    destination = save_inspection_figure(data, tmp_path / "inspection.png")

    assert data.metadata["rocks"][0]["rock_id"] == 1
    assert destination.is_file()


def test_missing_dataset_is_rejected(tmp_path) -> None:
    _write_output(tmp_path, include_depth=False)

    with pytest.raises(OutputValidationError, match="Missing HDF5 datasets: depth"):
        load_and_validate_output(tmp_path)


def test_unknown_segmented_rock_id_is_rejected(tmp_path) -> None:
    _write_output(tmp_path, rock_id=2)

    with pytest.raises(OutputValidationError, match="unknown rock IDs"):
        load_and_validate_output(tmp_path)


def test_all_declared_frames_are_validated(tmp_path) -> None:
    _write_output(tmp_path, modern=True)

    frames = validate_all_outputs(tmp_path)

    assert len(frames) == 1
    assert frames[0].frame_metadata["camera_id"] == "camera_000"


def test_excessive_background_is_rejected(tmp_path) -> None:
    _write_output(tmp_path, modern=True, background_fraction=0.02)

    with pytest.raises(OutputValidationError, match="background fraction"):
        validate_all_outputs(tmp_path)
