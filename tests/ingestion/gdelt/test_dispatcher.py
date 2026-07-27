from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from ingestion.gdelt.dispatcher import _event_params, dispatch_events
from ingestion.gdelt.models import CleanGdeltEvent


def make_clean_event(event_id: int = 1001) -> CleanGdeltEvent:
    return CleanGdeltEvent(
        global_event_id=event_id,
        event_date=date(2026, 7, 27),
        event_code="042",
        event_base_code="04",
        event_root_code="04",
        quad_class=1,
        goldstein_scale=Decimal("1.9"),
        num_mentions=10,
        num_sources=3,
        num_articles=4,
        avg_tone=Decimal("-2.25"),
        actor1_country_code="USA",
        actor2_country_code="IND",
        actor1_type="GOV",
        actor2_type="BUS",
        action_geo_lat=Decimal("38.8951"),
        action_geo_long=Decimal("-77.0364"),
        action_geo_country_code="USA",
        source_url="https://example.com/story",
        has_missing_actors=False,
        is_synthetic=False,
    )


def test_event_params_formatting() -> None:
    event = make_clean_event(2002)
    params = _event_params(event)

    assert params[0] == 2002
    assert params[1] == date(2026, 7, 27)
    assert params[11] == "USA"
    assert params[12] == "IND"
    assert params[19] is False


@pytest.mark.asyncio
async def test_dispatch_events_batches_inserts() -> None:
    events = [make_clean_event(i) for i in range(10)]

    mock_cursor = AsyncMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor

    dispatched = await dispatch_events(mock_conn, events, batch_size=4)

    assert dispatched == 10
    # Expected 3 batches for 10 items with batch_size 4 (4 + 4 + 2)
    assert mock_cursor.executemany.call_count == 3
