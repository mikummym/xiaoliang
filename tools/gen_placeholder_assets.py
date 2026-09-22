"""生成占位像素素材：一个蓝发小人（后续可替换为 AI 生成的正式素材）。

用法（项目根目录）：
    .venv\\Scripts\\python tools\\gen_placeholder_assets.py

输出到 assets\\：每个动作一张横向排列的 sprite sheet（帧尺寸 64x64，透明背景），
外加描述帧数/帧率的 manifest.json。

v0.2 新增 6 组动作（spec §2.4）：poke_react / eating / sleeping / woken /
climbing / sitting_top。climbing 只画"右壁向上爬"：爬下 = 帧序倒放、
左壁 = 水平镜像，均由渲染层（SpriteManager.get_frame）完成，无需额外素材。
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
BOWL = (210, 210, 220, 255)   # 喂食用的碗
LEDGE = (150, 115, 80, 255)       # 顶边坐姿的搁板板面（暖木色）
LEDGE_DARK = (100, 72, 48, 255)   # 搁板板底暗边（做出板的厚度）


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


def draw_poke_react(d: ImageDraw.ImageDraw, *, exclaim: bool = False) -> None:
    """被戳反应：举手惊讶；exclaim 帧头顶画感叹号（两帧交替 = 吓一跳）。"""
    draw_pet(d, arms_up=True)
    if exclaim:
        d.rectangle([31, 2, 33, 8], fill=EYE)    # 感叹号竖笔
        d.rectangle([31, 9, 33, 11], fill=EYE)   # 感叹号的点


def draw_eating(d: ImageDraw.ImageDraw, *, body_dy: int = 0) -> None:
    """喂食：身前捧碗，body_dy 做咀嚼点头起伏。碗画在小人之后（挡住下半身）。"""
    draw_pet(d, body_dy=body_dy)
    d.rectangle([24, 48, 40, 50], fill=BOWL)     # 碗口
    d.rectangle([27, 50, 37, 56], fill=BOWL)     # 碗身


def draw_sleeping(d: ImageDraw.ImageDraw, *, zzz_big: bool = False) -> None:
    """睡觉：侧躺姿势 + 大小 zzz 交替（大 z = 呼气帧，2fps 慢节奏）。"""
    d.rectangle([14, 40, 26, 52], fill=HAIR)     # 头（躺下偏左）
    d.rectangle([20, 43, 26, 49], fill=SKIN)     # 脸
    d.line((21, 46, 25, 46), fill=EYE)           # 闭眼横线
    d.rectangle([27, 41, 48, 52], fill=CLOTH)    # 躺着的身体
    d.rectangle([48, 44, 54, 50], fill=SKIN)     # 露出的脚
    if zzz_big:                                  # 大 z：两横一斜，加粗
        d.line((42, 20, 50, 20), fill=EYE, width=2)
        d.line((50, 20, 42, 28), fill=EYE, width=2)
        d.line((42, 28, 50, 28), fill=EYE, width=2)
    else:                                        # 小 z：细笔画
        d.line((46, 30, 51, 30), fill=EYE)
        d.line((51, 30, 46, 35), fill=EYE)
        d.line((46, 35, 51, 35), fill=EYE)


def draw_woken(d: ImageDraw.ImageDraw, *, zzz: bool = False) -> None:
    """睡眼惺忪：站立揉眼；zzz 帧头顶仍飘小 z（还没醒透），身体起伏交替。"""
    draw_pet(d, body_dy=0 if zzz else 1)
    if zzz:
        d.line((44, 6, 48, 6), fill=EYE)
        d.line((48, 6, 44, 10), fill=EYE)
        d.line((44, 10, 48, 10), fill=EYE)


def draw_climbing(d: ImageDraw.ImageDraw, *, phase: int = 0) -> None:
    """爬墙：侧面朝右贴墙，手臂/腿按 phase 0-3 交替（攀爬循环）。

    只画"右壁向上爬"：爬下 = 帧序倒放、左壁 = 水平镜像，
    由 SpriteManager.get_frame 渲染时处理（spec §2.4，一组素材三种用法）。
    """
    d.rectangle([28, 14, 40, 26], fill=HAIR)     # 头
    d.rectangle([30, 20, 38, 26], fill=SKIN)     # 脸
    d.point((36, 22), fill=EYE)                  # 眼睛（侧面只见一只）
    d.rectangle([28, 27, 40, 44], fill=CLOTH)    # 躯干
    if phase % 2 == 0:                           # 手臂一上一下交替抓墙
        d.rectangle([39, 8, 42, 20], fill=SKIN)
        d.rectangle([39, 30, 42, 38], fill=SKIN)
    else:
        d.rectangle([39, 16, 42, 28], fill=SKIN)
        d.rectangle([39, 34, 42, 42], fill=SKIN)
    off = 2 if phase < 2 else -2                 # 腿交替蹬墙
    d.rectangle([29, 44, 32, 52 + off], fill=CLOTH)
    d.rectangle([34, 44, 37, 52 - off], fill=CLOTH)
    d.rectangle([29, 52 + off, 32, 54 + off], fill=EYE)   # 鞋
    d.rectangle([34, 52 - off, 37, 54 - off], fill=EYE)


def draw_sitting_top(d: ImageDraw.ImageDraw, *, leg_swing: int = 0) -> None:
    """顶边坐姿（侧面朝右）：坐在横贯画面的搁板上，大腿水平前伸、小腿悬空交替晃荡。

    与站姿的剪影区别（验收反馈：旧画法腿垂直下垂，远看像站着）：
    大腿水平 + 小腿垂在膝下 + 手臂搭向腿面，一眼可读为"坐"。
    搁板：修复"顶边坐着悬空、没有支撑物"——渲染层会把坐姿窗口向墙外平移，
    搁板横贯整帧宽 0..63，伸出屏幕边缘的一端被自然裁剪，读作"固定在侧壁上
    探出来的小搁板"。板面从 y35 起，正好托住底边在 y34 的大腿。
    贴边可见带约束（评审 major 修复）：角色必须收在第 0..42 可见列内——
    贴边偏移会把帧内第 43..63 列推出屏幕（右壁裁掉 43..63，左壁镜像后裁掉
    原帧 0..20），肢体画进这些列会被屏幕边缘竖直切断。所以除搁板外所有
    绘制坐标整体左移 6 列（角色含摆幅占 17..42），只有搁板横贯整帧、
    端头被屏幕边缘裁剪。
    遮挡关系（靠绘制顺序实现）：远侧腿先画 → 搁板盖住其中段（读作腿从板后
    垂过、鞋露在板下）→ 大腿/躯干画在板上 → 近侧腿最后画，垂在板前。
    leg_swing 取 1/0/-1：近/远两条腿的小腿与鞋绕膝盖反向摆动。
    """
    ls = leg_swing
    # 远侧腿（最先画：中段稍后被搁板遮住，只露出膝上的连接和板下的鞋）
    d.rectangle([28, 34, 33, 42], fill=SKIN)            # 远小腿上段
    d.rectangle([28 - ls, 42, 33 - ls, 48], fill=SKIN)  # 远小腿下段（随 ls 摆）
    d.rectangle([26 - ls, 48, 35 - ls, 52], fill=EYE)   # 远侧鞋
    # 搁板：唯一横贯整帧的元素（0..63），板面 + 暗底边做出厚度；
    # 盖住远侧腿中段形成前后遮挡，端头伸出屏幕边缘被裁读作固定在侧壁上
    d.rectangle([0, 35, 63, 38], fill=LEDGE)            # 板面（托住大腿）
    d.rectangle([0, 39, 63, 40], fill=LEDGE_DARK)       # 板底暗边（厚度）
    # 大腿：从臀（左端）到膝（右端）水平前伸——坐姿的关键剪影，底边贴住板面
    d.rectangle([17, 28, 39, 34], fill=CLOTH)
    # 躯干与头（坐姿：躯干比站姿短，整体压低；画在大腿之后压住腿根）
    d.rectangle([21, 16, 33, 30], fill=CLOTH)           # 躯干
    d.rectangle([22, 4, 36, 16], fill=HAIR)             # 头颅
    d.rectangle([27, 10, 36, 16], fill=SKIN)            # 脸（侧面朝右）
    d.point((33, 12), fill=EYE)                         # 眼睛（侧面只见一只）
    # 近侧腿（最后画：垂在搁板前，与远侧腿反向摆，前后层次一目了然）
    d.rectangle([34, 34, 39, 43], fill=SKIN)            # 近小腿上段
    d.rectangle([34 + ls, 43, 39 + ls, 50], fill=SKIN)  # 近小腿下段
    d.rectangle([32 + ls, 50, 41 + ls, 54], fill=EYE)   # 近侧鞋
    # 手臂：从肩垂下搭在大腿上
    d.rectangle([28, 20, 32, 29], fill=SKIN)


def make_sheet(frames_params: list[dict], out_name: str, draw=draw_pet) -> int:
    """按每帧参数画一张 sprite sheet（draw 指定绘制函数），返回帧数。"""
    sheet = Image.new("RGBA", (FRAME * len(frames_params), FRAME), (0, 0, 0, 0))
    for i, params in enumerate(frames_params):
        frame = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        draw(ImageDraw.Draw(frame), **params)
        sheet.paste(frame, (i * FRAME, 0), frame)
    sheet.save(ASSETS_DIR / out_name)
    return len(frames_params)


def main() -> None:
    ASSETS_DIR.mkdir(exist_ok=True)
    # name → (每帧参数, fps, 绘制函数)；帧数/帧率严格按 spec §2.4
    specs = {
        "idle": ([{"body_dy": 0}, {"body_dy": 0},
                  {"body_dy": 1}, {"body_dy": 1}], 3, draw_pet),
        "walk_right": ([{"leg_offset": o} for o in (-2, -1, 0, 1, 2, 1)],
                       8, draw_pet),
        "dragged": ([{"arms_up": True, "leg_offset": 1},
                     {"arms_up": True, "leg_offset": -1}], 6, draw_pet),
        "falling": ([{"arms_up": True, "body_dy": 0},
                     {"arms_up": True, "body_dy": 1}], 6, draw_pet),
        "poke_react": ([{"exclaim": True}, {"exclaim": False}],
                       6, draw_poke_react),
        "eating": ([{"body_dy": 0}, {"body_dy": 1},
                    {"body_dy": 0}, {"body_dy": 1}], 6, draw_eating),
        "sleeping": ([{"zzz_big": False}, {"zzz_big": True}], 2, draw_sleeping),
        "woken": ([{"zzz": False}, {"zzz": True}], 3, draw_woken),
        "climbing": ([{"phase": p} for p in range(4)], 8, draw_climbing),
        "sitting_top": ([{"leg_swing": s} for s in (1, 0, -1, 0)],
                        3, draw_sitting_top),
    }
    manifest = {"frame_size": [FRAME, FRAME], "actions": {}}
    for name, (frames_params, fps, draw) in specs.items():
        file_name = f"{name}.png"
        count = make_sheet(frames_params, file_name, draw=draw)
        manifest["actions"][name] = {"file": file_name, "frames": count, "fps": fps}

    # walk_left 由 walk_right 逐帧镜像生成（v0.1 逻辑不变）
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
