"""屏幕布局查询：邻屏检测（spec §4）。

纯几何函数 neighbor_edges 不依赖 Qt（可单测）；Qt 薄层把 QScreen
工作区换算成矩形元组后交给纯函数。坐标沿用 Qt QRect 约定：
(left, top, right, bottom)，right/bottom 为包含式（= left+width-1），
因此物理紧邻的两屏边缘坐标差 1，默认容差 tol=1。
"""
from PySide6.QtGui import QGuiApplication


def neighbor_edges(rect: tuple, others: list, tol: int = 1) -> set:
    """rect 的左/右边缘外是否紧邻其他屏幕。

    rect/others 元素：(left, top, right, bottom) 全局坐标元组。
    返回 {-1, 1} 的子集：-1 = 左缘有邻屏，1 = 右缘有邻屏。
    相邻判定：邻屏对应边缘坐标与 rect 边缘差 ≤ tol，且垂直范围有交集
    （上下完全错开的屏即使 x 相邻也不算——小凉不可能走过去）。
    """
    left, top, right, bottom = rect
    result = set()
    for other in others:
        if tuple(other) == tuple(rect):
            continue                       # 跳过自身
        ol, ot, orr, ob = other
        if not (ot < bottom and ob > top):
            continue                       # 垂直无交集
        if abs(orr - left) <= tol:
            result.add(-1)                 # 邻屏右缘贴着我左缘
        if abs(ol - right) <= tol:
            result.add(1)                  # 邻屏左缘贴着我右缘
    return result


def _workarea_rects() -> tuple:
    """(主屏工作区矩形, 所有屏工作区矩形列表)。"""
    screens = QGuiApplication.screens()
    primary = QGuiApplication.primaryScreen().availableGeometry()
    rects = []
    for s in screens:
        g = s.availableGeometry()
        rects.append((g.left(), g.top(), g.right(), g.bottom()))
    return (primary.left(), primary.top(),
            primary.right(), primary.bottom()), rects


def wrap_and_cling_edges() -> tuple:
    """返回 (可穿越边缘集合, 需 mask 裁剪的边缘集合)。

    可穿越 = 无邻屏的边缘（尽头才是"传送门"，有邻屏的边缘是"墙"，
    走到就停——spec §1.4/§4）；需 mask = 有邻屏的边缘（贴边推出的
    墨水会画到邻屏上，需 setMask 裁剪——spec §4.2）。
    两者互为补集，供 main.py 一次性取用。
    """
    primary, rects = _workarea_rects()
    cling = neighbor_edges(primary, rects)
    wrap = {-1, 1} - cling
    return wrap, cling
