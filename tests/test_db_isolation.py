"""Unit tests verifying test database isolation guards.

Ensures that:
- Production database URLs ('war_impact', default postgres, template databases) are strictly rejected.
- Test database URLs ('war_impact_test', 'ci_test_db') are accepted.
- Validation is purely string/metadata based and executes before any socket connection.
"""

import pytest
from tests.conftest import validate_test_db_target


def test_production_database_url_is_strictly_rejected():
    """Verify that targeting production 'war_impact' raises RuntimeError before connecting."""
    prod_urls = [
        "postgresql://war_impact:war_impact_password@localhost:5432/war_impact",
        "postgresql+psycopg://war_impact:war_impact_password@localhost:5432/war_impact",
        "postgresql://user:pass@prod-db.internal:5432/war_impact",
        "postgresql://localhost:5432/war_impact",
    ]

    for url in prod_urls:
        with pytest.raises(RuntimeError) as exc_info:
            validate_test_db_target(url)
        assert "PROD DATABASE ACCESS BLOCKED" in str(exc_info.value)
        assert "war_impact" in str(exc_info.value)


def test_unsafe_system_databases_are_rejected():
    """Verify that system databases (postgres, template1, empty) are rejected."""
    unsafe_urls = [
        "postgresql://localhost:5432/postgres",
        "postgresql://localhost:5432/template1",
        "postgresql://localhost:5432/",
        "",
        None,
    ]

    for url in unsafe_urls:
        with pytest.raises(RuntimeError):
            validate_test_db_target(url)


def test_non_test_named_database_is_rejected():
    """Verify that any database name lacking 'test' is rejected."""
    non_test_urls = [
        "postgresql://localhost:5432/analytics",
        "postgresql://localhost:5432/staging_war",
        "postgresql://localhost:5432/production_replica",
    ]

    for url in non_test_urls:
        with pytest.raises(RuntimeError) as exc_info:
            validate_test_db_target(url)
        assert "ISOLATION GUARD REJECTION" in str(exc_info.value)


def test_valid_isolated_test_database_urls_are_accepted():
    """Verify that explicitly named test databases pass validation."""
    valid_test_urls = [
        "postgresql://war_impact:war_impact_password@localhost:5432/war_impact_test",
        "postgresql+psycopg://war_impact:war_impact_password@localhost:5432/war_impact_test",
        "postgresql://user:pass@localhost:5432/my_app_test",
        "postgresql://localhost:5432/test_ci_db",
    ]

    for url in valid_test_urls:
        # Should not raise
        validate_test_db_target(url)


def test_pytest_configure_rejects_production_env(monkeypatch):
    """Verify that pytest_configure rejects incoming production DATABASE_URL before changing it."""
    from tests.conftest import pytest_configure

    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/war_impact")
    with pytest.raises(RuntimeError) as exc_info:
        pytest_configure(None)
    assert "PROD DATABASE ACCESS BLOCKED" in str(exc_info.value)
