"""PetWindow 渲染层回归测试（offscreen 跑，不需要真屏幕）。

回归背景：贴边推出量 _cling_margin 是纯渲染层偏移（状态机坐标里没有它）。
修复前坐顶跳下时它在 FALLING 期间保留、落地回 IDLE 那一帧归零，窗口在落地
帧横向瞬移 36 逻辑像素（肉眼明显一跳）；且下落全程贴在屏幕缘外侧。修复改为
按下落进度平滑归零，因此"坐顶→跳下→落地"全程逐帧水平位移都应是小幅渐变。
"""
import os
import random
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 必须在 Qt 导入前设置

import pytest
from PySide6.QtCore import QPoint

from xiaoliang.pet_window import PetWindow
from xiaoliang.sprite import SpriteManager
from xiaoliang.state_machine import Bounds, PetStateMachine, State

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


class _FakeClock:
    """固定 33ms/帧的假时钟：_on_tick 用它算 dt，测试才能确定性推进。"""

    def restart(self):
        return 33.0


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    return qapp


@pytest.fixture(scope="module")
def sprites(app):
    return SpriteManager(ASSETS_DIR, scale=1)


def _record_moves(window):
    """包装 move()，逐帧记录窗口全局 x。"""
    xs = []
    orig = window.move
    window.move = lambda p: (xs.append(p.x()), orig(p))
    return xs


def _run_fall_from_top(machine, window):
    """摆好"右壁坐顶"场景并跑到落地，返回逐帧状态序列。"""
    machine.climb_wall = 1
    machine.x = float(1920 - window.width())
    machine.y = 0.0
    machine.state = State.SITTING_TOP
    machine._timer = 0.12          # 坐几帧就跳
    machine._rng = random.Random(2)  # random()=0.956 ≥0.5 → 跳下分支
    states = []
    for _ in range(80):
        window._on_tick()
        states.append(machine.state)
        if machine.state is State.IDLE:
            break
    return states


def test_fall_from_top_has_no_horizontal_teleport(app, sprites):
    """坐顶跳下全程（含落地帧）逐帧水平位移必须是小幅渐变，不能瞬移。"""
    machine = PetStateMachine(Bounds(1920, 1080), *sprites.frame_size(),
                              rng=random.Random(7))
    window = PetWindow(machine, sprites, origin=QPoint(0, 0))
    window._clock = _FakeClock()
    xs = _record_moves(window)

    states = _run_fall_from_top(machine, window)
    assert State.FALLING in states, "场景没走到跳下分支"
    assert states[-1] is State.IDLE, "没跑到落地"

    jumps = [abs(b - a) for a, b in zip(xs, xs[1:])]
    # 平滑归零时单帧漂移约 1-2px；修复前落地帧为 36px
    assert max(jumps) <= 3, f"逐帧水平位移峰值 {max(jumps)}px，存在瞬移"


def test_fall_without_cling_stays_put_horizontally(app, sprites):
    """不贴边时空中下落（拖拽松手）水平方向应完全不动，归零逻辑不能误伤。"""
    machine = PetStateMachine(Bounds(1920, 1080), *sprites.frame_size(),
                              rng=random.Random(7))
    window = PetWindow(machine, sprites, origin=QPoint(0, 0))
    window._clock = _FakeClock()
    xs = _record_moves(window)

    machine.x = 500.0
    machine.y = 100.0
    machine.state = State.FALLING
    machine.vy = 0.0
    states = []
    for _ in range(80):
        window._on_tick()
        states.append(machine.state)
        if machine.state is State.IDLE:
            break
    assert states[-1] is State.IDLE
    assert len(set(xs)) == 1, f"无贴边下落水平不应移动，实际 x 序列 {sorted(set(xs))}"


def test_climb_down_landing_has_no_horizontal_teleport(app, sprites):
    """爬下落地帧同样不能横向瞬移（与跳下修复同族）。

    修复前：CLIMBING down 全程保留推出量 36，落地回 IDLE 一帧归零 →
    窗口横跳 36px。修复：落地前最后一段（竖直距离 = 推出量）渐出。
    矮工作区（高 400）+ 默认爬速 40px/s：渐出区单帧水平漂移 ≈1.3px。
    """
    machine = PetStateMachine(Bounds(1920, 400), *sprites.frame_size(),
                              rng=random.Random(7))
    window = PetWindow(machine, sprites, origin=QPoint(0, 0))
    window._clock = _FakeClock()
    xs = _record_moves(window)

    machine.climb_wall = 1
    machine.x = float(1920 - window.width())
    machine.y = 0.0
    machine.state = State.SITTING_TOP
    machine._timer = 0.12          # 坐几帧就起身
    machine._rng = random.Random(1)  # random()=0.134 <0.5 → 原路爬下分支
    states = []
    for _ in range(400):           # 272px @40px/s ≈ 205 tick，留余量
        window._on_tick()
        states.append(machine.state)
        if machine.state is State.IDLE:
            break
    assert State.CLIMBING in states, "场景没走到爬下分支"
    assert states[-1] is State.IDLE, "没跑到落地"

    jumps = [abs(b - a) for a, b in zip(xs, xs[1:])]
    assert max(jumps) <= 3, f"逐帧水平位移峰值 {max(jumps)}px，存在瞬移"
