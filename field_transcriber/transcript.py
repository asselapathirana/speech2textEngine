"""Dependency-free validation for canonical transcript JSON."""

from __future__ import annotations

import math
from typing import Any

from .models import DomainError


def _number(value: Any, name: str, *, nullable: bool = False) -> float | None:
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DomainError(f"{name} must be a number", step="result_validation")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise DomainError(f"{name} must be finite and non-negative", step="result_validation")
    return number


def _confidence(value: Any, name: str) -> None:
    number = _number(value, name, nullable=True)
    if number is not None and number > 1:
        raise DomainError(f"{name} must be between zero and one", step="result_validation")


def validate_transcript(document: Any, expected_digest: str) -> None:
    if not isinstance(document, dict):
        raise DomainError("transcript root must be an object", step="result_validation")
    for key in ("schema_version", "recording", "language", "segments", "run"):
        if key not in document:
            raise DomainError(f"transcript is missing {key}", step="result_validation")
    if document["schema_version"] != "1.0":
        raise DomainError("unsupported transcript schema version", step="result_validation")
    recording = document["recording"]
    if not isinstance(recording, dict) or recording.get("sha256") != expected_digest:
        raise DomainError("transcript recording digest mismatch", step="result_validation")
    if not isinstance(recording.get("original_name"), str) or not recording["original_name"]:
        raise DomainError("transcript recording name is missing", step="result_validation")
    language = document["language"]
    if not isinstance(language, dict) or not isinstance(language.get("code"), str) or not language["code"]:
        raise DomainError("detected language is missing", step="result_validation")
    _confidence(language.get("confidence"), "language confidence")
    run = document["run"]
    if not isinstance(run, dict) or not all(isinstance(run.get(k), str) and run[k] for k in ("model", "compute_type", "created_at")):
        raise DomainError("run metadata is incomplete", step="result_validation")
    segments = document["segments"]
    if not isinstance(segments, list):
        raise DomainError("segments must be a list", step="result_validation")
    if not segments:
        raise DomainError("no speech segments were detected", step="no_speech_detected")
    previous_end = 0.0
    qualifying = 0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise DomainError(f"segment {index} must be an object", step="result_validation")
        start = _number(segment.get("start"), f"segment {index} start")
        end = _number(segment.get("end"), f"segment {index} end")
        if end < start or start < previous_end:
            raise DomainError(f"segment {index} has invalid ordering", step="result_validation")
        previous_end = end
        speaker = segment.get("speaker")
        if speaker is not None and not isinstance(speaker, str):
            raise DomainError(f"segment {index} speaker is invalid", step="result_validation")
        text = segment.get("text")
        if not isinstance(text, str):
            raise DomainError(f"segment {index} text is invalid", step="result_validation")
        if text.strip():
            qualifying += 1
        _confidence(segment.get("confidence"), f"segment {index} confidence")
        words = segment.get("words")
        if not isinstance(words, list):
            raise DomainError(f"segment {index} words must be a list", step="result_validation")
        for word_index, word in enumerate(words):
            if not isinstance(word, dict) or not isinstance(word.get("text"), str):
                raise DomainError(f"word {word_index} in segment {index} is invalid", step="result_validation")
            word_start = _number(word.get("start"), "word start", nullable=True)
            word_end = _number(word.get("end"), "word end", nullable=True)
            if (word_start is None) != (word_end is None) or (word_start is not None and word_end < word_start):
                raise DomainError("word timing is invalid", step="result_validation")
            _confidence(word.get("confidence"), "word confidence")
    if not qualifying:
        raise DomainError("no non-empty speech text was detected", step="no_speech_detected")
