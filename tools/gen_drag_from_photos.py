"""从 4 帧被拎源图生成 dragged sheet（正式被拎素材第一单）。

源图：assets/src/dragged.png（入库前用户文件名 111.png）—— 透明背景 PNG、
4 帧横排、被拎后颈后的挣扎循环（身体横担、头朝右、四肢垂荡）。产物与其
余动作同约定：128x128 帧、底边踩 y=126、透明背景横排 sheet；帧数/帧率写
回 manifest.json。

与 gen_climb_from_photos.py 流水线的差异点：
  1. 水平**居中**而不是右对齐：被拎时窗口跟手、不贴墙，没有贴边推出量要
     配套（climbing/sitting_top 右对齐是为 CLING_MARGIN=36 服务）；
  2. 帧率 4fps：挣扎循环 1 秒一轮，与坐顶呼吸同节奏（初版 8fps 验收判
     "晃动频率太大"）；
  3. 替换对象是 B 方案"站姿左右拧 2 帧"的假挣扎：正式素材是真被拎姿势，
     四肢垂荡的摆动由源图 4 帧直接给出，不需要程序微动画；
  4. 尺寸校准 DRAG_SIZE：本源图角色天生画大一号（实测与 idle 线性比约
     1.43：全身 alpha 面积比开方、发罩宽/高比三指标一致），bbox-fit 只管
     姿势外廓、管不了源图自带尺度，故拟合比再乘 0.70 把头身对齐 idle。

帧分割按"全空列"切：源图帧间距不保证均匀，等分宽度可能切到垂下的手。
本脚本是 dragged sheet 的唯一生成者：gen_assets_from_photos.py 重跑时
只读盘拼总览、不再覆写该文件。

用法（项目根目录）：.venv\\Scripts\\python tools\\gen_drag_from_photos.py
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
SRC_PATH = ROOT / "assets" / "src" / "dragged.png"  # 默认源图（透明底 4 帧）
ASSETS_DIR = ROOT / "assets"
PREVIEW_PATH = ROOT / "xinsucai" / "drag_preview.png"

FRAME = 128          # 目标帧尺寸（与 manifest frame_size 一致）
ANCHOR_Y = 126       # 内容底边落点：与 B 方案 ANCHOR 同值，各动作同地平面
CONTENT_MAX_H = 112  # 内容最大高度：与其余动作同值，保证身形大小一致
CONTENT_MAX_W = FRAME - 8
DRAG_FPS = 4         # 挣扎循环 1 秒一轮，与坐顶呼吸同节奏（8fps 验收判太快）
DRAG_SIZE = 0.70     # 尺寸校准：源图角色天生约 1.43 倍（实测），乘在拟合比上对齐 idle 头身
EXPECTED_FRAMES = 4  # 源图帧数：分割结果不符即报错，避免切错帧写坏 sheet


def split_frames(rgba: Image.Image) -> list:
    """按全空列（整列 alpha=0）把整图逐帧切开，返回 RGBA 段列表。"""
    w, h = rgba.size
    a = rgba.getchannel("A").tobytes()
    # 每列是否有内容：全空列才是帧间可靠分界（等分宽度可能切到垂手）
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
    """4 段统一缩放塞进 128x128 帧：底边贴 ANCHOR_Y、水平居中。

    缩放比取"最宽帧、最高帧"都能塞下的最小值并全帧共用：逐帧各自 fit 会
    让挣扎循环里身形忽大忽小地闪。BOX 降采样对像素风源图振铃最少。
    """
    boxes = [s.getbbox() for s in segs]  # alpha 非零包围盒
    max_w = max(b[2] - b[0] for b in boxes)
    max_h = max(b[3] - b[1] for b in boxes)
    # bbox-fit 只管姿势外廓、管不了源图自带的人物尺度（本源图画大约 1.43
    # 倍），乘校准系数 DRAG_SIZE 把头身对齐 idle；逐帧各自 fit 会让挣扎循
    # 环里身形忽大忽小地闪，故全帧共用一个比。BOX 降采样对像素风振铃最少
    scale = min(CONTENT_MAX_W / max_w, CONTENT_MAX_H / max_h) * DRAG_SIZE
    print(f"源帧包围盒最大 {max_w}x{max_h}，统一缩放比 {scale:.4f}（含校准 {DRAG_SIZE}）")
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
    ap = argparse.ArgumentParser(description="从 4 帧被拎源图生成 dragged sheet（详见模块 docstring）")
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
    fname = manifest["actions"]["dragged"]["file"]
    sheet.save(ASSETS_DIR / fname)
    manifest["actions"]["dragged"]["frames"] = len(frames)
    manifest["actions"]["dragged"]["fps"] = DRAG_FPS
    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  dragged: {len(frames)} 帧 -> {fname}")

    # 总览图：灰底（透明 PNG 在黑色查看器里会误判）+ 一行 idle 供比对身形大小
    idle_sheet = Image.open(ASSETS_DIR / manifest["actions"]["idle"]["file"])
    idle_n = manifest["actions"]["idle"]["frames"]
    rows = [("dragged", frames),
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
