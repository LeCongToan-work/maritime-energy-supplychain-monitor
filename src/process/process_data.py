"""
process_data.py
---------------
Thuc thi xu ly du lieu tu tang Bronze (data/raw/*.parquet) sang tang Processed / Silver (data/processed/*.parquet)
va cap nhat vao DuckDB Warehouse (data/maritime_dwh.duckdb).

Ap dung 3 phuong an da thong nhat:
  - Van de 1 (Phuong an 1A): Dien khuyet area_name tu duoarea (ZEU -> Europe, RGC -> U.S. Gulf Coast),
                             giu nguyen file raw o tang Bronze.
  - Van de 2 (Phuong an 2A): Dong bo lich giao dich bang Causal Forward-Fill (LOCF) tren Calendar Spine
                             365 ngay/nam (khong gay data leakage).
  - Van de 3 (Phuong an 3A): Chuan hoa trong tai capacity_cargo va capacity bang tong cac cot thanh phan,
                             giu lai cot goc (*_raw) va cot chenh lech lam tron (*_rounding_diff).

Dau ra tai thu muc data/processed/:
  1. eia_energy_prices_staging.parquet       (2,899 dong - da xu ly 1A & ep kieu)
  2. eia_energy_prices_daily_filled.parquet  (4,234 dong - da xu ly 1A + 2A Causal Forward-Fill)
  3. imf_chokepoint_daily_processed.parquet  (59,276 dong - da xu ly 3A & ep kieu)
  4. maritime_energy_daily_joined.parquet    (59,276 dong - bang tich hop Chokepoint + Gia Brent & Diesel)

Chay:
  venv\\Scripts\\python.exe -m src.process.process_data
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import duckdb

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DUCKDB_PATH = PROJECT_ROOT / "data" / "maritime_dwh.duckdb"

RAW_EIA_PARQUET = DATA_RAW_DIR / "eia_energy_prices_daily_raw.parquet"
RAW_IMF_PARQUET = DATA_RAW_DIR / "imf_chokepoint_daily_raw.parquet"

OUT_EIA_STAGING = DATA_PROCESSED_DIR / "eia_energy_prices_staging.parquet"
OUT_EIA_FILLED = DATA_PROCESSED_DIR / "eia_energy_prices_daily_filled.parquet"
OUT_IMF_PROCESSED = DATA_PROCESSED_DIR / "imf_chokepoint_daily_processed.parquet"
OUT_JOINED = DATA_PROCESSED_DIR / "maritime_energy_daily_joined.parquet"


def build_processed_layer() -> None:
    if not RAW_EIA_PARQUET.exists():
        raise FileNotFoundError(f"Khong tim thay file raw EIA: {RAW_EIA_PARQUET}")
    if not RAW_IMF_PARQUET.exists():
        raise FileNotFoundError(f"Khong tim thay file raw IMF: {RAW_IMF_PARQUET}")

    DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DUCKDB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS silver;")

        # -------------------------------------------------------------------
        # 1. Phuong an 1A: Staging EIA Energy Prices (Fill area_name tu duoarea)
        # -------------------------------------------------------------------
        logger.info("Dang xu ly [1/4] Phuong an 1A: EIA Energy Staging (map duoarea -> area_name)...")
        con.execute(f"""
            CREATE OR REPLACE TABLE silver.stg_eia_energy_prices AS
            WITH source AS (
                SELECT * FROM read_parquet('{RAW_EIA_PARQUET.as_posix()}')
            ),
            typed AS (
                SELECT
                    TRY_CAST(period AS DATE)                    AS period_date,
                    duoarea,
                    "area-name"                                 AS area_name_raw,
                    CASE duoarea
                        WHEN 'ZEU' THEN 'Europe'
                        WHEN 'RGC' THEN 'U.S. Gulf Coast'
                        ELSE NULLIF("area-name", 'NA')
                    END                                         AS area_name,
                    product,
                    "product-name"                              AS product_name,
                    process,
                    "process-name"                              AS process_name,
                    series,
                    "series-description"                        AS series_description,
                    TRY_CAST(value AS DOUBLE)                   AS price_value,
                    units,
                    TRY_CAST(_ingested_at_utc AS TIMESTAMPTZ)   AS ingested_at_utc
                FROM source
            )
            SELECT * FROM typed
            ORDER BY series, period_date;
        """)
        con.execute(f"""
            COPY silver.stg_eia_energy_prices
            TO '{OUT_EIA_STAGING.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 2. Phuong an 3A: Staging IMF PortWatch Chokepoint (Chuan hoa capacity)
        # -------------------------------------------------------------------
        logger.info("Dang xu ly [2/4] Phuong an 3A: IMF Chokepoint Processed (tinh lai capacity)...")
        con.execute(f"""
            CREATE OR REPLACE TABLE silver.stg_imf_chokepoint_daily AS
            WITH source AS (
                SELECT * FROM read_parquet('{RAW_IMF_PARQUET.as_posix()}')
            ),
            typed AS (
                SELECT
                    TRY_CAST(date AS DATE)                      AS observation_date,
                    year,
                    month,
                    day,
                    portid,
                    portname,
                    n_container,
                    n_dry_bulk,
                    n_general_cargo,
                    n_roro,
                    n_tanker,
                    n_cargo,
                    n_total,
                    capacity_container,
                    capacity_dry_bulk,
                    capacity_general_cargo,
                    capacity_roro,
                    capacity_tanker,
                    capacity_cargo                              AS capacity_cargo_raw,
                    capacity                                    AS capacity_raw,
                    (capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro)
                                                                AS capacity_cargo,
                    (capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro + capacity_tanker)
                                                                AS capacity,
                    ABS(capacity_cargo - (capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro))
                                                                AS capacity_cargo_rounding_diff,
                    ABS(capacity - (capacity_cargo + capacity_tanker))
                                                                AS capacity_rounding_diff,
                    ObjectId                                    AS object_id,
                    TRY_CAST(_ingested_at_utc AS TIMESTAMPTZ)   AS ingested_at_utc
                FROM source
            )
            SELECT * FROM typed
            ORDER BY portid, observation_date;
        """)
        con.execute(f"""
            COPY silver.stg_imf_chokepoint_daily
            TO '{OUT_IMF_PROCESSED.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 3. Phuong an 2A: Causal Forward-Fill (LOCF) tren Calendar Spine
        #    Trace back phien giao dich cuoi cung cua nam 2020 (2020-12-31) tu EIA API v2:
        #      - RBRTE (Brent): 51.22 $/BBL
        #      - EER_EPD2DXL0_PF4_RGC_DPG (ULSD Diesel): 1.432 $/GAL
        #    De Causal Forward-Fill cho 3 ngay nghi dau nam 2021 (01/01 - 03/01/2021)
        #    truoc phien giao dich dau tien cua nam 2021 (2021-01-04).
        # -------------------------------------------------------------------
        logger.info("Dang xu ly [3/4] Phuong an 2A: EIA Energy Daily Causal Forward-Fill (LOCF + 2020-12-31 Traceback)...")
        con.execute("""
            CREATE OR REPLACE TABLE silver.int_energy_prices_daily_filled AS
            WITH min_max_dates AS (
                SELECT
                    MIN(observation_date) AS min_obs_date,
                    MAX(observation_date) AS max_obs_date
                FROM silver.stg_imf_chokepoint_daily
            ),
            spine AS (
                SELECT CAST(d AS DATE) AS calendar_date
                FROM generate_series(
                    DATE '2020-12-31',
                    (SELECT max_obs_date FROM min_max_dates),
                    INTERVAL 1 DAY
                ) AS t(d)
            ),
            series_dim AS (
                SELECT DISTINCT
                    series,
                    duoarea,
                    area_name,
                    product,
                    product_name,
                    process,
                    process_name,
                    series_description,
                    units
                FROM silver.stg_eia_energy_prices
            ),
            eia_with_traceback AS (
                SELECT
                    period_date,
                    series,
                    price_value
                FROM silver.stg_eia_energy_prices
                UNION ALL
                SELECT DATE '2020-12-31' AS period_date, 'RBRTE' AS series, 51.22 AS price_value
                WHERE NOT EXISTS (
                    SELECT 1 FROM silver.stg_eia_energy_prices
                    WHERE series = 'RBRTE' AND period_date = DATE '2020-12-31'
                )
                UNION ALL
                SELECT DATE '2020-12-31' AS period_date, 'EER_EPD2DXL0_PF4_RGC_DPG' AS series, 1.432 AS price_value
                WHERE NOT EXISTS (
                    SELECT 1 FROM silver.stg_eia_energy_prices
                    WHERE series = 'EER_EPD2DXL0_PF4_RGC_DPG' AND period_date = DATE '2020-12-31'
                )
            ),
            grid AS (
                SELECT s.calendar_date, d.*
                FROM spine s
                CROSS JOIN series_dim d
            ),
            joined AS (
                SELECT
                    g.calendar_date,
                    g.series,
                    g.duoarea,
                    g.area_name,
                    g.product,
                    g.product_name,
                    g.process,
                    g.process_name,
                    g.series_description,
                    g.units,
                    p.price_value                                                   AS price_value_observed,
                    CASE WHEN p.price_value IS NOT NULL THEN g.calendar_date END    AS trading_date
                FROM grid g
                LEFT JOIN eia_with_traceback p
                    ON p.series = g.series
                    AND p.period_date = g.calendar_date
            ),
            filled AS (
                SELECT
                    *,
                    LAST_VALUE(price_value_observed IGNORE NULLS) OVER w            AS price_value,
                    LAST_VALUE(trading_date IGNORE NULLS) OVER w                    AS last_trading_date
                FROM joined
                WINDOW w AS (
                    PARTITION BY series
                    ORDER BY calendar_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )
            )
            SELECT
                calendar_date,
                series,
                duoarea,
                area_name,
                product,
                product_name,
                process,
                process_name,
                series_description,
                units,
                price_value,
                price_value_observed,
                last_trading_date,
                (price_value_observed IS NULL AND price_value IS NOT NULL)          AS is_forward_filled,
                DATE_DIFF('day', last_trading_date, calendar_date)                  AS days_since_last_trade
            FROM filled
            WHERE calendar_date >= (SELECT min_obs_date FROM min_max_dates)
            ORDER BY series, calendar_date;
        """)
        con.execute(f"""
            COPY silver.int_energy_prices_daily_filled
            TO '{OUT_EIA_FILLED.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 4. Bang tich hop: Chokepoint Daily + Gia Brent & ULSD Diesel (Pivoted)
        # -------------------------------------------------------------------
        logger.info("Dang xu ly [4/4] Tich hop Chokepoint Daily voi Gia Brent & Diesel...")
        con.execute("""
            CREATE OR REPLACE TABLE silver.int_maritime_energy_daily_joined AS
            WITH energy_pivot AS (
                SELECT
                    calendar_date,
                    MAX(CASE WHEN series = 'RBRTE' THEN price_value END)                        AS brent_usd_per_bbl,
                    MAX(CASE WHEN series = 'RBRTE' THEN area_name END)                          AS brent_pricing_hub,
                    MAX(CASE WHEN series = 'RBRTE' THEN is_forward_filled END)                  AS brent_is_ffill,
                    MAX(CASE WHEN series = 'EER_EPD2DXL0_PF4_RGC_DPG' THEN price_value END)     AS ulsd_usd_per_gal,
                    MAX(CASE WHEN series = 'EER_EPD2DXL0_PF4_RGC_DPG' THEN area_name END)       AS ulsd_pricing_hub,
                    MAX(CASE WHEN series = 'EER_EPD2DXL0_PF4_RGC_DPG' THEN is_forward_filled END) AS ulsd_is_ffill
                FROM silver.int_energy_prices_daily_filled
                GROUP BY calendar_date
            )
            SELECT
                c.observation_date,
                c.year,
                c.month,
                c.day,
                c.portid,
                c.portname,
                c.n_container,
                c.n_dry_bulk,
                c.n_general_cargo,
                c.n_roro,
                c.n_tanker,
                c.n_cargo,
                c.n_total,
                c.capacity_container,
                c.capacity_dry_bulk,
                c.capacity_general_cargo,
                c.capacity_roro,
                c.capacity_tanker,
                c.capacity_cargo,
                c.capacity,
                c.capacity_cargo_raw,
                c.capacity_raw,
                c.capacity_cargo_rounding_diff,
                c.capacity_rounding_diff,
                e.brent_usd_per_bbl,
                e.brent_pricing_hub,
                e.brent_is_ffill,
                e.ulsd_usd_per_gal,
                e.ulsd_pricing_hub,
                e.ulsd_is_ffill,
                c.object_id,
                c.ingested_at_utc
            FROM silver.stg_imf_chokepoint_daily c
            LEFT JOIN energy_pivot e
                ON c.observation_date = e.calendar_date
            ORDER BY c.portid, c.observation_date;
        """)
        con.execute(f"""
            COPY silver.int_maritime_energy_daily_joined
            TO '{OUT_JOINED.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # In bao cao ket qua xuat file
        # -------------------------------------------------------------------
        outputs = [
            ("silver.stg_eia_energy_prices", OUT_EIA_STAGING),
            ("silver.int_energy_prices_daily_filled", OUT_EIA_FILLED),
            ("silver.stg_imf_chokepoint_daily", OUT_IMF_PROCESSED),
            ("silver.int_maritime_energy_daily_joined", OUT_JOINED),
        ]
        print("\n" + "=" * 95)
        print("  KET QUA TAO TANG DU LIEU DA XU LY (DATA/PROCESSED & DUCKDB SILVER SCHEMA)")
        print("=" * 95)
        print(f"  {'Bang DuckDB':<42} {'File Parquet':<40} {'So dong':>9} {'Kich thuoc':>10}")
        print("  " + "-" * 91)
        for tbl, fpath in outputs:
            cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            size_kb = fpath.stat().st_size / 1024
            print(f"  {tbl:<42} {fpath.name:<40} {cnt:>9,} {size_kb:>8.1f} KB")
        print("=" * 95 + "\n")

    finally:
        con.close()


if __name__ == "__main__":
    build_processed_layer()
