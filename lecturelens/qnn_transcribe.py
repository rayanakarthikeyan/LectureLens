"""Adapter for Qualcomm's ai-hub-apps whisper_windows_py sample.

Run this with the sample's native ARM64 Python environment. The sample's
WhisperApp is used unchanged; LectureLens divides WAV into <=25 s windows.
"""

from __future__ import annotations

import argparse
import json
import sys
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-dir", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    app_dir = args.app_dir.resolve()
    if not (app_dir / "models" / "encoder.onnx").is_file() or not (app_dir / "models" / "decoder.onnx").is_file():
        raise FileNotFoundError("Qualcomm Whisper encoder.onnx and decoder.onnx are missing")
    sys.path.insert(0, str(app_dir))
    from utils.model import WhisperApp, load_model  # type: ignore[import-not-found]

    model = load_model(str(app_dir / "models" / "encoder.onnx"), str(app_dir / "models" / "decoder.onnx"))
    app = WhisperApp(model)
    segments = []
    chunk_path = args.audio.parent / "qnn-current-chunk.wav"
    try:
        with wave.open(str(args.audio), "rb") as source:
            if source.getnchannels() != 1 or source.getframerate() != 16000 or source.getsampwidth() != 2:
                raise ValueError("Expected 16 kHz mono 16-bit PCM WAV")
            rate = source.getframerate()
            total_frames = source.getnframes()
            frames_per_chunk = 25 * rate
            position = 0
            while position < total_frames:
                count = min(frames_per_chunk, total_frames - position)
                source.setpos(position)
                with wave.open(str(chunk_path), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(rate)
                    output.writeframes(source.readframes(count))
                text = str(app.transcribe(str(chunk_path))).strip()
                if text:
                    segments.append({"id": len(segments), "start": position / rate, "end": (position + count) / rate, "text": text, "page": None})
                position += count
    finally:
        chunk_path.unlink(missing_ok=True)
    args.output.write_text(json.dumps({"segments": segments, "timing": "25-second window starts; word-level timestamps unavailable"}, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
