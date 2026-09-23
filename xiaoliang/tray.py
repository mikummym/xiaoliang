"""系统托盘：暂停/恢复、静音、开机自启、退出。双击托盘图标 = 暂停/恢复。"""
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import autostart
from .state_machine import PetStateMachine


class PetTray(QSystemTrayIcon):
    def __init__(self, machine: PetStateMachine, icon: QPixmap, on_quit, *,
                 sound_cfg: dict | None = None, on_cfg_changed=None):
        super().__init__(QIcon(icon), None)
        self.machine = machine
        self.setToolTip("小凉")

        # 初始文字与勾选状态都来自 machine.paused（配置 paused=true 启动时
        # 菜单应直接显示"恢复"）
        self._pause_action = QAction("恢复" if machine.paused else "暂停", self)
        self._pause_action.setCheckable(True)
        self._pause_action.setChecked(machine.paused)
        self._pause_action.toggled.connect(self._on_toggle_pause)

        # ── v0.3 静音开关（spec §5.2）：与 cfg["sound"]["muted"] 双向同步。
        # SoundEngine 持有同一 dict 引用，改这里立即全局生效；
        # on_cfg_changed 负责落盘 config.json
        self._mute_action = None
        if sound_cfg is not None:
            self._sound_cfg = sound_cfg
            self._on_cfg_changed = on_cfg_changed
            self._mute_action = QAction("静音", self)
            self._mute_action.setCheckable(True)
            self._mute_action.setChecked(bool(sound_cfg.get("muted", False)))
            self._mute_action.toggled.connect(self._on_toggle_mute)

        # ── v0.3 开机自启（spec §5.1）：真相源 = 注册表，启动时读一次；
        # is_enabled() 返回 None（注册表被锁）→ 菜单项置灰
        self._autostart_action = QAction("开机自启", self)
        self._autostart_action.setCheckable(True)
        enabled = autostart.is_enabled()
        if enabled is None:
            self._autostart_action.setEnabled(False)
        else:
            self._autostart_action.setChecked(enabled)
        self._autostart_action.toggled.connect(self._on_toggle_autostart)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(on_quit)

        menu = QMenu()
        menu.addAction(self._pause_action)
        if self._mute_action is not None:
            menu.addAction(self._mute_action)
        menu.addAction(self._autostart_action)
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

    def _on_toggle_mute(self, checked: bool) -> None:
        """静音开关：改共享 dict（引擎立即生效）+ 落盘 config。"""
        # 直改共享 dict：SoundEngine 持同一引用，下一次 should_play 现读即生效，
        # 无需通知机制；on_cfg_changed 把整个 cfg 写回 config.json
        self._sound_cfg["muted"] = checked
        if self._on_cfg_changed is not None:
            self._on_cfg_changed()

    def _on_toggle_autostart(self, checked: bool) -> None:
        """开机自启开关：写/删注册表；失败则回滚勾选态。"""
        if not autostart.set_enabled(checked):
            # blockSignals 保护回滚：setChecked 会触发 toggled 信号，若不屏蔽
            # 会再次进入本回调形成抖动；屏蔽后手动还原注册表实况再放行信号
            self._autostart_action.blockSignals(True)   # 防回滚再触发
            self._autostart_action.setChecked(autostart.is_enabled() or False)
            self._autostart_action.blockSignals(False)

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
