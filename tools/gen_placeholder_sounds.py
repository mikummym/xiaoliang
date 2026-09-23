"""生成占位戳音效：两个不同音高的短促"叮/咚"（后续替换为正式素材）。

用法（项目根目录）：
    .venv\\Scripts\\python tools\\gen_placeholder_sounds.py

输出到 assets\\sounds\\poke\\：poke_a.wav / poke_b.wav
（16-bit 单声道 22050Hz；SoundEngine 目录式加载，丢新 wav 即加音效）。
"""
import math
import struct
import wave
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "sounds" / "poke"
RATE = 22050


def blip(freq: float, secs: float = 0.18) -> bytes:
    """合成指数衰减短音：基频正弦 + 半幅倍频，比纯音圆润一点。"""
    n = int(RATE * secs)
    frames = bytearray()
    for i in range(n):
        t = i / RATE
        env = math.exp(-t * 12.0)                       # 衰减包络
        v = (math.sin(2 * math.pi * freq * t)
             + 0.5 * math.sin(4 * math.pi * freq * t))
        frames += struct.pack("<h", int(v * env * 12000))
    return bytes(frames)


def write_wav(path: Path, data: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_wav(OUT_DIR / "poke_a.wav", blip(880.0))      # 偏高音"叮"
    write_wav(OUT_DIR / "poke_b.wav", blip(660.0))      # 偏低音"咚"
    print(f"已生成占位音效: {OUT_DIR}")


if __name__ == "__main__":
    main()
