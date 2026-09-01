import json

import pytest

from rocksynth.core.config import ConfigError, load_scene_config


def test_default_scene_config_is_valid() -> None:
    config = load_scene_config("configs/scene.json")

    assert config["seed"] == 7
    assert config["rocks"]["count"] == 28
    assert config["terrain"]["material"]["material_id"] == "dense_sand"
    assert config["terrain"]["size"] == 40.0
    assert config["rocks"]["placement_radius"] == 9.0
    assert "asset_mode" not in config["rocks"]
    assert "procedural_fraction" not in config["rocks"]
    assert len(config["camera_rig"]["poses"]) == 9
    assert config["camera_rig"]["rig_id"] == "local_overhead"


def test_missing_section_is_rejected(tmp_path) -> None:
    config_path = tmp_path / "invalid.json"
    config_path.write_text(json.dumps({"seed": 1}), encoding="utf-8")

    with pytest.raises(ConfigError, match="Missing configuration sections"):
        load_scene_config(config_path)


def test_physics_rejects_artificial_post_settlement_burial(tmp_path) -> None:
    config = load_scene_config("configs/scene.json")
    config["rocks"]["bury_fraction_range"] = [0.0, 0.1]
    config_path = tmp_path / "invalid-burial.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="bury_fraction_range must be \\[0, 0\\]"):
        load_scene_config(config_path)


@pytest.mark.parametrize("legacy_option", ["asset_mode", "procedural_fraction", "aspect_ratio_range"])
def test_legacy_rock_modes_are_rejected(tmp_path, legacy_option: str) -> None:
    config = load_scene_config("configs/scene.json")
    config["rocks"][legacy_option] = "legacy"
    config_path = tmp_path / "legacy.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="Unsupported rock options"):
        load_scene_config(config_path)
