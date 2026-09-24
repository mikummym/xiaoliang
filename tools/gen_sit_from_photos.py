"""从单帧坐姿源图生成 sitting_top sheet（正式坐顶素材第一单）。

源图：assets/src/sit.png —— 透明背景 PNG、单帧正面坐姿（双手撑地、腿前
伸）。产物与其余动作同约定：128x128 帧、透明背景横排 sheet；帧数/帧率写回
manifest.json。

画面构成（验收反馈：不能虚空坐着，要和 v0.1 占位版一样有支撑物）：
  1. 搁板：暖木色横板横贯整帧宽 0..127（板面 + 板底暗边做出厚度）。渲染层
     会把坐姿窗口向墙外推出 36 列，搁板伸出屏幕边缘的一端被自然裁剪，读作
     "固定在侧壁上探出来的小搁板"——与 v0.1 占位素材 draw_sitting_top 的
     搁板语义、配色（LEDGE/LEDGE_DARK）完全一致；
  2. 角色：臀部压在搁板板面上、小腿/鞋叠画在板前并垂到板下（悬空晃荡感）。
     板托在臀部坐线而不是包围盒底行——坐姿包围盒最低点是前伸的鞋底，板
     画在鞋底行会让屁股悬空读作虚空坐（验收反馈：板上移 ~25px）；
  3. 水平**右对齐**（内容右缘第 91 列、右空 36 列）：与 climbing 同规则，
     配套 pet_window.CLING_MARGIN_LOGICAL=36 的贴边推出量；左壁渲染用镜像
     帧，同一条规则两面墙都成立；
  4. 微动画：单帧源图做不了逐腿摆动（腿是整图的一部分），改为绕底部锚点的
     呼吸起伏（sy 1→1.03→1，屁股不离板、头顶微微起伏）；日后要真晃腿需提
     供多帧源图走抽卡管线。

本脚本是 sitting_top sheet 的唯一生成者：gen_assets_from_photos.py 重跑时
只读盘拼总览、不再覆写该文件。

用法（项目根目录）：.venv\\Scripts\\python tools\\gen_sit_from_photos.py
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
SRC_PATH = ROOT / "assets" / "src" / "sit.png"  # 默认源图（透明底单帧坐姿）
ASSETS_DIR = ROOT / "assets"
PREVIEW_PATH = ROOT / "xinsucai" / "sit_preview.png"

FRAME = 128          # 目标帧尺寸（与 manifest frame_size 一致）
RIGHT_EDGE = 91      # 角色内容右缘列号：右空 36 列，配套 CLING_MARGIN_LOGICAL
CONTENT_MAX_W = RIGHT_EDGE + 1   # 右对齐下角色可用最大宽度（左缘顶到第 0 列）
CONTENT_MAX_H = 103  # 角色最大高度：头顶留余量给呼吸拉伸
CHAR_BOTTOM = 109    # 角色内容底边行号（鞋底）：鞋垂在搁板下沿之下=悬空晃荡
# 搁板板面首行：验收反馈先上移 25px（104→79，板托臀部坐线而非鞋底行）、
# 再下移 10px 定稿（79→89）。板面往下 6 行 + 暗边 2 行，小腿/鞋叠画在
# 板前并垂到板下
LEDGE_TOP = 89
LEDGE_FACE = (150, 115, 80, 255)    # 板面暖木色（v0.1 占位版 LEDGE 同值）
LEDGE_DARK = (100, 72, 48, 255)     # 板底暗边（v0.1 占位版 LEDGE_DARK 同值）
LEDGE_FACE_H = 6     # 板面行数
LEDGE_EDGE_H = 2     # 板底暗边行数（做出板的厚度）
# 呼吸起伏配方：(sy, ) 绕底部锚点纵向拉伸——屁股贴板不动、头顶微升
BREATH_SY = (1.0, 1.015, 1.03, 1.015)
SIT_FPS = 4          # 4 帧呼吸周期 1s，与 idle 呼吸同节奏


def build_frames(char: Image.Image) -> list:
    """单帧坐姿按呼吸配方派生 4 帧：右对齐 + 屁股压板面 + 先板后人。"""
    scale = min(CONTENT_MAX_W / char.width, CONTENT_MAX_H / char.height)
    nw = max(1, round(char.width * scale))
    nh = max(1, round(char.height * scale))
    print(f"源坐姿包围盒 {char.width}x{char.height}，缩放比 {scale:.4f} -> {nw}x{nh}")
    x = RIGHT_EDGE + 1 - nw  # 右对齐：右空恰好 36 列
    frames = []
    for sy in BREATH_SY:
        nh_i = max(1, round(nh * sy))
        body = char.resize((nw, nh_i), Image.BOX)  # BOX：像素风降采样无振铃
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        # 先画搁板（横贯整帧，伸出屏幕缘的一端由渲染裁剪读作"壁探出的板"）；
        # 板托在臀部坐线，小腿/鞋随后叠画在板前并垂到板下（悬空晃荡感）
        d = ImageDraw.Draw(frame)
        d.rectangle((0, LEDGE_TOP, FRAME - 1, LEDGE_TOP + LEDGE_FACE_H - 1),
                    fill=LEDGE_FACE)
        d.rectangle((0, LEDGE_TOP + LEDGE_FACE_H, FRAME - 1,
                     LEDGE_TOP + LEDGE_FACE_H + LEDGE_EDGE_H - 1),
                    fill=LEDGE_DARK)
        # 后画角色：鞋底垂到板下、臀部压在板面上 = 坐在板沿
        frame.paste(body, (x, CHAR_BOTTOM - nh_i + 1), body)
        frames.append(frame)
    return frames


def to_sheet(frames: list) -> Image.Image:
    """帧序列横排拼成 sprite sheet。"""
    sheet = Image.new("RGBA", (FRAME * len(frames), FRAME), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * FRAME, 0), f)
    return sheet


def main() -> int:
    ap = argparse.ArgumentParser(description="从单帧坐姿源图生成 sitting_top sheet（详见模块 docstring）")
    ap.add_argument("--src", type=Path, default=SRC_PATH, help="源图路径（透明底单帧）")
    args = ap.parse_args()

    manifest = json.loads((ASSETS_DIR / "manifest.json").read_text(encoding="utf-8"))
    src = Image.open(args.src)
    if src.mode != "RGBA":
        sys.exit(f"源图模式为 {src.mode}，预期 RGBA 透明背景；带底色源图请先抠底")
    box = src.getbbox()
    if box is None:
        sys.exit("源图全透明，没有可用的坐姿内容")
    frames = build_frames(src.crop(box))
    sheet = to_sheet(frames)
    fname = manifest["actions"]["sitting_top"]["file"]
    sheet.save(ASSETS_DIR / fname)
    manifest["actions"]["sitting_top"]["frames"] = len(frames)
    manifest["actions"]["sitting_top"]["fps"] = SIT_FPS
    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"  sitting_top: {len(frames)} 帧 -> {fname}")

    # 总览图：灰底 + idle/climbing 两行供比对身形大小与地平面
    rows = [("sitting_top", frames)]
    for name in ("climbing", "idle"):
        s = Image.open(ASSETS_DIR / manifest["actions"][name]["file"])
        n = manifest["actions"][name]["frames"]
        rows.append((name, [s.crop((i * FRAME, 0, (i + 1) * FRAME, FRAME))
                            for i in range(n)]))
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
