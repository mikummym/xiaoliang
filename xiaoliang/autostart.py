"""开机自启：winreg 读写 HKCU Run 键（spec §5.1）。

只影响当前用户（HKCU），无需管理员权限。真相源 = 注册表本身：
用户可能在任务管理器"启动"页启用/禁用，config.json 不存副本，
避免两份状态漂移。注册表被组策略锁死等异常 → 记日志返回 None/False，
托盘菜单置灰，程序照常跑。
"""
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

APP_NAME = "xiaoliang"          # Run 键下的值名（测试会 monkeypatch）
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command() -> str:
    """Run 键命令行：打包态 = 带引号 exe 路径；源码态 = pythonw + main.py。

    源码态优先 pythonw.exe（无控制台窗口）；venv 里没有则退回 python.exe。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" "{main_py}"'


def is_enabled():
    """读 Run 键：True/False；注册表不可读（异常）返回 None（菜单置灰）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False              # 值不存在 = 未启用（正常情况）
    except OSError as exc:
        logger.warning("读开机自启注册表失败: %s", exc)
        return None


def set_enabled(enable: bool) -> bool:
    """写/删 Run 键，返回是否成功（失败记日志，托盘勾选回滚）。"""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ,
                                  autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass          # 本来就没有 = 删除幂等成功
        return True
    except OSError as exc:
        logger.warning("写开机自启注册表失败: %s", exc)
        return False