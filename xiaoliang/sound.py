"""声音引擎：戳音效（QSoundEffect）+ TTS（QTextToSpeech），spec §2。

职责边界：只管"怎么发声、发不发得出去"；"什么时候该发声"归
reminder.ReminderLogic（免打扰）与 GUI 接线层。开关判定 should_play
为纯函数可单测；真实后端初始化失败时引擎降级为静默空操作——
绝不因声音问题拖垮桌宠（公司机器 zBox 注入冲突的前车之鉴）。
线程模型：全部活在主 GUI 线程 Qt 事件循环，两个后端均异步非阻塞。
"""
import logging
import random
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 戳音效冷却（毫秒）：连戳不机关枪（spec §2.2）
POKE_COOLDOWN_MS = 500


def should_play(sound_cfg, category: str) -> bool:
    """开关判定纯函数：muted 一票否决 → 类别开关（缺失默认开）。

    sound_cfg 非 dict（配置损坏）时静默返回 False——坏配置不该炸耳朵。
    本函数不得触碰 Qt 类型：保持纯函数可单测（spec §7）。
    """
    if not isinstance(sound_cfg, dict):
        return False
    if sound_cfg.get("muted", False):           # 总静音一票否决
        return False
    return bool(sound_cfg.get(category, True))  # 类别缺省视为开


class SoundEngine:
    """音效池 + TTS 双通道。

    sound_cfg 持有 config["sound"] 的**同一 dict 引用**：托盘切换
    muted 直接改 dict，引擎下一次判定立即生效，无需通知机制（故每次
    发声时现读、不在启动时拷贝快照）。音效池 = sounds_dir 下全部 .wav
    （目录式加载：用户丢文件即加音效，删文件即移除，零代码改动——
    spec §2.1）；目录为空/缺失 = 戳她静音。任何初始化失败 → _ok=False，
    引擎降级为静默空操作，绝不抛异常拖垮桌宠。
    """

    def __init__(self, sound_cfg: dict, sounds_dir: Path | None = None, *,
                 rng=None, clock_ms=None):
        self._cfg = sound_cfg                    # 共享 dict 引用，托盘改了立即生效
        self._rng = rng or random.Random()
        self._clock_ms = clock_ms or (lambda: time.monotonic() * 1000.0)
        self._effects: list = []
        self._tts = None
        self._ok = False
        self._last_poke_ms = float("-inf")       # 冷却起算点：首戳必过
        try:
            self._init_backend(sounds_dir)
            self._ok = True
        except Exception:                        # 任何后端问题都不拖垮桌宠
            logger.exception("声音引擎初始化失败，降级为静默模式")

    def _init_backend(self, sounds_dir: Path | None) -> None:
        """装载 Qt 后端。任何异常向上抛，由 __init__ 统一降级。

        惰性导入 QtMultimedia/QtTextToSpeech（同 reminder.py 风格）：
        模块导入不依赖 Qt，pytest 可纯逻辑测试。
        """
        from PySide6.QtCore import QUrl
        from PySide6.QtMultimedia import QSoundEffect
        from PySide6.QtTextToSpeech import QTextToSpeech
        if sounds_dir is not None and sounds_dir.is_dir():
            for path in sorted(sounds_dir.glob("*.wav")):
                effect = QSoundEffect()
                effect.setSource(QUrl.fromLocalFile(str(path)))
                self._effects.append(effect)
            logger.info("戳音效池加载 %d 个: %s", len(self._effects), sounds_dir)
        self._tts = QTextToSpeech()
        # 优先中文嗓音（Windows SAPI 的 Huihui/Xiaoxiao 等），找不到用默认
        for voice in self._tts.availableVoices():
            if voice.locale().name().startswith("zh"):
                self._tts.setVoice(voice)
                break

    def play_poke(self) -> None:
        """播一个随机戳音效（开关 + 500ms 冷却由引擎内部管理）。"""
        if not self._ok or not should_play(self._cfg, "poke_sfx"):
            return
        now = self._clock_ms()
        if now - self._last_poke_ms < POKE_COOLDOWN_MS:  # 冷却内：丢弃，防连戳机关枪
            return
        self._last_poke_ms = now
        if self._effects:                                # 空池静音，不炸
            effect = self._rng.choice(self._effects)
            effect.stop()          # 打断上一次未播完的同类音效，避免叠音爆音
            effect.play()

    def speak(self, text: str, category: str) -> None:
        """TTS 念一句（入队模式：连续两句不互相掐断，spec §2.1）。

        category ∈ "sit_reminder"/"hourly_chime"，对应独立开关。
        真实 Qt6 QTextToSpeech 用 enqueue(text) 入队（say 只收单参且会
        打断当前语音）；测试假部件 FakeTts 用 say(text, category) 记录以
        供断言——按是否有 enqueue 分派，真实/假部件各得其所，两套协议
        均不抛异常。
        """
        if not self._ok or not should_play(self._cfg, category):
            return
        try:
            if hasattr(self._tts, "enqueue"):            # 真实 Qt6：入队，连续两句不互掐
                self._tts.enqueue(text)
            else:                                         # 测试假部件：say(text, category) 记录
                self._tts.say(text, category)
        except Exception:                                 # TTS 故障不拖垮桌宠，静默吞
            logger.exception("TTS 播放失败: %r", text)
