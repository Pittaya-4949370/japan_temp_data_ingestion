"""Airflow DAG for daily Japan weather ingestion from Open-Meteo.

Deploy the whole project folder to Airflow, for example:
/opt/airflow/dags/japan-weather-pipeline/

The DAG writes files to:
/opt/airflow/dags/japan-weather-pipeline/data/weather_daily/
unless JAPAN_WEATHER_OUTPUT_DIR is set.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pendulum
from airflow.decorators import dag, task


PROJECT_ROOT = Path(os.environ.get("JAPAN_WEATHER_PROJECT_ROOT", Path(__file__).resolve().parents[1]))
CITIES_CSV = PROJECT_ROOT / "config" / "cities.csv"
OUTPUT_DIR = Path(os.environ.get("JAPAN_WEATHER_OUTPUT_DIR", PROJECT_ROOT / "data" / "weather_daily"))
MASTER_CSV = OUTPUT_DIR.parent / "weather_daily_master.csv"
ANALYSIS_DIR = Path(os.environ.get("JAPAN_WEATHER_ANALYSIS_DIR", PROJECT_ROOT / "output"))


@dag(
    dag_id="japan_weather_openmeteo_daily",
    description="Fetch daily weather data for Japanese tourist cities from Open-Meteo.",
    schedule="15 8 * * *",  # 08:15 Asia/Tokyo every day
    start_date=pendulum.datetime(2026, 1, 1, tz="Asia/Tokyo"),
    catchup=False,
    tags=["weather", "open-meteo", "japan"],
)
def japan_weather_openmeteo_daily():
    @task
    def fetch_yesterday_weather() -> str:
        script = PROJECT_ROOT / "src" / "fetch_open_meteo_daily.py"
        cmd = [
            sys.executable,
            str(script),
            "--mode",
            "yesterday",
            "--cities",
            str(CITIES_CSV),
            "--out",
            str(OUTPUT_DIR),
        ]
        subprocess.run(cmd, check=True)
        return str(MASTER_CSV)

    @task
    def create_analysis(master_csv: str) -> str:
        script = PROJECT_ROOT / "src" / "analyze_weather_trends.py"
        cmd = [
            sys.executable,
            str(script),
            "--master",
            master_csv,
            "--out",
            str(ANALYSIS_DIR),
        ]
        subprocess.run(cmd, check=True)
        return str(ANALYSIS_DIR)

    create_analysis(fetch_yesterday_weather())


japan_weather_openmeteo_daily()
