import json

import pytest

from lithosynth.core.config import ConfigError, load_scene_config


def test_default_scene_config_is_valid() -> None:
    config = load_scene_config("configs/scene.json")

    assert config["seed"] == 7
    assert config["rocks"]["count"] == 12


def test_missing_section_is_rejected(tmp_path) -> None:
    config_path = tmp_path / "invalid.json"
    config_path.write_text(json.dumps({"seed": 1}), encoding="utf-8")

    with pytest.raises(ConfigError, match="Missing configuration sections"):
        load_scene_config(config_path)
