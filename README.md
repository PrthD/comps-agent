# KV Comps Valuation Agent

An explainable, conservative comparable-sales valuation tool for lenders. It mirrors an appraiser's
sales-comparison workflow: retrieve recent nearby sales, flag $/sqft outliers, adjust for
differences between each comp and the subject, and produce a defensible conservative value with a
range, a confidence level, and a plain-English rationale. The headline is the conservative value a
lender can size against, not a single black-box point estimate.

Every number is computed by pure, tested functions. The language model only normalizes the input
and writes the explanation; it never computes or changes a figure.

## Architecture

Subject (PDF, image, pasted text, or a form) goes to AI extraction, which fills a structured
subject for the user to review. The deterministic core then runs over an in-memory King County
sales store: retrieve, score, flag outliers, hedonic adjust, and estimate, producing the
conservative value, range, and confidence. The result is the conservative value, the point estimate
and range, a confidence badge, a comp table with exclusion flags, a map, and the rationale. The
service is stateless. React frontend, FastAPI backend.

## Accuracy

A leave-one-out backtest on King County sales gives a median absolute error (MdAPE) of 9.8% over the
383 valued subjects, with 17 of 400 declined as having too few comparable sales. Off-market
valuation is hard, and this is an honest, defensible result for a transparent comps pipeline. See
`docs/eval_report.md`.

## Run it

Requires Python 3.11 (managed with uv) and Node 20+.

```
make install        # backend (uv sync) + frontend (npm install)
make dev            # run the backend and frontend together
```

Or run each side on its own:

```
make dev-backend    # FastAPI on http://localhost:8000
make dev-frontend   # Vite on http://localhost:5173
```

Open http://localhost:5173, load a sample, and click Value.

Optional: set `GEMINI_API_KEY` in `backend/.env` for AI-written rationales. Without a key the app
runs fully in deterministic mode with a templated rationale; every number is identical either way.

## Common tasks

```
make test     # backend pytest + frontend vitest
make lint     # ruff + TypeScript typecheck
make build    # frontend production build
make data     # regenerate the King County parquet
make eval     # run the backtest, writes docs/eval_report.md
```

## Layout

- `backend/`  FastAPI app, deterministic core, agent layer, and tests
- `frontend/` Vite + React + TypeScript single-page app
- `docs/`     evaluation report and design notes
