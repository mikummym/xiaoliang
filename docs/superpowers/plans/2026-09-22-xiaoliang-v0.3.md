# 小凉 v0.3 实施计划：声音互动、屏幕穿越、健康提醒与多屏修复

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 v0.3 全部范围：4 个遗留修复（暂停冻结事件、攀爬中喂食、多屏贴边溢出、暂停半空松手）+ 5 个新功能（戳音效、屏幕穿越、久坐提醒、整点报时、开机自启），2026-09-25 前发布。

**Architecture:** 状态机（纯逻辑）扩展穿越意图与 REMINDING 状态；新增四个内聚模块：`sound.py`（声音引擎）、`reminder.py`（提醒服务）、`screen_info.py`（屏幕几何）、`autostart.py`（注册表自启）；GUI 层（pet_window/tray/main）只做接线与渲染。延续"纯逻辑可单测、Qt 只在薄层"的既有架构。

**Tech Stack:** Python 3 + PySide6（QtMultimedia 音效 / QtTextToSpeech TTS，均已随现有 PySide6 安装）+ 标准库（ctypes/winreg/wave）。**零新增第三方依赖**。

**Spec:** `docs/superpowers/specs/2026-09-22-xiaoliang-v0.3-design.md`（执行时必读，plan 与 spec 冲突时以 spec 为准并停下询问）

## Global Constraints

- 零新增第三方运行时依赖：只用 PySide6 与标准库（PIL 仅限 tools/ 素材脚本，现状保持）
- 所有代码加必要中文注释：模块/函数 docstring + 关键逻辑行内注释，解释"为什么"（用户常设规范）
- 现有 103 个 pytest 必须保持全绿，不得修改既有测试断言来迁就新代码（除非 spec 明确改变旧行为）
- 纯逻辑模块（state_machine/reminder.ReminderLogic/screen_info.neighbor_edges/sound.should_play/config）不得 import Qt 对象；Qt 只出现在薄驱动层
- 每条 commit message 以 `Co-Authored-By: Claude Code <noreply@anthropic.com>` 结尾（用 `git commit -m "标题" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"` 形式）
- 测试命令统一用项目 venv：`.venv\Scripts\python -m pytest ...`（在 `D:\projects\xiaoliang` 下执行）
- 分支：从 master 新建 `feat/v0.3`，全部任务在该分支提交（完工后由用户决定合并方式）
- GUI 程序验证留给用户手动执行（验收清单在 spec §8），代理不弹窗、不启动 GUI 进程做验证

---

### Task 1: config.py 迁移——v0.3 新键（wrap_chance / sound / remind）

**Files:**
- Modify: `xiaoliang/config.py`
- Test: `tests/test_config.py`（追加）

**Interfaces:**
- Consumes: 无（地基任务）
- Produces: `DEFAULT_CONFIG` 新增键 `"wrap_chance": 0.08`、`"sound": {"muted": False, "poke_sfx": True, "sit_reminder": True, "hourly_chime": True}`、`"remind": {"sit_minutes": 45, "idle_threshold_minutes": 5}`；`needs_migration(path) -> bool` 升级为嵌套检查。后续任务直接 `cfg["wrap_chance"]`、`cfg["sound"]`、`cfg["remind"]` 取用。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_config.py`，沿用该文件既有的临时目录 fixture 风格；如现有测试用 `tmp_path` 写 json 文件再 load，照抄该模式）

```python
def test_v02_config_migrates_to_v03(tmp_path):
    """v0.2 的 5 键配置：load 后补全 v0.3 新键，旧值保留。"""
    p = tmp_path / "config.json"
    p.write_text('{"scale": 2, "walk_speed": 60.0, "paused": false,'
                 ' "sleep_start": "23:00", "sleep_end": "07:00"}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["wrap_chance"] == 0.08
    assert cfg["sound"] == {"muted": False, "poke_sfx": True,
                            "sit_reminder": True, "hourly_chime": True}
    assert cfg["remind"] == {"sit_minutes": 45, "idle_threshold_minutes": 5}
    assert cfg["sleep_start"] == "23:00"          # 旧值保留
    assert needs_migration(p) is True             # 缺新键 → 需要迁移回写


def test_partial_sound_section_filled(tmp_path):
    """sound 段存在但缺子键：缺的子键补默认，已有子键保留。"""
    p = tmp_path / "config.json"
    p.write_text('{"sound": {"muted": true}}', encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sound"]["muted"] is True
    assert cfg["sound"]["poke_sfx"] is True
    assert needs_migration(p) is True             # 嵌套缺键也算需迁移


def test_bad_wrap_chance_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"wrap_chance": 5}', encoding="utf-8")
    assert load_config(p)["wrap_chance"] == 0.08


def test_bad_sound_section_falls_back_whole(tmp_path):
    """sound 段不是对象 → 整段回退默认（与其他键的回退语义一致）。"""
    p = tmp_path / "config.json"
    p.write_text('{"sound": "loud", "remind": {"sit_minutes": -3}}',
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["sound"] == DEFAULT_CONFIG["sound"]
    assert cfg["remind"] == DEFAULT_CONFIG["remind"]


def test_v03_config_needs_no_migration(tmp_path):
    p = tmp_path / "config.json"
    save_config(load_config(p), p)                # 生成完整默认配置
    assert needs_migration(p) is False
```

（测试文件头部若无 `DEFAULT_CONFIG` / `save_config` / `needs_migration` 导入则补上。）

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: 新增 5 个测试 FAIL（KeyError: 'wrap_chance' 等），既有测试仍 PASS

- [ ] **Step 3: 实现**（`xiaoliang/config.py`）

```python
DEFAULT_CONFIG = {
    "scale": 2,
    "walk_speed": 60.0,
    "paused": False,
    "sleep_start": "23:00",   # 睡眠时段起点（含），HH:MM 24 小时制
    "sleep_end": "07:00",     # 睡眠时段终点（不含）；start>end 表示跨午夜
    "wrap_chance": 0.08,      # v0.3：IDLE 出门时触发屏幕穿越的概率
    # v0.3：声音开关。muted=总开关（托盘菜单同步），其余为分类开关（手改）
    "sound": {
        "muted": False,
        "poke_sfx": True,
        "sit_reminder": True,
        "hourly_chime": True,
    },
    # v0.3：提醒服务参数（单位分钟，正数）
    "remind": {
        "sit_minutes": 45,
        "idle_threshold_minutes": 5,
    },
}


def _coerce_wrap_chance(v):
    """wrap_chance 必须是 [0,1] 的数字（bool 不算），统一收敛为 float。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"wrap_chance 必须是数字，收到 {type(v).__name__}")
    v = float(v)
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"wrap_chance 必须在 [0,1]，收到 {v}")
    return v


def _make_sub_coercer(defaults: dict):
    """工厂：生成嵌套配置段（sound/remind）的校验器。

    语义：段必须是 JSON 对象；缺的子键补默认值；任何子键类型/取值非法
    → 抛 ValueError，由 load_config 的按键回退逻辑把**整段**回退默认
    （段内一半合法一半非法的"半份配置"比整段默认更容易让人困惑）。
    """
    def coerce(v):
        if not isinstance(v, dict):
            raise ValueError(f"必须是 JSON 对象，收到 {type(v).__name__}")
        out = dict(defaults)
        for key, dval in defaults.items():
            if key not in v:
                continue                      # 缺子键 → 用默认值
            val = v[key]
            if isinstance(dval, bool):
                if not isinstance(val, bool):
                    raise ValueError(f"子键 {key} 必须是布尔值，收到 {val!r}")
            else:                             # 数值子键：正数，收敛 float
                if (isinstance(val, bool)
                        or not isinstance(val, (int, float)) or val <= 0):
                    raise ValueError(f"子键 {key} 必须是正数，收到 {val!r}")
                val = float(val)
            out[key] = val
        return out
    return coerce


_COERCE = {
    "scale": _coerce_scale,
    "walk_speed": _coerce_walk_speed,
    "paused": _coerce_paused,
    "sleep_start": _coerce_hhmm,
    "sleep_end": _coerce_hhmm,
    "wrap_chance": _coerce_wrap_chance,
    "sound": _make_sub_coercer(DEFAULT_CONFIG["sound"]),
    "remind": _make_sub_coercer(DEFAULT_CONFIG["remind"]),
}
```

`needs_migration` 的判定改为递归缺键检查（替换最后一行 `return not set(...)`）：

```python
def _has_missing_keys(defaults: dict, data: dict) -> bool:
    """递归检查 data 是否缺 defaults 的任何键（含嵌套段的子键）。"""
    for key, dval in defaults.items():
        if key not in data:
            return True
        if isinstance(dval, dict) and isinstance(data[key], dict):
            if _has_missing_keys(dval, data[key]):
                return True
    return False


def needs_migration(path: Path) -> bool:
    """检测配置文件是否为缺少新键的旧版本（v0.1 缺 sleep_*，v0.2 缺 v0.3 键）。

    只有"文件存在、是合法 JSON 对象、且缺 DEFAULT_CONFIG 的键（含嵌套
    子键）"才算需要迁移，main.py 据此把补全后的配置回写。
    文件不存在或损坏/非对象（load_config 已回退默认值）时返回 False——
    这两种情况不应再动用户的文件。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    return _has_missing_keys(DEFAULT_CONFIG, data)
```

（`load_config` 的按键遍历 `for key in DEFAULT_CONFIG` 无需改动——新键自动走 `_COERCE`；`cfg = dict(DEFAULT_CONFIG)` 是浅拷贝，嵌套 dict 会被共享——把该行改为 `cfg = json.loads(json.dumps(DEFAULT_CONFIG))` 做深拷贝，防止运行时改 `cfg["sound"]["muted"]` 污染模块级默认值。这是一个真实 bug 风险，必须改，加行内注释说明。）

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_config.py -v`
Expected: 全部 PASS（含既有测试）

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/config.py tests/test_config.py
git commit -m "feat(config): v0.3 配置迁移——wrap_chance/sound/remind 键与嵌套校验" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: 状态机遗留修复①②④——暂停冻结事件、攀爬中喂食、暂停半空松手

**Files:**
- Modify: `xiaoliang/state_machine.py`（`poke` / `feed` / `drag_end` / EATING tick 分支 / `__init__`）
- Test: `tests/test_state_machine.py`（追加，复用文件内既有 `FakeRandom` / `FakeClock` / `make_machine`）

**Interfaces:**
- Consumes: 现有 `PetStateMachine` 全部 API
- Produces: `poke() -> bool`（**签名变更**：返回是否受理，暂停时 False——GUI Task 10 据此决定是否播音效）；`feed()` 接受状态新增 `CLIMBING`/`SITTING_TOP`；`drag_end()` 暂停时直接落地置 IDLE。新私有字段 `self._eat_in_air: bool`。

- [ ] **Step 1: 写失败测试**（追加到 `tests/test_state_machine.py`）

```python
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
```

**同时删除既有测试 `test_feed_refused_while_climbing`**（`tests/test_state_machine.py` 约 339–343 行，断言攀爬中 `feed() is False`）——spec §1.2 明确推翻该旧行为（这正是 Global Constraints 中"除非 spec 明确改变旧行为"的例外），新行为由上面的 `test_feed_accepted_while_climbing_then_falls` 覆盖。删除时在 commit message 中注明。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_state_machine.py -v`
Expected: 新增测试 FAIL（`poke() is False` 失败因现返回 None；攀爬 feed 返回 False；暂停松手后 state 是 FALLING 等），既有测试（除已删除的 `test_feed_refused_while_climbing`）PASS

- [ ] **Step 3: 实现**（`xiaoliang/state_machine.py`）

`__init__` 末尾追加字段（放在 `_resume_timer` 附近，加注释）：

```python
        # v0.3 修复②：EATING 是否发生在空中（攀爬/坐顶时接住食物）——
        # 吃完需要转 FALLING 自然下落，而不是原地回 IDLE（会悬空）
        self._eat_in_air = False
```

`poke()` 改动（精确编辑指令）：签名改为 `def poke(self) -> bool:`；方法体第一行（docstring 之后）插入守卫 `if self.paused: return False`，附行内注释"v0.3 修复①（spec §1.1）：暂停 = 整体冻结，事件完全无响应"；方法体内原有的全部裸 `return`（共 3 处：睡眠中被戳转 WOKEN 分支、连戳重播分支、常规反应末尾）改为 `return True`；docstring 首段追加一行"返回是否受理：暂停时 False（GUI 据此不播音效）"。主体逻辑与特判顺序不变。

`feed()` 整体替换为：

```python
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
```

`tick()` 的 EATING 分支整体替换为（`in_window` 沿用 tick 顶部已算好的局部变量）：

```python
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
```

`drag_end()` 加暂停分支：

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_state_machine.py -v`
Expected: 全部 PASS。若既有测试因 `poke()` 返回值变化失败——不会（既有测试不断言 poke 返回值），失败则检查是否误改了主体逻辑。

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/state_machine.py tests/test_state_machine.py
git commit -m "fix(state): 暂停冻结戳/喂食事件、攀爬坐顶可喂食、暂停半空松手落地" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 状态机穿越——wrap_chance / wrap_edges / 三岔骰子 / 穿越周期

**Files:**
- Modify: `xiaoliang/state_machine.py`（`__init__`、`_decide_walk_or_climb`、`_tick_walking`、新方法 `_start_wrap_sequence`/`_tick_wrap`/`set_wrap_edges`、`_start_sleeping`/`_start_idle`/`_start_walking`）
- Test: `tests/test_state_machine.py`（追加）

**Interfaces:**
- Consumes: Task 2 后的状态机
- Produces: 构造参数 `wrap_chance: float = 0.08`、`wrap_edges: Iterable[int] | None = None`（元素 -1/1）；实例属性 `self.wrap_edges: set[int]`；方法 `set_wrap_edges(edges) -> None`。main.py（Task 12）注入初值并在屏幕热插拔时调 setter。

- [ ] **Step 1: 写失败测试**（追加）

```python
# ── v0.3 新功能⑥：屏幕穿越（spec §1.4） ────────────────────────────

def test_decide_can_choose_wrap():
    # random_value 0.20 落在 [climb 0.15, 0.15+0.08) → 穿越分支
    m = make_machine(rng=FakeRandom(choice_value=-1, random_value=0.20),
                     wrap_edges={-1, 1})
    m.tick(1.1)                        # IDLE 出门掷骰
    assert m.state is State.WALKING
    assert m._walk_intent == "wrap"
    assert m.direction == -1           # 选中的可穿越边缘方向


def test_wrap_skipped_when_no_edges():
    """wrap_edges 为空：穿越概率并入普通散步。"""
    m = make_machine(rng=FakeRandom(choice_value=-1, random_value=0.20),
                     wrap_edges=set())
    m.tick(1.1)
    assert m.state is State.WALKING
    assert m._walk_intent is None      # 普通散步


def test_wrap_full_cycle_left_exit_right_enter():
    m = make_machine(rng=FakeRandom(choice_value=-1, random_value=0.20),
                     wrap_edges={-1, 1}, start_x=30)
    m.tick(1.1)                        # → WALKING wrap 向左（speed 100）
    m.tick(0.5)                        # x = -20，尚未整体没入（> -64）
    assert m._walk_intent == "wrap"
    m.tick(0.6)                        # x = -80 ≤ -64 → 瞬移到 x=800（右端屏外）
    assert m.x == 800.0
    m.tick(0.7)                        # 向左走回 70px → x=730 ≤ 736（max_x）→ 入屏
    assert m._walk_intent is None      # 转普通散步
    assert m.state is State.WALKING
    assert m.direction == -1


def test_wrap_right_exit_left_enter():
    m = make_machine(rng=FakeRandom(choice_value=1, random_value=0.20),
                     wrap_edges={-1, 1}, start_x=800 - 64 - 10)
    m.tick(1.1)                        # → wrap 向右
    m.tick(0.9)                        # x = 744+90=834 ≥ 800 → 瞬移 x=-64
    assert m.x == -64.0
    m.tick(0.7)                        # 向右走回 70px → x=6 ≥ 0 → 入屏
    assert m._walk_intent is None


def test_sleep_window_during_wrap_clamps_into_view():
    """穿越途中（屏外）到点睡觉：位置钳回工作区，不能睡在屏幕外。"""
    clock = FakeClock(dtime(12, 0))
    m = make_machine(rng=FakeRandom(choice_value=-1, random_value=0.20),
                     wrap_edges={-1, 1}, clock=clock, start_x=30)
    m.tick(1.1)
    m.tick(1.0)                        # x = -70 ≤ -64 → 瞬移到 x=800（屏外）
    assert m.x == 800.0
    clock.now = dtime(23, 30)          # 进入睡眠时段
    m.tick(0.1)
    assert m.state is State.SLEEPING
    assert m.x == 800 - 64             # 已钳回工作区右界


def test_set_wrap_edges_filters_invalid():
    m = make_machine()
    m.set_wrap_edges({-1, 0, 5})
    assert m.wrap_edges == {-1}
```

注：测试里的 tick 步长按 100px/s 走速与既有测试同款推算（转移当帧不位移）；若实现后个别断言差一帧，微调 dt 对齐，**不得改变断言语义**。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_state_machine.py -v`
Expected: 新增 FAIL（`__init__() got an unexpected keyword argument 'wrap_edges'` 等）

- [ ] **Step 3: 实现**

`__init__` 签名在 `climb_low_mood_factor` 之后加两个参数，体内初始化两个字段：

```python
                 wrap_chance: float = 0.08,
                 wrap_edges=None,
```

```python
        # ── v0.3 穿越（spec §1.4）：概率与可穿越边缘集合（GUI 注入，
        # 元素 -1=左缘 / 1=右缘；某侧边缘外有相邻屏幕则该侧不可穿越）──
        self.wrap_chance = wrap_chance
        self.wrap_edges = {e for e in (wrap_edges or ()) if e in (-1, 1)}
        # 穿越阶段："out"=正走出屏幕 / "in"=瞬移后正走回屏内 / None=不在穿越
        self._wrap_phase: str | None = None
```

新方法（放在 `set_paused` 附近的事件 API 区）：

```python
    def set_wrap_edges(self, edges) -> None:
        """更新可穿越边缘集合（屏幕热插拔时由 GUI 刷新，spec §1.4）。"""
        self.wrap_edges = {e for e in edges if e in (-1, 1)}
```

`_decide_walk_or_climb` 整体替换为三岔：

```python
    def _decide_walk_or_climb(self) -> None:
        """发呆计时到点后掷骰子，三岔（spec §1.4）：
        攀爬 climb_chance（心情差 ×0.3）→ 穿越 wrap_chance（仅当存在
        可穿越边缘时参与，否则概率并入散步）→ 普通散步。
        """
        chance = self.climb_chance
        if self.status.is_bored:         # 心情差（<20）：没兴致玩，概率 ×0.3
            chance *= self.climb_low_mood_factor
        roll = self._rng.random()
        if roll < chance:
            self._start_climb_sequence()
            return
        if self.wrap_edges and roll < chance + self.wrap_chance:
            self._start_wrap_sequence()
            return
        self._start_walking()
```

新方法（放在 `_start_climb_sequence` 之后）：

```python
    def _start_wrap_sequence(self) -> None:
        """穿越意图：选定一个可穿越边缘方向走过去，到缘不停直接走出屏幕。"""
        edge = self._rng.choice(sorted(self.wrap_edges))   # sorted 保证可测
        self.direction = edge
        self._walk_intent = "wrap"
        self._wrap_phase = "out"
        self.state = State.WALKING

    def _tick_wrap(self) -> None:
        """穿越推进（位移已在 _tick_walking 顶部完成）：
        out 阶段走到整体没入屏外 → 瞬移到对端屏外转 in 阶段；
        in 阶段走回屏内 → 转普通散步并重置随机计时（不在边缘立刻停）。
        穿越期间不递减计时器、不做边缘钳制。
        """
        if self._wrap_phase == "out":
            exited = (self.x <= -self.pet_width if self.direction < 0
                      else self.x >= self.bounds.width)
            if exited:
                self.x = float(self.bounds.width if self.direction < 0
                               else -self.pet_width)
                self._wrap_phase = "in"
        elif self._wrap_phase == "in":
            if 0.0 <= self.x <= self.bounds.width - self.pet_width:
                self._walk_intent = None
                self._wrap_phase = None
                self._timer = self._rng.uniform(*self.walk_range)
```

`_tick_walking` 在 climb 分支之后、普通边缘检查之前插入：

```python
        if self._walk_intent == "wrap":
            self._tick_wrap()
            return
```

`_start_sleeping` 加钳制与清理（整方法替换）：

```python
    def _start_sleeping(self) -> None:
        self.state = State.SLEEPING
        self._walk_intent = None
        self._wrap_phase = None
        # 穿越途中（可能在屏外）到点睡觉：把位置钳回工作区，
        # 避免"睡在屏幕外看不见"（spec §1.6）
        max_x = float(self.bounds.width - self.pet_width)
        self.x = min(max(self.x, 0.0), max_x)
```

`_start_idle` 与 `_start_walking` 各加一行 `self._wrap_phase = None`（与 `self._walk_intent = None` 并列）。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_state_machine.py -v`
Expected: 全部 PASS。特别关注既有走路/攀爬测试——`FakeRandom.random_value=0.99` 默认高于 0.15+0.08，不会误入穿越分支。

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/state_machine.py tests/test_state_machine.py
git commit -m "feat(state): 屏幕穿越——三岔骰子、走出/瞬移/走回周期、可穿越边缘注入" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: 状态机 REMINDING 状态与 remind() API

**Files:**
- Modify: `xiaoliang/state_machine.py`（`State` 枚举、`__init__`、`tick`、新方法 `remind`）
- Test: `tests/test_state_machine.py`（追加）

**Interfaces:**
- Consumes: Task 2/3 后的状态机
- Produces: `State.REMINDING`；构造参数 `remind_secs: float = 3.0`；方法 `remind() -> bool`（拒绝条件：paused / SLEEPING / WOKEN / DRAGGED / REMINDING，拒绝时零副作用返回 False）。reminder 服务（Task 6 产出、Task 12 接线）调用。

- [ ] **Step 1: 写失败测试**（追加）

```python
# ── v0.3 新功能⑦⑧配套：REMINDING（spec §1.5） ─────────────────────

def test_remind_accepted_from_idle_and_returns():
    m = make_machine()
    assert m.remind() is True
    assert m.state is State.REMINDING
    m.tick(3.1)                        # remind_secs 默认 3.0
    assert m.state is State.IDLE


def test_remind_rejected_while_paused():
    m = make_machine()
    m.set_paused(True)
    assert m.remind() is False
    assert m.state is State.IDLE


def test_remind_rejected_while_sleeping():
    clock = FakeClock(dtime(23, 30))
    m = make_machine(clock=clock)
    m.tick(0.5)                        # 入睡
    assert m.state is State.SLEEPING
    assert m.remind() is False
    assert m.state is State.SLEEPING   # 零副作用


def test_remind_resumes_walking_remaining_timer():
    """提醒播完回原状态并接续剩余计时（同 POKE_REACT 恢复机制）。"""
    m = make_machine(rng=FakeRandom(choice_value=1, random_value=0.99))
    m.tick(1.1)                        # → WALKING，walk 计时 2.0
    m.tick(1.0)                        # 剩 1.0
    assert m.remind() is True
    m.tick(3.1)                        # REMINDING 3.0 播完 → 回 WALKING
    assert m.state is State.WALKING
    m.tick(0.5)                        # 剩 0.5，还没走完
    assert m.state is State.WALKING
    m.tick(0.6)
    assert m.state is State.IDLE


def test_remind_from_climbing_returns_to_climbing():
    m = make_machine(rng=FakeRandom(choice_value=-1, random_value=0.1),
                     start_x=0)
    m.tick(1.1)
    assert m.state is State.CLIMBING
    assert m.remind() is True
    m.tick(3.1)
    assert m.state is State.CLIMBING   # 回墙上继续爬


def test_remind_rejected_while_dragged():
    m = make_machine()
    m.drag_start()
    assert m.remind() is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_state_machine.py -v`
Expected: FAIL（`AttributeError: ... has no attribute 'REMINDING'` / `remind`）

- [ ] **Step 3: 实现**

`State` 枚举追加（`SITTING_TOP` 之后）：

```python
    REMINDING = auto()     # 久坐提醒/整点报时：播伸懒腰动画后回原状态
```

`__init__` 签名加 `remind_secs: float = 3.0`（`eating_secs` 之后），体内：

```python
        self.remind_secs = remind_secs
        # REMINDING 的恢复机制（与 POKE_REACT 的 _pre_poke_state 同款但
        # 独立字段：REMINDING 中被戳 → POKE_REACT 播完回 REMINDING，
        # 两层嵌套互不覆盖）
        self._pre_remind_state: State | None = None
        self._remind_resume_timer = 0.0
```

`remind()` 新方法（事件 API 区，`feed` 之后）：

```python
    def remind(self) -> bool:
        """提醒事件（久坐/整点服务触发，spec §1.5）：播伸懒腰动画，
        播完回原状态并接续剩余计时。

        拒绝条件（返回 False，零副作用）：暂停 / 睡觉 / 惺忪 / 被拎着 /
        正在提醒中——这是防御性兜底，完整免打扰判定在 reminder 服务层。
        被拒时调用方仍会念语音：提醒的使命是传达信息，动画只是锦上添花。
        """
        if self.paused:
            return False
        if self.state in (State.SLEEPING, State.WOKEN, State.DRAGGED,
                          State.REMINDING):
            return False
        self._pre_remind_state = self.state
        self._remind_resume_timer = self._timer
        self.state = State.REMINDING
        self._timer = self.remind_secs
        return True
```

`tick()` 加 REMINDING 分支（POKE_REACT 分支之后）：

```python
        elif self.state is State.REMINDING:
            self._timer -= dt
            if self._timer <= 0:
                # 播完回提醒前状态并接续剩余计时（同 POKE_REACT 恢复机制）
                prev = self._pre_remind_state
                if prev is None or prev is State.REMINDING:
                    prev = State.IDLE    # 防御：绝不回到自身
                self.state = prev
                self._timer = self._remind_resume_timer
```

模块 docstring 追加一行 v0.3 说明（新状态 REMINDING、穿越意图、暂停冻结事件）。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_state_machine.py -v`
Expected: 全部 PASS

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/state_machine.py tests/test_state_machine.py
git commit -m "feat(state): REMINDING 状态与 remind() 事件——提醒动画播完接续原状态" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: screen_info.py——邻屏检测（纯几何 + Qt 薄层）

**Files:**
- Create: `xiaoliang/screen_info.py`
- Test: `tests/test_screen_info.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `neighbor_edges(rect, others, tol=1) -> set[int]`（纯函数；rect 为 `(left, top, right, bottom)` 元组，Qt `QRect` 的 right/bottom 为**包含式**坐标，相邻屏差 1 → 默认 tol=1）；`wrap_and_cling_edges() -> tuple[set[int], set[int]]`（Qt 层：返回 (可穿越边缘=无邻屏侧, 需 mask 边缘=有邻屏侧)）。Task 10（mask）、Task 12（注入）消费。

- [ ] **Step 1: 写失败测试**（新建 `tests/test_screen_info.py`）

```python
"""screen_info 纯几何逻辑测试（Qt 薄层留给 GUI 验收，spec §4）。"""
from xiaoliang.screen_info import neighbor_edges

# 主屏工作区 1920x1080（Qt 包含式坐标：right = left+width-1）
PRIMARY = (0, 0, 1919, 1079)


def test_single_screen_no_neighbors():
    assert neighbor_edges(PRIMARY, [PRIMARY]) == set()


def test_neighbor_on_right():
    right = (1920, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, right]) == {1}


def test_neighbor_on_left():
    left = (-1920, 0, -1, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, left]) == {-1}


def test_neighbors_both_sides():
    left = (-1920, 0, -1, 1079)
    right = (1920, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, left, right]) == {-1, 1}


def test_gap_beyond_tolerance_not_neighbor():
    """间距 2px（超出 tol=1）：不算相邻。"""
    gapped = (1921, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, gapped]) == set()


def test_vertical_disjoint_not_neighbor():
    """右上方远处的屏（垂直无交集）：不算相邻。"""
    above = (1920, -2000, 3839, -1000)
    assert neighbor_edges(PRIMARY, [PRIMARY, above]) == set()


def test_partial_vertical_overlap_counts():
    """垂直部分重叠（如邻屏分辨率更矮）：算相邻。"""
    short = (1920, 500, 3839, 900)
    assert neighbor_edges(PRIMARY, [PRIMARY, short]) == {1}


def test_touching_one_pixel_is_neighbor():
    """Qt 包含式坐标下相邻屏 left - 主屏 right == 1：tol=1 命中。"""
    touch = (1920, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, touch], tol=1) == {1}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_screen_info.py -v`
Expected: FAIL（ModuleNotFoundError: xiaoliang.screen_info）

- [ ] **Step 3: 实现**（新建 `xiaoliang/screen_info.py`）

```python
"""屏幕布局查询：邻屏检测（spec §4）。

纯几何函数 neighbor_edges 不依赖 Qt（可单测）；Qt 薄层把 QScreen
工作区换算成矩形元组后交给纯函数。坐标沿用 Qt QRect 约定：
(left, top, right, bottom)，right/bottom 为包含式（= left+width-1），
因此物理紧邻的两屏边缘坐标差 1，默认容差 tol=1。
"""
from PySide6.QtGui import QGuiApplication


def neighbor_edges(rect: tuple, others: list, tol: int = 1) -> set:
    """rect 的左/右边缘外是否紧邻其他屏幕。

    rect/others 元素：(left, top, right, bottom) 全局坐标元组。
    返回 {-1, 1} 的子集：-1 = 左缘有邻屏，1 = 右缘有邻屏。
    相邻判定：邻屏对应边缘坐标与 rect 边缘差 ≤ tol，且垂直范围有交集
    （上下完全错开的屏即使 x 相邻也不算——小凉不可能走过去）。
    """
    left, top, right, bottom = rect
    result = set()
    for other in others:
        if tuple(other) == tuple(rect):
            continue                       # 跳过自身
        ol, ot, orr, ob = other
        if not (ot < bottom and ob > top):
            continue                       # 垂直无交集
        if abs(orr - left) <= tol:
            result.add(-1)                 # 邻屏右缘贴着我左缘
        if abs(ol - right) <= tol:
            result.add(1)                  # 邻屏左缘贴着我右缘
    return result


def _workarea_rects() -> tuple:
    """(主屏工作区矩形, 所有屏工作区矩形列表)。"""
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen().availableGeometry()
    rects = []
    for s in screens:
        g = s.availableGeometry()
        rects.append((g.left(), g.top(), g.right(), g.bottom()))
    return (primary.left(), primary.top(),
            primary.right(), primary.bottom()), rects


def wrap_and_cling_edges() -> tuple:
    """返回 (可穿越边缘集合, 需 mask 裁剪的边缘集合)。

    可穿越 = 无邻屏的边缘（尽头才是"传送门"，有邻屏的边缘是"墙"，
    走到就停——spec §1.4/§4）；需 mask = 有邻屏的边缘（贴边推出的
    墨水会画到邻屏上，需 setMask 裁剪——spec §4.2）。
    两者互为补集，供 main.py 一次性取用。
    """
    primary, rects = _workarea_rects()
    cling = neighbor_edges(primary, rects)
    wrap = {-1, 1} - cling
    return wrap, cling
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_screen_info.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/screen_info.py tests/test_screen_info.py
git commit -m "feat(screen): 屏幕邻接检测——穿越可通行边缘与贴边 mask 边缘" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: reminder.py——久坐提醒 + 整点报时（纯逻辑 + Qt 心跳驱动）

**Files:**
- Create: `xiaoliang/reminder.py`
- Test: `tests/test_reminder.py`（新建）

**Interfaces:**
- Consumes: 无（免打扰查询由调用方注入 `dnd` 回调；Task 12 传 `lambda: machine.paused or machine.in_sleep_window()`）
- Produces: `get_idle_seconds() -> float`（Win32 键鼠空闲秒数）；`ReminderLogic(sit_minutes=45, idle_threshold_minutes=5, *, heartbeat_secs=15, rng=None, dnd=None)` 带纯方法 `tick(now: datetime, idle_secs: float) -> list[tuple[str, str]]`（返回 `("sit"|"hour", 文案)` 列表）；`ReminderService(logic, on_event, *, idle_provider=get_idle_seconds, clock=None)` 带 `start()`（Qt QTimer 驱动，`on_event(kind, text)` 回调）；`hour_text(now) -> str`。

- [ ] **Step 1: 写失败测试**（新建 `tests/test_reminder.py`）

```python
"""提醒服务纯逻辑测试：假时钟驱动 tick()，不碰 Qt/Win32（spec §3、§7）。"""
from datetime import datetime, timedelta

from xiaoliang.reminder import ReminderLogic, hour_text

BASE = datetime(2026, 9, 24, 10, 0, 0)
STEP = timedelta(seconds=15)           # 与默认心跳间隔一致


def run_ticks(logic, count, start=BASE, idle_secs=0.0):
    """连续驱动 count 次心跳，收集全部触发事件。"""
    events = []
    for i in range(count):
        events.extend(logic.tick(start + STEP * i, idle_secs))
    return events


def test_sit_reminder_fires_after_threshold():
    # sit_minutes=1 → 60s；每次心跳累加 15s → 第 4 次到点
    logic = ReminderLogic(sit_minutes=1, idle_threshold_minutes=5)
    events = run_ticks(logic, 4)
    assert len(events) == 1
    assert events[0][0] == "sit"
    assert isinstance(events[0][1], str) and events[0][1]


def test_sit_reminder_restarts_after_firing():
    logic = ReminderLogic(sit_minutes=1, idle_threshold_minutes=5)
    events = run_ticks(logic, 8)       # 第 4、8 次各触发一轮
    assert [k for k, _ in events] == ["sit", "sit"]


def test_sit_timer_resets_on_idle():
    logic = ReminderLogic(sit_minutes=1, idle_threshold_minutes=5)
    assert run_ticks(logic, 3) == []                     # 累计 45s
    ev = logic.tick(BASE + timedelta(seconds=45), 400.0) # 离开 400s > 300s
    assert ev == []
    ev = run_ticks(logic, 3, start=BASE + timedelta(seconds=60))
    assert ev == []                                      # 重计 45s 未到点
    ev = logic.tick(BASE + timedelta(seconds=105), 0.0)
    assert len(ev) == 1 and ev[0][0] == "sit"


def test_hour_chime_on_hour_change():
    logic = ReminderLogic()
    logic.tick(datetime(2026, 9, 24, 14, 59, 50), 0.0)   # 初始化 last_hour
    events = logic.tick(datetime(2026, 9, 24, 15, 0, 5), 0.0)
    assert len(events) == 1
    assert events[0][0] == "hour"
    assert "下午3点整" in events[0][1]


def test_no_chime_on_first_tick():
    logic = ReminderLogic()
    assert logic.tick(BASE, 0.0) == []                   # 首次只初始化


def test_no_chime_after_sleep_gap():
    """两次心跳跨度远超心跳间隔（合盖唤醒）：静默同步，不补报。"""
    logic = ReminderLogic()
    logic.tick(datetime(2026, 9, 24, 14, 0, 0), 0.0)
    events = logic.tick(datetime(2026, 9, 24, 16, 30, 0), 0.0)
    assert events == []


def test_no_chime_when_away():
    logic = ReminderLogic()
    logic.tick(datetime(2026, 9, 24, 14, 59, 50), 0.0)
    events = logic.tick(datetime(2026, 9, 24, 15, 0, 5), 400.0)
    assert events == []


def test_dnd_suppresses_everything():
    flag = {"on": True}
    logic = ReminderLogic(sit_minutes=1, dnd=lambda: flag["on"])
    assert run_ticks(logic, 5) == []                     # 久坐被压制
    flag["on"] = False
    events = run_ticks(logic, 4, start=BASE + timedelta(seconds=75))
    assert len(events) == 1 and events[0][0] == "sit"    # 解除后恢复


def test_hour_text_formats():
    assert hour_text(datetime(2026, 9, 24, 15, 0)) == "现在下午3点整"
    assert hour_text(datetime(2026, 9, 24, 12, 0)) == "现在中午12点整"
    assert hour_text(datetime(2026, 9, 24, 0, 0)) == "现在凌晨12点整"
    assert hour_text(datetime(2026, 9, 24, 9, 0)) == "现在上午9点整"


def test_get_idle_seconds_smoke():
    """Win32 实调冒烟：非负 float（仅 Windows 跑，其他平台跳过）。"""
    import sys
    if sys.platform != "win32":
        import pytest
        pytest.skip("Windows only")
    from xiaoliang.reminder import get_idle_seconds
    assert get_idle_seconds() >= 0.0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_reminder.py -v`
Expected: FAIL（ModuleNotFoundError: xiaoliang.reminder）

- [ ] **Step 3: 实现**（新建 `xiaoliang/reminder.py`）

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_reminder.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/reminder.py tests/test_reminder.py
git commit -m "feat(remind): 久坐提醒与整点报时——空闲检测、免打扰、防休眠误报" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: sound.py——声音引擎（音效池 + TTS + 开关）

**Files:**
- Create: `xiaoliang/sound.py`
- Test: `tests/test_sound.py`（新建）

**Interfaces:**
- Consumes: `cfg["sound"]` dict（Task 1；引擎持有**同一 dict 引用**，托盘改 muted 立即生效）
- Produces: `should_play(sound_cfg, category) -> bool`（纯函数；category ∈ "poke_sfx"/"sit_reminder"/"hourly_chime"）；`POKE_COOLDOWN_MS = 500`；`SoundEngine(sound_cfg: dict, sounds_dir: Path | None = None, *, rng=None, clock_ms=None)` 带 `play_poke()`、`speak(text: str, category: str)`。Task 10/11/12 消费。

- [ ] **Step 1: 写失败测试**（新建 `tests/test_sound.py`）

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_sound.py -v`
Expected: FAIL（ModuleNotFoundError: xiaoliang.sound）

- [ ] **Step 3: 实现**（新建 `xiaoliang/sound.py`）

```python
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
    """
    if not isinstance(sound_cfg, dict):
        return False
    if sound_cfg.get("muted", False):
        return False
    return bool(sound_cfg.get(category, True))


class SoundEngine:
    """音效池 + TTS 双通道。

    sound_cfg 持有 config["sound"] 的**同一 dict 引用**：托盘切换
    muted 直接改 dict，引擎下一次判定立即生效，无需通知机制。
    音效池 = sounds_dir 下全部 .wav（目录式加载：用户丢文件即加音效，
    删文件即移除，零代码改动——spec §2.1）；目录为空/缺失 = 戳她静音。
    """

    def __init__(self, sound_cfg: dict, sounds_dir: Path | None = None, *,
                 rng=None, clock_ms=None):
        self._cfg = sound_cfg
        self._rng = rng or random.Random()
        self._clock_ms = clock_ms or (lambda: time.monotonic() * 1000.0)
        self._effects: list = []
        self._tts = None
        self._ok = False
        self._last_poke_ms = float("-inf")
        try:
            self._init_backend(sounds_dir)
            self._ok = True
        except Exception:
            logger.exception("声音引擎初始化失败，降级为静默模式")

    def _init_backend(self, sounds_dir: Path | None) -> None:
        """装载 Qt 后端。任何异常向上抛，由 __init__ 统一降级。"""
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
        if now - self._last_poke_ms < POKE_COOLDOWN_MS:
            return
        self._last_poke_ms = now
        if self._effects:
            effect = self._rng.choice(self._effects)
            effect.stop()          # 打断上一次未播完的同类音效，避免叠音爆音
            effect.play()

    def speak(self, text: str, category: str) -> None:
        """TTS 念一句（入队模式：连续两句不互相掐断，spec §2.1）。

        category ∈ "sit_reminder"/"hourly_chime"，对应独立开关。
        """
        if not self._ok or not should_play(self._cfg, category):
            return
        from PySide6.QtTextToSpeech import QTextToSpeech
        try:
            self._tts.say(text, QTextToSpeech.QueueMode.Enqueue)
        except Exception:
            logger.exception("TTS 播放失败: %r", text)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_sound.py -v`
Expected: 11 PASS

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/sound.py tests/test_sound.py
git commit -m "feat(sound): 声音引擎——音效池随机播放、TTS 入队、开关与冷却、失败降级静默" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: autostart.py——开机自启（HKCU Run 注册表）

**Files:**
- Create: `xiaoliang/autostart.py`
- Test: `tests/test_autostart.py`（新建）

**Interfaces:**
- Consumes: 无
- Produces: `autostart_command() -> str`（Run 键命令行）；`is_enabled() -> bool | None`（None = 注册表不可读，菜单应置灰）；`set_enabled(enable: bool) -> bool`（返回是否成功）。Task 11（托盘）消费。真相源 = 注册表本身，config.json 不存副本（spec §5.1）。

- [ ] **Step 1: 写失败测试**（新建 `tests/test_autostart.py`）

```python
"""开机自启测试：命令行构造为纯函数；注册表读写用临时键名做往返实测。"""
import sys
from pathlib import Path

import pytest

from xiaoliang import autostart


def test_command_source_mode_points_to_main_py():
    """源码运行态：pythonw（或 python）+ main.py 绝对路径，均带引号。"""
    if getattr(sys, "frozen", False):
        pytest.skip("仅源码态")
    cmd = autostart.autostart_command()
    assert cmd.lower().endswith('main.py"') or "main.py" in cmd
    assert cmd.startswith('"')


def test_command_frozen_mode_is_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\apps\xiaoliang.exe")
    assert autostart.autostart_command() == '"C:\\apps\\xiaoliang.exe"'


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 注册表")
def test_registry_roundtrip(monkeypatch):
    """用临时键名做 写→读→删→读 往返，不碰真实的 xiaoliang 键。"""
    monkeypatch.setattr(autostart, "APP_NAME", "xiaoliang_pytest_tmp")
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(True) is True
    assert autostart.is_enabled() is True
    assert autostart.set_enabled(False) is True
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(False) is True   # 删除不存在的值幂等
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv\Scripts\python -m pytest tests/test_autostart.py -v`
Expected: FAIL（ModuleNotFoundError: xiaoliang.autostart）

- [ ] **Step 3: 实现**（新建 `xiaoliang/autostart.py`）

```python
"""开机自启：winreg 读写 HKCU Run 键（spec §5.1）。

只影响当前用户（HKCU），无需管理员权限。真相源 = 注册表本身：
用户可能在任务管理器"启动"页启用/禁用，config.json 不存副本，
避免两份状态漂移。注册表被组策略锁死等异常 → 记日志返回 None/False，
托盘菜单置灰，程序照常跑。
"""
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "xiaoliang"          # Run 键下的值名（测试会 monkeypatch）
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    """Run 键命令行：打包态 = 带引号 exe 路径；源码态 = pythonw + main.py。

    源码态优先 pythonw.exe（无控制台窗口）；venv 里没有则退回 python.exe。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{main_py}"'


def is_enabled():
    """读 Run 键：True/False；注册表不可读（异常）返回 None（菜单置灰）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False              # 值不存在 = 未启用（正常情况）
    except OSError as exc:
        logger.warning("读开机自启注册表失败: %s", exc)
        return None


def set_enabled(enable: bool) -> bool:
    """写/删 Run 键，返回是否成功（失败记日志，托盘勾选回滚）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                                  autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass          # 本来就没有 = 删除幂等成功
        return True
    except OSError as exc:
        logger.warning("写开机自启注册表失败: %s", exc)
        return False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv\Scripts\python -m pytest tests/test_autostart.py -v`
Expected: 3 PASS（非 Windows 平台注册表测试自动 skip）

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang/autostart.py tests/test_autostart.py
git commit -m "feat(autostart): 开机自启——HKCU Run 键读写，真相源为注册表" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: 占位资产——remind 精灵图 + 戳音效 wav + assets/README

**Files:**
- Modify: `tools/gen_placeholder_assets.py`（specs 字典加 "remind" 条目）
- Create: `tools/gen_placeholder_sounds.py`
- Modify: `assets/manifest.json`（由脚本重新生成）
- Create: `assets/remind.png`、`assets/sounds/poke/poke_a.wav`、`assets/sounds/poke/poke_b.wav`（由脚本生成）
- Modify: `assets/README.md`

**Interfaces:**
- Consumes: 现有 `make_sheet` / `draw_pet`（gen_placeholder_assets.py）
- Produces: manifest 新动作 `"remind"`（4 帧 @ 4fps，remind.png）；`assets/sounds/poke/*.wav`（SoundEngine 目录式加载）。Task 10 的 `STATE_ACTION[State.REMINDING] = "remind"` 依赖 manifest 里该动作存在。

- [ ] **Step 1: 扩展素材脚本**（`tools/gen_placeholder_assets.py` 的 `specs` 字典追加一条，`"sitting_top"` 之后）

```python
        # v0.3 提醒动作：举手伸懒腰（复用 draw_pet 的 arms_up + 呼吸起伏，
        # 占位素材——正式素材替换规格见 assets/README.md）
        "remind": ([{"arms_up": True, "body_dy": dy} for dy in (0, 1, 2, 1)],
                   4, draw_pet),
```

- [ ] **Step 2: 新建音频脚本**（`tools/gen_placeholder_sounds.py`）

```python
"""生成占位戳音效：两个不同音高的短促"叮/咚"（后续替换为正式素材）。

用法（项目根目录）：
    .venv\\Scripts\\python tools\\gen_placeholder_sounds.py

输出到 assets\\sounds\\poke\\：poke_a.wav / poke_b.wav
（16-bit 单声道 22050Hz；SoundEngine 目录式加载，丢新 wav 即加音效）。
"""
import math
import struct
import wave
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds" / "poke"
RATE = 22050


def blip(freq: float, secs: float = 0.18) -> bytes:
    """合成指数衰减短音：基频正弦 + 半幅倍频，比纯音圆润一点。"""
    n = int(RATE * secs)
    frames = bytearray()
    for i in range(n):
        t = i / RATE
        env = math.exp(-t * 12.0)                       # 衰减包络
        v = (math.sin(2 * math.pi * freq * t)
             + 0.5 * math.sin(4 * math.pi * freq * t))
        frames += struct.pack("<h", int(v * env * 12000))
    return bytes(frames)


def write_wav(path: Path, data: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_wav(OUT_DIR / "poke_a.wav", blip(880.0))      # 偏高音"叮"
    write_wav(OUT_DIR / "poke_b.wav", blip(660.0))      # 偏低音"咚"
    print(f"已生成占位音效: {OUT_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 跑生成脚本 + 素材校验**

Run:
```powershell
.venv\Scripts\python tools\gen_placeholder_assets.py
.venv\Scripts\python tools\gen_placeholder_sounds.py
.venv\Scripts\python tools\check_sprites.py
```
Expected: 素材脚本列出含 `remind: remind.png 4 帧 @ 4 fps`；check_sprites 通过（manifest 与 PNG 尺寸一致）。注意：gen_placeholder_assets.py 会重生成全部 PNG 与 manifest——确认 git diff 中既有素材若无像素级差异之外的意外变化（脚本是确定性的，应只有新增 remind 条目与文件）。

- [ ] **Step 4: 更新 `assets/README.md`**

追加一节（沿用文件现有行文风格）：

```markdown
## 音频素材（v0.3）

- `sounds/poke/*.wav`：戳她音效池，程序启动时目录式加载（随机播一个）。
  规格：wav 格式（QSoundEffect 原生支持），建议 16-bit 单声道、≤1 秒短音。
  替换/新增：把 wav 丢进目录即可，无需改代码或配置；删文件即移除。
- `remind.png`：提醒动作（伸懒腰），4 帧 @ 4fps，帧规格与其他动作一致
  （64×64 逻辑像素横排）。替换时按 manifest.json 的 remind 条目画好
  帧数与尺寸，跑 `tools\check_sprites.py` 验证。
- 占位音效由 `tools\gen_placeholder_sounds.py` 合成（正弦短音），
  正式素材就绪后直接覆盖。
```

- [ ] **Step 5: Commit**

```powershell
git add tools/gen_placeholder_assets.py tools/gen_placeholder_sounds.py assets/
git commit -m "feat(assets): remind 伸懒腰占位帧与占位戳音效，音频替换规格入 README" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 10: pet_window.py——REMINDING 映射、戳音效、贴边 mask、空中进食贴边保持

**Files:**
- Modify: `xiaoliang/pet_window.py`
- Test: 无新增单测（GUI 层，验收清单 §8 覆盖）；跑全量回归确保不破坏既有

**Interfaces:**
- Consumes: `State.REMINDING`（Task 4）、`machine.poke() -> bool`（Task 2）、`SoundEngine.play_poke()`（Task 7）、manifest "remind" 动作（Task 9）
- Produces: `PetWindow(machine, sprites, origin=None, on_quit=None, *, sound=None, mask_edges=None)`；`set_mask_edges(edges: set) -> None`。Task 12 注入。

- [ ] **Step 1: 映射表与导入**

文件头 `from PySide6.QtGui import` 行加 `QRegion`。`STATE_ACTION` 加：

```python
    State.REMINDING: "remind",
```

`STATE_ZH` 加：

```python
    State.REMINDING: "伸懒腰",
```

模块 docstring 追加 v0.3 说明（REMINDING 渲染、贴边 mask、戳音效）。

- [ ] **Step 2: 构造函数扩展**（`__init__` 签名与字段）

```python
    def __init__(self, machine: PetStateMachine, sprites: SpriteManager,
                 origin: QPoint | None = None, on_quit=None, *,
                 sound=None, mask_edges=None):
```

字段初始化（`self._cling_margin = 0` 附近）：

```python
        # ── v0.3 注入：声音引擎（戳音效）与需 mask 裁剪的边缘集合 ──
        # sound 可为 None（测试/静音环境）；mask_edges = 贴边侧有相邻
        # 屏幕的边缘（{-1,1} 子集），由 screen_info 计算、main.py 注入
        self._sound = sound
        self._mask_edges = set(mask_edges or ())
        # mask 是否已设置：只在需要↔不需要切换或推出量变化时调
        # setMask/clearMask（窗口重组合有成本，不能每帧做）
        self._mask_on = False
        self._mask_margin_px = -1
```

新方法（`current_action` 附近）：

```python
    def set_mask_edges(self, edges: set) -> None:
        """屏幕热插拔时刷新需 mask 的边缘集合（main.py 调，spec §4.2）。"""
        self._mask_edges = set(edges)
        if self._mask_on:            # 强制下次 tick 重算 mask
            self.clearMask()
            self._mask_on = False
            self._mask_margin_px = -1
```

- [ ] **Step 3: 贴边保持分支扩展**（`_on_tick` 内）

现有分支：

```python
        elif self.machine.state in (State.POKE_REACT, State.FALLING):
```

改为（注释同步更新）：

```python
        elif self.machine.state in (State.POKE_REACT, State.FALLING,
                                    State.EATING, State.REMINDING):
            # 在壁上被戳/空中进食/壁上被提醒/跳下的瞬间 machine.x 仍吸附
            # 在墙边，推出量必须沿用进入前的值不能归零，否则窗口一帧横跳
            # K*scale；落地/播完回 IDLE 等地面状态后由下一分支清除。
            # EATING/REMINDING 发生在地面时 _cling_margin 本来就是 0，
            # pass 保持不变，无副作用
```

（注意：v0.2 该分支注释只提 POKE_REACT/FALLING，替换整段注释。）

- [ ] **Step 4: mask 逻辑**（`_on_tick` 内，`cling_off = ...` 计算之后、`self.move(...)` 之前插入）

```python
        # ── v0.3 修复③（spec §4.2）：贴边侧有相邻屏幕时，Windows 不按
        # 单屏边界裁剪窗口，推出的搁板端头/脚部墨水会画到邻屏上——用
        # setMask 裁掉越界条带。只在边缘归属/推出量变化时重设 mask，
        # 不是每帧操作。宽度 = 推出逻辑列 × 素材放大 × 设备像素比
        # （widget 坐标在高 DPI 下按设备像素解释，100% 缩放时 dpr=1）
        need_mask = (self._cling_margin > 0
                     and self.machine.climb_wall in self._mask_edges)
        if need_mask:
            margin_px = int(round(self._cling_margin * self.sprites.scale
                                  * self.devicePixelRatioF()))
            if not self._mask_on or margin_px != self._mask_margin_px:
                w, h = int(self.width() * self.devicePixelRatioF()), \
                    int(self.height() * self.devicePixelRatioF())
                if self.machine.climb_wall > 0:
                    # 右壁：窗口右侧 margin_px 越界 → 裁掉右边条带
                    region = QRegion(0, 0, w - margin_px, h)
                else:
                    # 左壁：裁掉左边条带
                    region = QRegion(margin_px, 0, w - margin_px, h)
                self.setMask(region)
                self._mask_on = True
                self._mask_margin_px = margin_px
        elif self._mask_on:
            self.clearMask()
            self._mask_on = False
            self._mask_margin_px = -1
```

（验收 §8 第 4 项在高 DPI 屏上核对；若 mask 位置偏差，去掉 `devicePixelRatioF()` 因子即为 100% 缩放语义——两种都试过后取正确者，并更新此处注释。）

- [ ] **Step 5: 戳音效**（`mouseReleaseEvent` 内戳判定分支）

现有：

```python
            if not self._drag_moved and pressed_ms < POKE_MAX_MS:
                # 短按且无有效位移 = 戳：...
                self.machine.poke()
```

改为：

```python
            if not self._drag_moved and pressed_ms < POKE_MAX_MS:
                # 短按且无有效位移 = 戳：不调 drag_end()（不触发下落），
                # machine.poke() 内部会回退到拖拽前状态并播放反应。
                # v0.3：poke() 返回是否受理（暂停时 False）——受理才播
                # 音效，保证"暂停 = 完全无响应"的语义（spec §1.1）
                if self.machine.poke() and self._sound is not None:
                    self._sound.play_poke()
```

- [ ] **Step 6: 回归**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: 全量 PASS（既有 GUI 无单测，靠 import 冒烟 + 后续验收）

Run 冒烟（不弹窗，仅验证模块可导入构造签名）:
`.venv\Scripts\python -c "import xiaoliang.pet_window"`
Expected: 无异常

- [ ] **Step 7: Commit**

```powershell
git add xiaoliang/pet_window.py
git commit -m "feat(gui): REMINDING 渲染、戳音效、多屏贴边 setMask 裁剪、空中进食贴边保持" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 11: tray.py——"静音"与"开机自启"菜单项

**Files:**
- Modify: `xiaoliang/tray.py`
- Test: 无新增单测（GUI 层，验收 §8 覆盖）；跑全量回归

**Interfaces:**
- Consumes: `cfg["sound"]`（Task 1，共享 dict 引用）、`autostart.is_enabled/set_enabled`（Task 8）
- Produces: `PetTray(machine, icon, on_quit, *, sound_cfg=None, on_cfg_changed=None)`。Task 12 注入。

- [ ] **Step 1: 实现**（`xiaoliang/tray.py`）

文件头加导入：

```python
from . import autostart
```

模块 docstring 更新：`"""系统托盘：暂停/恢复、静音、开机自启、退出。双击托盘图标 = 暂停/恢复。"""`

`__init__` 签名扩展：

```python
    def __init__(self, machine: PetStateMachine, icon: QPixmap, on_quit, *,
                 sound_cfg: dict | None = None, on_cfg_changed=None):
```

在 `quit_action` 创建之前插入两个新菜单项（`menu = QMenu()` 之后的 addAction 顺序 = 暂停 / 静音 / 开机自启 / 分隔线 / 退出）：

```python
        # ── v0.3 静音开关（spec §5.2）：与 cfg["sound"]["muted"] 双向同步。
        # SoundEngine 持有同一 dict 引用，改这里立即全局生效；
        # on_cfg_changed 负责落盘 config.json
        self._mute_action = None
        if sound_cfg is not None:
            self._sound_cfg = sound_cfg
            self._on_cfg_changed = on_cfg_changed
            self._mute_action = QAction("静音", self)
            self._mute_action.setCheckable(True)
            self._mute_action.setChecked(bool(sound_cfg.get("muted", False)))
            self._mute_action.toggled.connect(self._on_toggle_mute)

        # ── v0.3 开机自启（spec §5.1）：真相源 = 注册表，启动时读一次；
        # is_enabled() 返回 None（注册表被锁）→ 菜单项置灰
        self._autostart_action = QAction("开机自启", self)
        self._autostart_action.setCheckable(True)
        enabled = autostart.is_enabled()
        if enabled is None:
            self._autostart_action.setEnabled(False)
        else:
            self._autostart_action.setChecked(enabled)
        self._autostart_action.toggled.connect(self._on_toggle_autostart)
```

菜单装配处改为：

```python
        menu = QMenu()
        menu.addAction(self._pause_action)
        if self._mute_action is not None:
            menu.addAction(self._mute_action)
        menu.addAction(self._autostart_action)
        menu.addSeparator()
        menu.addAction(quit_action)
```

新回调方法（`_on_toggle_pause` 之后）：

```python
    def _on_toggle_mute(self, checked: bool) -> None:
        """静音开关：改共享 dict（引擎立即生效）+ 落盘 config。"""
        self._sound_cfg["muted"] = checked
        if self._on_cfg_changed is not None:
            self._on_cfg_changed()

    def _on_toggle_autostart(self, checked: bool) -> None:
        """开机自启开关：写/删注册表；失败则回滚勾选态。"""
        if not autostart.set_enabled(checked):
            self._autostart_action.blockSignals(True)   # 防回滚再触发
            self._autostart_action.setChecked(autostart.is_enabled() or False)
            self._autostart_action.blockSignals(False)
```

- [ ] **Step 2: 回归 + 冒烟**

Run: `.venv\Scripts\python -m pytest tests/ -q` 全绿；
Run: `.venv\Scripts\python -c "import xiaoliang.tray"` 无异常

- [ ] **Step 3: Commit**

```powershell
git add xiaoliang/tray.py
git commit -m "feat(tray): 托盘菜单新增静音与开机自启开关" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 12: main.py 接线——声音/提醒/屏幕布局/自启全部装配

**Files:**
- Modify: `main.py`
- Test: 无新增单测（装配层，验收 §8 覆盖）；全量回归 + import 冒烟

**Interfaces:**
- Consumes: Task 1–11 全部产出
- Produces: 完整可运行的 v0.3 程序

- [ ] **Step 1: 实现**（`main.py`）

导入区追加：

```python
from xiaoliang.reminder import ReminderLogic, ReminderService
from xiaoliang.screen_info import wrap_and_cling_edges
from xiaoliang.sound import SoundEngine
```

`main()` 内，`sprites = SpriteManager(...)` 成功之后、`area = ...` 附近改为：

```python
    area = QGuiApplication.primaryScreen().availableGeometry()
    origin = area.topLeft()  # 工作区左上角（任务栏在顶/左时非零）
    fw, fh = sprites.frame_size()
    # ── v0.3：屏幕布局 → 可穿越边缘（无邻屏侧）与贴边 mask 边缘（有邻屏侧）
    wrap_edges, cling_mask_edges = wrap_and_cling_edges()
    machine = PetStateMachine(
        Bounds(area.width(), area.height()), fw, fh,
        walk_speed=float(cfg["walk_speed"]),
        start_x=(area.width() - fw) / 2,
        status=status,
        sleep_start=cfg["sleep_start"],
        sleep_end=cfg["sleep_end"],
        wrap_chance=float(cfg["wrap_chance"]),
        wrap_edges=wrap_edges,
        on_status_change=save_status)   # 戳/喂食数值变化后即时落盘
    machine.set_paused(bool(cfg["paused"]))

    # ── v0.3：声音引擎（初始化失败自动降级静默，不影响启动） ──
    sound = SoundEngine(cfg["sound"],
                        sounds_dir=assets_dir() / "sounds" / "poke")

    window = PetWindow(machine, sprites, origin=origin, on_quit=app.quit,
                       sound=sound, mask_edges=cling_mask_edges)
    window.move(origin.x() + int(machine.x), origin.y() + int(machine.y))
    window.show()

    def save_cfg() -> None:
        """配置落盘（托盘静音开关等运行时变更）；失败只记日志。"""
        try:
            save_config(cfg, cfg_path)
        except OSError as exc:
            logging.warning("配置保存失败: %s", exc)

    tray = PetTray(machine, sprites.get_frame("idle", 0), app.quit,
                   sound_cfg=cfg["sound"], on_cfg_changed=save_cfg)
    tray.show()

    # ── v0.3：提醒服务（久坐 + 整点）。免打扰 = 暂停或小凉睡觉时段；
    # 事件 → 动画（remind 被拒拉倒，语音照念）+ TTS ──
    logic = ReminderLogic(
        sit_minutes=float(cfg["remind"]["sit_minutes"]),
        idle_threshold_minutes=float(cfg["remind"]["idle_threshold_minutes"]),
        dnd=lambda: machine.paused or machine.in_sleep_window())

    def on_reminder(kind: str, text: str) -> None:
        machine.remind()
        sound.speak(text,
                    "sit_reminder" if kind == "sit" else "hourly_chime")

    reminders = ReminderService(logic, on_reminder)
    reminders.start()

    # ── v0.3：显示器热插拔 → 刷新穿越/mask 边缘（spec §4.1） ──
    def refresh_screens(*_args) -> None:
        wrap_now, mask_now = wrap_and_cling_edges()
        machine.set_wrap_edges(wrap_now)
        window.set_mask_edges(mask_now)

    app.screenAdded.connect(refresh_screens)
    app.screenRemoved.connect(refresh_screens)
```

（替换原有 machine/window/tray 构造段落；`save_timer`、`aboutToQuit` 等既有装配保持不变。）

- [ ] **Step 2: 回归 + 冒烟**

Run: `.venv\Scripts\python -m pytest tests/ -q`
Expected: 全量 PASS

Run: `.venv\Scripts\python -c "import main"`
Expected: 无异常（不执行 main()）

- [ ] **Step 3: Commit**

```powershell
git add main.py
git commit -m "feat(main): v0.3 接线——声音引擎、提醒服务、屏幕布局刷新、托盘扩展" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 13: xiaoliang.spec 统一 onefile + 打包验证

**Files:**
- Modify: `xiaoliang.spec`

**Interfaces:**
- Consumes: 全部前序任务的产物（assets/sounds 目录随 assets 整体收入）
- Produces: `dist\xiaoliang.exe`（onefile，含 v0.3 全部功能）

- [ ] **Step 1: 改 spec**

`Analysis` 的 `hiddenimports` 改为（防 hooks 遗漏 Qt 多媒体/TTS 插件）：

```python
    hiddenimports=['PySide6.QtMultimedia', 'PySide6.QtTextToSpeech'],
```

`EXE(...)` 改 onefile（并入 binaries/datas、删 `exclude_binaries`），并**删除整个 `coll = COLLECT(...)` 段**：

```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='xiaoliang',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

（`datas=[('assets', 'assets')]` 已含 sounds 子目录，不改。）

- [ ] **Step 2: 打包并验证**

Run: `.venv\Scripts\python -m PyInstaller xiaoliang.spec --noconfirm`
Expected: 构建成功，产出 `dist\xiaoliang.exe`（无 `dist\xiaoliang\` 目录形态）

Run: `Get-Item dist\xiaoliang.exe | Select-Object Length`
Expected: 体积 40–80MB（spec §8 第 9 项；QtMultimedia/TTS 插件会略增体积，超 80MB 记录并知会用户）

（exe 行为验证 = 用户验收 §8 第 9 项，代理不启动 GUI。）

- [ ] **Step 3: Commit**

```powershell
git add xiaoliang.spec
git commit -m "build(spec): 统一为 onefile 打包并显式收入 QtMultimedia/QtTextToSpeech" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 14: README 更新 + 全量回归收尾

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: 全部前序任务的最终行为
- Produces: v0.3 文档（功能、配置、验收清单、已知问题清理）

- [ ] **Step 1: README 更新**

1. **功能特性**节：追加 v0.3 条目——戳音效（目录式音效池）、屏幕穿越（无邻屏边缘、随机低概率）、久坐提醒（空闲检测 + 免打扰）、整点报时（防休眠误报）、开机自启（托盘开关）、多屏贴边裁剪修复；
2. **配置说明**节：补 `wrap_chance`、`sound.*`、`remind.*` 三组新键的取值与默认值（对照 Task 1 的 DEFAULT_CONFIG 逐项写）；音效替换指引链接 `assets/README.md`；
3. **手动验收**清单：把 spec §8 的 9 条按现有编号风格（26 起）追加；
4. **已知问题**节：删除已修复的 4 条（暂停戳、攀爬喂食、多屏溢出、暂停半空松手）；保留"爬墙/顶边被戳播地面姿势素材"一条并注明 remind 素材同理（正式素材阶段一并出）；新增一条："小凉活动范围仍为主屏工作区，拖拽/穿越不跨屏（跨屏重绑定列入路线图）"；
5. **路线图**节：追加候选——跨屏活动、正式立绘/音效素材、气泡对话（v0.3 brainstorming 中记录的未选方向）。

- [ ] **Step 2: 全量回归**

Run: `.venv\Scripts\python -m pytest tests/ -v`
Expected: 全部 PASS（预计 103 既有 + 约 45 新增 ≈ 148 个）

Run: `.venv\Scripts\python tools\check_sprites.py`
Expected: PASS

- [ ] **Step 3: Commit**

```powershell
git add README.md
git commit -m "docs(readme): v0.3 功能/配置/验收清单，清理已修复的已知问题" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

## 完工定义（DoD）

1. `feat/v0.3` 分支上 Task 1–14 全部提交，全量 pytest 绿；
2. `dist\xiaoliang.exe`（onefile）构建成功、体积 40–80MB；
3. 用户按 README 新验收清单（§8 的 9 条 + 既有 1–25 抽查）手动验收；
4. 验收问题走 fix 分支修复（沿用 v0.2 的 fix/v0.3-acceptance 模式）；
5. 合并 master → 用户打 tag `v0.3.0` + GitHub Release（资产 = onefile exe）；
6. 教学走读课（发布后安排，spec 执行模式 C）。
