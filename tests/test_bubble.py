"""BubbleWidget 语音气泡回归测试（offscreen 跑，不需要真屏幕）。

覆盖设计约定的四条硬行为：到时自隐、跟随锚点、贴屏幕边钳位/翻到脚下、
鼠标点穿+不抢焦点。排版（折行/尺寸）只断言不变式，不断言具体像素——
offscreen 的字体度量与真机不同。
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 必须在 Qt 导入前设置

import pytest
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from xiaoliang.bubble import MAX_W, BubbleWidget


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    return qapp


class _Anchor:
    """可变锚点：测试里改 rect，气泡跟随计时器应读到新位置。"""

    def __init__(self, rect: QRect):
        self.rect = rect

    def __call__(self) -> QRect:
        return self.rect


def test_say_shows_then_auto_hides(app):
    """say() 立刻显示；到时（ms 覆写提速）自动隐藏。"""
    b = BubbleWidget(anchor=_Anchor(QRect(400, 400, 128, 128)))
    b.say("该起来活动一下啦", ms=60)
    assert b.isVisible()
    QTest.qWait(200)  # > ms=60，自隐定时器应已触发
    assert not b.isVisible()


def test_bubble_sits_above_pet_and_follows_anchor(app):
    """气泡摆在她头顶正上方；锚点移动后跟随计时器把气泡带过去。"""
    anchor = _Anchor(QRect(400, 600, 128, 128))
    b = BubbleWidget(anchor=anchor)
    b.say("整点报时", ms=5000)
    # 头顶摆位：气泡底边（含尾巴）≈ 锚点顶边 - 2
    assert b.y() + b.height() == pytest.approx(anchor.rect.top() - 2, abs=1)
    # 水平对准她中心
    assert b.x() + b.width() // 2 == pytest.approx(
        anchor.rect.center().x(), abs=1)

    anchor.rect = QRect(700, 500, 128, 128)  # 她走开了
    QTest.qWait(250)                          # > FOLLOW_MS=100
    assert b.x() > 500, "气泡没跟着锚点移动"
    assert b.y() + b.height() == pytest.approx(500 - 2, abs=1)
    b.hide()


def test_no_room_above_flips_below_pet(app):
    """她贴屏幕顶（爬墙/坐顶）时头顶没空间：气泡翻到脚下、尾巴朝上。"""
    screen = QGuiApplication.primaryScreen().availableGeometry()
    anchor = _Anchor(QRect(screen.center().x(), screen.top(), 128, 128))
    b = BubbleWidget(anchor=anchor)
    b.say("我在顶上", ms=5000)
    assert b.y() == pytest.approx(anchor.rect.bottom() + 2, abs=1)
    b.hide()


def test_clamped_to_screen_horizontally(app):
    """她在屏幕最左/最右边缘时，气泡钳回屏内（宁可尾巴偏心不出屏）。"""
    screen = QGuiApplication.primaryScreen().availableGeometry()
    for edge_x in (screen.left(), screen.right() - 128):
        b = BubbleWidget(anchor=_Anchor(QRect(edge_x, 600, 128, 128)))
        b.say("贴着边说话也要看得见", ms=5000)
        assert b.x() >= screen.left()
        assert b.x() + b.width() <= screen.right() + 1
        b.hide()


def test_long_text_wraps_within_max_width(app):
    """长句折行：宽度不超 MAX_W、高度超过单行（说明真的折了）。"""
    b = BubbleWidget(anchor=_Anchor(QRect(400, 600, 128, 128)))
    short = BubbleWidget(anchor=_Anchor(QRect(400, 600, 128, 128)))
    short.say("短", ms=5000)
    b.say("你已经连续坐了很久啦，起来活动一下肩颈，顺便看看远处放松眼睛",
          ms=5000)
    assert b.width() <= MAX_W
    assert b.height() > short.height()
    b.hide()
    short.hide()


def test_click_through_and_no_focus_steal(app):
    """鼠标点穿 + 弹出不抢焦点：气泡盖着她时不能挡戳/拖，不能打断输入。"""
    b = BubbleWidget(anchor=_Anchor(QRect(400, 600, 128, 128)))
    assert b.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    assert b.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert b.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
