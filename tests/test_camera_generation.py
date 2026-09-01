from rocksynth.generators import generate_scene


def test_camera_rig_is_calibrated_and_reproducible(asset_scene_config) -> None:
    first = generate_scene(asset_scene_config).camera_rig
    second = generate_scene(asset_scene_config).camera_rig

    assert first == second
    assert len(first.cameras) == len(asset_scene_config["camera_rig"]["poses"])
    assert len({camera.camera_id for camera in first.cameras}) == len(first.cameras)
    for camera in first.cameras:
        assert camera.resolution == (640, 480)
        assert camera.intrinsics == (540.0, 540.0, 320.0, 240.0)
        assert camera.location[2] > camera.look_at[2]
        assert camera.max_background_fraction == 0.002
        assert camera.location[2] - camera.look_at[2] > 5.0
