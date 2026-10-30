"""全量素材校验：检查 manifest 与 assets 下所有动作 sheet 是否严格对齐。

运行时 xiaoliang/sprite.py 只校验 frame_size / frames / fps 合法性、文件存在、
能解码，**不校验宽度是否等于 frames×128**——帧数写错时程序不会报错，只会把
后面的帧当成别的图，播出来是错的。这个脚本补上这层体检。

检查项：
  1. 每个动作的 file 存在、能解码、尺寸 = frames×128 x 128、RGBA
  2. 每帧 alpha 有内容；内容不贴左右/顶部边界（贴边说明被裁）
  3. 底部落在锚点 ANCHOR_Y 附近（脚底贴地平线）
  4. 各动作内容尺寸是否大体一致（躺姿等特意不同的只提示，不算失败）
  5. 循环衔接：末帧→首帧差异不应明显大于普通相邻帧差异
     （走路/攀爬这类循环步态"末帧再迈一步"差异大属正常）
  6. 应用 STATE_ACTION 用到的动作是否都在 manifest 里、有无多余项

用法（项目根目录）：
  .venv\\Scripts\\python tools\\check_assets.py
退出码 0 = 全部通过，1 = 有问题。
"""
import json
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("需要依赖：.venv\\Scripts\\python -m pip install numpy pillow")

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FRAME = 128
ANCHOR_Y = 126

# 必须与 xiaoliang/pet_window.py 的 STATE_ACTION 保持一致，另加走路两个方向
REQUIRED = {
    "idle", "dragged", "falling", "poke_react", "eating",
    "sleeping", "woken", "climbing", "sitting_top", "remind",
    "walk_left", "walk_right",
}


def _diff(x: np.ndarray, y: np.ndarray) -> float:
    union = int((x | y).sum())
    return int((x ^ y).sum()) / max(1, union)


def main() -> int:
    manifest = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))
    problems, info, sizes = [], [], {}

    fs = manifest.get("frame_size")
    if fs != [FRAME, FRAME]:
        problems.append(f"frame_size 期望 [{FRAME},{FRAME}]，实际 {fs}")

    actions = manifest.get("actions", {})
    missing = REQUIRED - set(actions)
    extra = set(actions) - REQUIRED
    if missing:
        problems.append(f"manifest 缺少应用需要的动作: {sorted(missing)}")
    if extra:
        problems.append(f"manifest 有应用用不到的动作: {sorted(extra)}")

    for name, action in actions.items():
        path = ASSETS / action["file"]
        if not path.exists():
            problems.append(f"{name}: 文件不存在 {path}")
            continue
        im = Image.open(path)
        w, h = im.size
        n = action["frames"]

        if im.mode != "RGBA":
            problems.append(f"{name}: 模式 {im.mode}，应为 RGBA")
        if h != FRAME:
            problems.append(f"{name}: 高度 {h} != {FRAME}")
        if w != n * FRAME:
            problems.append(f"{name}: 宽度 {w} != frames({n}) x {FRAME} = {n * FRAME}")
            continue

        arr = np.array(im.convert("RGBA"))
        masks = [arr[:, i * FRAME:(i + 1) * FRAME, 3] > 0 for i in range(n)]
        blanks = [i for i, m in enumerate(masks) if not m.any()]
        for i in blanks:
            problems.append(f"{name}: 第 {i} 帧是空白")
        good = [m for m in masks if m.any()]
        if not good:
            continue

        xs0 = min(int(np.where(m.any(axis=0))[0].min()) for m in good)
        xs1 = max(int(np.where(m.any(axis=0))[0].max()) for m in good)
        ys0 = min(int(np.where(m.any(axis=1))[0].min()) for m in good)
        ys1 = max(int(np.where(m.any(axis=1))[0].max()) for m in good)
        sizes[name] = (xs1 - xs0 + 1, ys1 - ys0 + 1)

        if xs0 == 0 or xs1 == FRAME - 1:
            problems.append(f"{name}: 内容贴左右边界 x=[{xs0},{xs1}]，可能被裁")
        if ys0 == 0:
            problems.append(f"{name}: 顶部贴边 y=0，可能被裁")
        if not (ANCHOR_Y - 6 <= ys1 <= ANCHOR_Y):
            problems.append(f"{name}: 底部 y={ys1}，未落在锚点 {ANCHOR_Y} 附近")

        steps = [_diff(masks[i], masks[(i + 1) % n]) for i in range(n)]
        wrap, inner = steps[-1], steps[:-1]
        avg = sum(inner) / len(inner) if inner else 0.0
        if wrap > max(0.05, avg * 2.0):
            problems.append(
                f"{name}: 末→首差异 {wrap:.0%} 明显大于相邻帧 {avg:.0%}，循环会跳")

        info.append(
            f"{name:<12} {n:>2}帧 @{action['fps']}fps  内容 {xs1 - xs0 + 1}x{ys1 - ys0 + 1}"
            f"  底部y={ys1}  末→首{wrap:.0%}(相邻均{avg:.0%})")

    print("=== 每个动作 ===")
    for line in info:
        print("  " + line)

    if sizes:
        ws = [s[0] for s in sizes.values()]
        hs = [s[1] for s in sizes.values()]
        median_h = sorted(hs)[len(hs) // 2]
        print("\n=== 尺寸一致性 ===")
        print(f"  宽度范围 {min(ws)}~{max(ws)}，高度范围 {min(hs)}~{max(hs)}")
        for name, (_, hh) in sorted(sizes.items(), key=lambda kv: kv[1][1]):
            if abs(hh - median_h) > 12:
                print(f"  ! {name} 高度 {hh} 与中位数 {median_h} 偏差较大（躺姿等可忽略）")

    print("\n=== 结论 ===")
    if problems:
        for p in problems:
            print("  ✗ " + p)
        return 1
    print(f"  ✓ {len(actions)} 个动作全部通过校验")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
