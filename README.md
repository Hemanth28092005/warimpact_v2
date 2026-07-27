# Global Geopolitical Instability and Trade Impact Platform

Status: Phase 0 complete.

## Tech Stack

| Layer | Technology | Notes |
| --- | --- | --- |
| Backend | Python 3.11+, FastAPI | Versioned API routes will live under `/api/v1` in later phases. |
| Database | PostgreSQL 15+ | Local development uses Docker Compose. |
| ORM / Migrations | SQLAlchemy 2.x, Alembic | All schema changes go through Alembic migrations. |
| Frontend | React 18, Vite 5, TypeScript | No `.jsx` files. |
| Mapping | Deck.gl 9.x, MapLibre GL JS | `.env.example` includes placeholder map token variables. |
| ML / NLP | XGBoost, LightGBM, HuggingFace Transformers | Installed as optional Python dependencies when modeling phases begin. |
| CI | GitHub Actions | Lint, type-check, and tests run on pull requests. |

## Getting Started

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Start Postgres:

   ```powershell
   docker compose -f docker/docker-compose.yml up -d
   ```

3. Install Python dependencies in a Python 3.11+ environment:

   ```powershell
   python -m pip install -e ".[dev]"
   ```

4. Run migrations:

   ```powershell
   python -m alembic -c db/alembic.ini upgrade head
   ```

5. Start the frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

## Phase 0 Complete

Phase 0 provides repository scaffolding, documentation contracts, local Postgres compose configuration, Alembic wiring, a reversible proof migration, CI configuration, and a Vite React TypeScript frontend shell. It intentionally contains no application logic.
