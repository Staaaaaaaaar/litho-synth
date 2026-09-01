import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from rocksynth.inspection import load_and_validate_output, save_inspection_figure, validate_all_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and visualize one RockSynth scene output.")
    parser.add_argument("output_dir", type=Path, nargs="?", default=REPOSITORY_ROOT / "output" / "demo")
    parser.add_argument("--frame", type=int, default=0, help="HDF5 frame index to inspect")
    parser.add_argument("--all", action="store_true", help="Validate and save an inspection image for every frame")
    parser.add_argument("--save", type=Path, help="Inspection image path (default: OUTPUT_DIR/inspection_NNN.png)")
    parser.add_argument("--show", action="store_true", help="Open the inspection figure in a GUI window")
    args = parser.parse_args()

    if args.all:
        frames = validate_all_outputs(args.output_dir)
        for data in frames:
            frame_index = int(data.frame_metadata["frame_index"])
            destination = args.output_dir / f"inspection_{frame_index:03d}.png"
            save_inspection_figure(data, destination)
        print(f"Output is valid: {len(frames)} frames inspected in {args.output_dir}")
    else:
        data = load_and_validate_output(args.output_dir, frame=args.frame)
        destination = args.save or args.output_dir / f"inspection_{args.frame:03d}.png"
        saved_path = save_inspection_figure(data, destination, show=args.show)
        visible_ids = set(data.rock_id_segmap.flat).difference({0})
        print(
            f"Output is valid: {len(data.metadata['rocks'])} rocks, "
            f"{len(visible_ids)} visible; inspection saved to {saved_path}"
        )


if __name__ == "__main__":
    main()
