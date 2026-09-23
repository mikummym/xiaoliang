"""开机自启测试：命令行构造为纯函数；注册表读写用临时键名做往返实测。"""
import sys
from pathlib import Path

import pytest

from xiaoliang import autostart


def test_command_source_mode_points_to_main_py():
    """源码运行态：pythonw（或 python）+ main.py 绝对路径，均带引号。"""
    if getattr(sys, "frozen", False):
        pytest.skip("仅源码态")
    cmd = autostart.autostart_command()
    assert cmd.lower().endswith('main.py"') or "main.py" in cmd
    assert cmd.startswith('"')


def test_command_frozen_mode_is_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\apps\xiaoliang.exe")
    assert autostart.autostart_command() == '"C:\\apps\\xiaoliang.exe"'


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 注册表")
def test_registry_roundtrip(monkeypatch):
    """用临时键名做 写→读→删→读 往返，不碰真实的 xiaoliang 键。"""
    monkeypatch.setattr(autostart, "APP_NAME", "xiaoliang_pytest_tmp")
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(True) is True
    assert autostart.is_enabled() is True
    assert autostart.set_enabled(False) is True
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(False) is True   # 删除不存在的值幂等
