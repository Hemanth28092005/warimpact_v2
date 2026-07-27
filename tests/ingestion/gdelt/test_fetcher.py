from datetime import datetime

from ingestion.gdelt.fetcher import iter_backfill_feed_files, parse_lastupdate


def test_parse_lastupdate_selects_export_csv_zip() -> None:
    feed_file = parse_lastupdate(
        "\n".join(
            [
                "1 x http://example.com/20260727000000.gkg.csv.zip",
                "2 x http://example.com/20260727000000.export.CSV.zip",
            ]
        )
    )

    assert feed_file.url.endswith("20260727000000.export.CSV.zip")
    assert feed_file.timestamp == datetime(2026, 7, 27, 0, 0, 0)


def test_iter_backfill_feed_files_generates_15_minute_urls() -> None:
    files = list(
        iter_backfill_feed_files(
            datetime(2026, 7, 27, 0, 4, 0),
            datetime(2026, 7, 27, 0, 30, 0),
        )
    )

    assert [item.url.rsplit("/", 1)[-1] for item in files] == [
        "20260727000000.export.CSV.zip",
        "20260727001500.export.CSV.zip",
        "20260727003000.export.CSV.zip",
    ]
