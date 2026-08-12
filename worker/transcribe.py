from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def normalize_result(raw: dict[str, Any], digest: str, original_name: str, *, duration_seconds: float, peak_gpu_memory_mb: int | None) -> dict[str, Any]:
    segments = []
    for segment in raw.get("segments", []):
        words = []
        for word in segment.get("words", []):
            words.append({
                "text": str(word.get("word", word.get("text", ""))).strip(),
                "start": word.get("start"),
                "end": word.get("end"),
                "confidence": word.get("score", word.get("confidence")),
            })
        segments.append({
            "start": segment.get("start"),
            "end": segment.get("end"),
            "speaker": segment.get("speaker"),
            "text": str(segment.get("text", "")).strip(),
            "confidence": segment.get("score", segment.get("confidence")),
            "words": words,
        })
    return {
        "schema_version": "1.0",
        "recording": {"sha256": digest, "original_name": original_name},
        "language": {"code": raw.get("language", "und"), "confidence": raw.get("language_probability")},
        "segments": segments,
        "run": {
            "model": "large-v3",
            "compute_type": "float16",
            "created_at": datetime.now(UTC).isoformat(),
            "duration_seconds": duration_seconds,
            "peak_gpu_memory_mb": peak_gpu_memory_mb,
        },
    }


def transcribe(input_path: Path, original_name: str, digest: str, token: str) -> dict[str, Any]:
    import torch
    import whisperx
    from whisperx.diarize import DiarizationPipeline

    started = time.monotonic()
    torch.cuda.reset_peak_memory_stats()
    audio = whisperx.load_audio(str(input_path))
    model = whisperx.load_model("large-v3", "cuda", compute_type="float16")
    result = model.transcribe(audio, batch_size=8)
    align_model, metadata = whisperx.load_align_model(language_code=result["language"], device="cuda")
    result = whisperx.align(result["segments"], align_model, metadata, audio, "cuda", return_char_alignments=False)
    diarizer = DiarizationPipeline(token=token, device="cuda", model_name="pyannote/speaker-diarization-community-1")
    diarization = diarizer(audio)
    result = whisperx.assign_word_speakers(diarization, result)
    peak = round(torch.cuda.max_memory_allocated() / (1024 * 1024))
    return normalize_result(result, digest, original_name, duration_seconds=time.monotonic() - started, peak_gpu_memory_mb=peak)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--recording-sha256", required=True)
    parser.add_argument("--original-name", required=True)
    args = parser.parse_args(argv)
    token = os.environ.get("HF_TOKEN")
    if not token:
        parser.error("HF_TOKEN is required")
    document = transcribe(args.input, args.original_name, args.recording_sha256, token)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".transcript.", suffix=".json", dir=args.output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, args.output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
