"""语音气泡窗口：把提醒语音的文本以对话框气泡形式显示在小凉头顶。

为什么是独立顶层窗口而不是画进宠物窗口：宠物窗口的 128 帧尺寸、贴边
推出量（CLING_MARGIN_LOGICAL）、镜像几何全部以窗口尺寸为前提，塞进气
泡要改窗口大小并重算整套贴边数学（回归测试全跟着动）；独立窗口零侵入，
宠物窗口一行不改。

行为约定：
- 跟随：每 FOLLOW_MS 按锚点（小凉窗口全局矩形）重新摆位，她边爬边说
  也不脱节；优先头顶，头顶出屏幕（贴顶爬墙时）改放脚下、尾巴朝上
- 自动消失：时长按字数估（MS_PER_CHAR/字、最少 MIN_MS），与 TTS 念完
  的节奏大致同步；新一句顶掉旧一句（重计时重排版）
- 不挡操作：WA_TransparentForMouseEvents 鼠标点穿（气泡盖着她时照样
  能戳/拖）；WA_ShowWithoutActivating 弹出时不抢键盘焦点
- 开关语义：分类开关（sit_reminder/hourly_chime）同时管语音和气泡
  （main.on_reminder 接线）；muted 只静音、气泡照弹（静音≠不想看）
"""
from PySide6.QtCore import QPointF, QRect, Qt, QTimer
from PySide6.QtGui import (QGuiApplication, QPainter, QPen, QColor,
                           QPolygonF)
from PySide6.QtWidgets import QWidget

MAX_W = 260          # 气泡最大宽度（逻辑像素）：再宽就横出屏幕观感差
PAD = 10             # 文字到气泡边的内边距
RADIUS = 10          # 圆角半径
TAIL_H = 8           # 指向小凉的小尾巴高度
TAIL_W = 14          # 小尾巴底边宽度
MS_PER_CHAR = 200    # 显示时长按字数估：与 TTS 中文语速大致同步
MIN_MS = 3000        # 再短的话也至少显示 3 秒，来得及读
FOLLOW_MS = 100      # 跟随重摆位间隔：比宠物 30fps 慢足够、比肉眼快足够

FILL = QColor(255, 255, 255, 240)   # 近白微透：桌面任何底色上都读得清
BORDER = QColor(110, 110, 110)
TEXT = QColor(40, 40, 40)


class BubbleWidget(QWidget):
    """圆角矩形 + 小尾巴的对话气泡；say() 一句，到时自隐。"""

    def __init__(self, anchor):
        """anchor：无参 callable，返回小凉窗口的全局 QRect（接线方传
        window.frameGeometry 即可）；气泡据此摆位与跟随。"""
        super().__init__(None,
                         Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # 鼠标点穿：气泡常悬在她头顶，不能挡住戳/拖她的手感
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        # 弹出时不抢焦点：打字/游戏途中被提醒不应打断当前输入
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._anchor = anchor
        self._lines: list = []
        self._tail_up = False   # 尾巴朝上=气泡在她脚下（头顶没空间时）
        self._tail_x = 0        # 尾巴尖的窗口内 x：对准她中心
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)
        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(FOLLOW_MS)
        self._follow_timer.timeout.connect(self._reposition)

    def say(self, text: str, ms: int | None = None) -> None:
        """显示一句气泡：排版 → 摆位 → 计时自隐；新句顶掉旧句。"""
        self._lines = self._wrap(text)
        self._resize_to_text()
        if ms is None:
            ms = max(MIN_MS, MS_PER_CHAR * len(text))
        self._reposition()
        self.show()
        self._follow_timer.start()
        self._hide_timer.start(ms)

    def _wrap(self, text: str) -> list:
        """按 MAX_W 内宽逐字贪心折行。PySide6 未暴露 QFontMetrics.wrapText，
        自己折：中文提醒文本任意字间可断行，逐字量宽即可（ASCII 单词
        理论上会被腰斩，但提醒文案是纯中文，不为它上单词边界规则）。"""
        fm = self.fontMetrics()
        inner = MAX_W - 2 * PAD
        lines: list = []
        cur = ""
        for ch in text:
            if ch == "\n":
                lines.append(cur)
                cur = ""
            elif cur and fm.horizontalAdvance(cur + ch) > inner:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
        return lines or [""]

    def _resize_to_text(self) -> None:
        """气泡尺寸 = 折行后文字块 + 内边距 + 尾巴高。"""
        fm = self.fontMetrics()
        widths = [fm.horizontalAdvance(line) for line in self._lines]
        w = min(MAX_W, max(widths) + 2 * PAD)
        h = 2 * PAD + len(self._lines) * fm.lineSpacing() + TAIL_H
        self.resize(w, h)

    def _reposition(self) -> None:
        """按锚点摆位：优先头顶、出屏改脚下；水平对准她中心并钳回屏内。"""
        target: QRect = self._anchor()
        screen = QGuiApplication.primaryScreen().availableGeometry()
        y = target.top() - self.height() - 2
        self._tail_up = y < screen.top()   # 贴顶爬墙时头顶没空间
        if self._tail_up:
            y = target.bottom() + 2
        x = target.center().x() - self.width() // 2
        x = min(max(x, screen.left()), screen.right() - self.width())
        # 尾巴尖对准她水平中心：气泡被钳位时尾巴偏到气泡内侧相应位置
        self._tail_x = min(max(target.center().x() - x,
                               RADIUS + TAIL_W // 2),
                           self.width() - RADIUS - TAIL_W // 2)
        self.move(int(x), int(y))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(BORDER, 1.5)
        p.setPen(pen)
        p.setBrush(FILL)
        # 身体矩形：给尾巴让出 TAIL_H（尾巴朝下占底边、朝上占顶边）
        r = self.rect()
        body = (r.adjusted(0, TAIL_H, 0, 0) if self._tail_up
                else r.adjusted(0, 0, 0, -TAIL_H))
        # 先画尾巴再画身体：身体填充盖住两者接缝，观感是一体轮廓
        if self._tail_up:
            tip = QPointF(self._tail_x, body.top() - TAIL_H)
            base_y = body.top() + 2
        else:
            tip = QPointF(self._tail_x, body.bottom() + TAIL_H)
            base_y = body.bottom() - 2
        # 尾巴三角形必须传 QPolygonF：裸元组列表会命中 PySide6 的
        # drawPolygon 重载歧义，异步绘制时段错误崩溃（实测）
        p.drawPolygon(QPolygonF([
            QPointF(self._tail_x - TAIL_W // 2, base_y),
            QPointF(self._tail_x + TAIL_W // 2, base_y), tip]))
        p.drawRoundedRect(body, RADIUS, RADIUS)
        # 文字逐行画在身体内：AlignHCenter 负责居中，行高与排版一致
        fm = self.fontMetrics()
        p.setPen(QPen(TEXT))
        y = body.top() + PAD
        for line in self._lines:
            p.drawText(body.left() + PAD, y,
                       body.width() - 2 * PAD, fm.lineSpacing(),
                       Qt.AlignmentFlag.AlignHCenter
                       | Qt.AlignmentFlag.AlignTop, line)
            y += fm.lineSpacing()
        p.end()
