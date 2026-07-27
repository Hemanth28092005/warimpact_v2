"""Database dispatcher for cleaned GDELT events."""

from __future__ import annotations

from collections.abc import Sequence

from psycopg import AsyncConnection

from ingestion.gdelt.models import CleanGdeltEvent

DEFAULT_BATCH_SIZE = 750


async def dispatch_events(
    conn: AsyncConnection,
    events: Sequence[CleanGdeltEvent],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    total = 0
    for start in range(0, len(events), batch_size):
        batch = events[start : start + batch_size]
        if not batch:
            continue
        async with conn.cursor() as cur:
            await cur.executemany(_UPSERT_SQL, [_event_params(event) for event in batch])
        total += len(batch)
    return total


def _event_params(event: CleanGdeltEvent) -> tuple[object, ...]:
    return (
        event.global_event_id,
        event.event_date,
        event.event_code,
        event.event_base_code,
        event.event_root_code,
        event.quad_class,
        event.goldstein_scale,
        event.num_mentions,
        event.num_sources,
        event.num_articles,
        event.avg_tone,
        event.actor1_country_code,
        event.actor2_country_code,
        event.actor1_type,
        event.actor2_type,
        event.action_geo_lat,
        event.action_geo_long,
        event.action_geo_country_code,
        event.source_url,
        event.has_missing_actors,
        event.is_synthetic,
    )


_UPSERT_SQL = """
insert into gdelt_events (
    global_event_id, event_date, event_code, event_base_code, event_root_code,
    quad_class, goldstein_scale, num_mentions, num_sources, num_articles,
    avg_tone, actor1_country_code, actor2_country_code, actor1_type, actor2_type,
    action_geo_lat, action_geo_long, action_geo_country_code, source_url,
    has_missing_actors, is_synthetic
)
values (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
on conflict (global_event_id) do update set
    event_date = excluded.event_date,
    event_code = excluded.event_code,
    event_base_code = excluded.event_base_code,
    event_root_code = excluded.event_root_code,
    quad_class = excluded.quad_class,
    goldstein_scale = excluded.goldstein_scale,
    num_mentions = excluded.num_mentions,
    num_sources = excluded.num_sources,
    num_articles = excluded.num_articles,
    avg_tone = excluded.avg_tone,
    actor1_country_code = excluded.actor1_country_code,
    actor2_country_code = excluded.actor2_country_code,
    actor1_type = excluded.actor1_type,
    actor2_type = excluded.actor2_type,
    action_geo_lat = excluded.action_geo_lat,
    action_geo_long = excluded.action_geo_long,
    action_geo_country_code = excluded.action_geo_country_code,
    source_url = excluded.source_url,
    has_missing_actors = excluded.has_missing_actors,
    is_synthetic = excluded.is_synthetic,
    ingested_at = now()
"""


if __name__ == "__main__":
    print("GDELT dispatcher ready")
