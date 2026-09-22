# 小凉 v0.3 设计规格：声音互动、屏幕穿越、健康提醒与多屏修复

- 日期：2026-09-22
- 状态：待用户审阅
- 前序：v0.2 已发布（master @ 419856d，GitHub Release「小凉 v0.2.0」）
- 交付期限：**2026-09-25（中秋节）之前完成发布**
- 执行模式：**C——全代理执行**（brainstorming → spec → plan → Workflow 子代理驱动），完工后附**教学走读课**（逐模块讲解设计意图与实现，用户可提问；节后用户可选小模块练手重构）

## 0. 范围

**遗留修复（4）**

| # | 问题 | 来源 |
|---|------|------|
| ① | 暂停时戳/喂食仍改数值、播反应 | v0.2 已知问题（README） |
| ② | 攀爬中/坐顶时右键喂食无反应 | v0.2 已知问题 |
| ③ | 多显示器贴边溢出：推出 21 逻辑列的墨水（搁板端头/脚部碎片）画到相邻屏 | v0.2 已知问题（README） |
| ④ | 暂停中拖到半空松手 → 角色悬停半空 | v0.2 已知问题（README 标 v0.3 处理） |

**新功能（5）**

| # | 功能 | 决策记录 |
|---|------|---------|
| ⑤ | 戳她时语音（音效）互动 | 混合方案 C：戳=音效文件，提醒/报时=TTS；音效素材用户后续可替换 |
| ⑥ | 屏幕一端穿越到另一端（仅左右两侧） | 随机分流：IDLE 出门掷骰子三岔（攀爬/穿越/散步） |
| ⑦ | 久坐提醒 | 空闲检测（GetLastInputInfo）+ 免打扰 |
| ⑧ | 整点报时 | TTS + 防休眠误报 |
| ⑨ | 开机自启 | HKCU Run 注册表键，真相源=注册表 |

**明确不做**：AI 聊天（用户裁定太复杂）；跨屏活动范围（小凉继续只生活在主屏工作区，邻屏语义见 §4）；声音音量调节（只有开关，YAGNI）。

**顺手裁定**：`xiaoliang.spec` 从 onedir 统一为 **onefile**，与发布产物一致，`assets/sounds/` 加进 datas。

## 1. 状态机改动（state_machine.py）

保持"纯逻辑、不依赖 Qt、可单测"的现有原则；新参数全部走构造函数注入、带默认值，rng/clock 可注入。

### 1.1 修复①：暂停冻结事件

`poke()` 与 `feed()` 开头检查 `self.paused`：暂停时**事件完全无响应**（不播动画、不改数值、`feed()` 返回 False）。理由：暂停 = 整体冻结，半响应（播动画不改数值）造成"她动了但数值没变"的困惑。GUI 层被拒时无需提示（托盘已有暂停勾选态）。

### 1.2 修复②：攀爬中可喂食

`feed()` 接受状态扩展为：`IDLE / WALKING / SLEEPING / WOKEN / CLIMBING / SITTING_TOP`。在墙上/顶上接住食物 → 原地进入 EATING → 吃完转 FALLING 自然下落 → `_land()` 统一收口（沿用现有"跳下复用 FALLING"模式）。

### 1.3 修复④：暂停中半空松手落地

`drag_end()` 时若 `self.paused`：直接落到正下方地面（x 不变、y = floor_y），状态置 IDLE。暂停渲染本就播 idle 帧（规格 3.4），视觉上"被放下后乖乖站好"。非暂停路径行为不变（FALLING）。

### 1.4 新功能⑥：穿越（意图制，不加新状态枚举）

`_decide_walk_or_climb()` 掷骰子变三岔：

- 攀爬：`climb_chance`（默认 0.15 不变；心情差 ×0.3 不变）
- 穿越：`wrap_chance`（新参数，默认 0.08）——**仅当存在可穿越边缘时参与掷骰**，否则概率并入普通散步
- 普通散步：剩余概率

穿越意图 `_walk_intent = "wrap"`：

1. 选定一个可穿越边缘（注入的 `wrap_edges` 中随机；两侧都可穿越时 50/50），朝该方向走；
2. 到达边缘**不减速继续走出屏幕**：x 允许超出 `[0, bounds.width - pet_width]`，直到窗口整体没入（x ≤ -pet_width 或 x ≥ bounds.width）；
3. 瞬移到对端屏外（从左出 → 出现在 x = bounds.width 处，向左走回屏内；从右出 → 出现在 x = -pet_width 处，向右走回）；
4. 走回屏内后继续普通行走，剩余计时走完 → IDLE。

全程复用 WALKING 状态与现有走路帧。**穿越范围 = 当前屏幕（主屏工作区）两端**。

**可穿越边缘集合**由 GUI 注入（构造参数 `wrap_edges` + setter `set_wrap_edges()`，值为如 `{-1, 1}` / `{1}` / `set()`）：某侧边缘外有相邻屏幕 → 该侧不可穿越（走到该侧照旧停下发呆，观感上邻屏是"墙"，无邻屏的尽头才是"传送门"）；两侧都有邻屏 → 永不穿越。屏幕布局变化时 GUI 刷新注入。

### 1.5 新功能⑦⑧配套：REMINDING 状态

- 新增 `State.REMINDING` + 事件 API `remind() -> bool`；
- 复用 POKE_REACT 的恢复机制（`_pre_poke_state` / `_resume_timer` 同款）：播完回原状态并接续剩余计时；
- 拒绝条件（返回 False，零副作用）：`paused`，或状态在 `SLEEPING / WOKEN / DRAGGED / REMINDING`；免打扰的完整判定在提醒服务层（§3），此处是防御性兜底；
- 时长 `remind_secs`（新参数，默认 3.0 秒）；
- **被拒时语音照念**——提醒的使命是传达信息，动画只是锦上添花（接线见 §5）。

### 1.6 睡眠时段交互

REMINDING 与穿越不打断现有睡眠时段入口规则：`in_window` 时 REMINDING 播完自然回原状态（原状态若是 IDLE/WALKING 下一 tick 入睡）；穿越中的 WALKING 同样受睡眠统一入口管辖（进窗即 `_start_sleeping()`，穿越意图作废）。

## 2. 声音引擎（新模块 sound.py）

**职责边界**：只管"怎么发声、发不发得出去"；"什么时候该发声"归提醒服务（§3）。

**技术选型**（已验证当前 venv 可用，零新增 Python 依赖）：

- 音效：`PySide6.QtMultimedia.QSoundEffect`
- TTS：`PySide6.QtTextToSpeech.QTextToSpeech`（Windows 上走系统 SAPI 嗓音）

### 2.1 SoundEngine 类

两条独立通道：

- **音效通道**（戳她）：启动扫描 `assets/sounds/poke/` 目录加载全部 `.wav` 进音效池；`play_poke()` 随机挑一个播放。**目录为空/缺失 = 戳她静音，不报错**。用户丢新 wav 进目录即加音效、删文件即移除（零代码改动；打包态路径规则与现有 assets 一致，见 §6）。格式约定 wav（QSoundEffect 原生支持），替换规格写入 assets/README。
- **TTS 通道**（久坐提醒/整点报时）：优先选 zh-CN 嗓音，找不到用系统默认；`speak(text)` 用入队模式（QTextToSpeech 队列），连续两句不互相掐断。

### 2.2 开关模型

```json
"sound": { "muted": false, "poke_sfx": true, "sit_reminder": true, "hourly_chime": true }
```

- `muted` = 总开关，托盘菜单"静音"勾选项双向同步（点了立即生效并落盘）；
- 三个类别开关手改 config.json；
- 判定顺序：`muted` 一票否决 → 类别开关 → 发声。判定逻辑为纯函数（可单测）；
- **戳音效冷却 500ms**：连戳不机关枪（引擎内部管理）。

### 2.3 容错

初始化失败（无音频设备、Qt 插件缺失、注入冲突）→ 引擎降级为**静默空操作**：记日志，桌宠照常跑，绝不因声音崩溃。

### 2.4 线程模型

全部活在主 GUI 线程 Qt 事件循环（QSoundEffect/QTextToSpeech 均异步非阻塞），不引入新线程。

## 3. 提醒服务（新模块 reminder.py）

**职责**：决定"什么时候该提醒"，到点通过回调通知外界；自己不发声、不改状态机。

### 3.1 驱动与可测性

- 主线程低频 `QTimer` 心跳，每 **15 秒** tick 一次（整点报时最多晚 15 秒，可接受）；
- 核心逻辑为**纯方法** `tick(now, idle_secs)`：时钟与空闲时长外部注入，pytest 用假时钟测全部规则，不碰 Qt。

### 3.2 空闲检测

ctypes 调 `kernel32.GetLastInputInfo` + `GetTickCount`（标准库，无新依赖），算出键鼠已空闲秒数；封装为可注入 provider（测试换假数据）。

### 3.3 久坐提醒

- 心跳累加"连续在座时长"；空闲超过 `idle_threshold_minutes`（默认 5）→ 判定离开 → 计时清零；
- 连续在座满 `sit_minutes`（默认 45）→ 触发 → 计时清零重新数；
- 文案从内置池随机（模块常量，如"坐了 45 分钟啦，起来接杯水吧"）。

### 3.4 整点报时

- 记录上次见到的小时数，心跳发现**小时变了**就报时（"现在下午 3 点整"风格，模板池随机）；
- **防休眠误报**：两次心跳间真实时间跨度远超心跳间隔（如合盖唤醒）→ 只静默同步小时数、不补报；
- 文案池同上，模块常量。

### 3.5 免打扰统一闸（触发前逐项检查）

1. 暂停中（以 `machine.paused` 为准，config 仅初始值）→ 不提醒；
2. 小凉睡觉时段 → 复用现有纯函数 `in_sleep_window_minutes` + sleep_start/end 配置，久坐与整点都闭嘴；
3. 人不在（空闲超阈值）→ 不提醒。

### 3.6 配置

```json
"remind": { "sit_minutes": 45, "idle_threshold_minutes": 5 }
```

功能开关沿用 `sound.sit_reminder` / `sound.hourly_chime`——一个开关管住整个功能（语音+动画），不搞两套。

## 4. 屏幕信息与多屏修复（新模块 screen_info.py）

### 4.1 模块结构

薄 Qt 查询层 + 纯几何逻辑（矩形运算与 Qt 解耦，可单测）：

- `neighbor_edges(screen_geo, all_screen_geos) -> set[int]`：判断某屏左/右边缘外是否紧邻其他屏幕（虚拟桌面矩形相交检测，留 1px 容差）；
- 消费方：贴边渲染的 mask 决策（§4.2）、穿越可通行边缘注入（§1.4）。

### 4.2 修复③：setMask 裁剪贴边溢出

- `_cling_margin > 0` **且**贴边侧有相邻屏时：对窗口 `setMask()` 裁掉越界条带（宽度 = 推出量 × sprites.scale × devicePixelRatioF），视觉 = 在屏幕边界被"切齐"，手/后背仍搭在边缘；
- mask 只在贴边状态/方向**变化的瞬间**设置或 `clearMask()`，不是每帧操作；
- 单显示器或贴边侧无邻屏：完全不碰 mask，零开销、行为与 v0.2 一致。

### 4.3 活动范围不变

小凉继续只生活在**主屏工作区**（bounds 启动时绑定，不做跨屏重绑定——YAGNI，记 README 路线图）。"当前屏幕"即主屏。

## 5. 开机自启、托盘、配置与接线

### 5.1 开机自启（新模块 autostart.py，~40 行）

- 标准库 `winreg` 读写 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`（当前用户，无需管理员）；
- 值 = 带引号可执行路径：打包态 `sys.executable`；源码态 `pythonw.exe + main.py` 完整命令行；
- **真相源 = 注册表本身**，config.json 不存副本（用户可能在任务管理器"启动"页禁用，两份必漂移）；托盘勾选态启动时从注册表读；
- 注册表读写失败（组策略锁死等）→ 记日志、菜单项置灰，程序照常跑。

### 5.2 托盘菜单

```
暂停/恢复
静音          ← 新增 checkable，与 sound.muted 双向同步（同 pause 的 listener 模式）
开机自启      ← 新增 checkable，点击即写/删 Run 键
──────────
退出
```

右键上下文菜单（喂食/状态/暂停/退出）结构不变（`feed()` 内部已接受新状态）。

### 5.3 config.json 完整新形态

```json
{
  "scale": 2, "walk_speed": 60.0, "paused": false,
  "sleep_start": "23:00", "sleep_end": "07:00",
  "wrap_chance": 0.08,
  "sound": { "muted": false, "poke_sfx": true, "sit_reminder": true, "hourly_chime": true },
  "remind": { "sit_minutes": 45, "idle_threshold_minutes": 5 }
}
```

走现有 `needs_migration` 补全机制：v0.2 老配置启动时自动补全新键并回写，原有合法值保留，非法值回退默认。

### 5.4 main.py / pet_window.py 接线

- 启动创建 `SoundEngine(cfg)`、`ReminderService`（15s 心跳，注入时钟 + 空闲 provider + 免打扰查询）；
- 提醒回调 → `machine.remind()`（动画，被拒拉倒）+ `sound.speak(文案)`（照念）；
- pet_window 戳判定命中处 → `sound.play_poke()`（开关与冷却由引擎内部管）；
- `screen_info.neighbor_edges()` 结果 → `machine.set_wrap_edges()`；监听 `QGuiApplication.screenAdded / screenRemoved` 刷新；
- pet_window：`REMINDING` 补进 `STATE_ACTION`（"remind"）与 `STATE_ZH`（"伸懒腰"，与占位素材动作一致）映射；贴边 mask 逻辑（§4.2）。

## 6. 资产与打包

- `assets/remind.png` + manifest 条目：提醒动作（伸懒腰/举小牌），代理按现有像素风格生成占位帧，跑 `tools/check_sprites.py` 验证；
- `assets/sounds/poke/*.wav`：代理合成 2–3 个占位音效（简单波形）；目录式加载支持用户随时替换真素材；
- `assets/README.md` 更新：音频规格（wav、采样率、命名、替换步骤）与新动画帧规格；
- `xiaoliang.spec`：改 **onefile**，datas 加 `assets/sounds/`；确认 QtMultimedia / QtTextToSpeech 插件被 PyInstaller hooks 收进（必要时 hiddenimports）；体积目标仍在 40–80MB。

## 7. 测试策略

延续纯逻辑 pytest 风格：现有 103 个全保，新增约 60–80 个。

| 模块 | 覆盖 | 隔离手段 |
|------|------|---------|
| state_machine | 暂停时 poke/feed 零副作用；攀爬/坐顶喂食→EATING→FALLING→落地；暂停中松手落地；三岔骰子；穿越全周期（走出→瞬移→走回）；wrap_edges 为空/单侧；remind() 接受/拒绝与恢复接续 | 注入 rng/clock（现有模式） |
| reminder | 久坐累计/空闲清零/到点触发/触发后重计；整点跨小时；大跳变不补报；免打扰三闸 | `tick(now, idle_secs)` 纯方法 + 假时钟 |
| sound | 开关判定顺序；音效池随机；500ms 冷却 | 假播放器注入，不碰真实音频 |
| screen_info | 邻屏检测：左邻/右邻/双邻/无邻/不同分辨率/1px 容差 | 纯几何函数 |
| autostart | 命令行构造（打包态/源码态） | winreg 打桩 |
| config | v0.2 旧配置迁移补全；非法值回退 | 临时目录文件（现有模式） |

## 8. GUI 手动验收清单（写进 README，用户执行）

1. 戳她 → 音效；连戳 → 冷却生效；托盘"静音" → 全静（含 TTS）
2. 攀爬中/坐顶右键喂食 → 接住吃 → 吃完落下落地
3. 暂停中戳/喂食 → 完全无响应；暂停中拖到半空松手 → 落地站好
4. 多显示器贴边 → 邻屏边缘干净无墨水（setMask 生效）；单显示器行为不变
5. 穿越：临时 `wrap_chance` 改 1.0 → 走到无遮挡边缘穿出、对端走进；有邻屏侧不穿越
6. 久坐提醒：`sit_minutes` 改 1 验证触发（语音 + 伸懒腰动画）；离开超阈值回来 → 计时清零；睡觉时段/暂停/人不在 → 不触发
7. 整点报时：等整点或改系统时间验证；合盖唤醒不连环补报
8. 托盘"开机自启"勾选 → 注册表 Run 键出现 →（可选）重启验证自启
9. onefile spec 打包 → exe 行为与源码一致、体积 40–80MB、`assets/sounds/` 已收入

## 9. 发布与日程

- **22 晚**：spec 审阅通过 → writing-plans → 代理开始实现（我的全部模块 + 测试 + 占位素材）
- **23**：代理完成实现与自测；用户碎片时间抽查
- **24 晚**：GUI 验收清单 + 修 bug + onefile 打包
- **25 白天前**：master 打 tag `v0.3.0` + GitHub Release（onefile exe）→ 教学走读课（可安排在发布后/节后）

## 10. 编码规范（常设）

所有代码加必要中文注释：模块/函数 docstring + 关键逻辑行内注释，解释"为什么"。
