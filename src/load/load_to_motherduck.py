"""
load_to_motherduck.py
---------------------
Day cac file Parquet cua ca 3 tang Medallion (Bronze `raw`, Silver `silver`, Gold `gold`)
len MotherDuck Cloud (`maritime_dwh`).

  - Tao database `maritime_dwh` neu chua ton tai.
  - Tao cac schema `raw`, `silver`, `gold` va nap moi file Parquet thanh 1 bang
    (CREATE OR REPLACE -> chay lai idempotent, khong bi nhan doi du lieu).
  - Doi chieu so dong local vs cloud sau khi nap.

Yeu cau: bien moi truong MOTHERDUCK_TOKEN trong file .env
Chay:    venv\\Scripts\\python.exe -m src.load.load_to_motherduck
"""

import os
import sys
import logging
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DATA_GOLD_DIR = PROJECT_ROOT / "data" / "gold"

DATABASE_NAME = "maritime_dwh"

# (schema, table_name) -> file Parquet local
TABLES = {
    # Tang Bronze (Raw)
    ("raw", "eia_energy_prices_daily"): DATA_RAW_DIR / "eia_energy_prices_daily_raw.parquet",
    ("raw", "imf_chokepoint_daily"): DATA_RAW_DIR / "imf_chokepoint_daily_raw.parquet",
    # Tang Silver (Processed & Cleaned)
    ("silver", "stg_eia_energy_prices"): DATA_PROCESSED_DIR / "eia_energy_prices_staging.parquet",
    ("silver", "int_energy_prices_daily_filled"): DATA_PROCESSED_DIR / "eia_energy_prices_daily_filled.parquet",
    ("silver", "stg_imf_chokepoint_daily"): DATA_PROCESSED_DIR / "imf_chokepoint_daily_processed.parquet",
    ("silver", "int_maritime_energy_daily_joined"): DATA_PROCESSED_DIR / "maritime_energy_daily_joined.parquet",
    # Tang Gold (Dimensional Models & BI Analytics Marts)
    ("gold", "dim_chokepoints"): DATA_GOLD_DIR / "dim_chokepoints.parquet",
    ("gold", "dim_geopolitical_events"): DATA_GOLD_DIR / "dim_geopolitical_events.parquet",
    ("gold", "fct_energy_prices_daily"): DATA_GOLD_DIR / "fct_energy_prices_daily.parquet",
    ("gold", "fct_chokepoint_transit_daily"): DATA_GOLD_DIR / "fct_chokepoint_transit_daily.parquet",
    ("gold", "mart_chokepoint_energy_regime_daily"): DATA_GOLD_DIR / "mart_chokepoint_energy_regime_daily.parquet",
    ("gold", "mart_red_sea_cape_rerouting_daily"): DATA_GOLD_DIR / "mart_red_sea_cape_rerouting_daily.parquet",
}

# Goi Free cho 10 GB storage. Chan o 1 GB de khong bao gio cham nguong tinh phi.
MAX_UPLOAD_BYTES = 1 * 1024 ** 3


def check_local_files() -> None:
    missing = [str(p) for p in TABLES.values() if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Thieu file Parquet, hay chay ingest truoc: {missing}")

    total = sum(p.stat().st_size for p in TABLES.values())
    logger.info(f"Tong dung luong Parquet local: {total / 1024 ** 2:.2f} MB")
    if total > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            f"Du lieu {total / 1024 ** 3:.2f} GB vuot nguong an toan {MAX_UPLOAD_BYTES / 1024 ** 3:.0f} GB "
            "cua goi Free. Dung lai de tranh phat sinh phi."
        )


def connect_motherduck() -> duckdb.DuckDBPyConnection:
    token = os.getenv("MOTHERDUCK_TOKEN")
    if not token:
        raise ValueError("Thieu MOTHERDUCK_TOKEN trong file .env")

    # DuckDB tu doc MOTHERDUCK_TOKEN tu bien moi truong khi ket noi chuoi "md:"
    os.environ["motherduck_token"] = token
    con = duckdb.connect("md:")
    con.execute(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}")
    con.execute(f"USE {DATABASE_NAME}")
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute("CREATE SCHEMA IF NOT EXISTS gold")
    return con


def load_table(con: duckdb.DuckDBPyConnection, schema: str, table: str, parquet_path: Path) -> None:
    full_name = f"{DATABASE_NAME}.{schema}.{table}"
    local_rows = duckdb.sql(f"SELECT COUNT(*) FROM read_parquet('{parquet_path.as_posix()}')").fetchone()[0]

    logger.info(f"Dang nap {parquet_path.name} ({local_rows:,} dong) -> {full_name}")
    # read_parquet doc file tren may local, ket qua duoc ghi len cloud
    con.execute(
        f"CREATE OR REPLACE TABLE {full_name} AS "
        f"SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
    )

    cloud_rows = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
    if cloud_rows != local_rows:
        raise RuntimeError(f"{full_name}: local {local_rows:,} dong nhung cloud chi co {cloud_rows:,} dong")
    logger.info(f"OK {full_name}: {cloud_rows:,} dong (khop voi local)")


def run_load_motherduck() -> None:
    check_local_files()
    con = connect_motherduck()
    try:
        for (schema, table), path in TABLES.items():
            load_table(con, schema, table, path)

        tables = con.execute(
            "SELECT schema_name, table_name, estimated_size, column_count "
            "FROM duckdb_tables() WHERE database_name = ? ORDER BY schema_name, table_name",
            [DATABASE_NAME],
        ).fetchall()
        logger.info(f"Cac bang hien co trong {DATABASE_NAME}:")
        for schema, name, rows, cols in tables:
            logger.info(f"  {schema}.{name}: ~{rows:,} dong x {cols} cot")
    finally:
        con.close()


if __name__ == "__main__":
    try:
        run_load_motherduck()
    except Exception as exc:
        logger.error(str(exc))
        sys.exit(1)
