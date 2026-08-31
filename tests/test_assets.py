from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.assets import download_assets, prepare_surface

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_DIR = ROOT / "assets" / "manifests"
LOCK_FILE = ROOT / "assets" / "manifest.lock.json"


def test_manifests_follow_schema_and_have_unique_assets() -> None:
    assets = download_assets.load_assets(MANIFEST_DIR)

    assert {asset["type"] for asset in assets} == {"rock", "surface", "hdri"}
    keys = [download_assets.asset_key(asset) for asset in assets]
    assert len(keys) == len(set(keys))
    assert {"polyhaven", "ambientcg"} <= {asset["provider"] for asset in assets}


def test_lock_schema_and_sha256_round_trip(tmp_path: Path) -> None:
    repository_lock = download_assets.load_lock(LOCK_FILE)
    assert repository_lock["algorithm"] == "sha256"

    payload = tmp_path / "sample.bin"
    payload.write_bytes(b"lithosynth asset fixture\n")
    digest = download_assets.sha256_file(payload)
    assert digest == "303bbaf480522822eb0ac4cf6ead7cb6dc6073f95150d1795d534be3fe0f65dd"

    path = tmp_path / "manifest.lock.json"
    lock = {
        "schema_version": 1,
        "algorithm": "sha256",
        "assets": {
            "test:sample": {
                "sha256": digest,
                "cache_path": "test/sample/sample.bin",
            }
        },
    }
    download_assets.write_lock(path, lock)
    assert download_assets.load_lock(path) == lock

    malformed = json.loads(path.read_text(encoding="utf-8"))
    malformed["algorithm"] = "md5"
    path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(download_assets.AssetError, match="invalid sha256 lock file"):
        download_assets.load_lock(path)


def test_dry_run_is_offline_and_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_on_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("dry-run attempted network access")

    monkeypatch.setattr(download_assets.urllib.request, "urlopen", fail_on_network)
    lock_path = tmp_path / "manifest.lock.json"
    cache_dir = tmp_path / "cache"

    result = download_assets.main(
        [
            "--manifest-dir",
            str(MANIFEST_DIR),
            "--lock-file",
            str(lock_path),
            "--cache-dir",
            str(cache_dir),
            "--asset",
            "polyhaven:rock_09",
            "--asset",
            "ambientcg:Ground108",
            "--dry-run",
        ]
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "https://api.polyhaven.com/files/rock_09" in output
    assert "https://ambientcg.com/get?file=Ground108_2K-JPG.zip" in output
    assert not lock_path.exists()
    assert not cache_dir.exists()


def test_bulk_download_requires_explicit_asset(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = download_assets.main(
        [
            "--manifest-dir",
            str(MANIFEST_DIR),
            "--lock-file",
            str(tmp_path / "lock.json"),
            "--cache-dir",
            str(tmp_path / "cache"),
        ]
    )

    assert result == 2
    assert "refusing bulk download" in capsys.readouterr().err


def test_polyhaven_package_includes_texture_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    asset = next(
        asset
        for asset in download_assets.load_assets(MANIFEST_DIR)
        if download_assets.asset_key(asset) == "polyhaven:rock_09"
    )
    response = {
        "blend": {
            "1k": {
                "blend": {
                    "url": "https://example.test/rock_09_1k.blend",
                    "include": {
                        "textures/base.jpg": {"url": "https://example.test/base.jpg"},
                        "textures/normal.exr": {"url": "https://example.test/normal.exr"},
                    },
                }
            }
        }
    }
    monkeypatch.setattr(download_assets, "_request_json", lambda _url: response)

    package = download_assets.resolve_polyhaven_package(asset)

    assert package == [
        ("rock_09_1k.blend", "https://example.test/rock_09_1k.blend"),
        ("textures/base.jpg", "https://example.test/base.jpg"),
        ("textures/normal.exr", "https://example.test/normal.exr"),
    ]


def test_surface_package_is_safely_classified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = next(
        asset
        for asset in download_assets.load_assets(MANIFEST_DIR)
        if download_assets.asset_key(asset) == "ambientcg:Ground108"
    )
    source = tmp_path / "surface.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("Ground108_Color.jpg", b"color")
        archive.writestr("Ground108_NormalGL.png", b"normal")
        archive.writestr("Ground108_Roughness.jpg", b"roughness")
    monkeypatch.setattr(prepare_surface, "REPO_ROOT", tmp_path)

    metadata_path = prepare_surface.prepare_surface(
        asset,
        source,
        tmp_path / "assets" / "prepared",
        "a" * 64,
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert set(metadata["maps"]) >= {"basecolor", "normal", "roughness"}
    assert metadata["normal_map"] == "OpenGL"


def test_blend_surface_uses_locked_texture_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = next(
        asset
        for asset in download_assets.load_assets(MANIFEST_DIR)
        if download_assets.asset_key(asset) == "polyhaven:dense_sand"
    )
    source = tmp_path / "dense_sand.blend"
    source.write_bytes(b"blend fixture")
    base_color = tmp_path / "dense_sand_diff.jpg"
    normal = tmp_path / "dense_sand_nor_gl.exr"
    roughness = tmp_path / "dense_sand_rough.jpg"
    for texture in (base_color, normal, roughness):
        texture.write_bytes(b"texture fixture")
    monkeypatch.setattr(prepare_surface, "REPO_ROOT", tmp_path)

    metadata_path = prepare_surface.prepare_surface(
        asset,
        source,
        tmp_path / "assets" / "prepared",
        "b" * 64,
        (base_color, normal, roughness),
    )
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert set(metadata["maps"]) >= {"basecolor", "normal", "roughness"}
    assert metadata["tile_size_m"] == [2.0, 2.0]
