# 小凉（XiaoLiang）桌面宠物 — 设计文档

日期：2026-09-21
状态：已与用户对齐，待实现

## 1. 项目概述

"小凉"是一只运行在 Windows 桌面上的像素风桌面宠物：一个原创的蓝发动漫气质像素小人（慵懒、抱贝斯），平时在屏幕底部溜达、发呆，可以被鼠标拖拽，后续版本加入互动与陪伴功能。

**目标：**

- 主要目标：兴趣驱动，完整体验"用 AI 工具做出一个具体产品"的全流程（设计 → 开发 → 素材 → 发布 GitHub）
- 次要目标：练 Python 工程能力（GUI、状态机、多线程/定时器、单元测试、打包发布）

**非目标（明确不做）：**

- 不使用受版权保护的动漫角色素材（角色为原创，仅"气质神似"）
- v0.1 不做互动数值系统（心情/饱腹度）、不做提醒功能、不做 AI 聊天
- 不做跨平台适配（仅 Windows；PySide6 本身跨平台，但不为 macOS/Linux 做专门测试）

## 2. 版本路线

| 版本 | 主题 | 内容 |
|------|------|------|
| v0.1（MVP） | 观赏型 | 透明置顶窗口、像素角色显示、待机/溜达/发呆行为、鼠标拖拽、系统托盘 |
| v0.2 | 玩具型 | 戳它有反应、喂食、心情/饱腹度数值、晚上自动睡觉 |
| v0.3 | 伙伴型 | 久坐提醒、整点报时、开机自启、（可选）接 LLM AI 聊天 |

每个版本独立走完"设计 → 实现 → 发布"闭环。本文档只详细定义 v0.1，v0.2/v0.3 届时单独出设计文档。

## 3. v0.1（MVP）功能规格

### 3.1 角色与素材

- 像素风，单帧画布 64×64（显示时可整数倍放大，默认 2 倍 = 128×128 屏幕像素）
- 素材为 PNG sprite sheet（横向排列帧，透明背景），v0.1 需要 5 组动作：
  - `idle`（待机，含呼吸感，4 帧）
  - `walk_left` / `walk_right`（走路，各 6 帧）
  - `dragged`（被拎起，挣扎/悬空，2 帧）
  - `falling`（松手后下落，2 帧）
- 素材由 AI 工具生成（生成流程与提示词记录在 `assets/README.md`，保证可复现、可重绘）
- 素材目录结构：`assets/<action>.png` + `assets/manifest.json`（记录每个动作的帧数、帧尺寸、帧率）

### 3.2 窗口

- 无边框（`FramelessWindowHint`）、背景透明（`WA_TranslucentBackground`）、始终置顶（`WindowStaysOnTopHint`）
- 不在任务栏显示（`Tool` 窗口类型）
- 窗口大小 = 角色显示大小，跟随角色位置移动

### 3.3 行为（状态机）

v0.1 状态与转换：

```
IDLE ──(随机计时到)──> WALKING ──(随机计时到/到达屏幕边缘)──> IDLE
IDLE/WALKING ──(鼠标按下并拖动)──> DRAGGED
DRAGGED ──(鼠标松开)──> FALLING
FALLING ──(到达屏幕底部)──> IDLE
```

- IDLE：播放 idle 动画；停留 2~8 秒（随机）后转 WALKING
- WALKING：沿屏幕底部水平移动（速度可配置，默认约 60 px/s），随机选择方向；走 3~10 秒（随机）或碰到工作区边缘后转 IDLE
- DRAGGED：跟随鼠标，播放 dragged 动画
- FALLING：以恒定加速度下落（简单重力模拟），落地后转 IDLE
- 活动范围为**主显示器工作区**（不含任务栏遮挡区域）；多显示器 v0.1 只支持主屏

### 3.4 系统托盘

- 托盘图标菜单：暂停/恢复（暂停时角色停在原地播 idle）、退出
- 双击托盘图标 = 暂停/恢复

### 3.5 配置

`config.json`（首次运行自动生成默认值，与 exe/入口脚本同目录）：

```json
{
  "scale": 2,
  "walk_speed": 60,
  "paused": false
}
```

### 3.6 打包发布

- 用 PyInstaller 打包为单 exe（`dist/xiaoliang.exe`），让非 Python 用户也能跑
- GitHub 仓库：`xiaoliang`，README 含 GIF 演示、功能说明、下载链接（Releases 挂 exe）
- 许可证：MIT

## 4. 架构

```
xiaoliang/
├── main.py              程序入口（创建 QApplication、装配各组件）
├── xiaoliang/
│   ├── pet_window.py    透明置顶窗口：渲染当前帧、处理鼠标事件
│   ├── state_machine.py 纯逻辑状态机：状态、转换、tick 更新（不依赖 Qt widgets）
│   ├── sprite.py        SpriteManager：按 manifest.json 加载素材表、切帧、动画计时
│   ├── tray.py          系统托盘图标与菜单
│   └── config.py        配置读写（config.json）
├── assets/              PNG 素材表 + manifest.json + README.md（生成流程记录）
├── tests/               pytest 单元测试（重点覆盖 state_machine）
├── requirements.txt     PySide6
├── README.md
└── .gitignore
```

**核心设计原则：状态机与 GUI 分离。**

- `state_machine.py` 不 import 任何 Qt widget：输入是事件（`drag_start`、`drag_move`、`drag_end`、`tick(dt)`）与屏幕边界，输出是新状态与角色坐标。可用 pytest 纯逻辑测试
- `pet_window.py` 只做两件事：每个渲染 tick 向状态机要"当前状态 + 位置"并画对应帧；把鼠标事件翻译成状态机事件
- 动画帧选择：`sprite.py` 提供 `get_frame(state, elapsed_ms) -> QPixmap`，帧率来自 manifest
- 主循环用单个 `QTimer`（约 30 FPS）驱动状态机 tick 与重绘；v0.1 无需多线程

**数据流：**

```
鼠标事件 → pet_window → state_machine(事件)
QTimer(30fps) → state_machine.tick(dt) → (state, x, y)
                → pet_window 移动窗口 + sprite.get_frame(state) 绘制
```

## 5. 错误处理

- 素材缺失/manifest 与 PNG 不符：启动时报清晰错误信息并弹窗提示，不静默崩溃
- config.json 损坏：回退默认配置并在日志中警告
- 高 DPI 缩放：以逻辑像素计算坐标（Qt 默认处理），素材整数倍放大避免模糊；已知风险——Windows 显示缩放 125%/150% 时需实测，若有坐标偏移在 v0.1.x 修复
- 日志：`logging` 输出到 `%APPDATA%/xiaoliang/xiaoliang.log`（打包后用户目录可写）

## 6. 测试策略

- **单元测试（pytest）**：状态机全部转换路径（IDLE↔WALKING、拖拽、下落落地、边缘折返）、config 加载/回退、sprite 帧选择逻辑（mock 图像加载）
- **手动验收清单**（记录在 README）：窗口透明无边框、拖拽跟手、落地回待机、托盘暂停/退出、双屏环境下主屏正常
- GUI 层（pet_window/tray）不做自动化测试——MVP 阶段收益低

## 7. 开发节奏（参考）

每晚 1~2 小时，预计 1~2 周完成 v0.1：

1. 项目脚手架 + 透明窗口显示一张静态像素图（"它站住了"）
2. 素材生成（AI 出图 + 切表 + manifest）
3. sprite 动画 + IDLE/WALKING 状态机
4. 拖拽 + 下落
5. 托盘 + 配置 + 测试补齐
6. 打包 exe + README + 发布 GitHub

## 8. 已知风险

- **AI 素材一致性**：同一角色多动作多帧的风格一致性是最大不确定项。缓解：先生成单帧定稿角色形象，再基于它扩展动作；不行就退化为"少帧数 + 简单动作"（像素风容错高）
- Qt 透明窗口在个别显卡驱动下可能有渲染问题：遇到时记录到 README 已知问题
- PyInstaller 打包 PySide6 体积较大（约 40~80MB）：可接受，或后续用 UPX 压缩
