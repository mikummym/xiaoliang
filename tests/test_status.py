"""数值系统 PetStatus 单元测试（纯逻辑，spec §2.1）。"""
import logging

import pytest

from xiaoliang.status import PetStatus


def test_initial_values():
    s = PetStatus()
    assert s.mood == 80.0
    assert s.fullness == 80.0


def test_awake_decay_per_minute():
    s = PetStatus()
    s.tick(60.0)
    assert s.fullness == pytest.approx(79.5)   # -0.5/分钟
    assert s.mood == pytest.approx(79.7)       # -0.3/分钟


def test_hungry_triples_mood_decay():
    s = PetStatus(fullness=10.0)               # <20 视为饥饿
    s.tick(60.0)
    assert s.mood == pytest.approx(79.1)       # -0.3×3 = -0.9/分钟


def test_sleeping_recovers_mood_and_halves_fullness_decay():
    s = PetStatus()
    s.tick(60.0, sleeping=True)
    assert s.mood == pytest.approx(81.0)       # 睡觉心情 +1.0/分钟
    assert s.fullness == pytest.approx(79.75)  # 睡觉饱腹衰减减半 -0.25/分钟


def test_values_clamped_to_zero():
    s = PetStatus(mood=0.4, fullness=0.2)
    s.tick(600.0)                              # 10 分钟衰减 → 双双触底
    assert s.mood == 0.0
    assert s.fullness == 0.0


def test_feed_gains_and_clamps():
    s = PetStatus(mood=50.0, fullness=50.0)
    assert s.feed() is True
    assert s.fullness == pytest.approx(75.0)   # +25
    assert s.mood == pytest.approx(55.0)       # +5


def test_feed_clamped_at_100():
    s = PetStatus(mood=99.0, fullness=90.0)    # 90 恰好允许（>90 才拒绝）
    assert s.feed() is True
    assert s.mood == 100.0
    assert s.fullness == 100.0


def test_feed_refused_above_90_no_side_effect():
    s = PetStatus(mood=50.0, fullness=91.0)
    assert s.feed() is False
    assert s.fullness == 91.0                  # 数值不变
    assert s.mood == 50.0


def test_can_feed_property():
    assert PetStatus(fullness=90.0).can_feed is True
    assert PetStatus(fullness=90.1).can_feed is False


def test_poke_cooldown():
    s = PetStatus(mood=50.0)
    assert s.poke() is True
    assert s.mood == pytest.approx(53.0)       # +3
    assert s.poke() is False                   # 冷却中拒绝
    s.tick(9.9)
    assert s.poke() is False                   # 累计 9.9s < 10s
    s.tick(0.2)                                # 累计 10.1s ≥ 10s
    assert s.poke() is True
    # 53 - 清醒衰减 0.3×(10.1/60) + 3
    assert s.mood == pytest.approx(56.0 - 0.3 * (10.1 / 60))


def test_poke_in_cooldown_still_ticks_elapsed():
    s = PetStatus()
    s.poke()
    s.tick(5.0)
    assert s.poke() is False                   # 5s 仍在冷却


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "status.json"
    s = PetStatus(mood=42.5, fullness=66.25)
    s.save(path)
    loaded = PetStatus.load(path)
    assert loaded.mood == pytest.approx(42.5)
    assert loaded.fullness == pytest.approx(66.25)


def test_load_missing_file_returns_defaults(tmp_path):
    s = PetStatus.load(tmp_path / "nope.json")
    assert s.mood == 80.0
    assert s.fullness == 80.0


def test_load_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("not json{{", encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 80.0
    assert s.fullness == 80.0


def test_load_invalid_field_falls_back_per_key(tmp_path):
    path = tmp_path / "status.json"
    path.write_text('{"mood": "high", "fullness": 55}', encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 80.0                         # 坏字段回退默认
    assert s.fullness == pytest.approx(55.0)      # 好字段保留


def test_load_out_of_range_clamped(tmp_path):
    path = tmp_path / "status.json"
    path.write_text('{"mood": 500, "fullness": -3}', encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 100.0
    assert s.fullness == 0.0


def test_load_non_object_returns_defaults(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("[1, 2]", encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 80.0


def test_save_failure_only_warns(tmp_path, caplog):
    bad = tmp_path / "missing_dir" / "status.json"   # 父目录不存在 → OSError
    s = PetStatus()
    with caplog.at_level(logging.WARNING):
        s.save(bad)                                  # 不抛异常
    assert "保存失败" in caplog.text
