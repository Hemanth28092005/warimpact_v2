-- 001_new_dashboard_tables.sql
-- Phase 6a Dashboard Data Layer Tables Migration

-- 1. tracked_commodities
CREATE TABLE IF NOT EXISTS tracked_commodities (
    commodity_code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL,
    trade_type VARCHAR(16) NOT NULL,
    annual_value_usd NUMERIC(15, 2) NOT NULL,
    source_citation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. chokepoints
CREATE TABLE IF NOT EXISTS chokepoints (
    code VARCHAR(50) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    lat NUMERIC(9, 6) NOT NULL,
    long NUMERIC(9, 6) NOT NULL,
    baseline_mbd NUMERIC(8, 2) NOT NULL,
    source_year INTEGER NOT NULL,
    disruption_score NUMERIC(5, 2) NOT NULL DEFAULT 0.0,
    status VARCHAR(16) NOT NULL DEFAULT 'green',
    related_event_ids JSONB DEFAULT '[]'::jsonb,
    last_disruption_reason TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. world_boundaries
CREATE TABLE IF NOT EXISTS world_boundaries (
    iso_a3 VARCHAR(3) PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    geojson JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 4. regional_headlines
CREATE TABLE IF NOT EXISTS regional_headlines (
    id BIGSERIAL PRIMARY KEY,
    region VARCHAR(64) NOT NULL,
    rank INTEGER NOT NULL,
    headline TEXT NOT NULL,
    gdelt_event_id BIGINT REFERENCES gdelt_events(global_event_id) ON DELETE SET NULL,
    source_url TEXT,
    published_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_regional_headlines_region_rank UNIQUE (region, rank)
);
CREATE INDEX IF NOT EXISTS ix_regional_headlines_region ON regional_headlines(region);

-- 5. government_actions (India Government Policy Actions)
CREATE TABLE IF NOT EXISTS government_actions (
    rank SMALLINT PRIMARY KEY CHECK (rank BETWEEN 1 AND 10),
    headline TEXT NOT NULL,
    action_type VARCHAR(64) NOT NULL DEFAULT 'diplomatic_policy',
    gdelt_event_id BIGINT REFERENCES gdelt_events(global_event_id) ON DELETE SET NULL,
    source_url TEXT,
    published_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. protests
CREATE TABLE IF NOT EXISTS protests (
    id BIGSERIAL PRIMARY KEY,
    city VARCHAR(128) NOT NULL,
    event_date DATE NOT NULL,
    headline TEXT NOT NULL,
    action_geo_lat NUMERIC(9, 6),
    action_geo_long NUMERIC(9, 6),
    gdelt_event_id BIGINT REFERENCES gdelt_events(global_event_id) ON DELETE SET NULL,
    source_url TEXT,
    event_severity NUMERIC(5, 2) NOT NULL DEFAULT 0.0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_protests_city_date_headline UNIQUE (city, event_date, headline)
);
CREATE INDEX IF NOT EXISTS ix_protests_date ON protests(event_date);

-- 7. commodity_news
CREATE TABLE IF NOT EXISTS commodity_news (
    id BIGSERIAL PRIMARY KEY,
    commodity_code VARCHAR(50) NOT NULL REFERENCES tracked_commodities(commodity_code) ON DELETE CASCADE,
    rank INTEGER NOT NULL,
    headline TEXT NOT NULL,
    gdelt_event_id BIGINT REFERENCES gdelt_events(global_event_id) ON DELETE SET NULL,
    source_url TEXT,
    published_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_commodity_news_commodity_rank UNIQUE (commodity_code, rank)
);

-- 8. india_trade_routes
CREATE TABLE IF NOT EXISTS india_trade_routes (
    id BIGSERIAL PRIMARY KEY,
    commodity_code VARCHAR(50) NOT NULL REFERENCES tracked_commodities(commodity_code) ON DELETE CASCADE,
    partner_country VARCHAR(3) NOT NULL,
    primary_chokepoint VARCHAR(50) REFERENCES chokepoints(code) ON DELETE SET NULL,
    origin_lat NUMERIC(9, 6) NOT NULL,
    origin_long NUMERIC(9, 6) NOT NULL,
    dest_lat NUMERIC(9, 6) NOT NULL DEFAULT 18.950000,
    dest_long NUMERIC(9, 6) NOT NULL DEFAULT 72.950000,
    risk_score NUMERIC(5, 2) NOT NULL DEFAULT 0.0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_india_trade_routes_commodity_partner UNIQUE (commodity_code, partner_country)
);

-- 9. shipping_rates
CREATE TABLE IF NOT EXISTS shipping_rates (
    id BIGSERIAL PRIMARY KEY,
    route_id BIGINT REFERENCES india_trade_routes(id) ON DELETE CASCADE,
    rate_usd NUMERIC(10, 2),
    rate_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
