from datetime import time as dtime

import pytest

from xiaoliang.state_machine import (Bounds, PetStateMachine, State,
                                     in_sleep_window_minutes)
from xiaoliang.status import PetStatus


class FakeRandom:
    """可预测随机源：choice 返回预设值，uniform 返回区间上限。

    random() 默认 0.99 —— 高于攀爬概率 0.15，保证 v0.1 既有测试
    （只关心走动/发呆）不会意外走进攀爬分支。
    """

    def __init__(self, choice_value=1, random_value=0.99):
        self.choice_value = choice_value
        self.random_value = random_value

    def choice(self, seq):
        return self.choice_value

    def uniform(self, a, b):
        return b

    def random(self):
        return self.random_value


class FakeClock:
    """测试时钟：调用返回预设 time；改 .now 模拟时间流逝。"""

    def __init__(self, now=dtime(12, 0)):
        self.now = now

    def __call__(self):
        return self.now


def make_machine(rng=None, clock=None, status=None, **overrides) -> PetStateMachine:
    params = dict(
        bounds=Bounds(800, 600),
        pet_width=64, pet_height=64,
        walk_speed=100.0,
        idle_range=(1.0, 1.0),
        walk_range=(2.0, 2.0),
        gravity=1000.0,
        # 测试专用快参数：攀爬/坐/醒都压缩到 1 秒级，方便断言
        climb_speed=1000.0,
        sit_range=(1.0, 1.0),
        woken_range=(1.0, 1.0),
    )
    params.update(overrides)
    return PetStateMachine(rng=rng or FakeRandom(),
                           clock=clock or FakeClock(),
                           status=status or PetStatus(),
                           **params)


def test_initial_state_idle_on_floor():
    m = make_machine()
    assert m.state is State.IDLE
    assert m.y == 600 - 64
    assert m.x == pytest.approx((800 - 64) / 2)  # 默认居中


def test_idle_to_walking_after_timer():
    m = make_machine()
    m.tick(0.5)
    assert m.state is State.IDLE
    m.tick(0.6)  # 累计 1.1s > idle 1.0s
    assert m.state is State.WALKING


def test_walking_moves_in_chosen_direction():
    m = make_machine(rng=FakeRandom(choice_value=-1))
    m.tick(1.1)  # → WALKING，方向向左
    x0 = m.x
    m.tick(0.5)
    assert m.direction == -1
    assert m.x == pytest.approx(x0 - 50.0)


def test_walking_stops_at_left_edge_and_goes_idle():
    m = make_machine(rng=FakeRandom(choice_value=-1), start_x=30)
    m.tick(1.1)  # → WALKING 向左
    m.tick(1.0)  # 移动 100px，越过左边缘
    assert m.x == 0.0
    assert m.state is State.IDLE


def test_walking_stops_at_right_edge_and_goes_idle():
    m = make_machine(rng=FakeRandom(choice_value=1), start_x=800 - 64 - 30)
    m.tick(1.1)
    m.tick(1.0)
    assert m.x == 800 - 64
    assert m.state is State.IDLE


def test_walking_to_idle_after_timer():
    m = make_machine(rng=FakeRandom(choice_value=1),
                     walk_range=(0.5, 0.5), start_x=100)
    m.tick(1.1)  # → WALKING
    assert m.state is State.WALKING
    m.tick(0.6)  # 行走计时到
    assert m.state is State.IDLE


def test_drag_start_from_idle():
    m = make_machine()
    m.drag_start()
    assert m.state is State.DRAGGED


def test_drag_move_updates_and_clamps():
    m = make_machine()
    m.drag_start()
    m.drag_move(100, 200)
    assert (m.x, m.y) == (100, 200)
    m.drag_move(-50, 5000)
    assert m.x == 0.0
    assert m.y == 600 - 64


def test_drag_move_ignored_when_not_dragged():
    m = make_machine()
    m.drag_move(100, 100)
    assert (m.x, m.y) != (100, 100)


def test_drag_end_starts_falling():
    m = make_machine()
    m.drag_start()
    m.drag_move(100, 100)
    m.drag_end()
    assert m.state is State.FALLING


def test_falling_lands_on_floor_then_idle():
    m = make_machine(idle_range=(100.0, 100.0))  # 落地后长时间保持 IDLE 便于断言
    m.drag_start()
    m.drag_move(100, 100)
    m.drag_end()
    for _ in range(60):  # 2 秒 @30fps，足够从 y=100 落到 y=536
        m.tick(1 / 30)
    assert m.y == 600 - 64
    assert m.state is State.IDLE


def test_grab_while_falling():
    m = make_machine()
    m.drag_start()
    m.drag_move(100, 100)
    m.drag_end()
    m.tick(1 / 30)
    assert m.state is State.FALLING
    m.drag_start()
    assert m.state is State.DRAGGED


def test_paused_tick_is_noop():
    m = make_machine()
    m.set_paused(True)
    for _ in range(100):
        m.tick(0.1)
    assert m.state is State.IDLE
    m.set_paused(False)
    m.tick(1.1)
    assert m.state is State.WALKING


# ── v0.2：睡眠时段纯函数（spec §2.2） ──────────────────────────────

def test_window_cross_midnight():
    start, end = 23 * 60, 7 * 60
    assert in_sleep_window_minutes(23 * 60, start, end)        # 23:00 左闭
    assert in_sleep_window_minutes(23 * 60 + 30, start, end)   # 23:30
    assert in_sleep_window_minutes(3 * 60, start, end)         # 03:00
    assert not in_sleep_window_minutes(7 * 60, start, end)     # 07:00 右开
    assert not in_sleep_window_minutes(12 * 60, start, end)    # 中午


def test_window_same_day():
    start, end = 1 * 60, 2 * 60          # 01:00–02:00
    assert in_sleep_window_minutes(90, start, end)
    assert not in_sleep_window_minutes(120, start, end)


def test_window_equal_is_never():
    assert not in_sleep_window_minutes(23 * 60, 23 * 60, 23 * 60)


# ── v0.2：睡觉 / 睡醒（spec §2.2） ────────────────────────────────

def test_enters_sleeping_in_window():
    m = make_machine(clock=FakeClock(dtime(23, 30)))
    m.tick(0.1)
    assert m.state is State.SLEEPING


def test_wakes_when_window_ends():
    clock = FakeClock(dtime(23, 30))
    m = make_machine(clock=clock)
    m.tick(0.1)
    clock.now = dtime(7, 0)
    m.tick(0.1)
    assert m.state is State.IDLE


def test_poke_wakes_to_woken_then_sleeps_again():
    clock = FakeClock(dtime(23, 30))
    m = make_machine(clock=clock)
    m.tick(0.1)                          # SLEEPING
    m.poke()
    assert m.state is State.WOKEN        # 睡觉被戳 → 睡眼惺忪（非常规反应）
    m.tick(1.1)                          # woken_range=(1,1)
    assert m.state is State.SLEEPING     # 仍在时段 → 回笼觉


def test_woken_stays_awake_when_window_ended():
    clock = FakeClock(dtime(6, 59))
    m = make_machine(clock=clock)
    m.tick(0.1)
    m.poke()
    clock.now = dtime(7, 0)              # 惺忪期间过了 7 点
    m.tick(1.1)
    assert m.state is State.IDLE


def test_sleeping_recovers_mood():
    status = PetStatus(mood=50.0)
    m = make_machine(clock=FakeClock(dtime(23, 30)), status=status)
    m.tick(0.0)                          # dt=0 只切状态，数值不动
    m.tick(60.0)                         # 睡 60 秒
    assert status.mood == pytest.approx(51.0)       # +1.0/分钟
    assert status.fullness == pytest.approx(79.75)  # -0.25/分钟


def test_no_walk_decisions_while_sleeping():
    m = make_machine(clock=FakeClock(dtime(23, 30)))
    m.tick(0.1)
    x0 = m.x
    for _ in range(300):                 # 睡 30 秒也不许乱走
        m.tick(0.1)
    assert m.state is State.SLEEPING
    assert m.x == x0


# ── v0.2：戳（spec §2.2/§2.3） ────────────────────────────────────

def test_poke_from_idle_reacts_and_returns():
    m = make_machine()
    m.poke()
    assert m.state is State.POKE_REACT
    m.tick(1.1)                          # poke_react_secs=1.0
    assert m.state is State.IDLE


def test_poke_returns_to_walking():
    m = make_machine(start_x=400)
    m.tick(1.1)                          # IDLE 计时到 → WALKING
    assert m.state is State.WALKING
    m.poke()
    assert m.state is State.POKE_REACT
    m.tick(1.1)
    assert m.state is State.WALKING      # 回到戳之前的状态
    m.tick(0.5)
    assert m.state is State.WALKING      # 且散步剩余时长被恢复，不会立刻停


def test_poke_adds_mood_once_within_cooldown():
    status = PetStatus(mood=50.0)
    m = make_machine(status=status)
    m.poke()                             # +3
    m.tick(1.1)                          # 反应结束回 IDLE；冷却走了 1.1s
    m.poke()                             # 冷却中 → 动画照播、数值不加
    assert m.state is State.POKE_REACT
    assert status.mood == pytest.approx(53.0 - 0.3 * (1.1 / 60))


def test_poke_while_dragged_without_move_restores_state():
    # GUI 判定"按下但无有效位移"= 戳：回退拖拽前状态，不触发下落
    m = make_machine()
    m.drag_start()
    assert m.state is State.DRAGGED
    m.poke()
    assert m.state is State.POKE_REACT
    m.tick(1.1)
    assert m.state is State.IDLE         # 而不是 FALLING


def test_poke_on_wall_returns_to_climbing():
    m = make_machine(rng=FakeRandom(random_value=0.0), start_x=800 - 64)
    m.tick(1.1)                          # 贴右壁 → CLIMBING up
    assert m.state is State.CLIMBING
    m.poke()
    assert m.state is State.POKE_REACT
    m.tick(1.1)
    assert m.state is State.CLIMBING     # 墙上被戳：原地播完继续爬
    assert m.climb_direction == "up"


# ── v0.2：喂食（spec §2.2） ───────────────────────────────────────

def test_feed_from_idle_eats_then_idles():
    m = make_machine()
    assert m.feed() is True
    assert m.state is State.EATING
    m.tick(2.1)                          # eating_secs=2.0
    assert m.state is State.IDLE


def test_feed_gains_fullness():
    status = PetStatus(mood=50.0, fullness=50.0)
    m = make_machine(status=status)
    m.feed()
    assert status.fullness == pytest.approx(75.0)
    assert status.mood == pytest.approx(55.0)


def test_feed_refused_when_stuffed():
    status = PetStatus(fullness=91.0)
    m = make_machine(status=status)
    assert m.feed() is False
    assert m.state is State.IDLE         # 状态零副作用
    assert status.fullness == pytest.approx(91.0)


def test_feed_in_sleep_window_returns_to_sleep():
    m = make_machine(clock=FakeClock(dtime(23, 30)))
    m.tick(0.0)                          # SLEEPING
    assert m.feed() is True
    assert m.state is State.EATING       # 睡着了也能被投喂
    m.tick(2.1)
    assert m.state is State.SLEEPING     # 吃完仍在时段 → 回睡


# ── v0.3 修复①：暂停冻结事件（spec §1.1） ──────────────────────────

def test_poke_ignored_while_paused():
    m = make_machine()
    m.set_paused(True)
    mood0 = m.status.mood
    assert m.poke() is False          # v0.3 起 poke 返回是否受理
    assert m.state is State.IDLE      # 不播反应
    assert m.status.mood == mood0     # 不加心情


def test_feed_rejected_while_paused():
    m = make_machine()
    m.set_paused(True)
    full0 = m.status.fullness
    assert m.feed() is False
    assert m.state is State.IDLE
    assert m.status.fullness == full0


# ── v0.3 修复②：攀爬中/坐顶可喂食（spec §1.2） ─────────────────────

def test_feed_accepted_while_climbing_then_falls():
    # random_value 0.1 < climb_chance 0.15 → IDLE 出门即选攀爬；
    # start_x=0 已贴左壁 → 省去走向边缘，直接进 CLIMBING
    m = make_machine(rng=FakeRandom(choice_value=-1, random_value=0.1),
                     start_x=0)
    m.tick(1.1)                        # IDLE 计时 1.0 到点 → 掷骰 → 攀爬
    assert m.state is State.CLIMBING
    assert m.feed() is True            # 墙上接住食物
    assert m.state is State.EATING
    m.tick(2.1)                        # eating 2.0s 播完 → 空中进食转下落
    assert m.state is State.FALLING
    m.tick(0.1)                        # 本就贴地 → 首帧落地收口
    assert m.state is State.IDLE
    assert m.y == 600 - 64


def test_feed_accepted_while_sitting_top_then_falls():
    m = make_machine()
    m.state = State.SITTING_TOP        # 测试捷径：直接置于顶边
    m.y = 0.0
    assert m.feed() is True
    m.tick(2.1)                        # 吃完 → 从顶边下落
    assert m.state is State.FALLING
    m.tick(1.5)                        # gravity 1000 → 落地
    assert m.state is State.IDLE
    assert m.y == 600 - 64


def test_feed_on_ground_still_ends_idle_not_falling():
    """地面进食行为不变：吃完直接回 IDLE（不进入 FALLING）。"""
    m = make_machine()
    assert m.feed() is True
    m.tick(2.1)
    assert m.state is State.IDLE


# ── v0.3 修复④：暂停中半空松手直接落地（spec §1.3） ────────────────

def test_drag_end_while_paused_lands_on_floor():
    m = make_machine()
    m.set_paused(True)
    m.drag_start()
    m.drag_move(300, 200)              # 半空
    m.drag_end()
    assert m.state is State.IDLE       # 不再悬空 FALLING
    assert m.y == 600 - 64             # 落到正下方地面
    assert m.x == 300                  # 水平位置不变


def test_drag_end_while_running_still_falls():
    """非暂停路径行为不变：松手 → FALLING。"""
    m = make_machine()
    m.drag_start()
    m.drag_move(300, 200)
    m.drag_end()
    assert m.state is State.FALLING


# ── v0.2：攀爬线（spec §2.2） ─────────────────────────────────────

def test_climb_walks_to_nearest_edge_then_climbs():
    # x=700（中心 732 > 400）→ 最近边缘 = 右壁 736
    m = make_machine(rng=FakeRandom(random_value=0.0), start_x=700)
    m.tick(1.1)                          # IDLE 计时到 → 决定攀爬 → 走向右壁
    assert m.state is State.WALKING
    assert m._walk_intent == "climb"
    assert m.direction == 1
    m.tick(0.5)                          # 100px/s × 0.5 = 50px > 36px → 到壁
    assert m.state is State.CLIMBING
    assert m.climb_direction == "up"
    assert m.x == 800 - 64               # 吸附右壁


def test_climb_prefers_left_edge_when_closer():
    m = make_machine(rng=FakeRandom(random_value=0.0), start_x=100)
    m.tick(1.1)
    assert m.climb_wall == -1
    assert m.direction == -1
    m.tick(1.1)                          # 100px 到左壁
    assert m.state is State.CLIMBING
    assert m.x == 0.0


def test_climb_reaches_top_and_sits():
    m = make_machine(rng=FakeRandom(random_value=0.0), start_x=800 - 64)
    m.tick(1.1)                          # 已贴右壁 → 直接开爬
    assert m.state is State.CLIMBING
    m.tick(0.6)                          # 1000px/s × 0.6 > 536px → 到顶
    assert m.y == 0.0
    assert m.state is State.SITTING_TOP


def test_sit_then_climb_down_to_idle():
    # random 0.0 < 0.5 → 坐够后选择爬下
    m = make_machine(rng=FakeRandom(random_value=0.0), start_x=800 - 64)
    m.tick(1.1)                          # CLIMBING up
    m.tick(0.6)                          # SITTING_TOP（sit_range=(1,1)）
    m.tick(1.1)                          # 坐计时到 → CLIMBING down
    assert m.state is State.CLIMBING
    assert m.climb_direction == "down"
    m.tick(0.6)                          # 爬到底
    assert m.y == 600 - 64
    assert m.state is State.IDLE


def test_sit_then_jump_falls_and_lands():
    class ClimbThenJumpRandom(FakeRandom):
        """第 1 次 random()（攀爬决策）返回 0.0，之后返回 0.99（跳下）。"""

        def __init__(self):
            super().__init__()
            self._calls = 0

        def random(self):
            self._calls += 1
            return 0.0 if self._calls == 1 else 0.99

    m = make_machine(rng=ClimbThenJumpRandom(), start_x=800 - 64)
    m.tick(1.1)                          # CLIMBING up
    m.tick(0.6)                          # SITTING_TOP
    m.tick(1.1)                          # 坐计时到 → 跳下
    assert m.state is State.FALLING
    for _ in range(60):                  # 2s @30fps 足够从顶落到底
        m.tick(1 / 30)
    assert m.y == 600 - 64
    assert m.state is State.IDLE


def test_climb_interrupted_by_sleep_window():
    clock = FakeClock(dtime(12, 0))
    m = make_machine(clock=clock, rng=FakeRandom(random_value=0.0),
                     start_x=800 - 64)
    m.tick(1.1)                          # CLIMBING up
    clock.now = dtime(23, 30)            # 到点睡觉
    m.tick(0.1)                          # 应掉头向下
    assert m.state is State.CLIMBING
    assert m.climb_direction == "down"
    m.tick(0.6)                          # 到底
    assert m.state is State.SLEEPING     # 落地在时段内 → 直接睡


def test_sitting_interrupted_by_sleep_window():
    clock = FakeClock(dtime(12, 0))
    m = make_machine(clock=clock, rng=FakeRandom(random_value=0.0),
                     start_x=800 - 64)
    m.tick(1.1)
    m.tick(0.6)                          # SITTING_TOP
    clock.now = dtime(23, 30)
    m.tick(0.1)
    assert m.state is State.CLIMBING
    assert m.climb_direction == "down"


def test_drag_from_climbing_falls_normally():
    m = make_machine(rng=FakeRandom(random_value=0.0), start_x=800 - 64)
    m.tick(1.1)                          # CLIMBING up
    m.drag_start()
    m.drag_move(400, 300)
    m.drag_end()
    assert m.state is State.FALLING
    # 45 tick = 1.5s：从 y=300 落地约需 21 tick，落地后 IDLE 计时 1.0s，
    # 剩余须 <1s 才不会再次出门（否则 random()=0.0 必然又触发攀爬决策）
    for _ in range(45):
        m.tick(1 / 30)
    assert m.y == 600 - 64
    assert m.state is State.IDLE


def test_land_in_sleep_window_goes_to_sleep():
    m = make_machine(clock=FakeClock(dtime(23, 30)))
    m.drag_start()
    m.drag_move(100, 100)
    m.drag_end()
    for _ in range(60):
        m.tick(1 / 30)
    assert m.state is State.SLEEPING


# ── v0.2：数值联动（spec §2.1/§2.2） ─────────────────────────────

def test_machine_ticks_status_awake_decay():
    status = PetStatus()
    m = make_machine(status=status)
    m.tick(60.0)                         # 中午清醒 60 秒
    assert status.mood == pytest.approx(79.7)
    assert status.fullness == pytest.approx(79.5)


def test_paused_freezes_status():
    status = PetStatus()
    m = make_machine(status=status)
    m.set_paused(True)
    m.tick(60.0)
    assert status.mood == 80.0           # 暂停 = 数值全冻结
    assert m.state is State.IDLE


def test_hungry_slows_walking():
    status = PetStatus(fullness=10.0)
    m = make_machine(status=status, rng=FakeRandom(choice_value=1),
                     start_x=100)
    m.tick(1.1)                          # → WALKING 向右
    x0 = m.x
    m.tick(0.5)                          # 100 × 0.6 = 60px/s → +30
    assert m.x == pytest.approx(x0 + 30.0)


def test_low_mood_reduces_climb_chance():
    # 心情 10（<20）→ 攀爬概率 0.15×0.3 = 0.045
    bored = PetStatus(mood=10.0)
    m = make_machine(status=bored, rng=FakeRandom(random_value=0.1),
                     start_x=400)
    m.tick(1.1)                          # 0.1 > 0.045 → 不爬，普通溜达
    assert m.state is State.WALKING
    assert m._walk_intent is None
    # 0.04 < 0.045 → 触发攀爬
    m2 = make_machine(status=PetStatus(mood=10.0),
                      rng=FakeRandom(random_value=0.04), start_x=400)
    m2.tick(1.1)
    assert m2._walk_intent == "climb"


def test_normal_mood_climb_chance_not_reduced():
    m = make_machine(rng=FakeRandom(random_value=0.1), start_x=400)
    m.tick(1.1)                          # 0.1 < 0.15 → 攀爬（心情 80 不打折）
    assert m._walk_intent == "climb"


def test_on_status_change_called_on_poke_and_feed():
    calls = []
    m = make_machine(on_status_change=lambda: calls.append(1))
    m.poke()                             # 数值变化 → 回调（第 1 次）
    m.tick(1.1)
    m.feed()                             # 数值变化 → 回调（第 2 次）
    m.tick(2.1)
    m.feed()                             # 饱腹已 100 > 90 → 吃撑拒绝，无回调
    m.poke()                             # 冷却 10s 内（才过 3.2s）→ 无回调
    assert len(calls) == 2


def test_pause_listener_notified():
    seen = []
    m = make_machine()
    m.add_pause_listener(seen.append)
    m.set_paused(True)
    m.set_paused(False)
    assert seen == [True, False]
