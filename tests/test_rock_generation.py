from math import hypot

from lithosynth.core.config import load_scene_config
from lithosynth.generators import generate_scene


def test_sampling_is_reproducible() -> None:
    config = load_scene_config("configs/scene.json")
    config["seed"] = 11

    first = generate_scene(config)
    second = generate_scene(config)

    assert first == second


def test_sampled_rocks_do_not_overlap() -> None:
    config = load_scene_config("configs/scene.json")
    rocks = generate_scene(config).rocks

    for index, rock in enumerate(rocks):
        for other in rocks[index + 1 :]:
            distance = hypot(rock.location[0] - other.location[0], rock.location[1] - other.location[1])
            required = max(rock.scale[:2]) + max(other.scale[:2]) + config["rocks"]["minimum_gap"]
            assert distance >= required
