from pathlib import Path


def test_phase0_scaffold_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]

    assert (root / "ARCHITECTURE.md").exists()
    assert (root / "SCOPE.md").exists()
    assert (root / "db" / "alembic.ini").exists()
    assert (root / "frontend" / "package.json").exists()
    assert (root / "ingestion" / "common" / "celery_app.py").exists()
    assert (root / "ingestion" / "common" / "beat_schedule.py").exists()
    assert (root / "scripts" / "bootstrap_venv.ps1").exists()
    assert (root / "scripts" / "bootstrap_venv.sh").exists()


def test_celery_app_uses_env_configured_redis_defaults() -> None:
    from ingestion.common.celery_app import celery_app

    assert celery_app.conf.broker_url == "redis://localhost:6379/0"
    assert celery_app.conf.result_backend == "redis://localhost:6379/1"
    assert celery_app.conf.beat_schedule == {}
