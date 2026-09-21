"""配置读写：config.json 加载/保存，缺失或损坏时回退默认值。"""
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "scale": 2,
    "walk_speed": 60.0,
    "paused": False,
}


def default_config_path() -> Path:
    """config.json 位置：打包后与 exe 同目录，源码运行时在项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"


def load_config(path: Path) -> dict:
    """加载配置；文件不存在/损坏时返回默认配置，只保留已知键。"""
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
        if key in data:
            cfg[key] = data[key]
    return cfg


def save_config(cfg: dict, path: Path) -> None:
    """把配置写为 UTF-8 JSON。"""
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
