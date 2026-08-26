"""Environment-backed configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    gdelt_lastupdate_url: str
    gdelt_latest_interval_minutes: int
    celery_broker_url: str
    celery_result_backend: str
    log_level: str
    acled_email: str | None = None
    acled_access_key: str | None = None
    eia_api_key: str | None = None
    datagovin_api_key: str | None = None

    @property
    def psycopg_database_url(self) -> str:
        return self.database_url.replace("postgresql+psycopg://", "postgresql://")


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set in the environment or .env file")

    return Settings(
        database_url=database_url,
        gdelt_lastupdate_url=os.getenv(
            "GDELT_LASTUPDATE_URL",
            "https://data.gdeltproject.org/gdeltv2/lastupdate.txt",
        ),
        gdelt_latest_interval_minutes=int(os.getenv("GDELT_LATEST_INTERVAL_MINUTES", "15")),
        celery_broker_url=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
        celery_result_backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        acled_email=os.getenv("ACLED_EMAIL"),
        acled_access_key=os.getenv("ACLED_ACCESS_KEY"),
        eia_api_key=os.getenv("EIA_API_KEY"),
        datagovin_api_key=os.getenv("DATAGOVIN_API_KEY"),
    )


if __name__ == "__main__":
    print(get_settings())
