import blenderproc as bproc

import argparse
import sys
from pathlib import Path


def _find_repository_root() -> Path:
    candidates = [Path(__file__).resolve().parent, Path.cwd()]
    for starting_point in candidates:
        for candidate in (starting_point, *starting_point.parents):
            if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "lithosynth").is_dir():
                return candidate
    raise RuntimeError("Could not locate the LithoSynth repository root")


REPOSITORY_ROOT = _find_repository_root()
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from lithosynth.backends.blenderproc import render_scene
from lithosynth.core.config import load_scene_config
from lithosynth.generators import generate_scene


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a minimal LithoSynth multi-rock scene.")
    parser.add_argument("--config", type=Path, default=REPOSITORY_ROOT / "configs" / "scene.json")
    parser.add_argument("--output", type=Path, help="Override render.output_dir from the configuration")
    parser.add_argument("--seed", type=int, help="Override the configured random seed")
    args = parser.parse_args()

    config = load_scene_config(args.config)
    if args.seed is not None:
        config["seed"] = args.seed

    configured_output = Path(config["render"]["output_dir"])
    output_dir = args.output or configured_output
    if not output_dir.is_absolute():
        output_dir = REPOSITORY_ROOT / output_dir

    scene = generate_scene(config)
    render_scene(bproc, config, scene, output_dir)
    print(f"LithoSynth scene written to {output_dir}")


if __name__ == "__main__":
    main()
