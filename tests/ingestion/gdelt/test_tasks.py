from ingestion.common.beat_schedule import BEAT_SCHEDULE
from ingestion.gdelt import tasks
from pytest import MonkeyPatch


def test_beat_schedule_registers_latest_ingestion() -> None:
    schedule = BEAT_SCHEDULE["gdelt-run-latest-ingestion"]
    sentiment_schedule = BEAT_SCHEDULE["models-run-daily-sentiment-pipeline"]

    assert schedule["task"] == "ingestion.gdelt.tasks.run_latest_ingestion"
    assert sentiment_schedule["task"] == "models.sentiment.tasks.run_daily_sentiment_pipeline"


def test_latest_task_delegates_to_worker(monkeypatch: MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_ingestion_sync(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"records_processed": 1}

    monkeypatch.setattr(tasks, "run_ingestion_sync", fake_run_ingestion_sync)

    result = tasks.run_latest_ingestion.run()

    assert result == {"records_processed": 1}
    assert calls[0]["mode"] == "latest"
