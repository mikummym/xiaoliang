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
