# 小凉（XiaoLiang）桌面宠物 v0.2（玩具型）— 设计文档

日期：2026-09-21
状态：已与用户对齐，待实现
基线：v0.1（master @ acbc807，已发布 GitHub）

## 1. 版本定位

v0.2 在 v0.1（观赏型：显示/溜达/拖拽/托盘）之上加入**玩具型**能力：戳它有反应、右键喂食、心情/饱腹度数值、晚上定时睡觉、爬屏幕边缘到顶边坐下发呆。

架构决策（已对齐）：**扩展现有单一状态机**（方案 A），不引入双层状态机/行为树。数值系统独立为纯逻辑模块 `status.py`。沿用 v0.1 的核心原则：状态机与数值模块不 import 任何 Qt widget，依赖注入（RNG、时钟），pytest 纯逻辑可测。

**编码规范（用户要求）**：所有新写/修改的代码必须加入必要的中文注释——模块级 docstring 说明职责，类/函数 docstring 说明用途与参数，关键逻辑（状态转换、数值公式、边界处理、注入点）配行内中文注释。注释解释"为什么"，不复述代码。

## 2. 功能规格

### 2.1 数值系统（`xiaoliang/status.py`，新模块，纯逻辑）

两项数值，均为 float，钳制在 [0, 100]，初始 80.0：

- **心情 mood**、**饱腹度 fullness**

**衰减速率（每分钟）**：

| 条件 | fullness | mood |
|------|----------|------|
| 清醒 | -0.5 | -0.3；若 fullness < 20 则 ×3（即 -0.9） |
| 睡觉（SLEEPING） | -0.25 | **+1.0（回升）** |

实现为 `PetStatus.tick(dt_seconds, sleeping: bool)`，内部按 秒速率 = 分钟速率 / 60 计算。

**喂食 `feed()`**：fullness +25、mood +5（各自钳到 100）。**fullness > 90 时拒绝**（返回 False，GUI 菜单置灰）；fullness ≤ 90 允许。

**戳 `poke()`**：mood +3，**冷却 10.0 秒**（冷却中返回 False：动画照播，数值不加）。

**低数值行为修正**（由状态机读取）：

- fullness < 20 → 走路速度 ×0.6（蔫了）
- mood < 20 → 攀爬触发概率 ×0.3（没心情玩），发呆概率相应升高

**持久化 `status.json`**（与 config.json 同目录，gitignore）：

```json
{"mood": 80.0, "fullness": 80.0}
```

- 保存时机：每 60 秒 + 喂食/戳/退出时；保存失败（只读目录等）仅日志警告，不崩溃
- 启动加载：恢复数值，**不按离线时长补算衰减**（离线冻结）
- 文件损坏/字段缺失/类型错误 → 回退默认 80.0/80.0 并日志警告（复用 v0.1 config 的回退风格）

### 2.2 状态机扩展（`xiaoliang/state_machine.py`）

新增 6 个状态：`POKE_REACT`、`EATING`、`SLEEPING`、`WOKEN`、`CLIMBING`、`SITTING_TOP`（CLIMBING 用 `climb_direction ∈ {up, down}` 区分上下，共用动作素材：向下 = 帧序列倒放）。

新事件 API：`poke()`、`feed()`；构造注入：`status: PetStatus`、`clock`（默认取系统时间，测试注入 FakeClock）、`sleep_start/sleep_end`（"HH:MM" 字符串）。

**睡眠时段**：`in_sleep_window(now)` 支持跨午夜（start > end 时窗口为 [start, 24:00) ∪ [0:00, end)），半开区间。

**转换表（新增/修改部分）**：

```
IDLE/WALKING ──(时钟进入睡眠时段)──> SLEEPING
CLIMBING/SITTING_TOP ──(时钟进入睡眠时段)──> 立即转 CLIMBING(down)，到底后 SLEEPING
SLEEPING ──(时钟离开睡眠时段)──> IDLE
SLEEPING ──(poke)──> WOKEN ──(uniform(3,6)s)──> 仍在时段? SLEEPING : IDLE
SLEEPING ──(feed)──> EATING（吃完仍在时段 → SLEEPING，否则 → IDLE）
IDLE/WALKING ──(poke)──> POKE_REACT ──(1.0s)──> 回戳之前的状态（记住 _pre_poke_state）
IDLE/WALKING ──(feed)──> EATING ──(2.0s)──> IDLE
CLIMBING/SITTING_TOP ──(poke)──> POKE_REACT（原地播完 1.0s）──> 回爬/坐状态
IDLE（决定开始走动时）──(random() < 0.15；mood < 20 时概率 ×0.3 即 0.045)──> 走向最近的左/右工作区边缘 ──> CLIMBING(up)
CLIMBING(up) ──(y 到达 0，速度 40 px/s)──> SITTING_TOP ──(uniform(10,30)s)──> 50% CLIMBING(down)→到底→IDLE / 50% 跳下→FALLING（复用 v0.1）
CLIMBING/SITTING_TOP ──(拖拽)──> DRAGGED ──(松开)──> FALLING ──(落地)──> 时段内? SLEEPING : IDLE
任意状态 ──(paused)──> 全冻结（含 status.tick，沿用 v0.1 语义）
```

- 睡眠时段内不发生新的走动/攀爬决策；SLEEPING 原地播放睡觉动画（不移动）
- 低数值修正在 tick 中生效：fullness < 20 时 WALKING 速度 ×0.6；mood < 20 时攀爬概率 0.15 → 0.045
- 戳的判定入口：`poke()` 在 DRAGGED 状态被调用且拖拽未产生有效位移时，回退到拖拽前状态并进 POKE_REACT（GUI 层配合，见 2.3）

### 2.3 GUI 交互（`xiaoliang/pet_window.py` 扩展）

- **戳 vs 拖拽**：mousePress 记录时间与位置（并照旧 `drag_start()`）；移动超过 5px 标记为有效拖拽；mouseRelease 时若**未发生有效拖拽、按压时长 < 250ms** → 判定为戳，调 `machine.poke()`（不调 `drag_end()`）；否则走 v0.1 的 `drag_end()`
- **右键菜单（QMenu）**：喂食（fullness > 90 时置灰，文本"喂食（吃撑了）"）/ 状态（disabled 项，动态文本"心情 80 · 饱腹 45"，每次打开菜单刷新）/ 暂停·恢复 / 退出
- **悬停 tooltip**：每秒刷新，格式 `心情 😊{mood:.0f} · 饱腹 🍚{fullness:.0f} · {当前状态中文}`（状态中文名映射：发呆/溜达/爬墙/顶上坐着/睡觉/被拎着/下落中/吃东西/睡眼惺忪/被戳了）

### 2.4 素材（扩展 `tools/gen_placeholder_assets.py` 与 `assets/manifest.json`）

6 组新动作（64×64 帧，横向 PNG strip，透明背景，占位像素风；AI 换图流程与提示词模板沿用 `assets/README.md`）：

| action | 帧数 | fps | 说明 |
|--------|------|-----|------|
| `poke_react` | 2 | 6 | 惊讶表情（头顶"!"） |
| `eating` | 4 | 6 | 捧碗咀嚼 |
| `sleeping` | 2 | 2 | 躺姿 + zzz 气泡交替 |
| `woken` | 2 | 3 | 揉眼半睁 |
| `climbing` | 4 | 8 | 侧面贴墙向上爬（向下=倒放，左壁=镜像） |
| `sitting_top` | 4 | 3 | 顶边坐姿晃腿 |

SpriteManager / check_sprites.py 为 manifest 驱动，新动作**加载**零配置自动兼容；唯一代码改动是 `SpriteManager.get_frame` 增加 `reverse`（爬下倒放帧序）与 `mirror`（左壁水平镜像）两个关键字参数（向后兼容，默认 False）。

### 2.5 配置扩展（`xiaoliang/config.py`）

`DEFAULT_CONFIG` 新增：

```json
{"sleep_start": "23:00", "sleep_end": "07:00"}
```

校验（复用 v0.1 逐键校验/强制转换机制）：字符串且匹配 `^([01]\d|2[0-3]):[0-5]\d$`，非法 → 回退默认并日志警告。

## 3. 架构变更总览

```
xiaoliang/
├── status.py          【新】纯逻辑数值系统：PetStatus（tick/feed/poke/load/save）
├── state_machine.py   【扩展】+6 状态、poke/feed 事件、clock/status/sleep 注入、攀爬坐标逻辑
├── pet_window.py      【扩展】戳/拖拽判定、右键 QMenu、动态 tooltip
├── config.py          【扩展】sleep_start/sleep_end 默认与校验
├── main.py            【扩展】装配 PetStatus（加载/定时保存/退出保存）、传入状态机与窗口
├── sprite.py          【微扩展】get_frame 增加 reverse/mirror 关键字参数
├── tray.py            【微扩展】监听状态机暂停回调，与右键菜单双向同步勾选/文字
tests/
├── test_status.py     【新】
└── test_state_machine.py 【扩展】新状态全路径
tools/gen_placeholder_assets.py 【扩展】6 组新素材
```

依赖方向不变：main → (pet_window, tray, state_machine, sprite, config, status)；state_machine → status（单向）；两者均不 import Qt widgets。

## 4. 错误处理

- `status.json` 损坏/缺失/类型错 → 默认 80.0/80.0 + 日志警告；保存失败（OSError）→ 日志警告不崩溃
- `sleep_start/sleep_end` 非法格式 → 回退默认 + 日志警告
- 素材/manifest 不符 → 沿用 v0.1（AssetError 弹窗）
- 攀爬/顶边坐标越界 → 钳制在工作区内（沿用 v0.1 边界钳制）

## 5. 测试策略

**纯逻辑单测（pytest，FakeClock/FakeRandom 注入）**，关键用例：

- status：衰减速率（清醒/饥饿加速/睡觉回升与减半）、钳制、喂食（+25/+5、>90 拒绝、=90 允许）、戳冷却（10s 内 False、数值不加）、save/load round-trip、损坏回退
- 状态机：跨午夜时段进入/离开、SLEEPING→poke→WOKEN→回睡、时段内喂食→EATING→回睡、POKE_REACT 回原状态（地面/墙上两种）、攀爬触发概率受 mood 修正、CLIMBING(up)→SITTING_TOP→跳下(FALLING)/爬下 两出口、攀爬中进时段→爬下→SLEEPING、fullness<20 走路减速、暂停冻结数值、DRAGGED 无位移戳判定回退

**GUI 手动验收清单**（写入 README）：戳/拖拽互不干扰、右键菜单四项行为、吃撑置灰、tooltip 刷新、23:00 后（或改配置立即验证）入睡、睡觉戳醒再睡、爬边坐顶跳下、低饱腹度走路变慢、重启数值恢复。

GUI 层不做自动化测试（沿用 v0.1 裁定）。

## 6. 里程碑

1. **M1** status.py + 单测（数值系统独立可测）
2. **M2** 状态机：睡觉/戳/吃 三组状态 + 单测
3. **M3** 状态机：攀爬/顶边坐 + 单测
4. **M4** 素材：6 组新占位动作 + manifest + check_sprites 通过
5. **M5** GUI 集成：戳判定/右键菜单/tooltip + config 扩展 + main 装配 + status.json 持久化
6. **M6** README（新验收清单+已知问题更新）+ 重新打包 exe + 发布 v0.2.0

## 7. 已知风险

- **占位素材表现力**：睡觉/攀爬姿势用简单像素块表达，观感有限——与 v0.1 相同，AI 换图流程兜底
- **状态机复杂度**：转换表从 5 状态涨到 11 状态，靠"单文件集中 + 全路径单测"控制；v0.3 若再翻倍则重估分层方案
- **POKE_REACT 在墙上播放**：反应素材是地面姿势，贴墙播放略违和——占位阶段可接受，AI 素材阶段可为 climbing 单独出被戳帧（记录到 assets/README.md 待办）
- **跨午夜时段边界**：23:59→00:00 跳变、start==end 视为不睡觉（校验时若相等回退默认）——单测覆盖

## 8. 非目标（YAGNI，留 v0.3+）

- 顶边行走（坐在固定点，不沿顶边移动）
- 戳太多会生气、过食惩罚
- 离线按真实时间衰减
- 音效、多显示器、exe 瘦身（UPX）
