# Global Geopolitical Instability and Trade Impact Platform Architecture

## Project Description

This platform will collect conflict, instability, trade, commodity, and logistics signals to help analysts reason about geopolitical disruption and trade exposure. It will be built as a modular FastAPI backend, PostgreSQL data store, reproducible ingestion and modeling pipelines, and a React/Deck.gl geospatial frontend.

The project emphasizes data honesty, explicit scope, and phase-by-phase verification. Quantitative outputs will distinguish authoritative observations from proxies, estimates, or synthetic development data.

## Phases

### Phase 0: Repository Setup

Phase 0 establishes the repository structure, tooling contracts, documentation baseline, local Postgres configuration, Alembic migration path, and frontend scaffold. It contains no application logic and exists to prove that the development environment can run migrations, tests, Docker, and the Vite application shell.

### Phase 1: GDELT Event Ingestion Foundation

Phase 1 will implement the first conflict/event ingestion pipeline using GDELT 2.0 event data. The work will be split into fetch, parse, clean, dispatch, and worker modules with structured logging, retries, source health tracking, and tests around parsing and cleaning.

### Phase 2: GDELT Text and Sentiment Pipeline

Phase 2 will add GDELT GKG/text processing and RoBERTa-based sentiment analysis. Model output will be documented as a signal rather than ground truth, with clear caveats about source coverage, language bias, and confidence.

### Phase 3: Country Instability Index

Phase 3 will define and calculate a Country Instability Index using documented input features and transparent weighting or trained models. Any proxy labels will be documented in code and architecture notes, including source, update frequency, and known bias.

### Phase 4: Instability API Surface

Phase 4 will expose versioned FastAPI endpoints for countries, event summaries, instability scores, and source health. It will include request validation, structured error responses, and API key protection where endpoints are expensive or write-capable.

### Phase 5: Trade Data Ingestion

Phase 5 will add UN Comtrade, WITS, and World Bank trade data ingestion for the scoped countries and commodities. The pipeline will preserve source metadata, update cadence, and quality flags so derived trade exposure can be audited.

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

Phase 12 will strengthen observability, retry behavior, API security, CI quality gates, and deployment readiness. This phase will also review file sizes, module boundaries, coverage thresholds, and source health reporting across pipelines.

### Phase 13: Deployment and Release Readiness

Phase 13 will prepare Docker-based backend deployment for Railway and frontend deployment for Vercel. It will include production configuration documentation, smoke checks, and a release checklist that separates verified behavior from known limitations.

## Data Quality Log

No data has been ingested in Phase 0.

## Scope Decisions

No countries, commodities, ports, routes, or data sources have been selected beyond the project-level technology choices in Phase 0.
