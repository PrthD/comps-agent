"""Offline tests for the Gemini agent layer (BUILD_BRIEF §7/§11, P3).

The real Gemini API is NEVER called: the LLM seams are mocked — ``google.genai.Client`` for the
extract/reason unit tests, and the agent functions for the orchestration tests. The point of these
tests is the trust boundary (the LLM never overwrites a number), the ≤2-call budget, the bounded
re-query, and the deterministic fallback.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import config
from app.agent import orchestrator as orch
from app.agent.extract import _ExtractedSubject, extract_subject
from app.agent.reason import reason_over_valuation
from app.schemas import ScoredComp, Valuation


def _valuation_with(n_comps, confidence, make_comp) -> Valuation:
    """Build a Valuation carrying ``n_comps`` non-flagged comps at a given confidence level."""
    comps = [
        ScoredComp(
            comp=make_comp(), similarity=0.9, subscores={}, adjustments={}, adjusted_price=500000
        )
        for _ in range(n_comps)
    ]
    return Valuation(
        conservative_value=480000,
        point_estimate=500000,
        range_low=470000,
        range_high=520000,
        confidence=confidence,
        confidence_factors={},
        comps=comps,
        rationale="",
        mode="deterministic",
        elapsed_ms=0,
    )


def _patch_genai_client(monkeypatch, response):
    """Swap ``google.genai.Client`` for a fake that returns ``response`` and counts the calls."""
    state = {"calls": 0, "last_kwargs": None}

    class _Models:
        def generate_content(self, **kwargs):
            state["calls"] += 1
            state["last_kwargs"] = kwargs
            return response

    class _Client:
        def __init__(self, **_kwargs):
            self.models = _Models()

    monkeypatch.setattr("google.genai.Client", _Client)
    return state


def test_fallback_runs_without_key_and_matches_core(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """No key → mode 'deterministic' and numbers identical to the pure core pipeline."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)
    subject = make_subject()
    expected = orch.value_deterministic(subject, synthetic_store, hedonic_model)
    got = orch.run_valuation(subject, store=synthetic_store, hedonic=hedonic_model)

    assert got.mode == "deterministic"
    assert got.conservative_value == expected.conservative_value
    assert got.point_estimate == expected.point_estimate
    assert got.range_low == expected.range_low
    assert got.range_high == expected.range_high
    assert got.confidence == expected.confidence
    assert got.rationale == expected.rationale  # templated, byte-identical
    assert [sc.comp.sale_price for sc in got.comps] == [sc.comp.sale_price for sc in expected.comps]


def test_extract_maps_fields_and_flags_missing(monkeypatch):
    """A known parse maps to the right Subject fields; absent fields/coords are flagged."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    parsed = _ExtractedSubject(
        property_type="detached",
        beds=4.0,
        baths=2.5,
        sqft_living=2400,
        year_built=1998,
        grade=9,
        sqft_lot=None,  # absent in the document
        condition=None,  # absent in the document
    )
    state = _patch_genai_client(monkeypatch, SimpleNamespace(parsed=parsed, text="{}"))

    subject = extract_subject("4 bed / 2.5 bath, 2400 sqft, built 1998, grade 9")

    assert state["calls"] == 1  # exactly one extraction LLM call
    assert (subject.beds, subject.baths, subject.sqft_living) == (4.0, 2.5, 2400)
    assert (subject.year_built, subject.grade) == (1998, 9)
    # Missing fields are flagged for review, never fabricated:
    assert subject.sqft_lot is None and "sqft_lot" in subject.needs_review
    assert subject.condition is None and "condition" in subject.needs_review
    # Coordinates are never read from a document:
    assert "lat" in subject.needs_review and "lng" in subject.needs_review
    assert subject.field_confidence["lat"] == 0.0
    assert subject.field_confidence["beds"] == 0.9
    # As-of date defaults inside the data window (not today), so extraction valuations find comps:
    assert subject.as_of_date == config.DEFAULT_AS_OF_DATE


def test_extract_requires_a_key(monkeypatch):
    """With no key, extraction refuses (the no-LLM path enters via a hand-built Subject instead)."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)
    try:
        extract_subject("anything")
    except RuntimeError:
        return
    raise AssertionError("extract_subject should raise without a configured key")


def test_reason_returns_prose_without_mutating(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """Reasoning returns a string and does not change a single field of the finished Valuation."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    subject = make_subject()
    valuation = orch.value_deterministic(subject, synthetic_store, hedonic_model)
    snapshot = valuation.model_copy(deep=True)

    prose = "Conservative value is well supported by nearby recent comps."
    state = _patch_genai_client(monkeypatch, SimpleNamespace(text=prose, parsed=None))

    text = reason_over_valuation(subject, valuation)

    assert state["calls"] == 1  # exactly one reasoning LLM call
    assert text == prose
    assert valuation == snapshot  # pydantic equality: nothing mutated


def test_agent_path_keeps_numbers_and_replaces_rationale(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """mode='agent', rationale replaced, but the LLM string overwrites no computed number."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    subject = make_subject()
    expected = orch.value_deterministic(subject, synthetic_store, hedonic_model)

    calls = {"n": 0}

    def fake_reason(subj, val):
        calls["n"] += 1
        return "AGENT RATIONALE: point estimate is $999,999,999."  # a number it cannot apply

    monkeypatch.setattr(orch, "reason_over_valuation", fake_reason)
    got = orch.run_valuation(subject, store=synthetic_store, hedonic=hedonic_model)

    assert got.mode == "agent"
    assert calls["n"] == 1  # exactly one reasoning call
    assert got.rationale == "AGENT RATIONALE: point estimate is $999,999,999."
    assert got.point_estimate == expected.point_estimate
    assert got.conservative_value == expected.conservative_value
    assert (got.range_low, got.range_high) == (expected.range_low, expected.range_high)
    assert [sc.adjusted_price for sc in got.comps] == [sc.adjusted_price for sc in expected.comps]


def _insufficient_valuation() -> Valuation:
    """The empty / insufficient-comps result: zeroed figures, a fixed templated rationale."""
    return Valuation(
        conservative_value=0,
        point_estimate=0,
        range_low=0,
        range_high=0,
        confidence="Low",
        confidence_factors={},
        comps=[],
        rationale="Insufficient comparable sales: only 1 of 5 retrieved comps are comparable.",
        mode="deterministic",
        elapsed_ms=0,
    )


def test_insufficient_valuation_never_reasons(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """The empty/insufficient state skips the reason LLM and keeps its templated rationale."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    insufficient = _insufficient_valuation()
    monkeypatch.setattr(orch, "value_deterministic", lambda *a, **k: insufficient)
    monkeypatch.setattr(orch, "_requery", lambda *a, **k: None)  # nothing to widen to

    calls = {"n": 0}

    def fake_reason(subj, val):
        calls["n"] += 1
        return "SHOULD NOT BE CALLED"

    monkeypatch.setattr(orch, "reason_over_valuation", fake_reason)
    got = orch.run_valuation(make_subject(), store=synthetic_store, hedonic=hedonic_model)

    assert calls["n"] == 0  # never reasoned over an empty valuation
    assert got.mode == "deterministic"
    assert got.rationale.startswith("Insufficient comparable sales")


def test_run_valuation_falls_back_when_reasoning_fails(
    monkeypatch, make_subject, make_comp, synthetic_store, hedonic_model
):
    """A raising reason call (e.g. 429/timeout) → templated rationale, mode stays deterministic."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    valued = _valuation_with(12, "High", make_comp)  # > floor, High → no re-query
    valued.rationale = "TEMPLATE: conservative value $480,000 from 12 comps."
    monkeypatch.setattr(orch, "value_deterministic", lambda *a, **k: valued)

    def boom(subj, val):
        raise RuntimeError("429 rate limit exceeded")

    monkeypatch.setattr(orch, "reason_over_valuation", boom)
    got = orch.run_valuation(make_subject(), store=synthetic_store, hedonic=hedonic_model)

    assert got.mode == "deterministic"  # honest badge on fallback
    assert got.rationale == "TEMPLATE: conservative value $480,000 from 12 comps."
    assert "429" not in got.rationale  # the raw error never reaches the rationale


@pytest.mark.parametrize(
    "bad_text",
    [
        "",
        "   \n  ",
        "Please provide a complete JSON object so I can write the rationale.",
        "I'm sorry, but the provided data does not contain enough information.",
        "As an AI language model, I cannot generate this without more detail.",
    ],
)
def test_reason_rejects_unusable_output(
    monkeypatch, make_subject, synthetic_store, hedonic_model, bad_text
):
    """Empty/whitespace and meta-commentary responses raise so the orchestrator can fall back."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    subject = make_subject()
    valuation = orch.value_deterministic(subject, synthetic_store, hedonic_model)
    _patch_genai_client(monkeypatch, SimpleNamespace(text=bad_text, parsed=None))

    with pytest.raises(RuntimeError):
        reason_over_valuation(subject, valuation)


def test_run_valuation_rejects_meta_commentary_end_to_end(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """Through the real reason path: meta-commentary output is dropped, not shown to the user."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    subject = make_subject()
    # Real reason_over_valuation, but Gemini returns developer-facing chatter over the payload.
    _patch_genai_client(
        monkeypatch, SimpleNamespace(text="Please provide a complete JSON object.", parsed=None)
    )
    got = orch.run_valuation(subject, store=synthetic_store, hedonic=hedonic_model)

    assert got.mode == "deterministic"  # fell back to the template
    assert got.rationale  # non-empty
    assert "JSON" not in got.rationale and "provide a complete" not in got.rationale.lower()


def test_value_only_skips_reasoning(monkeypatch, make_subject, synthetic_store, hedonic_model):
    """Phase 1 returns the deterministic value with no LLM call, even when a model is available."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    calls = {"n": 0}

    def fake_reason(subj, val):
        calls["n"] += 1
        return "SHOULD NOT BE CALLED IN PHASE 1"

    monkeypatch.setattr(orch, "reason_over_valuation", fake_reason)
    val = orch.value_only(make_subject(), store=synthetic_store, hedonic=hedonic_model)

    assert calls["n"] == 0  # the slow reasoning call is deferred to /api/rationale
    assert val.mode == "deterministic"
    assert val.point_estimate > 0 and val.elapsed_ms >= 0


def test_generate_rationale_returns_agent_prose(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """Phase 2 with a model returns the LLM prose and mode 'agent'."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    monkeypatch.setattr(orch, "reason_over_valuation", lambda s, v: "AGENT PROSE about the value.")
    subject = make_subject()
    text, mode = orch.generate_rationale(subject, store=synthetic_store, hedonic=hedonic_model)

    assert mode == "agent" and text == "AGENT PROSE about the value."


def test_generate_rationale_falls_back_on_failure(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """A reasoning failure (e.g. 429) yields the template and 'deterministic', not the error."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)

    def boom(s, v):
        raise RuntimeError("429 rate limit exceeded")

    monkeypatch.setattr(orch, "reason_over_valuation", boom)
    subject = make_subject()
    text, mode = orch.generate_rationale(subject, store=synthetic_store, hedonic=hedonic_model)

    assert mode == "deterministic"
    assert text and "429" not in text  # the deterministic template, not the raw error


def test_reason_payload_is_display_formatted(monkeypatch, make_subject, make_comp):
    """FIX 1: every number handed to the model is a display string; no raw floats or line items."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    subject = make_subject()
    comp = ScoredComp(
        comp=make_comp(sale_price=588983),
        similarity=0.906722,
        subscores={},
        adjustments={"sqft_living": 12345},  # a per-comp line item that must NOT be passed
        adjusted_price=746521,
        status="included",
    )
    valuation = Valuation(
        conservative_value=588983,
        point_estimate=746521,
        range_low=700000,
        range_high=800000,
        confidence="Medium",
        confidence_factors={
            config.CF_COMP_COUNT: 12.0,
            config.CF_MEAN_DISTANCE_KM: 0.906722123682148,
            config.CF_DISPERSION: 0.13219706878514864,
            config.CF_MEDIAN_AGE_DAYS: 90.0,
            config.CF_MEAN_ADJUSTMENT: 0.0601753152025388,
        },
        comps=[comp],
        rationale="",
        mode="deterministic",
        elapsed_ms=0,
    )
    state = _patch_genai_client(
        monkeypatch, SimpleNamespace(text="A tight lender rationale.", parsed=None)
    )

    reason_over_valuation(subject, valuation)

    payload = state["last_kwargs"]["contents"][1]  # the json.dumps'd payload string
    # Display-quality values are present:
    assert "$588,983" in payload and "$746,521" in payload
    assert "0.9 km" in payload
    assert "13%" in payload and "6%" in payload and "90 days" in payload
    # Raw float precision and per-comp line-item integers never reach the model:
    assert "0.13219" not in payload and "0.906722" not in payload
    assert "12345" not in payload


def test_requery_runs_at_most_once(monkeypatch, make_subject, synthetic_store, hedonic_model):
    """A thin (far-away) subject triggers the widening, which is bounded to a single attempt."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)  # isolate the re-query from reasoning
    far_subject = make_subject(lat=48.20, lng=-121.50)  # ~60+ km from the synthetic cluster

    real_requery = orch._requery
    calls = {"n": 0}

    def counting_requery(*args, **kwargs):
        calls["n"] += 1
        return real_requery(*args, **kwargs)

    monkeypatch.setattr(orch, "_requery", counting_requery)
    valuation = orch.run_valuation(far_subject, store=synthetic_store, hedonic=hedonic_model)

    assert calls["n"] == 1  # widened exactly once — never looped
    assert valuation.mode == "deterministic"
    assert isinstance(valuation.point_estimate, int)  # still a complete, valid Valuation


def test_value_document_uses_at_most_two_llm_calls(
    monkeypatch, make_subject, synthetic_store, hedonic_model
):
    """The document path = extract + reason = ≤2 LLM calls; numbers still come from the core."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    central = make_subject()  # valid coords at the cluster center
    counts = {"extract": 0, "reason": 0}

    def fake_extract(content, mime_type=None):
        counts["extract"] += 1
        return central

    def fake_reason(subject, valuation):
        counts["reason"] += 1
        return "DOC RATIONALE"

    monkeypatch.setattr(orch, "extract_subject", fake_extract)
    monkeypatch.setattr(orch, "reason_over_valuation", fake_reason)

    expected = orch.value_deterministic(central, synthetic_store, hedonic_model)
    got = orch.value_document("listing text", store=synthetic_store, hedonic=hedonic_model)

    assert counts["extract"] == 1 and counts["reason"] == 1
    assert counts["extract"] + counts["reason"] <= 2  # ≤2 LLM calls per valuation
    assert got.mode == "agent"
    assert got.rationale == "DOC RATIONALE"
    assert got.point_estimate == expected.point_estimate  # core number, not the LLM


def test_adopt_widened_gates_on_confidence(make_comp):
    """Adopted only above the comp floor AND with confidence no worse, and only if improving."""
    current = _valuation_with(9, "Medium", make_comp)  # thin → would trigger the re-query
    assert orch._adopt_widened(current, _valuation_with(15, "Low", make_comp)) is False  # worse
    assert orch._adopt_widened(current, _valuation_with(6, "High", make_comp)) is False  # < floor
    assert orch._adopt_widened(current, _valuation_with(9, "Medium", make_comp)) is False  # no gain
    assert orch._adopt_widened(current, _valuation_with(15, "High", make_comp)) is True  # adopt


def test_run_valuation_does_not_adopt_lower_confidence(
    monkeypatch, make_subject, make_comp, synthetic_store, hedonic_model
):
    """End-to-end: a widened result with more comps but lower confidence is NOT adopted."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)
    current = _valuation_with(9, "Medium", make_comp)  # 9 < TARGET_COMPS_MIN → re-query fires
    widened = _valuation_with(15, "Low", make_comp)  # tempting count, worse comparability
    monkeypatch.setattr(orch, "value_deterministic", lambda *a, **k: current)
    monkeypatch.setattr(orch, "_requery", lambda *a, **k: widened)

    got = orch.run_valuation(make_subject(), store=synthetic_store, hedonic=hedonic_model)

    assert got.confidence == "Medium" and len(got.comps) == 9  # kept the better original


def test_value_deterministic_rejects_none_coords(make_subject, synthetic_store, hedonic_model):
    """The guard fails fast on None coords instead of producing NaN distances silently."""
    subject = make_subject(lat=None, lng=None)
    with pytest.raises(ValueError, match="lat"):
        orch.value_deterministic(subject, synthetic_store, hedonic_model)
