# 小凉 🎸

一只 Windows 桌面像素宠物：蓝发小人在屏幕底部溜达、发呆，可以用鼠标把她
拎起来（会挣扎），松手会掉回地面。常驻系统托盘，随时暂停/退出。

<!-- TODO(发布前): docs/demo.gif 尚未录制；用 ScreenToGif 等工具录一段 20 秒演示存为 docs/demo.gif 后，在此处添加 "![demo](docs/demo.gif)" -->

## 功能（v0.1）

- 🚶 自主行为：待机 ↔ 随机溜达 ↔ 屏幕边缘折返
- 🖱️ 鼠标拖拽：抓住、挣扎、松手下落、落地回待机，下落中可再次抓住
- 🎛️ 系统托盘：暂停/恢复（双击图标同效）、退出
- ⚙️ 配置：`config.json`（exe/入口脚本同目录，首次运行自动生成默认值）

| 键 | 默认 | 说明 |
|----|------|------|
| `scale` | 2 | 像素放大倍数（整数） |
| `walk_speed` | 60.0 | 行走速度（逻辑像素/秒） |
| `paused` | false | 启动时是否暂停 |

## 运行

### 方式一：下载 exe（推荐）

从 [Releases](../../releases) 下载 `xiaoliang.exe`，双击运行。

### 方式二：源码运行

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

## 开发

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -v          # 单元测试（状态机/配置/素材逻辑）
.venv\Scripts\python tools\gen_placeholder_assets.py  # 重新生成占位素材
.venv\Scripts\python tools\check_sprites.py           # 素材加载冒烟检查
```

### 打包

```powershell
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name xiaoliang --add-data "assets;assets" main.py
```

产物：`dist\xiaoliang.exe`。

## 架构

状态机（纯逻辑，pytest 覆盖）与 GUI 分离，详见
[设计文档](docs/superpowers/specs/2026-09-21-xiaoliang-desktop-pet-design.md)。

## 手动验收清单

发布前逐项人工确认（规格 §6；GUI 层不做自动化测试）。

### 窗口与行为

1. 屏幕上出现无边框、背景透明的小人（只有像素角色本体，无白色底）
2. 小人不在任务栏占位
3. 待机时播放呼吸动画；几秒后自己开始走路，走路动画与移动方向一致（向左走时面朝左）
4. 走到工作区左右边缘会停下，之后回到待机
5. 鼠标左键能把她拎起来（切换挣扎动画），拖动跟手
6. 松手后下落，落地回到待机；下落过程中可以再次抓住

### 环境适配

7. 任务栏放在屏幕**顶部/左侧**时：小人仍贴工作区底部（不悬浮任务栏高度）、水平活动范围正确、拖拽钳制在工作区内
8. 双屏环境：仅在主屏工作区活动，副屏正常无异常
9. Windows 显示缩放 125% / 150% 下坐标无偏移（规格 §5 已知风险项）

### 托盘与配置

10. 托盘出现小凉图标；右键"暂停"→ 角色停在原地播待机动画、不再走动、菜单文字变"恢复"；右键"恢复"→ 行为恢复
11. **双击**托盘图标 = 暂停/恢复切换（单击不触发）；以 `paused=true` 启动时菜单初始即显示"恢复"且为勾选态
12. 右键"退出"：程序完全退出（任务管理器无残留进程）
13. 首次运行自动在 exe/入口脚本同目录生成默认 `config.json`（目录只读时不生成、仅记日志，启动不受影响）
14. 手写 `config.json` 为 `{"scale": 3, "walk_speed": 150, "paused": false}` 重启后角色变大、走得更快；删除后恢复默认；写非法值（如 `"scale": "3x"`）时该键回退默认并在 `%APPDATA%\xiaoliang\xiaoliang.log` 记警告
15. 错误处理：临时改名 `assets\idle.png` 后启动 → 弹出"素材加载失败"错误框而不是闪退，日志有记录；改回文件名

### exe 打包

16. `dist\xiaoliang.exe` 启动后行为与源码运行一致；托盘"退出"能完全结束进程；体积在预期 40~80MB 范围

### 发布前待办

- [ ] 用 AI 生成的正式"小凉"立绘替换程序占位素材（生成流程与提示词模板见 [assets/README.md](assets/README.md)，格式兼容可直接替换，替换后跑 `tools\check_sprites.py` 验证）
- [ ] 录制 `docs/demo.gif` 并取消 README 顶部图片行的注释

## 已知问题（v0.1）

- 暂停状态下把她拖到半空松手：角色会悬停在半空（渲染待机动画），恢复暂停后才落地——规格未定义的边缘情况，v0.2 处理。

## 路线图

- [x] v0.1 观赏型：走动、拖拽、托盘
- [ ] v0.2 玩具型：戳她会有反应、喂食、心情/饱腹度、晚上自动睡觉
- [ ] v0.3 伙伴型：久坐提醒、整点报时、开机自启、AI 聊天

## License

[MIT](LICENSE)
