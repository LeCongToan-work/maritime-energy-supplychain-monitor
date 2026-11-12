"""
build_gold_marts.py
-------------------
Xay dung tang Gold / Marts Layer (schema `gold` trong DuckDB `data/maritime_dwh.duckdb`)
va xuat 6 file Parquet ra thu muc `data/gold/*.parquet`:

  Phan lop A - Core Dimensional & Fact Models:
    1. gold.dim_chokepoints                     -> data/gold/dim_chokepoints.parquet (28 dong)
    2. gold.dim_geopolitical_events             -> data/gold/dim_geopolitical_events.parquet (4 dong)
    3. gold.fct_energy_prices_daily             -> data/gold/fct_energy_prices_daily.parquet (2,117 dong)
    4. gold.fct_chokepoint_transit_daily        -> data/gold/fct_chokepoint_transit_daily.parquet (59,276 dong)

  Phan lop B - BI Analytics Marts:
    5. gold.mart_chokepoint_energy_regime_daily -> data/gold/mart_chokepoint_energy_regime_daily.parquet (59,276 dong)
    6. gold.mart_red_sea_cape_rerouting_daily   -> data/gold/mart_red_sea_cape_rerouting_daily.parquet (2,117 dong)

Chay:
  venv\\Scripts\\python.exe -m src.process.build_gold_marts
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
DATA_GOLD_DIR = PROJECT_ROOT / "data" / "gold"
DUCKDB_PATH = PROJECT_ROOT / "data" / "maritime_dwh.duckdb"
EVENTS_SEED_CSV = PROJECT_ROOT / "dbt_maritime" / "seeds" / "geopolitical_events.csv"

OUT_DIM_CHOKEPOINTS = DATA_GOLD_DIR / "dim_chokepoints.parquet"
OUT_DIM_EVENTS = DATA_GOLD_DIR / "dim_geopolitical_events.parquet"
OUT_FCT_ENERGY = DATA_GOLD_DIR / "fct_energy_prices_daily.parquet"
OUT_FCT_TRANSIT = DATA_GOLD_DIR / "fct_chokepoint_transit_daily.parquet"
OUT_MART_REGIME = DATA_GOLD_DIR / "mart_chokepoint_energy_regime_daily.parquet"
OUT_MART_REROUTING = DATA_GOLD_DIR / "mart_red_sea_cape_rerouting_daily.parquet"


def build_gold_layer() -> None:
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(
            f"Khong tim thay DuckDB warehouse tai {DUCKDB_PATH}. Hay chay src.process.process_data truoc."
        )
    if not EVENTS_SEED_CSV.exists():
        raise FileNotFoundError(f"Khong tim thay file seed su kien: {EVENTS_SEED_CSV}")

    DATA_GOLD_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DUCKDB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold;")

        # -------------------------------------------------------------------
        # 1. Bảng chiều Điểm nghẽn Hàng hải: gold.dim_chokepoints (28 dòng)
        # -------------------------------------------------------------------
        logger.info("Dang xay dung [1/6] gold.dim_chokepoints...")
        con.execute("""
            CREATE OR REPLACE TABLE gold.dim_chokepoints AS
            WITH agg AS (
                SELECT
                    portid,
                    portname,
                    ROUND(AVG(n_total) FILTER (WHERE year IN (2021, 2022)), 2)          AS baseline_n_total,
                    ROUND(AVG(n_tanker) FILTER (WHERE year IN (2021, 2022)), 2)         AS baseline_n_tanker,
                    ROUND(AVG(capacity_tanker) FILTER (WHERE year IN (2021, 2022)), 0)  AS baseline_capacity_tanker,
                    ROUND(SUM(n_tanker) * 100.0 / NULLIF(SUM(n_total), 0), 2)           AS avg_tanker_share_pct
                FROM silver.stg_imf_chokepoint_daily
                GROUP BY portid, portname
            )
            SELECT
                portid,
                portname,
                CASE
                    WHEN portname IN ('Suez Canal', 'Bab el-Mandeb Strait', 'Strait of Hormuz')
                        THEN 'Middle East & Red Sea'
                    WHEN portname IN ('Bosporus Strait', 'Gibraltar Strait', 'Kerch Strait')
                        THEN 'Mediterranean & Black Sea'
                    WHEN portname IN ('Dover Strait', 'Oresund Strait')
                        THEN 'Europe & Baltic'
                    WHEN portname IN ('Cape of Good Hope')
                        THEN 'Southern Africa'
                    WHEN portname IN ('Panama Canal', 'Magellan Strait', 'Yucatan Channel', 'Windward Passage', 'Mona Passage')
                        THEN 'Americas & Caribbean'
                    ELSE 'Asia-Pacific'
                END AS maritime_region,
                CASE
                    WHEN portname IN ('Strait of Hormuz', 'Bosporus Strait', 'Oresund Strait', 'Kerch Strait')
                        THEN 'Origin Energy Export Hub'
                    WHEN portname IN ('Suez Canal', 'Bab el-Mandeb Strait', 'Malacca Strait', 'Panama Canal',
                                      'Gibraltar Strait', 'Dover Strait', 'Taiwan Strait', 'Korea Strait')
                        THEN 'Global Transit Corridor'
                    WHEN portname IN ('Cape of Good Hope', 'Lombok Strait', 'Sunda Strait', 'Magellan Strait')
                        THEN 'Rerouting Alternative'
                    ELSE 'Regional Maritime Passage'
                END AS chokepoint_role,
                (baseline_n_tanker >= 10.0 OR portname IN (
                    'Strait of Hormuz', 'Malacca Strait', 'Suez Canal', 'Bab el-Mandeb Strait',
                    'Dover Strait', 'Gibraltar Strait', 'Panama Canal', 'Cape of Good Hope',
                    'Bosporus Strait', 'Oresund Strait'
                )) AS is_primary_oil_route,
                baseline_n_total,
                baseline_n_tanker,
                baseline_capacity_tanker,
                avg_tanker_share_pct
            FROM agg
            ORDER BY CAST(REPLACE(portid, 'chokepoint', '') AS INTEGER);
        """)
        con.execute(f"""
            COPY gold.dim_chokepoints
            TO '{OUT_DIM_CHOKEPOINTS.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 2. Bảng chiều Sự kiện Địa chính trị & Khí hậu: gold.dim_geopolitical_events (4 dòng)
        # -------------------------------------------------------------------
        logger.info("Dang xay dung [2/6] gold.dim_geopolitical_events...")
        con.execute(f"""
            CREATE OR REPLACE TABLE gold.dim_geopolitical_events AS
            WITH raw_seed AS (
                SELECT * FROM read_csv_auto('{EVENTS_SEED_CSV.as_posix()}', header=True)
            )
            SELECT
                CAST(s.event_id AS VARCHAR)                             AS event_id,
                CAST(s.event_name AS VARCHAR)                           AS event_name,
                CAST(s.start_date AS DATE)                              AS start_date,
                CAST(s.end_date AS DATE)                                AS end_date,
                DATE_DIFF('day', CAST(s.start_date AS DATE), CAST(s.end_date AS DATE)) + 1
                                                                        AS duration_days,
                d.portid                                                AS primary_portid,
                CAST(s.primary_chokepoint AS VARCHAR)                   AS primary_chokepoint,
                CAST(s.event_category AS VARCHAR)                       AS event_category,
                CAST(s.severity_level AS VARCHAR)                       AS severity_level,
                CAST(s.description AS VARCHAR)                          AS description
            FROM raw_seed s
            LEFT JOIN gold.dim_chokepoints d
                ON d.portname = s.primary_chokepoint
            ORDER BY s.event_id;
        """)
        con.execute(f"""
            COPY gold.dim_geopolitical_events
            TO '{OUT_DIM_EVENTS.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 3. Bảng Fact Giá Năng lượng Hàng ngày: gold.fct_energy_prices_daily (2,117 dòng)
        #    Tích hợp cả chuỗi gốc I(1), Crack Spread, và chuỗi dừng I(0)
        # -------------------------------------------------------------------
        logger.info("Dang xay dung [3/6] gold.fct_energy_prices_daily...")
        con.execute("""
            CREATE OR REPLACE TABLE gold.fct_energy_prices_daily AS
            WITH pivoted AS (
                SELECT
                    calendar_date,
                    MAX(CASE WHEN series = 'RBRTE' THEN price_value END)                        AS brent_usd_per_bbl,
                    MAX(CASE WHEN series = 'RBRTE' THEN is_forward_filled END)                  AS brent_is_ffill,
                    MAX(CASE WHEN series = 'RBRTE' THEN last_trading_date END)                  AS brent_last_trading_date,
                    MAX(CASE WHEN series = 'EER_EPD2DXL0_PF4_RGC_DPG' THEN price_value END)     AS ulsd_usd_per_gal,
                    MAX(CASE WHEN series = 'EER_EPD2DXL0_PF4_RGC_DPG' THEN is_forward_filled END) AS ulsd_is_ffill,
                    MAX(CASE WHEN series = 'EER_EPD2DXL0_PF4_RGC_DPG' THEN last_trading_date END) AS ulsd_last_trading_date
                FROM silver.int_energy_prices_daily_filled
                GROUP BY calendar_date
            ),
            derived AS (
                SELECT
                    calendar_date,
                    brent_usd_per_bbl,
                    ulsd_usd_per_gal,
                    ROUND(ulsd_usd_per_gal * 42.0, 4)                                           AS ulsd_usd_per_bbl,
                    ROUND((ulsd_usd_per_gal * 42.0) - brent_usd_per_bbl, 4)                     AS diesel_brent_crack_bbl,
                    ROUND(AVG(brent_usd_per_bbl) OVER w7, 4)                                    AS brent_ma7,
                    ROUND(AVG(ulsd_usd_per_gal) OVER w7, 4)                                     AS ulsd_ma7,
                    ROUND(AVG((ulsd_usd_per_gal * 42.0) - brent_usd_per_bbl) OVER w7, 4)        AS crack_ma7,
                    ROUND(brent_usd_per_bbl - LAG(brent_usd_per_bbl, 1) OVER w_ord, 4)          AS brent_diff_1d,
                    ROUND(LN(brent_usd_per_bbl / NULLIF(LAG(brent_usd_per_bbl, 1) OVER w_ord, 0)) * 100.0, 4)
                                                                                                AS brent_log_ret_1d,
                    ROUND(brent_usd_per_bbl - LAG(brent_usd_per_bbl, 7) OVER w_ord, 4)          AS brent_diff_7d,
                    ROUND(ulsd_usd_per_gal - LAG(ulsd_usd_per_gal, 1) OVER w_ord, 4)            AS ulsd_diff_1d,
                    ROUND(LN(ulsd_usd_per_gal / NULLIF(LAG(ulsd_usd_per_gal, 1) OVER w_ord, 0)) * 100.0, 4)
                                                                                                AS ulsd_log_ret_1d,
                    ROUND(ulsd_usd_per_gal - LAG(ulsd_usd_per_gal, 7) OVER w_ord, 4)            AS ulsd_diff_7d,
                    ROUND(((ulsd_usd_per_gal * 42.0) - brent_usd_per_bbl)
                        - LAG((ulsd_usd_per_gal * 42.0) - brent_usd_per_bbl, 7) OVER w_ord, 4)  AS crack_diff_7d,
                    brent_is_ffill,
                    ulsd_is_ffill,
                    brent_last_trading_date,
                    ulsd_last_trading_date
                FROM pivoted
                WINDOW
                    w_ord AS (ORDER BY calendar_date),
                    w7 AS (ORDER BY calendar_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
            )
            SELECT
                *,
                ROUND(STDDEV_SAMP(brent_log_ret_1d) OVER (
                    ORDER BY calendar_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
                ), 4) AS brent_volatility_30d,
                ROUND(STDDEV_SAMP(ulsd_log_ret_1d) OVER (
                    ORDER BY calendar_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
                ), 4) AS ulsd_volatility_30d
            FROM derived
            ORDER BY calendar_date;
        """)
        con.execute(f"""
            COPY gold.fct_energy_prices_daily
            TO '{OUT_FCT_ENERGY.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 4. Bảng Fact Lưu lượng Điểm nghẽn: gold.fct_chokepoint_transit_daily (59,276 dòng)
        #    Tích hợp I(1), I(0), Anomaly Z-Score 90d, Regime & Daily Alert Severity
        # -------------------------------------------------------------------
        logger.info("Dang xay dung [4/6] gold.fct_chokepoint_transit_daily...")
        con.execute("""
            CREATE OR REPLACE TABLE gold.fct_chokepoint_transit_daily AS
            WITH base AS (
                SELECT
                    c.observation_date,
                    c.year,
                    c.month,
                    c.day,
                    c.portid,
                    c.portname,
                    c.n_total,
                    c.n_tanker,
                    c.n_cargo,
                    c.n_container,
                    c.n_dry_bulk,
                    c.n_general_cargo,
                    c.n_roro,
                    c.capacity,
                    c.capacity_tanker,
                    c.capacity_cargo,
                    d.baseline_n_total,
                    d.baseline_n_tanker,
                    ROUND(c.n_tanker * 100.0 / NULLIF(c.n_total, 0), 2)                         AS tanker_share_pct,
                    ROUND((c.n_total - d.baseline_n_total) * 100.0 / NULLIF(d.baseline_n_total, 0), 2)
                                                                                                AS pct_vs_baseline_total,
                    ROUND((c.n_tanker - d.baseline_n_tanker) * 100.0 / NULLIF(d.baseline_n_tanker, 0), 2)
                                                                                                AS pct_vs_baseline_tanker,
                    ROUND(AVG(c.n_total) OVER w7, 2)                                            AS n_total_ma7,
                    ROUND(AVG(c.n_tanker) OVER w7, 2)                                           AS n_tanker_ma7,
                    ROUND(AVG(c.capacity_tanker) OVER w7, 0)                                    AS capacity_tanker_ma7,
                    c.n_total - LAG(c.n_total, 1) OVER w_ord                                    AS n_total_diff_1d,
                    c.n_tanker - LAG(c.n_tanker, 1) OVER w_ord                                  AS n_tanker_diff_1d,
                    AVG(c.n_total) OVER w90                                                     AS mean_total_90d,
                    STDDEV_SAMP(c.n_total) OVER w90                                             AS std_total_90d,
                    AVG(c.n_tanker) OVER w90                                                    AS mean_tanker_90d,
                    STDDEV_SAMP(c.n_tanker) OVER w90                                            AS std_tanker_90d,
                    ev.event_id                                                                 AS active_event_id
                FROM silver.stg_imf_chokepoint_daily c
                LEFT JOIN gold.dim_chokepoints d
                    ON c.portid = d.portid
                LEFT JOIN gold.dim_geopolitical_events ev
                    ON c.portid = ev.primary_portid
                    AND c.observation_date BETWEEN ev.start_date AND ev.end_date
                WINDOW
                    w_ord AS (PARTITION BY c.portid ORDER BY c.observation_date),
                    w7    AS (PARTITION BY c.portid ORDER BY c.observation_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),
                    w90   AS (PARTITION BY c.portid ORDER BY c.observation_date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW)
            ),
            metrics AS (
                SELECT
                    observation_date,
                    year,
                    month,
                    day,
                    portid,
                    portname,
                    n_total,
                    n_tanker,
                    n_cargo,
                    n_container,
                    n_dry_bulk,
                    n_general_cargo,
                    n_roro,
                    capacity,
                    capacity_tanker,
                    capacity_cargo,
                    tanker_share_pct,
                    pct_vs_baseline_total,
                    pct_vs_baseline_tanker,
                    n_total_ma7,
                    n_tanker_ma7,
                    capacity_tanker_ma7,
                    n_total_diff_1d,
                    n_tanker_diff_1d,
                    ROUND(n_total_ma7 - LAG(n_total_ma7, 7) OVER (PARTITION BY portid ORDER BY observation_date), 2)
                                                                                                AS n_total_diff_7d,
                    ROUND(n_tanker_ma7 - LAG(n_tanker_ma7, 7) OVER (PARTITION BY portid ORDER BY observation_date), 2)
                                                                                                AS n_tanker_diff_7d,
                    ROUND((n_total - mean_total_90d) / NULLIF(std_total_90d, 0), 3)             AS n_total_zscore_90d,
                    ROUND((n_tanker - mean_tanker_90d) / NULLIF(std_tanker_90d, 0), 3)          AS n_tanker_zscore_90d,
                    active_event_id,
                    CASE
                        WHEN active_event_id IS NOT NULL THEN 'Disruption Regime'
                        ELSE 'Normal Regime'
                    END                                                                         AS regime_type
                FROM base
            )
            SELECT
                *,
                CASE
                    WHEN pct_vs_baseline_total <= -50.0 OR n_total_zscore_90d <= -3.0 THEN 'Critical'
                    WHEN pct_vs_baseline_total <= -30.0 OR n_total_zscore_90d <= -2.0 THEN 'High'
                    WHEN pct_vs_baseline_total <= -15.0 OR n_total_zscore_90d <= -1.5 THEN 'Moderate'
                    WHEN pct_vs_baseline_total >= 30.0  OR n_total_zscore_90d >= 2.0  THEN 'Rerouting Surge'
                    ELSE 'Normal'
                END AS daily_alert_severity
            FROM metrics
            ORDER BY portid, observation_date;
        """)
        con.execute(f"""
            COPY gold.fct_chokepoint_transit_daily
            TO '{OUT_FCT_TRANSIT.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 5. Bảng Mart Tương quan Động & Chế độ Khủng hoảng:
        #    gold.mart_chokepoint_energy_regime_daily (59,276 dòng)
        # -------------------------------------------------------------------
        logger.info("Dang xay dung [5/6] gold.mart_chokepoint_energy_regime_daily...")
        con.execute("""
            CREATE OR REPLACE TABLE gold.mart_chokepoint_energy_regime_daily AS
            WITH joined AS (
                SELECT
                    t.observation_date,
                    t.year,
                    t.month,
                    t.portid,
                    t.portname,
                    d.maritime_region,
                    d.chokepoint_role,
                    d.is_primary_oil_route,
                    t.regime_type,
                    t.active_event_id,
                    ev.event_name,
                    ev.severity_level                                       AS event_severity_level,
                    t.daily_alert_severity,
                    t.n_total,
                    t.n_tanker,
                    t.capacity,
                    t.capacity_tanker,
                    t.tanker_share_pct,
                    t.pct_vs_baseline_total,
                    t.pct_vs_baseline_tanker,
                    t.n_total_ma7,
                    t.n_tanker_ma7,
                    t.n_total_diff_1d,
                    t.n_tanker_diff_1d,
                    t.n_total_diff_7d,
                    t.n_tanker_diff_7d,
                    t.n_total_zscore_90d,
                    t.n_tanker_zscore_90d,
                    e.brent_usd_per_bbl,
                    e.ulsd_usd_per_gal,
                    e.ulsd_usd_per_bbl,
                    e.diesel_brent_crack_bbl,
                    e.brent_ma7,
                    e.ulsd_ma7,
                    e.brent_diff_1d,
                    e.ulsd_diff_1d,
                    e.brent_diff_7d,
                    e.ulsd_diff_7d,
                    e.crack_diff_7d,
                    e.brent_volatility_30d,
                    e.brent_is_ffill,
                    e.ulsd_is_ffill
                FROM gold.fct_chokepoint_transit_daily t
                LEFT JOIN gold.dim_chokepoints d
                    ON t.portid = d.portid
                LEFT JOIN gold.dim_geopolitical_events ev
                    ON t.active_event_id = ev.event_id
                LEFT JOIN gold.fct_energy_prices_daily e
                    ON t.observation_date = e.calendar_date
            )
            SELECT
                *,
                ROUND(CORR(n_tanker_ma7, brent_usd_per_bbl) OVER w30, 4)    AS rolling_corr_30d_tanker_brent,
                ROUND(CORR(n_tanker_ma7, ulsd_usd_per_gal) OVER w30, 4)     AS rolling_corr_30d_tanker_ulsd,
                ROUND(CORR(n_tanker_ma7, brent_usd_per_bbl) OVER w90, 4)    AS rolling_corr_90d_tanker_brent,
                ROUND(CORR(n_tanker_ma7, ulsd_usd_per_gal) OVER w90, 4)     AS rolling_corr_90d_tanker_ulsd,
                ROUND(CORR(n_tanker_diff_7d, brent_diff_7d) OVER w90, 4)    AS rolling_corr_90d_diff7d_brent,
                ROUND(CORR(n_tanker_diff_7d, ulsd_diff_7d) OVER w90, 4)     AS rolling_corr_90d_diff7d_ulsd
            FROM joined
            WINDOW
                w30 AS (PARTITION BY portid ORDER BY observation_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW),
                w90 AS (PARTITION BY portid ORDER BY observation_date ROWS BETWEEN 89 PRECEDING AND CURRENT ROW)
            ORDER BY portid, observation_date;
        """)
        con.execute(f"""
            COPY gold.mart_chokepoint_energy_regime_daily
            TO '{OUT_MART_REGIME.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # 6. Bảng Mart Chỉ số Đổi tuyến Biển Đỏ - Mũi Hảo Vọng & Đối chiếu Hormuz:
        #    gold.mart_red_sea_cape_rerouting_daily (2,117 dòng)
        # -------------------------------------------------------------------
        logger.info("Dang xay dung [6/6] gold.mart_red_sea_cape_rerouting_daily...")
        con.execute("""
            CREATE OR REPLACE TABLE gold.mart_red_sea_cape_rerouting_daily AS
            WITH route_pivot AS (
                SELECT
                    observation_date,
                    MAX(CASE WHEN portname = 'Suez Canal' THEN n_total END)                 AS suez_n_total,
                    MAX(CASE WHEN portname = 'Suez Canal' THEN n_tanker END)                AS suez_n_tanker,
                    MAX(CASE WHEN portname = 'Suez Canal' THEN n_total_ma7 END)             AS suez_ma7_total,
                    MAX(CASE WHEN portname = 'Suez Canal' THEN n_tanker_ma7 END)            AS suez_ma7_tanker,
                    MAX(CASE WHEN portname = 'Bab el-Mandeb Strait' THEN n_total END)       AS babelmandeb_n_total,
                    MAX(CASE WHEN portname = 'Bab el-Mandeb Strait' THEN n_tanker END)      AS babelmandeb_n_tanker,
                    MAX(CASE WHEN portname = 'Bab el-Mandeb Strait' THEN n_total_ma7 END)   AS babelmandeb_ma7_total,
                    MAX(CASE WHEN portname = 'Bab el-Mandeb Strait' THEN n_tanker_ma7 END)  AS babelmandeb_ma7_tanker,
                    MAX(CASE WHEN portname = 'Cape of Good Hope' THEN n_total END)          AS cape_n_total,
                    MAX(CASE WHEN portname = 'Cape of Good Hope' THEN n_tanker END)         AS cape_n_tanker,
                    MAX(CASE WHEN portname = 'Cape of Good Hope' THEN n_total_ma7 END)      AS cape_ma7_total,
                    MAX(CASE WHEN portname = 'Cape of Good Hope' THEN n_tanker_ma7 END)     AS cape_ma7_tanker,
                    MAX(CASE WHEN portname = 'Strait of Hormuz' THEN n_total END)           AS hormuz_n_total,
                    MAX(CASE WHEN portname = 'Strait of Hormuz' THEN n_tanker END)          AS hormuz_n_tanker,
                    MAX(CASE WHEN portname = 'Strait of Hormuz' THEN n_total_ma7 END)       AS hormuz_ma7_total,
                    MAX(CASE WHEN portname = 'Strait of Hormuz' THEN n_tanker_ma7 END)      AS hormuz_ma7_tanker
                FROM gold.fct_chokepoint_transit_daily
                WHERE portname IN ('Suez Canal', 'Bab el-Mandeb Strait', 'Cape of Good Hope', 'Strait of Hormuz')
                GROUP BY observation_date
            )
            SELECT
                r.observation_date,
                r.suez_n_total,
                r.babelmandeb_n_total,
                r.cape_n_total,
                r.hormuz_n_total,
                r.suez_n_tanker,
                r.babelmandeb_n_tanker,
                r.cape_n_tanker,
                r.hormuz_n_tanker,
                r.suez_ma7_total,
                r.babelmandeb_ma7_total,
                r.cape_ma7_total,
                r.hormuz_ma7_total,
                r.suez_ma7_tanker,
                r.babelmandeb_ma7_tanker,
                r.cape_ma7_tanker,
                r.hormuz_ma7_tanker,
                ROUND(r.cape_n_total * 100.0 / NULLIF(r.babelmandeb_n_total + r.cape_n_total, 0), 2)
                                                                                            AS cape_rerouting_share_total_pct,
                ROUND(r.cape_n_tanker * 100.0 / NULLIF(r.babelmandeb_n_tanker + r.cape_n_tanker, 0), 2)
                                                                                            AS cape_rerouting_share_tanker_pct,
                ROUND(r.cape_ma7_total * 100.0 / NULLIF(r.babelmandeb_ma7_total + r.cape_ma7_total, 0), 2)
                                                                                            AS cape_rerouting_ma7_total_pct,
                e.brent_usd_per_bbl,
                e.ulsd_usd_per_gal,
                e.ulsd_usd_per_bbl,
                e.diesel_brent_crack_bbl,
                e.brent_diff_7d,
                e.ulsd_diff_7d,
                e.crack_diff_7d,
                CASE
                    WHEN r.observation_date >= DATE '2023-11-19' THEN 'Red Sea Crisis (Rerouting)'
                    ELSE 'Normal Transit'
                END AS red_sea_regime,
                CASE
                    WHEN r.observation_date >= DATE '2026-02-28' THEN 'Hormuz Disruption (Supply Shock)'
                    ELSE 'Normal Transit'
                END AS hormuz_regime
            FROM route_pivot r
            LEFT JOIN gold.fct_energy_prices_daily e
                ON r.observation_date = e.calendar_date
            ORDER BY r.observation_date;
        """)
        con.execute(f"""
            COPY gold.mart_red_sea_cape_rerouting_daily
            TO '{OUT_MART_REROUTING.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # -------------------------------------------------------------------
        # In báo cáo kết quả xây dựng tầng Gold
        # -------------------------------------------------------------------
        outputs = [
            ("gold.dim_chokepoints", OUT_DIM_CHOKEPOINTS),
            ("gold.dim_geopolitical_events", OUT_DIM_EVENTS),
            ("gold.fct_energy_prices_daily", OUT_FCT_ENERGY),
            ("gold.fct_chokepoint_transit_daily", OUT_FCT_TRANSIT),
            ("gold.mart_chokepoint_energy_regime_daily", OUT_MART_REGIME),
            ("gold.mart_red_sea_cape_rerouting_daily", OUT_MART_REROUTING),
        ]
        print("\n" + "=" * 100)
        print("  KET QUA TAO TANG GOLD / MARTS LAYER (DATA/GOLD & DUCKDB GOLD SCHEMA)")
        print("=" * 100)
        print(f"  {'Bang DuckDB':<44} {'File Parquet':<44} {'So dong':>9} {'Kich thuoc':>10}")
        print("  " + "-" * 96)
        for tbl, fpath in outputs:
            cnt = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            size_kb = fpath.stat().st_size / 1024
            print(f"  {tbl:<44} {fpath.name:<44} {cnt:>9,} {size_kb:>8.1f} KB")
        print("=" * 100 + "\n")

    finally:
        con.close()


if __name__ == "__main__":
    build_gold_layer()
