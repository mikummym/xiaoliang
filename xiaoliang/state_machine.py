"""宠物行为状态机：纯逻辑，不依赖 Qt，可单元测试。

坐标约定：(x, y) 为角色包围盒左上角，单位逻辑像素，原点为工作区左上角。
"""
import random
from dataclasses import dataclass
from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    WALKING = auto()
    DRAGGED = auto()
    FALLING = auto()


@dataclass(frozen=True)
class Bounds:
    """活动区域尺寸（主显示器工作区，逻辑像素）。"""
    width: int
    height: int


class PetStateMachine:
    def __init__(self, bounds: Bounds, pet_width: int, pet_height: int, *,
                 walk_speed: float = 60.0,
                 idle_range: tuple[float, float] = (2.0, 8.0),
                 walk_range: tuple[float, float] = (3.0, 10.0),
                 gravity: float = 1500.0,
                 start_x: float | None = None,
                 rng: random.Random | None = None):
        self.bounds = bounds
        self.pet_width = pet_width
        self.pet_height = pet_height
        self.walk_speed = walk_speed
        self.idle_range = idle_range
        self.walk_range = walk_range
        self.gravity = gravity
        self._rng = rng or random.Random()
        self.state = State.IDLE
        self.x = ((bounds.width - pet_width) / 2 if start_x is None
                  else float(start_x))
        self.y = float(self.floor_y)
        self.direction = 1  # 1 向右，-1 向左
        self.vy = 0.0
        self.paused = False
        self._timer = self._rng.uniform(*self.idle_range)

    @property
    def floor_y(self) -> float:
        """地面 y 坐标（角色底边贴工作区底边）。"""
        return self.bounds.height - self.pet_height

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def tick(self, dt: float) -> None:
        """推进 dt 秒。暂停或被拖拽时不更新。"""
        if self.paused or self.state is State.DRAGGED:
            return
        if self.state is State.IDLE:
            self._timer -= dt
            if self._timer <= 0:
                self._start_walking()
        elif self.state is State.WALKING:
            self.x += self.direction * self.walk_speed * dt
            max_x = self.bounds.width - self.pet_width
            if self.x <= 0:
                self.x = 0.0
                self._start_idle()
            elif self.x >= max_x:
                self.x = float(max_x)
                self._start_idle()
            else:
                self._timer -= dt
                if self._timer <= 0:
                    self._start_idle()
        elif self.state is State.FALLING:
            self.vy += self.gravity * dt
            self.y += self.vy * dt
            if self.y >= self.floor_y:
                self.y = float(self.floor_y)
                self.vy = 0.0
                self._start_idle()

    def drag_start(self) -> None:
        """被鼠标抓住。Task 6 测试覆盖，此处先提供接口。"""
        if self.state is not State.DRAGGED:
            self.state = State.DRAGGED
            self.vy = 0.0

    def drag_move(self, x: float, y: float) -> None:
        """拖拽中更新位置（钳制在活动区域内）。Task 6 测试覆盖。"""
        if self.state is not State.DRAGGED:
            return
        self.x = min(max(0.0, x), self.bounds.width - self.pet_width)
        self.y = min(max(0.0, y), self.bounds.height - self.pet_height)

    def drag_end(self) -> None:
        """松手 → 下落。Task 6 测试覆盖。"""
        if self.state is State.DRAGGED:
            self.state = State.FALLING
            self.vy = 0.0

    def _start_idle(self) -> None:
        self.state = State.IDLE
        self._timer = self._rng.uniform(*self.idle_range)

    def _start_walking(self) -> None:
        self.state = State.WALKING
        self.direction = self._rng.choice((-1, 1))
        self._timer = self._rng.uniform(*self.walk_range)
