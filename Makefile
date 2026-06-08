.PHONY: install dev-backend dev-frontend dev \
        test-backend test-frontend test \
        lint-backend lint-frontend lint \
        build data eval docker-build

# ── Install ───────────────────────────────────────────────────────────────────

install:
	cd backend && uv sync
	cd frontend && npm install

# ── Dev servers ───────────────────────────────────────────────────────────────

dev-backend:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# Run both sides together. Each server needs its own terminal; open a second
# terminal and run `make dev-frontend`, or use a process manager like `foreman`.
dev:
	@echo "Run 'make dev-backend' and 'make dev-frontend' in separate terminals."
	@echo "Or: cd backend && uv run uvicorn app.main:app --reload --port 8000 &"
	@echo "    cd frontend && npm run dev"

# ── Tests ─────────────────────────────────────────────────────────────────────

test-backend:
	cd backend && uv run pytest

test-frontend:
	cd frontend && npm test

test: test-backend test-frontend

# ── Lint / typecheck ──────────────────────────────────────────────────────────

lint-backend:
	cd backend && uv run ruff check .

lint-frontend:
	cd frontend && npx tsc --noEmit

lint: lint-backend lint-frontend

# ── Build ─────────────────────────────────────────────────────────────────────

build:
	cd frontend && npm run build

# ── Data / eval ───────────────────────────────────────────────────────────────

data:
	cd backend && uv run python scripts/prepare_data.py

eval:
	cd backend && uv run python -m app.eval.backtest

# ── Docker ────────────────────────────────────────────────────────────────────

docker-build:
	docker build -t comps-agent ./backend
