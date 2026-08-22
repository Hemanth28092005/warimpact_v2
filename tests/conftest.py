"""Global Pytest Configuration and Hard Database Isolation Guards.

STRICT POLICY:
- Tests, pytest fixtures, and test commands MUST NEVER connect to the production database.
- Any attempt to resolve or connect to a database named 'war_impact' or containing production
  credentials unconditionally raises RuntimeError before any socket or DB connection is opened.
- All integration and unit tests run exclusively against 'war_impact_test' or isolated mocks.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse
from typing import AsyncIterator, Iterator
import pytest
import psycopg
from psycopg import AsyncConnection, Connection

# Default test database URL
TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://war_impact:war_impact_password@localhost:5432/war_impact_test"
)


def validate_test_db_target(db_url: str | None) -> None:
    """Validate that the given DB connection URL is strictly isolated for testing.

    Raises:
        RuntimeError: If db_url targets the production database or lacks a dedicated test name.
    """
    if not db_url:
        raise RuntimeError("No database URL provided for validation.")

    # Normalize protocol for urlparse
    norm_url = db_url.replace("postgresql+psycopg://", "postgresql://")
    parsed = urlparse(norm_url)
    dbname = parsed.path.lstrip("/")

    # Check for production database name or unsafe targets
    if dbname == "war_impact":
        raise RuntimeError(
            f"PROD DATABASE ACCESS BLOCKED: Refusing to run tests against production database '{dbname}'! "
            f"Tests must target 'war_impact_test' or a dedicated test database."
        )

    if not dbname or dbname in {"postgres", "template1", "template0"}:
        raise RuntimeError(
            f"UNSAFE DATABASE TARGET: Database name '{dbname}' is not a valid test database."
        )

    if not ("test" in dbname.lower() or dbname.endswith("_test")):
        raise RuntimeError(
            f"ISOLATION GUARD REJECTION: Database '{dbname}' does not include 'test' in its name. "
            f"Target database must be explicitly named for testing (e.g., 'war_impact_test')."
        )


def pytest_configure(config):
    """Pytest session hook: enforce test database target in environment and settings."""
    # Check any incoming DATABASE_URL in the host environment FIRST
    incoming_db_url = os.environ.get("DATABASE_URL")
    if incoming_db_url:
        validate_test_db_target(incoming_db_url)

    incoming_test_url = os.environ.get("TEST_DATABASE_URL")
    if incoming_test_url:
        validate_test_db_target(incoming_test_url)

    # Set explicit isolated test URL
    os.environ["DATABASE_URL"] = TEST_DB_URL
    os.environ["TEST_DATABASE_URL"] = TEST_DB_URL

    # Validate active test target
    validate_test_db_target(TEST_DB_URL)


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Return the verified isolated test database URL."""
    validate_test_db_target(TEST_DB_URL)
    return TEST_DB_URL


@pytest.fixture
def test_sync_conn(test_db_url: str) -> Iterator[Connection]:
    """Provide a synchronous connection to the isolated test database."""
    validate_test_db_target(test_db_url)
    with psycopg.connect(test_db_url) as conn:
        yield conn


import pytest_asyncio

@pytest_asyncio.fixture
async def test_async_conn(test_db_url: str) -> AsyncIterator[AsyncConnection]:
    """Provide an asynchronous connection to the isolated test database."""
    validate_test_db_target(test_db_url)
    conn = await AsyncConnection.connect(test_db_url)
    try:
        yield conn
    finally:
        await conn.close()
