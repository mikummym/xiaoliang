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

- 动作名固定：`idle` / `walk_left` / `walk_right` / `dragged` / `falling` /
  `poke_react`(2帧@6fps) / `eating`(4帧@6fps) / `sleeping`(2帧@2fps) /
  `woken`(2帧@3fps) / `climbing`(4帧@8fps) / `sitting_top`(4帧@3fps) /
  `remind`(4帧@4fps)
- 朝向约定：角色默认画成朝右；`walk_left` 是 `walk_right` 的水平镜像；
  `climbing` 只画"右壁向上爬"，向下爬 = 帧序倒放、左壁 = 水平镜像
  （均由渲染层 `SpriteManager.get_frame` 完成，素材无需额外出图）

## AI 生成正式素材的流程（提示词模板）

1. 先定稿单帧形象（保证后续所有动作风格一致）：

   > pixel art sprite, 64x64, single character, anime girl with long blue
   > hair, sleepy relaxed expression, holding a bass guitar, side view,
   > transparent background, clean pixels, limited palette

2. 以定稿图为参考，逐动作生成帧序列（站立呼吸 4 帧 / 走路 6 帧 /
   被拎起 2 帧 / 下落 2 帧 / 被戳反应 2 帧 / 喂食 4 帧 / 睡觉 2 帧 /
   睡眼惺忪 2 帧 / 攀爬 4 帧（侧面朝右向上）/ 顶边坐姿 4 帧 /
   伸懒腰提醒 4 帧），每张拼成横向 sprite sheet
3. 替换本目录同名 PNG，按实际帧数/帧率更新 manifest.json
4. 运行 `.venv\Scripts\python tools\check_sprites.py` 验证可加载

## 待办

- [ ] 正式素材阶段为 `climbing` 与 `remind` 单独出"被戳"帧（当前在墙上被戳
      或提醒中被戳播放的是地面姿势的 `poke_react`，见主 README"已知问题"）

## 音频素材（v0.3）

- `sounds/poke/*.wav`：戳她音效池，程序启动时目录式加载（随机播一个）。
  规格：wav 格式（QSoundEffect 原生支持），建议 16-bit 单声道、≤1 秒短音。
  替换/新增：把 wav 丢进目录即可，无需改代码或配置；删文件即移除。
- `remind.png`：提醒动作（伸懒腰），4 帧 @ 4fps，帧规格与其他动作一致
  （64×64 逻辑像素横排）。替换时按 manifest.json 的 remind 条目画好
  帧数与尺寸，跑 `tools\check_sprites.py` 验证。
- 占位音效由 `tools\gen_placeholder_sounds.py` 合成（正弦短音），
  正式素材就绪后直接覆盖。
