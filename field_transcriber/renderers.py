from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def _timestamp(seconds: float, comma: bool = False) -> str:
    milliseconds = round(float(seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    separator = "," if comma else "."
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{separator}{millis:03d}"


def render_markdown(document: dict[str, Any]) -> str:
    recording = document["recording"]["original_name"]
    language = document["language"]["code"]
    lines = [f"# Transcript: {recording}", "", f"Language: `{language}`", ""]
    for segment in document["segments"]:
        speaker = segment.get("speaker") or "UNKNOWN"
        lines.extend([
            f"**[{_timestamp(segment['start'])}–{_timestamp(segment['end'])}] {speaker}**",
            "",
            segment["text"].strip(),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def render_srt(document: dict[str, Any]) -> str:
    blocks = []
    for number, segment in enumerate(document["segments"], 1):
        speaker = segment.get("speaker") or "UNKNOWN"
        blocks.append(
            f"{number}\n{_timestamp(segment['start'], True)} --> {_timestamp(segment['end'], True)}\n[{speaker}] {segment['text'].strip()}"
        )
    return "\n\n".join(blocks) + "\n"


def publish_transcripts(document: dict[str, Any], transcripts_root: Path, digest: str) -> list[Path]:
    target = transcripts_root / digest
    target.mkdir(parents=True, exist_ok=True)
    stem = Path(document["recording"]["original_name"]).stem
    payloads = {
        ".json": json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        ".md": render_markdown(document),
        ".srt": render_srt(document),
    }
    published: list[Path] = []
    for suffix, content in payloads.items():
        destination = target / f"{stem}{suffix}"
        fd, temporary = tempfile.mkstemp(prefix=f".{stem}.", suffix=suffix, dir=target)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        published.append(destination)
    return published
