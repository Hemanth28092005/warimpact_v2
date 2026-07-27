"""Database helpers for ingestion modules."""

from __future__ import annotations

import sys
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from psycopg import AsyncConnection

from ingestion.common.config import get_settings

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def open_async_connection() -> AsyncIterator[AsyncConnection]:
    settings = get_settings()
    conn = await AsyncConnection.connect(settings.psycopg_database_url)
    try:
        yield conn
    finally:
        await conn.close()


if __name__ == "__main__":
    print(get_settings().psycopg_database_url)
