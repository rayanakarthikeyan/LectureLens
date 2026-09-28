# LectureLens — proposal draft

**Use case.** Students often remember that a lecturer explained a concept but cannot find the moment in a long recording or connect it to the relevant slide. LectureLens keeps audio, transcript passages, and slide pages in one private, searchable timeline.

**Prototype completed.** A local Windows app imports recordings, SRT/VTT transcripts, and PDF slides. It renders slide pages, extracts selectable PDF text, ranks search results across slides and transcript passages, jumps to known recording times, and lets the user link a passage to a slide. It runs on `127.0.0.1` and uses no cloud API. Offline transcription adapters are implemented for Qualcomm's Whisper Windows sample and whisper.cpp; the Qualcomm adapter still needs model assets and validation on the target Snapdragon laptop.

**Snapdragon-powered HP PC target.** The app is intended to run on Windows 11 ARM64 Snapdragon-powered HP PCs. Its file handling, browser UI, and local search have no x86-only application dependency. Its QNN adapter calls Qualcomm's Whisper Windows sample with AI Hub encoder and decoder assets. The integration remains unvalidated on the exact target device.

**Differentiator.** Search results are source-linked rather than free-form claims. Students can verify an answer by opening the original transcript time or slide. Manual slide linking avoids pretending an inferred association is certain.

**Demo sequence.** Disconnect Wi-Fi; open the local app; import a recording, timestamped transcript, and slide PDF; search a lecture concept; play from the returned time; open the linked slide. Use original or permitted lecture materials.

**Technical evidence to add before asserting acceleration.** Capture the laptop and chipset model; verify the speech execution provider; measure transcription wall time for the same audio on CPU and QNN; report memory, model size, and battery test method. No NPU, token speed, or battery claim should appear until measured.

**Current limitations.** Search is keyword based, not semantic retrieval. PDFs need selectable text for search. Live capture, automatic slide alignment, validated NPU inference, LLM Q&A, and a packaged installer are not yet implemented. The Qualcomm adapter gives 25-second window timestamps rather than word timestamps.
