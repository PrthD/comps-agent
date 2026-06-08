"""Document / image / text → structured ``Subject`` via Gemini Flash-Lite (BUILD_BRIEF §7, P3).

This is the LLM's NORMALIZER role on the trust boundary: it reads a listing, an appraisal PDF, an
image, or pasted text and maps the property's attributes into the ``Subject`` contract. It never
values anything and never fabricates a value to fill a gap — a missing or ambiguous field comes
back null, is recorded with low ``field_confidence``, and is added to ``needs_review``. Coordinates
are deliberately never read from a document (listings don't carry them reliably); they are flagged
for the caller (the form / API path supplies real lat/lng directly).

Structured output (``response_schema``) gives us a clean, typed payload instead of free-text
parsing. The single ``generate_content`` call here is LLM call #1 of the ≤2-per-valuation budget.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app import config
from app.core.data import derive_property_type
from app.schemas import Subject

# Structural fields the LLM may read off a document. ``property_type`` is handled separately (it is
# advisory — retrieval re-derives it from grade) and lat/lng are intentionally excluded: never
# inferred from a document, always supplied by the caller.
_NUMERIC = ("beds", "baths", "sqft_living", "sqft_lot", "year_built", "condition", "grade")

_SYSTEM_INSTRUCTION = (
    "You normalize one residential property's details from a listing, appraisal, or pasted text "
    "into a structured record for a lender's valuation tool. Extract ONLY what is explicitly "
    "stated. If a field is absent, illegible, or ambiguous, leave it null — never guess, estimate, "
    "average, or infer a value to fill a gap. List any field you DID populate but are unsure about "
    "in `uncertain_fields`. Do not output coordinates. You never estimate the property's value."
)

_PROMPT = (
    "Extract this property's details into the schema. `sqft_living` is finished living area; "
    "`sqft_lot` is land/lot size. `condition` is a 1-5 rating only if such a scale is given, else "
    "null. `grade` is a numeric construction-quality grade only if present, else null. Leave "
    "anything not explicitly stated as null."
)


class _ExtractedSubject(BaseModel):
    """Gemini structured-output target. Every field is optional so missing data stays null."""

    property_type: str | None = None
    beds: float | None = None
    baths: float | None = None
    sqft_living: int | None = None
    sqft_lot: int | None = None
    year_built: int | None = None
    condition: int | None = None
    grade: int | None = None
    uncertain_fields: list[str] = Field(default_factory=list)


def _to_content_part(content: bytes | str, mime_type: str | None):
    """Wrap raw input as a Gemini content part: bytes need a mime type; text is passed through."""
    if isinstance(content, bytes):
        if not mime_type:
            raise ValueError("mime_type is required for binary (PDF/image) extraction input")
        from google.genai import types

        return types.Part.from_bytes(data=content, mime_type=mime_type)
    return content  # a plain string is itself a valid content part


def _sanitize(field: str, value):
    """Drop values that violate the ``Subject`` contract (so we flag, never coerce, bad data)."""
    if value is None:
        return None
    if field in ("sqft_living", "sqft_lot") and value <= 0:
        return None
    if field == "condition" and not (1 <= value <= 5):
        return None
    return value


def _build_subject(extracted: _ExtractedSubject) -> Subject:
    """Map the LLM's optional fields onto a ``Subject``, recording confidence + needs_review.

    Required-by-contract fields that are missing get an obvious placeholder (``sqft_living=1``;
    ``lat=lng=0.0``) and are added to ``needs_review`` — a flagged placeholder, never a fabricated
    real value. The caller/UI must resolve everything in ``needs_review`` before trusting a result.
    """
    uncertain = set(extracted.uncertain_fields or [])
    confidence: dict[str, float] = {}
    needs_review: list[str] = []
    values: dict[str, float | int] = {}

    for field in _NUMERIC:
        value = _sanitize(field, getattr(extracted, field))
        if value is None:
            confidence[field] = 0.0
            needs_review.append(field)
        else:
            values[field] = value
            confidence[field] = 0.4 if field in uncertain else 0.9
            if field in uncertain:
                needs_review.append(field)

    # property_type is advisory (retrieval re-derives it from grade) → never blocks review.
    property_type = extracted.property_type or derive_property_type(values.get("grade"))
    has_pt = bool(extracted.property_type) and "property_type" not in uncertain
    confidence["property_type"] = 0.9 if has_pt else 0.4

    # Coordinates are never read from a document; the caller supplies them (the form path does).
    confidence["lat"] = confidence["lng"] = 0.0
    needs_review.extend(("lat", "lng"))

    # Missing required fields are left as None (the canonical "not provided") and flagged in
    # needs_review — never backfilled with a fabricated or placeholder value. The gate catches them.
    return Subject(
        property_type=property_type,
        beds=values.get("beds"),
        baths=values.get("baths"),
        sqft_living=values.get("sqft_living"),
        sqft_lot=values.get("sqft_lot"),
        year_built=values.get("year_built"),
        condition=values.get("condition"),
        grade=values.get("grade"),
        lat=None,
        lng=None,
        # Default to the in-window date the form path uses, not date.today(): a today() default
        # falls outside the 2014-05..2015-05 data window and returns zero comps. The user can
        # still change it in the form.
        as_of_date=config.DEFAULT_AS_OF_DATE,
        field_confidence=confidence,
        needs_review=sorted(set(needs_review)),
    )


def extract_subject(content: bytes | str, mime_type: str | None = None) -> Subject:
    """Extract a ``Subject`` (per-field confidence + needs_review) from a doc / image / text.

    Requires a configured ``GEMINI_API_KEY``; callers that want a no-LLM path enter the pipeline
    with a hand-built ``Subject`` (the form path) instead of calling this.
    """
    if not config.MODEL_AVAILABLE:
        raise RuntimeError("extract_subject requires GEMINI_API_KEY; none is configured")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.GEMINI_EXTRACTION_MODEL,
        contents=[_to_content_part(content, mime_type), _PROMPT],
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=_ExtractedSubject,
            temperature=0.0,
        ),
    )
    extracted = response.parsed
    if not isinstance(extracted, _ExtractedSubject):
        extracted = _ExtractedSubject.model_validate_json(response.text or "{}")
    return _build_subject(extracted)
