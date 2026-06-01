"""FastAPI application entrypoint (BUILD_BRIEF §8).

Routes (/api/extract, /api/value, /api/health, /api/samples) and CORS are wired in P4.
Kept as a minimal app instance during P0 scaffolding — no routes yet.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="KV Comps Agent", version="0.1.0")
