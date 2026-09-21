# 小凉桌面宠物 v0.1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现"小凉"桌面宠物 v0.1（MVP）：一只像素小人在屏幕底部溜达/发呆，可拖拽、会下落，带系统托盘，最终打包为单 exe。

**Architecture:** PySide6 透明置顶无边框窗口显示像素动画；核心行为是纯逻辑状态机（IDLE/WALKING/DRAGGED/FALLING），不依赖 Qt widgets，用 pytest 覆盖；素材为横向 sprite sheet PNG + manifest.json 描述；单个 30 FPS QTimer 驱动状态机 tick 与重绘。

**Tech Stack:** Python 3.10+、PySide6、pytest、Pillow（仅占位素材生成脚本用）、PyInstaller。

**Spec:** `docs/superpowers/specs/2026-09-21-xiaoliang-desktop-pet-design.md`

## Global Constraints

- 工作目录：`D:\projects\xiaoliang`，所有命令在此目录执行（PowerShell）
- Python 命令一律用虚拟环境解释器：`.venv\Scripts\python`
- 仅支持 Windows + 主显示器工作区；坐标为 Qt 逻辑像素
- 素材帧画布 64×64，默认整数倍放大 scale=2；动画用最近邻缩放（FastTransformation）保持像素锐利
- 状态机模块（`state_machine.py`）禁止 import 任何 Qt 模块
- 所有 git commit message 末尾附一行：`Co-Authored-By: Claude Code <noreply@anthropic.com>`（用第二个 `-m` 传入）
- 每个任务结束必须 commit；测试命令统一 `python -m pytest`（从项目根运行，保证包可导入）

## 文件结构总览

```
D:\projects\xiaoliang\
├── main.py                      入口（Task 7 创建最小版，Task 8 完善）
├── xiaoliang\
│   ├── __init__.py              空文件
│   ├── config.py                配置读写（Task 1）
│   ├── sprite.py                素材加载/帧管理（Task 2 纯逻辑 + Task 4 Qt 加载）
│   ├── state_machine.py         行为状态机（Task 5-6）
│   ├── pet_window.py            透明窗口/渲染/鼠标（Task 7）
│   └── tray.py                  系统托盘（Task 8）
├── tools\
│   ├── gen_placeholder_assets.py  占位素材生成（Task 3）
│   └── check_sprites.py           素材加载冒烟检查（Task 4）
├── assets\                      素材表 + manifest.json + README.md（Task 3）
├── tests\
│   ├── test_config.py           Task 1
│   ├── test_sprite_logic.py     Task 2
│   └── test_state_machine.py    Task 5-6
├── requirements.txt / requirements-dev.txt / pytest.ini / .gitignore   Task 1
├── README.md / LICENSE          Task 9
└── docs\superpowers\…           已有设计文档
```

---

### Task 1: 项目脚手架与配置模块

**Files:**
- Create: `.gitignore`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `xiaoliang\__init__.py`, `xiaoliang\config.py`
- Test: `tests\test_config.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: `DEFAULT_CONFIG: dict`（键 `scale:int=2, walk_speed:float=60.0, paused:bool=False`）、`default_config_path() -> Path`、`load_config(path: Path) -> dict`、`save_config(cfg: dict, path: Path) -> None`

- [ ] **Step 1: 创建脚手架文件**

`.gitignore`：

```
.venv/
__pycache__/
*.pyc
build/
dist/
config.json
*.log
```

`requirements.txt`：

```
PySide6>=6.6
```

`requirements-dev.txt`：

```
-r requirements.txt
pytest>=8.0
pillow>=10.0
pyinstaller>=6.0
```

`pytest.ini`：

```ini
[pytest]
testpaths = tests
```

`xiaoliang\__init__.py`：空文件。

- [ ] **Step 2: 创建虚拟环境并安装依赖**

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

预期：安装成功，无报错。

- [ ] **Step 3: 写失败的测试 `tests\test_config.py`**

```python
import json

from xiaoliang.config import DEFAULT_CONFIG, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg == DEFAULT_CONFIG


def test_corrupt_file_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert load_config(p) == DEFAULT_CONFIG


def test_non_dict_json_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_config(p) == DEFAULT_CONFIG


def test_merges_known_keys_and_ignores_unknown(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"scale": 3, "unknown_key": 1}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["scale"] == 3
    assert cfg["walk_speed"] == DEFAULT_CONFIG["walk_speed"]
    assert "unknown_key" not in cfg


def test_save_then_load_roundtrip(tmp_path):
    p = tmp_path / "config.json"
    save_config({"scale": 4, "walk_speed": 120.0, "paused": True}, p)
    assert load_config(p) == {"scale": 4, "walk_speed": 120.0, "paused": True}
```

- [ ] **Step 4: 运行测试确认失败**

```powershell
.venv\Scripts\python -m pytest tests\test_config.py -v
```

预期：FAIL/ERROR，`ModuleNotFoundError: No module named 'xiaoliang.config'`。

- [ ] **Step 5: 实现 `xiaoliang\config.py`**

```python
"""配置读写：config.json 加载/保存，缺失或损坏时回退默认值。"""
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "scale": 2,
    "walk_speed": 60.0,
    "paused": False,
}


def default_config_path() -> Path:
    """config.json 位置：打包后与 exe 同目录，源码运行时在项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"


def load_config(path: Path) -> dict:
    """加载配置；文件不存在/损坏时返回默认配置，只保留已知键。"""
    cfg = dict(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("配置文件 %s 读取失败，使用默认配置: %s", path, exc)
        return cfg
    if not isinstance(data, dict):
        logger.warning("配置文件 %s 不是 JSON 对象，使用默认配置", path)
        return cfg
    for key in DEFAULT_CONFIG:
        if key in data:
            cfg[key] = data[key]
    return cfg


def save_config(cfg: dict, path: Path) -> None:
    """把配置写为 UTF-8 JSON。"""
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 6: 运行测试确认通过**

```powershell
.venv\Scripts\python -m pytest tests\test_config.py -v
```

预期：5 passed。

- [ ] **Step 7: Commit**

```powershell
git add .gitignore requirements.txt requirements-dev.txt pytest.ini xiaoliang tests
git commit -m "feat: 项目脚手架与配置模块" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 2: sprite 纯逻辑（manifest 解析 + 帧索引）

**Files:**
- Create: `xiaoliang\sprite.py`（本任务只写纯逻辑部分；Task 4 追加 SpriteManager）
- Test: `tests\test_sprite_logic.py`

**Interfaces:**
- Consumes: 无
- Produces: `AssetError(Exception)`、`parse_manifest(data: dict) -> dict`（校验失败抛 AssetError）、`frame_index(elapsed_ms: int, fps: float, frame_count: int) -> int`

- [ ] **Step 1: 写失败的测试 `tests\test_sprite_logic.py`**

```python
import pytest

from xiaoliang.sprite import AssetError, frame_index, parse_manifest

VALID_MANIFEST = {
    "frame_size": [64, 64],
    "actions": {
        "idle": {"file": "idle.png", "frames": 4, "fps": 3},
        "walk_left": {"file": "walk_left.png", "frames": 6, "fps": 8},
    },
}


def test_frame_index_cycles():
    assert frame_index(0, 4, 4) == 0
    assert frame_index(250, 4, 4) == 1
    assert frame_index(1000, 4, 4) == 0  # 4fps → 1 秒后回到第 0 帧


def test_frame_index_negative_elapsed_treated_as_zero():
    assert frame_index(-100, 4, 4) == 0


def test_frame_index_zero_count_raises():
    with pytest.raises(AssetError):
        frame_index(0, 4, 0)


def test_parse_manifest_accepts_valid():
    assert parse_manifest(VALID_MANIFEST) == VALID_MANIFEST


def test_parse_manifest_rejects_bad_frame_size():
    with pytest.raises(AssetError):
        parse_manifest({"frame_size": [64], "actions": VALID_MANIFEST["actions"]})


def test_parse_manifest_rejects_missing_action_field():
    bad = {"frame_size": [64, 64],
           "actions": {"idle": {"file": "i.png", "frames": 4}}}  # 缺 fps
    with pytest.raises(AssetError):
        parse_manifest(bad)


def test_parse_manifest_rejects_empty_actions():
    with pytest.raises(AssetError):
        parse_manifest({"frame_size": [64, 64], "actions": {}})
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.venv\Scripts\python -m pytest tests\test_sprite_logic.py -v
```

预期：ERROR，`No module named 'xiaoliang.sprite'`。

- [ ] **Step 3: 实现 `xiaoliang\sprite.py`（纯逻辑部分）**

```python
"""素材加载与动画帧管理。

纯逻辑部分（parse_manifest / frame_index）不依赖 Qt 对象，可单元测试；
SpriteManager（Task 4 追加）依赖 Qt，需在 QApplication 下使用。
"""
import json


class AssetError(Exception):
    """素材缺失或 manifest 格式错误。"""


def parse_manifest(data: dict) -> dict:
    """校验并返回 manifest。格式错误抛 AssetError。"""
    frame_size = data.get("frame_size")
    if (not isinstance(frame_size, list) or len(frame_size) != 2
            or not all(isinstance(v, int) and v > 0 for v in frame_size)):
        raise AssetError(f"manifest.frame_size 必须是两个正整数: {frame_size!r}")
    actions = data.get("actions")
    if not isinstance(actions, dict) or not actions:
        raise AssetError("manifest.actions 必须是非空对象")
    for name, action in actions.items():
        if not isinstance(action, dict):
            raise AssetError(f"actions.{name} 必须是对象")
        checks = (
            ("file", lambda v: isinstance(v, str) and bool(v)),
            ("frames", lambda v: isinstance(v, int) and v > 0),
            ("fps", lambda v: isinstance(v, (int, float)) and v > 0),
        )
        for key, ok in checks:
            if key not in action or not ok(action[key]):
                raise AssetError(
                    f"actions.{name}.{key} 缺失或非法: {action.get(key)!r}")
    return data


def frame_index(elapsed_ms: int, fps: float, frame_count: int) -> int:
    """按经过时间计算当前帧序号（循环播放）。"""
    if frame_count <= 0:
        raise AssetError(f"frame_count 必须为正: {frame_count}")
    return int(max(0, elapsed_ms) * fps / 1000) % frame_count
```

注意：文件顶部暂时**不** import PySide6（Task 4 再加），保证纯逻辑测试轻量。

- [ ] **Step 4: 运行测试确认通过**

```powershell
.venv\Scripts\python -m pytest tests\test_sprite_logic.py -v
```

预期：7 passed。

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang\sprite.py tests\test_sprite_logic.py
git commit -m "feat: sprite 纯逻辑（manifest 解析与帧索引）" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 3: 占位素材生成脚本

产出正式开发用的占位像素素材（蓝发小人），并留下 AI 正式素材的替换说明。素材格式即规格 3.1 定义的 sprite sheet + manifest.json。

**Files:**
- Create: `tools\gen_placeholder_assets.py`, `assets\README.md`
- 生成（脚本运行产物）: `assets\idle.png`, `assets\walk_right.png`, `assets\walk_left.png`, `assets\dragged.png`, `assets\falling.png`, `assets\manifest.json`

**Interfaces:**
- Consumes: 无（Pillow 已在 Task 1 装好）
- Produces: `assets\manifest.json`，格式 `{"frame_size": [64, 64], "actions": {<name>: {"file": str, "frames": int, "fps": number}}}`，动作名固定为 `idle` / `walk_left` / `walk_right` / `dragged` / `falling`

- [ ] **Step 1: 写 `tools\gen_placeholder_assets.py`**

```python
"""生成占位像素素材：一个蓝发小人（后续可替换为 AI 生成的正式素材）。

用法（项目根目录）：
    .venv\\Scripts\\python tools\\gen_placeholder_assets.py

输出到 assets\\：每个动作一张横向排列的 sprite sheet（帧尺寸 64x64，透明背景），
外加描述帧数/帧率的 manifest.json。
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


def make_sheet(frames_params: list[dict], out_name: str) -> int:
    """按每帧参数画一张 sprite sheet，返回帧数。"""
    sheet = Image.new("RGBA", (FRAME * len(frames_params), FRAME), (0, 0, 0, 0))
    for i, params in enumerate(frames_params):
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        draw_pet(ImageDraw.Draw(frame), **params)
        sheet.paste(frame, (i * FRAME, 0), frame)
    sheet.save(ASSETS_DIR / out_name)
    return len(frames_params)


def main() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    specs = {
        "idle": ([{"body_dy": 0}, {"body_dy": 0}, {"body_dy": 1}, {"body_dy": 1}], 3),
        "walk_right": ([{"leg_offset": o} for o in (-2, -1, 0, 1, 2, 1)], 8),
        "dragged": ([{"arms_up": True, "leg_offset": 1},
                     {"arms_up": True, "leg_offset": -1}], 6),
        "falling": ([{"arms_up": True, "body_dy": 0},
                     {"arms_up": True, "body_dy": 1}], 6),
    }
    manifest = {"frame_size": [FRAME, FRAME], "actions": {}}
    for name, (frames_params, fps) in specs.items():
        file_name = f"{name}.png"
        count = make_sheet(frames_params, file_name)
        manifest["actions"][name] = {"file": file_name, "frames": count, "fps": fps}

    # walk_left 由 walk_right 逐帧镜像生成
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

- [ ] **Step 2: 写 `assets\README.md`**

```markdown
# 素材说明

## 当前素材：程序生成的占位小人

运行 `.venv\Scripts\python tools\gen_placeholder_assets.py` 重新生成。
占位素材用于开发期，正式发布前替换为 AI 生成的"小凉"形象（蓝发、慵懒气质、
可抱贝斯），保持同样的文件格式即可，代码无需改动。

## 格式约定

- 每个动作一张横向排列的 sprite sheet PNG，帧尺寸 64x64，透明背景
- `manifest.json` 描述帧尺寸、每个动作的文件名/帧数/帧率：

  ```json
  {
    "frame_size": [64, 64],
    "actions": {
      "idle": {"file": "idle.png", "frames": 4, "fps": 3}
    }
  }
  ```

- 动作名固定：`idle` / `walk_left` / `walk_right` / `dragged` / `falling`
- 朝向约定：角色默认画成朝右；`walk_left` 是 `walk_right` 的水平镜像

## AI 生成正式素材的流程（提示词模板）

1. 先定稿单帧形象（保证后续所有动作风格一致）：

   > pixel art sprite, 64x64, single character, anime girl with long blue
   > hair, sleepy relaxed expression, holding a bass guitar, side view,
   > transparent background, clean pixels, limited palette

2. 以定稿图为参考，逐动作生成帧序列（站立呼吸 4 帧 / 走路 6 帧 /
   被拎起 2 帧 / 下落 2 帧），每张拼成横向 sprite sheet
3. 替换本目录同名 PNG，按实际帧数/帧率更新 manifest.json
4. 运行 `.venv\Scripts\python tools\check_sprites.py` 验证可加载
```

- [ ] **Step 3: 运行脚本并验证输出**

```powershell
.venv\Scripts\python tools\gen_placeholder_assets.py
dir assets
```

预期：打印 5 个动作的摘要；`assets` 下有 5 个 PNG + manifest.json。

- [ ] **Step 4: Commit**

```powershell
git add tools\gen_placeholder_assets.py assets
git commit -m "feat: 占位像素素材生成脚本与素材清单" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 4: SpriteManager（Qt 素材加载）

**Files:**
- Modify: `xiaoliang\sprite.py`（追加 SpriteManager 类与 Qt import）
- Create: `tools\check_sprites.py`（冒烟验证脚本）

**Interfaces:**
- Consumes: Task 2 的 `parse_manifest` / `frame_index` / `AssetError`；Task 3 的 `assets\`
- Produces: `SpriteManager(assets_dir: Path, scale: int = 2)`，方法 `get_frame(action: str, elapsed_ms: int) -> QPixmap`、`frame_size() -> tuple[int, int]`（放大后的逻辑尺寸）、`actions() -> list[str]`

GUI 类不做单元测试（规格第 6 节），用冒烟脚本手动验证。

- [ ] **Step 1: 在 `xiaoliang\sprite.py` 顶部加 import，文件末尾追加 SpriteManager**

顶部（`import json` 之后）加：

```python
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
```

文件末尾追加：

```python
class SpriteManager:
    """加载 sprite sheet 并按动作/时间返回当前帧（依赖 Qt，需先有 QApplication）。"""

    def __init__(self, assets_dir: Path, scale: int = 2):
        self._scale = scale
        manifest_path = assets_dir / "manifest.json"
        if not manifest_path.exists():
            raise AssetError(f"找不到素材清单: {manifest_path}")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AssetError(f"manifest.json 不是合法 JSON: {exc}") from exc
        self._manifest = parse_manifest(raw)
        fw, fh = self._manifest["frame_size"]
        self._frame_size = (fw, fh)
        self._frames: dict[str, list[QPixmap]] = {}
        self._fps: dict[str, float] = {}
        for name, action in self._manifest["actions"].items():
            path = assets_dir / action["file"]
            if not path.exists():
                raise AssetError(f"动作 {name!r} 的素材文件不存在: {path}")
            sheet = QImage(str(path))
            if sheet.isNull():
                raise AssetError(f"无法读取图片: {path}")
            need_w = fw * action["frames"]
            if sheet.width() < need_w or sheet.height() < fh:
                raise AssetError(
                    f"{path} 尺寸不足: 需要至少 {need_w}x{fh}，"
                    f"实际 {sheet.width()}x{sheet.height()}")
            pixmaps = []
            for i in range(action["frames"]):
                frame = sheet.copy(i * fw, 0, fw, fh).scaled(
                    fw * scale, fh * scale,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.FastTransformation)
                pixmaps.append(QPixmap.fromImage(frame))
            self._frames[name] = pixmaps
            self._fps[name] = action["fps"]

    def get_frame(self, action: str, elapsed_ms: int) -> QPixmap:
        """返回动作在 elapsed_ms 时刻应显示的帧。未知动作抛 AssetError。"""
        if action not in self._frames:
            raise AssetError(f"未知动作: {action!r}（可用: {self.actions()}）")
        frames = self._frames[action]
        return frames[frame_index(elapsed_ms, self._fps[action], len(frames))]

    def frame_size(self) -> tuple[int, int]:
        """放大后的帧尺寸（宽, 高），逻辑像素。"""
        return (self._frame_size[0] * self._scale, self._frame_size[1] * self._scale)

    def actions(self) -> list[str]:
        return sorted(self._frames)
```

- [ ] **Step 2: 写冒烟脚本 `tools\check_sprites.py`**

```python
"""素材加载冒烟检查：验证 assets 能被 SpriteManager 正确加载。

用法（项目根目录）：.venv\\Scripts\\python tools\\check_sprites.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from xiaoliang.sprite import SpriteManager  # noqa: E402


def main() -> int:
    app = QApplication([])  # QPixmap 需要 QGuiApplication 存在
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    sprites = SpriteManager(assets_dir, scale=2)
    print("动作:", sprites.actions())
    print("帧尺寸(放大后):", sprites.frame_size())
    for name in sprites.actions():
        pix = sprites.get_frame(name, 0)
        assert not pix.isNull(), f"{name} 第 0 帧为空"
        print(f"  {name}: 第0帧 {pix.width()}x{pix.height()} OK")
    # 跑一遍既有单元测试，确认 Qt import 没破坏纯逻辑
    del app
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 运行冒烟脚本 + 全量测试**

```powershell
.venv\Scripts\python tools\check_sprites.py
.venv\Scripts\python -m pytest -v
```

预期：脚本打印 5 个动作且全部 OK；pytest 全绿（12 个测试）。

- [ ] **Step 4: Commit**

```powershell
git add xiaoliang\sprite.py tools\check_sprites.py
git commit -m "feat: SpriteManager 素材加载与帧管理" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 5: 状态机 — 待机与行走

**Files:**
- Create: `xiaoliang\state_machine.py`
- Test: `tests\test_state_machine.py`

**Interfaces:**
- Consumes: 无（纯逻辑，禁止 import Qt）
- Produces:
  - `State(Enum)`: `IDLE / WALKING / DRAGGED / FALLING`
  - `Bounds(dataclass, frozen)`: `width: int, height: int`
  - `PetStateMachine(bounds: Bounds, pet_width: int, pet_height: int, *, walk_speed: float = 60.0, idle_range: tuple[float, float] = (2.0, 8.0), walk_range: tuple[float, float] = (3.0, 10.0), gravity: float = 1500.0, start_x: float | None = None, rng: random.Random | None = None)`
  - 属性：`state`, `x: float`, `y: float`（角色包围盒左上角，逻辑像素）, `direction: int`（1 右 / -1 左）, `vy: float`, `paused: bool`, `floor_y: float`
  - 方法：`tick(dt: float) -> None`（本任务实现 IDLE/WALKING 分支；DRAGGED/FALLING 在 Task 6）

- [ ] **Step 1: 写失败的测试 `tests\test_state_machine.py`**

```python
import pytest

from xiaoliang.state_machine import Bounds, PetStateMachine, State


class FakeRandom:
    """可预测随机源：choice 返回预设值，uniform 返回区间上限。"""

    def __init__(self, choice_value=1):
        self.choice_value = choice_value

    def choice(self, seq):
        return self.choice_value

    def uniform(self, a, b):
        return b


def make_machine(rng=None, **overrides) -> PetStateMachine:
    params = dict(
        bounds=Bounds(800, 600),
        pet_width=64, pet_height=64,
        walk_speed=100.0,
        idle_range=(1.0, 1.0),
        walk_range=(2.0, 2.0),
        gravity=1000.0,
    )
    params.update(overrides)
    return PetStateMachine(rng=rng or FakeRandom(), **params)


def test_initial_state_idle_on_floor():
    m = make_machine()
    assert m.state is State.IDLE
    assert m.y == 600 - 64
    assert m.x == pytest.approx((800 - 64) / 2)  # 默认居中


def test_idle_to_walking_after_timer():
    m = make_machine()
    m.tick(0.5)
    assert m.state is State.IDLE
    m.tick(0.6)  # 累计 1.1s > idle 1.0s
    assert m.state is State.WALKING


def test_walking_moves_in_chosen_direction():
    m = make_machine(rng=FakeRandom(choice_value=-1))
    m.tick(1.1)  # → WALKING，方向向左
    x0 = m.x
    m.tick(0.5)
    assert m.direction == -1
    assert m.x == pytest.approx(x0 - 50.0)


def test_walking_stops_at_left_edge_and_goes_idle():
    m = make_machine(rng=FakeRandom(choice_value=-1), start_x=30)
    m.tick(1.1)  # → WALKING 向左
    m.tick(1.0)  # 移动 100px，越过左边缘
    assert m.x == 0.0
    assert m.state is State.IDLE


def test_walking_stops_at_right_edge_and_goes_idle():
    m = make_machine(rng=FakeRandom(choice_value=1), start_x=800 - 64 - 30)
    m.tick(1.1)
    m.tick(1.0)
    assert m.x == 800 - 64
    assert m.state is State.IDLE


def test_walking_to_idle_after_timer():
    m = make_machine(rng=FakeRandom(choice_value=1),
                     walk_range=(0.5, 0.5), start_x=100)
    m.tick(1.1)  # → WALKING
    assert m.state is State.WALKING
    m.tick(0.6)  # 行走计时到
    assert m.state is State.IDLE
```

- [ ] **Step 2: 运行测试确认失败**

```powershell
.venv\Scripts\python -m pytest tests\test_state_machine.py -v
```

预期：ERROR，`No module named 'xiaoliang.state_machine'`。

- [ ] **Step 3: 实现 `xiaoliang\state_machine.py`**

```python
"""宠物行为状态机：纯逻辑，不依赖 Qt，可单元测试。

坐标约定：(x, y) 为角色包围盒左上角，单位逻辑像素，原点为工作区左上角。
"""
import random
from dataclasses import dataclass
from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    WALKING = auto()
    DRAGGED = auto()
    FALLING = auto()


@dataclass(frozen=True)
class Bounds:
    """活动区域尺寸（主显示器工作区，逻辑像素）。"""
    width: int
    height: int


class PetStateMachine:
    def __init__(self, bounds: Bounds, pet_width: int, pet_height: int, *,
                 walk_speed: float = 60.0,
                 idle_range: tuple[float, float] = (2.0, 8.0),
                 walk_range: tuple[float, float] = (3.0, 10.0),
                 gravity: float = 1500.0,
                 start_x: float | None = None,
                 rng: random.Random | None = None):
        self.bounds = bounds
        self.pet_width = pet_width
        self.pet_height = pet_height
        self.walk_speed = walk_speed
        self.idle_range = idle_range
        self.walk_range = walk_range
        self.gravity = gravity
        self._rng = rng or random.Random()
        self.state = State.IDLE
        self.x = ((bounds.width - pet_width) / 2 if start_x is None
                  else float(start_x))
        self.y = float(self.floor_y)
        self.direction = 1  # 1 向右，-1 向左
        self.vy = 0.0
        self.paused = False
        self._timer = self._rng.uniform(*self.idle_range)

    @property
    def floor_y(self) -> float:
        """地面 y 坐标（角色底边贴工作区底边）。"""
        return self.bounds.height - self.pet_height

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    def tick(self, dt: float) -> None:
        """推进 dt 秒。暂停或被拖拽时不更新。"""
        if self.paused or self.state is State.DRAGGED:
            return
        if self.state is State.IDLE:
            self._timer -= dt
            if self._timer <= 0:
                self._start_walking()
        elif self.state is State.WALKING:
            self.x += self.direction * self.walk_speed * dt
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
        # FALLING 分支在 Task 6 实现

    def drag_start(self) -> None:
        """被鼠标抓住。Task 6 测试覆盖，此处先提供接口。"""
        if self.state is not State.DRAGGED:
            self.state = State.DRAGGED
            self.vy = 0.0

    def drag_move(self, x: float, y: float) -> None:
        """拖拽中更新位置（钳制在活动区域内）。Task 6 测试覆盖。"""
        if self.state is not State.DRAGGED:
            return
        self.x = min(max(0.0, x), self.bounds.width - self.pet_width)
        self.y = min(max(0.0, y), self.bounds.height - self.pet_height)

    def drag_end(self) -> None:
        """松手 → 下落。Task 6 测试覆盖。"""
        if self.state is State.DRAGGED:
            self.state = State.FALLING
            self.vy = 0.0

    def _start_idle(self) -> None:
        self.state = State.IDLE
        self._timer = self._rng.uniform(*self.idle_range)

    def _start_walking(self) -> None:
        self.state = State.WALKING
        self.direction = self._rng.choice((-1, 1))
        self._timer = self._rng.uniform(*self.walk_range)
```

- [ ] **Step 4: 运行测试确认通过**

```powershell
.venv\Scripts\python -m pytest tests\test_state_machine.py -v
```

预期：6 passed。

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang\state_machine.py tests\test_state_machine.py
git commit -m "feat: 状态机待机与行走行为" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 6: 状态机 — 拖拽、下落与暂停

**Files:**
- Modify: `xiaoliang\state_machine.py`（给 tick 补 FALLING 分支；drag_* 方法 Task 5 已就位）
- Test: `tests\test_state_machine.py`（追加）

**Interfaces:**
- Consumes: Task 5 的 `PetStateMachine`（`drag_start()` / `drag_move(x, y)` / `drag_end()` / `set_paused(bool)`）
- Produces: 完整状态机——`FALLING` 在 tick 中受重力下落、落地转 IDLE；`paused=True` 时 tick 为 no-op；FALLING 中可再次 `drag_start()` 抓住

- [ ] **Step 1: 在 `tests\test_state_machine.py` 末尾追加失败测试**

```python
def test_drag_start_from_idle():
    m = make_machine()
    m.drag_start()
    assert m.state is State.DRAGGED


def test_drag_move_updates_and_clamps():
    m = make_machine()
    m.drag_start()
    m.drag_move(100, 200)
    assert (m.x, m.y) == (100, 200)
    m.drag_move(-50, 5000)
    assert m.x == 0.0
    assert m.y == 600 - 64


def test_drag_move_ignored_when_not_dragged():
    m = make_machine()
    m.drag_move(100, 100)
    assert (m.x, m.y) != (100, 100)


def test_drag_end_starts_falling():
    m = make_machine()
    m.drag_start()
    m.drag_move(100, 100)
    m.drag_end()
    assert m.state is State.FALLING


def test_falling_lands_on_floor_then_idle():
    m = make_machine(idle_range=(100.0, 100.0))  # 落地后长时间保持 IDLE 便于断言
    m.drag_start()
    m.drag_move(100, 100)
    m.drag_end()
    for _ in range(60):  # 2 秒 @30fps，足够从 y=100 落到 y=536
        m.tick(1 / 30)
    assert m.y == 600 - 64
    assert m.state is State.IDLE


def test_grab_while_falling():
    m = make_machine()
    m.drag_start()
    m.drag_move(100, 100)
    m.drag_end()
    m.tick(1 / 30)
    assert m.state is State.FALLING
    m.drag_start()
    assert m.state is State.DRAGGED


def test_paused_tick_is_noop():
    m = make_machine()
    m.set_paused(True)
    for _ in range(100):
        m.tick(0.1)
    assert m.state is State.IDLE
    m.set_paused(False)
    m.tick(1.1)
    assert m.state is State.WALKING
```

- [ ] **Step 2: 运行确认新测试失败**

```powershell
.venv\Scripts\python -m pytest tests\test_state_machine.py -v
```

预期：`test_falling_lands_on_floor_then_idle` FAIL（FALLING 时 tick 无下落逻辑，y 不变）；其余新测试可能已通过（drag_*/paused 接口 Task 5 已实现）——这是正常的。

- [ ] **Step 3: 在 `state_machine.py` 的 tick() 中补 FALLING 分支**

把 `# FALLING 分支在 Task 6 实现` 注释替换为：

```python
        elif self.state is State.FALLING:
            self.vy += self.gravity * dt
            self.y += self.vy * dt
            if self.y >= self.floor_y:
                self.y = float(self.floor_y)
                self.vy = 0.0
                self._start_idle()
```

- [ ] **Step 4: 运行全量测试确认通过**

```powershell
.venv\Scripts\python -m pytest -v
```

预期：全绿（19 个测试：config 5 + sprite 7 + state_machine 13... 以实际收集数为准，0 failed）。

- [ ] **Step 5: Commit**

```powershell
git add xiaoliang\state_machine.py tests\test_state_machine.py
git commit -m "feat: 状态机拖拽、下落与暂停" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 7: PetWindow + 最小 main.py（第一次看到小凉！）

**Files:**
- Create: `xiaoliang\pet_window.py`, `main.py`（最小版：窗口 + 状态机 + 素材 + 配置；托盘/日志 Task 8 加）

**Interfaces:**
- Consumes: `SpriteManager.get_frame/frame_size`、`PetStateMachine`（全部接口）、`load_config/default_config_path`
- Produces: `PetWindow(machine: PetStateMachine, sprites: SpriteManager)`（QWidget 子类，自带 30 FPS 驱动，无需外部调用）；`main.py` 可直接 `python main.py` 运行

GUI 无自动化测试，用手动验收清单。

- [ ] **Step 1: 实现 `xiaoliang\pet_window.py`**

```python
"""桌宠窗口：透明置顶无边框，渲染当前帧并把鼠标事件转发给状态机。"""
from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .sprite import SpriteManager
from .state_machine import PetStateMachine, State

FPS = 30

# 状态 → 动作名（WALKING 需按方向细分，单独处理）
STATE_ACTION = {
    State.IDLE: "idle",
    State.DRAGGED: "dragged",
    State.FALLING: "falling",
}


class PetWindow(QWidget):
    def __init__(self, machine: PetStateMachine, sprites: SpriteManager):
        super().__init__(None,
                         Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.machine = machine
        self.sprites = sprites
        self.setFixedSize(*sprites.frame_size())
        self.setWindowTitle("小凉")
        self._pixmap: QPixmap = sprites.get_frame("idle", 0)
        self._anim_ms = 0
        self._last_action = "idle"
        self._drag_offset: QPoint | None = None
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

    def _on_tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        self.machine.tick(dt)
        action = self.current_action()
        if action != self._last_action:
            self._anim_ms = 0          # 换动作时动画从头播
            self._last_action = action
        else:
            self._anim_ms += int(dt * 1000)
        self._pixmap = self.sprites.get_frame(action, self._anim_ms)
        self.move(int(self.machine.x), int(self.machine.y))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.machine.drag_start()
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None:
            pos = event.globalPosition().toPoint() - self._drag_offset
            self.machine.drag_move(pos.x(), pos.y())
            self.move(pos)  # 拖拽时立即跟手，不等下一个 tick
            event.accept()

    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self._drag_offset is not None):
            self._drag_offset = None
            self.machine.drag_end()
            event.accept()
```

- [ ] **Step 2: 实现最小 `main.py`**

```python
"""小凉桌面宠物 — 程序入口。"""
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from xiaoliang.config import default_config_path, load_config
from xiaoliang.pet_window import PetWindow
from xiaoliang.sprite import SpriteManager
from xiaoliang.state_machine import Bounds, PetStateMachine


def assets_dir() -> Path:
    """素材目录：打包后在 PyInstaller 解包目录，源码运行时在项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent / "assets"


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    cfg = load_config(default_config_path())
    sprites = SpriteManager(assets_dir(), scale=int(cfg["scale"]))
    area = QGuiApplication.primaryScreen().availableGeometry()
    fw, fh = sprites.frame_size()
    machine = PetStateMachine(
        Bounds(area.width(), area.height()), fw, fh,
        walk_speed=float(cfg["walk_speed"]),
        start_x=(area.width() - fw) / 2)
    machine.set_paused(bool(cfg["paused"]))
    window = PetWindow(machine, sprites)
    window.move(int(machine.x), int(machine.y))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 手动验收（清单）**

```powershell
.venv\Scripts\python main.py
```

逐项确认（不满足则修复后重跑）：

1. 屏幕上出现无边框、背景透明的小人（只有像素角色本体，无白色底）
2. 小人不在任务栏占位
3. 播放待机动画（有呼吸起伏）
4. 几秒后自己开始走路，走路动画与移动方向一致（向左走时面朝左）
5. 走到屏幕左右边缘会停下，之后回到待机
6. 鼠标左键能把它拎起来（切换挣扎动画），拖动跟手
7. 松手后下落，落地回到待机
8. 下落过程中可以再次抓住
9. 关闭方式（本任务还没有托盘）：任务管理器结束 python 进程——确认可接受，Task 8 补托盘退出

- [ ] **Step 4: Commit**

```powershell
git add xiaoliang\pet_window.py main.py
git commit -m "feat: 桌宠窗口与最小入口，角色可走动拖拽下落" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 8: 系统托盘 + 日志 + 错误处理（完整 main.py）

**Files:**
- Create: `xiaoliang\tray.py`
- Modify: `main.py`（加日志初始化、AssetError 弹窗、托盘装配）

**Interfaces:**
- Consumes: `PetStateMachine.set_paused`、`SpriteManager.get_frame`（取托盘图标）、`QApplication.quit`
- Produces: `PetTray(machine: PetStateMachine, icon: QPixmap, on_quit: callable)`（QSystemTrayIcon 子类，`show()` 后生效）

- [ ] **Step 1: 实现 `xiaoliang\tray.py`**

```python
"""系统托盘：暂停/恢复、退出。双击托盘图标 = 暂停/恢复。"""
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .state_machine import PetStateMachine


class PetTray(QSystemTrayIcon):
    def __init__(self, machine: PetStateMachine, icon: QPixmap, on_quit):
        super().__init__(QIcon(icon), None)
        self.machine = machine
        self.setToolTip("小凉")

        self._pause_action = QAction("暂停", self)
        self._pause_action.setCheckable(True)
        self._pause_action.setChecked(machine.paused)
        self._pause_action.toggled.connect(self._on_toggle_pause)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(on_quit)

        menu = QMenu()
        menu.addAction(self._pause_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.setContextMenu(menu)
        self._menu = menu  # 保持引用，防止被垃圾回收
        self.activated.connect(self._on_activated)

    def _on_toggle_pause(self, checked: bool) -> None:
        self.machine.set_paused(checked)
        self._pause_action.setText("恢复" if checked else "暂停")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # 单击/双击
            self._pause_action.toggle()
```

- [ ] **Step 2: 完善 `main.py`（整文件替换）**

```python
"""小凉桌面宠物 — 程序入口。"""
import logging
import os
import sys
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from xiaoliang.config import default_config_path, load_config
from xiaoliang.pet_window import PetWindow
from xiaoliang.sprite import AssetError, SpriteManager
from xiaoliang.state_machine import Bounds, PetStateMachine
from xiaoliang.tray import PetTray


def setup_logging() -> None:
    """日志写到 %APPDATA%\\xiaoliang\\xiaoliang.log（打包后该目录仍可写）。"""
    log_dir = Path(os.environ.get("APPDATA", str(Path.home()))) / "xiaoliang"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "xiaoliang.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def assets_dir() -> Path:
    """素材目录：打包后在 PyInstaller 解包目录，源码运行时在项目根。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "assets"
    return Path(__file__).resolve().parent / "assets"


def main() -> int:
    setup_logging()
    logging.info("小凉启动")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关窗口不退出，由托盘控制
    cfg = load_config(default_config_path())
    try:
        sprites = SpriteManager(assets_dir(), scale=int(cfg["scale"]))
    except AssetError as exc:
        logging.exception("素材加载失败")
        QMessageBox.critical(None, "小凉启动失败", f"素材加载失败：\n{exc}")
        return 1
    area = QGuiApplication.primaryScreen().availableGeometry()
    fw, fh = sprites.frame_size()
    machine = PetStateMachine(
        Bounds(area.width(), area.height()), fw, fh,
        walk_speed=float(cfg["walk_speed"]),
        start_x=(area.width() - fw) / 2)
    machine.set_paused(bool(cfg["paused"]))
    window = PetWindow(machine, sprites)
    window.move(int(machine.x), int(machine.y))
    window.show()
    tray = PetTray(machine, sprites.get_frame("idle", 0), app.quit)
    tray.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 手动验收（清单）**

```powershell
.venv\Scripts\python main.py
```

1. 托盘出现小凉图标
2. 右键托盘 → "暂停"：角色停在原地播待机动画，不再走动；菜单文字变"恢复"
3. 右键 → "恢复"：行为恢复
4. 双击托盘图标：等同暂停/恢复切换
5. 右键 → "退出"：程序完全退出（任务管理器无残留 python 进程）
6. 错误处理：把 `assets\idle.png` 临时改名后启动 → 弹出"素材加载失败"错误框而不是闪退；`%APPDATA%\xiaoliang\xiaoliang.log` 里有记录；改回文件名
7. 配置生效：手写 `config.json` 为 `{"scale": 3, "walk_speed": 150, "paused": false}`，重启后角色变大、走得更快；删除 config.json 恢复默认

- [ ] **Step 4: Commit**

```powershell
git add xiaoliang\tray.py main.py
git commit -m "feat: 系统托盘、日志与启动错误处理" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

---

### Task 9: README、LICENSE 与 PyInstaller 打包

**Files:**
- Create: `README.md`, `LICENSE`
- Modify: `.gitignore`（确认 dist/build 已忽略——Task 1 已含，无需改则跳过）

**Interfaces:**
- Consumes: 可运行的完整程序（Task 8 产物）
- Produces: `dist\xiaoliang.exe`（单文件、无控制台窗口）；GitHub 发布就绪的仓库

- [ ] **Step 1: 写 `README.md`**

````markdown
# 小凉 🎸

一只 Windows 桌面像素宠物：蓝发小人在屏幕底部溜达、发呆，可以用鼠标把她
拎起来（会挣扎），松手会掉回地面。常驻系统托盘，随时暂停/退出。

![demo](docs/demo.gif)
<!-- TODO(发布前): 用 ScreenToGif 等工具录一段 20 秒演示替换此文件 -->

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
````

- [ ] **Step 2: 写 `LICENSE`（MIT 全文）**

```
MIT License

Copyright (c) 2026 bowen.liwx

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: 打包并验证 exe**

```powershell
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name xiaoliang --add-data "assets;assets" main.py
dist\xiaoliang.exe
```

验收：

1. exe 启动后角色出现，行走/拖拽/托盘行为与源码运行一致
2. exe 同目录生成不了 config.json 没关系（读取缺省即可），手动放一个 `{"scale": 3}` 的 config.json 重启 exe，确认变大
3. 托盘"退出"能完全结束进程
4. 记录 exe 体积（预期 40~80MB，超出过多则检查是否误打包了无关库）

- [ ] **Step 4: 全量测试回归**

```powershell
.venv\Scripts\python -m pytest -v
```

预期：0 failed。

- [ ] **Step 5: Commit**

```powershell
git add README.md LICENSE
git commit -m "docs: README 与 MIT 许可证；完成 v0.1 打包验证" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

- [ ] **Step 6: 发布到 GitHub（需要用户配合）**

1. 在 GitHub 网页新建空仓库 `xiaoliang`（不要勾选初始化 README/license）
2. 推送：

```powershell
git remote add origin https://github.com/<你的用户名>/xiaoliang.git
git branch -M main
git push -u origin main
```

3. （可选，发布前）录一段演示 GIF 存为 `docs\demo.gif`，commit 并 push；在 Releases 上传 `dist\xiaoliang.exe`

---

## 自查记录（写计划时已完成）

- **规格覆盖**：3.1 素材→Task 3/4；3.2 窗口→Task 7；3.3 行为→Task 5/6；3.4 托盘→Task 8；3.5 配置→Task 1/8；3.6 打包发布→Task 9；第 4 节架构→文件结构总览；第 5 节错误处理→Task 4（AssetError）/Task 8（弹窗+日志）；第 6 节测试→各 TDD 任务 + Task 7/8 手动清单。无遗漏
- **类型一致性**：`frame_size()` 返回放大后尺寸（Task 4 定义，Task 7 用于 setFixedSize 与状态机 pet_width/height）；`drag_move` 参数为 float（Task 5 定义，Task 7 传 int 兼容）；动作名 5 个在 Task 3 manifest、Task 7 STATE_ACTION、Task 4 冒烟脚本中一致
- **已知留给执行时的注意点**：Task 6 Step 4 的测试总数以 pytest 实际收集为准；DPI 缩放坐标若偏移属规格已知风险，v0.1.x 修复，不阻塞本计划
