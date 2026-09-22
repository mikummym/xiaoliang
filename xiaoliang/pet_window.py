"""桌宠窗口：透明置顶无边框，渲染当前帧并把鼠标事件转发给状态机。

状态机坐标以工作区左上角为原点（规格 3.3）；
全局屏幕坐标 = origin（availableGeometry().topLeft()）+ 状态机坐标。

v0.2 新增（spec §2.3）：
- 戳 vs 拖拽判定：按压 <250ms 且位移 <5px = 戳（machine.poke()），
  否则走 v0.1 拖拽流程（machine.drag_end() 下落）
- 右键菜单：喂食（吃撑置灰）/ 状态展示 / 暂停·恢复 / 退出
- 悬停 tooltip：每秒刷新"心情 😊N · 饱腹 🍚N · 状态中文"
- 攀爬渲染：爬下 = 帧序倒放，左壁 = 水平镜像（get_frame kwargs）
"""
import math
import time

from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QToolTip, QWidget

from .sprite import SpriteManager
from .state_machine import PetStateMachine, State

FPS = 30

# 戳判定阈值（spec §2.3）：按压时长与位移都必须小于该值才算"戳"
POKE_MAX_MS = 250
POKE_MAX_PX = 5.0

# 攀爬/坐姿贴边的渲染补偿（逻辑像素）：climbing 帧素材里"手"最远画到
# 第 42 逻辑列（含），墙侧第 43..63 共 21 列是空白——不补偿时角色看起来
# 悬空在离屏幕边缘 21 逻辑像素处。把窗口向墙外推出这段空白（×scale、
# ×climb_wall 方向），手就正好搭在屏幕边缘上。
CLING_MARGIN_LOGICAL = 21

# 状态 → 动作名（WALKING 按方向细分、CLIMBING 的倒放/镜像单独处理）
STATE_ACTION = {
    State.IDLE: "idle",
    State.DRAGGED: "dragged",
    State.FALLING: "falling",
    State.POKE_REACT: "poke_react",
    State.EATING: "eating",
    State.SLEEPING: "sleeping",
    State.WOKEN: "woken",
    State.CLIMBING: "climbing",
    State.SITTING_TOP: "sitting_top",
}

# 状态 → tooltip 中文名（spec §2.3 映射表，逐字一致）
STATE_ZH = {
    State.IDLE: "发呆",
    State.WALKING: "溜达",
    State.DRAGGED: "被拎着",
    State.FALLING: "下落中",
    State.POKE_REACT: "被戳了",
    State.EATING: "吃东西",
    State.SLEEPING: "睡觉",
    State.WOKEN: "睡眼惺忪",
    State.CLIMBING: "爬墙",
    State.SITTING_TOP: "顶上坐着",
}


class PetWindow(QWidget):
    def __init__(self, machine: PetStateMachine, sprites: SpriteManager,
                 origin: QPoint | None = None, on_quit=None):
        super().__init__(None,
                         Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.machine = machine
        self.sprites = sprites
        # 工作区左上角的全局屏幕坐标（任务栏在顶部/左侧时非零）
        self._origin = origin if origin is not None else QPoint(0, 0)
        # 右键菜单"退出"回调（main.py 注入 app.quit）
        self._on_quit = on_quit
        self.setFixedSize(*sprites.frame_size())
        self.setWindowTitle("小凉")
        self._pixmap: QPixmap = sprites.get_frame("idle", 0)
        self._anim_ms = 0
        self._last_action = "idle"
        self._drag_offset: QPoint | None = None
        # ── 戳/拖拽判定状态：按压时刻、按压位置、是否已发生有效位移 ──
        self._press_ts = 0.0
        self._press_pos: QPoint | None = None
        self._drag_moved = False
        # 贴边偏移保持标志：在壁上被戳/跳下的瞬间 machine.x 仍吸附在墙边，
        # 偏移若立即归零窗口会横跳 21*scale 物理像素，故用此标志跨帧保持
        self._wall_cling = False
        # tooltip 刷新计时（毫秒累计，每满 1000 刷一次）
        self._tooltip_ms = 0
        self._refresh_tooltip()
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setInterval(1000 // FPS)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start()
        # ── 悬停 tooltip 自管理 ──
        # 为什么不用 Qt 内建悬停触发：本窗口是分层透明（WA_Translucent-
        # Background）且 30fps 高频重绘/移动，Qt 的自动 tooltip 在这种
        # 窗口上不可靠（实测只有右键菜单路径能弹出），改为鼠标进入后
        # 延迟手动 QToolTip.showText；内容仍由 _refresh_tooltip 维护。
        self.setMouseTracking(True)
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(500)  # 悬停约 0.5s 才弹，划过不闪
        self._tooltip_timer.timeout.connect(self._show_tooltip)

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

    def _refresh_tooltip(self) -> None:
        """悬停 tooltip：数值 + 状态中文名（格式严格按 spec §2.3）。"""
        s = self.machine.status
        self.setToolTip(f"心情 😊{s.mood:.0f} · 饱腹 🍚{s.fullness:.0f} · "
                        f"{STATE_ZH.get(self.machine.state, '')}")

    def _show_tooltip(self) -> None:
        """悬停计时到点：在鼠标当前位置手动弹出 tooltip（内容取 setToolTip）。"""
        QToolTip.showText(QCursor.pos(), self.toolTip())

    def enterEvent(self, event):
        """鼠标进入：启动悬停计时，到点由 _show_tooltip 手动弹出。"""
        self._tooltip_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开：取消待弹的计时，并隐藏可能已显示的 tooltip。"""
        self._tooltip_timer.stop()
        QToolTip.hideText()
        super().leaveEvent(event)

    def _on_tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        self.machine.tick(dt)
        action = self.current_action()
        if action != self._last_action:
            self._anim_ms = 0          # 换动作时动画从头播
            self._last_action = action
        else:
            self._anim_ms += int(dt * 1000)
        # 攀爬渲染：爬下倒放帧序；左壁水平镜像——坐姿同样镜像，因为
        # SITTING_TOP 只会从 CLIMBING 到顶进入，climb_wall 在坐姿下仍然
        # 有效，不镜像的话左右两侧坐上去姿势会朝错方向
        climbing = self.machine.state is State.CLIMBING
        sitting = self.machine.state is State.SITTING_TOP
        self._pixmap = self.sprites.get_frame(
            action, self._anim_ms,
            reverse=climbing and self.machine.climb_direction == "down",
            mirror=(climbing or sitting) and self.machine.climb_wall < 0)
        # 攀爬/坐姿贴屏幕边缘：把窗口向墙外推出素材墙侧的空白列
        #（CLING_MARGIN_LOGICAL 为逻辑像素，×scale 换算、×climb_wall 定向：
        # 右壁推出屏幕右缘、左壁推出左缘），手就正好搭在屏幕边缘上。
        # 纯渲染层偏移，不改状态机坐标；三段逻辑决定偏移是否生效：
        if self.machine.state in (State.CLIMBING, State.SITTING_TOP):
            # 贴壁状态：开启并保持偏移
            self._wall_cling = True
        elif self.machine.state in (State.POKE_REACT, State.FALLING):
            # 在壁上被戳（POKE_REACT，播完自然回到贴壁状态）或坐够跳下
            #（FALLING）的瞬间 machine.x 仍吸附在墙边，偏移必须沿用不能
            # 归零，否则窗口一帧横跳 21*scale；FALLING 落地后进
            # IDLE/SLEEPING，由下一分支清除
            pass
        else:
            # IDLE/WALKING/DRAGGED/SLEEPING/EATING/WOKEN：不贴边，偏移归零
            self._wall_cling = False
        # POKE_REACT/FALLING 素材的角色占帧内第 22..42 逻辑列，贴边状态
        # 下完全落在可见带内（右壁可见 0..42、左壁镜像可见原帧 21..63），
        # 保持偏移不会把角色裁掉，无需额外处理
        cling_off = 0
        if self._wall_cling:
            cling_off = (CLING_MARGIN_LOGICAL * self.sprites.scale
                         * self.machine.climb_wall)
        self.move(self._to_global(self.machine.x, self.machine.y)
                  + QPoint(cling_off, 0))
        # tooltip 每秒刷新：数值随时间衰减，刷太快没有意义
        self._tooltip_ms += int(dt * 1000)
        if self._tooltip_ms >= 1000:
            self._tooltip_ms = 0
            self._refresh_tooltip()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()

    def mousePressEvent(self, event):
        # 任意鼠标键按下都取消待弹的 tooltip：右键按下后 contextMenuEvent
        # 的 QMenu.exec 会进入嵌套事件循环、定时器照跑，且菜单抓取鼠标后
        # Windows 不会给下层窗口发 Leave（有 capture 时无 WM_MOUSELEAVE），
        # 待弹的 tooltip 会压在已打开的菜单上——所以这里不能只管左键。
        self._tooltip_timer.stop()
        QToolTip.hideText()
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录按压时刻/位置供戳判定；照旧先 drag_start()——真拖拽时
            # 状态机立即进入 DRAGGED 才能跟手（戳的情况松手时回退）
            self._press_ts = time.monotonic()
            self._press_pos = event.globalPosition().toPoint()
            self._drag_moved = False
            self.machine.drag_start()
            self._drag_offset = (event.globalPosition().toPoint()
                                 - self.frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is None:
            return
        pos = event.globalPosition().toPoint()
        # 位移超过阈值才算有效拖拽：戳的时候手抖几像素不会误判
        if not self._drag_moved and self._press_pos is not None:
            delta = pos - self._press_pos
            if math.hypot(delta.x(), delta.y()) > POKE_MAX_PX:
                self._drag_moved = True
        if self._drag_moved:
            target = pos - self._drag_offset
            # machine 使用工作区坐标：全局屏幕坐标先减去工作区原点
            self.machine.drag_move(target.x() - self._origin.x(),
                                   target.y() - self._origin.y())
            # 拖拽时立即跟手，不等下一个 tick（用钳制后的 machine 坐标，
            # 保证窗口不拖出工作区）
            self.move(self._to_global(self.machine.x, self.machine.y))
        event.accept()

    def mouseReleaseEvent(self, event):
        # v0.1 已知边缘情况（v0.2 仍未定义，见 README 已知问题）：暂停中
        # 松手时 tick 为 no-op，角色停在半空 FALLING，恢复暂停后落地。
        if (event.button() == Qt.MouseButton.LeftButton
                and self._drag_offset is not None):
            self._drag_offset = None
            pressed_ms = (time.monotonic() - self._press_ts) * 1000.0
            if not self._drag_moved and pressed_ms < POKE_MAX_MS:
                # 短按且无有效位移 = 戳：不调 drag_end()（不触发下落），
                # machine.poke() 内部会回退到拖拽前状态并播放反应
                self.machine.poke()
            else:
                self.machine.drag_end()
            event.accept()

    def contextMenuEvent(self, event):
        """右键菜单（spec §2.3）：每次打开都重建，实时反映数值与暂停状态。"""
        status = self.machine.status
        menu = QMenu(self)
        # 喂食：吃撑（fullness > 90）时置灰并改文案
        feed_action = menu.addAction(
            "喂食" if status.can_feed else "喂食（吃撑了）")
        feed_action.setEnabled(status.can_feed)
        feed_action.triggered.connect(lambda: self.machine.feed())
        # 状态展示项：不可点击，只显示当前数值
        status_action = menu.addAction(
            f"心情 {status.mood:.0f} · 饱腹 {status.fullness:.0f}")
        status_action.setEnabled(False)
        menu.addSeparator()
        pause_action = menu.addAction(
            "恢复" if self.machine.paused else "暂停")
        # set_paused 会经状态机回调同步托盘勾选/文字（见 tray.sync_pause）
        pause_action.triggered.connect(
            lambda: self.machine.set_paused(not self.machine.paused))
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self._quit)
        menu.exec(event.globalPos())

    def _quit(self) -> None:
        """退出入口：状态落盘由 main.py 的 aboutToQuit 兜底，这里只退。"""
        if self._on_quit is not None:
            self._on_quit()
