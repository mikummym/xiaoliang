"""宠物数值系统：心情/饱腹度纯逻辑模块，不依赖 Qt（spec §2.1）。

两项数值范围 [0, 100]，初始 80.0：
- 清醒时持续衰减；饥饿（饱腹<20）时心情衰减 ×3；睡觉时心情回升、饱腹衰减减半
- 喂食 +25/+5，饱腹 >90 拒绝；戳 +3 心情，10 秒数值冷却
- 持久化为 status.json（与 config.json 同目录同风格）：损坏回退默认，
  保存失败仅告警——数值系统永远不该让程序崩溃
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 速率与阈值常量（spec §2.1；调数值只改这里） ──────────────────────
DECAY_FULLNESS_PER_MIN = 0.5     # 清醒时饱腹衰减/分钟
DECAY_MOOD_PER_MIN = 0.3         # 清醒时心情衰减/分钟
HUNGRY_THRESHOLD = 20.0          # 饱腹低于此值视为"饥饿"
HUNGRY_MOOD_MULTIPLIER = 3.0     # 饥饿时心情衰减倍率
SLEEP_MOOD_PER_MIN = 1.0         # 睡觉时心情回升/分钟
SLEEP_FULLNESS_PER_MIN = 0.25    # 睡觉时饱腹衰减/分钟（清醒的一半）

FEED_FULLNESS = 25.0             # 单次喂食恢复饱腹
FEED_MOOD = 5.0                  # 单次喂食恢复心情
FEED_REFUSE_ABOVE = 90.0         # 饱腹超过此值拒绝喂食（GUI 置灰同判据）
POKE_MOOD = 3.0                  # 单次戳恢复心情
POKE_COOLDOWN = 10.0             # 戳的数值冷却（秒）；冷却中动画照播数值不加

DEFAULT_VALUE = 80.0             # 初始/回退默认值
MIN_VALUE = 0.0
MAX_VALUE = 100.0


class PetStatus:
    """心情 + 饱腹度。所有方法纯计算，可单测；文件 IO 仅在 load/save。"""

    def __init__(self, mood: float = DEFAULT_VALUE,
                 fullness: float = DEFAULT_VALUE):
        self.mood = self._clamp(mood)
        self.fullness = self._clamp(fullness)
        # 戳冷却计时：初始视为冷却已结束（启动后第一次戳立即生效）
        self._poke_elapsed = POKE_COOLDOWN

    @staticmethod
    def _clamp(v: float) -> float:
        return min(max(MIN_VALUE, float(v)), MAX_VALUE)

    def tick(self, dt_seconds: float, sleeping: bool = False) -> None:
        """推进 dt 秒的数值变化。秒速率 = 分钟速率 / 60。

        sleeping=True 用睡眠速率（心情回升、饱腹衰减减半）。
        暂停时上层（状态机）不调用本方法 → 数值随暂停冻结（spec §2.2）。
        """
        minutes = dt_seconds / 60.0
        if sleeping:
            self.fullness -= SLEEP_FULLNESS_PER_MIN * minutes
            self.mood += SLEEP_MOOD_PER_MIN * minutes
        else:
            self.fullness -= DECAY_FULLNESS_PER_MIN * minutes
            # 饥饿加速心情恶化：倍率在饱腹扣减后判定
            multiplier = (HUNGRY_MOOD_MULTIPLIER
                          if self.fullness < HUNGRY_THRESHOLD else 1.0)
            self.mood -= DECAY_MOOD_PER_MIN * multiplier * minutes
        self._poke_elapsed += dt_seconds
        self.mood = self._clamp(self.mood)
        self.fullness = self._clamp(self.fullness)

    @property
    def can_feed(self) -> bool:
        """是否允许喂食（GUI 菜单置灰判据，与 feed() 保持同一标准）。"""
        return self.fullness <= FEED_REFUSE_ABOVE

    def feed(self) -> bool:
        """喂食：饱腹 ≤90 成功 +25/+5；吃撑返回 False，数值零副作用。"""
        if not self.can_feed:
            return False
        self.fullness = self._clamp(self.fullness + FEED_FULLNESS)
        self.mood = self._clamp(self.mood + FEED_MOOD)
        return True

    def poke(self) -> bool:
        """戳：冷却结束返回 True 并 +3 心情；冷却中返回 False（不加数值）。"""
        if self._poke_elapsed < POKE_COOLDOWN:
            return False
        self._poke_elapsed = 0.0
        self.mood = self._clamp(self.mood + POKE_MOOD)
        return True

    @property
    def is_hungry(self) -> bool:
        """饱腹过低：状态机据此把走路速度 ×0.6（spec §2.1）。"""
        return self.fullness < HUNGRY_THRESHOLD

    @property
    def is_bored(self) -> bool:
        """心情过低：状态机据此把攀爬概率 ×0.3（spec §2.1）。"""
        return self.mood < HUNGRY_THRESHOLD

    def save(self, path: Path) -> None:
        """写入 status.json；OSError 仅告警不抛（只读目录不该毁掉运行）。"""
        data = {"mood": self.mood, "fullness": self.fullness}
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except OSError as exc:
            logger.warning("状态保存失败 %s: %s", path, exc)

    @classmethod
    def load(cls, path: Path) -> "PetStatus":
        """从 status.json 恢复；缺失/损坏/字段非法均回退默认值（记警告）。

        不做离线衰减补算（spec §2.1：离线冻结），故文件中无需时间戳。
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return cls()
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("状态文件 %s 读取失败，使用默认值: %s", path, exc)
            return cls()
        if not isinstance(data, dict):
            logger.warning("状态文件 %s 不是 JSON 对象，使用默认值", path)
            return cls()
        values = {}
        for key in ("mood", "fullness"):
            v = data.get(key)
            # bool 是 int 子类，须显式排除（与 config.py 同风格）
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                logger.warning("状态项 %s=%r 非法，使用默认值 %s",
                               key, v, DEFAULT_VALUE)
                v = DEFAULT_VALUE
            values[key] = float(v)
        return cls(mood=values["mood"], fullness=values["fullness"])
