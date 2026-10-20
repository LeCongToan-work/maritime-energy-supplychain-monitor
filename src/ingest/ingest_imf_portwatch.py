import os
import time
import logging
from pathlib import Path
import yaml
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/sources_config.yaml")
OUTPUT_PARQUET = Path("data/raw/eia_energy_prices_daily_raw.parquet")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["eia_energy"]


def fetch_eia_series(api_key: str, base_url: str, series_code: str, start_date: str) -> list:
    params = {
        "api_key": api_key,
        "frequency": "daily",
        "data[0]": "value",
        "facets[series][]": series_code,
        "start": start_date,
        "offset": 0,
        "length": 5000,
    }

    all_rows = []
    while True:
        resp = requests.get(base_url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json().get("response", {})
        rows = data.get("data", [])
        if not rows:
            break
        all_rows.extend(rows)
        if len(all_rows) >= int(data.get("total", 0)):
            break
        params["offset"] += params["length"]
        time.sleep(0.5)

    return all_rows


def run_ingest_eia():
    api_key = os.getenv("EIA_API_KEY")
    if not api_key:
        raise ValueError("Missing EIA_API_KEY in environment variables.")

    cfg = load_config()
    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    raw_records = []
    for metric_name, series_code in cfg["series"].items():
        logger.info(f"Fetching raw EIA series: {metric_name} ({series_code}) from {cfg['start_date']}")
        rows = fetch_eia_series(
            api_key=api_key,
            base_url=cfg["base_url"],
            series_code=series_code,
            start_date=cfg["start_date"],
        )
        raw_records.extend(rows)

    if not raw_records:
        logger.warning("No data returned from EIA API.")
        return

    # Giu nguyen du lieu goc dang string/object de tranh loi kieu du lieu khi luu Parquet
    df_raw = pd.DataFrame(raw_records).astype(str)
    df_raw["_ingested_at_utc"] = pd.Timestamp.utcnow().isoformat()

    df_raw.to_parquet(OUTPUT_PARQUET, index=False, compression="snappy")
    logger.info(f"Saved {len(df_raw)} raw rows to {OUTPUT_PARQUET}")


if __name__ == "__main__":
    run_ingest_eia()