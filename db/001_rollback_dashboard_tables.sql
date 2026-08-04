-- 001_rollback_dashboard_tables.sql
-- Rollback Script for Phase 6a Dashboard Data Layer Tables

DROP TABLE IF EXISTS shipping_rates CASCADE;
DROP TABLE IF EXISTS india_trade_routes CASCADE;
DROP TABLE IF EXISTS commodity_news CASCADE;
DROP TABLE IF EXISTS protests CASCADE;
DROP TABLE IF EXISTS government_actions CASCADE;
DROP TABLE IF EXISTS regional_headlines CASCADE;
DROP TABLE IF EXISTS world_boundaries CASCADE;
DROP TABLE IF EXISTS chokepoints CASCADE;
DROP TABLE IF EXISTS tracked_commodities CASCADE;
