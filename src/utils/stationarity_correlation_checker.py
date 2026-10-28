"""
stationarity_correlation_checker.py
-----------------------------------
Kiem dinh Tinh Dung (Stationarity: ADF & KPSS) va Phan tich Tuong quan (Correlation,
Regime-Switching, Rerouting Matrix & Granger Causality) giua Gia Nang Luong (U.S. EIA)
va Luu luong / Trong tai qua 28 Diem Nghen Hang Hai (IMF PortWatch).

Nguon du lieu dau vao:
  - data/processed/maritime_energy_daily_joined.parquet   (59,276 dong = 28 chokepoints x 2,117 ngay)
  - data/seeds/geopolitical_events.csv                    (4 su kien dia chinh tri & khi hau)

Cac hang muc kiem dinh:
  [1] STATIONARITY - ENERGY PRICES   : ADF & KPSS tren chuoi goc I(1), sai phan bac 1, log-return va Crack Spread.
  [2] STATIONARITY - 28 CHOKEPOINTS  : ADF & KPSS tren chuoi goc va sai phan bac 1 cua n_total, n_tanker, capacity.
  [3] CORRELATION - BRENT vs ULSD    : Pearson r, Spearman rho, t-stat tren Level, Diff 1d, Log-Return 1d, Diff 7d.
  [4] CORRELATION - OIL vs CHOKEPOINT: So sanh tuong quan tren Chuoi Goc (Level) vs Chuoi Dung (Delta_7 MA7).
  [5] GEOPOLITICAL REGIME ANALYSIS   : Bien dong luu luong, gia dau va tuong quan trong 4 su kien (EVT_01..EVT_04).
  [6] MARITIME REROUTING MATRIX      : Ma tran tuong quan doi tuyen Suez / Bab el-Mandeb <-> Cape of Good Hope.
  [7] GRANGER CAUSALITY & LEAD-LAG   : Kiem dinh nhan qua Granger F-test (do tre 7 ngay) tren chuoi dung.

Chay:
  venv\\Scripts\\python.exe -m src.utils.stationarity_correlation_checker
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
JOINED_PARQUET = PROJECT_ROOT / "data" / "processed" / "maritime_energy_daily_joined.parquet"
EVENTS_CSV = PROJECT_ROOT / "data" / "seeds" / "geopolitical_events.csv"

WIDTH = 108


def sep(char: str = "-", width: int = WIDTH) -> str:
    return char * width


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Cac ham Kiem dinh Kinh te luong (Econometric Tests)
# ---------------------------------------------------------------------------
def adf_test(series: pd.Series, max_lags: int | None = None) -> dict:
    """
    Kiem dinh Augmented Dickey-Fuller (ADF) co hang so ('c'):
      Delta y_t = alpha + beta * y_{t-1} + sum_{i=1}^p gamma_i * Delta y_{t-i} + e_t
    Chon bac tre p toi uu theo tieu chuan AIC.
    Gia tri toi han MacKinnon (2010): 1% = -3.434, 5% = -2.863, 10% = -2.568.
    """
    y = series.dropna().to_numpy(dtype=float)
    n = len(y)
    if max_lags is None:
        max_lags = int(np.ceil(12.0 * ((n / 100.0) ** 0.25)))

    dy = np.diff(y)
    best_aic = np.inf
    best_res = None

    for p in range(0, max_lags + 1):
        dep = dy[p:]
        t_eff = len(dep)
        if t_eff <= p + 5:
            break
        cols = [np.ones(t_eff), y[p : n - 1]]
        for lag in range(1, p + 1):
            cols.append(dy[p - lag : n - 1 - lag])
        X = np.column_stack(cols)
        beta, _, _, _ = np.linalg.lstsq(X, dep, rcond=None)
        resid = dep - X @ beta
        ssr = float(np.sum(resid ** 2))
        sigma2 = ssr / t_eff
        k = X.shape[1]
        aic = np.log(sigma2) + 2.0 * k / t_eff

        if aic < best_aic:
            s2_unbiased = ssr / (t_eff - k)
            cov = s2_unbiased * np.linalg.inv(X.T @ X)
            se_beta = float(np.sqrt(cov[1, 1]))
            t_stat = float(beta[1] / se_beta)
            best_aic = aic
            best_res = {
                "adf_stat": round(t_stat, 4),
                "lag": p,
                "n_obs": t_eff,
                "stationary_5pct": bool(t_stat < -2.863),
                "stationary_1pct": bool(t_stat < -3.434),
            }
    return best_res


def kpss_test(series: pd.Series) -> dict:
    """
    Kiem dinh KPSS (Kwiatkowski-Phillips-Schmidt-Shin, 1992) voi hang so ('c'):
      H0: Chuoi DUNG quanh trung binh (Level Stationary)
      H1: Chuoi co Unit Root / Structural Drift
    Gia tri toi han KPSS (1992): 10% = 0.347, 5% = 0.463, 1% = 0.739.
    """
    y = series.dropna().to_numpy(dtype=float)
    n = len(y)
    resid = y - np.mean(y)
    s_t = np.cumsum(resid)
    eta = float(np.sum(s_t ** 2) / (n ** 2))

    lags = int(np.ceil(4.0 * ((n / 100.0) ** 0.25)))
    gamma_0 = float(np.sum(resid ** 2) / n)
    s2 = gamma_0
    for l in range(1, lags + 1):
        w = 1.0 - l / (lags + 1.0)
        gamma_l = float(np.sum(resid[l:] * resid[:-l]) / n)
        s2 += 2.0 * w * gamma_l

    kpss_stat = eta / s2 if s2 > 0 else np.nan
    return {
        "kpss_stat": round(float(kpss_stat), 4),
        "lags": lags,
        "stationary_5pct": bool(kpss_stat < 0.463),
    }


def corr_stats(x: pd.Series, y: pd.Series) -> dict:
    df_xy = pd.DataFrame({"x": x, "y": y}).dropna()
    n = len(df_xy)
    if n < 10:
        return {"n": n, "pearson_r": np.nan, "spearman_rho": np.nan, "t_stat": np.nan, "p_val": np.nan}
    r = float(df_xy["x"].corr(df_xy["y"], method="pearson"))
    rho = float(df_xy["x"].rank().corr(df_xy["y"].rank(), method="pearson"))
    if abs(r) >= 1.0:
        t_stat = np.inf
        p_val = 0.0
    else:
        t_stat = r * math.sqrt((n - 2) / (1.0 - r * r))
        p_val = 2.0 * (1.0 - normal_cdf(abs(t_stat)))
    return {
        "n": n,
        "pearson_r": round(r, 4),
        "spearman_rho": round(rho, 4),
        "t_stat": round(t_stat, 2),
        "p_val": round(p_val, 6),
    }


def granger_f_test(y_target: pd.Series, x_cause: pd.Series, max_lag: int = 7) -> dict:
    """
    Kiem dinh Nhan qua Granger (Granger Causality F-test) tren chuoi da dung:
      H0: x_cause KHONG Granger-cause y_target voi do tre 1..max_lag.
      Nguong F(7, inf): 10% = 1.72, 5% = 2.01, 1% = 2.64.
    """
    df_yx = pd.DataFrame({"y": y_target, "x": x_cause}).dropna()
    y = df_yx["y"].to_numpy(dtype=float)
    x = df_yx["x"].to_numpy(dtype=float)
    n = len(y)
    t_eff = n - max_lag

    Y = y[max_lag:]
    X_r = np.column_stack([np.ones(t_eff)] + [y[max_lag - k : n - k] for k in range(1, max_lag + 1)])
    beta_r, _, _, _ = np.linalg.lstsq(X_r, Y, rcond=None)
    rss_r = float(np.sum((Y - X_r @ beta_r) ** 2))

    X_u = np.column_stack([X_r] + [x[max_lag - k : n - k] for k in range(1, max_lag + 1)])
    beta_u, _, _, _ = np.linalg.lstsq(X_u, Y, rcond=None)
    rss_u = float(np.sum((Y - X_u @ beta_u) ** 2))

    df_num = max_lag
    df_den = t_eff - X_u.shape[1]
    f_stat = ((rss_r - rss_u) / df_num) / (rss_u / df_den)
    return {
        "lags": max_lag,
        "f_stat": round(float(f_stat), 3),
        "sig_10pct": bool(f_stat > 1.72),
        "sig_5pct": bool(f_stat > 2.01),
        "sig_1pct": bool(f_stat > 2.64),
    }


# ---------------------------------------------------------------------------
# Cac ham in bao cao
# ---------------------------------------------------------------------------
def run_stationarity_energy(energy: pd.DataFrame) -> None:
    print("\n  [1] KIEM DINH TINH DUNG - CHUOI GIA NANG LUONG (ADF crit 5% = -2.863 | KPSS crit 5% = 0.463)")
    print("  " + sep())
    print(
        f"  {'Chuoi du lieu':<32} {'Mean':>9} {'Std':>8} {'Min':>9} {'Max':>9} "
        f"{'ADF Stat':>10} {'Lag':>4} {'KPSS Stat':>10}  Ket luan (5%)"
    )
    print("  " + sep())

    items = [
        ("Brent Crude ($/BBL) - Level", energy["brent_usd_per_bbl"]),
        ("Brent Crude - Diff 1d", energy["brent_diff"]),
        ("Brent Crude - Log-Return (%)", energy["brent_log_ret"]),
        ("ULSD Diesel ($/GAL) - Level", energy["ulsd_usd_per_gal"]),
        ("ULSD Diesel - Diff 1d", energy["ulsd_diff"]),
        ("ULSD Diesel - Log-Return (%)", energy["ulsd_log_ret"]),
        ("Diesel-Brent Crack ($/BBL)", energy["diesel_brent_crack_bbl"]),
        ("Diesel-Brent Crack - Diff 1d", energy["diesel_brent_crack_bbl"].diff()),
    ]
    for label, s in items:
        adf = adf_test(s)
        kpss = kpss_test(s)
        is_stat = adf["stationary_5pct"] and kpss["stationary_5pct"]
        verdict = "DUNG - I(0)" if is_stat else "KHONG DUNG - I(1)"
        print(
            f"  {label:<32} {s.mean():>9.3f} {s.std():>8.3f} {s.min():>9.3f} {s.max():>9.3f} "
            f"{adf['adf_stat']:>10.4f} {adf['lag']:>4} {kpss['kpss_stat']:>10.4f}  {verdict}"
        )


def run_stationarity_chokepoints(df: pd.DataFrame) -> None:
    print("\n  [2] KIEM DINH TINH DUNG - 28 DIEM NGHEN HANG HAI (CHUOI GOC vs SAI PHAN BAC 1)")
    print("  " + sep())
    print(
        f"  {'Port ID':<13} {'Ten Diem Nghen':<24} "
        f"{'n_total ADF':>11} {'n_total KPSS':>12} {'n_tanker ADF':>12} {'n_tanker KPSS':>13} "
        f"{'Diff1 ADF':>10} {'Diff1 KPSS':>10}  Ket luan Goc -> Diff1"
    )
    print("  " + sep())

    def port_sort_key(item):
        pid = item[0][0]
        digits = "".join(ch for ch in str(pid) if ch.isdigit())
        return int(digits) if digits else 0

    grouped = sorted(df.sort_values("observation_date").groupby(["portid", "portname"]), key=port_sort_key)
    stat_lvl_count = 0
    stat_diff_count = 0

    for (portid, portname), grp in grouped:
        s_tot = grp.set_index("observation_date")["n_total"]
        s_tk = grp.set_index("observation_date")["n_tanker"]
        adf_tot = adf_test(s_tot)
        kpss_tot = kpss_test(s_tot)
        adf_tk = adf_test(s_tk)
        kpss_tk = kpss_test(s_tk)
        adf_d1 = adf_test(s_tk.diff())
        kpss_d1 = kpss_test(s_tk.diff())

        lvl_ok = adf_tk["stationary_5pct"] and kpss_tk["stationary_5pct"]
        diff_ok = adf_d1["stationary_5pct"] and kpss_d1["stationary_5pct"]
        if lvl_ok:
            stat_lvl_count += 1
        if diff_ok:
            stat_diff_count += 1

        verdict = f"{'I(0)' if lvl_ok else 'I(1)'} -> {'I(0)' if diff_ok else 'I(1)'}"
        print(
            f"  {portid:<13} {portname[:23]:<24} "
            f"{adf_tot['adf_stat']:>11.4f} {kpss_tot['kpss_stat']:>12.4f} "
            f"{adf_tk['adf_stat']:>12.4f} {kpss_tk['kpss_stat']:>13.4f} "
            f"{adf_d1['adf_stat']:>10.4f} {kpss_d1['kpss_stat']:>10.4f}  {verdict}"
        )

    print("  " + sep())
    print(
        f"  Tong ket n_tanker: Chuoi goc dung = {stat_lvl_count}/28 diem nghen | "
        f"Sai phan bac 1 dung = {stat_diff_count}/28 diem nghen (100%)"
    )


def run_brent_ulsd_correlation(energy: pd.DataFrame) -> None:
    print("\n  [3] TUONG QUAN NOI TAI GIUA DAU THO BRENT (EUROPE) VA DIESEL ULSD (U.S. GULF COAST)")
    print("  " + sep())
    print(f"  {'Cap do bien doi':<38} {'N':>6} {'Pearson r':>11} {'Spearman rho':>13} {'t-stat':>9} {'p-value':>10}")
    print("  " + sep())

    pairs = [
        ("Chuoi goc (Level - I(1))", energy["brent_usd_per_bbl"], energy["ulsd_usd_per_gal"]),
        ("Sai phan 1 ngay (Diff 1d - I(0))", energy["brent_diff"], energy["ulsd_diff"]),
        ("Log-Return 1 ngay (I(0))", energy["brent_log_ret"], energy["ulsd_log_ret"]),
        ("Bien dong 7 ngay (Diff 7d - I(0))", energy["brent_usd_per_bbl"].diff(7), energy["ulsd_usd_per_gal"].diff(7)),
    ]
    for label, x, y in pairs:
        c = corr_stats(x, y)
        print(
            f"  {label:<38} {c['n']:>6,} {c['pearson_r']:>+11.4f} "
            f"{c['spearman_rho']:>+13.4f} {c['t_stat']:>+9.2f} {c['p_val']:>10.6f}"
        )


def run_chokepoint_oil_correlations(df: pd.DataFrame) -> None:
    print("\n  [4] TUONG QUAN GIA DAU VA LUU LUONG 28 CHOKEPOINTS (CHUOI GOC LEVEL vs CHUOI DUNG DELTA_7 MA7)")
    print("  " + sep())
    print(
        f"  {'Port ID':<13} {'Ten Diem Nghen':<24} {'TB Tau':>7} {'TB Tanker':>9} "
        f"{'r(Brent,Tot)':>13} {'r(Brent,Tkr)':>13} {'r(ULSD,Tot)':>12} {'r(ULSD,Tkr)':>12} {'r_Diff7(B,Tkr)':>15}"
    )
    print("  " + sep())

    rows = []
    for (portid, portname), grp in df.sort_values("observation_date").groupby(["portid", "portname"]):
        g = grp.set_index("observation_date")
        r_b_tot = corr_stats(g["n_total"], g["brent_usd_per_bbl"])["pearson_r"]
        r_b_tk = corr_stats(g["n_tanker"], g["brent_usd_per_bbl"])["pearson_r"]
        r_u_tot = corr_stats(g["n_total"], g["ulsd_usd_per_gal"])["pearson_r"]
        r_u_tk = corr_stats(g["n_tanker"], g["ulsd_usd_per_gal"])["pearson_r"]

        tk_d7 = g["n_tanker"].rolling(7).mean().diff(7)
        b_d7 = g["brent_usd_per_bbl"].rolling(7).mean().diff(7)
        r_d7 = corr_stats(tk_d7, b_d7)["pearson_r"]

        rows.append({
            "portid": portid,
            "portname": portname,
            "mean_tot": g["n_total"].mean(),
            "mean_tk": g["n_tanker"].mean(),
            "r_b_tot": r_b_tot,
            "r_b_tk": r_b_tk,
            "r_u_tot": r_u_tot,
            "r_u_tk": r_u_tk,
            "r_d7": r_d7,
        })

    rows.sort(key=lambda x: x["r_u_tot"])
    for r in rows:
        print(
            f"  {r['portid']:<13} {r['portname'][:23]:<24} {r['mean_tot']:>7.1f} {r['mean_tk']:>9.1f} "
            f"{r['r_b_tot']:>+13.4f} {r['r_b_tk']:>+13.4f} {r['r_u_tot']:>+12.4f} "
            f"{r['r_u_tk']:>+12.4f} {r['r_d7']:>+15.4f}"
        )


def run_regime_analysis(df: pd.DataFrame) -> None:
    print("\n  [5] PHAN TICH THEO CHE DO SU KIEN DIA CHINH TRI (GEOPOLITICAL REGIME ANALYSIS)")
    print("  " + sep())
    if not EVENTS_CSV.exists():
        print("  Khong tim thay file geopolitical_events.csv")
        return

    events = pd.read_csv(EVENTS_CSV)
    print(
        f"  {'ID':<7} {'Su kien':<34} {'Chokepoint':<21} {'So ngay':>7} "
        f"{'Delta Tanker':>13} {'Delta Brent':>12} {'r(Tkr,Brent)':>13}"
    )
    print("  " + sep())

    for _, ev in events.iterrows():
        p_name = ev["primary_chokepoint"]
        s_date = pd.to_datetime(ev["start_date"])
        e_date = pd.to_datetime(ev["end_date"])
        sub = df[df["portname"] == p_name].sort_values("observation_date")
        during = sub[(sub["observation_date"] >= s_date) & (sub["observation_date"] <= e_date)]
        before = sub[
            (sub["observation_date"] < s_date)
            & (sub["observation_date"] >= s_date - pd.Timedelta(days=180))
        ]
        if len(before) < 10:
            before = sub[sub["observation_date"] < s_date]

        d_tk = (during["n_tanker"].mean() - before["n_tanker"].mean()) / before["n_tanker"].mean() * 100.0
        d_br = (
            (during["brent_usd_per_bbl"].mean() - before["brent_usd_per_bbl"].mean())
            / before["brent_usd_per_bbl"].mean()
            * 100.0
        )
        r_ev = corr_stats(during["n_tanker"], during["brent_usd_per_bbl"])["pearson_r"]
        r_str = f"{r_ev:+.4f}" if not np.isnan(r_ev) else "N/A (<10d)"
        print(
            f"  {ev['event_id']:<7} {ev['event_name'][:33]:<34} {p_name[:20]:<21} {len(during):>7,} "
            f"{d_tk:>+12.1f}% {d_br:>+11.1f}% {r_str:>13}"
        )


def run_rerouting_matrix(df: pd.DataFrame) -> None:
    print("\n  [6] MA TRAN TUONG QUAN DOI TUYEN HANG HAI (SUEZ / BAB EL-MANDEB <-> CAPE OF GOOD HOPE)")
    print("  " + sep())
    print(f"  {'Cap Diem Nghen':<48} {'Bien so':<12} {'Pearson r':>11} {'Spearman rho':>13} {'t-stat':>9}")
    print("  " + sep())

    piv_tot = df.pivot(index="observation_date", columns="portname", values="n_total")
    piv_tk = df.pivot(index="observation_date", columns="portname", values="n_tanker")

    pairs = [
        ("Suez Canal <-> Bab el-Mandeb Strait", "n_total", piv_tot["Suez Canal"], piv_tot["Bab el-Mandeb Strait"]),
        ("Bab el-Mandeb Strait <-> Cape of Good Hope", "n_total", piv_tot["Bab el-Mandeb Strait"], piv_tot["Cape of Good Hope"]),
        ("Suez Canal <-> Cape of Good Hope", "n_total", piv_tot["Suez Canal"], piv_tot["Cape of Good Hope"]),
        ("Bab el-Mandeb Strait <-> Cape of Good Hope", "n_tanker", piv_tk["Bab el-Mandeb Strait"], piv_tk["Cape of Good Hope"]),
        ("Suez Canal <-> Cape of Good Hope", "n_tanker", piv_tk["Suez Canal"], piv_tk["Cape of Good Hope"]),
    ]
    for label, var, x, y in pairs:
        c = corr_stats(x, y)
        print(f"  {label:<48} {var:<12} {c['pearson_r']:>+11.4f} {c['spearman_rho']:>+13.4f} {c['t_stat']:>+9.2f}")


def run_granger_causality(df: pd.DataFrame) -> None:
    print("\n  [7] KIEM DINH NHAN QUA GRANGER TREN CHUOI DUNG (LAG = 7 NGAY | F crit 5% = 2.01, 10% = 1.72)")
    print("  " + sep())
    print(
        f"  {'Diem Nghen':<24} {'F(Flow -> Brent)':>17} {'F(Tanker -> Brent)':>19} "
        f"{'F(Tanker -> ULSD)':>18} {'F(Brent -> Flow)':>17}  Ket luan"
    )
    print("  " + sep())

    key_ports = [
        "Strait of Hormuz",
        "Bab el-Mandeb Strait",
        "Suez Canal",
        "Cape of Good Hope",
        "Bosporus Strait",
        "Malacca Strait",
        "Panama Canal",
        "Gibraltar Strait",
    ]
    for pname in key_ports:
        g = df[df["portname"] == pname].sort_values("observation_date").set_index("observation_date")
        x_flow = g["n_total"].rolling(7).mean().diff(1)
        x_tk = g["n_tanker"].rolling(7).mean().diff(1)
        y_brent = g["brent_usd_per_bbl"].diff(1)
        y_ulsd = g["ulsd_usd_per_gal"].diff(1)

        f1 = granger_f_test(y_brent, x_flow, 7)
        f2 = granger_f_test(y_brent, x_tk, 7)
        f3 = granger_f_test(y_ulsd, x_tk, 7)
        f4 = granger_f_test(x_flow, y_brent, 7)

        notes = []
        if f1["sig_5pct"]:
            notes.append("Flow->Brent (5%)")
        elif f1["sig_10pct"]:
            notes.append("Flow->Brent (10%)")
        if f3["sig_5pct"]:
            notes.append("Tanker->ULSD (5%)")
        verdict = ", ".join(notes) if notes else "Khong co nhan qua tuyen tinh ngan han"

        print(
            f"  {pname:<24} {f1['f_stat']:>17.3f} {f2['f_stat']:>19.3f} "
            f"{f3['f_stat']:>18.3f} {f4['f_stat']:>17.3f}  {verdict}"
        )


def main() -> None:
    print(sep("="))
    print("  STATIONARITY & CORRELATION CHECKER - Maritime Energy Supply Chain Monitor")
    print(sep("="))

    if not JOINED_PARQUET.exists():
        print(f"  [ERROR] Khong tim thay file: {JOINED_PARQUET}")
        print("          Hay chay `python -m src.process.process_data` truoc.")
        sys.exit(1)

    df = pd.read_parquet(JOINED_PARQUET)
    df["observation_date"] = pd.to_datetime(df["observation_date"])
    print(f"  Du lieu dau vao : {JOINED_PARQUET.name} ({len(df):,} dong | {df['portid'].nunique()} chokepoints)")

    energy = (
        df[["observation_date", "brent_usd_per_bbl", "ulsd_usd_per_gal"]]
        .drop_duplicates(subset=["observation_date"])
        .sort_values("observation_date")
        .set_index("observation_date")
    )
    energy["brent_diff"] = energy["brent_usd_per_bbl"].diff()
    energy["brent_log_ret"] = np.log(energy["brent_usd_per_bbl"]).diff() * 100.0
    energy["ulsd_diff"] = energy["ulsd_usd_per_gal"].diff()
    energy["ulsd_log_ret"] = np.log(energy["ulsd_usd_per_gal"]).diff() * 100.0
    energy["diesel_brent_crack_bbl"] = energy["ulsd_usd_per_gal"] * 42.0 - energy["brent_usd_per_bbl"]

    run_stationarity_energy(energy)
    run_stationarity_chokepoints(df)
    run_brent_ulsd_correlation(energy)
    run_chokepoint_oil_correlations(df)
    run_regime_analysis(df)
    run_rerouting_matrix(df)
    run_granger_causality(df)
    print("\n" + sep("=") + "\n")


if __name__ == "__main__":
    main()
