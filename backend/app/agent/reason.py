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
from app.schemas import Subject, Valuation

_SYSTEM_INSTRUCTION = (
    "You are a real-estate analyst writing a concise, lender-facing rationale for a residential "
    "comparable-sales valuation. A deterministic engine has ALREADY computed every figure, and the "
    "UI already shows the user the full stat row, the comparable-sales table, and the per-row "
    "exclusion reasons. Do NOT restate those: never re-list individual comps, their prices, or "
    "their line-item adjustments, and do not repeat every figure back. Instead INTERPRET, in at "
    "most THREE short paragraphs: (1) why the conservative value is the defensible figure a lender "
    "should size against, and how it sits relative to the point estimate and range; (2) what the "
    "comparable set supports in aggregate, not a roll-call of sales; (3) the single most "
    "important limitation or risk a lender should watch. You may quote the conservative value once "
    "if it helps, but keep it tight. Never invent, recompute, or change any number, range, "
    "confidence level, or which comps were used or excluded. Use the provided mean_distance figure "
    "when describing how far comparables are from the subject. Do not infer or compute distances "
    "from other fields. Use plain punctuation only: no em-dashes or en-dashes. Output prose only."
)

_PROMPT = (
    "Write the lender rationale for this finished valuation. The JSON below is the computed result "
    "and an aggregate summary of the comp set, with every figure already display-formatted:"
)

# Phrases that mark developer-facing meta-commentary rather than a lender rationale. If the model
# gets confused (e.g. by a thin payload) and talks about the request, the data, or its own limits
# instead of the valuation, we reject the text and fall back to the deterministic template rather
# than surface raw model chatter to the end user.
_META_MARKERS: tuple[str, ...] = (
    "json",
    "provide a complete",
    "please provide",
    "the provided data",
    "complete object",
    "as an ai",
    "as a language model",
    "i'm sorry",
    "i am sorry",
    "i cannot provide",
    "i cannot generate",
)


def _is_meta_commentary(text: str) -> bool:
    """True if the response is about the request/data/model rather than a lender rationale."""
    low = text.lower()
    return any(marker in low for marker in _META_MARKERS)


# Display formatters — the model must NEVER see a raw float or unformatted integer, so everything
# is pre-formatted to the exact strings a person would read (dollars with commas, distance in km,
# rates as whole percentages, age in whole days). Mirrors the frontend's number formatting.
def _money(value: float) -> str:
    return f"${round(value):,}"


def _km(value: float) -> str:
    return f"{value:.1f} km"


def _pct(value: float) -> str:
    # Half-up (floor(x+0.5)) to byte-match the frontend stat row's Math.round on the SAME source
    # float, so a quoted prose percentage can never disagree with the displayed stat (e.g. 12.5 ->
    # "13%" in both, never "12%" via Python's banker's round). Confidence factors are always >= 0.
    return f"{int(value * 100 + 0.5)}%"


def _factors_display(factors: dict[str, float]) -> dict[str, str]:
    """Confidence factors as display strings (count whole, distance km, rates %, age days)."""
    return {
        "comp_count": str(round(factors.get(config.CF_COMP_COUNT, 0))),
        "mean_distance": _km(factors.get(config.CF_MEAN_DISTANCE_KM, 0.0)),
        "price_dispersion": _pct(factors.get(config.CF_DISPERSION, 0.0)),
        "median_sale_age": f"{round(factors.get(config.CF_MEDIAN_AGE_DAYS, 0.0))} days",
        "mean_adjustment": _pct(factors.get(config.CF_MEAN_ADJUSTMENT, 0.0)),
    }


def _comp_summary(valuation: Valuation) -> dict:
    """Aggregate, display-formatted view of the comp set. No per-comp roll-call, no line items."""
    included = [sc for sc in valuation.comps if sc.status == "included"]
    summary: dict = {
        "total_found": len(valuation.comps),
        "included": len(included),
        "excluded": sum(1 for sc in valuation.comps if sc.status != "included"),
        "excluded_by_reason": {
            "$/sqft outlier": sum(1 for sc in valuation.comps if sc.status == "outlier"),
            "low similarity": sum(1 for sc in valuation.comps if sc.status == "low_similarity"),
            "over adjusted": sum(1 for sc in valuation.comps if sc.status == "large_adjustment"),
        },
    }
    if included:
        adj = [sc.adjusted_price for sc in included]
        sims = [sc.similarity for sc in included]
        summary["included_adjusted_price_range"] = f"{_money(min(adj))} to {_money(max(adj))}"
        summary["included_similarity_range"] = f"{_pct(min(sims))} to {_pct(max(sims))}"
        # No distance range here: proximity is described only by the mean_distance figure in
        # confidence_factors (the stat row's value), so the prose can't quote a max/range instead.
    return summary


def _payload(subject: Subject, valuation: Valuation) -> dict:
    """Read-only, fully display-formatted JSON for the model (never mutates the Valuation).

    Dollars carry "$"/commas, distance is "x.x km", dispersion/adjustment are whole percentages,
    and age is whole days, so the model can only quote display-quality strings. Per-comp line-item
    adjustments are intentionally omitted: the table already shows them, and the prose interprets
    the set in aggregate rather than narrating each sale.
    """
    sqft = f"{subject.sqft_living:,}" if subject.sqft_living else None
    return {
        "subject": {
            "property_type": subject.property_type,
            "beds": subject.beds,
            "baths": subject.baths,
            "sqft_living": sqft,
            "year_built": subject.year_built,
            "grade": subject.grade,
            "condition": subject.condition,
            "as_of_date": str(subject.as_of_date),
        },
        "valuation": {
            "conservative_value": _money(valuation.conservative_value),
            "point_estimate": _money(valuation.point_estimate),
            "range": f"{_money(valuation.range_low)} to {_money(valuation.range_high)}",
            "confidence": valuation.confidence,
            "confidence_factors": _factors_display(valuation.confidence_factors),
        },
        "comp_summary": _comp_summary(valuation),
    }


def reason_over_valuation(subject: Subject, valuation: Valuation) -> str:
    """Return a plain-English rationale for the valuation. Never mutates ``valuation``.

    Raises on a missing key, an empty/failed response, or output that is developer-facing
    meta-commentary rather than a rationale; the orchestrator catches that and falls back to the
    deterministic templated rationale, so a valuation is always returned and raw model text or API
    errors never reach the user.
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
    if _is_meta_commentary(text):
        raise RuntimeError("reasoning response is meta-commentary, not a lender rationale")
    return text
