-- Migration 006: Create bilateral_trade table for Phase 5 Trade Exposure Layer

CREATE TABLE IF NOT EXISTS bilateral_trade (
    id SERIAL PRIMARY KEY,
    reporter_country VARCHAR(3) NOT NULL,
    partner_country VARCHAR(3) NOT NULL,
    year INT NOT NULL,
    trade_flow VARCHAR(10) NOT NULL, -- 'export', 'import', 'total'
    trade_value_usd NUMERIC(18,2) NOT NULL,
    commodity_code VARCHAR(10) NOT NULL DEFAULT 'TOTAL',
    data_source VARCHAR(50) NOT NULL,
    is_estimated BOOLEAN NOT NULL DEFAULT FALSE,
    ingested_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT unique_reporter_partner_flow UNIQUE (reporter_country, partner_country, year, trade_flow, commodity_code)
);

CREATE INDEX IF NOT EXISTS idx_bilateral_trade_reporter ON bilateral_trade (reporter_country);
CREATE INDEX IF NOT EXISTS idx_bilateral_trade_partner ON bilateral_trade (partner_country);
