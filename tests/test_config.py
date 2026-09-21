import json

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
    assert load_config(p) == {"scale": 4, "walk_speed": 120.0, "paused": True}
