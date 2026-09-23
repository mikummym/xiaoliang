import json

import pytest

from xiaoliang.config import (DEFAULT_CONFIG, load_config, needs_migration,
                              save_config)


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
    # v0.3：旧文件缺 sleep/wrap_chance/sound/remind 键时由 load_config 补默认值
    assert load_config(p) == {"scale": 4, "walk_speed": 120.0, "paused": True,
                              "sleep_start": "23:00", "sleep_end": "07:00",
                              "wrap_chance": 0.08,
                              "sound": {"muted": False, "poke_sfx": True,
                                        "sit_reminder": True,
                                        "hourly_chime": True},
                              "remind": {"sit_minutes": 45,
                                         "idle_threshold_minutes": 5}}


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


# ── v0.2 验收补充：旧配置文件缺键检测（main.py 据此自动回写补全） ──────

def test_needs_migration_missing_file(tmp_path):
    """文件不存在走"生成默认配置"路径，不属于缺键迁移。"""
    assert needs_migration(tmp_path / "absent.json") is False


def test_needs_migration_old_v01_file(tmp_path):
    # v0.1 的旧配置只有 3 键，缺 v0.2 新增的 sleep_start/sleep_end → 需补全
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"scale": 2, "walk_speed": 60.0, "paused": False}),
                 encoding="utf-8")
    assert needs_migration(p) is True


def test_needs_migration_complete_file(tmp_path):
    p = tmp_path / "config.json"
    save_config(DEFAULT_CONFIG, p)
    assert needs_migration(p) is False


def test_needs_migration_corrupt_or_non_dict(tmp_path):
    # 损坏/非对象由 load_config 回退默认已处理，迁移不应再去动用户文件
    p = tmp_path / "config.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert needs_migration(p) is False
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert needs_migration(p) is False


def test_needs_migration_extra_unknown_key_only(tmp_path):
    # 键齐全只是多了未知键 → 不回写（不无谓改动用户文件）
    p = tmp_path / "config.json"
    data = dict(DEFAULT_CONFIG)
    data["unknown_key"] = 1
    p.write_text(json.dumps(data), encoding="utf-8")
    assert needs_migration(p) is False


def test_migration_preserves_user_values(tmp_path):
    """补全回写必须保留用户已有合法值，只补缺失键（模拟 main.py 的迁移流程）。"""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"scale": 3, "walk_speed": 120.0, "paused": True}),
                 encoding="utf-8")
    assert needs_migration(p) is True
    cfg = load_config(p)      # 加载：缺失键已在内存补默认值
    save_config(cfg, p)       # 回写：文件变成完整 8 键
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"scale": 3, "walk_speed": 120.0, "paused": True,
                    "sleep_start": "23:00", "sleep_end": "07:00",
                    "wrap_chance": 0.08,
                    "sound": {"muted": False, "poke_sfx": True,
                              "sit_reminder": True, "hourly_chime": True},
                    "remind": {"sit_minutes": 45,
                               "idle_threshold_minutes": 5}}
    assert needs_migration(p) is False   # 回写后不再需要迁移


# ── v0.3：新键 wrap_chance / sound / remind 的迁移与校验 ────────────────

def test_v02_config_migrates_to_v03(tmp_path):
    """v0.2 的 5 键配置：load 后补全 v0.3 新键，旧值保留。"""
    p = tmp_path / "config.json"
    p.write_text('{"scale": 2, "walk_speed": 60.0, "paused": false,'
                 ' "sleep_start": "23:00", "sleep_end": "07:00"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["wrap_chance"] == 0.08
    assert cfg["sound"] == {"muted": False, "poke_sfx": True,
                            "sit_reminder": True, "hourly_chime": True}
    assert cfg["remind"] == {"sit_minutes": 45, "idle_threshold_minutes": 5}
    assert cfg["sleep_start"] == "23:00"          # 旧值保留
    assert needs_migration(p) is True             # 缺新键 → 需要迁移回写


def test_partial_sound_section_filled(tmp_path):
    """sound 段存在但缺子键：缺的子键补默认，已有子键保留。"""
    p = tmp_path / "config.json"
    p.write_text('{"sound": {"muted": true}}', encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sound"]["muted"] is True
    assert cfg["sound"]["poke_sfx"] is True
    assert needs_migration(p) is True             # 嵌套缺键也算需迁移


def test_bad_wrap_chance_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"wrap_chance": 5}', encoding="utf-8")
    assert load_config(p)["wrap_chance"] == 0.08


def test_bad_sound_section_falls_back_whole(tmp_path):
    """sound 段不是对象 → 整段回退默认（与其他键的回退语义一致）。"""
    p = tmp_path / "config.json"
    p.write_text('{"sound": "loud", "remind": {"sit_minutes": -3}}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sound"] == DEFAULT_CONFIG["sound"]
    assert cfg["remind"] == DEFAULT_CONFIG["remind"]


def test_v03_config_needs_no_migration(tmp_path):
    p = tmp_path / "config.json"
    save_config(load_config(p), p)                # 生成完整默认配置
    assert needs_migration(p) is False
