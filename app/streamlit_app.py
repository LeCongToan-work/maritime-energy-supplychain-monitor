"""
streamlit_app.py
----------------
 Maritime & Energy Supply Chain Monitor — Streamlit Dashboard (2 Pages)
  - Trang 1: Báo cáo tổng quan cho Ban điều hành (Executive Overview — 1 màn hình, 6 khối)
  - Trang 2: Phân tích chuyên sâu cho Chuyên viên Kế hoạch & Rủi ro Logistics (Operational & Risk Analytics)

Nguồn dữ liệu: DuckDB schema `bi_mart` (`data/maritime_dwh.duckdb`) / Parquet `data/gold/*.parquet`.
Chạy ứng dụng:
  venv\\Scripts\\streamlit.exe run app/streamlit_app.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ---------------------------------------------------------------------------
# Cấu hình trang & CSS tinh gọn (Đảm bảo Trang 1 vừa khít 1 màn hình, màu chuẩn)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Giám sát Điểm nghẽn Hàng hải & Giá Năng lượng",
    page_icon="🚢",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = PROJECT_ROOT / "data" / "maritime_dwh.duckdb"
GOLD_DIR = PROJECT_ROOT / "data" / "gold"

# Bảng màu ngữ nghĩa: Chỉ dùng Đỏ, Vàng, Xanh cho trạng thái; Xám/Xanh đậm trung tính cho dữ liệu
COLOR_RED = "#D92D20"
COLOR_AMBER = "#F79009"
COLOR_GREEN = "#12B76A"
COLOR_NAVY = "#1D2939"
COLOR_SLATE = "#475467"
COLOR_BLUE = "#1570EF"
COLOR_TEAL = "#0E9384"
COLOR_BG_RED = "#FEF3F2"
COLOR_BG_AMBER = "#FFFAEB"
COLOR_BG_GREEN = "#ECFDF3"
COLOR_BG_NEUTRAL = "#F8FAFC"

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.7rem !important;
        padding-bottom: 0.6rem !important;
        padding-left: 1.4rem !important;
        padding-right: 1.4rem !important;
        max-width: 100% !important;
    }
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.35rem !important;
    }
    .exec-banner {
        border-radius: 6px;
        padding: 8px 14px;
        margin-bottom: 4px;
        border-left: 5px solid #1D2939;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        font-size: 0.92rem;
    }
    .kpi-card {
        background: #FFFFFF;
        border: 1px solid #E4E7EC;
        border-top: 4px solid #475467;
        border-radius: 6px;
        padding: 8px 10px 4px 10px;
        box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        height: 100%;
    }
    .kpi-title {
        font-size: 0.76rem;
        font-weight: 600;
        color: #475467;
        text-transform: uppercase;
        letter-spacing: 0.02em;
        margin-bottom: 2px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .kpi-value {
        font-size: 1.38rem;
        font-weight: 700;
        color: #101828;
        line-height: 1.15;
    }
    .kpi-delta {
        font-size: 0.75rem;
        color: #475467;
        margin-top: 2px;
        margin-bottom: 2px;
    }
    .impact-box {
        background: #FFFFFF;
        border: 1px solid #E4E7EC;
        border-radius: 6px;
        padding: 10px 12px;
        height: 100%;
    }
    .impact-header {
        font-size: 0.82rem;
        font-weight: 700;
        text-transform: uppercase;
        margin-bottom: 8px;
        padding-bottom: 4px;
        border-bottom: 2px solid #E4E7EC;
    }
    .impact-item {
        font-size: 0.83rem;
        padding: 5px 0;
        border-bottom: 1px dashed #F2F4F7;
        line-height: 1.3;
    }
    .impact-item:last-child {
        border-bottom: none;
    }
    .footer-bar {
        font-size: 0.76rem;
        color: #667085;
        background: #F8FAFC;
        border: 1px solid #E4E7EC;
        border-radius: 5px;
        padding: 5px 12px;
        margin-top: 4px;
        text-align: center;
    }
    .method-warn {
        background: #FFFAEB;
        border-left: 4px solid #F79009;
        padding: 8px 12px;
        border-radius: 4px;
        font-size: 0.85rem;
        color: #7A2E0E;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Tải dữ liệu từ kho `bi_mart` (Có cache để phản hồi tức thời)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=600)
def load_bi_mart_data() -> dict[str, pd.DataFrame]:
    if DUCKDB_PATH.exists():
        con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
        try:
            dim_chokepoints = con.execute("SELECT * FROM bi_mart.dim_chokepoints").fetchdf()
            dim_events = con.execute("SELECT * FROM bi_mart.dim_geopolitical_events ORDER BY start_date").fetchdf()
            fact_energy = con.execute("SELECT * FROM bi_mart.fact_energy_prices_daily ORDER BY calendar_date").fetchdf()
            fact_transit = con.execute(
                "SELECT * FROM bi_mart.fact_chokepoint_transit_daily ORDER BY portid, observation_date"
            ).fetchdf()
            fact_regime = con.execute(
                "SELECT * FROM bi_mart.fact_chokepoint_energy_regime_daily ORDER BY portid, observation_date"
            ).fetchdf()
            fact_rerouting = con.execute(
                "SELECT * FROM bi_mart.fact_red_sea_cape_rerouting_daily ORDER BY observation_date"
            ).fetchdf()
            fact_outlier = con.execute(
                "SELECT * FROM bi_mart.fact_outlier_consensus_labeled_daily ORDER BY portid, observation_date"
            ).fetchdf()
        finally:
            con.close()
    else:
        dim_chokepoints = pd.read_parquet(GOLD_DIR / "dim_chokepoints.parquet")
        dim_events = pd.read_parquet(GOLD_DIR / "dim_geopolitical_events.parquet")
        fact_energy = pd.read_parquet(GOLD_DIR / "fct_energy_prices_daily.parquet")
        fact_transit = pd.read_parquet(GOLD_DIR / "fct_chokepoint_transit_daily.parquet")
        fact_regime = pd.read_parquet(GOLD_DIR / "mart_chokepoint_energy_regime_daily.parquet")
        fact_rerouting = pd.read_parquet(GOLD_DIR / "mart_red_sea_cape_rerouting_daily.parquet")
        fact_outlier = pd.read_parquet(GOLD_DIR / "mart_outlier_consensus_labeled_daily.parquet")

    for df, col in [
        (fact_energy, "calendar_date"),
        (fact_transit, "observation_date"),
        (fact_regime, "observation_date"),
        (fact_rerouting, "observation_date"),
        (fact_outlier, "observation_date"),
        (dim_events, "start_date"),
        (dim_events, "end_date"),
    ]:
        df[col] = pd.to_datetime(df[col])

    return {
        "dim_chokepoints": dim_chokepoints,
        "dim_events": dim_events,
        "fact_energy": fact_energy,
        "fact_transit": fact_transit,
        "fact_regime": fact_regime,
        "fact_rerouting": fact_rerouting,
        "fact_outlier": fact_outlier,
    }


def make_sparkline_svg(values: list[float], stroke_color: str = "#475467", width: int = 190, height: int = 28) -> str:
    """Tạo sparkline SVG nội tuyến siêu nhẹ cho thẻ KPI (không tốn chiều cao khung Plotly)."""
    clean_vals = [float(v) for v in values if pd.notna(v)]
    if len(clean_vals) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    vmin, vmax = min(clean_vals), max(clean_vals)
    span = (vmax - vmin) if vmax != vmin else 1.0
    n = len(clean_vals)
    pts = []
    for i, val in enumerate(clean_vals):
        x = 3 + (i / (n - 1)) * (width - 6)
        y = (height - 4) - ((val - vmin) / span) * (height - 8)
        pts.append(f"{x:.1f},{y:.1f}")
    pts_str = " ".join(pts)
    last_x, last_y = pts[-1].split(",")
    return (
        f'<svg width="100%" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
        f'<polyline fill="none" stroke="{stroke_color}" stroke-width="1.8" points="{pts_str}"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2.6" fill="{stroke_color}"/>'
        f"</svg>"
    )


def render_kpi_card(
    title: str,
    big_value: str,
    delta_text: str,
    spark_vals: list[float],
    status: str = "neutral",
) -> None:
    """Hiển thị thẻ KPI chuẩn: Số lớn + Chênh lệch so với mức nền + Sparkline nhỏ."""
    border_map = {
        "critical": COLOR_RED,
        "warning": COLOR_AMBER,
        "good": COLOR_GREEN,
        "neutral": COLOR_SLATE,
    }
    top_color = border_map.get(status, COLOR_SLATE)
    svg = make_sparkline_svg(spark_vals, stroke_color=top_color)
    html = f"""
    <div class="kpi-card" style="border-top-color: {top_color};">
        <div class="kpi-title">{title}</div>
        <div class="kpi-value">{big_value}</div>
        <div class="kpi-delta">{delta_text}</div>
        <div style="margin-top:2px;">{svg}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Khởi tạo dữ liệu & Thanh điều hướng 2 Trang
# ---------------------------------------------------------------------------
data = load_bi_mart_data()
dim_chokepoints = data["dim_chokepoints"]
dim_events = data["dim_events"]
fact_energy = data["fact_energy"]
fact_transit = data["fact_transit"]
fact_regime = data["fact_regime"]
fact_rerouting = data["fact_rerouting"]
fact_outlier = data["fact_outlier"]

max_obs_ts = fact_transit["observation_date"].max()
max_obs_date = max_obs_ts.date()
today_date = date.today()
freshness_lag_days = (today_date - max_obs_date).days

if freshness_lag_days <= 3:
    fresh_color = COLOR_GREEN
    fresh_label = f"● Tươi (trễ {freshness_lag_days} ngày)"
elif freshness_lag_days <= 7:
    fresh_color = COLOR_AMBER
    fresh_label = f"● Trễ nhẹ ({freshness_lag_days} ngày)"
else:
    fresh_color = COLOR_RED
    fresh_label = f"● Quá hạn ({freshness_lag_days} ngày so với {today_date.strftime('%d/%m/%Y')})"

nav_col1, nav_col2 = st.columns([3.2, 2.8])
with nav_col1:
    page = st.radio(
        "Chế độ xem",
        options=[
            "Trang 1 · Tổng quan Ban điều hành (Executive)",
            "Trang 2 · Phân tích Chuyên sâu & Rủi ro Logistics (Operational)",
        ],
        horizontal=True,
        label_visibility="collapsed",
    )


# ===========================================================================
# TRANG 1: BÁO CÁO TỔNG QUAN CHO BAN ĐIỀU HÀNH (EXECUTIVE OVERVIEW)
# ===========================================================================
if page.startswith("Trang 1"):
    with nav_col2:
        time_window = st.radio(
            "Khoảng thời gian",
            options=["30d", "Từ 11/2023", "Tất cả"],
            index=1,
            horizontal=True,
            label_visibility="collapsed",
        )

    if time_window == "30d":
        start_filter = max_obs_ts - pd.Timedelta(days=29)
        window_desc = "30 ngày gần nhất"
    elif time_window == "Từ 11/2023":
        start_filter = pd.Timestamp("2023-11-19")
        window_desc = "từ 19/11/2023 (Khủng hoảng Biển Đỏ)"
    else:
        start_filter = fact_transit["observation_date"].min()
        window_desc = "toàn kỳ (01/2021 – 11/2026)"

    df_rr_win = fact_rerouting[fact_rerouting["observation_date"] >= start_filter].copy()
    df_en_win = fact_energy[fact_energy["calendar_date"] >= start_filter].copy()
    df_tr_win = fact_transit[fact_transit["observation_date"] >= start_filter].copy()

    # Tính các chỉ số cho [A] và [B1..B5]
    base_suez = float(
        dim_chokepoints.loc[dim_chokepoints["portname"] == "Suez Canal", "baseline_n_total"].iloc[0]
    )
    base_bab = float(
        dim_chokepoints.loc[dim_chokepoints["portname"] == "Bab el-Mandeb Strait", "baseline_n_total"].iloc[0]
    )
    base_cape = float(
        dim_chokepoints.loc[dim_chokepoints["portname"] == "Cape of Good Hope", "baseline_n_total"].iloc[0]
    )

    # Mức nền trước khủng hoảng Biển Đỏ (2021–2022)
    pre_rr = fact_rerouting[fact_rerouting["observation_date"] < pd.Timestamp("2023-01-01")]
    pre_en = fact_energy[fact_energy["calendar_date"] < pd.Timestamp("2023-01-01")]
    base_cape_share = float(pre_rr["cape_rerouting_share_total_pct"].mean())
    base_brent = float(pre_en["brent_usd_per_bbl"].mean())
    base_ulsd = float(pre_en["ulsd_usd_per_gal"].mean())
    base_crack = float(pre_en["diesel_brent_crack_bbl"].mean())

    # Số liệu trong cửa sổ đang chọn & ngày mới nhất
    suez_win_avg = float(df_rr_win["suez_n_total"].mean())
    bab_win_avg = float(df_rr_win["babelmandeb_n_total"].mean())
    cape_win_avg = float(df_rr_win["cape_n_total"].mean())

    suez_pct_vs_base = (suez_win_avg - base_suez) * 100.0 / base_suez
    bab_pct_vs_base = (bab_win_avg - base_bab) * 100.0 / base_bab
    red_sea_combined_pct = ((suez_win_avg + bab_win_avg) - (base_suez + base_bab)) * 100.0 / (base_suez + base_bab)

    cape_share_win = float(df_rr_win["cape_rerouting_share_total_pct"].mean())
    cape_share_delta = cape_share_win - base_cape_share

    latest_en = fact_energy.iloc[-1]
    latest_brent = float(latest_en["brent_usd_per_bbl"])
    brent_30d_ago = float(fact_energy.iloc[-31]["brent_usd_per_bbl"]) if len(fact_energy) > 31 else base_brent
    brent_30d_pct = (latest_brent - brent_30d_ago) * 100.0 / brent_30d_ago
    latest_vol_30d = float(latest_en["brent_volatility_30d"])
    latest_crack = float(latest_en["diesel_brent_crack_bbl"])
    crack_delta_vs_base = latest_crack - base_crack

    # Điểm nghẽn đang cảnh báo High/Critical tại ngày mới nhất (dùng MA7 để tránh nhiễu 1 ngày)
    latest_tr = fact_transit[fact_transit["observation_date"] == max_obs_ts].copy()
    alert_ports = latest_tr[latest_tr["daily_alert_severity"].isin(["High", "Critical"])].sort_values(
        "pct_vs_baseline_total"
    )
    n_alert_ports = len(alert_ports)
    top3_alert_names = [
        f"{r['portname'].replace(' Strait', '').replace(' Canal', '')} ({r['pct_vs_baseline_total']:+.0f}%)"
        for _, r in alert_ports.head(3).iterrows()
    ]
    top3_str = ", ".join(top3_alert_names) if top3_alert_names else "Không có điểm nghẽn vượt ngưỡng"

    # -----------------------------------------------------------------------
    # [A] CÂU KẾT LUẬN TỰ SINH (1 dòng, màu theo mức nghiêm trọng) + ĐỘ TƯƠI
    # -----------------------------------------------------------------------
    if red_sea_combined_pct <= -30.0 or n_alert_ports >= 5:
        banner_bg = COLOR_BG_RED
        banner_border = COLOR_RED
        severity_tag = "CẢNH BÁO CAO"
    elif red_sea_combined_pct <= -15.0 or n_alert_ports >= 2:
        banner_bg = COLOR_BG_AMBER
        banner_border = COLOR_AMBER
        severity_tag = "CẢNH BÁO TRUNG BÌNH"
    else:
        banner_bg = COLOR_BG_GREEN
        banner_border = COLOR_GREEN
        severity_tag = "BÌNH THƯỜNG"

    auto_conclusion = (
        f"<b>[{severity_tag} · {window_desc}]</b> "
        f"Lưu lượng Suez <b>{suez_pct_vs_base:+.1f}%</b> & Bab el-Mandeb <b>{bab_pct_vs_base:+.1f}%</b> so với mức nền; "
        f"<b>{cape_share_win:.1f}%</b> tàu Á–Âu đi vòng Mũi Hảo Vọng; "
        f"Brent <b>${latest_brent:.2f}/bbl</b> ({brent_30d_pct:+.1f}% trong 30 ngày)."
    )

    st.markdown(
        f"""
        <div class="exec-banner" style="background:{banner_bg}; border-left-color:{banner_border};">
            <div style="color:#101828;">{auto_conclusion}</div>
            <div style="font-size:0.80rem; color:#344054; font-weight:600;">
                Dữ liệu đến: <code>{max_obs_date.strftime('%d/%m/%Y')}</code> &nbsp;
                <span style="color:{fresh_color}; font-weight:700;">{fresh_label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # [B1] – [B5] 5 THẺ CHỈ SỐ TỔNG QUAN (Số lớn + Chênh lệch vs nền + Sparkline)
    # -----------------------------------------------------------------------
    b_cols = st.columns([1.05, 1.0, 1.05, 1.0, 1.35])

    # Chuỗi sparkline (lấy tối đa 60 điểm mẫu đều trong cửa sổ để vẽ nhanh)
    step_s = max(1, len(df_rr_win) // 50)
    sp_b1 = (
        ((df_rr_win["suez_ma7_total"] + df_rr_win["babelmandeb_ma7_total"]) - (base_suez + base_bab))
        * 100.0
        / (base_suez + base_bab)
    ).iloc[::step_s].tolist()
    sp_b2 = df_rr_win["cape_rerouting_ma7_total_pct"].iloc[::step_s].tolist()
    sp_b3 = df_en_win["brent_ma7"].iloc[::step_s].tolist()
    sp_b4 = df_en_win["crack_ma7"].iloc[::step_s].tolist()

    daily_alerts_ts = (
        df_tr_win.groupby("observation_date")["daily_alert_severity"]
        .apply(lambda s: int(s.isin(["High", "Critical"]).sum()))
        .iloc[::step_s]
        .tolist()
    )

    with b_cols[0]:
        b1_status = "critical" if red_sea_combined_pct <= -30 else ("warning" if red_sea_combined_pct <= -15 else "good")
        render_kpi_card(
            title="[B1] Lưu lượng Suez & Bab vs Nền",
            big_value=f"{red_sea_combined_pct:+.1f}%",
            delta_text=f"Suez {suez_pct_vs_base:+.1f}% · Bab {bab_pct_vs_base:+.1f}% (vs nền 21–22)",
            spark_vals=sp_b1,
            status=b1_status,
        )

    with b_cols[1]:
        b2_status = "critical" if cape_share_win >= 65 else ("warning" if cape_share_win >= 50 else "good")
        render_kpi_card(
            title="[B2] Tỷ trọng đi vòng Cape (%)",
            big_value=f"{cape_share_win:.1f}%",
            delta_text=f"{cape_share_delta:+.1f} điểm % vs nền ({base_cape_share:.1f}%)",
            spark_vals=sp_b2,
            status=b2_status,
        )

    with b_cols[2]:
        b3_status = "critical" if latest_brent >= 100 else ("warning" if latest_brent >= 85 else "neutral")
        render_kpi_card(
            title="[B3] Giá dầu Brent ($/bbl)",
            big_value=f"${latest_brent:.2f}",
            delta_text=f"30d: {brent_30d_pct:+.1f}% · Biến động 30d: {latest_vol_30d:.2f}%",
            spark_vals=sp_b3,
            status=b3_status,
        )

    with b_cols[3]:
        b4_status = "critical" if latest_crack >= 50 else ("warning" if latest_crack >= 35 else "neutral")
        render_kpi_card(
            title="[B4] Crack Spread Diesel–Brent",
            big_value=f"${latest_crack:.2f}/bbl",
            delta_text=f"{crack_delta_vs_base:+.1f} $/bbl vs nền (${base_crack:.1f}/bbl)",
            spark_vals=sp_b4,
            status=b4_status,
        )

    with b_cols[4]:
        b5_status = "critical" if n_alert_ports >= 6 else ("warning" if n_alert_ports >= 3 else "good")
        render_kpi_card(
            title="[B5] Điểm nghẽn cảnh báo High/Critical",
            big_value=f"{n_alert_ports} / 28",
            delta_text=f"Top 3: {top3_str}",
            spark_vals=daily_alerts_ts,
            status=b5_status,
        )

    # -----------------------------------------------------------------------
    # [C] BIỂU ĐỒ CHÍNH (2 PANEL CHUNG TRỤC THỜI GIAN) & [D] THIỆT HẠI | LỢI ÍCH
    # -----------------------------------------------------------------------
    cd_cols = st.columns([3.35, 2.05])

    with cd_cols[0]:
        df_plot = df_rr_win.copy()
        df_plot["suez_pct_base"] = (df_plot["suez_ma7_total"] - base_suez) * 100.0 / base_suez
        df_plot["bab_pct_base"] = (df_plot["babelmandeb_ma7_total"] - base_bab) * 100.0 / base_bab
        df_plot["cape_pct_base"] = (df_plot["cape_ma7_total"] - base_cape) * 100.0 / base_cape

        fig_c = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            row_heights=[0.54, 0.46],
            subplot_titles=(
                "[C1] Lưu lượng Suez, Bab el-Mandeb & Mũi Hảo Vọng (% lệch MA7 so với mức nền 2021–2022)",
                "[C2] Đồng biến động Giá dầu Brent & ULSD Diesel quy đổi ($/bbl, vùng bóng = sự kiện)",
            ),
        )

        # Panel trên: % lệch so với nền của Suez, Bab el-Mandeb, Cape of Good Hope
        fig_c.add_trace(
            go.Scatter(
                x=df_plot["observation_date"],
                y=df_plot["suez_pct_base"],
                name="Suez Canal (% vs nền)",
                line=dict(color=COLOR_AMBER, width=1.9),
            ),
            row=1,
            col=1,
        )
        fig_c.add_trace(
            go.Scatter(
                x=df_plot["observation_date"],
                y=df_plot["bab_pct_base"],
                name="Bab el-Mandeb (% vs nền)",
                line=dict(color=COLOR_RED, width=2.0),
            ),
            row=1,
            col=1,
        )
        fig_c.add_trace(
            go.Scatter(
                x=df_plot["observation_date"],
                y=df_plot["cape_pct_base"],
                name="Mũi Hảo Vọng (% vs nền)",
                line=dict(color=COLOR_GREEN, width=2.0),
            ),
            row=1,
            col=1,
        )
        fig_c.add_hline(y=0, line_dash="dot", line_color="#98A2B3", row=1, col=1)

        # Panel dưới: Giá dầu Brent & Diesel quy đổi ($/bbl)
        fig_c.add_trace(
            go.Scatter(
                x=df_plot["observation_date"],
                y=df_plot["brent_usd_per_bbl"],
                name="Brent ($/bbl)",
                line=dict(color=COLOR_NAVY, width=1.9),
            ),
            row=2,
            col=1,
        )
        fig_c.add_trace(
            go.Scatter(
                x=df_plot["observation_date"],
                y=df_plot["ulsd_usd_per_bbl"],
                name="ULSD Diesel proxy ($/bbl = $/gal × 42)",
                line=dict(color=COLOR_BLUE, width=1.7, dash="dot"),
            ),
            row=2,
            col=1,
        )

        # Vùng bóng sự kiện địa chính trị (Shaded Event Bands)
        event_colors = {
            "EVT_01": "rgba(247, 144, 9, 0.18)",
            "EVT_02": "rgba(21, 112, 239, 0.10)",
            "EVT_03": "rgba(217, 45, 32, 0.09)",
            "EVT_04": "rgba(217, 45, 32, 0.18)",
        }
        win_min = df_plot["observation_date"].min()
        win_max = df_plot["observation_date"].max()
        for _, ev in dim_events.iterrows():
            ev_s = max(ev["start_date"], win_min)
            ev_e = min(ev["end_date"], win_max)
            if ev_e >= win_min and ev_s <= win_max:
                fig_c.add_vrect(
                    x0=ev_s,
                    x1=ev_e,
                    fillcolor=event_colors.get(ev["event_id"], "rgba(150,150,150,0.12)"),
                    line_width=0,
                    annotation_text=ev["event_id"],
                    annotation_position="top left",
                    annotation_font_size=10,
                )

        fig_c.update_layout(
            height=355,
            margin=dict(l=8, r=8, t=26, b=6),
            paper_bgcolor="white",
            plot_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10.5)),
            hovermode="x unified",
        )
        fig_c.update_annotations(font_size=11.5)
        fig_c.update_yaxes(title_text="% vs nền", gridcolor="#F2F4F7", row=1, col=1, title_font=dict(size=10))
        fig_c.update_yaxes(title_text="USD / bbl", gridcolor="#F2F4F7", row=2, col=1, title_font=dict(size=10))
        st.plotly_chart(fig_c, use_container_width=True, config={"displayModeBar": False})

    with cd_cols[1]:
        # Tính chỉ số Thiệt hại | Lợi ích từ dữ liệu thực đo trong cửa sổ chọn so với mức nền 2021–2022
        brent_win_avg = float(df_en_win["brent_usd_per_bbl"].mean())
        ulsd_win_avg = float(df_en_win["ulsd_usd_per_gal"].mean())
        crack_win_avg = float(df_en_win["diesel_brent_crack_bbl"].mean())

        brent_pct_vs_base = (brent_win_avg - base_brent) * 100.0 / base_brent
        ulsd_pct_vs_base = (ulsd_win_avg - base_ulsd) * 100.0 / base_ulsd
        cape_pct_vs_base = (cape_win_avg - base_cape) * 100.0 / base_cape
        cape_tnk_win = float(df_rr_win["cape_rerouting_share_tanker_pct"].mean())
        cape_cnt_win = float(df_rr_win["cape_rerouting_share_container_pct"].mean())

        loss_col, gain_col = st.columns(2)
        with loss_col:
            st.markdown(
                f"""
                <div class="impact-box" style="border-top: 3px solid {COLOR_RED};">
                    <div class="impact-header" style="color:{COLOR_RED};">[D1] THIỆT HẠI (ĐO ĐƯỢC)</div>
                    <div class="impact-item">
                        <b style="color:{COLOR_RED};">↓ {bab_pct_vs_base:+.1f}%</b><br/>
                        Lưu lượng <b>Bab el-Mandeb</b><br/>
                        <span style="color:#667085; font-size:0.76rem;">{base_bab:.1f} → {bab_win_avg:.1f} tàu/ngày</span>
                    </div>
                    <div class="impact-item">
                        <b style="color:{COLOR_RED};">↓ {suez_pct_vs_base:+.1f}%</b><br/>
                        Lưu lượng <b>Kênh đào Suez</b><br/>
                        <span style="color:#667085; font-size:0.76rem;">{base_suez:.1f} → {suez_win_avg:.1f} tàu/ngày</span>
                    </div>
                    <div class="impact-item">
                        <b style="color:{COLOR_AMBER if brent_pct_vs_base >= 0 else COLOR_SLATE};">
                            {'↑' if brent_pct_vs_base >= 0 else '↓'} Brent {brent_pct_vs_base:+.1f}% · ULSD {ulsd_pct_vs_base:+.1f}%
                        </b><br/>
                        Giá nhiên liệu giao ngay vs nền<br/>
                        <span style="color:#667085; font-size:0.76rem;">TB kỳ: ${brent_win_avg:.1f}/bbl · ${ulsd_win_avg:.2f}/gal</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with gain_col:
            st.markdown(
                f"""
                <div class="impact-box" style="border-top: 3px solid {COLOR_GREEN};">
                    <div class="impact-header" style="color:{COLOR_GREEN};">[D2] DỊCH CHUYỂN & LỢI ÍCH</div>
                    <div class="impact-item">
                        <b style="color:{COLOR_GREEN};">↑ {cape_pct_vs_base:+.1f}%</b><br/>
                        Lưu lượng <b>Mũi Hảo Vọng</b><br/>
                        <span style="color:#667085; font-size:0.76rem;">{base_cape:.1f} → {cape_win_avg:.1f} tàu/ngày</span>
                    </div>
                    <div class="impact-item">
                        <b style="color:{COLOR_GREEN};">↑ {cape_share_win:.1f}% ({cape_share_delta:+.1f} đ%)</b><br/>
                        Tỷ trọng hấp thụ tuyến Cape<br/>
                        <span style="color:#667085; font-size:0.76rem;">Container: {cape_cnt_win:.1f}% · Tanker: {cape_tnk_win:.1f}%</span>
                    </div>
                    <div class="impact-item">
                        <b style="color:{COLOR_BLUE};">↗ Crack ${crack_win_avg:.1f}/bbl</b><br/>
                        Biên lọc dầu (Lợi ích tiềm năng)<br/>
                        <span style="color:#667085; font-size:0.75rem;"><i>Suy luận từ proxy giá, không đo lợi nhuận</i></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Mục mở rộng tùy chọn: Ước tính chi phí đi vòng bằng tiền theo giả định
        with st.expander("🧮 Mô phỏng chi phí nhiên liệu đi vòng (Ước tính theo giả định, không phải số đo)"):
            st.caption(
                "⚠️ **Lưu ý:** Kho dữ liệu không chứa chi phí tiền tệ hay mức tiêu hao nhiên liệu thực tế. "
                "Công cụ dưới đây chỉ nhân các giả định đầu vào của người dùng:"
            )
            s_c1, s_c2, s_c3 = st.columns(3)
            with s_c1:
                extra_days = st.slider(
                    "Số ngày đi vòng thêm",
                    min_value=5,
                    max_value=18,
                    value=10,
                    help="Nguồn tham khảo giả định: UNCTAD (2024) ước tính đi vòng Mũi Hảo Vọng kéo dài hải trình Á–Âu thêm ~10–14 ngày.",
                )
            with s_c2:
                tons_per_day = st.slider(
                    "Tiêu hao (tấn/ngày)",
                    min_value=20,
                    max_value=120,
                    value=45,
                    help="Nguồn tham khảo giả định: IMO Fourth GHG Study (2020) cho tàu thương mại cỡ trung (Panamax/Container/Tanker).",
                )
            with s_c3:
                proxy_bunker_ton = round(latest_en["ulsd_usd_per_gal"] * 315.0, -1)
                fuel_price_ton = st.slider(
                    "Giá nhiên liệu ($/tấn)",
                    min_value=400,
                    max_value=1200,
                    value=int(min(max(proxy_bunker_ton, 400), 1200)),
                    step=10,
                    help="Giả định giá nhiên liệu ($/tấn). Mặc định quy đổi xấp xỉ từ giá ULSD mới nhất (1 tấn ≈ 315 gallon).",
                )
            est_cost_per_voyage = extra_days * tons_per_day * fuel_price_ton
            st.markdown(
                f"👉 **Chi phí nhiên liệu tăng thêm ước tính (theo giả định):** "
                f"`${est_cost_per_voyage:,.0f} / chuyến` "
                f"(`{extra_days} ngày × {tons_per_day} tấn/ngày × ${fuel_price_ton}/tấn`)."
            )

    # -----------------------------------------------------------------------
    # CHÂN TRANG (FOOTER)
    # -----------------------------------------------------------------------
    st.markdown(
        """
        <div class="footer-bar">
            <b>Nguồn:</b> IMF PortWatch (28 điểm nghẽn hàng hải), U.S. EIA API v2 (Brent Europe FOB & ULSD USGC FOB)
            &nbsp;·&nbsp; <b>Giới hạn đo lường:</b> Giá diesel ULSD là chỉ báo proxy, không phải giá dầu bunker hàng hải thực tế;
            kho dữ liệu không bao gồm cước vận tải (Freight Rate) và phụ phí BAF.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# TRANG 2: PHÂN TÍCH CHUYÊN SÂU CHO CHUYÊN VIÊN KẾ HOẠCH & RỦI RO LOGISTICS
# ===========================================================================
else:
    with nav_col2:
        st.markdown(
            f"<div style='text-align:right; font-size:0.84rem; padding-top:4px;'>"
            f"Dữ liệu đến: <code>{max_obs_date.strftime('%d/%m/%Y')}</code> · "
            f"<span style='color:{fresh_color}; font-weight:700;'>{fresh_label}</span></div>",
            unsafe_allow_html=True,
        )

    # Bộ lọc tác nghiệp Trang 2: Vùng, Điểm nghẽn, Loại tàu, Khoảng thời gian
    f_col1, f_col2, f_col3, f_col4 = st.columns([1.3, 1.5, 1.2, 1.3])
    with f_col1:
        regions = ["Tất cả vùng"] + sorted(dim_chokepoints["maritime_region"].unique().tolist())
        sel_region = st.selectbox("Vùng hàng hải", options=regions, index=0)

    avail_ports_df = (
        dim_chokepoints
        if sel_region == "Tất cả vùng"
        else dim_chokepoints[dim_chokepoints["maritime_region"] == sel_region]
    )
    avail_ports = avail_ports_df["portname"].tolist()

    with f_col2:
        default_port = "Bab el-Mandeb Strait" if "Bab el-Mandeb Strait" in avail_ports else avail_ports[0]
        sel_port = st.selectbox(
            "Điểm nghẽn tiêu điểm (cho Tương quan & Chi tiết)",
            options=avail_ports,
            index=avail_ports.index(default_port),
        )

    with f_col3:
        vessel_map = {
            "Tổng số tàu (n_total)": ("n_total", "baseline_n_total"),
            "Tàu chở dầu (n_tanker)": ("n_tanker", "baseline_n_tanker"),
            "Tàu container (n_container)": ("n_container", None),
            "Tàu hàng rời (n_dry_bulk)": ("n_dry_bulk", None),
        }
        sel_vessel_label = st.selectbox("Loại tàu phân tích", options=list(vessel_map.keys()), index=0)
        sel_vessel_col, _ = vessel_map[sel_vessel_label]

    with f_col4:
        min_d = fact_transit["observation_date"].min().date()
        date_range = st.date_input(
            "Khoảng thời gian",
            value=(date(2023, 1, 1), max_obs_date),
            min_value=min_d,
            max_value=max_obs_date,
        )
        if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
            d_start, d_end = pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1])
        else:
            d_start, d_end = pd.Timestamp("2023-01-01"), max_obs_ts

    # -----------------------------------------------------------------------
    # KHỐI 1 & KHỐI 2: BẢN ĐỒ NHIỆT 28 ĐIỂM NGHẼN THEO TUẦN & THAY THẾ TUYẾN
    # -----------------------------------------------------------------------
    row1_c1, row1_c2 = st.columns([1.45, 1.25])

    with row1_c1:
        st.markdown("##### 1. Bản đồ nhiệt 28 Điểm nghẽn theo tuần (% lệch so với nền 2021–2022, xếp theo mức nghiêm trọng)")
        df_hm = fact_transit[
            (fact_transit["observation_date"] >= d_start) & (fact_transit["observation_date"] <= d_end)
        ].copy()
        if sel_region != "Tất cả vùng":
            df_hm = df_hm[df_hm["portname"].isin(avail_ports)]

        # Tính baseline cho loại tàu được chọn (nếu container/dry_bulk thì tính từ 2021-2022)
        base_by_port = (
            fact_transit[fact_transit["observation_date"] < pd.Timestamp("2023-01-01")]
            .groupby("portname")[sel_vessel_col]
            .mean()
            .replace(0, np.nan)
        )
        df_hm["week_start"] = df_hm["observation_date"].dt.to_period("W").apply(lambda r: r.start_time)
        weekly_piv = df_hm.groupby(["portname", "week_start"])[sel_vessel_col].mean().unstack("week_start")
        weekly_pct = weekly_piv.div(base_by_port, axis=0).subtract(1.0).multiply(100.0).round(1)

        # Sắp xếp điểm nghẽn theo mức giảm nặng nhất trong 8 tuần gần nhất
        recent_cols = weekly_pct.columns[-8:] if len(weekly_pct.columns) >= 8 else weekly_pct.columns
        sort_order = weekly_pct[recent_cols].mean(axis=1).sort_values(ascending=True).index
        weekly_pct = weekly_pct.loc[sort_order]

        fig_hm = go.Figure(
            data=go.Heatmap(
                z=weekly_pct.values,
                x=weekly_pct.columns,
                y=weekly_pct.index,
                colorscale=[
                    [0.0, "#B42318"],
                    [0.30, "#F79009"],
                    [0.50, "#F8FAFC"],
                    [0.75, "#6CE9A6"],
                    [1.0, "#027A48"],
                ],
                zmin=-80,
                zmax=80,
                colorbar=dict(title="% vs nền", thickness=12),
                hovertemplate="Điểm nghẽn: %{y}<br>Tuần: %{x|%d/%m/%Y}<br>Lệch vs nền: %{z:+.1f}%<extra></extra>",
            )
        )
        fig_hm.update_layout(
            height=410,
            margin=dict(l=6, r=6, t=8, b=6),
            yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
            xaxis=dict(tickfont=dict(size=10)),
        )
        st.plotly_chart(fig_hm, use_container_width=True, config={"displayModeBar": False})

    with row1_c2:
        st.markdown("##### 2. Thay thế tuyến: Suez / Bab el-Mandeb vs. Mũi Hảo Vọng (Tách Tàu dầu & Tàu Container)")
        df_sub = fact_rerouting[
            (fact_rerouting["observation_date"] >= d_start) & (fact_rerouting["observation_date"] <= d_end)
        ].copy()

        fig_sub = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.10,
            subplot_titles=(
                "Tàu chở dầu (Tanker MA7 tàu/ngày & Tỷ trọng đi vòng Cape %)",
                "Tàu Container (Container MA7 tàu/ngày & Tỷ trọng đi vòng Cape %)",
            ),
            specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
        )

        # Panel 1: Tanker
        fig_sub.add_trace(
            go.Scatter(
                x=df_sub["observation_date"],
                y=df_sub["babelmandeb_ma7_tanker"],
                name="Bab el-Mandeb (Tanker)",
                line=dict(color=COLOR_RED, width=1.8),
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        fig_sub.add_trace(
            go.Scatter(
                x=df_sub["observation_date"],
                y=df_sub["cape_ma7_tanker"],
                name="Mũi Hảo Vọng (Tanker)",
                line=dict(color=COLOR_GREEN, width=1.8),
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        fig_sub.add_trace(
            go.Scatter(
                x=df_sub["observation_date"],
                y=df_sub["cape_rerouting_share_tanker_pct"].rolling(7, min_periods=1).mean(),
                name="Tỷ trọng Cape Tanker (%)",
                line=dict(color=COLOR_NAVY, width=1.4, dash="dot"),
            ),
            row=1,
            col=1,
            secondary_y=True,
        )

        # Panel 2: Container
        fig_sub.add_trace(
            go.Scatter(
                x=df_sub["observation_date"],
                y=df_sub["babelmandeb_ma7_container"],
                name="Bab el-Mandeb (Container)",
                line=dict(color=COLOR_AMBER, width=1.8),
            ),
            row=2,
            col=1,
            secondary_y=False,
        )
        fig_sub.add_trace(
            go.Scatter(
                x=df_sub["observation_date"],
                y=df_sub["cape_ma7_container"],
                name="Mũi Hảo Vọng (Container)",
                line=dict(color=COLOR_TEAL, width=1.8),
            ),
            row=2,
            col=1,
            secondary_y=False,
        )
        fig_sub.add_trace(
            go.Scatter(
                x=df_sub["observation_date"],
                y=df_sub["cape_rerouting_share_container_pct"].rolling(7, min_periods=1).mean(),
                name="Tỷ trọng Cape Container (%)",
                line=dict(color=COLOR_BLUE, width=1.4, dash="dot"),
            ),
            row=2,
            col=1,
            secondary_y=True,
        )

        fig_sub.update_layout(
            height=410,
            margin=dict(l=6, r=6, t=24, b=6),
            legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="right", x=1, font=dict(size=9.5)),
            hovermode="x unified",
            paper_bgcolor="white",
            plot_bgcolor="white",
        )
        fig_sub.update_annotations(font_size=11)
        fig_sub.update_yaxes(title_text="Tàu/ngày", secondary_y=False, gridcolor="#F2F4F7")
        fig_sub.update_yaxes(title_text="Cape %", range=[0, 100], secondary_y=True, showgrid=False)
        st.plotly_chart(fig_sub, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # -----------------------------------------------------------------------
    # KHỐI 3 & KHỐI 4: NGHIÊN CỨU SỰ KIỆN (±30 NGÀY, MỐC 100) & TƯƠNG QUAN SAI PHÂN
    # -----------------------------------------------------------------------
    row2_c1, row2_c2 = st.columns([1.25, 1.45])

    with row2_c1:
        st.markdown("##### 3. Nghiên cứu sự kiện (±30 ngày quanh ngày bùng phát, chuẩn hóa = 100 tại t = 0)")
        ev_options = [
            f"{r['event_id']} · {r['event_name']} ({r['primary_chokepoint']}, {r['start_date'].strftime('%d/%m/%Y')})"
            for _, r in dim_events.iterrows()
        ]
        sel_ev_str = st.selectbox("Chọn sự kiện từ dim_geopolitical_events", options=ev_options, index=2)
        sel_ev_id = sel_ev_str.split(" · ")[0]
        ev_row = dim_events[dim_events["event_id"] == sel_ev_id].iloc[0]
        t0 = ev_row["start_date"]
        ev_port = ev_row["primary_chokepoint"]

        ev_tr = fact_transit[
            (fact_transit["portname"] == ev_port)
            & (fact_transit["observation_date"] >= t0 - pd.Timedelta(days=30))
            & (fact_transit["observation_date"] <= t0 + pd.Timedelta(days=30))
        ].copy()
        ev_en = fact_energy[
            (fact_energy["calendar_date"] >= t0 - pd.Timedelta(days=30))
            & (fact_energy["calendar_date"] <= t0 + pd.Timedelta(days=30))
        ].copy()

        ev_merged = pd.merge(
            ev_tr[["observation_date", "n_total_ma7", "n_tanker_ma7"]],
            ev_en[["calendar_date", "brent_usd_per_bbl", "ulsd_usd_per_gal"]],
            left_on="observation_date",
            right_on="calendar_date",
            how="inner",
        )
        ev_merged["rel_day"] = (ev_merged["observation_date"] - t0).dt.days
        t0_row = ev_merged[ev_merged["rel_day"] == 0].iloc[0] if (ev_merged["rel_day"] == 0).any() else ev_merged.iloc[0]

        for col_n, new_c in [
            ("n_total_ma7", "idx_total"),
            ("n_tanker_ma7", "idx_tanker"),
            ("brent_usd_per_bbl", "idx_brent"),
            ("ulsd_usd_per_gal", "idx_ulsd"),
        ]:
            base_v = float(t0_row[col_n]) if float(t0_row[col_n]) != 0 else 1.0
            ev_merged[new_c] = (ev_merged[col_n] / base_v) * 100.0

        fig_ev = go.Figure()
        fig_ev.add_trace(
            go.Scatter(
                x=ev_merged["rel_day"],
                y=ev_merged["idx_total"],
                name=f"{ev_port} · Tổng tàu MA7 (Idx)",
                line=dict(color=COLOR_RED, width=2.2),
            )
        )
        fig_ev.add_trace(
            go.Scatter(
                x=ev_merged["rel_day"],
                y=ev_merged["idx_tanker"],
                name=f"{ev_port} · Tàu dầu MA7 (Idx)",
                line=dict(color=COLOR_AMBER, width=1.8, dash="dot"),
            )
        )
        fig_ev.add_trace(
            go.Scatter(
                x=ev_merged["rel_day"],
                y=ev_merged["idx_brent"],
                name="Giá Brent (Idx)",
                line=dict(color=COLOR_NAVY, width=2.0),
            )
        )
        fig_ev.add_trace(
            go.Scatter(
                x=ev_merged["rel_day"],
                y=ev_merged["idx_ulsd"],
                name="Giá ULSD Diesel (Idx)",
                line=dict(color=COLOR_BLUE, width=1.8),
            )
        )
        fig_ev.add_vline(x=0, line_dash="dash", line_color=COLOR_RED, annotation_text="Ngày sự kiện (t=0)")
        fig_ev.add_hline(y=100, line_dash="dot", line_color="#98A2B3")
        fig_ev.update_layout(
            height=330,
            margin=dict(l=6, r=6, t=10, b=6),
            xaxis_title="Số ngày quanh mốc sự kiện (t = -30 đến +30)",
            yaxis_title="Chỉ số chuẩn hóa (t=0 = 100)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=9.5)),
            hovermode="x unified",
            paper_bgcolor="white",
            plot_bgcolor="white",
        )
        st.plotly_chart(fig_ev, use_container_width=True, config={"displayModeBar": False})

    with row2_c2:
        st.markdown(f"##### 4. Quan hệ Giá & Lưu lượng tại `{sel_port}` (Tính trên chuỗi sai phân dừng $I(0)$)")
        st.markdown(
            """
            <div class="method-warn">
                ⚠️ <b>Cảnh báo cố định:</b> Chỉ số dưới đây đo lường <b>đồng biến động (co-movement)</b> trên chuỗi đã lấy sai phân dừng
                (đã loại bỏ các ngày điền khuyết giá <code>is_forward_filled</code> khi tính sai phân ngày), cỡ mẫu sự kiện nhỏ,
                <b>KHÔNG phải quan hệ nhân quả</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

        df_p_reg = fact_regime[
            (fact_regime["portname"] == sel_port)
            & (fact_regime["observation_date"] >= d_start)
            & (fact_regime["observation_date"] <= d_end)
        ].copy()

        # Tính tương quan trễ (Lead-Lag k = -14..+14) trên chuỗi sai phân tuần (diff_7d) và sai phân ngày thực (không ffill)
        valid_tr_days = df_p_reg[~df_p_reg["brent_is_ffill"]].copy()
        lags = list(range(-14, 15))
        ccf_brent = []
        ccf_ulsd = []
        for k in lags:
            # k > 0: Lưu lượng đi trước giá k ngày
            s_flow = df_p_reg["n_tanker_diff_7d"]
            s_brent = df_p_reg["brent_diff_7d"].shift(-k)
            s_ulsd = df_p_reg["ulsd_diff_7d"].shift(-k)
            ccf_brent.append(float(s_flow.corr(s_brent)) if s_flow.notna().sum() > 20 else 0.0)
            ccf_ulsd.append(float(s_flow.corr(s_ulsd)) if s_flow.notna().sum() > 20 else 0.0)

        fig_corr = make_subplots(
            rows=1,
            cols=2,
            column_widths=[0.58, 0.42],
            subplot_titles=(
                "Tương quan lăn 90d (Sai phân tuần Δ7 Tanker vs Δ7 Giá)",
                "Tương quan trễ (Lag k = -14..+14 ngày trên Δ7)",
            ),
        )
        fig_corr.add_trace(
            go.Scatter(
                x=df_p_reg["observation_date"],
                y=df_p_reg["rolling_corr_90d_diff7d_brent"],
                name="Corr 90d (Δ7 Tanker, Δ7 Brent)",
                line=dict(color=COLOR_NAVY, width=1.8),
            ),
            row=1,
            col=1,
        )
        fig_corr.add_trace(
            go.Scatter(
                x=df_p_reg["observation_date"],
                y=df_p_reg["rolling_corr_90d_diff7d_ulsd"],
                name="Corr 90d (Δ7 Tanker, Δ7 ULSD)",
                line=dict(color=COLOR_BLUE, width=1.8),
            ),
            row=1,
            col=1,
        )
        fig_corr.add_hline(y=0, line_dash="dot", line_color="#98A2B3", row=1, col=1)

        fig_corr.add_trace(
            go.Bar(
                x=lags,
                y=ccf_brent,
                name="CCF Δ7 Brent",
                marker_color=COLOR_NAVY,
            ),
            row=1,
            col=2,
        )
        fig_corr.add_trace(
            go.Bar(
                x=lags,
                y=ccf_ulsd,
                name="CCF Δ7 ULSD",
                marker_color=COLOR_BLUE,
            ),
            row=1,
            col=2,
        )
        fig_corr.update_layout(
            height=305,
            margin=dict(l=6, r=6, t=26, b=6),
            legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="right", x=1, font=dict(size=9.5)),
            paper_bgcolor="white",
            plot_bgcolor="white",
            barmode="group",
        )
        fig_corr.update_annotations(font_size=10.5)
        fig_corr.update_yaxes(range=[-0.8, 0.8], gridcolor="#F2F4F7", row=1, col=1)
        fig_corr.update_yaxes(range=[-0.5, 0.5], gridcolor="#F2F4F7", row=1, col=2)
        st.plotly_chart(fig_corr, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    # -----------------------------------------------------------------------
    # KHỐI 5: BỘ KHÁM PHÁ BẤT THƯỜNG (TÁCH RIÊNG SỰ KIỆN THẬT VS LỖI CẢM BIẾN L10)
    # -----------------------------------------------------------------------
    st.markdown("##### 5. Bộ khám phá Bất thường & Dịch chuyển Chế độ (`L01`–`L10`, tách riêng Sự kiện thật vs. Lỗi cảm biến AIS)")

    df_out_win = fact_outlier[
        (fact_outlier["observation_date"] >= d_start)
        & (fact_outlier["observation_date"] <= d_end)
        & (fact_outlier["chokepoint_label_code"] != "L00")
    ].copy()
    if sel_region != "Tất cả vùng":
        df_out_win = df_out_win[df_out_win["maritime_region"] == sel_region]

    tab_real, tab_sensor = st.tabs(
        [
            "🌊 Sự kiện Hàng hải & Dịch chuyển Chế độ thật (L01 – L09)",
            "📡 Lỗi Cảm biến / Khuyết Bản tin AIS DWT (L10 — Cần lọc khi tính tải trọng)",
        ]
    )

    with tab_real:
        df_real = df_out_win[df_out_win["chokepoint_label_code"] != "L10"].copy()
        c_f1, c_f2 = st.columns([1.2, 2.8])
        with c_f1:
            phenom_type = st.radio(
                "Phân nhóm động học chuỗi thời gian",
                options=[
                    "Tất cả (L01–L09)",
                    "Cú sốc ngắn hạn I(0) (AO / IO / TC)",
                    "Dịch chuyển chế độ dài hạn (LS — Level Shift)",
                ],
            )
            if phenom_type.startswith("Cú sốc"):
                df_real = df_real[~df_real["chokepoint_ts_label"].str.startswith("LS")]
            elif phenom_type.startswith("Dịch chuyển"):
                df_real = df_real[df_real["chokepoint_ts_label"].str.startswith("LS")]

            lbl_counts = (
                df_real.groupby(["chokepoint_label_code", "chokepoint_ts_label", "chokepoint_domain_label"], as_index=False)
                .agg(so_ngay_cang=("observation_date", "count"), so_cang=("portname", "nunique"))
                .sort_values("so_ngay_cang", ascending=False)
            )
            st.dataframe(lbl_counts, use_container_width=True, hide_index=True, height=210)

        with c_f2:
            avail_codes = sorted(df_real["chokepoint_label_code"].unique().tolist())
            sel_codes = st.multiselect(
                "Lọc theo mã nhãn (L01–L09)",
                options=avail_codes,
                default=avail_codes,
            )
            df_real_filtered = df_real[df_real["chokepoint_label_code"].isin(sel_codes)].sort_values(
                "observation_date", ascending=False
            )
            show_cols = [
                "observation_date",
                "portname",
                "chokepoint_label_code",
                "chokepoint_ts_label",
                "chokepoint_domain_label",
                "n_total",
                "pct_vs_baseline_total",
                "shock_mod_z_90d",
                "struct_mod_z_base",
                "brent_usd_per_bbl",
            ]
            st.dataframe(df_real_filtered[show_cols].head(250), use_container_width=True, hide_index=True, height=210)

    with tab_sensor:
        df_sensor = df_out_win[df_out_win["chokepoint_label_code"] == "L10"].sort_values(
            "observation_date", ascending=False
        )
        st.caption(
            f"Ghi nhận **{len(df_sensor):,} bản ghi (`port-days`)** thuộc nhãn `L10: Telemetry Glitch / AIS Missing DWT / Flatline` "
            "(có lượt tàu `n_total > 0` nhưng tổng trọng tải `capacity = 0` do thiếu bản tin tĩnh AIS Type 5, hoặc tín hiệu đóng băng). "
            "Các bản ghi này được tách riêng để không gây báo động giả về gián đoạn chuỗi cung ứng."
        )
        sensor_cols = [
            "observation_date",
            "portname",
            "n_total",
            "capacity",
            "is_ais_dwt_reporting_anomaly",
            "is_flatline_telemetry_anomaly",
            "chokepoint_domain_label",
        ]
        st.dataframe(df_sensor[sensor_cols], use_container_width=True, hide_index=True, height=220)

    # -----------------------------------------------------------------------
    # KHỐI 6: MỤC MỞ RỘNG "DỮ LIỆU VÀ PHƯƠNG PHÁP" (ĐỘ TƯƠI, FORWARD-FILL, GIỚI HẠN)
    # -----------------------------------------------------------------------
    with st.expander("📚 Dữ liệu & Phương pháp luận: Độ tươi, Ngày điền khuyết (is_forward_filled), Kiểm định tính dừng & Giới hạn"):
        m_c1, m_c2 = st.columns([1.3, 1.7])
        with m_c1:
            total_days = len(fact_energy)
            brent_ffill_days = int(fact_energy["brent_is_ffill"].sum())
            ulsd_ffill_days = int(fact_energy["ulsd_is_ffill"].sum())
            max_brent_trade = pd.to_datetime(fact_energy["brent_last_trading_date"].max()).strftime("%d/%m/%Y")
            max_ulsd_trade = pd.to_datetime(fact_energy["ulsd_last_trading_date"].max()).strftime("%d/%m/%Y")

            st.markdown(
                f"""
                **1. Độ tươi dữ liệu & Trạng thái đồng bộ:**
                - Ngày quan sát hàng hải mới nhất (`IMF PortWatch`): `{max_obs_date.strftime('%d/%m/%Y')}` ({fresh_label}).
                - Phiên giao dịch thực mới nhất (`U.S. EIA`): Brent `{max_brent_trade}` · ULSD `{max_ulsd_trade}`.
                - Tổng số ngày lịch liên tục: `{total_days:,}` ngày (`01/01/2021` – `{max_obs_date.strftime('%d/%m/%Y')}`).

                **2. Tác động của các ngày điền khuyết giá (`is_forward_filled`):**
                - Hoạt động hàng hải diễn ra 365 ngày/năm, nhưng thị trường dầu mỏ nghỉ cuối tuần và ngày lễ:
                  * **Brent (`brent_is_ffill = TRUE`):** `{brent_ffill_days:,} / {total_days:,}` ngày (`{brent_ffill_days*100/total_days:.1f}%`).
                  * **ULSD (`ulsd_is_ffill = TRUE`):** `{ulsd_ffill_days:,} / {total_days:,}` ngày (`{ulsd_ffill_days*100/total_days:.1f}%`).
                - Trên các ngày `is_forward_filled = TRUE`, giá giữ nguyên của phiên trước nên **lợi suất 1 ngày bằng `0%` ($\Delta P_{{1d}} = 0$)**.
                - Nếu tính biến động hoặc phát hiện ngoại lai trên cả ngày nghỉ sẽ làm co hẹp giả tạo độ lệch chuẩn và IQR. Do đó, hệ thống **chỉ kiểm định ngoại lai giá trên các phiên giao dịch thực (`is_ffill = FALSE`)** và dùng **sai phân 7 ngày ($\Delta_7$)** khi xét đồng biến động với lưu lượng tàu.

                **3. Nguồn & Giới hạn đo lường:**
                - Giá Diesel ULSD bờ vịnh Mỹ (`$/gal`) được dùng làm chỉ báo đại diện (proxy), không phải giá dầu nhiên liệu hàng hải (VLSFO/MGO bunker) tại từng cảng.
                - Kho dữ liệu không có biến chi phí cước tàu (Freight Rates) và phụ phí nhiên liệu (BAF).
                """
            )

        with m_c2:
            st.markdown("**Minh họa các ngày điền khuyết (`is_forward_filled = TRUE`) tạo lợi suất bằng 0 trong 90 ngày gần nhất:**")
            df_ff_plot = fact_energy.tail(90).copy()
            obs_pts = df_ff_plot[~df_ff_plot["brent_is_ffill"]]
            ff_pts = df_ff_plot[df_ff_plot["brent_is_ffill"]]

            fig_ff = go.Figure()
            fig_ff.add_trace(
                go.Scatter(
                    x=df_ff_plot["calendar_date"],
                    y=df_ff_plot["brent_usd_per_bbl"],
                    mode="lines",
                    name="Đường giá Brent liên tục (Calendar Spine)",
                    line=dict(color="#98A2B3", width=1.5),
                )
            )
            fig_ff.add_trace(
                go.Scatter(
                    x=obs_pts["calendar_date"],
                    y=obs_pts["brent_usd_per_bbl"],
                    mode="markers",
                    name="Phiên giao dịch thực (is_ffill = False)",
                    marker=dict(color=COLOR_NAVY, size=6),
                )
            )
            fig_ff.add_trace(
                go.Scatter(
                    x=ff_pts["calendar_date"],
                    y=ff_pts["brent_usd_per_bbl"],
                    mode="markers",
                    name="Ngày điền khuyết LOCF (is_ffill = True, ΔP = 0)",
                    marker=dict(color=COLOR_AMBER, size=7, symbol="diamond"),
                )
            )
            fig_ff.update_layout(
                height=260,
                margin=dict(l=6, r=6, t=10, b=6),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=9.5)),
                yaxis_title="Brent ($/bbl)",
                paper_bgcolor="white",
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_ff, use_container_width=True, config={"displayModeBar": False})
