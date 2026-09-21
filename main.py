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
