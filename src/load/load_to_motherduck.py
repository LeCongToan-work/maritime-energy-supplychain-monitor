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
import json
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
MOTHERDUCK_FREE_LIMIT_GB = 10.0
DEFAULT_STOP_THRESHOLD_GB = 9.0
DEFAULT_WARN_THRESHOLD_GB = 7.5
LIMIT_REACHED_EXIT_CODE = 42

QUOTA_ERROR_KEYWORDS = (
    "storage limit",
    "quota",
    "free tier",
    "lite plan",
    "plan limit",
    "limit exceeded",
    "compute limit",
    "compute hours",
    "pulse",
    "payment required",
    "insufficient",
    "exceeded maximum",
)


class MotherDuckLimitReachedError(RuntimeError):
    """Bao hieu tai khoan MotherDuck da cham nguong gioi han goi mien phi."""


def _get_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(f"Gia tri {name}={raw!r} khong hop le, dung mac dinh {default}")
        return default


def _write_quota_report(report: dict) -> None:
    report_path = os.getenv("QUOTA_REPORT_PATH")
    if not report_path:
        return
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Da ghi bao cao dung luong MotherDuck tai: {path}")


def _is_quota_exception(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(keyword in msg for keyword in QUOTA_ERROR_KEYWORDS)


def check_local_files() -> int:
    missing = [str(spec[2]) for spec in TABLE_SPECS if not spec[2].exists()]
    if missing:
        raise FileNotFoundError(f"Thieu file Parquet, hay chay pipeline truoc: {missing}")

    total = sum(spec[2].stat().st_size for spec in TABLE_SPECS)
    logger.info(f"Tong dung luong Parquet local ({len(TABLE_SPECS)} bang): {total / 1024 ** 2:.2f} MB")
    if total > MAX_UPLOAD_BYTES:
        raise MotherDuckLimitReachedError(
            f"Du lieu upload {total / 1024 ** 3:.2f} GB vuot nguong an toan moi lan day "
            f"{MAX_UPLOAD_BYTES / 1024 ** 3:.2f} GB."
        )
    return total


def query_motherduck_storage_usage(con: duckdb.DuckDBPyConnection) -> dict:
    """
    Truy van tong dung luong dang su dung tren MotherDuck (tinh ca active, historical,
    retained_for_clone va failsafe bytes) tu MD_INFORMATION_SCHEMA.STORAGE_INFO.
    """
    report = {
        "source": "unknown",
        "free_limit_gb": MOTHERDUCK_FREE_LIMIT_GB,
        "stop_threshold_gb": _get_float_env("MOTHERDUCK_STOP_THRESHOLD_GB", DEFAULT_STOP_THRESHOLD_GB),
        "warn_threshold_gb": _get_float_env("MOTHERDUCK_WARN_THRESHOLD_GB", DEFAULT_WARN_THRESHOLD_GB),
        "active_bytes": 0,
        "historical_bytes": 0,
        "retained_for_clone_bytes": 0,
        "failsafe_bytes": 0,
        "total_bytes": 0,
        "total_gb": 0.0,
        "databases": [],
    }

    try:
        rows = con.execute("""
            SELECT
                database_name,
                COALESCE(active_bytes, 0) AS active_bytes,
                COALESCE(historical_bytes, 0) AS historical_bytes,
                COALESCE(retained_for_clone_bytes, 0) AS retained_for_clone_bytes,
                COALESCE(failsafe_bytes, 0) AS failsafe_bytes
            FROM MD_INFORMATION_SCHEMA.STORAGE_INFO
        """).fetchall()
        report["source"] = "MD_INFORMATION_SCHEMA.STORAGE_INFO"
        for db_name, active_b, hist_b, clone_b, fail_b in rows:
            db_total = int(active_b + hist_b + clone_b + fail_b)
            report["active_bytes"] += int(active_b)
            report["historical_bytes"] += int(hist_b)
            report["retained_for_clone_bytes"] += int(clone_b)
            report["failsafe_bytes"] += int(fail_b)
            report["databases"].append(
                {
                    "database_name": db_name,
                    "total_gb": round(db_total / 1024**3, 4),
                    "active_gb": round(active_b / 1024**3, 4),
                    "historical_gb": round(hist_b / 1024**3, 4),
                    "failsafe_gb": round(fail_b / 1024**3, 4),
                }
            )
    except Exception as exc:
        logger.warning(
            f"Khong truy van duoc MD_INFORMATION_SCHEMA.STORAGE_INFO ({exc}). "
            "Thu fallback bang PRAGMA database_size."
        )
        try:
            row = con.execute("SELECT database_size FROM pragma_database_size() LIMIT 1").fetchone()
            report["source"] = "pragma_database_size"
            if row and row[0]:
                logger.info(f"MotherDuck database_size (pragma): {row[0]}")
        except Exception:
            pass

    report["total_bytes"] = (
        report["active_bytes"]
        + report["historical_bytes"]
        + report["retained_for_clone_bytes"]
        + report["failsafe_bytes"]
    )
    report["total_gb"] = round(report["total_bytes"] / 1024**3, 4)
    return report


def enforce_motherduck_quota(
    con: duckdb.DuckDBPyConnection,
    incoming_bytes: int,
    stage: str,
) -> dict:
    """
    Kiem tra dung luong MotherDuck truoc/sau khi nap du lieu.
    Neu cham nguong dung an toan (mac dinh 9.0 GB / 10.0 GB goi Free), ghi bao cao va
    nem MotherDuckLimitReachedError de CI/CD thong bao va tu dong dung.
    """
    report = query_motherduck_storage_usage(con)
    report["stage"] = stage
    report["incoming_mb"] = round(incoming_bytes / 1024**2, 2)
    projected_bytes = report["total_bytes"] + (incoming_bytes if stage == "pre_upload" else 0)
    projected_gb = round(projected_bytes / 1024**3, 4)
    report["projected_gb"] = projected_gb

    stop_limit_gb = report["stop_threshold_gb"]
    warn_limit_gb = report["warn_threshold_gb"]

    if report["source"] == "MD_INFORMATION_SCHEMA.STORAGE_INFO":
        logger.info(
            f"Dung luong MotherDuck [{stage}]: {report['total_gb']:.4f} GB "
            f"(du kien: {projected_gb:.4f} GB / nguong dung: {stop_limit_gb:.2f} GB | "
            f"goi Free: {MOTHERDUCK_FREE_LIMIT_GB:.0f} GB)"
        )
        if projected_gb >= stop_limit_gb:
            report["limit_reached"] = True
            report["reason"] = (
                f"Dung luong MotherDuck ({projected_gb:.4f} GB) da cham nguong an toan "
                f"{stop_limit_gb:.2f} GB / {MOTHERDUCK_FREE_LIMIT_GB:.0f} GB cua goi mien phi."
            )
            _write_quota_report(report)
            raise MotherDuckLimitReachedError(report["reason"])

        if projected_gb >= warn_limit_gb:
            logger.warning(
                f"CANH BAO SOM: Dung luong MotherDuck ({projected_gb:.4f} GB) da vuot "
                f"{warn_limit_gb:.2f} GB (sap cham gioi han {MOTHERDUCK_FREE_LIMIT_GB:.0f} GB)."
            )

    report["limit_reached"] = False
    _write_quota_report(report)
    return report


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
    local_bytes = check_local_files()

    # Cap nhat Local DuckDB truoc
    logger.info(f"=== [BUOC 1] CAP NHAT RANG BUOC PK/FK TREN LOCAL DUCKDB ({LOCAL_DUCKDB_PATH.name}) ===")
    local_con = duckdb.connect(str(LOCAL_DUCKDB_PATH))
    try:
        sync_tables_with_constraints(local_con, db_prefix="")
    finally:
        local_con.close()

    if local_only:
        return

    # Cap nhat MotherDuck Cloud (kem kiem tra gioi han goi mien phi)
    logger.info(f"=== [BUOC 2] DONG BO BANG & RANG BUOC PK/FK LEN MOTHERDUCK CLOUD ({DATABASE_NAME}) ===")
    md_con: duckdb.DuckDBPyConnection | None = None
    try:
        md_con = connect_motherduck()
        enforce_motherduck_quota(md_con, incoming_bytes=local_bytes, stage="pre_upload")
        sync_tables_with_constraints(md_con, db_prefix=DATABASE_NAME)
        enforce_motherduck_quota(md_con, incoming_bytes=local_bytes, stage="post_upload")
    except MotherDuckLimitReachedError:
        raise
    except Exception as exc:
        if _is_quota_exception(exc):
            reason = f"MotherDuck tra ve loi gioi han goi mien phi (storage/compute): {exc}"
            _write_quota_report(
                {
                    "limit_reached": True,
                    "stage": "motherduck_api_error",
                    "free_limit_gb": MOTHERDUCK_FREE_LIMIT_GB,
                    "incoming_mb": round(local_bytes / 1024**2, 2),
                    "reason": reason,
                }
            )
            raise MotherDuckLimitReachedError(reason) from exc
        raise
    finally:
        if md_con is not None:
            md_con.close()


if __name__ == "__main__":
    try:
        is_local_only = "--local" in sys.argv
        run_load_motherduck(local_only=is_local_only)
    except MotherDuckLimitReachedError as exc:
        logger.critical(f"[MOTHERDUCK_LIMIT_REACHED] {exc}")
        sys.exit(LIMIT_REACHED_EXIT_CODE)
    except Exception as exc:
        logger.error(str(exc))
        sys.exit(1)
