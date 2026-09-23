"""提醒服务：久坐提醒 + 整点报时（spec §3）。

分层：ReminderLogic 是纯逻辑（时钟/空闲时长外部注入，pytest 假时钟
可测全部规则）；ReminderService 只是 Qt 心跳驱动器（QTimer 每
heartbeat 秒调一次 logic.tick）。ctypes 调 Win32 GetLastInputInfo 做
键鼠空闲检测——标准库实现，零新增依赖。
"""
import ctypes
import logging
import random
from datetime import datetime

logger = logging.getLogger(__name__)

# 久坐提醒文案池（代码可读可改；随机挑一句避免复读机感）
SIT_TEXTS = (
    "已经坐了很久啦，起来接杯水、活动活动腿吧",
    "久坐不好，站起来伸个懒腰放松一下",
    "该起来走一走了，顺便望望远处让眼睛休息",
    "连续坐了快一个小时啦，起来动动脖子和腰",
)


def hour_text(now: datetime) -> str:
    """整点报时文案：中文时段 + 12 小时制，如"现在下午3点整"。"""
    h = now.hour
    if h < 6:
        period = "凌晨"
    elif h < 9:
        period = "早上"
    elif h < 12:
        period = "上午"
    elif h < 13:
        period = "中午"
    elif h < 18:
        period = "下午"
    else:
        period = "晚上"
    return f"现在{period}{h % 12 or 12}点整"


def get_idle_seconds() -> float:
    """Win32 键鼠空闲秒数（GetLastInputInfo）。失败时返回 0（视为在场，
    宁可多提醒不可漏提醒）。作为可注入 provider，测试用假数据替换。"""
    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        elapsed = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        return max(0.0, elapsed / 1000.0)   # dwTime/GetTickCount 均为毫秒
    except (AttributeError, OSError):       # 非 Windows 或调用失败
        return 0.0


class ReminderLogic:
    """纯逻辑：外部驱动 tick(now, idle_secs)，返回本次触发的事件列表。

    久坐：心跳按名义间隔累加"连续在座时长"（不用真实时间差，防止
    心跳抖动导致重复计时）；空闲超阈值判定离开 → 清零重数。
    整点：小时数变化即报时；两次心跳真实跨度 > heartbeat×4 判定系统
    休眠唤醒 → 只静默同步不补报（spec §3.4 防连环报时）。
    免打扰：dnd() 为真（暂停/睡眠时段）时压制一切并重置累计。
    """

    def __init__(self, sit_minutes: float = 45,
                 idle_threshold_minutes: float = 5, *,
                 heartbeat_secs: float = 15,
                 rng: random.Random | None = None,
                 dnd=None):
        self.sit_secs = sit_minutes * 60
        self.idle_threshold = idle_threshold_minutes * 60
        self.heartbeat = heartbeat_secs
        self._rng = rng or random.Random()
        self._dnd = dnd or (lambda: False)
        self._sat_secs = 0.0               # 连续在座累计
        self._last_hour: int | None = None
        self._last_tick: datetime | None = None

    def tick(self, now: datetime, idle_secs: float) -> list:
        """推进一次心跳，返回 [("sit"|"hour", 文案), ...]（通常 0 或 1 条）。"""
        # 真实时间跨度：远超心跳间隔 = 系统睡过（合盖/休眠唤醒）
        gap = ((now - self._last_tick).total_seconds()
               if self._last_tick is not None else None)
        self._last_tick = now
        slept = gap is not None and gap > self.heartbeat * 4
        away = idle_secs >= self.idle_threshold
        if self._dnd():
            # 免打扰：重置久坐累计并同步小时数（解除后不误报旧账）
            self._sat_secs = 0.0
            self._last_hour = now.hour
            return []
        events = []
        # ── 整点报时 ──
        if self._last_hour is None:
            self._last_hour = now.hour     # 首次心跳只初始化，不报时
        elif now.hour != self._last_hour:
            self._last_hour = now.hour
            if not slept and not away:     # 休眠唤醒/人不在 → 跳过
                events.append(("hour", hour_text(now)))
        # ── 久坐提醒 ──
        if away or slept:
            self._sat_secs = 0.0           # 离开或休眠 → 不算在座
        else:
            self._sat_secs += self.heartbeat
            if self._sat_secs >= self.sit_secs:
                self._sat_secs = 0.0       # 触发后清零，开始下一轮
                events.append(("sit", self._rng.choice(SIT_TEXTS)))
        return events


class ReminderService:
    """Qt 心跳驱动器：QTimer 每 heartbeat 秒调一次 logic.tick。

    on_event(kind, text) 回调由接线方（main.py）实现：kind ∈ "sit"/"hour"。
    空闲 provider 与时钟可注入（测试用），默认实调 Win32 / datetime.now。
    """

    def __init__(self, logic: ReminderLogic, on_event, *,
                 idle_provider=get_idle_seconds, clock=None):
        from PySide6.QtCore import QTimer
        self._logic = logic
        self._on_event = on_event
        self._idle = idle_provider
        self._clock = clock or datetime.now
        self._timer = QTimer()
        self._timer.setInterval(int(logic.heartbeat * 1000))
        self._timer.timeout.connect(self._fire)

    def start(self) -> None:
        self._timer.start()

    def _fire(self) -> None:
        try:
            events = self._logic.tick(self._clock(), self._idle())
        except Exception:                  # 提醒失败不能拖垮桌宠主循环
            logger.exception("提醒服务 tick 异常")
            return
        for kind, text in events:
            self._on_event(kind, text)
