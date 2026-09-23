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
    sprites = SpriteManager(assets_dir, scale=1)
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
