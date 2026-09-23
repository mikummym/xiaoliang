"""桌宠窗口：透明置顶无边框，渲染当前帧并把鼠标事件转发给状态机。

状态机坐标以工作区左上角为原点（规格 3.3）；
全局屏幕坐标 = origin（availableGeometry().topLeft()）+ 状态机坐标。

v0.2 新增（spec §2.3）：
- 戳 vs 拖拽判定：按压 <250ms 且位移 <5px = 戳（machine.poke()），
  否则走 v0.1 拖拽流程（machine.drag_end() 下落）
- 右键菜单：喂食（吃撑置灰）/ 状态展示 / 暂停·恢复 / 退出
- 悬停 tooltip：每秒刷新"心情 😊N · 饱腹 🍚N · 状态中文"
- 攀爬渲染：爬下 = 帧序倒放，左壁 = 水平镜像（get_frame kwargs）
- 坐顶姿势：面向墙 / 背靠墙两种随机姿势（背靠墙水平镜像复用同一组
  sitting_top 帧，不新增任何素材）

v0.3 新增（spec §4.2 等）：
- REMINDING 渲染：久坐提醒/整点报时播"伸懒腰"动画，播完回原状态
- 戳音效：machine.poke() 受理（返回 True）才播音效，暂停时 poke 拒绝
  返回 False 即静音，保证"暂停 = 完全无响应"语义
- 多屏贴边 setMask 裁剪：贴边侧有相邻屏幕时 Windows 不按单屏边界裁剪
  窗口，推出的搁板端头/脚部墨水会画到邻屏——用 setMask 裁掉越界条带
"""
import math
import random
import time

from PySide6.QtCore import QElapsedTimer, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QPainter, QPixmap, QRegion
from PySide6.QtWidgets import QMenu, QToolTip, QWidget

from .sprite import SpriteManager
from .state_machine import PetStateMachine, State

FPS = 30

# 戳判定阈值（spec §2.3）：按压时长与位移都必须小于该值才算"戳"
POKE_MAX_MS = 250
POKE_MAX_PX = 5.0

# 攀爬/坐姿贴边的渲染补偿（逻辑像素）：正式素材是水平居中的正面立绘，
# 128 帧里内容占第 36..91 列、两侧各 36 列空白——不补偿时角色贴边看起来
# 悬空在离屏幕边缘 36 逻辑像素处。把窗口向墙外推出这段空白（×scale、
# ×climb_wall 方向），身体就正好贴住屏幕边缘。
CLING_MARGIN_LOGICAL = 36

# 背靠墙坐姿的贴边推出量（逻辑像素）：坐姿与攀爬共用同一居中素材，
# 左右空白对称，推出量与 CLING_MARGIN_LOGICAL 相同。
CLING_MARGIN_BACK = 36

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
    State.REMINDING: "remind",
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
    State.REMINDING: "伸懒腰",
}


class PetWindow(QWidget):
    def __init__(self, machine: PetStateMachine, sprites: SpriteManager,
                 origin: QPoint | None = None, on_quit=None, *,
                 sound=None, mask_edges=None):
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
        # 贴边推出列数（逻辑像素，0 = 不贴边）：用数值而非布尔，因为顶边
        # 两种坐姿推出量不同（面向墙 21 / 背靠墙 17），且在壁上被戳/跳下
        # 的瞬间 machine.x 仍吸附在墙边，必须跨帧沿用同一推出量，立即归零
        # 窗口会横跳 K*scale 物理像素
        self._cling_margin = 0
        # ── v0.3 注入：声音引擎（戳音效）与需 mask 裁剪的边缘集合 ──
        # sound 可为 None（测试/静音环境）；mask_edges = 贴边侧有相邻
        # 屏幕的边缘（{-1,1} 子集），由 screen_info 计算、main.py 注入
        self._sound = sound
        self._mask_edges = set(mask_edges or ())
        # mask 是否已设置：只在需要↔不需要切换或推出量变化时调
        # setMask/clearMask（窗口重组合有成本，不能每帧做）
        self._mask_on = False
        self._mask_margin_px = -1
        # 本次坐顶的姿势：True=面向墙、False=背靠墙，进入 SITTING_TOP 的
        # 瞬间随机掷一次，坐姿期间保持不变
        self._sit_facing_wall = True
        # 是否已处于坐姿：检测"进入坐姿的瞬间"（上升沿），保证只掷一次
        self._in_sitting = False
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

    def set_mask_edges(self, edges: set) -> None:
        """屏幕热插拔时刷新需 mask 的边缘集合（main.py 调，spec §4.2）。"""
        self._mask_edges = set(edges)
        if self._mask_on:            # 强制下次 tick 重算 mask
            self.clearMask()
            self._mask_on = False
            self._mask_margin_px = -1

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
        # 攀爬渲染：爬下倒放帧序；镜像规则见下。坐姿的 climb_wall 依然
        # 有效——SITTING_TOP 只会从 CLIMBING 到顶进入，记录的是哪面墙
        climbing = self.machine.state is State.CLIMBING
        sitting = self.machine.state is State.SITTING_TOP
        # 进入坐姿的瞬间掷一次姿势（面向墙/背靠墙 50/50），坐姿期间保持
        if sitting and not self._in_sitting:
            self._sit_facing_wall = random.random() < 0.5
            self._in_sitting = True
        elif not sitting:
            self._in_sitting = False
        # 镜像规则（真值表）：
        # - 攀爬：左壁（climb_wall<0）镜像，右壁原样——面向墙
        # - 坐姿·面向墙：与攀爬同向，左壁才镜像（脸/鞋尖朝墙）
        # - 坐姿·背靠墙：与攀爬反向，右壁才镜像——镜像后后背落在第 46 列，
        #   推出 17 列（CLING_MARGIN_BACK）后背正好贴住屏幕右缘；左壁则
        #   不镜像，原帧后背就在第 17 列，同样推出 17 列贴住屏幕左缘
        if climbing:
            mirror = self.machine.climb_wall < 0
        elif sitting:
            mirror = (self._sit_facing_wall == (self.machine.climb_wall < 0))
        else:
            mirror = False
        self._pixmap = self.sprites.get_frame(
            action, self._anim_ms,
            reverse=climbing and self.machine.climb_direction == "down",
            mirror=mirror)
        # 攀爬/坐姿贴屏幕边缘：把窗口向墙外推出素材墙侧的空白列
        #（_cling_margin 为逻辑像素，×scale 换算、×climb_wall 定向：
        # 右壁推出屏幕右缘、左壁推出左缘），手/鞋尖/后背正好搭在屏幕边缘。
        # 纯渲染层偏移，不改状态机坐标；三段逻辑决定推出列数：
        if climbing:
            # 攀爬：墙侧第 43..63 共 21 列空白，推出 21 列手搭屏幕边缘
            self._cling_margin = CLING_MARGIN_LOGICAL
        elif sitting:
            # 坐顶按姿势取推出量：面向墙 = 鞋尖/脸在第 42 列贴边（21），
            # 背靠墙 = 镜像帧后背在第 46 列贴边（17）。爬→坐切换若掷中
            # 背靠墙，推出量 21→17 造成的 8 物理像素位移与换姿势同帧
            # 发生，被姿势切换本身掩盖，看起来不突兀
            self._cling_margin = (CLING_MARGIN_LOGICAL if self._sit_facing_wall
                                  else CLING_MARGIN_BACK)
        elif self.machine.state in (State.POKE_REACT, State.FALLING,
                                    State.EATING, State.REMINDING):
            # 在壁上被戳/空中进食/壁上被提醒/跳下的瞬间 machine.x 仍吸附
            # 在墙边，推出量必须沿用进入前的值不能归零，否则窗口一帧横跳
            # K*scale；落地/播完回 IDLE 等地面状态后由下一分支清除。
            # EATING/REMINDING 发生在地面时 _cling_margin 本来就是 0，
            # pass 保持不变，无副作用
            pass
        else:
            # IDLE/WALKING/DRAGGED/SLEEPING/EATING/WOKEN：不贴边，推出量归零
            self._cling_margin = 0
        # POKE_REACT/FALLING 素材的角色占帧内第 22..42 逻辑列：推出量为
        # 21 或 17 时，两壁可见带（右壁 0..63-K、左壁镜像前 K..63）都完整
        # 覆盖 22..42，保持偏移不会把角色裁掉，无需额外处理
        cling_off = (self._cling_margin * self.sprites.scale
                     * self.machine.climb_wall)
        # ── v0.3 修复③（spec §4.2）：贴边侧有相邻屏幕时，Windows 不按
        # 单屏边界裁剪窗口，推出的搁板端头/脚部墨水会画到邻屏上——用
        # setMask 裁掉越界条带。只在边缘归属/推出量变化时重设 mask，
        # 不是每帧操作。宽度 = 推出逻辑列 × 素材放大 × 设备像素比
        # （widget 坐标在高 DPI 下按设备像素解释，100% 缩放时 dpr=1）
        need_mask = (self._cling_margin > 0
                     and self.machine.climb_wall in self._mask_edges)
        if need_mask:
            margin_px = int(round(self._cling_margin * self.sprites.scale
                                  * self.devicePixelRatioF()))
            if not self._mask_on or margin_px != self._mask_margin_px:
                w, h = int(self.width() * self.devicePixelRatioF()), \
                    int(self.height() * self.devicePixelRatioF())
                if self.machine.climb_wall > 0:
                    # 右壁：窗口右侧 margin_px 越界 → 裁掉右边条带
                    region = QRegion(0, 0, w - margin_px, h)
                else:
                    # 左壁：裁掉左边条带
                    region = QRegion(margin_px, 0, w - margin_px, h)
                self.setMask(region)
                self._mask_on = True
                self._mask_margin_px = margin_px
        elif self._mask_on:
            self.clearMask()
            self._mask_on = False
            self._mask_margin_px = -1
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
                # machine.poke() 内部会回退到拖拽前状态并播放反应。
                # v0.3：poke() 返回是否受理（暂停时 False）——受理才播
                # 音效，保证"暂停 = 完全无响应"的语义（spec §1.1）
                if self.machine.poke() and self._sound is not None:
                    self._sound.play_poke()
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
