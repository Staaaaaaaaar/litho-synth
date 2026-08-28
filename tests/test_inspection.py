import json

import h5py
import numpy as np
import pytest

from lithosynth.inspection import OutputValidationError, load_and_validate_output, save_inspection_figure


def _write_output(tmp_path, *, rock_id: int = 1, include_depth: bool = True) -> None:
    metadata = {
        "terrain": {"size": 4.0},
        "rocks": [
            {
                "rock_id": 1,
                "location": [0.0, 0.0, 0.5],
                "dimensions": [1.0, 1.0, 1.0],
                "base_color": [0.3, 0.3, 0.3, 1.0],
                "roughness": 0.8,
            }
        ],
        "camera": {"resolution": [4, 3]},
    }
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
