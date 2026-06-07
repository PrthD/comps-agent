"""Gemini Flash reasoning: a lender-facing rationale over a FINISHED valuation (BUILD_BRIEF §7, P3).

This is the LLM's EXPLAINER role on the trust boundary. It reads the subject and the completed
``Valuation`` (every figure already computed by the deterministic core) and writes plain English:
why the conservative value is defensible, which comps drove it, what was adjusted, and what was
flagged/excluded and why. It is strictly downstream of the numbers — it returns a *string* only, so
it cannot change a figure, a range, a confidence level, or which comps were used. It may agree or
disagree with the deterministic outlier flags in prose, but it cannot alter them. This is LLM call
#2 of the ≤2-per-valuation budget; the caller assigns the result to ``Valuation.rationale``.
"""

from __future__ import annotations

import json

from app import config
from app.schemas import ScoredComp, Subject, Valuation

_SYSTEM_INSTRUCTION = (
    "You are a real-estate analyst writing a concise, lender-facing rationale for a residential "
    "comparable-sales valuation. A deterministic engine has ALREADY computed every number; the "
    "figures are final. Quote them exactly — never invent, recompute, or change any value, range, "
    "confidence level, or which comps were used or flagged. Explain in plain English: (1) the "
    "conservative value as the defensible figure a lender should size against, and how it relates "
    "to the point estimate and range; (2) which comparable sales most support it and the "
    "adjustments applied to them; (3) which comps were flagged as $/sqft outliers and excluded, "
    "and why. You may briefly note whether you agree with the outlier flags, but you cannot change "
    "them. State key limitations honestly. Output prose only — a few short paragraphs at most."
)

_PROMPT = "Write the rationale for this finished valuation. The JSON below is the computed result:"


def _comp_row(scored: ScoredComp) -> dict:
    """Compact, read-only view of one scored comp for the prompt (numbers exactly as computed)."""
    comp = scored.comp
    return {
        "sale_price": comp.sale_price,
        "adjusted_price": scored.adjusted_price,
        "sale_date": str(comp.sale_date),
        "distance_km": round(comp.distance_km, 2),
        "sqft_living": comp.sqft_living,
        "beds": comp.beds,
        "baths": comp.baths,
        "grade": comp.grade,
        "similarity": round(scored.similarity, 3),
        "adjustments": {k: round(v) for k, v in scored.adjustments.items()},
        "flagged": scored.flagged,
        "flag_reason": scored.flag_reason,
    }


def _payload(subject: Subject, valuation: Valuation) -> dict:
    """Build the read-only JSON payload handed to the model (does not touch the Valuation)."""
    return {
        "subject": {
            "property_type": subject.property_type,
            "beds": subject.beds,
            "baths": subject.baths,
            "sqft_living": subject.sqft_living,
            "year_built": subject.year_built,
            "grade": subject.grade,
            "condition": subject.condition,
            "as_of_date": str(subject.as_of_date),
        },
        "valuation": {
            "conservative_value": valuation.conservative_value,
            "point_estimate": valuation.point_estimate,
            "range_low": valuation.range_low,
            "range_high": valuation.range_high,
            "confidence": valuation.confidence,
            "confidence_factors": valuation.confidence_factors,
        },
        "comps": [_comp_row(sc) for sc in valuation.comps],
    }


def reason_over_valuation(subject: Subject, valuation: Valuation) -> str:
    """Return a plain-English rationale for the valuation. Never mutates ``valuation``.

    Raises on a missing key or an empty/failed response; the orchestrator catches that and falls
    back to the deterministic templated rationale, so a valuation is always returned.
    """
    if not config.MODEL_AVAILABLE:
        raise RuntimeError("reason_over_valuation requires GEMINI_API_KEY; none is configured")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    response = client.models.generate_content(
        model=config.GEMINI_REASONING_MODEL,
        contents=[_PROMPT, json.dumps(_payload(subject, valuation), default=str)],
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_INSTRUCTION,
            temperature=0.2,
        ),
    )
    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise RuntimeError("empty reasoning response from Gemini")
    return text
