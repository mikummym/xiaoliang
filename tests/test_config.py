import json

import pytest

from xiaoliang.config import DEFAULT_CONFIG, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg == DEFAULT_CONFIG


def test_corrupt_file_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert load_config(p) == DEFAULT_CONFIG


def test_non_dict_json_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_config(p) == DEFAULT_CONFIG


def test_merges_known_keys_and_ignores_unknown(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"scale": 3, "unknown_key": 1}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["scale"] == 3
    assert cfg["walk_speed"] == DEFAULT_CONFIG["walk_speed"]
    assert "unknown_key" not in cfg


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    save_config({"scale": 4, "walk_speed": 120.0, "paused": True}, p)
    # v0.2：旧文件缺 sleep 键时由 load_config 补默认值，期望 dict 需含之
    assert load_config(p) == {"scale": 4, "walk_speed": 120.0, "paused": True,
                              "sleep_start": "23:00", "sleep_end": "07:00"}


def test_wrong_typed_values_fall_back_per_key(tmp_path):
    """非法值（如 "3x"）只让该键回退默认，其余合法键照常生效（规格 §5）。"""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"scale": "3x", "walk_speed": 150.0,
                             "paused": False}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["scale"] == DEFAULT_CONFIG["scale"]   # 非法 → 默认
    assert cfg["walk_speed"] == 150.0                # 合法 → 保留
    assert cfg["paused"] is False


def test_bool_scale_rejected(tmp_path):
    """bool 是 int 子类，必须显式拒绝，避免 scale=true 被当成 1。"""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"scale": True}), encoding="utf-8")
    assert load_config(p)["scale"] == DEFAULT_CONFIG["scale"]


def test_non_positive_scale_rejected(tmp_path):
    p = tmp_path / "config.json"
    for bad in (0, -2):
        p.write_text(json.dumps({"scale": bad}), encoding="utf-8")
        assert load_config(p)["scale"] == DEFAULT_CONFIG["scale"]


def test_integer_valued_float_scale_coerced(tmp_path):
    """scale=2.0 收敛为 int 2（JSON 里 2.0 是常见的写法）。"""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"scale": 2.0}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["scale"] == 2
    assert isinstance(cfg["scale"], int)


def test_non_bool_paused_rejected(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"paused": "yes"}), encoding="utf-8")
    assert load_config(p)["paused"] == DEFAULT_CONFIG["paused"]


def test_walk_speed_int_coerced_to_float(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"walk_speed": 90}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["walk_speed"] == 90.0
    assert isinstance(cfg["walk_speed"], float)


# ── v0.2：睡眠时段配置（spec §2.5） ────────────────────────────────

def test_sleep_keys_default(tmp_path):
    cfg = load_config(tmp_path / "absent.json")
    assert cfg["sleep_start"] == "23:00"
    assert cfg["sleep_end"] == "07:00"


def test_sleep_keys_valid_custom(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"sleep_start": "22:30", "sleep_end": "06:15"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "22:30"
    assert cfg["sleep_end"] == "06:15"


@pytest.mark.parametrize("bad", [
    "24:00", "7:00", "23:60", "2300", "", "ab:cd", None, 23, True,
])
def test_sleep_keys_invalid_fall_back(tmp_path, bad):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"sleep_start": bad, "sleep_end": bad}),
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "23:00"
    assert cfg["sleep_end"] == "07:00"


def test_sleep_keys_equal_fall_back(tmp_path):
    # 相等 = 空窗口（永不睡觉），视为非法配置，两键一起回退默认
    p = tmp_path / "config.json"
    p.write_text('{"sleep_start": "08:00", "sleep_end": "08:00"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "23:00"
    assert cfg["sleep_end"] == "07:00"


def test_one_sleep_key_invalid_only_that_key_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"sleep_start": "22:00", "sleep_end": " nope"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "22:00"   # 合法键保留
    assert cfg["sleep_end"] == "07:00"     # 非法键回退
