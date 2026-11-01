"""
outlier_consensus_checker.py
----------------------------
He thong Phat hien, Kiem chung Dong thuan Kep (Dual-Method Consensus) va Phan loai Gan nhan
Outlier Tu dong (Zero-Touch Literature-Grounded Taxonomy L00..L10) tren du lieu
Chuoi cung ung Hang hai (IMF PortWatch) va Gia Nang luong (U.S. EIA).

Dong thoi tao bang BI Mart:
  - DuckDB Table : gold.mart_outlier_consensus_labeled_daily (59,276 dong)
  - Parquet File : data/gold/mart_outlier_consensus_labeled_daily.parquet

Co so hoc thuat:
  1. Iglewicz & Hoaglin (1993): Robust Modified Z-Score dua tren Median & MAD (|M_t| > 3.5).
  2. Tukey (1977): Non-Parametric Interquartile Range (IQR) Fence [Q1 - 2*IQR, Q3 + 2*IQR].
  3. Tsay (1988) & Chen & Liu (1993, JASA): 4 nhan dong hoc chuoi thoi gian (AO, IO, TC, LS).
  4. Charles & Darne (2005, 2014): Phan loai AO vs IO tren chuoi loi suat gia dau Brent & Diesel.
  5. Chandola et al. (2009, ACM CSUR) & Blazquez-Garcia et al. (2021, ACM CSUR):
     Point Anomaly, Contextual Anomaly, Collective (Subsequence) Anomaly.
  6. Riveiro et al. (2018), Wolsing et al. (2022) & Verschuur / IMF PortWatch (2022-2024):
     Phan loai di thuong AIS hang hai, tai dinh tuyen (Spatial Rerouting) va dong luong do bao.

Chay:
  venv\\Scripts\\python.exe -m src.utils.outlier_consensus_checker
"""

from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = PROJECT_ROOT / "data" / "maritime_dwh.duckdb"
DATA_GOLD_DIR = PROJECT_ROOT / "data" / "gold"
OUT_MART_OUTLIER_PARQUET = DATA_GOLD_DIR / "mart_outlier_consensus_labeled_daily.parquet"


def compute_rolling_mad_zscore(series: pd.Series, window: int, min_periods: int = 20) -> pd.Series:
    """
    Phuong phap 1: Robust Rolling Modified Z-Score (Iglewicz & Hoaglin, 1993)
      M_t = 0.6745 * (x_t - Median_W(x)) / MAD_W(x)
    """
    med = series.rolling(window=window, min_periods=min_periods).median()
    abs_dev = (series - med).abs()
    mad = abs_dev.rolling(window=window, min_periods=min_periods).median()
    mad_safe = mad.replace(0, np.nan)
    mod_z = 0.6745 * (series - med) / mad_safe
    return mod_z.fillna(0.0)


def compute_rolling_iqr_flags(
    series: pd.Series, window: int, k: float = 2.0, min_periods: int = 20
) -> tuple[pd.Series, pd.Series]:
    """
    Phuong phap 2: Non-Parametric Rolling Tukey IQR Fence (Tukey, 1977)
      Lower = Q1 - k * IQR, Upper = Q3 + k * IQR
    Tra ve (is_iqr_outlier, iqr_exceed_ratio)
    """
    q25 = series.rolling(window=window, min_periods=min_periods).quantile(0.25)
    q75 = series.rolling(window=window, min_periods=min_periods).quantile(0.75)
    iqr = (q75 - q25).replace(0, np.nan)
    lower = q25 - k * iqr
    upper = q75 + k * iqr
    is_out = ((series < lower) | (series > upper)).fillna(False)
    exceed = np.where(
        series > upper,
        (series - upper) / iqr,
        np.where(series < lower, (series - lower) / iqr, 0.0),
    )
    return pd.Series(is_out, index=series.index, dtype=bool), pd.Series(
        np.nan_to_num(exceed, nan=0.0), index=series.index
    )


def compute_contiguous_run_lengths(mask: pd.Series) -> pd.Series:
    """
    Tinh do dai chuoi ngay lien tiep (contiguous run length) ma mask == True.
    Dung de phan biet AO (1-2 ngay), TC (3-14 ngay), va LS (>= 15 ngay)
    hoan toan tu dong ma khong phu thuoc vao bang su kien tinh.
    """
    arr = mask.fillna(False).astype(bool).to_numpy()
    n = len(arr)
    lengths = np.zeros(n, dtype=int)
    i = 0
    while i < n:
        if arr[i]:
            j = i
            while j < n and arr[j]:
                j += 1
            lengths[i:j] = j - i
            i = j
        else:
            i += 1
    return pd.Series(lengths, index=mask.index)


def build_and_evaluate_outlier_mart() -> None:
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"Khong tim thay DuckDB tai {DUCKDB_PATH}")

    DATA_GOLD_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))

    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS gold;")

        # ===================================================================
        # 1. KIEM TRA QUY TAC VAT LY & BAO TOAN KY THUAT (LOP 1 - HARD RULES)
        # ===================================================================
        print("=" * 108)
        print("  [LOP 1] KIEM TRA QUY TAC VAT LY & BAO TOAN KY THUAT (DOMAIN HARD RULES)")
        print("=" * 108)

        hard_checks = con.execute("""
            SELECT
                COUNT(*) AS total_rows,
                COUNT(*) FILTER (WHERE n_total < 0 OR capacity < 0) AS negative_values,
                COUNT(*) FILTER (
                    WHERE n_total != (n_container + n_dry_bulk + n_general_cargo + n_roro + n_tanker)
                ) AS vessel_count_mismatch,
                COUNT(*) FILTER (
                    WHERE capacity != (capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro + capacity_tanker)
                ) AS capacity_mismatch_after_3a,
                COUNT(*) FILTER (WHERE capacity_rounding_diff > 0) AS raw_rounding_diff_rows,
                MAX(capacity_rounding_diff) AS max_raw_rounding_diff_dwt,
                COUNT(*) FILTER (WHERE (n_total > 0 AND capacity = 0) OR (n_total = 0 AND capacity > 0)) AS count_capacity_contradiction
            FROM silver.stg_imf_chokepoint_daily
        """).fetchone()

        energy_hard = con.execute("""
            SELECT
                COUNT(*) AS total_days,
                COUNT(*) FILTER (WHERE brent_usd_per_bbl <= 0 OR ulsd_usd_per_gal <= 0) AS non_positive_prices,
                COUNT(*) FILTER (WHERE brent_usd_per_bbl IS NULL OR ulsd_usd_per_gal IS NULL) AS null_prices,
                COUNT(*) FILTER (WHERE ABS(brent_log_ret_1d) > 50.0 OR ABS(ulsd_log_ret_1d) > 50.0) AS extreme_50pct_jumps
            FROM gold.fct_energy_prices_daily
        """).fetchone()

        print(f"  1. IMF Chokepoints ({hard_checks[0]:,} dong):")
        print(f"     - Gia tri am (n_total < 0 hoac capacity < 0)           : {hard_checks[1]:,} dong")
        print(f"     - Sai lech tong so tau (n_total != sum(n_i))           : {hard_checks[2]:,} dong")
        print(f"     - Sai lech tong trong tai sau Phuong an 3A             : {hard_checks[3]:,} dong (Truoc 3A co {hard_checks[4]:,} dong lech <= {hard_checks[5]} DWT)")
        print(f"     - Ban ghi co tau nhung DWT = 0 (AIS Type 5 Missing)    : {hard_checks[6]:,} dong")
        print(f"  2. EIA Energy Prices ({energy_hard[0]:,} ngay):")
        print(f"     - Gia <= 0 hoac NULL                                   : {energy_hard[1]} dong <= 0 | {energy_hard[2]} dong NULL")
        print(f"     - Nhay gia phi vat ly (> 50%/ngay)                     : {energy_hard[3]} ngay")

        # ===================================================================
        # 2. PHAT HIEN & GAN NHAN OUTLIER GIA NANG LUONG (LOP 2A)
        # ===================================================================
        print("\n" + "=" * 108)
        print("  [LOP 2A] PHAT HIEN & GAN NHAN OUTLIER GIA NANG LUONG (DUAL-METHOD CONSENSUS: MAD & IQR)")
        print("=" * 108)

        df_energy = con.execute("""
            SELECT
                calendar_date,
                brent_usd_per_bbl,
                ulsd_usd_per_gal,
                ulsd_usd_per_bbl,
                diesel_brent_crack_bbl,
                brent_diff_1d,
                brent_log_ret_1d,
                ulsd_diff_1d,
                ulsd_log_ret_1d,
                ROUND(diesel_brent_crack_bbl - LAG(diesel_brent_crack_bbl, 1) OVER (ORDER BY calendar_date), 4) AS crack_diff_1d,
                ROUND((brent_usd_per_bbl - LAG(brent_usd_per_bbl, 30) OVER (ORDER BY calendar_date))
                      * 100.0 / NULLIF(LAG(brent_usd_per_bbl, 30) OVER (ORDER BY calendar_date), 0), 2) AS brent_change_30d_pct,
                brent_is_ffill,
                ulsd_is_ffill
            FROM gold.fct_energy_prices_daily
            ORDER BY calendar_date
        """).fetchdf()

        # Tinh Rolling Modified Z-Score (MAD) va Rolling Tukey IQR tren cac phien giao dich thuc
        for prefix, col, ffill_col in [
            ("brent", "brent_log_ret_1d", "brent_is_ffill"),
            ("ulsd", "ulsd_log_ret_1d", "ulsd_is_ffill"),
            ("crack", "crack_diff_1d", "brent_is_ffill"),
        ]:
            df_energy[f"{prefix}_mod_z_63d"] = 0.0
            df_energy[f"{prefix}_iqr_exceed_63d"] = 0.0
            df_energy[f"is_{prefix}_mad_outlier"] = False
            df_energy[f"is_{prefix}_iqr_outlier"] = False
            df_energy[f"is_{prefix}_consensus_outlier"] = False
            df_energy[f"{prefix}_ts_label"] = "NONE"

            valid_mask = (~df_energy[ffill_col]) & df_energy[col].notna()
            sub_s = df_energy.loc[valid_mask, col]
            mod_z = compute_rolling_mad_zscore(sub_s, window=63, min_periods=20)
            iqr_flag, iqr_exc = compute_rolling_iqr_flags(sub_s, window=63, k=2.0, min_periods=20)
            mad_flag = mod_z.abs() > 3.5
            cons_flag = mad_flag & iqr_flag

            # Phan loai AO vs IO theo Chen & Liu (1993) / Charles & Darne (2005, 2014)
            next_s = sub_s.shift(-1)
            is_ao = cons_flag & ((sub_s * next_s) < 0) & (next_s.abs() >= 0.40 * sub_s.abs())
            ts_lbl = np.where(
                ~cons_flag,
                "NONE",
                np.where(
                    is_ao,
                    "AO (Additive Outlier - Mean-Reverting Spike)",
                    "IO (Innovational Outlier - Propagating Shock)",
                ),
            )

            df_energy.loc[valid_mask, f"{prefix}_mod_z_63d"] = mod_z.round(3)
            df_energy.loc[valid_mask, f"{prefix}_iqr_exceed_63d"] = iqr_exc.round(3)
            df_energy.loc[valid_mask, f"is_{prefix}_mad_outlier"] = mad_flag
            df_energy.loc[valid_mask, f"is_{prefix}_iqr_outlier"] = iqr_flag
            df_energy.loc[valid_mask, f"is_{prefix}_consensus_outlier"] = cons_flag
            df_energy.loc[valid_mask, f"{prefix}_ts_label"] = ts_lbl

            n_obs = int(valid_mask.sum())
            n_mad = int(mad_flag.sum())
            n_iqr = int(iqr_flag.sum())
            n_cons = int(cons_flag.sum())
            n_one = int((mad_flag ^ iqr_flag).sum())
            n_ao = int(is_ao.sum())
            n_io = n_cons - n_ao
            print(
                f"  * {col:<20} (N={n_obs:,} phien): MAD={n_mad:>2} | IQR={n_iqr:>2} | "
                f"CONSENSUS={n_cons:>2} ({n_cons*100/n_obs:.2f}%) [AO={n_ao:>2}, IO={n_io:>2}] | "
                f"Loai bo nhiễu (1 PP)={n_one:>2}"
            )

        df_energy["is_any_energy_consensus_outlier"] = (
            df_energy["is_brent_consensus_outlier"]
            | df_energy["is_ulsd_consensus_outlier"]
            | df_energy["is_crack_consensus_outlier"]
        )

        def assign_energy_labels(row: pd.Series) -> tuple[str, str]:
            if not row["is_any_energy_consensus_outlier"]:
                return ("NONE", "Normal Energy Market")
            # Uu tien nhan AO/IO cua bien co |ModZ| lon nhat
            candidates = [
                (abs(row["brent_mod_z_63d"]), row["brent_ts_label"], "brent", row["brent_log_ret_1d"]),
                (abs(row["ulsd_mod_z_63d"]), row["ulsd_ts_label"], "ulsd", row["ulsd_log_ret_1d"]),
                (abs(row["crack_mod_z_63d"]), row["crack_ts_label"], "crack", row["crack_diff_1d"]),
            ]
            # Chi xet cac bien dat consensus outlier
            active = []
            if row["is_brent_consensus_outlier"]:
                active.append(candidates[0])
            if row["is_ulsd_consensus_outlier"]:
                active.append(candidates[1])
            if row["is_crack_consensus_outlier"]:
                active.append(candidates[2])
            active.sort(key=lambda x: x[0], reverse=True)
            best_ts = active[0][1]

            if row["is_brent_consensus_outlier"] or row["is_ulsd_consensus_outlier"]:
                ret_val = (
                    row["brent_log_ret_1d"]
                    if row["is_brent_consensus_outlier"]
                    else row["ulsd_log_ret_1d"]
                )
                if ret_val > 0:
                    dom = "Positive Energy Price Shock (Supply / Geopolitical Surge)"
                else:
                    dom = "Negative Energy Price Shock (Demand / Market Correction Crash)"
            else:
                if row["crack_diff_1d"] > 0:
                    dom = "Refining Crack Spread Surge (Distillate Shortage / Squeeze)"
                else:
                    dom = "Refining Crack Spread Compression (Expiry / Mean Reversion)"
            return (best_ts, dom)

        e_labels = df_energy.apply(assign_energy_labels, axis=1, result_type="expand")
        df_energy["energy_ts_label"] = e_labels[0]
        df_energy["energy_domain_label"] = e_labels[1]

        # ===================================================================
        # 3. PHAT HIEN & GAN NHAN OUTLIER 28 DIEM NGHEN HANG HAI (LOP 2B & LOP 3)
        # ===================================================================
        print("\n" + "=" * 108)
        print("  [LOP 2B & LOP 3] PHAT HIEN & GAN NHAN 10 NHAN TU DONG (L00..L10) TREN 28 DIEM NGHEN")
        print("=" * 108)

        df_transit = con.execute("""
            SELECT
                t.observation_date,
                t.portid,
                t.portname,
                d.maritime_region,
                d.chokepoint_role,
                d.is_primary_oil_route,
                d.baseline_n_total,
                d.baseline_n_tanker,
                t.n_total,
                t.n_tanker,
                t.capacity,
                t.capacity_tanker,
                t.n_total_ma7,
                t.n_tanker_ma7,
                t.n_total_diff_1d,
                t.n_total_diff_7d,
                t.n_tanker_diff_7d,
                t.pct_vs_baseline_total,
                t.pct_vs_baseline_tanker,
                t.n_total_zscore_90d,
                t.n_tanker_zscore_90d,
                t.active_event_id,
                t.regime_type
            FROM gold.fct_chokepoint_transit_daily t
            JOIN gold.dim_chokepoints d USING (portid)
            ORDER BY t.portid, t.observation_date
        """).fetchdf()

        port_dfs = []
        for pid, grp in df_transit.groupby("portid", sort=False):
            g = grp.copy()

            # 1. Cap do Cu soc Ngan han I(0) tren n_total_diff_7d (Cua so truot 90 ngay)
            g["shock_mod_z_90d"] = compute_rolling_mad_zscore(
                g["n_total_diff_7d"], window=90, min_periods=30
            ).round(3)
            shock_iqr_flag, shock_iqr_exc = compute_rolling_iqr_flags(
                g["n_total_diff_7d"], window=90, k=2.0, min_periods=30
            )
            g["shock_iqr_exceed_90d"] = shock_iqr_exc.round(3)
            g["is_shock_mad_outlier"] = g["shock_mod_z_90d"].abs() > 3.5
            g["is_shock_iqr_outlier"] = shock_iqr_flag
            g["is_shock_consensus_outlier"] = g["is_shock_mad_outlier"] & g["is_shock_iqr_outlier"]

            # 2. Cap do Dut gay Cau truc (MA7 so voi phan phoi Baseline 2021-2022)
            base_mask = g["observation_date"] < pd.Timestamp("2023-01-01")
            base_series = g.loc[base_mask, "n_total_ma7"].dropna()
            base_med = base_series.median()
            base_mad = max((base_series - base_med).abs().median(), 1e-6)
            base_q25 = base_series.quantile(0.25)
            base_q75 = base_series.quantile(0.75)
            base_iqr = max(base_q75 - base_q25, 1e-6)

            g["struct_mod_z_base"] = (0.6745 * (g["n_total_ma7"] - base_med) / base_mad).round(3)
            g["is_struct_mad_outlier"] = g["struct_mod_z_base"].abs() > 3.5
            lower_b = base_q25 - 2.0 * base_iqr
            upper_b = base_q75 + 2.0 * base_iqr
            g["is_struct_iqr_outlier"] = (g["n_total_ma7"] < lower_b) | (g["n_total_ma7"] > upper_b)
            struct_exc = np.where(
                g["n_total_ma7"] > upper_b,
                (g["n_total_ma7"] - upper_b) / base_iqr,
                np.where(g["n_total_ma7"] < lower_b, (g["n_total_ma7"] - lower_b) / base_iqr, 0.0),
            )
            g["struct_iqr_exceed_base"] = np.round(struct_exc, 3)
            g["is_struct_consensus_outlier"] = g["is_struct_mad_outlier"] & g["is_struct_iqr_outlier"]

            # 3. Tong hop Consensus Outlier & Do dai chuoi ngay lien tiep (Contiguous Run Length)
            g["is_chokepoint_consensus_outlier"] = (
                g["is_shock_consensus_outlier"] | g["is_struct_consensus_outlier"]
            )
            g["consensus_run_days"] = compute_contiguous_run_lengths(
                g["is_chokepoint_consensus_outlier"]
            )

            # 4. Cac co kiem tra tin hieu AIS / Telemetry (Lop 1)
            g["is_ais_dwt_reporting_anomaly"] = (g["n_total"] > 0) & (g["capacity"] == 0)
            same_as_prev = (g["n_total_diff_1d"] == 0) & (g["baseline_n_total"] >= 20.0) & (g["n_total"] > 0)
            flat_run = compute_contiguous_run_lengths(same_as_prev)
            g["is_flatline_telemetry_anomaly"] = flat_run >= 5

            # Lag 14d cua struct_mod_z_base va Lead 1d/2d cua n_total de phat hien Typhoon AO va Route Normalization
            g["lag14_struct_mod_z"] = g["struct_mod_z_base"].shift(14).fillna(0.0)
            g["next_day_n_total"] = g["n_total"].shift(-1).fillna(g["n_total"])
            g["next2_day_n_total"] = g["n_total"].shift(-2).fillna(g["n_total"])

            port_dfs.append(g)

        df_all = pd.concat(port_dfs, ignore_index=True)

        # Tinh chi so boi canh toan mang luoi theo tung ngay (Cross-Chokepoint Context)
        daily_corridor_stress = (
            df_all[df_all["chokepoint_role"] == "Global Transit Corridor"]
            .groupby("observation_date")["struct_mod_z_base"]
            .apply(lambda s: int((s < -3.0).sum()))
            .rename("n_corridors_depressed")
        )
        cape_daily_z = (
            df_all[df_all["portname"] == "Cape of Good Hope"]
            .set_index("observation_date")["struct_mod_z_base"]
            .rename("cape_struct_mod_z")
        )

        df_all = df_all.merge(daily_corridor_stress, on="observation_date", how="left")
        df_all = df_all.merge(cape_daily_z, on="observation_date", how="left")
        df_all = df_all.merge(
            df_energy[
                [
                    "calendar_date",
                    "brent_usd_per_bbl",
                    "ulsd_usd_per_gal",
                    "ulsd_usd_per_bbl",
                    "diesel_brent_crack_bbl",
                    "brent_log_ret_1d",
                    "ulsd_log_ret_1d",
                    "crack_diff_1d",
                    "brent_change_30d_pct",
                    "brent_mod_z_63d",
                    "brent_iqr_exceed_63d",
                    "is_brent_consensus_outlier",
                    "ulsd_mod_z_63d",
                    "ulsd_iqr_exceed_63d",
                    "is_ulsd_consensus_outlier",
                    "crack_mod_z_63d",
                    "crack_iqr_exceed_63d",
                    "is_crack_consensus_outlier",
                    "is_any_energy_consensus_outlier",
                    "energy_ts_label",
                    "energy_domain_label",
                ]
            ],
            left_on="observation_date",
            right_on="calendar_date",
            how="left",
        ).drop(columns=["calendar_date"])

        # ===================================================================
        # 4. GAN NHAN TU DONG 100% KHONG PHU THUOC EVENT_ID TINH (L00..L10)
        # ===================================================================
        def assign_chokepoint_taxonomy(row: pd.Series) -> tuple[str, str, str, str]:
            """
            Tra ve 4 truong nhan:
              (chokepoint_label_code, chokepoint_ts_label, chokepoint_acm_label, chokepoint_domain_label)
            Hoan toan dua tren dau hieu toan hoc da bien (Zero-Touch Future-Proof).
            """
            is_cons = bool(row["is_chokepoint_consensus_outlier"])
            is_shock = bool(row["is_shock_consensus_outlier"])
            is_struct = bool(row["is_struct_consensus_outlier"])
            run_days = int(row["consensus_run_days"])
            role = row["chokepoint_role"]
            s_z = float(row["struct_mod_z_base"])
            sh_z = float(row["shock_mod_z_90d"])
            pct_base = float(row["pct_vs_baseline_total"])
            brent_30d = float(row["brent_change_30d_pct"]) if pd.notna(row["brent_change_30d_pct"]) else 0.0

            # Neu khong phai Consensus Outlier nhung vi pham AIS DWT hoac Flatline -> L10
            if not is_cons:
                if row["is_ais_dwt_reporting_anomaly"] or row["is_flatline_telemetry_anomaly"]:
                    return (
                        "L10",
                        "DATA_ANOMALY",
                        "Data-Level Reporting Anomaly",
                        "L10: Telemetry Glitch / AIS Missing DWT / Flatline",
                    )
                return ("L00", "NONE", "Normal Observation", "L00: Normal Maritime Flow")

            # L08: Environmental Typhoon / Severe Weather 24-48h Closure (AO - Additive Outlier)
            # Luu luong roi ve <= 2 tau (giam >= 95% so voi baseline) trong ngan han va bat tang ngay sau do
            if (
                row["n_total"] <= 2
                and pct_base <= -95.0
                and not is_struct
                and (row["next_day_n_total"] >= 15 or row["next2_day_n_total"] >= 30)
            ):
                return (
                    "L08",
                    "AO (Additive Outlier)",
                    "Point Anomaly",
                    "L08: Environmental Typhoon / Severe Weather Closure",
                )

            # L05: Post-Crisis Route Normalization (Phuc hoi kenh chinh hoac giam tai tuyen vong)
            if is_shock and (
                (role == "Global Transit Corridor" and row["lag14_struct_mod_z"] < -3.5 and sh_z > 3.5)
                or (role == "Rerouting Alternative" and row["lag14_struct_mod_z"] > 3.5 and sh_z < -3.5)
            ):
                return (
                    "L05",
                    "TC (Temporary Change)",
                    "Collective (Subsequence) Anomaly",
                    "L05: Post-Crisis Route Normalization Transition",
                )

            # L07: Acute Operational Blockage (Su co tac nghen van hanh ngan han 3-14 ngay kieu Ever Given)
            if (
                role in ("Global Transit Corridor", "Origin Energy Export Hub")
                and (s_z < -3.5 or sh_z < -3.5)
                and pct_base <= -35.0
                and 1 <= run_days <= 14
            ):
                return (
                    "L07",
                    "TC (Temporary Change)",
                    "Collective (Subsequence) Anomaly",
                    "L07: Acute Operational Blockage (Short-Term Canal Halt)",
                )

            # Xet cac dot dich chuyen muc nen keo dai (LS - Level Shift, is_struct == True va run_days > 14 hoac struct_consensus)
            if is_struct:
                # L02: Macro Demand Collapse / Recession Shock (Nhieu hanh lang cung suy giam + Gia dau giam sau)
                if row["n_corridors_depressed"] >= 3 and s_z < -3.5 and brent_30d <= -15.0:
                    return (
                        "L02",
                        "LS (Level Shift)",
                        "Collective (Subsequence) Anomaly",
                        "L02: Macro Demand Collapse / Recession Shock",
                    )

                # L01: Supply Shock Blockade tai Origin Energy Export Hub (Hormuz, Bosporus...)
                if role == "Origin Energy Export Hub" and s_z < -3.5:
                    return (
                        "L01",
                        "LS (Level Shift)",
                        "Collective (Subsequence) Anomaly",
                        "L01: Origin Energy Export Hub Blockade / Supply Shock",
                    )

                # L03: Sustained Corridor Restriction & Rerouting tai Global Transit Corridor (Bab el-Mandeb, Suez, Panama)
                if role == "Global Transit Corridor" and s_z < -3.5:
                    return (
                        "L03",
                        "LS (Level Shift)",
                        "Collective (Subsequence) Anomaly",
                        "L03: Sustained Corridor Restriction (Geopolitical / Climate)",
                    )

                # L04: Spatial Rerouting Surge tai Rerouting Alternative (Cape of Good Hope, Sunda)
                if role == "Rerouting Alternative" and s_z > 3.5:
                    return (
                        "L04",
                        "LS (Level Shift)",
                        "Collective (Subsequence) Anomaly",
                        "L04: Spatial Rerouting Surge (Detour Absorption)",
                    )

                # L06: Pre-Sanction / Tariff Front-Loading Surge (Origin Hub hoac Global Corridor tang vot kem gia dau tang)
                if role in ("Origin Energy Export Hub", "Global Transit Corridor") and s_z > 3.5 and brent_30d >= 5.0:
                    return (
                        "L06",
                        "TC (Temporary Change)",
                        "Contextual Anomaly",
                        "L06: Pre-Sanction / Front-Loading Transit Surge",
                    )

                # Con lai: Regional Trade Volume Shift
                return (
                    "L09",
                    "LS (Level Shift)",
                    "Contextual / Collective Anomaly",
                    "L09: Regional Trade Volume Shift / Seasonal Regime",
                )

            # Neu chi la Shock ngan han I(0) (is_shock == True, is_struct == False)
            if role == "Origin Energy Export Hub" and sh_z < -3.5:
                return (
                    "L01",
                    "IO (Innovational Outlier)",
                    "Contextual Anomaly",
                    "L01: Origin Energy Export Hub Acute Disruption Shock",
                )

            return (
                "L09",
                "IO (Innovational Outlier)",
                "Contextual Anomaly",
                "L09: Short-Term Weather / Convoy Bunching Shock",
            )

        tax_df = df_all.apply(assign_chokepoint_taxonomy, axis=1, result_type="expand")
        df_all["chokepoint_label_code"] = tax_df[0]
        df_all["chokepoint_ts_label"] = tax_df[1]
        df_all["chokepoint_acm_label"] = tax_df[2]
        df_all["chokepoint_domain_label"] = tax_df[3]

        # Bo cac cot tam truoc khi luu vao DuckDB & Parquet
        drop_cols = ["lag14_struct_mod_z", "next_day_n_total", "next2_day_n_total"]
        df_mart = df_all.drop(columns=drop_cols).sort_values(["portid", "observation_date"]).reset_index(drop=True)

        # Luu thanh bang BI Mart trong DuckDB schema `gold` va xuat Parquet
        con.register("df_mart_view", df_mart)
        con.execute("""
            CREATE OR REPLACE TABLE gold.mart_outlier_consensus_labeled_daily AS
            SELECT * FROM df_mart_view
            ORDER BY portid, observation_date;
        """)
        con.execute(f"""
            COPY gold.mart_outlier_consensus_labeled_daily
            TO '{OUT_MART_OUTLIER_PARQUET.as_posix()}' (FORMAT PARQUET, COMPRESSION SNAPPY);
        """)

        # In thong ke tong hop cac nhan L00..L10
        summary_labels = (
            df_mart.groupby(
                ["chokepoint_label_code", "chokepoint_ts_label", "chokepoint_acm_label", "chokepoint_domain_label"],
                as_index=False,
            )
            .agg(
                port_days=("observation_date", "count"),
                unique_ports=("portname", "nunique"),
                avg_pct_vs_base=("pct_vs_baseline_total", "mean"),
                min_shock_modz=("shock_mod_z_90d", "min"),
                max_struct_modz=("struct_mod_z_base", "max"),
            )
            .sort_values("chokepoint_label_code")
        )
        print(summary_labels.to_string(index=False))

        size_kb = OUT_MART_OUTLIER_PARQUET.stat().st_size / 1024
        print("\n" + "=" * 108)
        print(
            f"  DA TAO BI MART: gold.mart_outlier_consensus_labeled_daily "
            f"({len(df_mart):,} dong x {df_mart.shape[1]} cot | {size_kb:,.1f} KB)"
        )
        print("=" * 108)

    finally:
        con.close()


if __name__ == "__main__":
    build_and_evaluate_outlier_mart()
