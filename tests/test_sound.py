"""声音引擎测试：假播放器 + 假时钟，不碰真实音频设备（spec §2、§7）。"""
import random

from xiaoliang.sound import POKE_COOLDOWN_MS, SoundEngine, should_play


# ── 开关纯函数 ─────────────────────────────────────────────────────

def test_muted_overrides_everything():
    assert should_play({"muted": True, "poke_sfx": True}, "poke_sfx") is False


def test_category_off():
    assert should_play({"muted": False, "poke_sfx": False}, "poke_sfx") is False


def test_missing_category_defaults_on():
    assert should_play({"muted": False}, "hourly_chime") is True


def test_bad_cfg_silent():
    assert should_play(None, "poke_sfx") is False


# ── 引擎（假后端） ─────────────────────────────────────────────────

class FakeEffect:
    def __init__(self):
        self.plays = 0

    def stop(self):
        pass

    def play(self):
        self.plays += 1


class FakeTts:
    def __init__(self):
        self.said = []

    def say(self, text, category):
        self.said.append((text, category))


class FakeMsClock:
    def __init__(self):
        self.now_ms = 0.0

    def __call__(self):
        return self.now_ms


def make_engine(cfg=None, n_effects=2):
    """绕过真实后端构造引擎：手工装配假部件（测试专用捷径）。

    用 __new__ 跳过 __init__（不触碰 QtMultimedia/QtTextToSpeech），
    按 __init__ 的字段契约逐个赋值——字段名与真实实现必须一致。
    """
    eng = SoundEngine.__new__(SoundEngine)
    eng._cfg = cfg if cfg is not None else {
        "muted": False, "poke_sfx": True,
        "sit_reminder": True, "hourly_chime": True}
    eng._rng = random.Random(42)
    eng._clock_ms = FakeMsClock()
    eng._effects = [FakeEffect() for _ in range(n_effects)]
    eng._tts = FakeTts()
    eng._ok = True
    eng._last_poke_ms = float("-inf")
    return eng


def test_play_poke_plays_one_effect():
    eng = make_engine()
    eng.play_poke()
    assert sum(e.plays for e in eng._effects) == 1


def test_play_poke_cooldown():
    eng = make_engine()
    eng.play_poke()
    eng._clock_ms.now_ms = POKE_COOLDOWN_MS - 1
    eng.play_poke()                        # 冷却内 → 忽略
    assert sum(e.plays for e in eng._effects) == 1
    eng._clock_ms.now_ms = POKE_COOLDOWN_MS
    eng.play_poke()                        # 冷却到点 → 播
    assert sum(e.plays for e in eng._effects) == 2


def test_play_poke_muted():
    eng = make_engine(cfg={"muted": True, "poke_sfx": True})
    eng.play_poke()
    assert sum(e.plays for e in eng._effects) == 0


def test_play_poke_empty_pool_silent():
    eng = make_engine(n_effects=0)
    eng.play_poke()                        # 不炸即可


def test_speak_routes_category():
    eng = make_engine()
    eng.speak("起来喝水", "sit_reminder")
    assert eng._tts.said == [("起来喝水", "sit_reminder")]


def test_speak_category_off():
    eng = make_engine(cfg={"muted": False, "hourly_chime": False})
    eng.speak("现在下午3点整", "hourly_chime")
    assert eng._tts.said == []


def test_backend_failure_degrades_silent():
    """后端初始化失败 → _ok=False，一切调用安全空操作。"""
    eng = make_engine()
    eng._ok = False
    eng.play_poke()
    eng.speak("x", "sit_reminder")
    assert eng._tts.said == []
