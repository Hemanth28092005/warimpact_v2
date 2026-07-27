from ingestion.common.beat_schedule import BEAT_SCHEDULE
from ingestion.gdelt import tasks
from pytest import MonkeyPatch


def test_beat_schedule_registers_latest_ingestion() -> None:
    schedule = BEAT_SCHEDULE["gdelt-run-latest-ingestion"]

    assert schedule["task"] == "ingestion.gdelt.tasks.run_latest_ingestion"


def test_latest_task_delegates_to_worker(monkeypatch: MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run_ingestion_sync(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {"records_processed": 1}

    monkeypatch.setattr(tasks, "run_ingestion_sync", fake_run_ingestion_sync)

    result = tasks.run_latest_ingestion.run()

    assert result == {"records_processed": 1}
    assert calls[0]["mode"] == "latest"
