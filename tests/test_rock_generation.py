from math import cos, hypot, sin

import pytest

from lithosynth.core.config import load_scene_config
from lithosynth.generators import generate_scene


def test_sampling_is_reproducible(asset_scene_config) -> None:
    asset_scene_config["seed"] = 11

    first = generate_scene(asset_scene_config)
    second = generate_scene(asset_scene_config)

    assert first == second


def test_sampled_rocks_do_not_overlap(asset_scene_config) -> None:
    rocks = generate_scene(asset_scene_config).rocks

    for index, rock in enumerate(rocks):
        for other in rocks[index + 1 :]:
            distance = hypot(rock.location[0] - other.location[0], rock.location[1] - other.location[1])
            required = (
                max(rock.dimensions[:2]) / 2.0
                + max(other.dimensions[:2]) / 2.0
                + asset_scene_config["rocks"]["minimum_gap"]
            )
            assert distance >= required


def test_generated_rocks_have_physical_metrics(asset_scene_config) -> None:
    for rock in generate_scene(asset_scene_config).rocks:
        assert rock.volume > 0
        assert rock.surface_area > 0
        assert all(dimension > 0 for dimension in rock.dimensions)
        assert rock.asset.asset_id


def test_initial_rocks_clear_their_complete_terrain_footprints(asset_scene_config) -> None:
    scene = generate_scene(asset_scene_config)

    for rock in scene.rocks:
        half_x, half_y = rock.dimensions[0] / 2.0, rock.dimensions[1] / 2.0
        cosine, sine = cos(rock.rotation_euler[2]), sin(rock.rotation_euler[2])
        support_heights = []
        for row in range(asset_scene_config["rocks"]["support_samples"]):
            local_y = (
                -half_y
                + 2.0 * half_y * row / (asset_scene_config["rocks"]["support_samples"] - 1)
            )
            for column in range(asset_scene_config["rocks"]["support_samples"]):
                local_x = (
                    -half_x
                    + 2.0 * half_x * column / (asset_scene_config["rocks"]["support_samples"] - 1)
                )
                world_x = rock.location[0] + local_x * cosine - local_y * sine
                world_y = rock.location[1] + local_x * sine + local_y * cosine
                support_heights.append(scene.terrain.height_at(world_x, world_y))
        expected_z = (
            max(support_heights)
            + rock.dimensions[2] / 2.0
            + asset_scene_config["rocks"]["drop_height"]
        )
        assert rock.location[2] == pytest.approx(expected_z)


def test_generator_samples_only_prepared_assets(asset_scene_config) -> None:
    asset_scene_config["rocks"]["count"] = 4
    rocks = generate_scene(asset_scene_config).rocks

    assert {rock.asset.source for rock in rocks} == {"fixture"}
    assert all(rock.asset.mesh_path.endswith("/prepared/fixture/rock/prepared.blend") for rock in rocks)


def test_generator_requires_prepared_assets(tmp_path) -> None:
    config = load_scene_config("configs/scene.json")
    config["rocks"]["asset_manifest"] = str(tmp_path / "missing.json")

    with pytest.raises(FileNotFoundError, match="No prepared scanned rocks"):
        generate_scene(config)
