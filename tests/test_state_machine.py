import pytest

from xiaoliang.state_machine import Bounds, PetStateMachine, State


class FakeRandom:
    """可预测随机源：choice 返回预设值，uniform 返回区间上限。"""

    def __init__(self, choice_value=1):
        self.choice_value = choice_value

    def choice(self, seq):
        return self.choice_value

    def uniform(self, a, b):
        return b


def make_machine(rng=None, **overrides) -> PetStateMachine:
    params = dict(
        bounds=Bounds(800, 600),
        pet_width=64, pet_height=64,
        walk_speed=100.0,
        idle_range=(1.0, 1.0),
        walk_range=(2.0, 2.0),
        gravity=1000.0,
    )
    params.update(overrides)
    return PetStateMachine(rng=rng or FakeRandom(), **params)


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
