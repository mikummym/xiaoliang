"""用干净参考图 sit.png 生成「坐姿晃腿」动作（代码摆腿，不依赖视频）。

背景：图生视频模型在坐姿这件事上始终把脸画歪（眼睛/嘴糊成一团，脸上
还带一坨灰泥色阴影），靠后处理调色救不回来。而「晃腿」本身就是刚性
旋转，完全可以由代码精确控制——于是改用参考图做底、只对双腿做旋转。

做法：
  1. 以 assets/src/sit.png 为底图（脸/衣服/头发都是干净的原始像素）；
  2. 用连通块分析得到左右腿的范围（y>=107 处两腿分离）；
  3. 把每条腿连同上大腿（y>=100）切出来做成独立图层，从底图挖掉；
  4. 每条腿绕髋部支点 (leg_cx, 100) 做刚性旋转，左右相反的相位，
     角度 = amp * sin(2πi/n)，首尾帧角度相同可无缝循环；
  5. 旋转后贴回底图，输出 8 帧 sheet。

用法（项目根目录）：
  .venv\\Scripts\\python tools\\gen_sit_swing.py [--amp 8] [--frames 8] [--write]
"""
import argparse
import json
import math
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("需要依赖：.venv\\Scripts\\python -m pip install numpy pillow")

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
SRC = ASSETS_DIR / "src" / "sit.png"
FRAME = 128
LEG_Y0 = 107           # 两腿在 y>=107 才真正分离，从这里切开
PIVOT_Y = 107          # 旋转支点：腿的顶端（膝关节处）
SEAM_BAND = 3          # 接缝带：旋转后把原图这几行回贴，消除根部的洞
LEGS = {"left": (38, 60), "right": (70, 92)}   # 每条腿的 x 范围（左闭右开）


def _extract_leg(base: Image.Image, x0: int, x1: int) -> Image.Image:
    """把指定 x 范围内的腿部像素复制到一张全透明同尺寸图上。"""
    src = base.load()
    leg = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    dst = leg.load()
    for y in range(LEG_Y0, FRAME):
        for x in range(x0, x1):
            px = src[x, y]
            if px[3]:
                dst[x, y] = px
    return leg


def _palette(img: Image.Image) -> np.ndarray:
    """收集底图的不透明像素颜色作为调色板（参考图只有 24 色）。"""
    arr = np.asarray(img)
    op = arr[:, :, 3] > 0
    return np.unique(arr[:, :, :3][op].reshape(-1, 3), axis=0)


def _rotate(layer: Image.Image, deg: float, pivot: tuple, palette: np.ndarray) -> Image.Image:
    """绕支点刚性旋转，并把结果归位到原调色板。

    128 画布上直接旋转会糊边，先放大 4 倍旋转、BOX 缩回；缩放会让边缘
    产生过渡色，所以再把每个像素吸附回底图调色板里最近的颜色、alpha
    按阈值二值化——这样旋转帧和原图一样是干净的像素画，不会比静止帧糊。
    """
    if abs(deg) < 0.25:          # 静止帧直接原图，避免重采样造成 1px 抖动
        return layer
    z = 4
    big = layer.resize((FRAME * z, FRAME * z), Image.BICUBIC)
    big = big.rotate(deg, resample=Image.BICUBIC,
                     center=(pivot[0] * z, pivot[1] * z))
    small = np.asarray(big.resize((FRAME, FRAME), Image.BOX)).astype(np.int16)

    alpha = small[:, :, 3]
    opaque = alpha >= 100
    rgb = small[:, :, :3].astype(np.int32)
    # 每个不透明像素吸附到最近调色板颜色（用 int32，避免 255^2 在 int16 上溢出）
    pal = palette.astype(np.int32)
    dist = ((rgb[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(axis=3)
    nearest = pal[np.argmin(dist, axis=2)]
    out = np.zeros((FRAME, FRAME, 4), dtype=np.uint8)
    out[opaque, :3] = nearest[opaque]
    out[opaque, 3] = 255
    return Image.fromarray(out, mode="RGBA")


def build(frames: int, amp: float) -> list:
    base = Image.open(SRC).convert("RGBA")
    palette = _palette(base)
    body = base.copy()
    legs = {}
    for name, (x0, x1) in LEGS.items():
        legs[name] = _extract_leg(base, x0, x1)
        # 从身体上挖掉腿部，之后再由旋转后的腿覆盖
        px = body.load()
        for y in range(LEG_Y0, FRAME):
            for x in range(x0, x1):
                if px[x, y][3]:
                    px[x, y] = (0, 0, 0, 0)

    out = []
    for i in range(frames):
        # 左右腿反相：一腿前摆时另一腿后摆，读起来像来回踢腿
        a = amp * math.sin(2 * math.pi * i / frames)
        img = body.copy()
        img.alpha_composite(_rotate(legs["left"], a,
                                    (sum(LEGS["left"]) // 2, PIVOT_Y), palette))
        img.alpha_composite(_rotate(legs["right"], -a,
                                    (sum(LEGS["right"]) // 2, PIVOT_Y), palette))
        # 回贴接缝带：旋转会让腿根部相对大腿产生缝隙，用原始像素盖住
        for x0, x1 in LEGS.values():
            band = base.crop((x0, LEG_Y0, x1, LEG_Y0 + SEAM_BAND))
            img.paste(band, (x0, LEG_Y0), band)
        out.append(img)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--amp", type=float, default=8.0, help="最大摆腿角度（度）")
    ap.add_argument("--write", action="store_true", help="写入 assets 并更新 manifest")
    a = ap.parse_args()

    if not SRC.exists():
        sys.exit(f"缺少参考图：{SRC}")

    frames = build(a.frames, a.amp)
    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * FRAME, 0), f)

    out_dir = ROOT / "xinsucai" / "gen"
    out_dir.mkdir(parents=True, exist_ok=True)
    sheet.save(out_dir / "sitting_top_swing_sheet.png")
    print(f"预览 sheet: {out_dir / 'sitting_top_swing_sheet.png'}")

    if a.write:
        manifest = json.loads((ASSETS_DIR / "manifest.json").read_text(encoding="utf-8"))
        target = ASSETS_DIR / manifest["actions"]["sitting_top"]["file"]
        sheet.save(target)
        print(f"已写入 {target}（frames={len(frames)}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
