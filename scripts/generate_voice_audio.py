import json
import math
import struct
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VOICE_DIR = PROJECT_ROOT / "data" / "synthetic" / "voice"
NOTES_FILE = VOICE_DIR / "notes.json"


def main():
    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        notes = json.load(f)

    for n in notes:
        wav_path = VOICE_DIR / f"{n['id']}.wav"
        with wave.open(str(wav_path), "w") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            duration = n.get("duration_sec", 3)
            num_samples = 16000 * duration
            # Generate synthetic audio tone (440 Hz)
            for i in range(num_samples):
                val = int(800 * math.sin(2 * math.pi * 440 * (i / 16000)))
                wav_file.writeframesraw(struct.pack("<h", val))

    print(f"Generated {len(notes)} synthetic WAV audio files in {VOICE_DIR}")


if __name__ == "__main__":
    main()
