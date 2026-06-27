"""Fetch daily weather data from Open-Meteo Historical Weather API.

Outputs:
1) Partitioned daily CSV files:
   data/weather_daily/date=YYYY-MM-DD/weather_daily_YYYY-MM-DD.csv
2) Accumulated master CSV:
   data/weather_daily_master.csv

Example:
    python src/fetch_open_meteo_daily.py --mode yesterday
    python src/fetch_open_meteo_daily.py --start-date 2000-01-01 --end-date 2026-06-26
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

DAILY_VARIABLES = [
    "temperature_2m_mean",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_mean",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "wind_speed_10m_max",
]

COLUMN_RENAME = {
    "temperature_2m_mean": "temp_mean_c",
    "temperature_2m_max": "temp_max_c",
    "temperature_2m_min": "temp_min_c",
    "apparent_temperature_mean": "apparent_temp_mean_c",
    "precipitation_sum": "precipitation_sum_mm",
    "rain_sum": "rain_sum_mm",
    "snowfall_sum": "snowfall_sum_cm",
    "wind_speed_10m_max": "wind_speed_10m_max_kmh",
}


@dataclass(frozen=True)
class City:
    city: str
    country: str
    latitude: float
    longitude: float
    timezone: str


def yesterday_in_timezone(tz_name: str = "Asia/Tokyo") -> date:
    """Return yesterday's date in the target timezone."""
    return datetime.now(ZoneInfo(tz_name)).date() - timedelta(days=1)


def read_cities(path: Path) -> list[City]:
    if not path.exists():
        raise FileNotFoundError(f"City config not found: {path}")

    cities: list[City] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"city", "country", "latitude", "longitude", "timezone"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")

        for row in reader:
            cities.append(
                City(
                    city=row["city"].strip(),
                    country=row["country"].strip(),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    timezone=row["timezone"].strip(),
                )
            )

    if not cities:
        raise ValueError(f"No cities found in {path}")
    return cities


def request_with_retry(params: dict, retries: int = 3, sleep_seconds: int = 3) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(OPEN_METEO_ARCHIVE_URL, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 - keep CLI error readable
            last_error = exc
            if attempt < retries:
                time.sleep(sleep_seconds * attempt)

    raise RuntimeError(f"Open-Meteo request failed after {retries} attempts: {last_error}")


def fetch_city_daily(city: City, start_date: str, end_date: str) -> pd.DataFrame:
    params = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": city.timezone,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    payload = request_with_retry(params)
    daily = payload.get("daily")
    if not daily or "time" not in daily:
        raise ValueError(f"No daily data returned for {city.city}: {payload}")

    df = pd.DataFrame(daily)
    df = df.rename(columns=COLUMN_RENAME)
    df.insert(0, "date", df.pop("time"))
    df.insert(1, "city", city.city)
    df.insert(2, "country", city.country)
    df.insert(3, "latitude", city.latitude)
    df.insert(4, "longitude", city.longitude)
    df.insert(5, "timezone", city.timezone)
    df["source"] = "open-meteo-historical-weather-api"
    df["ingested_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return df


def write_partitioned_daily(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for day, daily_df in df.groupby("date", sort=True):
        partition_dir = out_dir / f"date={day}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        daily_path = partition_dir / f"weather_daily_{day}.csv"
        daily_df.sort_values(["date", "city"]).to_csv(daily_path, index=False, encoding="utf-8")


def update_master(df_new: pd.DataFrame, master_path: Path) -> pd.DataFrame:
    master_path.parent.mkdir(parents=True, exist_ok=True)
    if master_path.exists():
        df_old = pd.read_csv(master_path)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new.copy()

    # Re-running the same date should update the row, not duplicate it.
    df_all = (
        df_all.sort_values(["date", "city", "ingested_at_utc"])
        .drop_duplicates(subset=["date", "city"], keep="last")
        .sort_values(["date", "city"])
    )
    df_all.to_csv(master_path, index=False, encoding="utf-8")
    return df_all


def run_pipeline(cities_path: Path, out_dir: Path, start_date: str, end_date: str) -> pd.DataFrame:
    cities = read_cities(cities_path)
    frames = [fetch_city_daily(city, start_date, end_date) for city in cities]
    df_new = pd.concat(frames, ignore_index=True)

    write_partitioned_daily(df_new, out_dir)
    master_path = out_dir.parent / "weather_daily_master.csv"
    df_master = update_master(df_new, master_path)

    print(f"Fetched rows this run: {len(df_new):,}")
    print(f"Master rows: {len(df_master):,}")
    print(f"Daily partitions: {out_dir}")
    print(f"Master file: {master_path}")
    return df_master


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Japan daily weather data from Open-Meteo.")
    parser.add_argument("--mode", choices=["yesterday", "range"], default="yesterday")
    parser.add_argument("--start-date", help="YYYY-MM-DD. Required for range mode.")
    parser.add_argument("--end-date", help="YYYY-MM-DD. Required for range mode.")
    parser.add_argument("--cities", default="config/cities.csv", help="Path to city config CSV.")
    parser.add_argument("--out", default="data/weather_daily", help="Output directory for daily partitions.")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)

    if args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    elif args.mode == "yesterday":
        day = yesterday_in_timezone("Asia/Tokyo").isoformat()
        start_date = day
        end_date = day
    else:
        raise ValueError("For range mode, provide both --start-date and --end-date")

    if start_date > end_date:
        raise ValueError(f"start_date must be <= end_date, got {start_date} > {end_date}")

    run_pipeline(Path(args.cities), Path(args.out), start_date, end_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
