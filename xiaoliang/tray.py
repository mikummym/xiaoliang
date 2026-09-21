"""系统托盘：暂停/恢复、退出。双击托盘图标 = 暂停/恢复。"""
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .state_machine import PetStateMachine


class PetTray(QSystemTrayIcon):
    def __init__(self, machine: PetStateMachine, icon: QPixmap, on_quit):
        super().__init__(QIcon(icon), None)
        self.machine = machine
        self.setToolTip("小凉")

        # 初始文字与勾选状态都来自 machine.paused（配置 paused=true 启动时
        # 菜单应直接显示"恢复"）
        self._pause_action = QAction("恢复" if machine.paused else "暂停", self)
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
        # 暂停双向同步（spec §3）：右键菜单调 machine.set_paused 时，状态机
        # 经此回调通知托盘刷新勾选与文字；反向（托盘→状态机）原有逻辑不变
        machine.add_pause_listener(self.sync_pause)

    def _on_toggle_pause(self, checked: bool) -> None:
        self.machine.set_paused(checked)
        self._pause_action.setText("恢复" if checked else "暂停")

    def _on_activated(self, reason) -> None:
        # 规格 3.4：双击托盘图标 = 暂停/恢复（单击不触发）。双击时系统只发
        # 一次 DoubleClick，故切换恰好一次。
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._pause_action.toggle()

    def sync_pause(self, paused: bool) -> None:
        """状态机暂停变更回调：只刷新 UI，不回写状态机（防递归）。"""
        # blockSignals 避免 setChecked 触发 toggled → 再次 set_paused 死循环
        self._pause_action.blockSignals(True)
        self._pause_action.setChecked(paused)
        self._pause_action.setText("恢复" if paused else "暂停")
        self._pause_action.blockSignals(False)
