from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from ingestion.gdelt.worker import build_arg_parser, run_ingestion


def test_build_arg_parser() -> None:
    parser = build_arg_parser()

    latest_args = parser.parse_args(["--mode", "latest"])
    assert latest_args.mode == "latest"

    backfill_args = parser.parse_args([
        "--mode", "backfill",
        "--start", "2026-07-01T00:00:00",
        "--end", "2026-07-01T01:00:00"
    ])
    assert backfill_args.mode == "backfill"
    assert backfill_args.start == "2026-07-01T00:00:00"


@pytest.mark.asyncio
async def test_run_ingestion_backfill_validation() -> None:
    with patch("ingestion.gdelt.worker.open_async_connection") as mock_open:
        mock_conn = AsyncMock()
        mock_open.return_value.__aenter__.return_value = mock_conn

        with pytest.raises(ValueError, match="backfill mode requires start and end"):
            await run_ingestion(mode="backfill", run_id=uuid4())
