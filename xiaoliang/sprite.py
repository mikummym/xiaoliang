"""素材加载与动画帧管理。

纯逻辑部分（parse_manifest / frame_index）不依赖 Qt 对象，可单元测试；
SpriteManager（Task 4 追加）依赖 Qt，需在 QApplication 下使用。
"""
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap


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
