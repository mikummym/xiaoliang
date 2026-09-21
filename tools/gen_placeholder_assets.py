"""生成占位像素素材：一个蓝发小人（后续可替换为 AI 生成的正式素材）。

用法（项目根目录）：
    .venv\\Scripts\\python tools\\gen_placeholder_assets.py

输出到 assets\\：每个动作一张横向排列的 sprite sheet（帧尺寸 64x64，透明背景），
外加描述帧数/帧率的 manifest.json。
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

FRAME = 64
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

HAIR = (110, 150, 235, 255)   # 蓝发
SKIN = (245, 220, 200, 255)   # 皮肤
CLOTH = (60, 64, 80, 255)     # 深色衣服
EYE = (40, 40, 50, 255)       # 眼睛/鞋


def draw_pet(d: ImageDraw.ImageDraw, *, leg_offset: int = 0,
             arms_up: bool = False, body_dy: int = 0) -> None:
    """在单帧内画小人。leg_offset: 走路腿部错位; arms_up: 举手; body_dy: 呼吸起伏。"""
    y = body_dy
    d.rectangle([24, 12 + y, 40, 24 + y], fill=HAIR)    # 头顶
    d.rectangle([22, 16 + y, 25, 32 + y], fill=HAIR)    # 左侧垂发
    d.rectangle([39, 16 + y, 42, 32 + y], fill=HAIR)    # 右侧垂发
    d.rectangle([26, 20 + y, 38, 30 + y], fill=SKIN)    # 脸
    d.point((29, 25 + y), fill=EYE)                     # 左眼
    d.point((35, 25 + y), fill=EYE)                     # 右眼
    d.rectangle([26, 31 + y, 38, 44 + y], fill=CLOTH)   # 身体
    if arms_up:                                         # 手臂（举起/放下）
        d.rectangle([22, 22 + y, 25, 32 + y], fill=SKIN)
        d.rectangle([39, 22 + y, 42, 32 + y], fill=SKIN)
    else:
        d.rectangle([23, 32 + y, 25, 42 + y], fill=SKIN)
        d.rectangle([39, 32 + y, 41, 42 + y], fill=SKIN)
    d.rectangle([27 + leg_offset, 45 + y, 30 + leg_offset, 52 + y], fill=CLOTH)
    d.rectangle([34 - leg_offset, 45 + y, 37 - leg_offset, 52 + y], fill=CLOTH)
    d.rectangle([26 + leg_offset, 52 + y, 31 + leg_offset, 54 + y], fill=EYE)
    d.rectangle([33 - leg_offset, 52 + y, 38 - leg_offset, 54 + y], fill=EYE)


def make_sheet(frames_params: list[dict], out_name: str) -> int:
    """按每帧参数画一张 sprite sheet，返回帧数。"""
    sheet = Image.new("RGBA", (FRAME * len(frames_params), FRAME), (0, 0, 0, 0))
    for i, params in enumerate(frames_params):
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        draw_pet(ImageDraw.Draw(frame), **params)
        sheet.paste(frame, (i * FRAME, 0), frame)
    sheet.save(ASSETS_DIR / out_name)
    return len(frames_params)


def main() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    specs = {
        "idle": ([{"body_dy": 0}, {"body_dy": 0}, {"body_dy": 1}, {"body_dy": 1}], 3),
        "walk_right": ([{"leg_offset": o} for o in (-2, -1, 0, 1, 2, 1)], 8),
        "dragged": ([{"arms_up": True, "leg_offset": 1},
                     {"arms_up": True, "leg_offset": -1}], 6),
        "falling": ([{"arms_up": True, "body_dy": 0},
                     {"arms_up": True, "body_dy": 1}], 6),
    }
    manifest = {"frame_size": [FRAME, FRAME], "actions": {}}
    for name, (frames_params, fps) in specs.items():
        file_name = f"{name}.png"
        count = make_sheet(frames_params, file_name)
        manifest["actions"][name] = {"file": file_name, "frames": count, "fps": fps}

    # walk_left 由 walk_right 逐帧镜像生成
    right = Image.open(ASSETS_DIR / "walk_right.png")
    n_frames = right.width // FRAME
    left = Image.new("RGBA", right.size, (0, 0, 0, 0))
    for i in range(n_frames):
        box = (i * FRAME, 0, (i + 1) * FRAME, FRAME)
        left.paste(ImageOps.mirror(right.crop(box)), (i * FRAME, 0))
    left.save(ASSETS_DIR / "walk_left.png")
    manifest["actions"]["walk_left"] = {
        "file": "walk_left.png", "frames": n_frames,
        "fps": manifest["actions"]["walk_right"]["fps"]}

    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成素材到 {ASSETS_DIR}:")
    for name, a in sorted(manifest["actions"].items()):
        print(f"  {name}: {a['file']} {a['frames']} 帧 @ {a['fps']} fps")


if __name__ == "__main__":
    main()
