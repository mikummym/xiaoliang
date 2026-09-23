"""从单帧源图派生全部动作 sprite sheet（B 方案：程序化微动画）。

源图：assets/src/stand.jpg（站立）、assets/src/sleep.jpg（睡觉），
白底 JPG（ChatGPT 生成的像素风单帧）。本工具把它们加工成 manifest 里
声明的 12 个动作的横向 sprite sheet，帧尺寸 128x128、透明背景。

流水线：
  1. 边缘泛洪填充抠掉白底（只从图像边界向内 Flood，角色内部即使有白色
     也不会被误删——它被深色描边包住，与边界不连通）；
  2. 光晕清理：JPG 压缩会在轮廓外留下一圈近白噪点，把"紧邻透明区且
     近白"的像素再删一轮，去掉白边；
  3. 按 alpha 包围盒裁剪，BOX 降采样塞进 128x128 帧（像素风源图用 BOX
     平均降采样比 LANCZOS 更少振铃），脚底对齐帧底、水平居中；
  4. 逐动作微动画：以"脚底中心"为锚点做 缩放/旋转/上下位移 的仿射变换，
     呼吸、走路弹跳、挤压拉伸等全靠这几个参数组合出来；
  5. 横向拼帧写 assets/<action>.png；walk_left 直接镜像 walk_right。

另输出 xinsucai/preview.png 总览图（灰底+动作名）供肉眼验收。

依赖说明：Pillow 只是本开发工具的依赖，运行时加载图片仍走 PySide6 的
QImage（xiaoliang/sprite.py），不进入打包依赖。

用法（项目根目录）：.venv\\Scripts\\python tools\\gen_assets_from_photos.py
"""
import json
import math
import sys
from collections import deque
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # 缺 Pillow 时给出可执行的提示，而不是裸 traceback
    sys.exit("需要 Pillow（仅开发工具依赖）：.venv\\Scripts\\python -m pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "assets" / "src"
ASSETS_DIR = ROOT / "assets"
PREVIEW_PATH = ROOT / "xinsucai" / "preview.png"

FRAME = 128          # 目标帧尺寸（用户定稿）
ANCHOR = (64, 126)   # 微动画锚点：脚底中心。脚踩在 y=126，留 2px 底边
CONTENT_MAX_H = 112  # 内容最大高度：头顶留 ~14px 余量给拉伸/弹跳动作
BG_TOL_SQ = 60 ** 2  # 泛洪容差（RGB 距离平方）：盖住 JPG 噪点与抗锯齿边
HALO_MIN = 200       # 光晕清理阈值：min(r,g,b) 不低于它且低饱和才算白边

# 每个动作的帧参数表：(源图, sx, sy, 旋转度, 上下位移)。
# 缩放/旋转都绕脚底锚点发生，所以 sy<1 是"蹲坐压扁"、sy>1 是"向上拉伸"。
ACTIONS = {
    # 站立呼吸：轻微起伏 + 胸腔缩放
    "idle": [("stand", 1, 1, 0, 0), ("stand", 1, 1.01, 0, -1),
             ("stand", 1, 1.02, 0, -2), ("stand", 1, 1.01, 0, -1)],
    # 走路：正面角色的"颠步"——每 3 帧一个落脚周期，配左右摆倾
    "walk_right": [("stand", 1, 1, 0, -2), ("stand", 1, 1, 2.2, -3),
                   ("stand", 1, 1, 2.2, -2), ("stand", 1, 1, 0, -2),
                   ("stand", 1, 1, -2.2, -3), ("stand", 1, 1, -2.2, -2)],
    # 被拎着：像挂件一样左右晃
    "dragged": [("stand", 1, 1, 4, 0), ("stand", 1, 1, -4, 0)],
    # 下落：拉长身形 + 小幅摆动（慌）
    "falling": [("stand", 0.97, 1.04, 3, 0), ("stand", 0.97, 1.04, -3, 0)],
    # 被戳：先压扁吃惊，再弹起回敬
    "poke_react": [("stand", 1.07, 0.93, 0, 0), ("stand", 0.97, 1.05, 0, -2)],
    # 喂食：咀嚼压缩循环
    "eating": [("stand", 1, 1, 0, 0), ("stand", 1.02, 0.97, 0, 0),
               ("stand", 1, 1, 0, -1), ("stand", 1.02, 0.97, 0, 0)],
    # 睡觉：睡姿图做腹式呼吸
    "sleeping": [("sleep", 1, 1, 0, 0), ("sleep", 1.01, 1.03, 0, 0)],
    # 睡醒：第 0 帧还是睡姿，第 1 帧弹起来变站姿（惊醒感）
    "woken": [("sleep", 1, 1, 0, 0), ("stand", 1, 1.04, -3, -2)],
    # 攀爬：左右拧身 + 上拽交替（贴墙时的蠕动）
    "climbing": [("stand", 1, 1, 2.5, 0), ("stand", 1, 1, -2.5, -3),
                 ("stand", 1, 1, 2.5, 0), ("stand", 1, 1, -2.5, -3)],
    # 顶边坐姿：整体压扁成"坐下"，再叠呼吸
    "sitting_top": [("stand", 1, 0.86, 0, 0), ("stand", 1, 0.87, 0, -1),
                    ("stand", 1, 0.88, 0, -2), ("stand", 1, 0.87, 0, -1)],
    # 提醒（伸懒腰）：向上拔高再回落
    "remind": [("stand", 1, 1, 0, 0), ("stand", 0.97, 1.06, 0, 0),
               ("stand", 0.94, 1.12, -2, 0), ("stand", 0.97, 1.06, 0, 0)],
}


def _dist_sq(px, seed):
    """像素与背景种子色的 RGB 距离平方（免开方，够判阈值）。"""
    return (px[0] - seed[0]) ** 2 + (px[1] - seed[1]) ** 2 + (px[2] - seed[2]) ** 2


def remove_background(img: Image.Image) -> Image.Image:
    """边缘泛洪抠白底，返回 RGBA（背景 alpha=0）。

    为什么从边界泛洪而不是全局阈值：角色脸上/眼白也可能接近白色，
    全局阈值会挖穿脸；泛洪只删"与图像边界连通"的近白区域，描边是防火墙。
    """
    img = img.convert("RGB")
    w, h = img.size
    # 拍平成 RGB 字节串再切三元组（getdata 在 Pillow 12 已废弃）
    data = img.tobytes()
    px = [data[i * 3:(i + 1) * 3] for i in range(w * h)]
    # 种子色取四角平均：白底可能有轻微渐变/偏色，四角比单点稳
    corners = [px[0], px[w - 1], px[(h - 1) * w], px[h * w - 1]]
    seed = tuple(sum(c[i] for c in corners) // 4 for i in range(3))

    seen = bytearray(w * h)
    queue = deque()
    # 四条边上的近白像素全部入队作为泛洪源
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
    alpha = out.getchannel("A")
    a_px = [0 if seen[i] else 255 for i in range(w * h)]

    # 光晕清理一轮：紧贴透明区、近白且低饱和的像素是 JPG 振铃留下的白边，
    # 删掉；角色真正的浅色（皮肤/眼白）饱和度高或被描边包住，不受影响
    def _is_halo(i):
        if a_px[i] == 0:
            return False
        r, g, b = px[i][:3]
        if min(r, g, b) < HALO_MIN or max(r, g, b) - min(r, g, b) > 24:
            return False
        x, y = i % w, i // w
        return any(
            0 <= nx < w and 0 <= ny < h and a_px[ny * w + nx] == 0
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
        )

    for i in range(w * h):
        if _is_halo(i):
            a_px[i] = 0
    alpha.putdata(a_px)
    out.putalpha(alpha)
    return out


def fit_frame(base: Image.Image) -> Image.Image:
    """裁包围盒 + 降采样到 128x128 帧：脚底贴 ANCHOR、水平居中。"""
    box = base.getbbox()  # alpha 非零包围盒
    char = base.crop(box)
    scale = min((FRAME - 8) / char.width, CONTENT_MAX_H / char.height)
    nw, nh = max(1, round(char.width * scale)), max(1, round(char.height * scale))
    # BOX = 块平均，像素风源图降采样不产生新振铃色
    char = char.resize((nw, nh), Image.BOX)
    frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
    frame.paste(char, ((FRAME - nw) // 2, ANCHOR[1] - nh), char)
    return frame


def make_frame(base: Image.Image, sx, sy, rot_deg, dy) -> Image.Image:
    """对整帧底图做绕脚底锚点的仿射变换，产出一帧微动画。

    正向映射 p = T + R·S·(q - a)；PIL 的 AFFINE 要的是反向系数
    （输出坐标 → 源坐标），即 (R·S) 的逆矩阵：
        [[cos/sx,  sin/sx],
         [-sin/sy, cos/sy]]
    平移项 c/f 由锚点 a 与目标锚点 T 解出。
    """
    if (sx, sy, rot_deg, dy) == (1, 1, 0, 0):
        return base.copy()  # 恒等帧直接拷贝，避免无谓的重采样模糊
    th = math.radians(rot_deg)
    c_, s_ = math.cos(th), math.sin(th)
    a, b = c_ / sx, s_ / sx
    d, e = -s_ / sy, c_ / sy
    tx, ty = ANCHOR[0], ANCHOR[1] + dy
    cx = ANCHOR[0] - (a * tx + b * ty)
    fy = ANCHOR[1] - (d * tx + e * ty)
    return base.transform((FRAME, FRAME), Image.AFFINE, (a, b, cx, d, e, fy),
                          resample=Image.BILINEAR)


def main() -> int:
    manifest = json.loads((ASSETS_DIR / "manifest.json").read_text(encoding="utf-8"))
    bases = {
        "stand": fit_frame(remove_background(Image.open(SRC_DIR / "stand.jpg"))),
        "sleep": fit_frame(remove_background(Image.open(SRC_DIR / "sleep.jpg"))),
    }
    # 打印站立帧左右空白列数：贴边推出量（pet_window 的 CLING_MARGIN_*）
    # 要按新素材的对称空白重新标定，这里给出实测值
    bbox = bases["stand"].getbbox()
    print(f"站立帧内容包围盒={bbox} 左空白={bbox[0]} 右空白={FRAME - bbox[2]}")

    sheets = {}
    for name, params in ACTIONS.items():
        want = manifest["actions"][name]["frames"]
        assert len(params) == want, f"{name}: 参数表 {len(params)} 帧 != manifest {want} 帧"
        frames = [make_frame(bases[src], *p) for src, *p in params]
        sheets[name] = frames

    # walk_left = walk_right 的逐帧水平镜像（朝向约定，见 assets/README.md）
    sheets["walk_left"] = [f.transpose(Image.FLIP_LEFT_RIGHT)
                           for f in sheets["walk_right"]]

    for name, frames in sheets.items():
        sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
        for i, f in enumerate(frames):
            sheet.paste(f, (i * FRAME, 0), f)
        sheet.save(ASSETS_DIR / manifest["actions"][name]["file"])
        print(f"  {name}: {len(frames)} 帧 -> {manifest['actions'][name]['file']}")

    # 总览图：灰底（透明 PNG 在黑色查看器里会误判）+ 动作名，供肉眼验收
    label_w = 110
    max_frames = max(len(f) for f in sheets.values())
    preview = Image.new("RGB", (label_w + max_frames * FRAME,
                                len(sheets) * (FRAME + 4) + 4), (96, 96, 96))
    draw = ImageDraw.Draw(preview)
    font = ImageFont.load_default()
    order = list(ACTIONS.keys()) + ["walk_left"]
    for row, name in enumerate(order):
        y = 4 + row * (FRAME + 4)
        draw.text((6, y + FRAME // 2), name, fill=(255, 255, 255), font=font)
        for i, f in enumerate(sheets[name]):
            preview.paste(f, (label_w + i * FRAME, y), f)
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    preview.save(PREVIEW_PATH)
    print(f"总览图: {PREVIEW_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
