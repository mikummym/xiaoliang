"""从 4 帧攀爬源图生成 climbing sheet（正式攀爬素材第一单）。

源图：assets/src/climbing2.png —— 透明背景 PNG、4 帧横排、角色朝右的
攀爬循环。产物与其余动作同约定：128x128 帧、脚底踩 y=126、透明背景横排
sheet；帧数/帧率写回 manifest.json（4 帧 @8fps，与 B 方案同值）。

与 gen_walk_from_photos.py 流水线的差异点（为什么单独一个脚本）：
  1. 源图已是透明背景 PNG：不需要泛洪抠底，也不需要白边光晕清理（那两
     步分别服务于黑底/白底 JPG 源图）；
  2. 水平方向**右对齐**而不是居中：内容右缘落在第 91 列、右空 36 列，与
     pet_window.CLING_MARGIN_LOGICAL=36 的贴边推出量配套——右壁推出 36
     后手掌正好搭住屏幕右缘；左壁渲染用水平镜像帧，其左空 36 列由本帧右
     空镜像而来，同一条对齐规则两面墙都成立（居中摆放会让手离墙差一截）；
  3. 帧分割仍按"全空列"切：源图帧间距不保证均匀，等分宽度可能切到手臂。

朝向约定（assets/README.md）：sheet 存朝右原帧；左壁由渲染层镜像。
本脚本是 climbing sheet 的唯一生成者：gen_assets_from_photos.py 重跑时
只读盘拼总览、不再覆写该文件。

用法（项目根目录）：.venv\\Scripts\\python tools\\gen_climb_from_photos.py
换源图：--src <路径>
"""
import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # 缺 Pillow 时给出可执行的提示，而不是裸 traceback
    sys.exit("需要 Pillow（仅开发工具依赖）：.venv\\Scripts\\python -m pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = ROOT / "assets" / "src" / "climbing2.png"  # 默认源图（透明底 4 帧）
ASSETS_DIR = ROOT / "assets"
PREVIEW_PATH = ROOT / "xinsucai" / "climb_preview.png"

FRAME = 128          # 目标帧尺寸（与 manifest frame_size 一致）
ANCHOR_Y = 126       # 内容底边落点：与 B 方案 ANCHOR 同值，各动作同地平面
CONTENT_MAX_H = 112  # 内容最大高度：与 B 方案/walk 同值，保证身形大小一致
CONTENT_MAX_W = FRAME - 8
RIGHT_EDGE = 91      # 内容右缘列号：右空 36 列，配套 CLING_MARGIN_LOGICAL
CLIMB_FPS = 8        # 与 manifest 现值一致（B 方案攀爬帧率，观感已验收）
EXPECTED_FRAMES = 4  # 源图帧数：分割结果不符即报错，避免切错帧写坏 sheet


def split_frames(rgba: Image.Image) -> list:
    """按全空列（整列 alpha=0）把整图逐帧切开，返回 RGBA 段列表。"""
    w, h = rgba.size
    a = rgba.getchannel("A").tobytes()
    # 每列是否有内容：全空列才是帧间可靠分界（等分宽度可能切到摆臂）
    col_has = [any(a[y * w + x] for y in range(0, h, 2)) for x in range(w)]
    segs, start = [], None
    for x in range(w + 1):
        has = x < w and col_has[x]
        if has and start is None:
            start = x
        elif not has and start is not None:
            if x - start >= 8:  # 宽度 <8px 的段是噪点孤岛，丢弃
                segs.append(rgba.crop((start, 0, x, h)))
            start = None
    return segs


def build_frames(segs: list) -> list:
    """4 段统一缩放塞进 128x128 帧：底边贴 ANCHOR_Y、右缘贴 RIGHT_EDGE。

    缩放比取"最宽帧、最高帧"都能塞下的最小值并全帧共用：逐帧各自 fit 会
    让攀爬循环里身形忽大忽小地闪。BOX 降采样对像素风源图振铃最少。
    """
    boxes = [s.getbbox() for s in segs]  # alpha 非零包围盒
    max_w = max(b[2] - b[0] for b in boxes)
    max_h = max(b[3] - b[1] for b in boxes)
    scale = min(CONTENT_MAX_W / max_w, CONTENT_MAX_H / max_h)
    print(f"源帧包围盒最大 {max_w}x{max_h}，统一缩放比 {scale:.4f}")
    frames = []
    for seg, box in zip(segs, boxes):
        char = seg.crop(box)
        nw = max(1, round(char.width * scale))
        nh = max(1, round(char.height * scale))
        char = char.resize((nw, nh), Image.BOX)
        # 右对齐：右空恰好 36 列（贴边推出量配套，见模块 docstring 第 2 点）
        x = RIGHT_EDGE + 1 - nw
        if x < 0:
            sys.exit(f"缩放后内容宽 {nw} 超过右对齐可用宽度 {RIGHT_EDGE + 1}："
                     f"调小 CONTENT_MAX_H 或检查源图")
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        frame.paste(char, (x, ANCHOR_Y - nh), char)
        frames.append(frame)
    return frames


def to_sheet(frames: list) -> Image.Image:
    """帧序列横排拼成 sprite sheet。"""
    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * FRAME, 0), f)
    return sheet


def main() -> int:
    ap = argparse.ArgumentParser(description="从 4 帧攀爬源图生成 climbing sheet（详见模块 docstring）")
    ap.add_argument("--src", type=Path, default=SRC_PATH, help="源图路径（透明底横排帧条）")
    args = ap.parse_args()

    manifest = json.loads((ASSETS_DIR / "manifest.json").read_text(encoding="utf-8"))
    src = Image.open(args.src)
    if src.mode != "RGBA":
        sys.exit(f"源图模式为 {src.mode}，预期 RGBA 透明背景；带底色源图请先抠底")
    segs = split_frames(src)
    if len(segs) != EXPECTED_FRAMES:
        sys.exit(f"源图切出 {len(segs)} 段，预期 {EXPECTED_FRAMES} 段："
                 f"检查帧间是否有全空列分隔")
    frames = build_frames(segs)
    sheet = to_sheet(frames)
    fname = manifest["actions"]["climbing"]["file"]
    sheet.save(ASSETS_DIR / fname)
    manifest["actions"]["climbing"]["frames"] = len(frames)
    manifest["actions"]["climbing"]["fps"] = CLIMB_FPS
    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  climbing: {len(frames)} 帧 -> {fname}")

    # 总览图：灰底（透明 PNG 在黑色查看器里会误判）+ 一行 idle 供比对身形大小
    idle_sheet = Image.open(ASSETS_DIR / manifest["actions"]["idle"]["file"])
    idle_n = manifest["actions"]["idle"]["frames"]
    rows = [("climbing", frames),
            ("idle", [idle_sheet.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME))
                      for i in range(idle_n)])]
    label_w = 110
    max_frames = max(len(f) for _, f in rows)
    preview = Image.new("RGB", (label_w + max_frames * FRAME,
                                len(rows) * (FRAME + 4) + 4), (96, 96, 96))
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default()
    for row, (name, fs) in enumerate(rows):
        y = 4 + row * (FRAME + 4)
        draw.text((6, y + FRAME // 2), name, fill=(255, 255, 255), font=font)
        for i, f in enumerate(fs):
            preview.paste(f, (label_w + i * FRAME, y), f)
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    preview.save(PREVIEW_PATH)
    print(f"总览图: {PREVIEW_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
