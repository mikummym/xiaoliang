# 小凉 🎸

一只 Windows 桌面像素宠物：蓝发小人在屏幕底部溜达、发呆，可以用鼠标把她
拎起来（会挣扎），松手会掉回地面。常驻系统托盘，随时暂停/退出。

<!-- TODO(发布前): docs/demo.gif 尚未录制；用 ScreenToGif 等工具录一段 20 秒演示存为 docs/demo.gif 后，在此处添加 "![demo](docs/demo.gif)" -->

## 功能（v0.1）

- 🚶 自主行为：待机 ↔ 随机溜达 ↔ 屏幕边缘折返
- 🖱️ 鼠标拖拽：抓住、挣扎、松手下落、落地回待机，下落中可再次抓住
- 🎛️ 系统托盘：暂停/恢复（双击图标同效）、退出
- ⚙️ 配置：`config.json`（exe 同目录，首次运行自动按默认值工作）

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

## 路线图

- [x] v0.1 观赏型：走动、拖拽、托盘
- [ ] v0.2 玩具型：戳她会有反应、喂食、心情/饱腹度、晚上自动睡觉
- [ ] v0.3 伙伴型：久坐提醒、整点报时、开机自启、AI 聊天

## License

[MIT](LICENSE)
