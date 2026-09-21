# 小凉 v0.2（玩具型）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 v0.1 观赏型桌宠之上实现玩具型能力：戳有反应、右键喂食、心情/饱腹度数值（持久化）、定时睡觉（可戳醒）、爬屏幕边缘到顶边坐。

**Architecture:** 扩展单一 PetStateMachine（11 状态），数值系统独立为纯逻辑模块 status.py；状态机注入 RNG/时钟/状态对象，全部新行为可 pytest 纯逻辑测试；GUI 层只做事件转发与渲染。

**Tech Stack:** Python 3.10 / PySide6 6.11.2 / pytest / Pillow（素材生成）/ PyInstaller（打包）。

**Spec:** `docs/superpowers/specs/2026-09-21-xiaoliang-v0.2-toy-design.md`（数值与行为的唯一权威，冲突时以 spec 为准）

## Global Constraints

- 工作目录 `D:\projects\xiaoliang`，分支 `feat/v0.2-toy`；venv 为 `.venv`，一律用 `.venv\Scripts\python` / `.venv\Scripts\pyinstaller`
- Shell 是 Windows PowerShell 5.1：**没有 `&&`**，用 `; if ($?) { }` 串联
- `xiaoliang/state_machine.py` 与 `xiaoliang/status.py` **禁止 import PySide6**（纯逻辑）
- **中文注释规范（用户要求）**：模块级 docstring 说明职责；类/函数 docstring 说明用途与参数；关键逻辑（状态转换、数值公式、边界处理、注入点）写行内中文注释，解释"为什么"而非复述代码
- **禁止启动 GUI 程序**（不运行 `python main.py`、不运行 dist 下 exe）。验证手段仅限：pytest、`python -c "import ..."`、PIL 素材脚本、`tools/check_sprites.py`（headless 无窗口，允许）
- **禁止任何 git remote 操作**（不 push / 不 pull / 不建 PR）
- 每条 commit message 末尾加一行：`Co-Authored-By: Claude Code <noreply@anthropic.com>`
- `config.json` / `status.json` / `dist/` / `build/` 不入库（status.json 的 gitignore 在 Task 6 补充）
- 所有数值以 spec §2 为准（衰减率、阈值、冷却、速度、时长），不得自行调整
- 测试风格沿用现有 tests/：纯函数 + FakeRandom/FakeClock 注入，不用 pytest-qt

## File Structure

| 文件 | 动作 | 职责 |
|------|------|------|
| `xiaoliang/status.py` | 新建 | 心情/饱腹度：衰减/喂食/戳冷却/持久化（纯逻辑） |
| `tests/test_status.py` | 新建 | status 全覆盖单测 |
| `xiaoliang/config.py` | 修改 | +sleep_start/sleep_end 默认值、HH:MM 校验、相等回退 |
| `tests/test_config.py` | 修改 | 追加睡眠时段配置测试 |
| `xiaoliang/state_machine.py` | 重写扩展 | +6 状态、poke/feed 事件、时钟/状态注入、攀爬线 |
| `tests/test_state_machine.py` | 修改 | 更新 fixture（FakeClock、random()），追加新状态全路径测试 |
| `tools/gen_placeholder_assets.py` | 重写扩展 | +6 组新占位素材绘制函数 |
| `xiaoliang/sprite.py` | 微改 | get_frame 增加 reverse/mirror 关键字参数 |
| `xiaoliang/pet_window.py` | 重写扩展 | 戳/拖拽判定、右键 QMenu、tooltip、攀爬渲染 |
| `xiaoliang/tray.py` | 微改 | 注册暂停回调，与右键菜单双向同步 |
| `main.py` | 修改 | 装配 PetStatus（加载/60s 定时保存/事件保存/退出保存）、睡眠配置传入 |
| `README.md` / `assets/README.md` | 修改 | v0.2 功能、验收清单、已知问题、新动作换图说明 |
| `.gitignore` | 微改 | +status.json |

---

### Task 1: 数值系统 status.py

**Files:**
- Create: `xiaoliang/status.py`
- Test: `tests/test_status.py`

**Interfaces:**
- Consumes: 无（独立纯逻辑模块）
- Produces: `PetStatus(mood=80.0, fullness=80.0)`；方法 `tick(dt_seconds, sleeping=False)`、`feed() -> bool`、`poke() -> bool`、`save(path)`、类方法 `load(path) -> PetStatus`；属性 `can_feed -> bool`、`is_hungry -> bool`（fullness<20）、`is_bored -> bool`（mood<20）；模块常量 `FEED_REFUSE_ABOVE=90.0` 等。Task 3 的状态机与 Task 5 的 GUI 都依赖这些精确签名。

- [ ] **Step 1: 写失败测试 `tests/test_status.py`**

```python
"""数值系统 PetStatus 单元测试（纯逻辑，spec §2.1）。"""
import logging

import pytest

from xiaoliang.status import PetStatus


def test_initial_values():
    s = PetStatus()
    assert s.mood == 80.0
    assert s.fullness == 80.0


def test_awake_decay_per_minute():
    s = PetStatus()
    s.tick(60.0)
    assert s.fullness == pytest.approx(79.5)   # -0.5/分钟
    assert s.mood == pytest.approx(79.7)       # -0.3/分钟


def test_hungry_triples_mood_decay():
    s = PetStatus(fullness=10.0)               # <20 视为饥饿
    s.tick(60.0)
    assert s.mood == pytest.approx(79.1)       # -0.3×3 = -0.9/分钟


def test_sleeping_recovers_mood_and_halves_fullness_decay():
    s = PetStatus()
    s.tick(60.0, sleeping=True)
    assert s.mood == pytest.approx(81.0)       # 睡觉心情 +1.0/分钟
    assert s.fullness == pytest.approx(79.75)  # 睡觉饱腹衰减减半 -0.25/分钟


def test_values_clamped_to_zero():
    s = PetStatus(mood=0.4, fullness=0.2)
    s.tick(600.0)                              # 10 分钟衰减 → 双双触底
    assert s.mood == 0.0
    assert s.fullness == 0.0


def test_feed_gains_and_clamps():
    s = PetStatus(mood=50.0, fullness=50.0)
    assert s.feed() is True
    assert s.fullness == pytest.approx(75.0)   # +25
    assert s.mood == pytest.approx(55.0)       # +5


def test_feed_clamped_at_100():
    s = PetStatus(mood=99.0, fullness=90.0)    # 90 恰好允许（>90 才拒绝）
    assert s.feed() is True
    assert s.mood == 100.0
    assert s.fullness == 100.0


def test_feed_refused_above_90_no_side_effect():
    s = PetStatus(mood=50.0, fullness=91.0)
    assert s.feed() is False
    assert s.fullness == 91.0                  # 数值不变
    assert s.mood == 50.0


def test_can_feed_property():
    assert PetStatus(fullness=90.0).can_feed is True
    assert PetStatus(fullness=90.1).can_feed is False


def test_poke_cooldown():
    s = PetStatus(mood=50.0)
    assert s.poke() is True
    assert s.mood == pytest.approx(53.0)       # +3
    assert s.poke() is False                   # 冷却中拒绝
    s.tick(9.9)
    assert s.poke() is False                   # 累计 9.9s < 10s
    s.tick(0.2)                                # 累计 10.1s ≥ 10s
    assert s.poke() is True
    # 53 - 清醒衰减 0.3×(10.1/60) + 3
    assert s.mood == pytest.approx(56.0 - 0.3 * (10.1 / 60))


def test_poke_in_cooldown_still_ticks_elapsed():
    s = PetStatus()
    s.poke()
    s.tick(5.0)
    assert s.poke() is False                   # 5s 仍在冷却


def test_save_load_roundtrip(tmp_path):
    path = tmp_path / "status.json"
    s = PetStatus(mood=42.5, fullness=66.25)
    s.save(path)
    loaded = PetStatus.load(path)
    assert loaded.mood == pytest.approx(42.5)
    assert loaded.fullness == pytest.approx(66.25)


def test_load_missing_file_returns_defaults(tmp_path):
    s = PetStatus.load(tmp_path / "nope.json")
    assert s.mood == 80.0
    assert s.fullness == 80.0


def test_load_corrupt_file_returns_defaults(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("not json{{", encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 80.0
    assert s.fullness == 80.0


def test_load_invalid_field_falls_back_per_key(tmp_path):
    path = tmp_path / "status.json"
    path.write_text('{"mood": "high", "fullness": 55}', encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 80.0                         # 坏字段回退默认
    assert s.fullness == pytest.approx(55.0)      # 好字段保留


def test_load_out_of_range_clamped(tmp_path):
    path = tmp_path / "status.json"
    path.write_text('{"mood": 500, "fullness": -3}', encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 100.0
    assert s.fullness == 0.0


def test_load_non_object_returns_defaults(tmp_path):
    path = tmp_path / "status.json"
    path.write_text("[1, 2]", encoding="utf-8")
    s = PetStatus.load(path)
    assert s.mood == 80.0


def test_save_failure_only_warns(tmp_path, caplog):
    bad = tmp_path / "missing_dir" / "status.json"   # 父目录不存在 → OSError
    s = PetStatus()
    with caplog.at_level(logging.WARNING):
        s.save(bad)                                  # 不抛异常
    assert "保存失败" in caplog.text
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python -m pytest tests\test_status.py -v`
Expected: FAIL（ModuleNotFoundError: xiaoliang.status）

- [ ] **Step 3: 实现 `xiaoliang/status.py`**

```python
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
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python -m pytest tests\test_status.py -v`
Expected: 全部 PASS（17 个）

- [ ] **Step 5: 纯逻辑守卫 + 全量回归**

Run: `.venv\Scripts\python -c "import xiaoliang.status, sys; assert not any(m.startswith('PySide6') for m in sys.modules), 'status.py 不许依赖 Qt'; print('OK: no Qt')"`
Expected: `OK: no Qt`

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS（31 旧 + 17 新 = 48）

- [ ] **Step 6: Commit**

```powershell
git add xiaoliang/status.py tests/test_status.py
git commit -m @'
feat: 数值系统 status.py（心情/饱腹度衰减、喂食、戳冷却、持久化）

Co-Authored-By: Claude Code <noreply@anthropic.com>
'@
```

---

### Task 2: 配置扩展 sleep_start / sleep_end

**Files:**
- Modify: `xiaoliang/config.py`
- Test: `tests/test_config.py`（追加）

**Interfaces:**
- Consumes: v0.1 config.py 的逐键校验机制（`_COERCE` 表 + `load_config` 回退逻辑）
- Produces: `DEFAULT_CONFIG` 含 `"sleep_start": "23:00"`, `"sleep_end": "07:00"`；`load_config` 返回的 dict 保证这两个键存在且为合法 HH:MM 字符串、且不相等。Task 6 的 main.py 直接把 `cfg["sleep_start"]` / `cfg["sleep_end"]` 传给状态机。

- [ ] **Step 1: 在 `tests/test_config.py` 末尾追加失败测试**

（保持文件既有 import 与风格；若文件头没有 `import json` / `import pytest` 则补上）

```python
# ── v0.2：睡眠时段配置（spec §2.5） ────────────────────────────────

def test_sleep_keys_default(tmp_path):
    cfg = load_config(tmp_path / "absent.json")
    assert cfg["sleep_start"] == "23:00"
    assert cfg["sleep_end"] == "07:00"


def test_sleep_keys_valid_custom(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"sleep_start": "22:30", "sleep_end": "06:15"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "22:30"
    assert cfg["sleep_end"] == "06:15"


@pytest.mark.parametrize("bad", [
    "24:00", "7:00", "23:60", "2300", "", "ab:cd", None, 23, True,
])
def test_sleep_keys_invalid_fall_back(tmp_path, bad):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"sleep_start": bad, "sleep_end": bad}),
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "23:00"
    assert cfg["sleep_end"] == "07:00"


def test_sleep_keys_equal_fall_back(tmp_path):
    # 相等 = 空窗口（永不睡觉），视为非法配置，两键一起回退默认
    p = tmp_path / "config.json"
    p.write_text('{"sleep_start": "08:00", "sleep_end": "08:00"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "23:00"
    assert cfg["sleep_end"] == "07:00"


def test_one_sleep_key_invalid_only_that_key_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"sleep_start": "22:00", "sleep_end": " nope"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sleep_start"] == "22:00"   # 合法键保留
    assert cfg["sleep_end"] == "07:00"     # 非法键回退
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv\Scripts\python -m pytest tests\test_config.py -v`
Expected: 新增用例 FAIL（KeyError: 'sleep_start'），旧用例 PASS

- [ ] **Step 3: 修改 `xiaoliang/config.py`**

3a. 文件头 `import json` 之后加：

```python
import re
```

3b. `DEFAULT_CONFIG` 改为：

```python
DEFAULT_CONFIG = {
    "scale": 2,
    "walk_speed": 60.0,
    "paused": False,
    "sleep_start": "23:00",   # 睡眠时段起点（含），HH:MM 24 小时制
    "sleep_end": "07:00",     # 睡眠时段终点（不含）；start>end 表示跨午夜
}
```

3c. `_coerce_paused` 之后新增：

```python
# HH:MM 24 小时制（spec §2.5）：00:00–23:59，分钟 00–59
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _coerce_hhmm(v):
    """sleep_start/sleep_end 必须是合法 'HH:MM' 字符串。"""
    if not isinstance(v, str) or not _HHMM_RE.match(v):
        raise ValueError(f"必须是 'HH:MM' 格式字符串，收到 {v!r}")
    return v
```

3d. `_COERCE` 表加两项：

```python
_COERCE = {
    "scale": _coerce_scale,
    "walk_speed": _coerce_walk_speed,
    "paused": _coerce_paused,
    "sleep_start": _coerce_hhmm,
    "sleep_end": _coerce_hhmm,
}
```

3e. `load_config` 的 for 循环之后、`return cfg` 之前加跨键校验：

```python
    # 跨键校验：起止相等 = 空窗口（永不睡觉），视为非法配置，双双回退默认
    # （spec §7：start==end 视为不睡觉，校验时回退）
    if cfg["sleep_start"] == cfg["sleep_end"]:
        logger.warning("sleep_start 与 sleep_end 相同（%s），回退默认睡眠时段",
                       cfg["sleep_start"])
        cfg["sleep_start"] = DEFAULT_CONFIG["sleep_start"]
        cfg["sleep_end"] = DEFAULT_CONFIG["sleep_end"]
```

- [ ] **Step 4: 运行确认通过**

Run: `.venv\Scripts\python -m pytest tests\test_config.py -v`
Expected: 全部 PASS

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS（48 + 13 新增参数化等）

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/config.py tests/test_config.py
git commit -m @'
feat: 配置支持 sleep_start/sleep_end 睡眠时段（HH:MM 校验+相等回退）

Co-Authored-By: Claude Code <noreply@anthropic.com>
'@
```

---

### Task 3: 状态机扩展（睡觉/戳/吃/攀爬全部新状态）

**Files:**
- Modify: `xiaoliang/state_machine.py`（全文件替换为下方内容）
- Test: `tests/test_state_machine.py`（替换 fixture + 追加测试）

**Interfaces:**
- Consumes: Task 1 的 `PetStatus`（`tick/feed/poke/is_hungry/is_bored`）
- Produces（Task 5 GUI、Task 6 main 依赖的精确签名）:
  - `State` 新增成员：`POKE_REACT / EATING / SLEEPING / WOKEN / CLIMBING / SITTING_TOP`
  - `PetStateMachine.__init__` 新增关键字参数（均有默认值，v0.1 调用方式不受影响）：`climb_speed=40.0, climb_chance=0.15, climb_low_mood_factor=0.3, hungry_walk_factor=0.6, sit_range=(10.0,30.0), woken_range=(3.0,6.0), poke_react_secs=1.0, eating_secs=2.0, status=None, clock=None, sleep_start="23:00", sleep_end="07:00", on_status_change=None`
  - 新公开属性/方法：`machine.status`、`machine.climb_wall`（-1 左 / 1 右）、`machine.climb_direction`（"up"/"down"）、`poke() -> None`、`feed() -> bool`、`in_sleep_window() -> bool`、`add_pause_listener(callback)`（callback 签名 `(paused: bool) -> None`）
  - 模块级纯函数：`in_sleep_window_minutes(now_m, start_m, end_m) -> bool`、`parse_hhmm("HH:MM") -> int`
  - `clock` 注入约定：无参可调用对象，返回 `datetime.time`
  - `on_status_change` 约定：poke/feed 数值实际变化后调用（用于 Task 6 即时落盘）

- [ ] **Step 1: 更新 `tests/test_state_machine.py` 的 fixture**

文件头部 import 与 `FakeRandom`/`make_machine` **整体替换**为（v0.1 既有测试函数全部保留不动）：

```python
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
```

注意：既有 v0.1 测试一行不改，它们在新 fixture 下必须依然全绿（默认时钟=中午不在睡眠时段、默认 random=0.99 不触发攀爬）。

- [ ] **Step 2: 在 `tests/test_state_machine.py` 末尾追加新状态测试**

```python
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


def test_feed_refused_while_climbing():
    m = make_machine(rng=FakeRandom(random_value=0.0), start_x=800 - 64)
    m.tick(1.1)
    assert m.state is State.CLIMBING
    assert m.feed() is False             # 爬墙时不喂（spec 裁定见计划注记）


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
    for _ in range(90):
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
```

计划注记（实现裁定，spec 未明说处）：
- **feed() 仅接受 IDLE / WALKING / SLEEPING / WOKEN** 四种状态；其余状态（含 CLIMBING/SITTING_TOP/EATING/POKE_REACT/FALLING/DRAGGED）返回 False 且零副作用。
- **睡觉中被戳 → WOKEN**（而非常规 POKE_REACT）；WOKEN 中再戳 → 重置惺忪计时。
- spec §2.1 "发呆概率相应升高"由攀爬概率降低自然满足（不爬即普通溜达/发呆），无需单独机制。

- [ ] **Step 3: 运行确认新测试失败**

Run: `.venv\Scripts\python -m pytest tests\test_state_machine.py -v`
Expected: 新增用例大量 FAIL（State 无新成员 / 无 poke 等），v0.1 旧用例 PASS

- [ ] **Step 4: 全文件替换 `xiaoliang/state_machine.py`**

```python
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
                # 吃完：仍在睡眠时段回笼觉，否则回发呆
                if in_window:
                    self._start_sleeping()
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

    def poke(self) -> None:
        """戳事件：任何状态都可触发；心情加分由 status 冷却管理。

        特判（spec §2.2/§2.3）：
        - SLEEPING/WOKEN 中被戳 → 进 WOKEN（睡眼惺忪），不是常规反应
        - DRAGGED 中被戳 = GUI 判定"按下但无有效位移"（点击而非拖拽）：
          回退到拖拽前状态播反应，不触发下落
        """
        if self.status.poke() and self._on_status_change is not None:
            self._on_status_change()     # 数值真的变了才落盘
        base = (self._pre_drag_state if self.state is State.DRAGGED
                else self.state)
        if base is None or base is State.DRAGGED:
            base = State.IDLE            # 防御性兜底
        if base in (State.SLEEPING, State.WOKEN):
            self.state = State.WOKEN
            self._timer = self._rng.uniform(*self.woken_range)
            return
        if self.state is State.POKE_REACT:
            self._timer = self.poke_react_secs   # 连戳：反应重播
            return
        self._pre_poke_state = base
        self._resume_timer = self._timer         # 记下原状态剩余计时
        self.state = State.POKE_REACT
        self._timer = self.poke_react_secs

    def feed(self) -> bool:
        """喂食事件：仅空闲/走路/睡觉/惺忪时接受；吃撑或时机不对返回 False。

        返回 False 时零副作用（数值不变、状态不变），GUI 可安全忽略。
        """
        if self.state not in (State.IDLE, State.WALKING,
                              State.SLEEPING, State.WOKEN):
            return False
        if not self.status.feed():
            return False                 # 吃撑了
        if self._on_status_change is not None:
            self._on_status_change()
        self.state = State.EATING
        self._timer = self.eating_secs
        self._walk_intent = None         # 半路投喂：停下吃饭
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
        """松手 → 下落。"""
        if self.state is State.DRAGGED:
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
```

- [ ] **Step 5: 运行全部状态机测试**

Run: `.venv\Scripts\python -m pytest tests\test_state_machine.py -v`
Expected: 全部 PASS（v0.1 旧用例 14 个 + 新用例约 35 个）

- [ ] **Step 6: 纯逻辑守卫 + 全量回归**

Run: `.venv\Scripts\python -c "import xiaoliang.state_machine, sys; assert not any(m.startswith('PySide6') for m in sys.modules), '状态机不许依赖 Qt'; print('OK: no Qt')"`
Expected: `OK: no Qt`

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS，无失败无跳过异常

- [ ] **Step 7: Commit**

```powershell
git add xiaoliang/state_machine.py tests/test_state_machine.py
git commit -m @'
feat: 状态机扩展——睡觉/戳醒/喂食/攀爬/顶边坐全部新状态

注入时钟与 PetStatus；睡眠时段支持跨午夜；攀爬线含饥饿减速、
心情差降概率、到点掉头爬下等数值联动。v0.1 全部旧测试保持通过。

Co-Authored-By: Claude Code <noreply@anthropic.com>
'@
```

---

### Task 4: 6 组新占位素材（戳/吃/睡/醒/爬/顶坐）

**Files:**
- Modify: `tools/gen_placeholder_assets.py`（全文件替换为下方内容）
- Output: `assets/*.png` + `assets/manifest.json`（脚本生成物，随 commit 入库——v0.1 起 assets 就在仓库里）

**Interfaces:**
- Consumes: 无代码依赖（独立任务，排在 Task 3 之后执行）
- Produces（Task 5 渲染依赖）: manifest 新增 6 个动作名 `poke_react / eating / sleeping / woken / climbing / sitting_top`，帧数/帧率严格按 spec §2.4（2@6 / 4@6 / 2@2 / 2@3 / 4@8 / 4@3）；`climbing` 只画"右壁向上爬"，爬下倒放、左壁镜像由 `SpriteManager.get_frame` 渲染时完成（Task 5 实现）

- [ ] **Step 1: 全文件替换 `tools/gen_placeholder_assets.py`**

```python
"""生成占位像素素材：一个蓝发小人（后续可替换为 AI 生成的正式素材）。

用法（项目根目录）：
    .venv\\Scripts\\python tools\\gen_placeholder_assets.py

输出到 assets\\：每个动作一张横向排列的 sprite sheet（帧尺寸 64x64，透明背景），
外加描述帧数/帧率的 manifest.json。

v0.2 新增 6 组动作（spec §2.4）：poke_react / eating / sleeping / woken /
climbing / sitting_top。climbing 只画"右壁向上爬"：爬下 = 帧序倒放、
左壁 = 水平镜像，均由渲染层（SpriteManager.get_frame）完成，无需额外素材。
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

FRAME = 64
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

HAIR = (110, 150, 235, 255)   # 蓝发
SKIN = (245, 220, 200, 255)   # 皮肤
CLOTH = (60, 64, 80, 255)     # 深色衣服
EYE = (40, 40, 50, 255)       # 眼睛/鞋
BOWL = (210, 210, 220, 255)   # 喂食用的碗


def draw_pet(d: ImageDraw.ImageDraw, *, leg_offset: int = 0,
             arms_up: bool = False, body_dy: int = 0) -> None:
    """在单帧内画小人。leg_offset: 走路腿部错位; arms_up: 举手; body_dy: 呼吸起伏。"""
    y = body_dy
    d.rectangle([24, 12 + y, 40, 24 + y], fill=HAIR)    # 头顶
    d.rectangle([22, 16 + y, 25, 32 + y], fill=HAIR)    # 左侧垂发
    d.rectangle([39, 16 + y, 42, 32 + y], fill=HAIR)    # 右侧垂发
    d.rectangle([26, 20 + y, 38, 30 + y], fill=SKIN)    # 脸
    d.point((29, 25 + y), fill=EYE)                     # 左眼
    d.point((35, 25 + y), fill=EYE)                     # 右眼
    d.rectangle([26, 31 + y, 38, 44 + y], fill=CLOTH)   # 身体
    if arms_up:                                         # 手臂（举起/放下）
        d.rectangle([22, 22 + y, 25, 32 + y], fill=SKIN)
        d.rectangle([39, 22 + y, 42, 32 + y], fill=SKIN)
    else:
        d.rectangle([23, 32 + y, 25, 42 + y], fill=SKIN)
        d.rectangle([39, 32 + y, 41, 42 + y], fill=SKIN)
    d.rectangle([27 + leg_offset, 45 + y, 30 + leg_offset, 52 + y], fill=CLOTH)
    d.rectangle([34 - leg_offset, 45 + y, 37 - leg_offset, 52 + y], fill=CLOTH)
    d.rectangle([26 + leg_offset, 52 + y, 31 + leg_offset, 54 + y], fill=EYE)
    d.rectangle([33 - leg_offset, 52 + y, 38 - leg_offset, 54 + y], fill=EYE)


def draw_poke_react(d: ImageDraw.ImageDraw, *, exclaim: bool = False) -> None:
    """被戳反应：举手惊讶；exclaim 帧头顶画感叹号（两帧交替 = 吓一跳）。"""
    draw_pet(d, arms_up=True)
    if exclaim:
        d.rectangle([31, 2, 33, 8], fill=EYE)    # 感叹号竖笔
        d.rectangle([31, 9, 33, 11], fill=EYE)   # 感叹号的点


def draw_eating(d: ImageDraw.ImageDraw, *, body_dy: int = 0) -> None:
    """喂食：身前捧碗，body_dy 做咀嚼点头起伏。碗画在小人之后（挡住下半身）。"""
    draw_pet(d, body_dy=body_dy)
    d.rectangle([24, 48, 40, 50], fill=BOWL)     # 碗口
    d.rectangle([27, 50, 37, 56], fill=BOWL)     # 碗身


def draw_sleeping(d: ImageDraw.ImageDraw, *, zzz_big: bool = False) -> None:
    """睡觉：侧躺姿势 + 大小 zzz 交替（大 z = 呼气帧，2fps 慢节奏）。"""
    d.rectangle([14, 40, 26, 52], fill=HAIR)     # 头（躺下偏左）
    d.rectangle([20, 43, 26, 49], fill=SKIN)     # 脸
    d.line((21, 46, 25, 46), fill=EYE)           # 闭眼横线
    d.rectangle([27, 41, 48, 52], fill=CLOTH)    # 躺着的身体
    d.rectangle([48, 44, 54, 50], fill=SKIN)     # 露出的脚
    if zzz_big:                                  # 大 z：两横一斜，加粗
        d.line((42, 20, 50, 20), fill=EYE, width=2)
        d.line((50, 20, 42, 28), fill=EYE, width=2)
        d.line((42, 28, 50, 28), fill=EYE, width=2)
    else:                                        # 小 z：细笔画
        d.line((46, 30, 51, 30), fill=EYE)
        d.line((51, 30, 46, 35), fill=EYE)
        d.line((46, 35, 51, 35), fill=EYE)


def draw_woken(d: ImageDraw.ImageDraw, *, zzz: bool = False) -> None:
    """睡眼惺忪：站立揉眼；zzz 帧头顶仍飘小 z（还没醒透），身体起伏交替。"""
    draw_pet(d, body_dy=0 if zzz else 1)
    if zzz:
        d.line((44, 6, 48, 6), fill=EYE)
        d.line((48, 6, 44, 10), fill=EYE)
        d.line((44, 10, 48, 10), fill=EYE)


def draw_climbing(d: ImageDraw.ImageDraw, *, phase: int = 0) -> None:
    """爬墙：侧面朝右贴墙，手臂/腿按 phase 0-3 交替（攀爬循环）。

    只画"右壁向上爬"：爬下 = 帧序倒放、左壁 = 水平镜像，
    由 SpriteManager.get_frame 渲染时处理（spec §2.4，一组素材三种用法）。
    """
    d.rectangle([28, 14, 40, 26], fill=HAIR)     # 头
    d.rectangle([30, 20, 38, 26], fill=SKIN)     # 脸
    d.point((36, 22), fill=EYE)                  # 眼睛（侧面只见一只）
    d.rectangle([28, 27, 40, 44], fill=CLOTH)    # 躯干
    if phase % 2 == 0:                           # 手臂一上一下交替抓墙
        d.rectangle([39, 8, 42, 20], fill=SKIN)
        d.rectangle([39, 30, 42, 38], fill=SKIN)
    else:
        d.rectangle([39, 16, 42, 28], fill=SKIN)
        d.rectangle([39, 34, 42, 42], fill=SKIN)
    off = 2 if phase < 2 else -2                 # 腿交替蹬墙
    d.rectangle([29, 44, 32, 52 + off], fill=CLOTH)
    d.rectangle([34, 44, 37, 52 - off], fill=CLOTH)
    d.rectangle([29, 52 + off, 32, 54 + off], fill=EYE)   # 鞋
    d.rectangle([34, 52 - off, 37, 54 - off], fill=EYE)


def draw_sitting_top(d: ImageDraw.ImageDraw, *, leg_swing: int = 0) -> None:
    """顶边坐姿：手撑身侧、双腿悬空晃荡（leg_swing 取 1/0/-1 循环）。"""
    d.rectangle([24, 12, 40, 24], fill=HAIR)     # 头顶
    d.rectangle([22, 16, 25, 32], fill=HAIR)     # 左侧垂发
    d.rectangle([39, 16, 42, 32], fill=HAIR)     # 右侧垂发
    d.rectangle([26, 20, 38, 30], fill=SKIN)     # 脸
    d.point((29, 25), fill=EYE)                  # 左眼
    d.point((35, 25), fill=EYE)                  # 右眼
    d.rectangle([26, 31, 38, 46], fill=CLOTH)    # 躯干（坐姿略长）
    d.rectangle([22, 38, 26, 46], fill=SKIN)     # 左臂撑在身侧
    d.rectangle([38, 38, 42, 46], fill=SKIN)     # 右臂撑在身侧
    ls = leg_swing
    d.rectangle([27 + ls, 46, 31 + ls, 56], fill=CLOTH)   # 悬空腿 1
    d.rectangle([33 - ls, 46, 37 - ls, 56], fill=CLOTH)   # 悬空腿 2
    d.rectangle([26 + ls, 55, 32 + ls, 58], fill=EYE)     # 鞋 1
    d.rectangle([32 - ls, 55, 38 - ls, 58], fill=EYE)     # 鞋 2


def make_sheet(frames_params: list[dict], out_name: str, draw=draw_pet) -> int:
    """按每帧参数画一张 sprite sheet（draw 指定绘制函数），返回帧数。"""
    sheet = Image.new("RGBA", (FRAME * len(frames_params), FRAME), (0, 0, 0, 0))
    for i, params in enumerate(frames_params):
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        draw(ImageDraw.Draw(frame), **params)
        sheet.paste(frame, (i * FRAME, 0), frame)
    sheet.save(ASSETS_DIR / out_name)
    return len(frames_params)


def main() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    # name → (每帧参数, fps, 绘制函数)；帧数/帧率严格按 spec §2.4
    specs = {
        "idle": ([{"body_dy": 0}, {"body_dy": 0},
                  {"body_dy": 1}, {"body_dy": 1}], 3, draw_pet),
        "walk_right": ([{"leg_offset": o} for o in (-2, -1, 0, 1, 2, 1)],
                       8, draw_pet),
        "dragged": ([{"arms_up": True, "leg_offset": 1},
                     {"arms_up": True, "leg_offset": -1}], 6, draw_pet),
        "falling": ([{"arms_up": True, "body_dy": 0},
                     {"arms_up": True, "body_dy": 1}], 6, draw_pet),
        "poke_react": ([{"exclaim": True}, {"exclaim": False}],
                       6, draw_poke_react),
        "eating": ([{"body_dy": 0}, {"body_dy": 1},
                    {"body_dy": 0}, {"body_dy": 1}], 6, draw_eating),
        "sleeping": ([{"zzz_big": False}, {"zzz_big": True}], 2, draw_sleeping),
        "woken": ([{"zzz": False}, {"zzz": True}], 3, draw_woken),
        "climbing": ([{"phase": p} for p in range(4)], 8, draw_climbing),
        "sitting_top": ([{"leg_swing": s} for s in (1, 0, -1, 0)],
                        3, draw_sitting_top),
    }
    manifest = {"frame_size": [FRAME, FRAME], "actions": {}}
    for name, (frames_params, fps, draw) in specs.items():
        file_name = f"{name}.png"
        count = make_sheet(frames_params, file_name, draw=draw)
        manifest["actions"][name] = {"file": file_name, "frames": count, "fps": fps}

    # walk_left 由 walk_right 逐帧镜像生成（v0.1 逻辑不变）
    right = Image.open(ASSETS_DIR / "walk_right.png")
    n_frames = right.width // FRAME
    left = Image.new("RGBA", right.size, (0, 0, 0, 0))
    for i in range(n_frames):
        box = (i * FRAME, 0, (i + 1) * FRAME, FRAME)
        left.paste(ImageOps.mirror(right.crop(box)), (i * FRAME, 0))
    left.save(ASSETS_DIR / "walk_left.png")
    manifest["actions"]["walk_left"] = {
        "file": "walk_left.png", "frames": n_frames,
        "fps": manifest["actions"]["walk_right"]["fps"]}

    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成素材到 {ASSETS_DIR}:")
    for name, a in sorted(manifest["actions"].items()):
        print(f"  {name}: {a['file']} {a['frames']} 帧 @ {a['fps']} fps")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 生成素材并冒烟检查**

Run: `.venv\Scripts\python tools\gen_placeholder_assets.py`
Expected: 打印 11 个动作（v0.1 的 5 个 + 新 6 个），帧数/帧率与 spec §2.4 一致

Run: `.venv\Scripts\python tools\check_sprites.py`
Expected: 全部动作加载通过（check_sprites 为 manifest 驱动，无需改动；headless QApplication，允许运行）

- [ ] **Step 3: 全量回归**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS（test_sprite_logic 用合成 manifest，不受真实素材影响）

- [ ] **Step 4: Commit**

```powershell
git add tools/gen_placeholder_assets.py assets
git commit -m @'
feat: 6 组新占位素材（戳/吃/睡/醒/爬/顶坐）

climbing 只画右壁向上爬：爬下倒放、左壁镜像由渲染层处理。

Co-Authored-By: Claude Code <noreply@anthropic.com>
'@
```

---

### Task 5: GUI 集成（戳/拖拽判定、右键菜单、tooltip、攀爬渲染）

**Files:**
- Modify: `xiaoliang/sprite.py`（get_frame 增加 reverse/mirror）
- Modify: `xiaoliang/pet_window.py`（全文件替换为下方内容）
- Modify: `xiaoliang/tray.py`（增加暂停同步回调）

**Interfaces:**
- Consumes: Task 3 的 `machine.status / poke() / feed() / set_paused / add_pause_listener / climb_wall / climb_direction / State 新成员`；Task 4 的 6 个新动作名
- Produces（Task 6 main 依赖）: `PetWindow(machine, sprites, origin=None, on_quit=None)`——`on_quit` 为无参可调用对象（右键菜单"退出"时调用）；`SpriteManager.get_frame(action, elapsed_ms, *, reverse=False, mirror=False)`

GUI 层不做自动化测试（v0.1 裁定沿用）；验证 = pytest 回归 + import 冒烟 + check_sprites。

- [ ] **Step 1: 修改 `xiaoliang/sprite.py`**

import 行改为：

```python
from PySide6.QtGui import QImage, QPixmap, QTransform
```

`get_frame` 方法整体替换为：

```python
    def get_frame(self, action: str, elapsed_ms: int, *,
                  reverse: bool = False, mirror: bool = False) -> QPixmap:
        """返回动作在 elapsed_ms 时刻应显示的帧。未知动作抛 AssetError。

        reverse: 帧序倒放（向下爬墙复用向上爬素材，v0.2 spec §2.4）；
        mirror: 水平镜像（左壁爬墙复用右壁素材）。
        """
        if action not in self._frames:
            raise AssetError(f"未知动作: {action!r}（可用: {self.actions()}）")
        frames = self._frames[action]
        idx = frame_index(elapsed_ms, self._fps[action], len(frames))
        if reverse:
            idx = len(frames) - 1 - idx
        pixmap = frames[idx]
        if mirror:
            # 镜像生成新 QPixmap，不改动缓存的原始帧
            pixmap = pixmap.transformed(QTransform().scale(-1.0, 1.0))
        return pixmap
```

- [ ] **Step 2: 全文件替换 `xiaoliang/pet_window.py`**

```python
"""桌宠窗口：透明置顶无边框，渲染当前帧并把鼠标事件转发给状态机。

状态机坐标以工作区左上角为原点（规格 3.3）；
全局屏幕坐标 = origin（availableGeometry().topLeft()）+ 状态机坐标。

v0.2 新增（spec §2.3）：
- 戳 vs 拖拽判定：按压 <250ms 且位移 <5px = 戳（machine.poke()），
  否则走 v0.1 拖拽流程（machine.drag_end() 下落）
- 右键菜单：喂食（吃撑置灰）/ 状态展示 / 暂停·恢复 / 退出
- 悬停 tooltip：每秒刷新"心情 😊N · 饱腹 🍚N · 状态中文"
- 攀爬渲染：爬下 = 帧序倒放，左壁 = 水平镜像（get_frame kwargs）
"""
import math
import time

from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QWidget

from .sprite import SpriteManager
from .state_machine import PetStateMachine, State

FPS = 30

# 戳判定阈值（spec §2.3）：按压时长与位移都必须小于该值才算"戳"
POKE_MAX_MS = 250
POKE_MAX_PX = 5.0

# 状态 → 动作名（WALKING 按方向细分、CLIMBING 的倒放/镜像单独处理）
STATE_ACTION = {
    State.IDLE: "idle",
    State.DRAGGED: "dragged",
    State.FALLING: "falling",
    State.POKE_REACT: "poke_react",
    State.EATING: "eating",
    State.SLEEPING: "sleeping",
    State.WOKEN: "woken",
    State.CLIMBING: "climbing",
    State.SITTING_TOP: "sitting_top",
}

# 状态 → tooltip 中文名（spec §2.3 映射表，逐字一致）
STATE_ZH = {
    State.IDLE: "发呆",
    State.WALKING: "溜达",
    State.DRAGGED: "被拎着",
    State.FALLING: "下落中",
    State.POKE_REACT: "被戳了",
    State.EATING: "吃东西",
    State.SLEEPING: "睡觉",
    State.WOKEN: "睡眼惺忪",
    State.CLIMBING: "爬墙",
    State.SITTING_TOP: "顶上坐着",
}


class PetWindow(QWidget):
    def __init__(self, machine: PetStateMachine, sprites: SpriteManager,
                 origin: QPoint | None = None, on_quit=None):
        super().__init__(None,
                         Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.machine = machine
        self.sprites = sprites
        # 工作区左上角的全局屏幕坐标（任务栏在顶部/左侧时非零）
        self._origin = origin if origin is not None else QPoint(0, 0)
        # 右键菜单"退出"回调（main.py 注入 app.quit）
        self._on_quit = on_quit
        self.setFixedSize(*sprites.frame_size())
        self.setWindowTitle("小凉")
        self._pixmap: QPixmap = sprites.get_frame("idle", 0)
        self._anim_ms = 0
        self._last_action = "idle"
        self._drag_offset: QPoint | None = None
        # ── 戳/拖拽判定状态：按压时刻、按压位置、是否已发生有效位移 ──
        self._press_ts = 0.0
        self._press_pos: QPoint | None = None
        self._drag_moved = False
        # tooltip 刷新计时（毫秒累计，每满 1000 刷一次）
        self._tooltip_ms = 0
        self._refresh_tooltip()
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // FPS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()

    def current_action(self) -> str:
        """当前应播放的动作名。暂停时按规格 3.4 播放 idle。"""
        if self.machine.paused:
            return "idle"
        if self.machine.state is State.WALKING:
            return "walk_right" if self.machine.direction > 0 else "walk_left"
        return STATE_ACTION[self.machine.state]

    def _to_global(self, x: float, y: float) -> QPoint:
        """状态机坐标（工作区原点）→ 全局屏幕坐标。"""
        return QPoint(self._origin.x() + int(x), self._origin.y() + int(y))

    def _refresh_tooltip(self) -> None:
        """悬停 tooltip：数值 + 状态中文名（格式严格按 spec §2.3）。"""
        s = self.machine.status
        self.setToolTip(f"心情 😊{s.mood:.0f} · 饱腹 🍚{s.fullness:.0f} · "
                        f"{STATE_ZH.get(self.machine.state, '')}")

    def _on_tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        self.machine.tick(dt)
        action = self.current_action()
        if action != self._last_action:
            self._anim_ms = 0          # 换动作时动画从头播
            self._last_action = action
        else:
            self._anim_ms += int(dt * 1000)
        # 攀爬渲染：爬下倒放帧序、左壁水平镜像（一组 climbing 素材三种用法）
        climbing = self.machine.state is State.CLIMBING
        self._pixmap = self.sprites.get_frame(
            action, self._anim_ms,
            reverse=climbing and self.machine.climb_direction == "down",
            mirror=climbing and self.machine.climb_wall < 0)
        self.move(self._to_global(self.machine.x, self.machine.y))
        # tooltip 每秒刷新：数值随时间衰减，刷太快没有意义
        self._tooltip_ms += int(dt * 1000)
        if self._tooltip_ms >= 1000:
            self._tooltip_ms = 0
            self._refresh_tooltip()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录按压时刻/位置供戳判定；照旧先 drag_start()——真拖拽时
            # 状态机立即进入 DRAGGED 才能跟手（戳的情况松手时回退）
            self._press_ts = time.monotonic()
            self._press_pos = event.globalPosition().toPoint()
            self._drag_moved = False
            self.machine.drag_start()
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is None:
            return
        pos = event.globalPosition().toPoint()
        # 位移超过阈值才算有效拖拽：戳的时候手抖几像素不会误判
        if not self._drag_moved and self._press_pos is not None:
            delta = pos - self._press_pos
            if math.hypot(delta.x(), delta.y()) > POKE_MAX_PX:
                self._drag_moved = True
        if self._drag_moved:
            target = pos - self._drag_offset
            # machine 使用工作区坐标：全局屏幕坐标先减去工作区原点
            self.machine.drag_move(target.x() - self._origin.x(),
                                   target.y() - self._origin.y())
            # 拖拽时立即跟手，不等下一个 tick（用钳制后的 machine 坐标，
            # 保证窗口不拖出工作区）
            self.move(self._to_global(self.machine.x, self.machine.y))
        event.accept()

    def mouseReleaseEvent(self, event):
        # v0.1 已知边缘情况（v0.2 仍未定义，见 README 已知问题）：暂停中
        # 松手时 tick 为 no-op，角色停在半空 FALLING，恢复暂停后落地。
        if (event.button() == Qt.MouseButton.LeftButton
                and self._drag_offset is not None):
            self._drag_offset = None
            pressed_ms = (time.monotonic() - self._press_ts) * 1000.0
            if not self._drag_moved and pressed_ms < POKE_MAX_MS:
                # 短按且无有效位移 = 戳：不调 drag_end()（不触发下落），
                # machine.poke() 内部会回退到拖拽前状态并播放反应
                self.machine.poke()
            else:
                self.machine.drag_end()
            event.accept()

    def contextMenuEvent(self, event):
        """右键菜单（spec §2.3）：每次打开都重建，实时反映数值与暂停状态。"""
        status = self.machine.status
        menu = QMenu(self)
        # 喂食：吃撑（fullness > 90）时置灰并改文案
        feed_action = menu.addAction(
            "喂食" if status.can_feed else "喂食（吃撑了）")
        feed_action.setEnabled(status.can_feed)
        feed_action.triggered.connect(lambda: self.machine.feed())
        # 状态展示项：不可点击，只显示当前数值
        status_action = menu.addAction(
            f"心情 {status.mood:.0f} · 饱腹 {status.fullness:.0f}")
        status_action.setEnabled(False)
        menu.addSeparator()
        pause_action = menu.addAction(
            "恢复" if self.machine.paused else "暂停")
        # set_paused 会经状态机回调同步托盘勾选/文字（见 tray.sync_pause）
        pause_action.triggered.connect(
            lambda: self.machine.set_paused(not self.machine.paused))
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit)
        menu.exec(event.globalPos())

    def _quit(self) -> None:
        """退出入口：状态落盘由 main.py 的 aboutToQuit 兜底，这里只退。"""
        if self._on_quit is not None:
            self._on_quit()
```

- [ ] **Step 3: 修改 `xiaoliang/tray.py`**

`__init__` 末尾（`self.activated.connect(self._on_activated)` 之后）追加：

```python
        # 暂停双向同步（spec §3）：右键菜单调 machine.set_paused 时，状态机
        # 经此回调通知托盘刷新勾选与文字；反向（托盘→状态机）原有逻辑不变
        machine.add_pause_listener(self.sync_pause)
```

类末尾新增方法：

```python
    def sync_pause(self, paused: bool) -> None:
        """状态机暂停变更回调：只刷新 UI，不回写状态机（防递归）。"""
        # blockSignals 避免 setChecked 触发 toggled → 再次 set_paused 死循环
        self._pause_action.blockSignals(True)
        self._pause_action.setChecked(paused)
        self._pause_action.setText("恢复" if paused else "暂停")
        self._pause_action.blockSignals(False)
```

- [ ] **Step 4: 验证（GUI 层不做自动化测试，import 冒烟 + 回归）**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS

Run: `.venv\Scripts\python -c "import xiaoliang.pet_window, xiaoliang.tray, xiaoliang.sprite; print('OK')"`
Expected: `OK`（仅验证可导入，不实例化窗口、不弹窗）

Run: `.venv\Scripts\python tools\check_sprites.py`
Expected: 全部动作加载通过

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/sprite.py xiaoliang/pet_window.py xiaoliang/tray.py
git commit -m @'
feat: GUI 集成——戳/拖拽判定、右键菜单、tooltip、攀爬倒放镜像渲染

短按(<250ms)且位移(<5px)=戳，否则走拖拽；右键菜单每次打开重建以
反映实时数值；托盘与菜单暂停状态经状态机回调双向同步。

Co-Authored-By: Claude Code <noreply@anthropic.com>
'@
```

---

### Task 6: main.py 装配（status 持久化 + 睡眠配置 + 退出保存）

**Files:**
- Modify: `main.py`
- Modify: `.gitignore`（追加 `status.json`）

**Interfaces:**
- Consumes: Task 1 `PetStatus.load(path)` / `status.save(path)`；Task 2 `cfg["sleep_start"] / cfg["sleep_end"]`；Task 3 状态机新 kwargs（`status/sleep_start/sleep_end/on_status_change`）；Task 5 `PetWindow(..., on_quit=...)`
- Produces: 无（最终装配层）

- [ ] **Step 1: 修改 `main.py`**

import 区追加（融入既有 import，保持分组风格）：

```python
from PySide6.QtCore import QTimer

from xiaoliang.status import PetStatus
```

模块级常量（`from xiaoliang.tray import PetTray` 之后）：

```python
# 数值自动保存间隔（spec §2.1：每 60 秒 + 喂食/戳/退出时即时保存）
STATUS_SAVE_INTERVAL_MS = 60_000
```

`main()` 中 `cfg = load_config(cfg_path)` 所在段落之后、首次运行生成默认配置的 try 块之前插入：

```python
    # 数值系统：status.json 与 config.json 同目录；文件损坏/缺失时
    # PetStatus.load 内部回退默认 80/80（spec §2.1，离线不补算衰减）
    status_path = cfg_path.parent / "status.json"
    status = PetStatus.load(status_path)

    def save_status() -> None:
        """统一落盘入口：定时保存/数值变化回调/退出保存都走这里。

        save() 内部已捕获 OSError 只记日志，这里无需再包。
        """
        status.save(status_path)
```

`machine = PetStateMachine(...)` 构造整体替换为：

```python
    machine = PetStateMachine(
        Bounds(area.width(), area.height()), fw, fh,
        walk_speed=float(cfg["walk_speed"]),
        start_x=(area.width() - fw) / 2,
        status=status,
        sleep_start=cfg["sleep_start"],
        sleep_end=cfg["sleep_end"],
        on_status_change=save_status)   # 戳/喂食数值变化后即时落盘
```

`window = PetWindow(machine, sprites, origin=origin)` 替换为：

```python
    window = PetWindow(machine, sprites, origin=origin, on_quit=app.quit)
```

`tray.show()` 之后、`return app.exec()` 之前插入：

```python
    # 定时保存数值（每 60 秒）+ 退出时兜底保存
    save_timer = QTimer()
    save_timer.setInterval(STATUS_SAVE_INTERVAL_MS)
    save_timer.timeout.connect(save_status)
    save_timer.start()
    app.aboutToQuit.connect(save_status)
```

- [ ] **Step 2: `.gitignore` 追加一行**

在 `config.json` 行之后加：

```
status.json
```

（两者同为运行时生成文件，均不入库。）

- [ ] **Step 3: 验证**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS

Run: `.venv\Scripts\python -c "import main; print('OK')"`
Expected: `OK`（main() 有 `if __name__` 守卫，import 不启动 GUI）

- [ ] **Step 4: Commit**

```powershell
git add main.py .gitignore
git commit -m @'
feat: main.py 装配数值持久化与睡眠配置

status.json 每 60 秒 + 戳/喂食即时 + 退出兜底保存；sleep_start/
sleep_end 从 config 注入状态机；status.json 加入 gitignore。

Co-Authored-By: Claude Code <noreply@anthropic.com>
'@
```

---

### Task 7: 文档更新（README + assets/README）

**Files:**
- Modify: `README.md`
- Modify: `assets/README.md`

**Interfaces:**
- Consumes: 前 6 个任务的最终行为（文案必须与实际实现一致）
- Produces: 无

- [ ] **Step 1: `README.md` 按下述 6 处修改**

1）开头简介段（"一只 Windows 桌面像素宠物：……随时暂停/退出。"两行）替换为：

```markdown
一只 Windows 桌面像素宠物：蓝发小人在屏幕底部溜达、发呆，戳她会有反应，
右键可以喂食，到点自动睡觉，偶尔爬上屏幕边缘到顶边坐着晃腿。可以用鼠标
把她拎起来（会挣扎），松手会掉回地面。常驻系统托盘，随时暂停/退出。
```

2）`## 功能（v0.1）` 一节（标题 + 4 条 bullet + 配置表格，到 `## 运行` 之前）替换为：

````markdown
## 功能

**v0.2（玩具型）**

- 👉 戳：左键短按 = 戳，原地惊讶反应（心情 +3，10 秒冷却）
- 🍚 喂食：右键菜单喂食（饱腹 +25 / 心情 +5，吃撑时菜单置灰）
- 💗 数值：心情/饱腹度 0–100 随时间衰减；饥饿（<20）走路变慢、
  心情差（<20）不爱攀爬；存 `status.json`（config 同目录，不入库），
  离线不衰减
- 😴 定时睡觉：默认 23:00–07:00（可配、支持跨午夜）；睡觉中戳她会
  惺忪几秒再睡
- 🧗 攀爬：随机走向最近屏幕边缘 → 爬上去 → 顶边坐着晃腿 → 爬下或跳下
- 📋 状态查看：右键菜单显示数值；悬停 tooltip 每秒刷新

**v0.1（观赏型）**

- 🚶 自主行为：待机 ↔ 随机溜达 ↔ 屏幕边缘折返
- 🖱️ 鼠标拖拽：抓住、挣扎、松手下落、落地回待机，下落中可再次抓住
- 🎛️ 系统托盘：暂停/恢复（双击图标同效）、退出
- ⚙️ 配置：`config.json`（exe/入口脚本同目录，首次运行自动生成默认值）

| 键 | 默认 | 说明 |
|----|------|------|
| `scale` | 2 | 像素放大倍数（整数） |
| `walk_speed` | 60.0 | 行走速度（逻辑像素/秒） |
| `paused` | false | 启动时是否暂停 |
| `sleep_start` | `"23:00"` | 入睡时刻（HH:MM；与 `sleep_end` 相等视为非法回退默认） |
| `sleep_end` | `"07:00"` | 睡醒时刻（HH:MM；支持跨午夜时段） |

数值存档 `status.json` 在同目录自动生成（gitignore；删掉即重置为 80/80）。
````

3）`## 架构` 一节正文替换为：

```markdown
状态机与数值系统（纯逻辑，pytest 覆盖）与 GUI 分离，详见
[v0.1 设计文档](docs/superpowers/specs/2026-09-21-xiaoliang-desktop-pet-design.md)
与 [v0.2 设计文档](docs/superpowers/specs/2026-09-21-xiaoliang-v0.2-toy-design.md)。
```

4）手动验收清单：在 `### 托盘与配置` 的第 15 项之后、`### exe 打包` 之前插入新小节，并把 `### exe 打包` 的原第 16 项改为第 25 项：

```markdown
### v0.2 玩具

16. 左键短按（<0.25 秒且几乎不移动）= 戳：原地播惊讶反应，播完回原状态；拖拽照常（两者互不干扰）
17. 右键菜单四项：喂食 / 状态（不可点击，显示"心情 N · 饱腹 N"）/ 暂停·恢复 / 退出
18. 连续喂食到饱腹 >90：菜单项置灰且文案变"喂食（吃撑了）"
19. 悬停 tooltip 每秒刷新：`心情 😊N · 饱腹 🍚N · 状态中文`
20. 把 `sleep_start`/`sleep_end` 改成覆盖当前时刻后重启：角色原地入睡不再走动；戳她 → 惺忪几秒 → 回笼觉；时段结束后自然醒回发呆
21. 等攀爬触发（每次出门 15% 概率）：走向最近边缘 → 爬上去 → 顶边坐着晃腿 → 爬下或跳下落地
22. 饱腹低于 20（等衰减或手改 `status.json` 后重启）：走路速度明显变慢
23. 右键菜单"暂停/恢复"与托盘勾选、文字双向同步（任一侧操作，另一侧即时更新）
24. 重启程序：心情/饱腹恢复退出前数值（离线不衰减）

### exe 打包

25. `dist\xiaoliang.exe` 启动后行为与源码运行一致；托盘"退出"能完全结束进程；体积在预期 40~80MB 范围
```

5）`## 已知问题（v0.1）` 整节（标题 + 1 条 bullet）替换为：

```markdown
## 已知问题

- 暂停状态下把她拖到半空松手：角色悬停在半空（渲染待机动画），恢复暂停后
  才落地——规格未定义的边缘情况，v0.3 处理。
- 暂停中戳她仍会加心情并播反应（暂停只冻结 tick，不冻结事件）——v0.3 处理。
- 爬墙/顶边时被戳播放的是地面姿势的 POKE_REACT 素材（反应素材未区分
  朝向）——正式素材阶段可为 climbing 单独出被戳帧（见 assets/README 待办）。
```

6）路线图中 v0.2 一行勾选：

```markdown
- [x] v0.2 玩具型：戳她会有反应、喂食、心情/饱腹度、晚上自动睡觉
```

- [ ] **Step 2: `assets/README.md` 按下述 3 处修改**

1）"格式约定"中"动作名固定"与"朝向约定"两行替换为：

```markdown
- 动作名固定：`idle` / `walk_left` / `walk_right` / `dragged` / `falling` /
  `poke_react`(2帧@6fps) / `eating`(4帧@6fps) / `sleeping`(2帧@2fps) /
  `woken`(2帧@3fps) / `climbing`(4帧@8fps) / `sitting_top`(4帧@3fps)
- 朝向约定：角色默认画成朝右；`walk_left` 是 `walk_right` 的水平镜像；
  `climbing` 只画"右壁向上爬"，向下爬 = 帧序倒放、左壁 = 水平镜像
  （均由渲染层 `SpriteManager.get_frame` 完成，素材无需额外出图）
```

2）AI 生成流程第 2 步替换为：

```markdown
2. 以定稿图为参考，逐动作生成帧序列（站立呼吸 4 帧 / 走路 6 帧 /
   被拎起 2 帧 / 下落 2 帧 / 被戳反应 2 帧 / 喂食 4 帧 / 睡觉 2 帧 /
   睡眼惺忪 2 帧 / 攀爬 4 帧（侧面朝右向上）/ 顶边坐姿 4 帧），
   每张拼成横向 sprite sheet
```

3）文件末尾追加：

```markdown

## 待办

- [ ] 正式素材阶段为 `climbing` 单独出"被戳"帧（当前在墙上被戳播放的
      是地面姿势的 `poke_react`，见主 README"已知问题"）
```

- [ ] **Step 3: 验证 + Commit**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS（文档改动不应影响测试）

```powershell
git add README.md assets/README.md
git commit -m @'
docs: README v0.2 功能/验收清单/已知问题更新，素材文档补 6 组新动作

Co-Authored-By: Claude Code <noreply@anthropic.com>
'@
```

---

### Task 8: 打包验证（不产生 commit）

**Files:**
- Output: `dist\xiaoliang.exe`（gitignore，不入库）

**Interfaces:**
- Consumes: 全部前序任务的最终代码
- Produces: 可交付 exe；GUI 手动验收留给用户

- [ ] **Step 1: 全量测试**

Run: `.venv\Scripts\python -m pytest -v`
Expected: 全部 PASS（预计 80+ 用例：v0.1 的 31 个 + v0.2 新增）

- [ ] **Step 2: 打包**

Run: `.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name xiaoliang --add-data "assets;assets" main.py`
Expected: 打包成功无 ERROR（WARNING 可接受）

- [ ] **Step 3: 产物检查（禁止运行 exe / 禁止启动任何 GUI）**

Run: `.venv\Scripts\python -c "from pathlib import Path; p = Path('dist/xiaoliang.exe'); print(f'{p} 存在, {p.stat().st_size / 1048576:.1f} MB')"`
Expected: 文件存在，体积约 40 MB 量级

Run: `.venv\Scripts\python tools\check_sprites.py`
Expected: 全部 11 个动作加载通过

Run: `git status --porcelain`
Expected: 无未提交改动（build/dist/status.json 均已被 gitignore）

---

## 验收与收尾（控制者执行，非任务）

1. 最终整体代码评审（whole-branch review，最强模型）
2. `superpowers:finishing-a-development-branch`：全量测试 → 给用户三选项（本地合并 / 推送开 PR / 保留分支）——**推送永远是用户本人的操作**
3. 用户手动 GUI 验收：跑 `README.md` 的 v0.2 手动验收清单（16–25 项）+ 启动 `dist\xiaoliang.exe` 冒烟
4. 发布 v0.2.0（GitHub Release，用户操作）
