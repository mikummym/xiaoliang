"""提醒服务纯逻辑测试：假时钟驱动 tick()，不碰 Qt/Win32（spec §3、§7）。"""
from datetime import datetime, timedelta

from xiaoliang.reminder import ReminderLogic, hour_text

BASE = datetime(2026, 9, 24, 10, 0, 0)
STEP = timedelta(seconds=15)           # 与默认心跳间隔一致


def run_ticks(logic, count, start=BASE, idle_secs=0.0):
    """连续驱动 count 次心跳，收集全部触发事件。"""
    events = []
    for i in range(count):
        events.extend(logic.tick(start + STEP * i, idle_secs))
    return events


def test_sit_reminder_fires_after_threshold():
    # sit_minutes=1 → 60s；每次心跳累加 15s → 第 4 次到点
    logic = ReminderLogic(sit_minutes=1, idle_threshold_minutes=5)
    events = run_ticks(logic, 4)
    assert len(events) == 1
    assert events[0][0] == "sit"
    assert isinstance(events[0][1], str) and events[0][1]


def test_sit_reminder_restarts_after_firing():
    logic = ReminderLogic(sit_minutes=1, idle_threshold_minutes=5)
    events = run_ticks(logic, 8)       # 第 4、8 次各触发一轮
    assert [k for k, _ in events] == ["sit", "sit"]


def test_sit_timer_resets_on_idle():
    logic = ReminderLogic(sit_minutes=1, idle_threshold_minutes=5)
    assert run_ticks(logic, 3) == []                     # 累计 45s
    ev = logic.tick(BASE + timedelta(seconds=45), 400.0) # 离开 400s > 300s
    assert ev == []
    ev = run_ticks(logic, 3, start=BASE + timedelta(seconds=60))
    assert ev == []                                      # 重计 45s 未到点
    ev = logic.tick(BASE + timedelta(seconds=105), 0.0)
    assert len(ev) == 1 and ev[0][0] == "sit"


def test_hour_chime_on_hour_change():
    logic = ReminderLogic()
    logic.tick(datetime(2026, 9, 24, 14, 59, 50), 0.0)   # 初始化 last_hour
    events = logic.tick(datetime(2026, 9, 24, 15, 0, 5), 0.0)
    assert len(events) == 1
    assert events[0][0] == "hour"
    assert "下午3点整" in events[0][1]


def test_no_chime_on_first_tick():
    logic = ReminderLogic()
    assert logic.tick(BASE, 0.0) == []                   # 首次只初始化


def test_no_chime_after_sleep_gap():
    """两次心跳跨度远超心跳间隔（合盖唤醒）：静默同步，不补报。"""
    logic = ReminderLogic()
    logic.tick(datetime(2026, 9, 24, 14, 0, 0), 0.0)
    events = logic.tick(datetime(2026, 9, 24, 16, 30, 0), 0.0)
    assert events == []


def test_no_chime_when_away():
    logic = ReminderLogic()
    logic.tick(datetime(2026, 9, 24, 14, 59, 50), 0.0)
    events = logic.tick(datetime(2026, 9, 24, 15, 0, 5), 400.0)
    assert events == []


def test_dnd_suppresses_everything():
    flag = {"on": True}
    logic = ReminderLogic(sit_minutes=1, dnd=lambda: flag["on"])
    assert run_ticks(logic, 5) == []                     # 久坐被压制
    flag["on"] = False
    events = run_ticks(logic, 4, start=BASE + timedelta(seconds=75))
    assert len(events) == 1 and events[0][0] == "sit"    # 解除后恢复


def test_hour_text_formats():
    assert hour_text(datetime(2026, 9, 24, 15, 0)) == "现在下午3点整"
    assert hour_text(datetime(2026, 9, 24, 12, 0)) == "现在中午12点整"
    assert hour_text(datetime(2026, 9, 24, 0, 0)) == "现在凌晨12点整"
    assert hour_text(datetime(2026, 9, 24, 9, 0)) == "现在上午9点整"


def test_get_idle_seconds_smoke():
    """Win32 实调冒烟：非负 float（仅 Windows 跑，其他平台跳过）。"""
    import sys
    if sys.platform != "win32":
        import pytest
        pytest.skip("Windows only")
    from xiaoliang.reminder import get_idle_seconds
    assert get_idle_seconds() >= 0.0
