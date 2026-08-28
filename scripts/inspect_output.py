import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from lithosynth.inspection import load_and_validate_output, save_inspection_figure


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and visualize one LithoSynth scene output.")
    parser.add_argument("output_dir", type=Path, nargs="?", default=REPOSITORY_ROOT / "output" / "demo")
    parser.add_argument("--frame", type=int, default=0, help="HDF5 frame index to inspect")
    parser.add_argument("--save", type=Path, help="Inspection image path (default: OUTPUT_DIR/inspection.png)")
    parser.add_argument("--show", action="store_true", help="Open the inspection figure in a GUI window")
    args = parser.parse_args()

    data = load_and_validate_output(args.output_dir, frame=args.frame)
    destination = args.save or args.output_dir / "inspection.png"
    saved_path = save_inspection_figure(data, destination, show=args.show)
    visible_ids = set(data.rock_id_segmap.flat).difference({0})
    print(
        f"Output is valid: {len(data.metadata['rocks'])} rocks, "
        f"{len(visible_ids)} visible; inspection saved to {saved_path}"
    )


if __name__ == "__main__":
    main()
