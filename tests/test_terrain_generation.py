from lithosynth.core.config import load_scene_config
from lithosynth.generators import generate_scene


def test_generated_terrain_is_reproducible() -> None:
    config = load_scene_config("configs/scene.json")

    first = generate_scene(config).terrain
    second = generate_scene(config).terrain

    assert first == second
    assert first.kind == "flat"
    assert config["terrain"]["gray_range"][0] <= first.base_color[0] <= config["terrain"]["gray_range"][1]
    assert config["terrain"]["roughness_range"][0] <= first.roughness <= config["terrain"]["roughness_range"][1]
