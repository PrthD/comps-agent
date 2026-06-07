"""Offline tests for the FastAPI layer (BUILD_BRIEF §8/§11, P4).

The real Gemini API is never called: extraction is mocked and valuation runs in deterministic mode
(MODEL_AVAILABLE forced False). The TestClient context manager triggers the lifespan, so the real
bundled store + hedonic are loaded once via ``orchestrator.init`` — these are true integration tests
of the routes and the completeness gate.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.schemas import Subject, required_fields_missing


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:  # runs lifespan startup → orchestrator.init()
        yield test_client


def test_health_reflects_model_available(client, monkeypatch):
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["model_available"] is True
    assert body["comps_loaded"] > 0  # store loaded at startup, not per request

    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)
    assert client.get("/api/health").json()["model_available"] is False


def test_value_gate_rejects_incomplete_subject(client, monkeypatch):
    """A half-read doc (placeholder sqft/coords, missing beds) hits the gate, not a valuation."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)
    payload = {
        "property_type": "detached",
        "beds": 0.0,  # placeholder for "missing"
        "baths": 2.0,
        "sqft_living": 1,  # extractor placeholder
        "lat": 0.0,
        "lng": 0.0,  # coordinate placeholder
        "as_of_date": "2015-05-01",
        "needs_review": ["lat", "lng", "beds", "sqft_living"],
    }
    resp = client.post("/api/value", json=payload)

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "incomplete_subject"
    assert set(body["missing_fields"]) == {"sqft_living", "beds", "lat", "lng"}
    assert "conservative_value" not in body  # NO valuation was produced
    assert "comps" not in body


def test_value_complete_subject_returns_valuation(client, monkeypatch):
    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)  # deterministic path, no LLM
    payload = {
        "property_type": "detached",
        "beds": 3.0,
        "baths": 2.0,
        "sqft_living": 1800,
        "sqft_lot": 4000,
        "year_built": 1960,
        "condition": 3,
        "grade": 7,
        "lat": 47.6795,
        "lng": -122.346,
        "as_of_date": "2015-05-01",
    }
    resp = client.post("/api/value", json=payload)

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "deterministic"
    assert body["conservative_value"] > 0
    assert body["conservative_value"] <= body["point_estimate"]  # conservative headline
    assert len(body["comps"]) >= 1


def test_extract_returns_fields_and_does_not_value(client, monkeypatch, make_subject):
    """Extraction returns the Subject (with needs_review) and never auto-chains into a valuation."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    extracted = make_subject(
        field_confidence={"beds": 0.9, "lat": 0.0}, needs_review=["lat", "lng", "sqft_lot"]
    )
    calls = {"n": 0}

    def fake_extract(content, mime_type=None):
        calls["n"] += 1
        return extracted

    monkeypatch.setattr("app.main.extract_subject", fake_extract)
    resp = client.post("/api/extract", data={"text": "3 bed / 2 bath, 2000 sqft"})

    assert resp.status_code == 200
    body = resp.json()
    assert calls["n"] == 1
    assert body["beds"] == extracted.beds
    assert body["needs_review"] == ["lat", "lng", "sqft_lot"]
    assert "conservative_value" not in body and "point_estimate" not in body  # not valued


def test_extract_accepts_file_upload(client, monkeypatch, make_subject):
    """Multipart upload (python-multipart) routes raw bytes + mime type into extraction."""
    monkeypatch.setattr(config, "MODEL_AVAILABLE", True)
    seen = {}

    def fake_extract(content, mime_type=None):
        seen["type"] = type(content).__name__
        seen["mime"] = mime_type
        return make_subject(needs_review=["lat", "lng"])

    monkeypatch.setattr("app.main.extract_subject", fake_extract)
    resp = client.post(
        "/api/extract", files={"file": ("listing.pdf", b"%PDF-1.4 fake", "application/pdf")}
    )

    assert resp.status_code == 200
    assert seen["type"] == "bytes" and seen["mime"] == "application/pdf"


def test_extract_without_key_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(config, "MODEL_AVAILABLE", False)
    resp = client.post("/api/extract", data={"text": "anything"})
    assert resp.status_code == 503  # extraction needs the model; form path doesn't


def test_samples_are_gate_complete_and_varied(client):
    body = client.get("/api/samples").json()
    assert len(body) >= 3
    ids = {s["id"] for s in body}
    assert {"wallingford-dense", "foothills-sparse", "columbia-city-outliers"} <= ids
    for sample in body:
        subject = Subject(**sample["subject"])
        assert required_fields_missing(subject) == []  # every demo subject passes the gate
