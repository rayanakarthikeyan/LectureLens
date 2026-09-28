"""Small localhost-only HTTP server for LectureLens."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import subprocess
import threading
import time
import wave
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .core import (
    ALLOWED_AUDIO,
    MAX_AUDIO,
    MAX_PDF,
    MAX_TRANSCRIPT,
    decode_upload,
    lecture_summary,
    load_lecture,
    new_lecture,
    parse_transcript,
    save_lecture,
    search_lecture,
)

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DATA = ROOT / "data"
MAX_REQUEST = 225 * 1024 * 1024
MIME = {".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml"}


class LectureHandler(BaseHTTPRequestHandler):
    server_version = "LectureLens/0.1"

    def log_message(self, format, *args):
        print("[%s] %s" % (self.log_date_time_string(), format % args))

    def json_response(self, value, status=200):
        content = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def file_response(self, path: Path):
        if not path.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        mime = MIME.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        range_header = self.headers.get("Range", "")
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header)
        start, end = 0, size - 1
        if match:
            start = int(match.group(1))
            end = min(int(match.group(2)), end) if match.group(2) else end
            if start > end:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(HTTPStatus.PARTIAL_CONTENT if match else HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if match:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            while remaining:
                chunk = stream.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            if route == "/api/health":
                qnn_dir = os.getenv("QAI_WHISPER_DIR", "")
                qnn_python = os.getenv("QAI_WHISPER_PYTHON", "")
                qnn_ready = bool(qnn_dir and qnn_python and Path(qnn_python).is_file() and (Path(qnn_dir) / "models" / "encoder.onnx").is_file() and (Path(qnn_dir) / "models" / "decoder.onnx").is_file())
                cpp_ready = bool(os.getenv("WHISPER_CLI") and os.getenv("WHISPER_MODEL"))
                self.json_response({"ok": True, "offline": True, "transcriber": "qualcomm-qnn" if qnn_ready else "whisper-cpp" if cpp_ready else None})
                return
            if route == "/api/lectures":
                lectures = []
                for path in DATA.glob("*/lecture.json"):
                    try:
                        lectures.append(lecture_summary(json.loads(path.read_text(encoding="utf-8"))))
                    except (OSError, ValueError, KeyError):
                        continue
                lectures.sort(key=lambda lecture: lecture["created_at"], reverse=True)
                self.json_response({"lectures": lectures})
                return
            match = re.fullmatch(r"/api/lectures/([0-9a-f]{32})", route)
            if match:
                self.json_response(load_lecture(DATA, match.group(1)))
                return
            match = re.fullmatch(r"/api/lectures/([0-9a-f]{32})/search", route)
            if match:
                lecture = load_lecture(DATA, match.group(1))
                query = parse_qs(parsed.query).get("q", [""])[0][:200]
                self.json_response({"results": search_lecture(lecture, query), "query": query})
                return
            match = re.fullmatch(r"/media/([0-9a-f]{32})/(audio\.(?:mp3|m4a|wav|ogg|webm|mp4)|slides\.pdf|pages/page-\d+\.png)", route)
            if match:
                self.file_response(DATA / match.group(1) / match.group(2))
                return
            if route == "/":
                route = "/index.html"
            if re.fullmatch(r"/[a-zA-Z0-9_.-]+", route):
                self.file_response(WEB / route.lstrip("/"))
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except FileNotFoundError:
            self.json_response({"error": "Lecture not found"}, 404)
        except Exception as exc:
            self.json_response({"error": str(exc)}, 500)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_REQUEST:
                return self.json_response({"error": "Request is empty or too large"}, 413)
            payload = json.loads(self.rfile.read(length))
            route = urlparse(self.path).path
            if route == "/api/lectures":
                audio = decode_upload(payload.get("audio"), ALLOWED_AUDIO, MAX_AUDIO)
                pdf = decode_upload(payload.get("pdf"), {".pdf"}, MAX_PDF)
                transcript = decode_upload(payload.get("transcript"), {".srt", ".vtt", ".txt"}, MAX_TRANSCRIPT)
                lecture = new_lecture(DATA, str(payload.get("title", "")), audio, pdf, transcript)
                return self.json_response(lecture, 201)
            match = re.fullmatch(r"/api/lectures/([0-9a-f]{32})/segments/(\d+)/page", route)
            if match:
                lecture = load_lecture(DATA, match.group(1))
                segment_id = int(match.group(2))
                page = payload.get("page")
                if page is not None and (not isinstance(page, int) or page < 1 or page > len(lecture["pages"])):
                    raise ValueError("Invalid slide page")
                segment = next((item for item in lecture["segments"] if item["id"] == segment_id), None)
                if segment is None:
                    return self.json_response({"error": "Segment not found"}, 404)
                segment["page"] = page
                save_lecture(DATA, lecture)
                return self.json_response(segment)
            match = re.fullmatch(r"/api/lectures/([0-9a-f]{32})/transcribe", route)
            if match:
                return self.transcribe(match.group(1))
            self.json_response({"error": "Not found"}, 404)
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            self.json_response({"error": str(exc)}, 400)
        except FileNotFoundError:
            self.json_response({"error": "Lecture not found"}, 404)
        except Exception as exc:
            self.json_response({"error": str(exc)}, 500)

    def transcribe(self, lecture_id: str):
        """Optional whisper.cpp adapter. Requires a 16 kHz mono WAV input."""
        lecture = load_lecture(DATA, lecture_id)
        if not lecture.get("audio"):
            raise ValueError("This lecture has no audio")
        if not lecture["audio"].endswith(".wav"):
            raise ValueError("Offline transcription currently requires a 16 kHz mono WAV file")
        try:
            with wave.open(str(DATA / lecture_id / lecture["audio"]), "rb") as recording:
                if recording.getnchannels() != 1 or recording.getframerate() != 16000 or recording.getsampwidth() != 2:
                    raise ValueError("Whisper requires a 16 kHz mono 16-bit PCM WAV file")
        except wave.Error as exc:
            raise ValueError("Whisper requires an uncompressed PCM WAV file") from exc
        folder = DATA / lecture_id
        qnn_dir = os.getenv("QAI_WHISPER_DIR", "")
        qnn_python = os.getenv("QAI_WHISPER_PYTHON", "")
        started = time.perf_counter()
        if qnn_dir and qnn_python:
            if not Path(qnn_python).is_file() or not (Path(qnn_dir) / "models" / "encoder.onnx").is_file() or not (Path(qnn_dir) / "models" / "decoder.onnx").is_file():
                raise ValueError("Qualcomm Whisper Python or ONNX model assets are missing")
            output = folder / "qnn-transcript.json"
            command = [qnn_python, str(ROOT / "lecturelens" / "qnn_transcribe.py"), "--app-dir", qnn_dir, "--audio", str(folder / lecture["audio"]), "--output", str(output)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=1800, shell=False)
            if completed.returncode != 0 or not output.is_file():
                raise ValueError((completed.stderr or completed.stdout or "Qualcomm Whisper failed")[-1000:])
            result = json.loads(output.read_text(encoding="utf-8"))
            lecture["segments"] = result["segments"]
            lecture["transcription"] = {"engine": "Qualcomm AI Hub Whisper sample", "acceleration": "QNN configured; verify provider on device", "timing": result["timing"]}
        else:
            binary = os.getenv("WHISPER_CLI", "")
            model = os.getenv("WHISPER_MODEL", "")
            if not binary or not model:
                raise ValueError("Configure Qualcomm Whisper or whisper.cpp before starting LectureLens")
            if not Path(binary).is_file() or not Path(model).is_file():
                raise ValueError("Whisper CLI or model file does not exist")
            output = folder / "whisper-output"
            command = [binary, "-m", model, "-f", str(folder / lecture["audio"]), "-osrt", "-of", str(output)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=900, shell=False)
            if completed.returncode != 0 or not output.with_suffix(".srt").is_file():
                raise ValueError((completed.stderr or completed.stdout or "Whisper failed")[-1000:])
            lecture["segments"] = parse_transcript(output.with_suffix(".srt").read_text(encoding="utf-8", errors="replace"), "whisper-output.srt")
            lecture["transcription"] = {"engine": "whisper.cpp", "acceleration": "not verified"}
        lecture["transcription"]["wall_seconds"] = round(time.perf_counter() - started, 2)
        lecture["transcription"]["segments"] = len(lecture["segments"])
        save_lecture(DATA, lecture)
        self.json_response(lecture)


def main():
    parser = argparse.ArgumentParser(description="LectureLens offline lecture explorer")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), LectureHandler)
    address = f"http://127.0.0.1:{args.port}"
    print(f"LectureLens running at {address}")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
