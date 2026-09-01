from rocksynth.generators import generate_scene


def test_generated_terrain_is_reproducible(asset_scene_config) -> None:
    first = generate_scene(asset_scene_config).terrain
    second = generate_scene(asset_scene_config).terrain

    assert first == second
    assert first.kind == "heightfield"
    assert first.height_field.digest == second.height_field.digest
    assert first.height_at(0.0, 0.0) == second.height_at(0.0, 0.0)
    assert asset_scene_config["terrain"]["gray_range"][0] <= first.base_color[0] <= asset_scene_config["terrain"]["gray_range"][1]
    assert asset_scene_config["terrain"]["roughness_range"][0] <= first.roughness <= asset_scene_config["terrain"]["roughness_range"][1]


def test_height_queries_match_grid_samples(asset_scene_config) -> None:
    terrain = generate_scene(asset_scene_config).terrain
    height_field = terrain.height_field

    assert terrain.height_at(-terrain.size / 2.0, -terrain.size / 2.0) == (
        terrain.base_height + height_field.heights[0]
    )
    assert terrain.height_at(terrain.size / 2.0, terrain.size / 2.0) == (
        terrain.base_height + height_field.heights[-1]
    )
