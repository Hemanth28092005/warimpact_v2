# War Impact Platform — Implementation Plan

Generated from full code review + live database audit (2026-08-26).
Ordered by dependency and risk. Each phase ends with verification steps.

---

## Phase A — Critical Bug Fixes (stop active damage) · ~1 day

### A1. Guard destructive DELETEs in snapshot publishers
**Files:** `ingestion/dashboard/tasks.py:337,369`, `models/commodities/news.py:350`

- Wrap every `DELETE FROM ... WHERE ...` in `if staged_items:` / `if rows_to_insert:`
- Move DELETE + INSERT into a single transaction (they already are per-key; verify no early commit between them)
- Add a row-count sanity check: if new batch is < 20% of previous batch size for that key, log a warning and skip replacement (staleness beats blankness)

**Verify:** Simulate empty fetch (disconnect network) → run task → confirm old rows survive; confirm `regional_headlines` stays at 70 rows across 3 consecutive runs.

### A2. Fix `NameError` in sentiment scorer
**File:** `models/sentiment/scorer.py:147`

```python
pipe = _get_sentiment_pipeline()   # currently never called
if pipe is not None:
    ...
else:
    # fall through to AvgTone fallback instead of crashing
```
- Also fix `_MODEL_LOAD_FAILED` permanent latch (`scorer.py:36`): allow retry after cooldown instead of disabling until process restart
- Fix nondeterministic result ordering (L8): return results indexed to input events

**Verify:** Run `run_daily_sentiment_pipeline` locally → confirm RoBERTa path executes (or clean fallback) and `country_daily_signals` receives fresh sentiment rows.

### A3. Remove unconditional `verify=False` on GDELT fetches
**File:** `ingestion/gdelt/fetcher.py:117`

- Delete `verify=False` (default cert verification)
- If corporate proxy issues arise, gate behind `GDELT_TLS_INSECURE=true` env flag that logs a loud warning when set

**Verify:** Fetch lastupdate.txt successfully; confirm no `SSLError` in logs.

### A4. Stop leaking Gemini key in URL
**File:** `ingestion/dashboard/llm_filter.py:405`

- Replace `?key={gemini_key}` with header `x-goog-api-key: {gemini_key}`
- Remove debug `print(get_settings().psycopg_database_url)` from `ingestion/common/db.py:28`
- Add `GROQ_API_KEY`, `GEMINI_API_KEY` to `.env.example`

---

## Phase B — Real Trade Data Ingestion (fills the empty core table) · ~2 days

Current state: `bilateral_trade` = **0 rows**, so `trade_concentration` is a constant `0.05` fallback for all countries. The hardcoded fake matrix in `models/trade/ingest_trade.py` must go.

### B1. Build real UN Comtrade+ ingestion client
**New file:** `ingestion/comtrade/client.py`
- Register free API key at comtradeapi.un.org → store as `COMTRADE_API_KEY`
- Endpoint: `/v1/get/C/A/HS?reporterCode=...&period=2024&cmdCode=TOTAL&flowCode=X,M`
- Map ISO3 → UN M49 reporter codes for all 38 scope countries (+ all partners)
- Rate-limit aware: free tier ≈ 500 calls/day — batch reporters, cache responses, use Celery beat daily window
- Timeouts + retries using existing `ingestion/common/retry.py` (delete the duplicate ad-hoc loop in fetcher)

### B2. Rewrite `models/trade/ingest_trade.py`
- Delete `UN_COMTRADE_2023_DATA` fabricated matrix entirely
- Upsert into `bilateral_trade` preserving `data_source='COMTRADE_PLUS_API'`, `is_estimated` from source flags
- Idempotent via existing unique constraint `(reporter, partner, year, flow, commodity)`
- Emit `source_health` record per run

### B3. Fail loudly when features are degraded
**File:** `models/cii/features.py:108`
- Replace silent `except Exception → defaults` with: retry once, then raise (or at minimum set `features_degraded=true` flag persisted in the snapshot and surfaced by the CII API)

**Verify:** `SELECT count(*), count(DISTINCT reporter_country) FROM bilateral_trade;` ≥ 38 reporters × ~200 partners; retrain CII and confirm `trade_concentration` variance > 0 in feature snapshots; compare val R² against documented 0.8574.

---

## Phase C — Model Versioning & ML Correctness · ~2–3 days

### C1. Single source of truth for active model version
- Populate `cii_model_registry` on every promotion (currently 0 rows)
- New helper `models/cii/registry.py::get_active_model_version()` reading DB (fallback: artifacts metadata), raising if absent
- Replace ALL hardcoded `'cii-v20260730_promoted_live'` strings:
  - `models/cii/features.py:60-70`
  - `models/cascade/spike.py:33-35` (remove swallowed-exception stale pin)
  - `api/routes/cii.py` (filter queries by active version)

### C2. Make `/cii/latest` deterministic
**File:** `api/routes/cii.py:49-82`
- `DISTINCT ON (country_code)` must filter `WHERE model_version = :active_version` first — otherwise versions silently mix per-country (confirmed live: 4 versions coexist, promoted_live stops 07-31, v20260803 runs to 08-22)
- Decide retention policy: archive or delete superseded versions' score rows older than N days

### C3. Fix evaluation hygiene in `models/cii/train.py`
- Nested split: inner val fold for XGB-vs-LGBM selection, held-out outer fold for reported metrics (expanding-window time-series CV)
- Report both numbers in `metadata.json`; promotion guardrail reads only the outer-fold metric
- Relabel confidence intervals in `inference.py:111` as approximate (±1.96·RMSE), drop "empirical prediction interval" claim until calibrated

### C4. Contemporaneous leakage guard
**File:** `models/cii/features.py`
- `conflict_partner_exposure`: shift partner CII to t−1 (or t−30) before weighting; keep excluded from `FEATURE_COLUMNS` per ablation decision, but fix it for diagnostic correctness

**Verify:** Retrain end-to-end; registry row exists; `/api/v1/cii/latest` returns single uniform model_version; metrics report outer-fold values.

---

## Phase D — API Layer Hardening · ~1–2 days

### D1. Connection pooling
**File:** `ingestion/common/db.py`
- Introduce module-level `AsyncConnectionPool(min_size=2, max_size=10, open=False, timeout=5)` started in FastAPI lifespan, closed on shutdown
- Keep `open_async_connection()` signature; back it with pool checkout
- Move `WindowsSelectorEventLoopPolicy` out of db.py into api entrypoint

### D2. Uniform error handling
- Add exception handler: psycopg errors → 503 `{detail:"data layer unavailable"}`; JSON decode of snapshots → logged + skipped row, not 500
- Validate settings at startup (fail fast if `DATABASE_URL` missing)
- Health endpoint (`health.py`): wrap DB probe in try/except → return structured `{"status":"unhealthy"}` 503 instead of crash; remove fabricated metric fallbacks (`health.py:111-118`) — return `"unknown"`

### D3. Payload & validation discipline
- `/dashboard/boundaries`: add GZipMiddleware; support `?iso=` filter; consider TopoJSON or splitting response
- Add LIMIT caps + pagination (`limit/offset` params, max limit enforced) to `/trade-routes`, `/commodity-news`, `/cii/registry`, `/cii/latest`
- Regex-validate country codes: `^[A-Z]{3}$` in cascade/aggression/cii routes
- Constrain enum-ish params (`data_source`, `region`, `category`) to allowed sets
- CORS: replace `allow_origins=["*"]` with explicit frontend origin(s) from env; keep `allow_credentials=True` only if actually needed
- Bound `_FEED_CACHE` with TTL eviction (e.g., `cachetools.TLRUCache(maxsize=64, ttu=...)`)

**Verify:** pytest suite for routes (mock pool); load test /boundaries < 300ms compressed; garbage inputs (`country_code="1!%"`) → 422.

---

## Phase E — Pipeline Reliability & Scheduling · ~2 days

### E1. Task hardening
- Dashboard/commodity tasks: add `bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=3, soft_time_limit=600`
- Distributed lock (Redis `SET NX EX`) around each snapshot task to prevent overlapping runs (M2 race)
- Beat: chain sentiment → CII via chord/chain so `country_daily_signals` is complete before feature extraction (`beat_schedule.py:22-29`)
- GDELT latest mode: persist last-processed export URL in `_migration_meta`-style state table; skip unchanged files

### E2. Timezone normalization
- All internal datetimes UTC-aware: fix naive `datetime.strptime` (`fetcher.py:190`), `date.today()` (`cascade/detector.py:71,127`) → `datetime.now(timezone.utc).date()`

### E3. Cascade detector fixes
- Calendar-day rolling windows (`spike.py:82`): reindex to complete date grid before rolling (reuse grid approach from cii/features.py)
- Deduplicate clustered source spikes before contagion credit (min gap of N days between counted spikes)
- Replace hardcoded fallback dates `detector.py:161-162` with config/env

### E4. FIPS 10-4 code mapping
**File:** `ingestion/gdelt/cleaner.py`
- Ship a complete FIPS→ISO3 table (GDELT publishes one; ~250 entries) replacing the 11-entry dict + wrong pycountry alpha_2 fallback
- Backfill note: historical gdelt_events rows with NULL country attribution will need a one-off re-parse job (40M rows — run as throttled background task)

**Verify:** Spot-check counts: Germany/Japan/Spain event volumes should jump after remap; no regression in total event count.

---

## Phase F — Performance & Cost · ~1–2 days

- Cache headline-extraction results per canonical URL in `article_text_cache` (currently refetches same URLs per commodity, ~8,700 HTTP calls/run — news.py:304)
- Batch LLM validations: group candidates per region into fewer Groq/Gemini calls; add circuit breaker (skip provider for N minutes after repeated failures)
- Training prep N+1 (`train.py:79-92`): batch feature extraction per date-range query instead of 365×4 round trips

---

## Phase G — External Data Expansion (post-fix value adds) · backlog

| Priority | Source | Fills | Notes |
|---|---|---|---|
| P0 | UN Comtrade+ API | bilateral_trade | Covered in Phase B |
| P1 | ACLED API | conflict ground truth vs GDELT media signal | Free academic license; geolocated, curated |
| P1 | World Bank Pink Sheet | tracked_commodities (0 rows) | Free monthly CSV |
| P2 | Freightos FBX / Drewry WCI | shipping_rates (0 rows) | Public weekly indices |
| P2 | World Bank WGI API | better fragility labels than interpolated FSI | Free REST |
| P3 | OpenSanctions | sanctions exposure dimension | Free/open |

Each addition follows the established contract: source lineage in `data_source`, quality flags, `source_health` records, caveats in ARCHITECTURE.md.

---

## Execution Order & Dependencies

```
A1 ─┐
A2 ─┼─► (independent, do first — stop bleeding)
A3 ─┤
A4 ─┘
B1 ─► B2 ─► B3          (needs COMTRADE_API_KEY signup)
C1 ─► C2                (registry before route filtering)
C3, C4                  (needs B done to be meaningful — real features)
D1 ─► D2 ─► D3          (pool before error handling tests)
E1..E4                  (any time after A)
F                       (after E stabilizes cadence)
G                       (after B proves the ingestion pattern)
```

## Definition of Done (whole plan)

- [ ] Zero unguarded `DELETE` statements in snapshot paths
- [ ] Sentiment pipeline runs green 7 consecutive days
- [ ] `bilateral_trade` populated from real Comtrade API with source lineage
- [ ] Single active model version resolvable from DB; `/cii/latest` uniform
- [ ] Pooled connections; no endpoint returns raw 500 under DB failure
- [ ] All scheduled tasks retried, locked, and ordered correctly
- [ ] CI: ruff + mypy + pytest green; new tests cover A1/A2/C1/D2 regressions
