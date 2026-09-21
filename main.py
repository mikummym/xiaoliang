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
