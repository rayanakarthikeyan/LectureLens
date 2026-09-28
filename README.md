# LectureLens

An offline lecture explorer built for Windows on Snapdragon PCs. Import audio, a PDF slide deck, and an SRT/VTT transcript to search the lecture and jump back to the cited recording time or slide page. Lecture files and the search index stay in the local `data/` directory.

## Run

Requires Python 3.11 or newer. In PowerShell from this folder:

```powershell
python -m pip install -r requirements.txt
.\run.ps1
```

Open <http://127.0.0.1:8765> if the browser does not open automatically. The server binds only to `127.0.0.1`.

To try the app without your own files, first run `python examples/make_demo_slides.py`, then import `examples/demo.srt` and `examples/demo-slides.pdf` together. Link passages to slides using the selector beside each passage. The sample transcript is fictional and has no audio.

## Input and workflow

- Audio: MP3, M4A, WAV, OGG, WebM, or MP4, up to 120 MB. Playback depends on your browser's codec support.
- Slides: a selectable-text PDF, up to 30 MB and 80 pages. Image-only PDFs display correctly, but their text is not searchable because OCR is not included.
- Transcript: SRT or VTT for timestamps; TXT is accepted but may have no timestamps. A plain text passage gets no invented audio time.
- Search: local BM25-style keyword ranking over transcript passages and extracted PDF text. Results show the source snippet, playback time if known, and linked slide page if assigned.
- Slide alignment: manual per-passage selection, stored in `data/<lecture-id>/lecture.json`.

## Optional Snapdragon QNN transcription

The Qualcomm AI Hub [Whisper Windows sample](https://github.com/qualcomm/ai-hub-apps/blob/main/apps/whisper_windows_py/README.md) is the intended NPU backend. Its official setup uses an **ARM64 Python runtime**, ONNX Runtime QNN, and Qualcomm's encoder and decoder model files. Follow that sample's setup and verify its standalone `demo.py --audio-file` command on your laptop first. Then point LectureLens at the fetched sample directory and its ARM64 virtual environment:

```powershell
$env:QAI_WHISPER_DIR = 'C:\path\to\whisper_windows_py'
$env:QAI_WHISPER_PYTHON = 'C:\path\to\whisper_windows_py\.venv\Scripts\python.exe'
.\run.ps1
```

Import a **16 kHz mono 16-bit PCM WAV** without a transcript and click **Transcribe with Qualcomm Whisper**. LectureLens uses the sample's `WhisperApp` with its QNN model assets, processes 25-second windows, and records wall time. The returned timestamps mark window starts, not exact words. **This integration has not been run or benchmarked on the user's Snapdragon device yet**; confirm the actual execution provider before asserting NPU acceleration in a submission. The model assets are not bundled.

## Alternative offline transcription

LectureLens has an adapter for a local [whisper.cpp](https://github.com/ggml-org/whisper.cpp) `whisper-cli` executable. Download or build the executable and a compatible GGML model from its official project, then set paths before launching:

```powershell
$env:WHISPER_CLI = 'C:\path\to\whisper-cli.exe'
$env:WHISPER_MODEL = 'C:\path\to\ggml-base.en.bin'
.\run.ps1
```

Import a **16 kHz mono 16-bit PCM WAV** without a transcript. The **Transcribe locally with Whisper** button appears in the Recording panel. This adapter runs fully offline but does **not** claim NPU acceleration. Transcription is synchronous and can take several minutes. You can also generate SRT with another local speech recognizer and import it. If both backends are configured, the Qualcomm adapter is used.

Qualcomm publishes [Whisper-Base for Snapdragon X devices](https://aihub.qualcomm.com/compute/models/whisper_base) and a [Windows on Snapdragon Whisper demo](https://www.qualcomm.com/developer/blog/2025/05/deploy-ai-models-on-snapdragon-x-elite-with-qualcomm-ai-hub). The QNN adapter above uses the official sample's model interface; it still needs real device validation.

## What is implemented

- Local import, PDF rendering and text extraction, audio playback, SRT/VTT parsing, timestamped timeline, keyword search, manual slide links, and adapters for the Qualcomm Whisper sample and whisper.cpp.
- No cloud APIs, account, automatic OCR, model-generated summaries, live microphone capture, installer, or measured battery/latency claims. Qualcomm model assets and ARM64 runtime are not bundled.

## Verify

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
```

## Challenge presentation notes

Demonstrate an actual lecture or a recording you own. Show the app in airplane mode, import the files, search for a concept, and open the source moment and slide. Report only measured hardware results and name the execution provider used. The challenge asks for a proposal intended for Snapdragon-powered HP PCs; this code is a prototype for that target, not a completed NPU deployment.
