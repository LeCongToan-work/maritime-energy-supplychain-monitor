import time
import logging
from pathlib import Path
import yaml
import requests
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config/sources_config.yaml")
OUTPUT_PARQUET = Path("data/raw/imf_chokepoint_daily_raw.parquet")

EXPECTED_COLUMNS = [
    "date",
    "year",
    "month",
    "day",
    "portid",
    "portname",
    "n_container",
    "n_dry_bulk",
    "n_general_cargo",
    "n_roro",
    "n_tanker",
    "n_cargo",
    "n_total",
    "capacity_container",
    "capacity_dry_bulk",
    "capacity_general_cargo",
    "capacity_roro",
    "capacity_tanker",
    "capacity_cargo",
    "capacity",
    "ObjectId",
]


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["imf_portwatch"]


def fetch_chokepoint_data(cfg: dict) -> list[dict]:
    base_url = cfg["chokepoint_daily_url"]
    start_date = cfg.get("start_date", "2021-01-01")
    start_year = int(start_date.split("-")[0])
    batch_size = int(cfg.get("batch_size", 1000))
    timeout = int(cfg.get("timeout_seconds", 30))
    max_retries = int(cfg.get("max_retries", 3))

    # ArcGIS REST API gioi han maxRecordCount = 1000 tren server.
    # Phai tang offset theo so ban ghi thuc te nhan duoc (len(features))
    # thay vi so sanh len(features) < batch_size (gay dung som ngay batch dau tien).
    offset = 0
    all_rows = []

    while True:
        params = {
            "where": f"year >= {start_year}",
            "outFields": ",".join(EXPECTED_COLUMNS),
            "returnGeometry": "false",
            "orderByFields": "ObjectId ASC",
            "resultOffset": offset,
            "resultRecordCount": batch_size,
            "f": "json",
        }

        data = None
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.get(base_url, params=params, timeout=timeout)
                resp.raise_for_status()
                payload = resp.json()
                if "error" in payload:
                    raise RuntimeError(f"ArcGIS API error: {payload['error']}")
                data = payload
                break
            except Exception as exc:
                if attempt == max_retries:
                    raise
                wait_sec = 2 ** attempt
                logger.warning(f"Attempt {attempt}/{max_retries} failed ({exc}). Retrying in {wait_sec}s...")
                time.sleep(wait_sec)

        features = data.get("features", [])
        if not features:
            break

        batch_rows = [feat["attributes"] for feat in features if "attributes" in feat]
        all_rows.extend(batch_rows)
        offset += len(batch_rows)

        logger.info(f"Fetched {len(batch_rows)} rows (total so far: {len(all_rows)})")

        # Dung khi khong con cờ exceededTransferLimit VA so dong nhan duoc nho hon 1000 (maxRecordCount cua ArcGIS)
        if not data.get("exceededTransferLimit", False) and len(batch_rows) < 1000:
            break

        time.sleep(0.2)

    return all_rows


def normalize_chokepoint_df(raw_records: list[dict], start_date: str) -> pd.DataFrame:
    df = pd.DataFrame(raw_records)

    # Chuan hoa cot date ve dinh dang YYYY-MM-DD (string) tu year/month/day hoac epoch ms
    if {"year", "month", "day"}.issubset(df.columns):
        df["date"] = pd.to_datetime(df[["year", "month", "day"]]).dt.strftime("%Y-%m-%d")
    elif pd.api.types.is_numeric_dtype(df["date"]):
        df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    else:
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # Loc tu start_date tro di
    df = df[df["date"] >= start_date].copy()

    # Dam bao thu tu cot va kieu du lieu khop Data Dictionary
    int_cols = [
        "year", "month", "day",
        "n_container", "n_dry_bulk", "n_general_cargo", "n_roro",
        "n_tanker", "n_cargo", "n_total",
        "capacity_container", "capacity_dry_bulk", "capacity_general_cargo",
        "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity",
        "ObjectId",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

    str_cols = ["date", "portid", "portname"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].astype(str)

    df = df[EXPECTED_COLUMNS].copy()
    df["_ingested_at_utc"] = pd.Timestamp.now("UTC").isoformat()
    return df


def run_ingest_imf_portwatch():
    cfg = load_config()
    OUTPUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Starting IMF PortWatch Chokepoint ingestion from {cfg['start_date']}...")
    raw_records = fetch_chokepoint_data(cfg)

    if not raw_records:
        logger.warning("No data returned from IMF PortWatch API.")
        return

    df_raw = normalize_chokepoint_df(raw_records, cfg["start_date"])
    df_raw.to_parquet(OUTPUT_PARQUET, index=False, compression="snappy")

    n_ports = df_raw["portid"].nunique()
    logger.info(
        f"Saved {len(df_raw):,} rows across {n_ports} chokepoints to {OUTPUT_PARQUET}"
    )


if __name__ == "__main__":
    run_ingest_imf_portwatch()
