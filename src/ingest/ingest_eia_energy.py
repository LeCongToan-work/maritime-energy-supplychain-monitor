import os
import time
import logging
from pathlib import Path
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

OUTPUT_PARQUET = Path("data/raw/eia_energy_prices_daily_raw.parquet")

EIA_BASE_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
START_DATE = "2021-01-01"

# Danh sach ma series nang luong tren EIA:
# RBRTE: Gia dau tho Brent (Europe Brent Spot Price FOB - USD/barrel)
# EER_EPD2DXL0_PF4_RGC_DPG: Gia dau Diesel van tai (US Gulf Coast Ultra-Low Sulfur No 2 Diesel - USD/gallon)
ENERGY_SERIES = {
    "brent_crude": "RBRTE",
    "ulsd_diesel": "EER_EPD2DXL0_PF4_RGC_DPG",
}


def fetch_eia_series(api_key: str, series_code: str, start_date: str) -> list:
    params = {
        "api_key": api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": series_code,
        "start": start_date,
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 5000,
    }

    all_rows = []
    while True:
        resp = requests.get(EIA_BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("response", {})
        rows = data.get("data", [])

        if not rows:
            break

        all_rows.extend(rows)
        params["offset"] += len(rows)

        total_records = int(data.get("total", len(all_rows)))
        if len(all_rows) >= total_records:
            break

        time.sleep(0.5)

    return all_rows


def run_ingest_eia():
    api_key = os.getenv("EIA_API_KEY")
    if not api_key:
        raise ValueError("Missing EIA_API_KEY in .env file.")

    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    raw_records = []
    for metric_name, series_code in ENERGY_SERIES.items():
        logger.info(f"Fetching EIA energy series: {metric_name} ({series_code}) from {START_DATE}")
        rows = fetch_eia_series(
            api_key=api_key,
            series_code=series_code,
            start_date=START_DATE,
        )
        logger.info(f"Retrieved {len(rows)} records for {metric_name}")
        raw_records.extend(rows)

    if not raw_records:
        logger.warning("No data returned from EIA API.")
        return

    # Giu nguyen du lieu goc, ep ve string de dam bao an toan kieu du lieu o tang Raw
    df_raw = pd.DataFrame(raw_records).astype(str)
    df_raw["_ingested_at_utc"] = pd.Timestamp.now("UTC").isoformat()

    df_raw.to_parquet(OUTPUT_PARQUET, index=False, compression="snappy")
    logger.info(f"Total saved: {len(df_raw)} raw energy rows to {OUTPUT_PARQUET}")


if __name__ == "__main__":
    run_ingest_eia()