"""从 AI 生成的视频派生动作 sprite sheet（C 方案：图生视频）。

背景：单帧源图 + 仿射变换只能做"整体缩放/位移"的假动作，涉及四肢的
动作（举手、伸懒腰、咀嚼、倒地）根本做不出来。本工具改为以
assets/src/stand.jpg 为参考图，用图生视频模型产出整段动作循环，再从
视频里抽帧、抠背景、统一缩放，得到与 stand 完全同源的动作素材。

流水线：
  1. 按固定间隔抽 N 帧，覆盖视频里的一个完整循环（末帧不重复首帧）；
  2. 每帧抠白底（复用 gen_assets_from_photos.remove_background）；
  3. 用"N 帧 alpha 包围盒的并集"作为统一裁剪框，所有帧共用同一个缩放
     系数——绝不做逐帧 fit，否则每帧包围盒抖动会被放大成角色抖动；
  4. 呼吸/起伏这类"竖直方向的变化"在 960 视频里往往只有 8px，降到
     128 帧后不足 1px，肉眼看不见。因此从每帧真实包围盒高度解出一条
     呼吸曲线，按 --amp 倍放大成 sy 拉伸（脚底锚定，脚不离地）；
  5. 横向拼帧出 preview，确认后再写 assets/<action>.png 和 manifest。

用法（项目根目录）：
  .venv\\Scripts\\python tools\\gen_action_from_video.py <clip.mp4> <action> [--frames N] [--amp X] [--write]
"""
import argparse
import json
import math
import sys
from pathlib import Path

try:
    import numpy as np
    import imageio.v3 as iio
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("需要依赖：.venv\\Scripts\\python -m pip install imageio imageio-ffmpeg numpy pillow")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_assets_from_photos import (ACTIONS, ANCHOR, ASSETS_DIR, CONTENT_MAX_H,
                                    FRAME, make_frame, remove_background)

ROOT = Path(__file__).resolve().parent.parent


def _flood_frames(clip: Path, n: int) -> list:
    """从视频均匀抽 n 帧（覆盖一个循环，末帧不重复首帧），返回 RGBA 列表。"""
    frames = [np.asarray(f.convert("RGB") if hasattr(f, "convert") else f)
              for f in iio.imiter(str(clip), plugin="FFMPEG")]
    total = len(frames)
    if total < n:
        sys.exit(f"视频只有 {total} 帧，不够抽样 {n} 帧")
    step = total / n
    idx = [int(round(i * step)) for i in range(n)]
    out, tops, heights = [], [], []
    for i in idx:
        im = remove_background(Image.fromarray(frames[i]))
        box = im.getbbox()
        out.append((im, box))
        tops.append(box[1])
        heights.append(box[3] - box[1])
    return out, tops, heights


def _drop_strays(frame: Image.Image) -> Image.Image:
    """删掉角色本体以外的孤立碎屑。

    AI 视频偶尔在帧边缘画出多余的手/飘带，抠图后会变成几个孤立的 alpha
    小块。角色本体是一整块连通像素（头发→身体→手脚由描边连在一起），
    所以只保留最大连通域、其余清零，干净利落，不会误伤本体。
    """
    from collections import deque
    a = np.array(frame.getchannel("A"))
    if not a.any():
        return frame
    h, w = a.shape
    visited = np.zeros_like(a, dtype=bool)
    biggest = None
    for y in range(h):
        for x in range(w):
            if a[y, x] == 0 or visited[y, x]:
                continue
            q = deque([(y, x)])
            visited[y, x] = True
            comp = []
            while q:
                cy, cx = q.popleft()
                comp.append((cy, cx))
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and a[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        q.append((ny, nx))
            if biggest is None or len(comp) > len(biggest):
                biggest = comp
    if biggest is None:
        return frame
    keep = np.zeros_like(a, dtype=bool)
    for y, x in biggest:
        keep[y, x] = True
    a_clean = np.where(keep, a, 0)
    alpha = Image.fromarray(a_clean, mode="L")
    out = frame.copy()
    out.putalpha(alpha)
    return out


def _swing(frame, deg: float, pivot_y: float):
    """绕指定支点刚性旋转（钟摆摆动）。

    在 128 帧上直接 rotate 会糊边，先放到 4 倍再转、转完 BOX 缩回来，
    边缘比单次旋转干净得多。expand 关掉，保证 128 画布不随之变大。
    """
    if not deg:
        return frame
    z = 4
    big = frame.resize((FRAME * z, FRAME * z), Image.BICUBIC)
    big = big.rotate(deg, resample=Image.BICUBIC,
                     center=(FRAME * z // 2, round(pivot_y * z)))
    return big.resize((FRAME, FRAME), Image.BOX)


def build(clip: Path, n: int, amp: float, swing: float = 0.0,
          pivot_y: float = 24.0) -> tuple:
    frames, tops, heights = _flood_frames(clip, n)
    # 统一裁剪框：用各帧 bbox 的 10/90 百分位而不是 min/max。
    # 原因：AI 视频偶尔在单帧里冒出多余的物体（比如"被戳"动作里画了一只
    # 从画面外伸入的手），会把并集撑到画布边缘，导致整组角色被缩小。
    # 取百分位能稳健地丢掉这种单帧异常，正常帧的轻微位移不受影响。
    lefts = np.array([b[0] for _, b in frames])
    rights = np.array([b[2] for _, b in frames])
    tops_arr = np.array([b[1] for _, b in frames])
    bottoms = np.array([b[3] for _, b in frames])
    ux0 = int(np.percentile(lefts, 10))
    ux1 = int(np.percentile(rights, 90))
    uy0 = int(np.percentile(tops_arr, 10))
    uy1 = int(np.percentile(bottoms, 90))
    # 缩放基准取"最矮的一帧"（休息姿态）而不是并集高度：拉伸/举手会把
    # 并集高度撑大，按并集算会让角色整体变小，切换动作时忽大忽小
    h_rest = min(heights)
    scale = min((FRAME - 8) / (ux1 - ux0), CONTENT_MAX_H / h_rest)
    nw, nh = max(1, round((ux1 - ux0) * scale)), max(1, round((uy1 - uy0) * scale))

    h_min = h_rest
    out = []
    for i, ((im, _), h) in enumerate(zip(frames, heights)):
        char = im.crop((ux0, uy0, ux1, uy1)).resize((nw, nh), Image.BOX)
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        frame.paste(char, ((FRAME - nw) // 2, ANCHOR[1] - nh), char)
        sy = 1 + (h / h_min - 1) * amp      # 真实起伏曲线按 amp 倍放大
        f = make_frame(frame, 1, sy, 0, 0)
        f = _drop_strays(f)                 # 清掉帧边缘 AI 多画的手/碎屑
        # 钟摆：第 i 帧偏角 = swing * sin(2πi/n)，整圈首尾角度相同可无缝循环
        out.append(_swing(f, swing * math.sin(2 * math.pi * i / n), pivot_y))
    print(f"  统一裁剪 {ux1 - ux0}x{uy1 - uy0} -> {nw}x{nh}  "
          f"缩放={scale:.4f}  sy∈[{1:.3f}, {1 + (max(heights) / h_min - 1) * amp:.3f}]")
    return out


def preview(sheets: dict, path: Path) -> None:
    label_w, rows = 130, list(sheets.items())
    max_frames = max(len(f) for _, f in rows)
    img = Image.new("RGB", (label_w + max_frames * FRAME, len(rows) * (FRAME + 4) + 4),
                    (96, 96, 96))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for row, (name, frames) in enumerate(rows):
        y = 4 + row * (FRAME + 4)
        draw.text((6, y + FRAME // 2), name, fill=(255, 255, 255), font=font)
        for i, f in enumerate(frames):
            img.paste(f, (label_w + i * FRAME, y), f)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    print(f"预览: {path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("action")
    ap.add_argument("--frames", type=int, default=16)
    ap.add_argument("--amp", type=float, default=4.0,
                    help="竖直起伏放大倍数（128 帧下 1px 差异才看得见）")
    ap.add_argument("--swing", type=float, default=0.0,
                    help="绕支点钟摆偏角（度），0 = 不做旋转")
    ap.add_argument("--pivot-y", type=float, default=24.0,
                    help="旋转支点在 128 帧里的 y 坐标（领口位置≈24）")
    ap.add_argument("--write", action="store_true", help="写入 assets 并更新 manifest")
    a = ap.parse_args()

    clip = Path(a.clip)
    frames = build(clip, a.frames, a.amp, a.swing, a.pivot_y)
    # 原始 RGBA sheet 存档：验收时要用 alpha 量头宽/边距，preview 是灰底
    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * FRAME, 0), f)
    sheet.save(ROOT / "xinsucai" / "gen" / f"{a.action}_sheet.png")
    preview({a.action: frames}, ROOT / "xinsucai" / "gen" / f"{a.action}_preview.png")

    if a.write:
        manifest = json.loads((ASSETS_DIR / "manifest.json").read_text(encoding="utf-8"))
        sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
        for i, f in enumerate(frames):
            sheet.paste(f, (i * FRAME, 0), f)
        sheet.save(ASSETS_DIR / manifest["actions"][a.action]["file"])
        print(f"已写入 {manifest['actions'][a.action]['file']}，"
              f"记得同步 manifest: frames={len(frames)} fps=24/{int(round(97 / a.frames))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
