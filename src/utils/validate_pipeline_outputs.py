"""
validate_pipeline_outputs.py
----------------------------
Cong kiem tra chat luong truoc khi nap du lieu len MotherDuck (Pre-load Gate).
Dam bao toan bo 14 file Parquet cua ca 3 tang (Bronze, Silver, BI Mart) ton tai,
khong rong va dat cac dieu kien toan ven co ban truoc khi DROP/INSERT tren Cloud.

Chay:
  venv\\Scripts\\python.exe -m src.utils.validate_pipeline_outputs
"""

from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path

import duckdb

from src.load.load_to_motherduck import DATA_GOLD_DIR, DATA_PROCESSED_DIR, TABLE_SPECS

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def validate_outputs() -> None:
    con = duckdb.connect()
    summary_rows: list[tuple[str, str, int, float]] = []
    errors: list[str] = []

    try:
        for schema, table, parquet_path, *_ in TABLE_SPECS:
            if not parquet_path.exists():
                errors.append(f"Thieu file Parquet: {parquet_path}")
                continue

            row_count = con.execute(
                f"SELECT COUNT(*) FROM read_parquet('{parquet_path.as_posix()}')"
            ).fetchone()[0]
            size_mb = parquet_path.stat().st_size / 1024**2
            summary_rows.append((f"{schema}.{table}", parquet_path.name, int(row_count), size_mb))

            if row_count <= 0:
                errors.append(f"Bang {schema}.{table} ({parquet_path.name}) bi rong (0 dong)")

        # Kiem tra cac rang buoc nghiep vu cot loi tren Silver & Gold
        eia_stg = DATA_PROCESSED_DIR / "eia_energy_prices_staging.parquet"
        if eia_stg.exists():
            null_area = con.execute(
                f"""
                SELECT COUNT(*) FROM read_parquet('{eia_stg.as_posix()}')
                WHERE area_name IS NULL OR period_date IS NULL OR price_value IS NULL
                """
            ).fetchone()[0]
            if null_area > 0:
                errors.append(f"stg_eia_energy_prices co {null_area} dong NULL o area_name/period_date/price_value")

        dim_cp = DATA_GOLD_DIR / "dim_chokepoints.parquet"
        if dim_cp.exists():
            n_ports = con.execute(f"SELECT COUNT(*) FROM read_parquet('{dim_cp.as_posix()}')").fetchone()[0]
            if n_ports != 28:
                errors.append(f"dim_chokepoints ky vong 28 diem nghen nhung thuc te co {n_ports}")

        fct_transit = DATA_GOLD_DIR / "fct_chokepoint_transit_daily.parquet"
        fct_energy = DATA_GOLD_DIR / "fct_energy_prices_daily.parquet"
        max_transit_date = None
        max_energy_date = None

        if fct_transit.exists():
            max_transit_date = con.execute(
                f"SELECT MAX(observation_date) FROM read_parquet('{fct_transit.as_posix()}')"
            ).fetchone()[0]
        if fct_energy.exists():
            max_energy_date = con.execute(
                f"SELECT MAX(calendar_date) FROM read_parquet('{fct_energy.as_posix()}')"
            ).fetchone()[0]

        logger.info(
            f"Do tuoi du lieu dau ra: Chokepoint den {max_transit_date} | Energy den {max_energy_date}"
        )

        # Ghi bang tom tat vao GitHub Step Summary neu chay trong GitHub Actions
        step_summary = os.getenv("GITHUB_STEP_SUMMARY")
        if step_summary:
            lines = [
                "### Ket qua Pre-load Validation Gate",
                "",
                f"- **Chokepoint moi nhat:** `{max_transit_date}`",
                f"- **Energy price moi nhat:** `{max_energy_date}`",
                "",
                "| Bang | File Parquet | So dong | Dung luong (MB) |",
                "|---|---|---:|---:|",
            ]
            for tbl, fname, cnt, sz in summary_rows:
                lines.append(f"| `{tbl}` | `{fname}` | {cnt:,} | {sz:.2f} |")
            lines.append("")
            with open(step_summary, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

        if errors:
            for err in errors:
                logger.error(f"[VALIDATION ERROR] {err}")
            raise RuntimeError("Pre-load validation that bai. Khong day du lieu len MotherDuck.")

        logger.info(f"Pre-load validation DAT: {len(summary_rows)}/{len(TABLE_SPECS)} bang hop le.")
    finally:
        con.close()


if __name__ == "__main__":
    try:
        validate_outputs()
    except Exception as exc:
        logger.error(str(exc))
        sys.exit(1)
