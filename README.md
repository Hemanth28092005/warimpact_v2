# Global Geopolitical Instability and Trade Impact Platform

Status: Phase 0 complete.

## Tech Stack

| Layer | Technology | Notes |
| --- | --- | --- |
| Backend | Python 3.11+, FastAPI | Versioned API routes will live under `/api/v1` in later phases. |
| Database | PostgreSQL 15+ | Local development uses Docker Compose. |
| ORM / Migrations | SQLAlchemy 2.x, Alembic | All schema changes go through Alembic migrations. |
| Task Queue | Celery 5.x, Redis 7 | Ingestion and model runs execute as Celery tasks. |
| Scheduling | Celery Beat | Periodic jobs are defined in code, not cron. |
| Queue Monitoring | Flower | Optional local/staging dashboard for queue visibility. |
| Frontend | React 18, Vite 5, TypeScript | No `.jsx` files. |
| Mapping | Deck.gl 9.x, MapLibre GL JS | `.env.example` includes placeholder map token variables. |
| ML / NLP | XGBoost, LightGBM, HuggingFace Transformers | Installed as optional Python dependencies when modeling phases begin. |
| CI | GitHub Actions | Lint, type-check, and tests run on pull requests. |

## Getting Started

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Start Postgres and Redis:

   ```powershell
   docker compose -f docker/docker-compose.yml up -d
   ```

3. Create the Python virtual environment and install pinned backend dependencies:

   ```powershell
   .\scripts\bootstrap_venv.ps1
   ```

   On macOS/Linux:

   ```bash
   bash scripts/bootstrap_venv.sh
   ```

4. Run migrations:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic -c db/alembic.ini upgrade head
   ```

5. Start a Celery worker:

   ```powershell
   celery -A ingestion.common.celery_app worker --loglevel=info
   ```

6. Start the frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

## Phase 0 Complete

Phase 0 provides repository scaffolding, documentation contracts, local Postgres and Redis compose configuration, Celery app wiring, Alembic wiring, a reversible proof migration, CI configuration, and a Vite React TypeScript frontend shell. It intentionally contains no application logic.
