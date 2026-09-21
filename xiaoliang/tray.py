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
