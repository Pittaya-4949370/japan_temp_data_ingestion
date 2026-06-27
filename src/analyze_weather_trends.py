"""Create simple travel-season and climate trend summary files."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def comfort_score(temp_c: float) -> float:
    """Simple tourist comfort score centered around 22°C."""
    if pd.isna(temp_c):
        return np.nan
    return max(0.0, 100.0 - abs(temp_c - 22.0) * 8.0)


def rain_score(monthly_precip_mm: float) -> float:
    """Lower rain = better travel score. This is intentionally simple and explainable."""
    if pd.isna(monthly_precip_mm):
        return np.nan
    return max(0.0, 100.0 - monthly_precip_mm * 0.6)


def slope_per_decade(years: pd.Series, values: pd.Series) -> float:
    valid = pd.DataFrame({"year": years, "value": values}).dropna()
    if len(valid) < 3:
        return np.nan
    slope_per_year = np.polyfit(valid["year"], valid["value"], 1)[0]
    return float(slope_per_year * 10.0)


def analyze(master_csv: Path, out_dir: Path) -> None:
    if not master_csv.exists():
        raise FileNotFoundError(f"Master CSV not found: {master_csv}")

    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(master_csv)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    # 1) Which month is good for travel?
    monthly = (
        df.groupby(["city", "month"], as_index=False)
        .agg(
            avg_temp_mean_c=("temp_mean_c", "mean"),
            avg_temp_max_c=("temp_max_c", "mean"),
            avg_temp_min_c=("temp_min_c", "mean"),
            avg_monthly_precip_mm=("precipitation_sum_mm", "sum"),
            data_days=("date", "count"),
        )
        .sort_values(["city", "month"])
    )
    # Convert total precipitation across all years into average precipitation per observed month.
    years_per_city_month = df.groupby(["city", "month"])["year"].nunique().reset_index(name="years_observed")
    monthly = monthly.merge(years_per_city_month, on=["city", "month"], how="left")
    monthly["avg_monthly_precip_mm"] = monthly["avg_monthly_precip_mm"] / monthly["years_observed"]
    monthly["temp_comfort_score"] = monthly["avg_temp_mean_c"].apply(comfort_score)
    monthly["dry_weather_score"] = monthly["avg_monthly_precip_mm"].apply(rain_score)
    monthly["travel_score_0_100"] = (
        monthly["temp_comfort_score"] * 0.65 + monthly["dry_weather_score"] * 0.35
    ).round(1)
    monthly = monthly.sort_values(["city", "travel_score_0_100"], ascending=[True, False])
    monthly.to_csv(out_dir / "monthly_travel_summary.csv", index=False, encoding="utf-8")

    # 2) Long-term warming trend: annual average temperature slope per decade.
    annual = df.groupby(["city", "year"], as_index=False).agg(avg_temp_mean_c=("temp_mean_c", "mean"))
    trend_rows = []
    for city, g in annual.groupby("city"):
        trend_rows.append(
            {
                "city": city,
                "start_year": int(g["year"].min()),
                "end_year": int(g["year"].max()),
                "years_observed": int(g["year"].nunique()),
                "temp_trend_c_per_decade": round(slope_per_decade(g["year"], g["avg_temp_mean_c"]), 3),
            }
        )
    pd.DataFrame(trend_rows).to_csv(out_dir / "trend_by_city.csv", index=False, encoding="utf-8")

    # 3) Climate comparison: baseline 2000-2009 vs recent 2016-2025.
    period_df = df.copy()
    period_df["period"] = np.select(
        [
            period_df["year"].between(2000, 2009),
            period_df["year"].between(2016, 2025),
        ],
        ["baseline_2000_2009", "recent_2016_2025"],
        default="other",
    )
    period_df = period_df[period_df["period"] != "other"]
    if not period_df.empty:
        comp = (
            period_df.groupby(["city", "month", "period"], as_index=False)
            .agg(avg_temp_mean_c=("temp_mean_c", "mean"), days=("date", "count"))
            .pivot(index=["city", "month"], columns="period", values="avg_temp_mean_c")
            .reset_index()
        )
        if {"baseline_2000_2009", "recent_2016_2025"}.issubset(comp.columns):
            comp["warming_delta_c"] = comp["recent_2016_2025"] - comp["baseline_2000_2009"]
        comp.to_csv(out_dir / "climate_change_monthly_delta.csv", index=False, encoding="utf-8")

    print(f"Analysis files written to: {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Japan weather data.")
    parser.add_argument("--master", default="data/weather_daily_master.csv")
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    analyze(Path(args.master), Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
