# 素材说明

## 当前素材：程序生成的占位小人

运行 `.venv\Scripts\python tools\gen_placeholder_assets.py` 重新生成。
占位素材用于开发期，正式发布前替换为 AI 生成的"小凉"形象（蓝发、慵懒气质、
可抱贝斯），保持同样的文件格式即可，代码无需改动。

## 格式约定

- 每个动作一张横向排列的 sprite sheet PNG，帧尺寸 64x64，透明背景
- `manifest.json` 描述帧尺寸、每个动作的文件名/帧数/帧率：

  ```json
  {
    "frame_size": [64, 64],
    "actions": {
      "idle": {"file": "idle.png", "frames": 4, "fps": 3}
    }
  }
  ```

- 动作名固定：`idle` / `walk_left` / `walk_right` / `dragged` / `falling`
- 朝向约定：角色默认画成朝右；`walk_left` 是 `walk_right` 的水平镜像

## AI 生成正式素材的流程（提示词模板）

1. 先定稿单帧形象（保证后续所有动作风格一致）：

   > pixel art sprite, 64x64, single character, anime girl with long blue
   > hair, sleepy relaxed expression, holding a bass guitar, side view,
   > transparent background, clean pixels, limited palette

2. 以定稿图为参考，逐动作生成帧序列（站立呼吸 4 帧 / 走路 6 帧 /
   被拎起 2 帧 / 下落 2 帧），每张拼成横向 sprite sheet
3. 替换本目录同名 PNG，按实际帧数/帧率更新 manifest.json
4. 运行 `.venv\Scripts\python tools\check_sprites.py` 验证可加载
