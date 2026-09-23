"""宠物行为状态机：纯逻辑，不依赖 Qt，可单元测试。

坐标约定：(x, y) 为角色包围盒左上角，单位逻辑像素，原点为工作区左上角。

v0.2 扩展（spec: 2026-09-21-xiaoliang-v0.2-toy-design.md）：
- 数值联动：注入 PetStatus，随 tick 推进（暂停即冻结），饥饿减速、
  心情差降低攀爬概率
- 时钟注入 + 睡眠时段（支持跨午夜）：到点自动睡、戳醒惺忪、到点醒
- 新状态：POKE_REACT / EATING / SLEEPING / WOKEN / CLIMBING / SITTING_TOP
- 攀爬线：IDLE 出门时按概率走向最近侧壁 → 爬上去 → 顶边坐 →
  50% 原路爬下 / 50% 跳下（复用 FALLING）
"""
import random
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto

from .status import PetStatus


class State(Enum):
    IDLE = auto()
    WALKING = auto()
    DRAGGED = auto()
    FALLING = auto()
    POKE_REACT = auto()    # 被戳：原地反应，播完回原状态
    EATING = auto()        # 进食：吃完按时段回清醒/睡觉
    SLEEPING = auto()      # 睡眠时段内睡觉
    WOKEN = auto()         # 睡觉被戳醒：惺忪几秒后回睡或起床
    CLIMBING = auto()      # 贴侧壁攀爬（climb_direction 区分上/下）
    SITTING_TOP = auto()   # 顶边坐着晃腿发呆


@dataclass(frozen=True)
class Bounds:
    """活动区域尺寸（主显示器工作区，逻辑像素）。"""
    width: int
    height: int


def parse_hhmm(value: str) -> int:
    """"HH:MM" → 自 00:00 起的分钟数。格式合法性由 config 层保证。"""
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def in_sleep_window_minutes(now_m: int, start_m: int, end_m: int) -> bool:
    """睡眠时段判定，窗口为半开区间 [start, end)。

    start < end：当天普通窗口；
    start > end：跨午夜窗口（如 23:00→07:00）= [start,24:00) ∪ [0:00,end)；
    start == end：视为空窗口永不睡（config 层已把相等值回退为默认）。
    """
    if start_m == end_m:
        return False
    if start_m < end_m:
        return start_m <= now_m < end_m
    return now_m >= start_m or now_m < end_m


class PetStateMachine:
    def __init__(self, bounds: Bounds, pet_width: int, pet_height: int, *,
                 walk_speed: float = 60.0,
                 idle_range: tuple[float, float] = (2.0, 8.0),
                 walk_range: tuple[float, float] = (3.0, 10.0),
                 gravity: float = 1500.0,
                 climb_speed: float = 40.0,
                 climb_chance: float = 0.15,
                 climb_low_mood_factor: float = 0.3,
                 hungry_walk_factor: float = 0.6,
                 sit_range: tuple[float, float] = (10.0, 30.0),
                 woken_range: tuple[float, float] = (3.0, 6.0),
                 poke_react_secs: float = 1.0,
                 eating_secs: float = 2.0,
                 start_x: float | None = None,
                 rng: random.Random | None = None,
                 status: PetStatus | None = None,
                 clock=None,
                 sleep_start: str = "23:00",
                 sleep_end: str = "07:00",
                 on_status_change=None):
        self.bounds = bounds
        self.pet_width = pet_width
        self.pet_height = pet_height
        self.walk_speed = walk_speed
        self.idle_range = idle_range
        self.walk_range = walk_range
        self.gravity = gravity
        self.climb_speed = climb_speed
        self.climb_chance = climb_chance
        self.climb_low_mood_factor = climb_low_mood_factor
        self.hungry_walk_factor = hungry_walk_factor
        self.sit_range = sit_range
        self.woken_range = woken_range
        self.poke_react_secs = poke_react_secs
        self.eating_secs = eating_secs
        self._rng = rng or random.Random()
        # ── v0.2 注入依赖：数值系统 / 时钟（默认系统时间）/ 变更回调 ──
        self.status = status or PetStatus()
        self._clock = clock or (lambda: datetime.now().time())
        self._on_status_change = on_status_change
        self._sleep_start_m = parse_hhmm(sleep_start)
        self._sleep_end_m = parse_hhmm(sleep_end)
        self.state = State.IDLE
        self.x = ((bounds.width - pet_width) / 2 if start_x is None
                  else float(start_x))
        self.y = float(self.floor_y)
        self.direction = 1  # 1 向右，-1 向左
        self.vy = 0.0
        self.paused = False
        # 攀爬线：贴哪面墙（-1 左 / 1 右）与爬向（"up"/"down"）
        self.climb_wall = 1
        self.climb_direction = "up"
        # 行走意图：None = 普通溜达；"climb" = 走向目标边缘后开爬
        self._walk_intent: str | None = None
        self._walk_target_x = 0.0
        # 反应类状态的回退目标（戳结束回哪、拖拽前是什么）
        self._pre_poke_state: State | None = None
        self._pre_drag_state: State | None = None
        # 进 POKE_REACT 前原状态的剩余计时（反应播完后原样恢复，
        # 保证"回戳之前的状态"连时长也接续，而不是立刻到期换状态）
        self._resume_timer = 0.0
        # 暂停状态变更监听（GUI 层同步托盘/菜单勾选，见 tray.py）
        self._pause_listeners: list = []
        # v0.3 修复②：EATING 是否发生在空中（攀爬/坐顶时接住食物）——
        # 吃完需要转 FALLING 自然下落，而不是原地回 IDLE（会悬空）
        self._eat_in_air = False
        self._timer = self._rng.uniform(*self.idle_range)

    @property
    def floor_y(self) -> float:
        """地面 y 坐标（角色底边贴工作区底边）。"""
        return self.bounds.height - self.pet_height

    def add_pause_listener(self, callback) -> None:
        """注册暂停状态变更回调，签名 (paused: bool) -> None。"""
        self._pause_listeners.append(callback)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        for callback in self._pause_listeners:
            callback(paused)

    def in_sleep_window(self) -> bool:
        """注入时钟的当前时刻是否落在配置的睡眠时段内。"""
        now = self._clock()
        return in_sleep_window_minutes(now.hour * 60 + now.minute,
                                       self._sleep_start_m, self._sleep_end_m)

    def _effective_walk_speed(self) -> float:
        """行走速度：饱腹过低（<20）时 ×hungry_walk_factor 变慢（蔫了）。"""
        if self.status.is_hungry:
            return self.walk_speed * self.hungry_walk_factor
        return self.walk_speed

    def tick(self, dt: float) -> None:
        """推进 dt 秒。暂停或被拖拽时整体冻结（含数值，spec §2.2）。"""
        if self.paused or self.state is State.DRAGGED:
            return
        # 数值先行：睡觉用睡眠速率（心情回升、饱腹衰减减半）
        self.status.tick(dt, sleeping=self.state is State.SLEEPING)
        in_window = self.in_sleep_window()
        # ── 睡眠时段统一入口（spec §2.2 转换表） ──
        # POKE_REACT/EATING 不打断（播完自然回笼）；FALLING 由 _land 兜底
        if in_window:
            if self.state in (State.IDLE, State.WALKING):
                self._start_sleeping()
                return
            if self.state is State.CLIMBING and self.climb_direction == "up":
                # 向上爬时到点：掉头向下，落地时由 _land 决定入睡
                self.climb_direction = "down"
                return
            if self.state is State.SITTING_TOP:
                self._start_climbing("down")
                return
        # ── 各状态推进 ──
        if self.state is State.IDLE:
            self._timer -= dt
            if self._timer <= 0:
                self._decide_walk_or_climb()
        elif self.state is State.WALKING:
            self._tick_walking(dt)
        elif self.state is State.FALLING:
            self.vy += self.gravity * dt
            self.y += self.vy * dt
            if self.y >= self.floor_y:
                self.y = float(self.floor_y)
                self.vy = 0.0
                self._land()
        elif self.state is State.POKE_REACT:
            self._timer -= dt
            if self._timer <= 0:
                # 反应播完回戳之前的状态，并恢复其剩余计时（原样接续）
                prev = self._pre_poke_state
                if prev is None or prev is State.POKE_REACT:
                    prev = State.IDLE    # 防御：绝不回到反应自身（会死循环）
                self.state = prev
                self._timer = self._resume_timer
        elif self.state is State.EATING:
            self._timer -= dt
            if self._timer <= 0:
                if self._eat_in_air:
                    # v0.3 修复②：墙上/顶吃完 → 自然下落，_land 统一收口
                    self._eat_in_air = False
                    self.state = State.FALLING
                    self.vy = 0.0
                elif in_window:
                    self._start_sleeping()   # 仍在睡眠时段回笼觉
                else:
                    self._start_idle()
        elif self.state is State.SLEEPING:
            if not in_window:
                self._start_idle()       # 到点自然醒
        elif self.state is State.WOKEN:
            self._timer -= dt
            if self._timer <= 0:
                if in_window:
                    self._start_sleeping()
                else:
                    self._start_idle()
        elif self.state is State.CLIMBING:
            self._tick_climbing(dt)
        elif self.state is State.SITTING_TOP:
            self._timer -= dt
            if self._timer <= 0:
                # 坐够了：50% 原路爬下，50% 直接跳下（复用 FALLING）
                if self._rng.random() < 0.5:
                    self._start_climbing("down")
                else:
                    self.state = State.FALLING
                    self.vy = 0.0

    # ── 事件 API（GUI 层调用） ─────────────────────────────────────

    def poke(self) -> bool:
        """戳事件：任何状态都可触发；心情加分由 status 冷却管理。

        返回是否受理：暂停时 False（GUI 据此不播音效）。

        特判（spec §2.2/§2.3）：
        - SLEEPING/WOKEN 中被戳 → 进 WOKEN（睡眼惺忪），不是常规反应
        - DRAGGED 中被戳 = GUI 判定"按下但无有效位移"（点击而非拖拽）：
          回退到拖拽前状态播反应，不触发下落
        """
        if self.paused:                  # v0.3 修复①（spec §1.1）：暂停 = 整体冻结，事件完全无响应
            return False
        if self.status.poke() and self._on_status_change is not None:
            self._on_status_change()     # 数值真的变了才落盘
        base = (self._pre_drag_state if self.state is State.DRAGGED
                else self.state)
        if base is None or base is State.DRAGGED:
            base = State.IDLE            # 防御性兜底
        if base in (State.SLEEPING, State.WOKEN):
            self.state = State.WOKEN
            self._timer = self._rng.uniform(*self.woken_range)
            return True
        if self.state is State.POKE_REACT:
            self._timer = self.poke_react_secs   # 连戳：反应重播
            return True
        self._pre_poke_state = base
        self._resume_timer = self._timer         # 记下原状态剩余计时
        self.state = State.POKE_REACT
        self._timer = self.poke_react_secs
        return True

    def feed(self) -> bool:
        """喂食事件：空闲/走路/睡觉/惺忪/攀爬/坐顶时接受；吃撑或时机
        不对返回 False。返回 False 时零副作用，GUI 可安全忽略。

        v0.3 修复①②（spec §1.1/§1.2）：暂停时无响应；攀爬/坐顶也能
        接住食物——原地吃完后转 FALLING 自然下落（_eat_in_air 标记）。
        """
        if self.paused:
            return False
        airborne = self.state in (State.CLIMBING, State.SITTING_TOP)
        if self.state not in (State.IDLE, State.WALKING,
                              State.SLEEPING, State.WOKEN,
                              State.CLIMBING, State.SITTING_TOP):
            return False
        if not self.status.feed():
            return False                 # 吃撑了
        if self._on_status_change is not None:
            self._on_status_change()
        self.state = State.EATING
        self._timer = self.eating_secs
        self._walk_intent = None         # 半路投喂：停下吃饭
        self._eat_in_air = airborne
        return True

    # ── 拖拽（v0.1 行为不变；drag_start 多记一个回退状态） ─────────

    def drag_start(self) -> None:
        """被鼠标抓住；记住拖拽前状态（释放过快被判定为戳时要回退）。"""
        if self.state is not State.DRAGGED:
            self._pre_drag_state = self.state
            self.state = State.DRAGGED
            self.vy = 0.0

    def drag_move(self, x: float, y: float) -> None:
        """拖拽中更新位置（钳制在活动区域内）。"""
        if self.state is not State.DRAGGED:
            return
        self.x = min(max(0.0, x), self.bounds.width - self.pet_width)
        self.y = min(max(0.0, y), self.bounds.height - self.pet_height)

    def drag_end(self) -> None:
        """松手 → 下落。

        v0.3 修复④（spec §1.3）：暂停中松手不再悬停半空——直接落到
        正下方地面并置 IDLE（暂停渲染本就播 idle 帧，视觉上是"被放下
        后乖乖站好"），恢复暂停后无异常状态需要收口。
        """
        if self.state is State.DRAGGED:
            if self.paused:
                self.y = float(self.floor_y)
                max_x = float(self.bounds.width - self.pet_width)
                self.x = min(max(self.x, 0.0), max_x)
                self._walk_intent = None
                self.state = State.IDLE
                self._timer = self._rng.uniform(*self.idle_range)
                return
            self.state = State.FALLING
            self.vy = 0.0

    # ── 内部：状态进入与推进 ───────────────────────────────────────

    def _tick_walking(self, dt: float) -> None:
        speed = self._effective_walk_speed()
        self.x += self.direction * speed * dt
        if self._walk_intent == "climb":
            # 走向目标边缘：到达即开爬；计时先到则退化为普通散步收尾
            reached = (self.x <= self._walk_target_x if self.direction < 0
                       else self.x >= self._walk_target_x)
            if reached:
                self.x = self._walk_target_x
                self._start_climbing("up")
                return
            self._timer -= dt
            if self._timer <= 0:
                self._walk_intent = None
                self._start_idle()
            return
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

    def _tick_climbing(self, dt: float) -> None:
        if self.climb_direction == "up":
            self.y -= self.climb_speed * dt
            if self.y <= 0.0:
                self.y = 0.0             # 到顶
                self._start_sitting_top()
        else:
            self.y += self.climb_speed * dt
            if self.y >= self.floor_y:
                self.y = float(self.floor_y)
                self._walk_intent = None
                self._land()             # 落地统一收口（时段内直接睡）

    def _decide_walk_or_climb(self) -> None:
        """发呆计时到点后掷骰子：按概率去攀爬，否则普通散步（spec §2.2）。"""
        chance = self.climb_chance
        if self.status.is_bored:         # 心情差（<20）：没兴致玩，概率 ×0.3
            chance *= self.climb_low_mood_factor
        if self._rng.random() < chance:
            self._start_climb_sequence()
        else:
            self._start_walking()

    def _start_climb_sequence(self) -> None:
        """选最近的左/右边缘：已贴壁直接爬，否则先走过去（intent=climb）。"""
        max_x = float(self.bounds.width - self.pet_width)
        center = self.x + self.pet_width / 2
        if center <= self.bounds.width / 2:
            self.climb_wall = -1
            target = 0.0
        else:
            self.climb_wall = 1
            target = max_x
        if self.x == target:             # 恰好已在壁边：省掉走路
            self._start_climbing("up")
            return
        self.direction = 1 if target > self.x else -1
        self._walk_intent = "climb"
        self._walk_target_x = target
        self.state = State.WALKING
        # 计时器给足走完全程的时间（按当前有效速度），+1s 余量；
        # 饥饿减速时也能走到，不会半途而废
        dist = abs(target - self.x)
        self._timer = dist / self._effective_walk_speed() + 1.0

    def _start_climbing(self, direction: str) -> None:
        """贴壁开爬：x 吸附到墙面，竖直速度清零。"""
        self.state = State.CLIMBING
        self.climb_direction = direction
        max_x = float(self.bounds.width - self.pet_width)
        self.x = max_x if self.climb_wall > 0 else 0.0
        self.vy = 0.0
        self._walk_intent = None

    def _start_sitting_top(self) -> None:
        self.state = State.SITTING_TOP
        self._timer = self._rng.uniform(*self.sit_range)

    def _start_idle(self) -> None:
        self.state = State.IDLE
        self._walk_intent = None
        self._timer = self._rng.uniform(*self.idle_range)

    def _start_walking(self) -> None:
        self.state = State.WALKING
        self._walk_intent = None
        self.direction = self._rng.choice((-1, 1))
        self._timer = self._rng.uniform(*self.walk_range)

    def _start_sleeping(self) -> None:
        self.state = State.SLEEPING
        self._walk_intent = None

    def _land(self) -> None:
        """落地统一收口：睡眠时段内直接睡，否则回发呆。"""
        if self.in_sleep_window():
            self._start_sleeping()
        else:
            self._start_idle()
