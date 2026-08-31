"""Extract and classify one locked PBR surface package."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from download_assets import (
    DEFAULT_LOCK_FILE,
    DEFAULT_MANIFEST_DIR,
    AssetError,
    asset_key,
    load_assets,
    load_lock,
    select_assets,
    sha256_file,
)

DEFAULT_CACHE_DIR = REPO_ROOT / "assets" / "cache"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "assets" / "prepared"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".exr"}


def prepare_surface(
    asset: dict[str, Any],
    source: Path,
    output_dir: Path,
    source_hash: str,
    dependencies: tuple[Path, ...] = (),
) -> Path:
    target_dir = output_dir / asset["provider"] / asset["asset_id"]
    texture_dir = target_dir / "textures"
    if target_dir.exists():
        shutil.rmtree(target_dir)
    texture_dir.mkdir(parents=True)

    if zipfile.is_zipfile(source):
        _extract_zip_safely(source, texture_dir)
    elif source.suffix.lower() in IMAGE_SUFFIXES:
        shutil.copy2(source, texture_dir / source.name)
    elif dependencies:
        for dependency in dependencies:
            if dependency.suffix.lower() in IMAGE_SUFFIXES:
                shutil.copy2(dependency, texture_dir / dependency.name)
    else:
        raise AssetError(f"surface source must be a ZIP or image file: {source}")

    maps = _classify_maps(texture_dir, asset["texture_convention"]["channel_aliases"])
    if "basecolor" not in maps or "normal" not in maps:
        raise AssetError("surface package must contain at least basecolor and normal maps")
    metadata = {
        "schema_version": 1,
        "asset": asset_key(asset),
        "source_sha256": source_hash,
        "tile_size_m": asset["real_scale"]["tile_size_m"],
        "normal_map": asset["texture_convention"]["normal_map"],
        "maps": {
            channel: path.relative_to(REPO_ROOT).as_posix()
            for channel, path in maps.items()
        },
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata_path


def _extract_zip_safely(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise AssetError(f"unsafe ZIP member: {member.filename}")
            if member.is_dir() or member_path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            target = destination / member_path.name
            with archive.open(member) as input_file, target.open("wb") as output_file:
                shutil.copyfileobj(input_file, output_file)


def _classify_maps(texture_dir: Path, aliases: dict[str, list[str]]) -> dict[str, Path]:
    maps = {}
    files = sorted(path for path in texture_dir.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)
    for channel, channel_aliases in aliases.items():
        matches = [
            path
            for path in files
            if any(alias.lower() in path.stem.lower() for alias in channel_aliases)
        ]
        if matches:
            maps[channel] = matches[0]
    return maps


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset", required=True)
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    try:
        asset = select_assets(load_assets(args.manifest_dir), [args.asset])[0]
        if asset["type"] != "surface":
            raise AssetError(f"{asset_key(asset)} is not a surface")
        entry = load_lock(args.lock_file)["assets"].get(asset_key(asset))
        if not entry:
            raise AssetError(f"{asset_key(asset)} is not locked; download it first")
        source = args.cache_dir / entry["cache_path"]
        if not source.is_file() or sha256_file(source) != entry["sha256"]:
            raise AssetError(f"locked surface source is missing or has changed: {source}")
        dependencies = []
        for dependency in entry.get("dependencies", []):
            dependency_path = args.cache_dir / dependency["cache_path"]
            if not dependency_path.is_file() or sha256_file(dependency_path) != dependency["sha256"]:
                raise AssetError(f"locked surface dependency is missing or has changed: {dependency_path}")
            dependencies.append(dependency_path)
        metadata_path = prepare_surface(
            asset,
            source,
            args.output_dir,
            entry["sha256"],
            tuple(dependencies),
        )
        print(f"prepared {asset_key(asset)} -> {metadata_path}")
        return 0
    except (AssetError, KeyError, OSError, zipfile.BadZipFile) as error:
        print(f"surface preparation error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
