-- Migration 005: Create cascade_scores table for Phase 4 Cascade / Cross-Stream Correlation

CREATE TABLE IF NOT EXISTS cascade_scores (
    id SERIAL PRIMARY KEY,
    source_country VARCHAR(3) NOT NULL,
    target_country VARCHAR(3) NOT NULL,
    contagion_score DOUBLE PRECISION NOT NULL,
    co_spike_count INT NOT NULL,
    source_spike_count INT NOT NULL,
    window_days INT NOT NULL,
    analysis_start_date DATE NOT NULL,
    analysis_end_date DATE NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT unique_cascade_pair_window UNIQUE (source_country, target_country, window_days)
);

CREATE INDEX IF NOT EXISTS idx_cascade_scores_source ON cascade_scores (source_country);
CREATE INDEX IF NOT EXISTS idx_cascade_scores_target ON cascade_scores (target_country);
