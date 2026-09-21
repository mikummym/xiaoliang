"""桌宠窗口：透明置顶无边框，渲染当前帧并把鼠标事件转发给状态机。

状态机坐标以工作区左上角为原点（规格 3.3）；
全局屏幕坐标 = origin（availableGeometry().topLeft()）+ 状态机坐标。
"""
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
    def __init__(self, machine: PetStateMachine, sprites: SpriteManager,
                 origin: QPoint | None = None):
        super().__init__(None,
                         Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.machine = machine
        self.sprites = sprites
        # 工作区左上角的全局屏幕坐标（任务栏在顶部/左侧时非零）
        self._origin = origin if origin is not None else QPoint(0, 0)
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

    def _to_global(self, x: float, y: float) -> QPoint:
        """状态机坐标（工作区原点）→ 全局屏幕坐标。"""
        return QPoint(self._origin.x() + int(x), self._origin.y() + int(y))

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
        self.move(self._to_global(self.machine.x, self.machine.y))
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
            # machine 使用工作区坐标：全局屏幕坐标先减去工作区原点
            self.machine.drag_move(pos.x() - self._origin.x(),
                                   pos.y() - self._origin.y())
            # 拖拽时立即跟手，不等下一个 tick（用钳制后的 machine 坐标，
            # 保证窗口不拖出工作区）
            self.move(self._to_global(self.machine.x, self.machine.y))
            event.accept()

    def mouseReleaseEvent(self, event):
        # v0.1 已知边缘情况（留待 v0.2）：暂停中松手时 tick 为 no-op，
        # 角色会停在半空的 FALLING（按暂停规则渲染 idle），恢复暂停后落地。
        if (event.button() == Qt.MouseButton.LeftButton
                and self._drag_offset is not None):
            self._drag_offset = None
            self.machine.drag_end()
            event.accept()
