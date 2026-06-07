"""FastAPI application entrypoint (BUILD_BRIEF §8).

Four routes, with the completeness gate as a first-class backend check:

- ``GET  /api/health``  — readiness + keep-warm: status, model availability, comps loaded.
- ``POST /api/extract`` — document/image/text → a Subject for the UI to review. Extraction ONLY;
  it never auto-chains into valuation (keeps the flow at ≤2 LLM calls and the gate meaningful).
- ``POST /api/value``   — a complete Subject → Valuation. The completeness gate runs FIRST: an
  under-specified subject gets a distinct 422 ``incomplete_subject`` response and NO valuation, so a
  half-read document can never silently produce a misleading "no comps found".
- ``GET  /api/samples`` — a few real King County demo subjects (incl. a sparse-comps and an
  outlier-heavy case) for the UI.

The comps store + hedonic fit are loaded once at startup (``orchestrator.init`` in the lifespan),
never per request.

Timing honesty: ``Valuation.elapsed_ms`` from ``/api/value`` measures exactly the valuation work
the user waits on at "Value" (retrieve → score → flag → estimate → re-query → reasoning).
Extraction is a separate, earlier ``/api/extract`` call the user reviews in between, so it is NOT
folded into this number — the UI's "valued in X.Xs" reflects only the value step, as claimed.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config
from app.agent import orchestrator
from app.agent.extract import extract_subject
from app.schemas import Subject, Valuation, required_fields_missing


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Load the comps store + fit the hedonic model once, before the first request."""
    orchestrator.init()
    yield


app = FastAPI(title="KV Comps Agent", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,  # the Vercel origin(s); configured via env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _demo_subject(**kwargs) -> Subject:
    """Build a King County demo subject (as-of the end of the data window so comps exist)."""
    params = dict(
        property_type="detached",
        beds=3.0,
        baths=2.0,
        condition=3,
        grade=7,
        as_of_date=date(2015, 5, 1),  # data spans 2014-05..2015-05; value as-of the window's end
    )
    params.update(kwargs)
    return Subject(**params)


# Real King County demo subjects (coordinates verified against the bundled store).
_SAMPLES: list[dict] = [
    {
        "id": "wallingford-dense",
        "label": "Wallingford bungalow",
        "description": "Dense urban Seattle — many recent, nearby comps (a few $/sqft outliers).",
        "subject": _demo_subject(
            sqft_living=1800, sqft_lot=4000, year_built=1960, lat=47.6795, lng=-122.346
        ),
    },
    {
        "id": "foothills-sparse",
        "label": "Cascade foothills home",
        "description": "Rural east King County — sparse comps, wider margin, Low confidence.",
        "subject": _demo_subject(
            sqft_living=1700, sqft_lot=12000, year_built=1985, lat=47.60, lng=-121.72
        ),
    },
    {
        "id": "columbia-city-outliers",
        "label": "Columbia City house",
        "description": "High $/sqft dispersion neighborhood — several comps flagged and excluded.",
        "subject": _demo_subject(
            sqft_living=1600, sqft_lot=5000, year_built=1950, lat=47.5453, lng=-122.275
        ),
    },
]


@app.get("/api/health")
def health() -> dict:
    """Readiness + keep-warm probe. ``model_available`` mirrors a configured GEMINI_API_KEY."""
    return {
        "status": "ok",
        "model_available": config.MODEL_AVAILABLE,
        "comps_loaded": orchestrator.store_size(),
    }


@app.get("/api/samples")
def samples() -> list[dict]:
    """Preloaded demo subjects for the UI (a normal, a sparse-comps, and an outlier-heavy case)."""
    return _SAMPLES


@app.post("/api/extract", response_model=Subject)
async def extract(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
) -> Subject:
    """Extract a Subject (field_confidence + needs_review) from an uploaded file OR pasted text.

    Extraction only — the UI shows the result for review/editing, then calls ``/api/value``
    separately. Requires a configured model; the no-LLM path enters via the structured form instead.
    """
    if not config.MODEL_AVAILABLE:
        raise HTTPException(status_code=503, detail="extraction unavailable: no GEMINI_API_KEY")
    if file is None and not text:
        raise HTTPException(status_code=422, detail="provide either a file or text")
    try:
        if file is not None:
            return extract_subject(await file.read(), file.content_type)
        return extract_subject(text)
    except Exception as exc:  # surface LLM/parse failures as a clean 502, never a 500 stack
        raise HTTPException(status_code=502, detail=f"extraction failed: {exc}") from exc


@app.post("/api/value", response_model=None)  # union return; we serialize Valuation ourselves
def value(subject: Subject) -> Valuation | JSONResponse:
    """Value a COMPLETE subject. Completeness gate runs first; incomplete → 422, no valuation."""
    missing = required_fields_missing(subject)
    if missing:
        return JSONResponse(
            status_code=422,
            content={
                "error": "incomplete_subject",
                "missing_fields": missing,
                "message": (
                    "Cannot value: required fields are missing or unconfirmed. "
                    "Provide them (e.g. via the review form) and retry."
                ),
            },
        )
    return orchestrator.run_valuation(subject)
