"""从 4 帧走路源图生成 walk_right / walk_left sheet（A 方案抽卡第一单）。

源图：assets/src/walk_v2.jpg —— 黑底 JPG、5 帧横排（第 1 帧是正面站立，
用 --skip 1 忽略），第 2-5 帧为朝右走路循环。v1 源 assets/src/walk.jpg
保留作参考。产物与 gen_assets_from_photos.py 同约定：128x128 帧、脚底踩
y=126、水平居中、透明背景横排 sheet；并把 manifest.json 的 walk_* 帧数/
帧率同步成实测值。

与 B 方案流水线的差异点（为什么不能直接复用那个脚本）：
  1. 背景是黑不是白：泛洪种子色仍取四角均值（自动适应黑底），但容差从 60
     收紧到 30——黑底源图的角色描边也是深色，60 那档会顺着描边啃进轮廓；
  2. 不做白边光晕清理：那轮只针对白底 JPG 振铃，黑底振铃是深色噪点，
     留在剪影边上视觉上就是描边的一部分，删了反而缺边；
  3. 4 帧共用一个缩放比（按最宽/最高帧定标）：逐帧各自 fit 会让步态循环里
     身形忽大忽小地闪；
  4. 帧分割按"全空列"切而不是宽度四等分：源图帧间距不保证均匀。

walk_left = walk_right 逐帧水平镜像（朝向约定见 assets/README.md）。
本脚本是 walk 两动作 sheet 的唯一生成者：gen_assets_from_photos.py 重跑时
只读盘拼总览、不再覆写这两个文件。

用法（项目根目录）：.venv\\Scripts\\python tools\\gen_walk_from_photos.py
换源图/忽略开头帧：--src <路径> --skip <n>（默认 src/walk_v2.jpg、skip 1）
"""
import argparse
import json
import sys
from collections import deque
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # 缺 Pillow 时给出可执行的提示，而不是裸 traceback
    sys.exit("需要 Pillow（仅开发工具依赖）：.venv\\Scripts\\python -m pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = ROOT / "assets" / "src" / "walk_v2.jpg"  # 默认源图（v2 抽卡）
SRC_SKIP = 1           # 默认忽略源图开头 1 帧（v2 第 1 帧是正面站立）
ASSETS_DIR = ROOT / "assets"
PREVIEW_PATH = ROOT / "xinsucai" / "walk_preview.png"

FRAME = 128          # 目标帧尺寸（与 manifest frame_size 一致）
ANCHOR_Y = 126       # 脚底落点：与 B 方案 ANCHOR 同值，走路与站立同地平面
CONTENT_MAX_H = 112  # 内容最大高度：头顶留余量给弹跳，与 B 方案同值
CONTENT_MAX_W = FRAME - 8
BG_TOL_SQ = 30 ** 2  # 泛洪容差（RGB 距离平方）：只吃黑底与振铃，不啃深色描边
WALK_FPS = 6         # 4 帧一个步态周期 → 0.67s/周期，贴近旧 6 帧@8fps 的步速
EXPECTED_FRAMES = 4  # 源图帧数：分割结果不符即报错，避免切错帧写坏 sheet


def _dist_sq(px, seed):
    """像素与背景种子色的 RGB 距离平方（免开方，够判阈值）。"""
    return (px[0] - seed[0]) ** 2 + (px[1] - seed[1]) ** 2 + (px[2] - seed[2]) ** 2


def remove_background(img: Image.Image) -> Image.Image:
    """边缘泛洪抠黑底，返回 RGBA（背景 alpha=0）。

    为什么从边界泛洪而不是全局阈值：角色毛衣/袜子也是深色，全局阈值会挖穿
    身体；泛洪只删"与图像边界连通"的近黑区域，描边以内的深色不与边界连通。
    """
    img = img.convert("RGB")
    w, h = img.size
    data = img.tobytes()
    px = [data[i * 3:(i + 1) * 3] for i in range(w * h)]
    # 种子色取四角平均：黑底可能有轻微渐变/偏色，四角比单点稳
    corners = [px[0], px[w - 1], px[(h - 1) * w], px[h * w - 1]]
    seed = tuple(sum(c[i] for c in corners) // 4 for i in range(3))

    seen = bytearray(w * h)
    queue = deque()
    # 四条边上的近黑像素全部入队作为泛洪源
    for x in range(w):
        for y in (0, h - 1):
            i = y * w + x
            if not seen[i] and _dist_sq(px[i], seed) <= BG_TOL_SQ:
                seen[i] = 1
                queue.append(i)
    for y in range(h):
        for x in (0, w - 1):
            i = y * w + x
            if not seen[i] and _dist_sq(px[i], seed) <= BG_TOL_SQ:
                seen[i] = 1
                queue.append(i)
    while queue:
        i = queue.popleft()
        x, y = i % w, i // w
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h:
                j = ny * w + nx
                if not seen[j] and _dist_sq(px[j], seed) <= BG_TOL_SQ:
                    seen[j] = 1
                    queue.append(j)

    out = img.convert("RGBA")
    alpha = Image.new("L", (w, h), 0)
    alpha.putdata([0 if seen[i] else 255 for i in range(w * h)])
    out.putalpha(alpha)
    return out


def split_frames(rgba: Image.Image) -> list:
    """按全空列（整列 alpha=0）把整图逐帧切开，返回 RGBA 段列表。

    切出几段、忽略哪几段由 main 结合 --skip 判断，这里只负责切。
    """
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
            if x - start >= 8:  # 宽度 <8px 的段是 JPG 噪点孤岛，丢弃
                segs.append(rgba.crop((start, 0, x, h)))
            start = None
    return segs


def build_frames(segs: list) -> list:
    """4 段统一缩放塞进 128x128 帧：脚底贴 ANCHOR_Y、水平居中。

    缩放比取"最宽帧、最高帧"都能塞下的最小值并全帧共用：逐帧各自 fit 会
    让迈步幅度的差异变成身形闪烁。BOX 降采样对像素风源图振铃最少。
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
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        frame.paste(char, ((FRAME - nw) // 2, ANCHOR_Y - nh), char)
        frames.append(frame)
    return frames


def to_sheet(frames: list) -> Image.Image:
    """帧序列横排拼成 sprite sheet。"""
    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * FRAME, 0), f)
    return sheet


def main() -> int:
    ap = argparse.ArgumentParser(description="从多帧走路源图生成 walk sheet（详见模块 docstring）")
    ap.add_argument("--src", type=Path, default=SRC_PATH, help="源图路径（黑底横排帧条）")
    ap.add_argument("--skip", type=int, default=SRC_SKIP, help="忽略源图开头几帧（如站立帧）")
    args = ap.parse_args()

    manifest = json.loads((ASSETS_DIR / "manifest.json").read_text(encoding="utf-8"))
    segs = split_frames(remove_background(Image.open(args.src)))
    if len(segs) != args.skip + EXPECTED_FRAMES:
        sys.exit(f"源图切出 {len(segs)} 段，预期 {args.skip + EXPECTED_FRAMES} 段"
                 f"（含忽略 {args.skip} 段）：检查帧间留白是否连通或 BG_TOL_SQ 是否合适")
    right = build_frames(segs[args.skip:])
    left = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in right]  # 朝向约定

    sheets = {"walk_right": right, "walk_left": left}
    for name, frames in sheets.items():
        sheet = to_sheet(frames)
        sheet.save(ASSETS_DIR / manifest["actions"][name]["file"])
        manifest["actions"][name]["frames"] = len(frames)
        manifest["actions"][name]["fps"] = WALK_FPS
        print(f"  {name}: {len(frames)} 帧 -> {manifest['actions'][name]['file']}")
    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 总览图：灰底（透明 PNG 在黑色查看器里会误判）+ 一行 idle 供比对身形大小
    idle_sheet = Image.open(ASSETS_DIR / manifest["actions"]["idle"]["file"])
    idle_n = manifest["actions"]["idle"]["frames"]
    rows = list(sheets.items()) + [
        ("idle", [idle_sheet.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME))
                  for i in range(idle_n)])]
    label_w = 110
    max_frames = max(len(f) for _, f in rows)
    preview = Image.new("RGB", (label_w + max_frames * FRAME,
                                len(rows) * (FRAME + 4) + 4), (96, 96, 96))
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default()
    for row, (name, frames) in enumerate(rows):
        y = 4 + row * (FRAME + 4)
        draw.text((6, y + FRAME // 2), name, fill=(255, 255, 255), font=font)
        for i, f in enumerate(frames):
            preview.paste(f, (label_w + i * FRAME, y), f)
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    preview.save(PREVIEW_PATH)
    print(f"总览图: {PREVIEW_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
