"""小凉桌面宠物 — 程序入口。"""
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from xiaoliang.config import default_config_path, load_config, save_config
from xiaoliang.pet_window import PetWindow
from xiaoliang.sprite import AssetError, SpriteManager
from xiaoliang.state_machine import Bounds, PetStateMachine
from xiaoliang.status import PetStatus
from xiaoliang.tray import PetTray

# 数值自动保存间隔（spec §2.1：每 60 秒 + 喂食/戳/退出时即时保存）
STATUS_SAVE_INTERVAL_MS = 60_000


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
    cfg_path = default_config_path()
    cfg = load_config(cfg_path)

    # 数值系统：status.json 与 config.json 同目录；文件损坏/缺失时
    # PetStatus.load 内部回退默认 80/80（spec §2.1，离线不补算衰减）
    status_path = cfg_path.parent / "status.json"
    status = PetStatus.load(status_path)

    def save_status() -> None:
        """统一落盘入口：定时保存/数值变化回调/退出保存都走这里。

        save() 内部已捕获 OSError 只记日志，这里无需再包。
        """
        status.save(status_path)

    if not cfg_path.exists():
        # 首次运行自动生成默认 config.json（规格 3.5）。只读目录（如某些
        # 安装位置）写不进去也不应阻塞启动——记日志后用内存默认值继续。
        try:
            save_config(cfg, cfg_path)
        except OSError as exc:
            logging.warning("无法写入默认配置 %s（继续用默认值）: %s",
                            cfg_path, exc)
    try:
        sprites = SpriteManager(assets_dir(), scale=int(cfg["scale"]))
    except AssetError as exc:
        logging.exception("素材加载失败")
        QMessageBox.critical(None, "小凉启动失败", f"素材加载失败：\n{exc}")
        return 1
    area = QGuiApplication.primaryScreen().availableGeometry()
    origin = area.topLeft()  # 工作区左上角（任务栏在顶/左时非零）
    fw, fh = sprites.frame_size()
    machine = PetStateMachine(
        Bounds(area.width(), area.height()), fw, fh,
        walk_speed=float(cfg["walk_speed"]),
        start_x=(area.width() - fw) / 2,
        status=status,
        sleep_start=cfg["sleep_start"],
        sleep_end=cfg["sleep_end"],
        on_status_change=save_status)   # 戳/喂食数值变化后即时落盘
    machine.set_paused(bool(cfg["paused"]))
    window = PetWindow(machine, sprites, origin=origin, on_quit=app.quit)
    window.move(origin.x() + int(machine.x), origin.y() + int(machine.y))
    window.show()
    tray = PetTray(machine, sprites.get_frame("idle", 0), app.quit)
    tray.show()

    # 定时保存数值（每 60 秒）+ 退出时兜底保存
    save_timer = QTimer()
    save_timer.setInterval(STATUS_SAVE_INTERVAL_MS)
    save_timer.timeout.connect(save_status)
    save_timer.start()
    app.aboutToQuit.connect(save_status)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
