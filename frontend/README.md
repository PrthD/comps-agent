# Frontend, KV Comps Valuation (Vite + React + TS + Tailwind + react-leaflet)

A static single-page app for the comps valuation agent. It talks to the FastAPI backend over HTTP
(`VITE_API_BASE_URL`) and is built for static hosting (for example, Vercel).

**Flow:** input (Upload document / Paste text / Fill form) → review the extracted `Subject` in an
editable form with per-field confidence chips and "needs review" highlights → **Value** → results:
the conservative, lender-facing value as the headline, the point estimate + range, a confidence
badge with its factors, "valued in X ms", a Leaflet map (subject + comp pins, flagged $/sqft
outliers marked distinctly), a sortable comp table, and the rationale (agent or deterministic mode).

Extraction and valuation are **separate** calls, extraction only populates the form for review; it
never auto-values. That keeps the trip to ≤2 LLM calls and makes the completeness gate meaningful.

## Prerequisites

- Node 20+ (developed on Node 22) and npm.
- The backend running and reachable (see below).

## Local dev

From the repository root, `make dev` runs the backend and frontend together, and `make dev-frontend`
runs this app alone. To run the two sides by hand in separate terminals:

**Terminal 1, backend** (from `../backend`):

```bash
cd ../backend
uv sync
# optional: put GEMINI_API_KEY in backend/.env for agent-mode rationales.
# without a key the API runs fully in deterministic mode (templated rationale).
uv run uvicorn app.main:app --reload --port 8000
```

**Terminal 2, frontend** (from this directory):

```bash
npm install
cp .env.example .env        # VITE_API_BASE_URL=http://localhost:8000 (already the default)
npm run dev                 # http://localhost:5173
```

Open http://localhost:5173. Click **Load a sample → Wallingford** and **Value** for a one-click demo.
The "Cascade foothills" sample shows the sparse-comps / Low-confidence path; "Columbia City" shows
several $/sqft outliers being flagged and excluded.

> The samples use an as-of date of **2015-05-01**, inside the dataset window (King County sales run
> 2014-05 → 2015-05). Today's date would find zero comps, the form defaults to 2015-05-01 for the
> same reason.

## Environment

| Variable            | Purpose                                     | Default                 |
| ------------------- | ------------------------------------------- | ----------------------- |
| `VITE_API_BASE_URL` | Base URL of the FastAPI backend (no `/api`) | `http://localhost:8000` |

When deploying, set `VITE_API_BASE_URL` to the deployed backend URL.

## Scripts

| Command           | Does                                                        |
| ----------------- | ---------------------------------------------------------- |
| `npm run dev`     | Vite dev server with HMR.                                  |
| `npm run build`   | Type-check (`tsc --noEmit`) + production build to `dist/`. |
| `npm run preview` | Serve the built `dist/` locally.                           |
| `npm test`        | Vitest component tests (gate-error rendering, results headline). |

## Notes

- **Cold start:** an idle backend can take a few seconds to start. On load the app pings
  `/api/health` and shows a "starting up" state with auto-retry, gating the input UI on the engine
  being ready rather than showing a raw failed fetch.
- **Trust boundary:** every figure shown comes from the backend's structured `Valuation` fields. The
  rationale text is commentary rendered beside the numbers, never the source of a displayed number.
- **Map:** Leaflet + OpenStreetMap tiles (no API key).
