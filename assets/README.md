# 素材说明

## 当前素材：ChatGPT 单帧源图 + 程序派生微动画（B 方案）+ 走路抽卡（A 方案）+ 攀爬/坐顶/被拎专用管线

源图为 `assets/src/stand.jpg`（站立）与 `assets/src/sleep.jpg`（睡觉），
白底 JPG。运行 `.venv\Scripts\python tools\gen_assets_from_photos.py`
从这两张单帧派生除 walk 外全部动作的 sprite sheet（边缘泛洪抠底 → 光晕清理 →
包围盒裁剪 → 128 帧降采样 → 逐动作缩放/旋转/位移微动画 → 横排拼帧），
并输出总览图 `xinsucai/preview.png` 供肉眼验收。
Pillow 仅该开发工具使用，运行时加载仍走 PySide6 QImage，不进打包依赖。

走路两动作（2026-09-24 起）改走 A 方案抽卡：源图 `assets/src/walk_v2.jpg`
（黑底 5 帧横排，第 1 帧是正面站立、工具用 `--skip 1` 忽略，第 2-5 帧为
朝右走路循环），运行 `.venv\Scripts\python tools\gen_walk_from_photos.py`
生成 walk_right / walk_left（4 帧 @6fps）并同步 manifest.json 的帧数/帧率。
该脚本是这两个 sheet 的唯一生成者（黑底泛洪容差比白底紧，见脚本
docstring）；B 方案脚本重跑时只读盘拼总览、不覆写。日后换走路素材：覆盖
源图重跑即可（帧数/排版不符时用 `--src` / `--skip` 调整；初代源
`src/walk.jpg` 保留作参考）。

攀爬与坐顶（2026-09-24 起）各有专用管线，源图均为**透明底 PNG**（免抠底）：
- `climbing`：源图 `assets/src/climbing2.png`（4 帧横排朝右攀爬循环），
  运行 `.venv\Scripts\python tools\gen_climb_from_photos.py`。内容右对齐
  （右空 36 列）配套渲染层贴边推出量 CLING_MARGIN=36——居中摆会让手离墙
  悬空一截，见脚本 docstring
- `sitting_top`：源图 `assets/src/sit.png`（单帧正面坐姿），运行
  `.venv\Scripts\python tools\gen_sit_from_photos.py`（4 帧 @4fps 呼吸起伏）。
  搁板由程序绘制：暖木色横板横贯整帧（v0.1 占位版同语义同配色），伸出屏幕
  缘的一端被渲染裁剪读作"侧壁探出的小搁板"；板托臀部坐线（LEDGE_TOP=89，
  验收两轮微调定稿）。单帧源图做不了逐腿晃荡，微动画为绕底部锚点呼吸
- `dragged`：源图 `assets/src/dragged.png`（4 帧横排被拎后颈的挣扎循环，
  入库前用户文件名 111.png），运行
  `.venv\Scripts\python tools\gen_drag_from_photos.py`（4 帧 @4fps）。
  水平**居中**：被拎时窗口跟手、不贴墙，没有贴边推出量要配套（climbing/
  sitting_top 的右对齐是为 CLING_MARGIN=36 服务）；尺寸校准系数
  DRAG_SIZE=0.70（本源图角色天生画大约 1.43 倍，实测与对齐原理见脚本
  docstring）；替换掉 B 方案"站姿左右拧 2 帧"的假挣扎，四肢垂荡的摆动由
  源图 4 帧直接给出

日后若换成逐动作逐帧源图（A 方案抽卡），保持同样的文件格式替换同名
PNG、按实际帧数/帧率更新 manifest.json 即可，代码无需改动。
旧占位生成脚本 `tools\gen_placeholder_assets.py` 保留作回退参考。

## 格式约定

- 每个动作一张横向排列的 sprite sheet PNG，帧尺寸 128x128，透明背景
- `manifest.json` 描述帧尺寸、每个动作的文件名/帧数/帧率：

  ```json
  {
    "frame_size": [128, 128],
    "actions": {
      "idle": {"file": "idle.png", "frames": 4, "fps": 3}
    }
  }
  ```

- 动作名固定：`idle` / `walk_left` / `walk_right` / `dragged`(4帧@4fps) /
  `falling` / `poke_react`(2帧@6fps) / `eating`(4帧@6fps) /
  `sleeping`(2帧@2fps) / `woken`(2帧@3fps) / `climbing`(4帧@8fps) /
  `sitting_top`(4帧@4fps) / `remind`(4帧@4fps)
- 朝向约定：角色默认画成朝右；`walk_left` 是 `walk_right` 的水平镜像；
  `climbing` 只画"右壁向上爬"，向下爬 = 帧序倒放、左壁 = 水平镜像
  （均由渲染层 `SpriteManager.get_frame` 完成，素材无需额外出图）

## AI 生成正式素材的流程（提示词模板）

1. 先定稿单帧形象（保证后续所有动作风格一致）：

   > pixel art sprite, 128x128, single character, anime girl with long blue
   > hair, sleepy relaxed expression, holding a bass guitar, side view,
   > transparent background, clean pixels, limited palette

2. 以定稿图为参考，逐动作生成帧序列（站立呼吸 4 帧 / 走路 4 帧 /
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
  （128×128 逻辑像素横排）。替换时按 manifest.json 的 remind 条目画好
  帧数与尺寸，跑 `tools\check_sprites.py` 验证。
- 占位音效由 `tools\gen_placeholder_sounds.py` 合成（正弦短音），
  正式素材就绪后直接覆盖。
