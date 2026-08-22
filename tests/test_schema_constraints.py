"""Unit and integration tests verifying schema CHECK constraints and bounds on isolated test DB."""

import pytest
import psycopg
from psycopg.errors import CheckViolation
import uuid


def test_chokepoints_status_and_score_constraints(test_db_url: str):
    """Verify check constraints on chokepoints table."""
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            # Valid insert
            cur.execute(
                """
                INSERT INTO chokepoints (code, name, lat, long, baseline_mbd, source_year, status, disruption_score)
                VALUES ('CHK_VAL_1', 'Valid Chokepoint', 12.5, 45.0, 10.0, 2024, 'green', 15.0);
                """
            )

            # Invalid status should fail check constraint
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO chokepoints (code, name, lat, long, baseline_mbd, source_year, status, disruption_score)
                    VALUES ('CHK_INVAL_1', 'Invalid Status', 12.5, 45.0, 10.0, 2024, 'orange', 15.0);
                    """
                )
            conn.rollback()

            # Invalid disruption_score (> 100) should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO chokepoints (code, name, lat, long, baseline_mbd, source_year, status, disruption_score)
                    VALUES ('CHK_INVAL_2', 'Invalid Score High', 12.5, 45.0, 10.0, 2024, 'green', 150.0);
                    """
                )
            conn.rollback()

            # Invalid disruption_score (< 0) should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO chokepoints (code, name, lat, long, baseline_mbd, source_year, status, disruption_score)
                    VALUES ('CHK_INVAL_3', 'Invalid Score Low', 12.5, 45.0, 10.0, 2024, 'green', -10.0);
                    """
                )
            conn.rollback()


def test_government_actions_action_type_and_rank_constraints(test_db_url: str):
    """Verify check constraints on government_actions table."""
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            # Invalid action_type should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO government_actions (rank, headline, action_type, published_at)
                    VALUES (1, 'Test Action', 'invalid_action_type', NOW());
                    """
                )
            conn.rollback()

            # Invalid rank (< 1 or > 10) should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO government_actions (rank, headline, action_type, published_at)
                    VALUES (15, 'Test Action', 'diplomatic', NOW());
                    """
                )
            conn.rollback()


def test_protests_location_level_and_severity_constraints(test_db_url: str):
    """Verify check constraints on protests table."""
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            # Invalid location_level should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO protests (location_name, location_level, country_code, event_date, headline, event_severity)
                    VALUES ('Test Place', 'planetary_level', 'IND', CURRENT_DATE, 'Test Headline', 50.0);
                    """
                )
            conn.rollback()

            # Invalid event_severity (> 100) should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO protests (location_name, location_level, country_code, event_date, headline, event_severity)
                    VALUES ('Test Place', 'city', 'IND', CURRENT_DATE, 'Test Headline', 150.0);
                    """
                )
            conn.rollback()

            # Invalid event_severity (< 0) should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO protests (location_name, location_level, country_code, event_date, headline, event_severity)
                    VALUES ('Test Place', 'city', 'IND', CURRENT_DATE, 'Test Headline', -10.0);
                    """
                )
            conn.rollback()


def test_cascade_scores_and_runs_constraints(test_db_url: str):
    """Verify check constraints on cascade_scores and cascade_runs tables."""
    with psycopg.connect(test_db_url) as conn:
        with conn.cursor() as cur:
            # Invalid calculation_status on cascade_runs should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO cascade_runs (run_id, calculation_status)
                    VALUES (%s, 'partially_successful');
                    """,
                    (uuid.uuid4(),),
                )
            conn.rollback()

            # Invalid contagion_score (> 1.0 or < 0.0) on cascade_scores should fail
            with pytest.raises(CheckViolation):
                cur.execute(
                    """
                    INSERT INTO cascade_scores (source_country, target_country, contagion_score, co_spike_count, source_spike_count, window_days, analysis_start_date, analysis_end_date)
                    VALUES ('USA', 'ISR', 1.5, 5, 10, 7, CURRENT_DATE - 7, CURRENT_DATE);
                    """
                )
            conn.rollback()
