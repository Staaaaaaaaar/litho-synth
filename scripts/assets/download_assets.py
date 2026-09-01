#!/usr/bin/env python3
"""Resolve, download, verify, and lock explicitly selected source assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_DIR = REPO_ROOT / "assets" / "manifests"
DEFAULT_LOCK_FILE = REPO_ROOT / "assets" / "manifest.lock.json"
DEFAULT_CACHE_DIR = REPO_ROOT / "assets" / "cache"
REQUIRED_FIELDS = {
    "provider",
    "asset_id",
    "type",
    "source_url",
    "license",
    "license_url",
    "redistribution",
    "preferred_format",
    "real_scale",
}
SUPPORTED_PROVIDERS = {"polyhaven", "ambientcg"}
USER_AGENT = "rock-synth-asset-pipeline/0.1.1"


class AssetError(RuntimeError):
    """An actionable asset-pipeline failure."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(document: dict[str, Any], source: Path | str = "<manifest>") -> None:
    if document.get("schema_version") != 1:
        raise AssetError(f"{source}: schema_version must be 1")
    expected_type = document.get("asset_type")
    if expected_type not in {"rock", "surface", "hdri"}:
        raise AssetError(f"{source}: unsupported asset_type {expected_type!r}")
    assets = document.get("assets")
    if not isinstance(assets, list) or not assets:
        raise AssetError(f"{source}: assets must be a non-empty list")

    seen: set[str] = set()
    for index, asset in enumerate(assets):
        if not isinstance(asset, dict):
            raise AssetError(f"{source}: asset {index} must be an object")
        missing = REQUIRED_FIELDS - asset.keys()
        if missing:
            raise AssetError(f"{source}: asset {index} missing {sorted(missing)}")
        if asset["provider"] not in SUPPORTED_PROVIDERS:
            raise AssetError(f"{source}: unsupported provider {asset['provider']!r}")
        if asset["type"] != expected_type:
            raise AssetError(f"{source}: asset {asset['asset_id']!r} has mismatched type")
        key = asset_key(asset)
        if key in seen:
            raise AssetError(f"{source}: duplicate asset {key}")
        seen.add(key)
        for field in ("source_url", "license_url"):
            parsed = urllib.parse.urlparse(str(asset[field]))
            if parsed.scheme != "https" or not parsed.netloc:
                raise AssetError(f"{source}: {key} has invalid {field}")
        if asset["license"] != "CC0-1.0":
            raise AssetError(f"{source}: {key} must explicitly declare CC0-1.0")
        if not isinstance(asset["preferred_format"], dict):
            raise AssetError(f"{source}: {key} preferred_format must be an object")
        if not isinstance(asset["real_scale"], dict) or "unit" not in asset["real_scale"]:
            raise AssetError(f"{source}: {key} real_scale must declare unit")
        convention = "geometry_convention" if expected_type == "rock" else "texture_convention"
        if convention not in asset:
            raise AssetError(f"{source}: {key} missing {convention}")


def load_assets(manifest_dir: Path) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    paths = sorted(manifest_dir.glob("*.json"))
    if not paths:
        raise AssetError(f"no JSON manifests found in {manifest_dir}")
    for path in paths:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AssetError(f"cannot read manifest {path}: {exc}") from exc
        validate_manifest(document, path)
        assets.extend(document["assets"])
    return assets


def asset_key(asset: dict[str, Any]) -> str:
    return f"{asset['provider']}:{asset['asset_id']}"


def select_assets(assets: Iterable[dict[str, Any]], selectors: list[str]) -> list[dict[str, Any]]:
    available = list(assets)
    if not selectors:
        return available
    selected: list[dict[str, Any]] = []
    for selector in selectors:
        matches = [
            asset
            for asset in available
            if selector in {str(asset["asset_id"]), asset_key(asset)}
        ]
        if not matches:
            raise AssetError(f"unknown asset {selector!r}")
        if len(matches) > 1:
            choices = ", ".join(asset_key(asset) for asset in matches)
            raise AssetError(f"ambiguous asset {selector!r}; use one of: {choices}")
        if matches[0] not in selected:
            selected.append(matches[0])
    return selected


def _request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise AssetError(f"failed to query {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssetError(f"provider returned an unexpected response from {url}")
    return payload


def _url_candidates(value: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str]]:
    candidates: list[tuple[tuple[str, ...], str]] = []
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and urllib.parse.urlparse(url).scheme == "https":
            candidates.append((path, url))
        for key, nested in value.items():
            candidates.extend(_url_candidates(nested, (*path, str(key).lower())))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            candidates.extend(_url_candidates(nested, (*path, str(index))))
    return candidates


def _download_candidates(
    value: Any,
    path: tuple[str, ...] = (),
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    candidates: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    if isinstance(value, dict):
        if isinstance(value.get("url"), str):
            candidates.append((path, value))
        for key, nested in value.items():
            candidates.extend(_download_candidates(nested, (*path, str(key).lower())))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            candidates.extend(_download_candidates(nested, (*path, str(index))))
    return candidates


def resolve_polyhaven_package(asset: dict[str, Any]) -> list[tuple[str, str]]:
    api_url = f"https://api.polyhaven.com/files/{urllib.parse.quote(asset['asset_id'])}"
    candidates = _download_candidates(_request_json(api_url))
    if not candidates:
        raise AssetError(f"Poly Haven API returned no downloadable files for {asset_key(asset)}")

    preferred = asset["preferred_format"]
    containers = [
        str(preferred.get("container", "")).lower(),
        *(str(item).lower() for item in preferred.get("fallback_containers", [])),
    ]
    resolution = str(preferred.get("resolution", "")).lower()

    def score(candidate: tuple[tuple[str, ...], dict[str, Any]]) -> tuple[int, int, int]:
        path, download = candidate
        url = str(download["url"])
        haystack = "/".join((*path, Path(urllib.parse.urlparse(url).path).name.lower()))
        container_score = next(
            (len(containers) - index for index, item in enumerate(containers) if item and item in haystack),
            0,
        )
        return (container_score, int(bool(resolution and resolution in haystack)), -len(haystack))

    best = max(candidates, key=score)
    if score(best)[0] == 0:
        raise AssetError(
            f"Poly Haven has no preferred container for {asset_key(asset)} "
            f"(wanted {', '.join(filter(None, containers))})"
        )
    primary = best[1]
    primary_url = str(primary["url"])
    package = [(_filename_from_url(primary_url, asset), primary_url)]
    includes = primary.get("include", {})
    if isinstance(includes, dict):
        for relative_name, dependency in includes.items():
            if not isinstance(dependency, dict) or not isinstance(dependency.get("url"), str):
                continue
            relative_path = PurePosixPath(relative_name)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise AssetError(f"Poly Haven returned an unsafe dependency path: {relative_name}")
            package.append((relative_path.as_posix(), str(dependency["url"])))
    return package


def resolve_polyhaven_url(asset: dict[str, Any]) -> str:
    return resolve_polyhaven_package(asset)[0][1]


def resolve_download_url(asset: dict[str, Any]) -> str:
    if asset["provider"] == "polyhaven":
        return resolve_polyhaven_url(asset)
    if asset["provider"] == "ambientcg":
        parsed = urllib.parse.urlparse(asset["source_url"])
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.netloc.lower() not in {"ambientcg.com", "www.ambientcg.com"} or not query.get("file"):
            raise AssetError(
                f"{asset_key(asset)} must use an ambientCG https://ambientcg.com/get?file=... URL"
            )
        return str(asset["source_url"])
    raise AssetError(f"unsupported provider {asset['provider']!r}")


def planned_url(asset: dict[str, Any]) -> str:
    if asset["provider"] == "polyhaven":
        return f"https://api.polyhaven.com/files/{urllib.parse.quote(asset['asset_id'])}"
    return str(asset["source_url"])


def load_lock(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": 1, "algorithm": "sha256", "assets": {}}
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AssetError(f"cannot read lock file {path}: {exc}") from exc
    if (
        lock.get("schema_version") != 1
        or lock.get("algorithm") != "sha256"
        or not isinstance(lock.get("assets"), dict)
    ):
        raise AssetError(f"{path}: invalid sha256 lock file")
    return lock


def _filename_from_url(url: str, asset: dict[str, Any]) -> str:
    parsed = urllib.parse.urlparse(url)
    query_name = urllib.parse.parse_qs(parsed.query).get("file", [""])[0]
    filename = Path(query_name or parsed.path).name
    if not filename:
        container = asset["preferred_format"].get("container", "asset")
        filename = f"{asset['asset_id']}.{container}"
    return filename


def download_asset(
    asset: dict[str, Any],
    cache_dir: Path,
    lock: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    if asset["provider"] == "polyhaven":
        package = resolve_polyhaven_package(asset)
    else:
        url = resolve_download_url(asset)
        package = [(_filename_from_url(url, asset), url)]

    asset_directory = cache_dir / asset["provider"] / asset["asset_id"]
    locked = lock["assets"].get(asset_key(asset), {})
    locked_dependencies = {
        dependency["cache_path"]: dependency
        for dependency in locked.get("dependencies", [])
    }
    downloaded = []
    for index, (relative_name, url) in enumerate(package):
        destination = asset_directory / relative_name
        expected_record = locked if index == 0 else locked_dependencies.get(destination.relative_to(cache_dir).as_posix(), {})
        downloaded.append(
            _download_file(
                asset,
                destination,
                url,
                expected_record.get("sha256"),
            )
        )

    primary_path, primary_url, primary_hash, primary_size = downloaded[0]
    entry = _lock_entry(asset, primary_path, cache_dir, primary_url, primary_hash)
    entry["size_bytes"] = primary_size
    entry["dependencies"] = [
        {
            "cache_path": path.relative_to(cache_dir).as_posix(),
            "source_url": url,
            "sha256": digest,
            "size_bytes": size,
        }
        for path, url, digest, size in downloaded[1:]
    ]
    return primary_path, entry


def _download_file(
    asset: dict[str, Any],
    destination: Path,
    url: str,
    expected_hash: str | None,
) -> tuple[Path, str, str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        actual = sha256_file(destination)
        if expected_hash and actual != expected_hash:
            raise AssetError(
                f"cached file hash mismatch for {asset_key(asset)}: expected {expected_hash}, got {actual}"
            )
        return destination, url, actual, destination.stat().st_size

    temporary = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        temporary.unlink(missing_ok=True)
        raise AssetError(f"failed to download {asset_key(asset)} from {url}: {exc}") from exc

    actual = digest.hexdigest()
    if expected_hash and actual != expected_hash:
        temporary.unlink(missing_ok=True)
        raise AssetError(
            f"downloaded file hash mismatch for {asset_key(asset)}: expected {expected_hash}, got {actual}"
        )
    os.replace(temporary, destination)
    return destination, url, actual, size


def _lock_entry(
    asset: dict[str, Any],
    path: Path,
    cache_dir: Path,
    url: str,
    sha256: str,
) -> dict[str, Any]:
    return {
        "provider": asset["provider"],
        "asset_id": asset["asset_id"],
        "type": asset["type"],
        "source_url": url,
        "cache_path": path.relative_to(cache_dir).as_posix(),
        "sha256": sha256,
        "size_bytes": path.stat().st_size,
    }


def write_lock(path: Path, lock: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--asset",
        action="append",
        default=[],
        help="asset_id or provider:asset_id; repeat to select multiple assets",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the plan without network or writes")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        assets = load_assets(args.manifest_dir)
        selected = select_assets(assets, args.asset)
        if not args.dry_run and not args.asset:
            raise AssetError("refusing bulk download: pass one or more --asset values, or use --dry-run")

        if args.dry_run:
            for asset in selected:
                print(f"{asset_key(asset)} -> {planned_url(asset)}")
            return 0

        lock = load_lock(args.lock_file)
        for asset in selected:
            destination, entry = download_asset(asset, args.cache_dir, lock)
            lock["assets"][asset_key(asset)] = entry
            print(f"{asset_key(asset)} -> {destination} (sha256 {entry['sha256']})")
        write_lock(args.lock_file, lock)
        return 0
    except AssetError as exc:
        print(f"asset error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
