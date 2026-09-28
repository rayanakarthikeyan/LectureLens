"""Import, indexing, and retrieval. No remote services are used."""

from __future__ import annotations

import base64
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

MAX_AUDIO = 120 * 1024 * 1024
MAX_PDF = 30 * 1024 * 1024
MAX_TRANSCRIPT = 4 * 1024 * 1024
ALLOWED_AUDIO = {".mp3", ".m4a", ".wav", ".ogg", ".webm", ".mp4"}
WORDS = re.compile(r"[\w']+", re.UNICODE)
TIMESTAMP = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})(?:[.,](\d{1,3}))?")


def parse_time(value: str) -> float:
    match = TIMESTAMP.fullmatch(value.strip())
    if not match:
        raise ValueError(f"Invalid timestamp: {value}")
    hours, minutes, seconds, millis = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int((millis or "0").ljust(3, "0")) / 1000


def parse_transcript(source: str, filename: str = "") -> list[dict]:
    """Accept SRT, VTT, and timestamped text. Plain text gets no invented times."""
    source = source.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    blocks = re.split(r"\n\s*\n", source)
    segments = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0] == "WEBVTT" or lines[0].startswith("NOTE "):
            continue
        timing_idx = next((i for i, line in enumerate(lines[:3]) if "-->" in line), None)
        if timing_idx is None:
            continue
        raw_start, raw_end = [part.strip().split()[0] for part in lines[timing_idx].split("-->", 1)]
        try:
            start, end = parse_time(raw_start), parse_time(raw_end)
        except ValueError:
            continue
        body = " ".join(lines[timing_idx + 1 :])
        body = re.sub(r"<[^>]*>", "", body).strip()
        if body and end >= start:
            segments.append({"id": len(segments), "start": start, "end": end, "text": body, "page": None})

    if not segments:
        lines = [line.strip() for line in source.splitlines() if line.strip() and line.strip() != "WEBVTT"]
        for line in lines:
            match = re.match(r"^\[?((?:(?:\d+):)?\d{1,2}:\d{2}(?:[.,]\d{1,3})?)\]?\s*[-–:]?\s+(.+)$", line)
            if match:
                segments.append({"id": len(segments), "start": parse_time(match.group(1)), "end": None, "text": match.group(2), "page": None})
        if not segments:
            chunks = re.split(r"(?<=[.!?])\s+", " ".join(lines))
            segments = [{"id": i, "start": None, "end": None, "text": chunk, "page": None} for i, chunk in enumerate(chunks) if chunk]
    return segments


def tokens(text: str) -> list[str]:
    return [word.lower() for word in WORDS.findall(text) if len(word) > 1]


def search_lecture(lecture: dict, query: str, limit: int = 12) -> list[dict]:
    query_terms = tokens(query)
    if not query_terms:
        return []
    records = []
    for segment in lecture.get("segments", []):
        records.append({"kind": "transcript", "id": segment["id"], "text": segment["text"], "start": segment["start"], "end": segment["end"], "page": segment.get("page")})
    for page in lecture.get("pages", []):
        records.append({"kind": "slide", "id": page["number"], "text": page["text"], "page": page["number"], "start": None, "end": None})
    if not records:
        return []

    docs = [tokens(record["text"]) for record in records]
    n = len(docs)
    avg_len = sum(len(doc) for doc in docs) / n or 1
    df = {term: sum(term in doc for doc in docs) for term in set(query_terms)}
    results = []
    for record, doc in zip(records, docs):
        if not doc:
            continue
        score = 0.0
        for term in set(query_terms):
            count = doc.count(term)
            if count:
                idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
                score += idf * count * 2.2 / (count + 1.2 * (0.25 + 0.75 * len(doc) / avg_len))
        if score:
            text = record["text"]
            first = min((m.start() for term in query_terms for m in re.finditer(r"\b" + re.escape(term) + r"\b", text, re.I)), default=0)
            left = max(0, first - 85)
            right = min(len(text), first + 210)
            snippet = ("…" if left else "") + text[left:right].strip() + ("…" if right < len(text) else "")
            results.append({**{k: v for k, v in record.items() if k != "text"}, "snippet": snippet, "score": round(score, 3)})
    results.sort(key=lambda item: (-item["score"], item["kind"] != "transcript", item["id"]))
    return results[:limit]


def decode_upload(upload: dict | None, allowed: set[str], max_size: int) -> tuple[str, bytes] | None:
    if not upload:
        return None
    name = Path(str(upload.get("name", ""))).name
    if Path(name).suffix.lower() not in allowed:
        raise ValueError(f"Unsupported file type: {name}")
    try:
        content = base64.b64decode(upload["data"], validate=True)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid upload: {name}") from exc
    if len(content) > max_size:
        raise ValueError(f"File is too large: {name}")
    return name, content


def extract_pdf(pdf_path: Path, pages_dir: Path) -> list[dict]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for PDF import. Run: pip install -r requirements.txt") from exc
    document = pymupdf.open(pdf_path)
    if document.page_count > 80:
        raise ValueError("PDF exceeds the 80-page prototype limit")
    pages_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for index, page in enumerate(document):
        image_name = f"page-{index + 1}.png"
        page.get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False).save(pages_dir / image_name)
        page_text = page.get_text("text").replace("\ufffd", "").strip()
        pages.append({"number": index + 1, "text": page_text, "image": f"pages/{image_name}"})
    return pages


def lecture_summary(lecture: dict) -> dict:
    return {key: lecture[key] for key in ("id", "title", "created_at", "audio", "pdf") if key in lecture} | {"segments": len(lecture.get("segments", [])), "pages": len(lecture.get("pages", []))}


def save_lecture(data_dir: Path, lecture: dict) -> None:
    path = data_dir / lecture["id"] / "lecture.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(lecture, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_lecture(data_dir: Path, lecture_id: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{32}", lecture_id):
        raise FileNotFoundError("Lecture not found")
    path = data_dir / lecture_id / "lecture.json"
    return json.loads(path.read_text(encoding="utf-8"))


def new_lecture(data_dir: Path, title: str, audio: tuple[str, bytes] | None, pdf: tuple[str, bytes] | None, transcript: tuple[str, bytes] | None) -> dict:
    if not any((audio, pdf, transcript)):
        raise ValueError("Add at least one audio, PDF, or transcript file")
    lecture_id = uuid.uuid4().hex
    folder = data_dir / lecture_id
    folder.mkdir(parents=True)
    lecture = {"id": lecture_id, "title": (title.strip() or "Untitled lecture")[:120], "created_at": datetime.now(timezone.utc).isoformat(), "audio": None, "pdf": None, "segments": [], "pages": [], "transcription": None}
    try:
        if audio:
            name, content = audio
            lecture["audio"] = "audio" + Path(name).suffix.lower()
            (folder / lecture["audio"]).write_bytes(content)
        if pdf:
            name, content = pdf
            lecture["pdf"] = "slides.pdf"
            (folder / "slides.pdf").write_bytes(content)
            lecture["pages"] = extract_pdf(folder / "slides.pdf", folder / "pages")
        if transcript:
            name, content = transcript
            decoded = content.decode("utf-8-sig", errors="replace")
            lecture["segments"] = parse_transcript(decoded, name)
            (folder / ("transcript-original" + Path(name).suffix.lower())).write_bytes(content)
        save_lecture(data_dir, lecture)
        return lecture
    except Exception:
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        raise
