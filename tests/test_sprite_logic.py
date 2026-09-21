import pytest

from xiaoliang.sprite import AssetError, frame_index, parse_manifest

VALID_MANIFEST = {
    "frame_size": [64, 64],
    "actions": {
        "idle": {"file": "idle.png", "frames": 4, "fps": 3},
        "walk_left": {"file": "walk_left.png", "frames": 6, "fps": 8},
    },
}


def test_frame_index_cycles():
    assert frame_index(0, 4, 4) == 0
    assert frame_index(250, 4, 4) == 1
    assert frame_index(1000, 4, 4) == 0  # 4fps → 1 秒后回到第 0 帧


def test_frame_index_negative_elapsed_treated_as_zero():
    assert frame_index(-100, 4, 4) == 0


def test_frame_index_zero_count_raises():
    with pytest.raises(AssetError):
        frame_index(0, 4, 0)


def test_parse_manifest_accepts_valid():
    assert parse_manifest(VALID_MANIFEST) == VALID_MANIFEST


def test_parse_manifest_rejects_bad_frame_size():
    with pytest.raises(AssetError):
        parse_manifest({"frame_size": [64], "actions": VALID_MANIFEST["actions"]})


def test_parse_manifest_rejects_missing_action_field():
    bad = {"frame_size": [64, 64],
           "actions": {"idle": {"file": "i.png", "frames": 4}}}  # 缺 fps
    with pytest.raises(AssetError):
        parse_manifest(bad)


def test_parse_manifest_rejects_empty_actions():
    with pytest.raises(AssetError):
        parse_manifest({"frame_size": [64, 64], "actions": {}})
