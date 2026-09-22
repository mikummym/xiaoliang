"""配置读写：config.json 加载/保存，缺失或损坏时回退默认值。"""
import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "scale": 2,
    "walk_speed": 60.0,
    "paused": False,
    "sleep_start": "23:00",   # 睡眠时段起点（含），HH:MM 24 小时制
    "sleep_end": "07:00",     # 睡眠时段终点（不含）；start>end 表示跨午夜
}


def _coerce_scale(v):
    """scale 必须是正整数（bool 不算；整数值的 float 收敛为 int）。"""
    if isinstance(v, bool):
        raise ValueError("scale 不能是布尔值")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if not isinstance(v, int):
        raise ValueError(f"scale 必须是整数，收到 {type(v).__name__}")
    if v < 1:
        raise ValueError(f"scale 必须 >= 1，收到 {v}")
    return v


def _coerce_walk_speed(v):
    """walk_speed 必须是正数（bool 不算），统一收敛为 float。"""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"walk_speed 必须是数字，收到 {type(v).__name__}")
    v = float(v)
    if v <= 0:
        raise ValueError(f"walk_speed 必须 > 0，收到 {v}")
    return v


def _coerce_paused(v):
    """paused 必须是布尔值。"""
    if not isinstance(v, bool):
        raise ValueError(f"paused 必须是布尔值，收到 {type(v).__name__}")
    return v


# HH:MM 24 小时制（spec §2.5）：00:00–23:59，分钟 00–59
_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _coerce_hhmm(v):
    """sleep_start/sleep_end 必须是合法 'HH:MM' 字符串。"""
    if not isinstance(v, str) or not _HHMM_RE.match(v):
        raise ValueError(f"必须是 'HH:MM' 格式字符串，收到 {v!r}")
    return v


_COERCE = {
    "scale": _coerce_scale,
    "walk_speed": _coerce_walk_speed,
    "paused": _coerce_paused,
    "sleep_start": _coerce_hhmm,
    "sleep_end": _coerce_hhmm,
}


def default_config_path() -> Path:
    """config.json 位置：打包后与 exe 同目录，源码运行时在项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"


def load_config(path: Path) -> dict:
    """加载配置；文件不存在/损坏时返回默认配置，只保留已知键。

    单个键的值类型/取值非法（如 "scale": "3x"）时，该键回退默认值并记
    警告（规格 §5：损坏配置回退默认），其余合法键照常生效。
    """
    cfg = dict(DEFAULT_CONFIG)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("配置文件 %s 读取失败，使用默认配置: %s", path, exc)
        return cfg
    if not isinstance(data, dict):
        logger.warning("配置文件 %s 不是 JSON 对象，使用默认配置", path)
        return cfg
    for key in DEFAULT_CONFIG:
        if key not in data:
            continue
        try:
            cfg[key] = _COERCE[key](data[key])
        except (ValueError, TypeError) as exc:
            logger.warning("配置项 %s=%r 非法，使用默认值 %r: %s",
                           key, data[key], DEFAULT_CONFIG[key], exc)
    # 跨键校验：起止相等 = 空窗口（永不睡觉），视为非法配置，双双回退默认
    # （spec §7：start==end 视为不睡觉，校验时回退）
    if cfg["sleep_start"] == cfg["sleep_end"]:
        logger.warning("sleep_start 与 sleep_end 相同（%s），回退默认睡眠时段",
                       cfg["sleep_start"])
        cfg["sleep_start"] = DEFAULT_CONFIG["sleep_start"]
        cfg["sleep_end"] = DEFAULT_CONFIG["sleep_end"]
    return cfg


def needs_migration(path: Path) -> bool:
    """检测配置文件是否为缺少新键的旧版本（如 v0.1 的文件没有 sleep_start/sleep_end）。

    只有"文件存在、是合法 JSON 对象、且缺 DEFAULT_CONFIG 的键"才算需要迁移，
    main.py 据此把补全后的配置回写，方便用户发现并编辑新配置项。
    文件不存在（走生成默认配置的路径）或损坏/非对象（load_config 已回退
    默认值）时返回 False——这两种情况不应再动用户的文件。
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    return not set(DEFAULT_CONFIG) <= set(data)


def save_config(cfg: dict, path: Path) -> None:
    """把配置写为 UTF-8 JSON。"""
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
