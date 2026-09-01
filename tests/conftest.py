from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from rocksynth.core.config import load_scene_config


@pytest.fixture
def asset_scene_config(tmp_path: Path) -> dict[str, Any]:
    """Return a scene config backed by a minimal prepared rock asset."""
    assets_root = tmp_path / "assets"
    manifest_path = assets_root / "manifests" / "rocks.json"
    prepared_dir = assets_root / "prepared" / "fixture" / "rock"
    manifest_path.parent.mkdir(parents=True)
    prepared_dir.mkdir(parents=True)
    (prepared_dir / "prepared.blend").touch()
    (prepared_dir / "metadata.json").write_text(
        json.dumps(
            {
                "source_sha256": "a" * 64,
                "inspection": {
                    "non_manifold_edge_count": 0,
                    "volume_m3": 0.42,
                    "surface_area_m2": 3.1,
                    "dimensions_m": [1.0, 0.8, 0.6],
                },
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "provider": "fixture",
                        "asset_id": "rock",
                        "license": "CC0-1.0",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    config = load_scene_config("configs/scene.json")
    config["rocks"]["asset_manifest"] = str(manifest_path)
    return config
