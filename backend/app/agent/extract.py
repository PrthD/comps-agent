"""Document/text → structured Subject via Gemini Flash-Lite, multimodal (BUILD_BRIEF §7, P3)."""

from __future__ import annotations

from app.schemas import Subject


def extract_subject(content: bytes | str, mime_type: str | None = None) -> Subject:
    """Extract a Subject (with per-field confidence + needs_review) from a doc/image/text. (P3)"""
    raise NotImplementedError("P3: extract_subject (Gemini Flash-Lite)")
