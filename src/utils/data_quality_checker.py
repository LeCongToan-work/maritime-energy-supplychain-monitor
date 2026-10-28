"""
data_quality_checker.py
-----------------------
Kiem tra chat luong du lieu Bronze Layer, bao cao chi tiet den tung truong, tung dong.

Cac nhom kiem tra:
  [1] NULL        : moi truong -> so dong null, ti le %, danh sach dong cu the bi thieu.
  [2] DUPLICATE   : tung bo key (composite key, ObjectId) va trung lap toan dong -> in ra dong trung.
  [3] RULES       : dinh dang (ngay, so), mien gia tri (am, ngoai khoang), rang buoc nghiep vu
                    (n_total = n_cargo + n_tanker, ...) -> so dong vi pham + dong mau.
  [4] COVERAGE    : so nhom (chokepoint / series) thuc te so voi ky vong, so dong, khoang ngay, ngay bi thieu.
  [5] FIELD STATS : thong ke tung truong (numeric: min/max/mean/median/std; text: top gia tri).
  [6] SCHEMA      : truong thieu / truong thua so voi schema.
  [7] FINDINGS    : tong hop tung loi cu the. Khong dung PASS/FAIL chung chung.

Exit code: 0 = khong co loi, 1 = co it nhat mot loi.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"

NULL_LIKE = {"", "none", "nan", "null", "n/a", "na", "<na>"}
SAMPLE_ROWS = 10
WIDTH = 100


# ---------------------------------------------------------------------------
# Rule helpers: moi rule tra ve Series bool, True = dong vi pham
# ---------------------------------------------------------------------------
def bad_date(col):
    return lambda df: pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce").isna()


def bad_timestamp(col):
    return lambda df: pd.to_datetime(df[col], errors="coerce", utc=True).isna()


def bad_numeric(col):
    return lambda df: pd.to_numeric(df[col], errors="coerce").isna()


def non_positive(col):
    return lambda df: pd.to_numeric(df[col], errors="coerce") <= 0


def negative(cols):
    return lambda df: (df[cols] < 0).any(axis=1)


def not_equal_sum(total, parts, tolerance=0):
    return lambda df: (df[total] - df[parts].sum(axis=1)).abs() > tolerance


def out_of_range(col, low, high):
    return lambda df: ~df[col].between(low, high)


def date_parts_mismatch(df):
    d = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    return (d.dt.year != df["year"]) | (d.dt.month != df["month"]) | (d.dt.day != df["day"])


def bad_portid(df):
    return ~df["portid"].astype(str).str.fullmatch(r"chokepoint\d+")


def units_mismatch(df):
    expected = df["series"].map({"RBRTE": "$/BBL", "EER_EPD2DXL0_PF4_RGC_DPG": "$/GAL"})
    return expected.notna() & (expected != df["units"])


IMF_COUNT_COLS = [
    "n_container", "n_dry_bulk", "n_general_cargo", "n_roro", "n_tanker", "n_cargo", "n_total",
    "capacity_container", "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro",
    "capacity_tanker", "capacity_cargo", "capacity",
]

EIA_SCHEMA = {
    "file": DATA_RAW_DIR / "eia_energy_prices_daily_raw.parquet",
    "label": "EIA Energy Prices Daily (Bronze)",
    "fields": [
        "period", "duoarea", "area-name", "product", "product-name",
        "process", "process-name", "series", "series-description",
        "value", "units", "_ingested_at_utc",
    ],
    "id_fields": ["period", "series"],
    "unique_keys": [["period", "series"]],
    "rules": [
        ("period dung dinh dang YYYY-MM-DD", ["period"], bad_date("period")),
        ("value la so hop le", ["value"], bad_numeric("value")),
        ("value > 0", ["value"], non_positive("value")),
        ("units khop voi series (RBRTE=$/BBL, EER_*=$/GAL)", ["series", "units"], units_mismatch),
        ("_ingested_at_utc dung dinh dang timestamp", ["_ingested_at_utc"], bad_timestamp("_ingested_at_utc")),
    ],
    "coverage": {
        "group_col": "series",
        "label_col": "product-name",
        "date_col": "period",
        "expected_groups": 2,
        "check_daily_gaps": False,
    },
}

IMF_SCHEMA = {
    "file": DATA_RAW_DIR / "imf_chokepoint_daily_raw.parquet",
    "label": "IMF PortWatch Chokepoint Daily (Bronze)",
    "fields": [
        "date", "year", "month", "day", "portid", "portname",
        "n_container", "n_dry_bulk", "n_general_cargo", "n_roro",
        "n_tanker", "n_cargo", "n_total",
        "capacity_container", "capacity_dry_bulk", "capacity_general_cargo",
        "capacity_roro", "capacity_tanker", "capacity_cargo", "capacity",
        "ObjectId", "_ingested_at_utc",
    ],
    "id_fields": ["date", "portid"],
    "unique_keys": [["date", "portid"], ["ObjectId"]],
    "rules": [
        ("date dung dinh dang YYYY-MM-DD", ["date"], bad_date("date")),
        ("year/month/day khop voi date", ["date", "year", "month", "day"], date_parts_mismatch),
        ("month trong khoang 1-12", ["month"], out_of_range("month", 1, 12)),
        ("day trong khoang 1-31", ["day"], out_of_range("day", 1, 31)),
        ("portid dang chokepoint<so>", ["portid"], bad_portid),
        ("n_* va capacity_* khong am", IMF_COUNT_COLS, negative(IMF_COUNT_COLS)),
        ("n_cargo = container + dry_bulk + general_cargo + roro",
         ["n_cargo", "n_container", "n_dry_bulk", "n_general_cargo", "n_roro"],
         not_equal_sum("n_cargo", ["n_container", "n_dry_bulk", "n_general_cargo", "n_roro"])),
        ("n_total = n_cargo + n_tanker", ["n_total", "n_cargo", "n_tanker"],
         not_equal_sum("n_total", ["n_cargo", "n_tanker"])),
        ("capacity_cargo = tong capacity 4 nhom tau hang (dung sai lam tron 3 tan)",
         ["capacity_cargo", "capacity_container", "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro"],
         not_equal_sum("capacity_cargo",
                       ["capacity_container", "capacity_dry_bulk", "capacity_general_cargo", "capacity_roro"],
                       tolerance=3)),
        ("capacity = capacity_cargo + capacity_tanker (dung sai lam tron 1 tan)",
         ["capacity", "capacity_cargo", "capacity_tanker"],
         not_equal_sum("capacity", ["capacity_cargo", "capacity_tanker"], tolerance=1)),
        ("_ingested_at_utc dung dinh dang timestamp", ["_ingested_at_utc"], bad_timestamp("_ingested_at_utc")),
    ],
    "coverage": {
        "group_col": "portid",
        "label_col": "portname",
        "date_col": "date",
        "expected_groups": 28,
        "check_daily_gaps": True,
    },
}


def sep(char="-"):
    return char * WIDTH


def null_mask(series: pd.Series) -> pd.Series:
    mask = series.isnull()
    if not pd.api.types.is_numeric_dtype(series):
        text = series.astype("string").str.strip().str.lower()
        mask = mask | text.isin(NULL_LIKE).fillna(False)
    return mask


def show_rows(df: pd.DataFrame, mask: pd.Series, cols: list[str], indent: str = "      ") -> None:
    sample = df.loc[mask, cols].head(SAMPLE_ROWS)
    print(f"{indent}Dong mau (toi da {SAMPLE_ROWS}, cot 'row' la chi so dong trong file):")
    for line in sample.rename_axis("row").reset_index().to_string(index=False).splitlines():
        print(f"{indent}  {line}")
    if mask.sum() > SAMPLE_ROWS:
        print(f"{indent}  ... con {int(mask.sum()) - SAMPLE_ROWS} dong nua")


# ---------------------------------------------------------------------------
# [1] NULL
# ---------------------------------------------------------------------------
def check_null(df, schema, findings):
    total = len(df)
    print("\n  [1] NULL / MISSING PER FIELD")
    print("  " + sep())
    print(f"  {'#':<4}{'Truong':<28}{'dtype':<10}{'Hop le':>9}{'Null':>8}{'Null %':>9}  Ket qua")
    print("  " + sep("-"))

    masks = {}
    for i, col in enumerate(schema["fields"], 1):
        if col not in df.columns:
            print(f"  {i:<4}{col:<28}{'-':<10}{0:>9,}{total:>8,}{100.0:>8.2f}%  THIEU TRUONG TRONG FILE")
            findings.append(f"[NULL] Truong '{col}' khong ton tai trong file (thieu hoan toan {total:,} dong)")
            continue
        mask = null_mask(df[col])
        n_null = int(mask.sum())
        pct = n_null / total * 100 if total else 0.0
        status = f"THIEU {n_null:,} dong" if n_null else "day du"
        print(f"  {i:<4}{col:<28}{str(df[col].dtype):<10}{total - n_null:>9,}{n_null:>8,}{pct:>8.2f}%  {status}")
        if n_null:
            masks[col] = mask
            findings.append(f"[NULL] Truong '{col}' thieu {n_null:,}/{total:,} dong ({pct:.2f}%)")

    for col, mask in masks.items():
        print(f"\n    Chi tiet truong '{col}': {int(mask.sum()):,} dong bi thieu")
        show_rows(df, mask, [c for c in schema["id_fields"] if c in df.columns] + [col])


# ---------------------------------------------------------------------------
# [2] DUPLICATE
# ---------------------------------------------------------------------------
def check_duplicate(df, schema, findings):
    print("\n  [2] DUPLICATE")
    print("  " + sep())

    checks = [(" + ".join(k), k) for k in schema["unique_keys"]]
    checks.append(("TOAN BO DONG (tat ca cot ngoai _ingested_at_utc)",
                   [c for c in df.columns if c != "_ingested_at_utc"]))

    for name, key in checks:
        missing = [k for k in key if k not in df.columns]
        if missing:
            print(f"  Key [{name}]: bo qua vi thieu cot {missing}")
            findings.append(f"[DUPLICATE] Khong kiem tra duoc key [{name}] vi thieu cot {missing}")
            continue
        mask = df.duplicated(subset=key, keep=False)
        n_rows = int(mask.sum())
        n_groups = int(df.loc[mask, key].drop_duplicates().shape[0]) if n_rows else 0
        n_unique = int(df[key].drop_duplicates().shape[0])
        if n_rows == 0:
            print(f"  Key [{name}]: {n_unique:,} gia tri duy nhat / {len(df):,} dong -> khong trung")
            continue
        print(f"  Key [{name}]: {n_rows:,} dong trung thuoc {n_groups:,} nhom key")
        findings.append(f"[DUPLICATE] Key [{name}] co {n_rows:,} dong trung ({n_groups:,} nhom)")
        shown = [c for c in schema["id_fields"] if c in df.columns]
        shown += [c for c in key if c not in shown][:6]
        ordered = df.sort_values(key)
        show_rows(ordered, mask.reindex(ordered.index), shown, indent="    ")


# ---------------------------------------------------------------------------
# [3] RULES
# ---------------------------------------------------------------------------
def check_rules(df, schema, findings):
    print("\n  [3] FORMAT / RANGE / BUSINESS RULES")
    print("  " + sep())
    print(f"  {'#':<4}{'Quy tac':<62}{'Vi pham':>9}  Ket qua")
    print("  " + sep("-"))

    violations = []
    for i, (name, cols, func) in enumerate(schema["rules"], 1):
        missing = [c for c in cols if c not in df.columns]
        if missing:
            print(f"  {i:<4}{name[:61]:<62}{'-':>9}  BO QUA (thieu cot {missing})")
            findings.append(f"[RULE] Khong kiem tra duoc '{name}' vi thieu cot {missing}")
            continue
        mask = func(df).fillna(True)
        n_bad = int(mask.sum())
        print(f"  {i:<4}{name[:61]:<62}{n_bad:>9,}  {'dung' if not n_bad else 'SAI'}")
        if n_bad:
            violations.append((name, cols, mask))
            findings.append(f"[RULE] '{name}' vi pham {n_bad:,}/{len(df):,} dong")

    for name, cols, mask in violations:
        print(f"\n    Chi tiet quy tac '{name}': {int(mask.sum()):,} dong vi pham")
        shown = [c for c in schema["id_fields"] if c in df.columns]
        shown += [c for c in cols if c not in shown][:6]
        show_rows(df, mask, shown)


# ---------------------------------------------------------------------------
# [4] COVERAGE
# ---------------------------------------------------------------------------
def check_coverage(df, schema, findings):
    cfg = schema["coverage"]
    g, lab, dc = cfg["group_col"], cfg["label_col"], cfg["date_col"]
    print(f"\n  [4] COVERAGE THEO '{g}'")
    print("  " + sep())
    if not {g, lab, dc}.issubset(df.columns):
        print("  Bo qua vi thieu cot")
        return

    dates = pd.to_datetime(df[dc], format="%Y-%m-%d", errors="coerce")
    work = df.assign(_d=dates).dropna(subset=["_d"])
    n_groups = work[g].nunique()
    expected = cfg["expected_groups"]
    print(f"  So nhom '{g}' thuc te: {n_groups} | ky vong: {expected}")
    if n_groups != expected:
        findings.append(f"[COVERAGE] Chi co {n_groups}/{expected} nhom '{g}' trong file")

    global_min, global_max = work["_d"].min(), work["_d"].max()
    print(f"  Khoang ngay toan file: {global_min:%Y-%m-%d} -> {global_max:%Y-%m-%d}\n")
    print(f"  {'Nhom':<28}{'Ten':<30}{'So dong':>8}{'Tu ngay':>12}{'Den ngay':>12}{'Thieu ngay':>11}")
    print("  " + sep("-"))

    def sort_key(v):
        digits = "".join(ch for ch in str(v) if ch.isdigit())
        return (int(digits) if digits else 0, str(v))

    for key in sorted(work[g].unique(), key=sort_key):
        sub = work[work[g] == key]
        missing_days = 0
        if cfg["check_daily_gaps"]:
            full = pd.date_range(sub["_d"].min(), sub["_d"].max(), freq="D")
            missing_days = len(full.difference(pd.DatetimeIndex(sub["_d"].unique())))
        name = str(sub[lab].iloc[0])[:28]
        d_min, d_max = sub["_d"].min().strftime("%Y-%m-%d"), sub["_d"].max().strftime("%Y-%m-%d")
        print(f"  {str(key):<28}{name:<30}{len(sub):>8,}{d_min:>12}{d_max:>12}{missing_days:>11,}")
        if missing_days:
            findings.append(f"[COVERAGE] '{key}' ({name}) thieu {missing_days:,} ngay trong khoang "
                            f"{sub['_d'].min():%Y-%m-%d} -> {sub['_d'].max():%Y-%m-%d}")
        if sub["_d"].max() < global_max:
            findings.append(f"[COVERAGE] '{key}' ({name}) ket thuc som: {sub['_d'].max():%Y-%m-%d} "
                            f"< {global_max:%Y-%m-%d}")


# ---------------------------------------------------------------------------
# [5] FIELD STATS
# ---------------------------------------------------------------------------
def field_stats(df, schema):
    print("\n  [5] THONG KE TUNG TRUONG")
    print("  " + sep())
    for i, col in enumerate(schema["fields"], 1):
        if col not in df.columns:
            print(f"  {i:>2}. {col}: KHONG TON TAI")
            continue
        s = df[col].dropna()
        head = f"  {i:>2}. {col} [{df[col].dtype}] hop le={len(s):,} unique={s.nunique():,}"
        if pd.api.types.is_numeric_dtype(s) and len(s):
            print(head)
            print(f"        min={s.min():,} max={s.max():,} mean={s.mean():,.2f} "
                  f"median={s.median():,.2f} std={s.std():,.2f} so_dong_bang_0={int((s == 0).sum()):,}")
        else:
            print(head)
            top = s.value_counts().head(5)
            print("        top: " + " | ".join(f"{str(v)[:45]} ({c:,})" for v, c in top.items()))
            if len(s):
                print(f"        min={str(s.min())[:45]} max={str(s.max())[:45]}")


# ---------------------------------------------------------------------------
# [6] SCHEMA
# ---------------------------------------------------------------------------
def check_schema(df, schema, findings):
    print("\n  [6] SCHEMA")
    print("  " + sep())
    absent = [c for c in schema["fields"] if c not in df.columns]
    extra = [c for c in df.columns if c not in schema["fields"]]
    print(f"  Truong thieu so voi schema : {absent if absent else 'khong'}")
    print(f"  Truong thua ngoai schema   : {extra if extra else 'khong'}")
    if absent:
        findings.append(f"[SCHEMA] Thieu truong: {absent}")
    if extra:
        findings.append(f"[SCHEMA] Truong thua: {extra}")


def run_checks(schema) -> list[str] | None:
    file_path = schema["file"]
    print("\n" + sep("="))
    print(f"  DATASET : {schema['label']}")
    print(f"  FILE    : {file_path}")
    print(sep("="))

    if not file_path.exists():
        print(f"  [ERROR] File khong ton tai. Hay chay script ingest truoc.")
        return [f"[FILE] Khong tim thay {file_path}"]
    try:
        df = pd.read_parquet(file_path)
    except Exception as exc:
        print(f"  [ERROR] Khong doc duoc file: {exc}")
        return [f"[FILE] Khong doc duoc {file_path}: {exc}"]

    print(f"  Kich thuoc: {len(df):,} dong x {df.shape[1]} cot")

    findings: list[str] = []
    check_null(df, schema, findings)
    check_duplicate(df, schema, findings)
    check_rules(df, schema, findings)
    check_coverage(df, schema, findings)
    field_stats(df, schema)
    check_schema(df, schema, findings)

    print("\n  [7] FINDINGS")
    print("  " + sep())
    if findings:
        for n, item in enumerate(findings, 1):
            print(f"  {n:>2}. {item}")
    else:
        n_rules = len(schema["rules"])
        print(f"  Khong phat hien loi. Da quet {len(schema['fields'])} truong x {len(df):,} dong, "
              f"{len(schema['unique_keys']) + 1} kiem tra duplicate, {n_rules} quy tac, coverage va schema.")
    return findings


def main() -> None:
    print(sep("="))
    print("  DATA QUALITY CHECKER - Maritime Energy Supply Chain Monitor")
    print(sep("="))

    results = {
        EIA_SCHEMA["label"]: run_checks(EIA_SCHEMA),
        IMF_SCHEMA["label"]: run_checks(IMF_SCHEMA),
    }

    print("\n" + sep("="))
    print("  TONG KET")
    print(sep("="))
    total_issues = 0
    for name, findings in results.items():
        total_issues += len(findings)
        print(f"  {name}: {len(findings)} loi")
        for item in findings:
            print(f"      - {item}")
    print()
    sys.exit(1 if total_issues else 0)


if __name__ == "__main__":
    main()
