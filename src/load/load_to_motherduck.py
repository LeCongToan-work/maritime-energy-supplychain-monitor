"""
load_to_motherduck.py
---------------------
Day cac file Parquet cua ca 3 tang Medallion (Bronze `raw`, Silver `silver`, Gold `gold`)
len local DuckDB (`data/maritime_dwh.duckdb`) va MotherDuck Cloud (`maritime_dwh`)
kem theo day du cac rang buoc KHOA CHINH (PRIMARY KEY) va KHOA NGOAI (FOREIGN KEY).

  - Tao database `maritime_dwh` va cac schema `raw`, `silver`, `gold`.
  - Xoa bang theo thu tu nguoc (bang con Fact/Mart truoc, bang cha Dimension sau)
    va tao bang voi DDL tuong minh co PRIMARY KEY + FOREIGN KEY (...) REFERENCES ...
    theo thu tu xuoi (bang cha Dimension truoc, bang con Fact/Mart sau).
  - Nap du lieu tu Parquet va doi chieu so dong + danh sach rang buoc PK/FK.

Yeu cau: bien moi truong MOTHERDUCK_TOKEN trong file .env
Chay:
  venv\\Scripts\\python.exe -m src.load.load_to_motherduck          (Dong bo ca Local DuckDB & MotherDuck Cloud)
  venv\\Scripts\\python.exe -m src.load.load_to_motherduck --local  (Chi cap nhat Local DuckDB)
"""

from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DATA_GOLD_DIR = PROJECT_ROOT / "data" / "gold"
LOCAL_DUCKDB_PATH = PROJECT_ROOT / "data" / "maritime_dwh.duckdb"

DATABASE_NAME = "maritime_dwh"

# Danh sach bang theo thu tu phu thuoc (Parent truoc -> Child sau)
# Moi phan tu: (schema, table_name, parquet_path, primary_key_cols, foreign_keys)
# Trong do foreign_keys la list cac tuple: (fk_cols_list, ref_schema, ref_table, ref_cols_list)
TABLE_SPECS: list[tuple[str, str, Path, list[str], list[tuple[list[str], str, str, list[str]]]]] = [
    # -----------------------------------------------------------------------
    # 1. TANG BRONZE (RAW)
    # -----------------------------------------------------------------------
    (
        "raw",
        "eia_energy_prices_daily",
        DATA_RAW_DIR / "eia_energy_prices_daily_raw.parquet",
        ["series", "period"],
        [],
    ),
    (
        "raw",
        "imf_chokepoint_daily",
        DATA_RAW_DIR / "imf_chokepoint_daily_raw.parquet",
        ["portid", "date"],
        [],
    ),
    # -----------------------------------------------------------------------
    # 2. TANG SILVER (PROCESSED & CLEANED)
    # -----------------------------------------------------------------------
    (
        "silver",
        "stg_eia_energy_prices",
        DATA_PROCESSED_DIR / "eia_energy_prices_staging.parquet",
        ["series", "period_date"],
        [],
    ),
    (
        "silver",
        "int_energy_prices_daily_filled",
        DATA_PROCESSED_DIR / "eia_energy_prices_daily_filled.parquet",
        ["series", "calendar_date"],
        [],
    ),
    (
        "silver",
        "stg_imf_chokepoint_daily",
        DATA_PROCESSED_DIR / "imf_chokepoint_daily_processed.parquet",
        ["observation_date", "portid"],
        [],
    ),
    (
        "silver",
        "int_maritime_energy_daily_joined",
        DATA_PROCESSED_DIR / "maritime_energy_daily_joined.parquet",
        ["observation_date", "portid"],
        [
            (["observation_date", "portid"], "silver", "stg_imf_chokepoint_daily", ["observation_date", "portid"]),
        ],
    ),
    # -----------------------------------------------------------------------
    # 3. TANG BI MART (STAR SCHEMA DIMENSIONS & FACTS)
    # -----------------------------------------------------------------------
    (
        "bi_mart",
        "dim_chokepoints",
        DATA_GOLD_DIR / "dim_chokepoints.parquet",
        ["portid"],
        [],
    ),
    (
        "bi_mart",
        "dim_geopolitical_events",
        DATA_GOLD_DIR / "dim_geopolitical_events.parquet",
        ["event_id"],
        [
            (["primary_portid"], "bi_mart", "dim_chokepoints", ["portid"]),
        ],
    ),
    (
        "bi_mart",
        "dim_chokepoint_rerouting_map",
        DATA_GOLD_DIR / "dim_chokepoint_rerouting_map.parquet",
        ["primary_portid"],
        [
            (["primary_portid"], "bi_mart", "dim_chokepoints", ["portid"]),
            (["alt_portid"], "bi_mart", "dim_chokepoints", ["portid"]),
        ],
    ),
    (
        "bi_mart",
        "fact_energy_prices_daily",
        DATA_GOLD_DIR / "fct_energy_prices_daily.parquet",
        ["calendar_date"],
        [],
    ),
    (
        "bi_mart",
        "fact_chokepoint_transit_daily",
        DATA_GOLD_DIR / "fct_chokepoint_transit_daily.parquet",
        ["observation_date", "portid"],
        [
            (["portid"], "bi_mart", "dim_chokepoints", ["portid"]),
            (["active_event_id"], "bi_mart", "dim_geopolitical_events", ["event_id"]),
            (["observation_date"], "bi_mart", "fact_energy_prices_daily", ["calendar_date"]),
        ],
    ),
    (
        "bi_mart",
        "fact_chokepoint_energy_regime_daily",
        DATA_GOLD_DIR / "mart_chokepoint_energy_regime_daily.parquet",
        ["observation_date", "portid"],
        [
            (["observation_date", "portid"], "bi_mart", "fact_chokepoint_transit_daily", ["observation_date", "portid"]),
            (["portid"], "bi_mart", "dim_chokepoints", ["portid"]),
            (["active_event_id"], "bi_mart", "dim_geopolitical_events", ["event_id"]),
            (["observation_date"], "bi_mart", "fact_energy_prices_daily", ["calendar_date"]),
        ],
    ),
    (
        "bi_mart",
        "fact_red_sea_cape_rerouting_daily",
        DATA_GOLD_DIR / "mart_red_sea_cape_rerouting_daily.parquet",
        ["observation_date"],
        [
            (["observation_date"], "bi_mart", "fact_energy_prices_daily", ["calendar_date"]),
        ],
    ),
    (
        "bi_mart",
        "fact_outlier_consensus_labeled_daily",
        DATA_GOLD_DIR / "mart_outlier_consensus_labeled_daily.parquet",
        ["observation_date", "portid"],
        [
            (["observation_date", "portid"], "bi_mart", "fact_chokepoint_transit_daily", ["observation_date", "portid"]),
            (["portid"], "bi_mart", "dim_chokepoints", ["portid"]),
            (["active_event_id"], "bi_mart", "dim_geopolitical_events", ["event_id"]),
            (["observation_date"], "bi_mart", "fact_energy_prices_daily", ["calendar_date"]),
        ],
    ),
]

MAX_UPLOAD_BYTES = 1 * 1024**3


def check_local_files() -> None:
    missing = [str(spec[2]) for spec in TABLE_SPECS if not spec[2].exists()]
    if missing:
        raise FileNotFoundError(f"Thieu file Parquet, hay chay pipeline truoc: {missing}")

    total = sum(spec[2].stat().st_size for spec in TABLE_SPECS)
    logger.info(f"Tong dung luong Parquet local (13 bang): {total / 1024 ** 2:.2f} MB")
    if total > MAX_UPLOAD_BYTES:
        raise RuntimeError(
            f"Du lieu {total / 1024 ** 3:.2f} GB vuot nguong an toan {MAX_UPLOAD_BYTES / 1024 ** 3:.0f} GB "
            "cua goi Free. Dung lai de tranh phat sinh phi."
        )


def build_create_table_ddl(
    con: duckdb.DuckDBPyConnection,
    db_prefix: str,
    schema: str,
    table: str,
    parquet_path: Path,
    pk_cols: list[str],
    fks: list[tuple[list[str], str, str, list[str]]],
) -> str:
    cols_info = con.execute(
        f"DESCRIBE SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
    ).fetchall()

    col_defs = []
    for col_name, col_type, *_ in cols_info:
        col_defs.append(f'"{col_name}" {col_type}')

    if pk_cols:
        pk_expr = ", ".join(f'"{c}"' for c in pk_cols)
        col_defs.append(f"PRIMARY KEY ({pk_expr})")

    for fk_cols, ref_schema, ref_table, ref_cols in fks:
        fk_expr = ", ".join(f'"{c}"' for c in fk_cols)
        ref_expr = ", ".join(f'"{c}"' for c in ref_cols)
        ref_full = f"{ref_schema}.{ref_table}"
        col_defs.append(f"FOREIGN KEY ({fk_expr}) REFERENCES {ref_full} ({ref_expr})")

    full_name = f"{db_prefix}.{schema}.{table}" if db_prefix else f"{schema}.{table}"
    body = ",\n    ".join(col_defs)
    return f"CREATE TABLE {full_name} (\n    {body}\n);"


def sync_tables_with_constraints(con: duckdb.DuckDBPyConnection, db_prefix: str = "") -> None:
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("CREATE SCHEMA IF NOT EXISTS silver")
    con.execute("CREATE SCHEMA IF NOT EXISTS bi_mart")

    # Xoa bo schema gold cu (neu ton tai) de dam bao sach se theo yeu cau
    try:
        gold_schema = f"{db_prefix}.gold" if db_prefix else "gold"
        con.execute(f"DROP SCHEMA IF EXISTS {gold_schema} CASCADE")
        logger.info(f"Da xoa bo schema cu: {gold_schema}")
    except Exception as exc:
        logger.warning(f"Bo qua buoc xoa schema gold cu: {exc}")

    # 1. Xoa cac bang theo thu tu NGUOC (Child truoc -> Parent sau) de khong vi pham rang buoc FK khi DROP
    logger.info("Dang xoa cac bang cu theo thu tu phu thuoc nguoc (Child -> Parent)...")
    for schema, table, *_ in reversed(TABLE_SPECS):
        full_name = f"{db_prefix}.{schema}.{table}" if db_prefix else f"{schema}.{table}"
        con.execute(f"DROP TABLE IF EXISTS {full_name}")

    # 2. Tao bang voi PRIMARY KEY & FOREIGN KEY va nap du lieu theo thu tu XUOI (Parent -> Child)
    for schema, table, parquet_path, pk_cols, fks in TABLE_SPECS:
        full_name = f"{db_prefix}.{schema}.{table}" if db_prefix else f"{schema}.{table}"
        local_rows = duckdb.sql(
            f"SELECT COUNT(*) FROM read_parquet('{parquet_path.as_posix()}')"
        ).fetchone()[0]

        ddl = build_create_table_ddl(con, db_prefix, schema, table, parquet_path, pk_cols, fks)
        logger.info(
            f"Dang tao & nap {parquet_path.name} ({local_rows:,} dong | PK={pk_cols} | FKs={len(fks)}) -> {full_name}"
        )
        con.execute(ddl)
        con.execute(
            f"INSERT INTO {full_name} SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
        )

        target_rows = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
        if target_rows != local_rows:
            raise RuntimeError(
                f"{full_name}: local {local_rows:,} dong nhung đích chi co {target_rows:,} dong"
            )
        logger.info(f"OK {full_name}: {target_rows:,} dong (PK & {len(fks)} FK da kich hoat)")

    # 3. Tao View alias (fct_ -> fact_) de tuong thich toi da cac query analytics
    bi_mart_prefix = f"{db_prefix}.bi_mart" if db_prefix else "bi_mart"
    try:
        con.execute(
            f"CREATE OR REPLACE VIEW {bi_mart_prefix}.fct_energy_prices_daily AS SELECT * FROM {bi_mart_prefix}.fact_energy_prices_daily"
        )
        con.execute(
            f"CREATE OR REPLACE VIEW {bi_mart_prefix}.fct_chokepoint_transit_daily AS SELECT * FROM {bi_mart_prefix}.fact_chokepoint_transit_daily"
        )
        logger.info(f"Da tao cac View fct_* tuong thich trong {bi_mart_prefix}")
    except Exception as exc:
        logger.warning(f"Bo qua buoc tao View fct_*: {exc}")

    # 3. In danh sach rang buoc PRIMARY KEY va FOREIGN KEY da tao
    where_db = f"AND database_name = '{db_prefix}'" if db_prefix else ""
    constraints = con.execute(f"""
        SELECT
            schema_name,
            table_name,
            constraint_type,
            constraint_column_names,
            referenced_table,
            referenced_column_names
        FROM duckdb_constraints()
        WHERE constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
          {where_db}
        ORDER BY schema_name, table_name, constraint_type DESC
    """).fetchall()

    logger.info(f"Tong so rang buoc PK/FK da thiet lap: {len(constraints)}")
    for s_name, t_name, c_type, c_cols, ref_tbl, ref_cols in constraints:
        if c_type == "PRIMARY KEY":
            logger.info(f"  [PK] {s_name}.{t_name} ({', '.join(c_cols)})")
        else:
            logger.info(
                f"  [FK] {s_name}.{t_name} ({', '.join(c_cols)}) -> {s_name}.{ref_tbl} ({', '.join(ref_cols)})"
            )


def connect_motherduck() -> duckdb.DuckDBPyConnection:
    token = os.getenv("MOTHERDUCK_TOKEN")
    if not token:
        raise ValueError("Thieu MOTHERDUCK_TOKEN trong file .env")

    os.environ["motherduck_token"] = token
    con = duckdb.connect("md:")
    con.execute(f"CREATE DATABASE IF NOT EXISTS {DATABASE_NAME}")
    con.execute(f"USE {DATABASE_NAME}")
    return con


def run_load_motherduck(local_only: bool = False) -> None:
    check_local_files()

    # Cap nhat Local DuckDB truoc
    logger.info(f"=== [BUOC 1] CAP NHAT RANG BUOC PK/FK TREN LOCAL DUCKDB ({LOCAL_DUCKDB_PATH.name}) ===")
    local_con = duckdb.connect(str(LOCAL_DUCKDB_PATH))
    try:
        sync_tables_with_constraints(local_con, db_prefix="")
    finally:
        local_con.close()

    if local_only:
        return

    # Cap nhat MotherDuck Cloud
    logger.info(f"=== [BUOC 2] DONG BO BANG & RANG BUOC PK/FK LEN MOTHERDUCK CLOUD ({DATABASE_NAME}) ===")
    md_con = connect_motherduck()
    try:
        sync_tables_with_constraints(md_con, db_prefix=DATABASE_NAME)
    finally:
        md_con.close()


if __name__ == "__main__":
    try:
        is_local_only = "--local" in sys.argv
        run_load_motherduck(local_only=is_local_only)
    except Exception as exc:
        logger.error(str(exc))
        sys.exit(1)
