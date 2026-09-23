"""screen_info 纯几何逻辑测试（Qt 薄层留给 GUI 验收，spec §4）。"""
from xiaoliang.screen_info import neighbor_edges

# 主屏工作区 1920x1080（Qt 包含式坐标：right = left+width-1）
PRIMARY = (0, 0, 1919, 1079)


def test_single_screen_no_neighbors():
    assert neighbor_edges(PRIMARY, [PRIMARY]) == set()


def test_neighbor_on_right():
    right = (1920, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, right]) == {1}


def test_neighbor_on_left():
    left = (-1920, 0, -1, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, left]) == {-1}


def test_neighbors_both_sides():
    left = (-1920, 0, -1, 1079)
    right = (1920, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, left, right]) == {-1, 1}


def test_gap_beyond_tolerance_not_neighbor():
    """间距 2px（超出 tol=1）：不算相邻。"""
    gapped = (1921, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, gapped]) == set()


def test_vertical_disjoint_not_neighbor():
    """右上方远处的屏（垂直无交集）：不算相邻。"""
    above = (1920, -2000, 3839, -1000)
    assert neighbor_edges(PRIMARY, [PRIMARY, above]) == set()


def test_partial_vertical_overlap_counts():
    """垂直部分重叠（如邻屏分辨率更矮）：算相邻。"""
    short = (1920, 500, 3839, 900)
    assert neighbor_edges(PRIMARY, [PRIMARY, short]) == {1}


def test_touching_one_pixel_is_neighbor():
    """Qt 包含式坐标下相邻屏 left - 主屏 right == 1：tol=1 命中。"""
    touch = (1920, 0, 3839, 1079)
    assert neighbor_edges(PRIMARY, [PRIMARY, touch], tol=1) == {1}
