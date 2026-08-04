# Global Geopolitical Instability and Trade Impact Platform Architecture

## Project Description

This platform will collect conflict, instability, trade, commodity, and logistics signals to help analysts reason about geopolitical disruption and trade exposure. It will be built as a modular FastAPI backend, PostgreSQL data store, Celery and Redis automation layer, reproducible ingestion and modeling pipelines, and a React/Deck.gl geospatial frontend.

The project emphasizes data honesty, explicit scope, and phase-by-phase verification. Quantitative outputs will distinguish authoritative observations from proxies, estimates, or synthetic development data.

## Phases

### Phase 0: Repository Setup

Phase 0 establishes the repository structure, tooling contracts, documentation baseline, local Postgres and Redis configuration, Alembic migration path, Celery app scaffold, and frontend scaffold. It contains no application logic and exists to prove that the development environment can run migrations, tests, Docker services, the Celery worker shell, and the Vite application shell.

### Phase 1: GDELT Event Ingestion Foundation

Phase 1 will implement the first conflict/event ingestion pipeline using GDELT 2.0 event data. The work will be split into fetch, parse, clean, dispatch, worker, and Celery task modules with structured logging, retries, source health tracking, and tests around parsing and cleaning.

### Phase 2: GDELT Text and Sentiment Pipeline

Phase 2 will add GDELT GKG/text processing and RoBERTa-based sentiment analysis. Model output will be documented as a signal rather than ground truth, with clear caveats about source coverage, language bias, and confidence.

### Phase 3: Country Instability Index

Phase 3 will define and calculate a Country Instability Index using documented input features and transparent weighting or trained models. Any proxy labels will be documented in code and architecture notes, including source, update frequency, and known bias.

### Phase 4: Instability API Surface

Phase 4 will expose versioned FastAPI endpoints for countries, event summaries, instability scores, and source health. It will include request validation, structured error responses, and API key protection where endpoints are expensive or write-capable.

### Phase 5: Trade Data Ingestion

Phase 5 will add UN Comtrade, WITS, and World Bank trade data ingestion for the scoped countries and commodities. The pipeline will preserve source metadata, update cadence, Celery task traceability, and quality flags so derived trade exposure can be audited.

### Phase 6: Trade Exposure Modeling

Phase 6 will calculate country, commodity, and route exposure metrics by combining instability signals with trade volume and value data. Outputs will be framed as risk indicators, not guarantees, and every derived metric will keep source lineage.

### Phase 7: Geospatial Frontend Foundation

Phase 7 will build the first usable React/Deck.gl map experience using typed API clients and MapLibre or Mapbox rendering. The interface will prioritize inspection of countries, events, and source health over marketing-style presentation.

### Phase 8: Network and Route Graph Prototype

Phase 8 will introduce NetworkX-based graph prototypes for trade relationships, chokepoints, and dependency paths. The goal is explainable graph exploration first, with igraph reserved for later profiling-proven performance needs.

### Phase 9: Ports and Logistics Scope

Phase 9 will define major ports quantitatively and add logistics entities that connect trade flows to real-world infrastructure. Source citation and scope rationale will be recorded in SCOPE.md before any port dataset is treated as canonical.

### Phase 10: Scenario Analysis

Phase 10 will add scenario inputs that let analysts adjust instability, route, or commodity assumptions and compare potential exposure changes. UI and API copy will clearly state that scenarios are exploratory what-if analysis, not validated predictions.

### Phase 11: Commodity Signal Modeling

Phase 11 will prototype XGBoost or LightGBM commodity signal models where data supports validation. Forecasting language will be avoided unless held-out evaluation metrics are documented and acceptable for the stated use case.

### Phase 12: Operational Hardening

Phase 12 will strengthen observability, retry behavior, API security, queue monitoring, Celery Beat scheduling, CI quality gates, and deployment readiness. This phase will also review file sizes, module boundaries, coverage thresholds, and source health reporting across pipelines.

### Phase 13: Deployment and Release Readiness

Phase 13 will prepare Docker-based backend deployment for Railway and frontend deployment for Vercel. It will include production configuration documentation, smoke checks, and a release checklist that separates verified behavior from known limitations.

## Data Quality Log

No data has been ingested in Phase 0.

## Scope Decisions

No countries, commodities, ports, routes, or data sources have been selected beyond the project-level technology choices in Phase 0.

## Country Bilateral Aggression Score Component

### Architecture & Framing ("What this is / What this is not")
- **What this is**: A quantitative, bounded $[0.0, 100.0]$ metric measuring bilateral conflict severity and strategic relationship stance between 38 target countries ($C(38,2) = 703$ canonical pairs).
  - **GDELT-derived Scores** (`data_source = 'gdelt_derived'`): Computed over a **trailing 365-day rolling window** (`event_date >= target_date - 365 days`) using GDELT 2.0 event severity ($0.4 \cdot tone\_norm + 0.4 \cdot goldstein\_norm + 0.2 \cdot quad\_class\_signed$) and log-scaled volume importance weights.
  - **External Baseline Scores** (`data_source = 'external_baseline'`): Seeded from Correlates of War (COW) published datasets (Formal Alliances v4.1 through 2012, MID v4.2 through 2010) for pairs with 0 GDELT events in the trailing 365-day window.
- **What this is NOT**:
  - The external baseline is **not a real-time diplomatic intelligence feed**. It reflects static historical alliance and dispute status as of dataset publication (`baseline_data_year` = 2012 for Alliances, 2010 for MIDs) until superseded by real GDELT events (`event_count > 0`).
  - Unrecorded pairs lacking both GDELT events and COW records are stored with `aggression_score = NULL` and logged as explicitly unscored. Zero fabricated, guessed, or default middle values are ever inserted.

## Phase 4: Cascade / Cross-Stream Correlation System

### Architecture & Graph Construction
- **Country Adjacency Graph**: Built on the 38 in-scope countries incorporating two edge types:
  1. **Physical Borders**: Sourced from the **REST Countries API v3.1** (`https://restcountries.com/v3.1/all`) land border dataset.
  2. **Bilateral Event Linkage**: Sourced from `country_aggression_scores.event_count` (trailing 365-day window), adding edges for the top 5 highest event volume pairs per country.
- **Spike Detection**: For each country, identifies spike dates where $\text{cii\_score} > \text{rolling\_mean\_30d} + K \cdot \text{rolling\_std\_30d}$ ($K = 2.0$ default, configurable). Queries are strictly scoped to a single `model_version` to prevent statistical corruption.
- **BFS Contagion Score**: When source country $A$ spikes on day $D$, counts co-spikes in adjacent country $B$ within $[D, D + N]$ days ($N = 7$ default, configurable). $\text{contagion\_score} = \frac{\text{co\_spike\_count}}{\text{source\_spike\_count}}$.

### System Limitations & Analytical Disclaimers (Non-Negotiable)
1. **Correlation $\neq$ Causation**:
   Shared external macro shocks (e.g., a regional or global crisis affecting multiple countries simultaneously) can produce co-occurring CII spikes without direct contagion between the countries.
2. **Statistical Association Measure**:
   `contagion_score` measures empirical temporal co-occurrence of statistical outliers within an $N$-day window. It is NOT a structural, physical, or causal dynamic model.
3. **Signal Confounding & Spurious Correlations**:
   CII is derived from GDELT conflict and sentiment signals. Without cross-referencing secondary streams (e.g., Phase 5 trade exposure, bilateral capital flows, logistics chokepoints), spurious correlations cannot be ruled out.
4. **Fixed-Sigma Spike Threshold Bias**:
   Because spike detection uses an absolute $K \cdot \text{std}$ threshold, it is miscalibrated across countries with different baseline volatility. Stable countries with naturally low CII variance (e.g. ESP, $\text{std} \approx 3.65$) register "spikes" from routine noise ($+3\text{--}10$ point moves) far more often than chronically volatile countries (e.g. YEM, std much higher, operating near the 100.00 score ceiling), where even severe real escalations often fail to exceed a 2-sigma threshold. Empirically: ESP registered 46 spike days vs. YEM's 11, despite YEM undergoing well-documented severe escalation during this period. Consequently, cascade contagion scores for conflict-cluster country pairs (e.g. SYR-YEM, SDN-SSD, ISR-SYR: 0.00--0.25) are systematically LOWER than for stable-country pairs (e.g. DEU-ITA, USA-CAN: 0.48--0.73) — this should NOT be read as evidence that contagion is weaker among conflict-prone countries; it is a detector calibration artifact.

## Phase 5: Lightweight Trade Exposure Layer

### Data Source & Schema
- **Data Source**: Published **UN Comtrade Database 2023** (`https://comtradeplus.un.org`), dataset `UN_COMTRADE_2023`.
- **Publication Lag**: 2023 edition (lagging ~1--2 years relative to present).
- **Scope & Quality**: Ingests total annual bilateral trade (exports + imports) for all 38 reporter countries across **all global trading partners**. Preserves `is_estimated = True` where source figures include UN Comtrade estimates for partially reporting territories.

### Derived Features & Empirical Ablation (`models/cii/features.py`)
1. `trade_concentration` (**ACTIVE IN MODEL**): Herfindahl-Hirschman Index (HHI) computed over the global trading partner set for each reporter country:
   $$\text{HHI} = \sum_{p \in \text{All Partners}} \left( \frac{\text{trade\_value}_p}{\text{total\_global\_trade}} \times 100 \right)^2 \implies \text{trade\_concentration} = \frac{\text{HHI}}{10000.0}$$
2. `conflict_partner_exposure` (**EXCLUDED FROM ACTIVE FEATURE SET**): Trade-weighted sum of in-scope partners' CII scores on the target date:
   $$\text{conflict\_partner\_exposure} = \sum_{p \in \text{In-Scope}} \left( \frac{\text{trade\_value}_p}{\sum_{j \in \text{In-Scope}} \text{trade\_value}_j} \right) \times \text{cii\_score}_p$$

> [!NOTE]
> **Empirical Ablation Finding & Exclude Decision**:
> `conflict_partner_exposure` was fully implemented, fixed for driver type compatibility (`Decimal` parsing), and tested across historical training samples. In isolation, it exhibited strong positive linear correlation with the target FSI label ($r = +0.3449$). However, ablation testing revealed that combining `conflict_partner_exposure` with `trade_concentration` was **net-negative for model generalization** ($R^2 = 0.8195$ with both features vs. $R^2 = \mathbf{0.8303}$ with `trade_concentration` alone). Because partner conflict signal is largely redundant with direct country-level conflict and sentiment features, `conflict_partner_exposure` was excluded from active `FEATURE_COLUMNS` to prevent multicollinearity and over-parameterization while keeping its code path intact for diagnostic research.

### Retraining & Guardrail Promotion Results
- **Active Baseline Model** (`cii-v20260730_promoted_live`): 9 baseline features, $R^2 = 0.6726$, $\text{RMSE} = 14.5597$, $\text{AUC} = 0.6300$.
- **Retrained Promoted Model** (`cii-v20260730`): 10 features (`trade_concentration` active), $R^2 = \mathbf{0.8574}$, $\text{RMSE} = \mathbf{9.6075}$, $\text{AUC} = \mathbf{0.6318}$.
- **Guardrail Outcome**: **PROMOTED** to active live model. Retaining `trade_concentration` alone improved validation $R^2$ to $0.8574$ ($+0.1848$ gain) and reduced RMSE to $9.6075$ (a 34.0% err## Phase 5: Machine Learning Core & Model Metrics Framing

### Model Performance & Versioning
- **Trade Concentration Feature Model (`cii-v20260730`)**: Evaluates trade vulnerability (HHI) and GDELT conflict signals against 366-day FSI benchmarks across 38 nations.
  - **Validation $R^2$**: **85.74%** ($0.8574$, beating baseline $0.8549$).
  - **Validation RMSE**: **9.6075** (34.0% error reduction vs naive baseline).
  - **Classifier ROC-AUC**: **0.6318** (Spike escalation prediction).
- **CII Overall Regressor**: Measures country instability signals; overall baseline regressor $R^2 = 0.68$ across raw historical FSI benchmarks.
- **Empirical Feature Selection Finding**: `conflict_partner_exposure` was tested and found to correlate with FSI in isolation ($R^2 = 0.8195$). However, when combined with `trade_concentration`, validation $R^2$ dropped from $0.8303$ to $0.8195$ due to signal redundancy with existing 30-day GDELT conflict and sentiment intensity features. The feature remains present in `models/cii/features.py` for research evaluation but is excluded from active model promotion (`cii-v20260730`).

## Phase 6a: Dashboard Data Layer & Schema Contracts

### Schema & Foreign Key Decisions
- **`shipping_rates.route_id` Foreign Key**: `shipping_rates` references `india_trade_routes.id` (`BIGINT REFERENCES india_trade_routes(id) ON DELETE CASCADE`). This surrogate key design guarantees database-level foreign key integrity, fast indexed integer joins, and automatic cascade cleanup if a trade route is modified or removed.
- **Full-Globe Boundary Coverage (`world_boundaries`)**: Stores GeoJSON boundaries for **253 total global countries** from Natural Earth to render a visually complete globe in the frontend, with 38 carrying live CII/risk telemetry.
- **7 Spec-Compliant Headline Regions (`regional_headlines`)**: 7 standalone region keys (`united_states`, `india`, `africa`, `asia_pacific`, `middle_east`, `europe`, `latin_america_australia`), ensuring India and the United States each maintain dedicated top-10 headline panels (**70 rows** total).
- **Chokepoint-Null Risk Scoring (`india_trade_routes`)**: When a trade route has `primary_chokepoint IS NULL`, the disruption weight ($0.25$) is explicitly redistributed across CII ($40\%$) and Aggression ($35\%$):
  $$\text{risk\_score} = \frac{0.40}{0.75} \times \text{CII} + \frac{0.35}{0.75} \times \text{Aggression} \approx 0.5333 \times \text{CII} + 0.4667 \times \text{Aggression}$$






