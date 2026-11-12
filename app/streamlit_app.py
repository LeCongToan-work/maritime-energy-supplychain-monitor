"""
streamlit_app.py
----------------
Maritime & Energy Supply Chain Monitor — Streamlit Dashboard (2 Pages)
  - Trang 1: Báo cáo Tổng quan cho Ban điều hành
  - Trang 2: Phân tích Chuỗi Điểm nghẽn, Bản đồ Lưu lượng & Đồng biến động Giá Năng lượng
  - Thanh điều hướng Sidebar bên trái (mặc định thu gọn, bấm '>' để mở)
  - Cả 2 trang dùng chung Bộ lọc Lịch quét khoảng thời gian & Bộ lọc chọn điểm nghẽn
  - Biểu đồ tự động co giãn kích thước theo số lượng đại lượng được chọn
  - Tương thích cả Chế độ Sáng (Light Mode) & Chế độ Tối (Dark Mode)

Nguồn dữ liệu: DuckDB schema `bi_mart` (`data/maritime_dwh.duckdb`) / Parquet `data/gold/*.parquet`.
Chạy ứng dụng:
  venv\\Scripts\\streamlit.exe run app/streamlit_app.py
"""

from __future__ import annotations

from datetime import date
import math
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ---------------------------------------------------------------------------
# Cấu hình trang & CSS thích ứng cả Light Mode & Dark Mode (Sidebar trái, thu gọn mặc định)
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

# Định nghĩa nền thống nhất duy nhất dùng cho CẢ HAI TRANG
BASELINE_START = pd.Timestamp("2021-01-01")
BASELINE_END = pd.Timestamp("2022-12-31")
BASELINE_DEF_TEXT = "Trung bình ngày giai đoạn chuẩn 2 năm: 01/01/2021 – 31/12/2022 (730 ngày)"
MIN_BASELINE_TOTAL = 10.0  # Ngưỡng tối thiểu (tàu/ngày) cho danh sách mặc định tránh nhiễu

# Bảng màu tương phản cao cho cả nền Sáng & nền Tối
COLOR_RED = "#F04438"
COLOR_AMBER = "#F79009"
COLOR_GREEN = "#12B76A"
COLOR_PRIMARY = "#2E90FA"
COLOR_SLATE = "#98A2B3"
COLOR_BLUE = "#38BDF8"
COLOR_TEAL = "#14B8A6"
COLOR_VIOLET = "#A78BFA"
COLOR_PINK = "#F472B6"
COLOR_GRAY_DOT = "#94A3B8"
COLOR_BG_RED = "rgba(240, 68, 56, 0.13)"
COLOR_BG_AMBER = "rgba(247, 144, 9, 0.14)"
COLOR_BG_GREEN = "rgba(18, 183, 106, 0.13)"
GRID_COLOR = "rgba(128, 128, 128, 0.22)"

TRACE_PALETTE = [
    "#F04438",
    "#F79009",
    "#2E90FA",
    "#12B76A",
    "#A78BFA",
    "#14B8A6",
    "#F472B6",
    "#38BDF8",
    "#FB923C",
    "#4ADE80",
]

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.65rem !important;
        padding-bottom: 0.55rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.35rem !important;
    }
    .exec-banner {
        border-radius: 6px;
        padding: 9px 14px;
        margin-bottom: 4px;
        border-left: 5px solid #2E90FA;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 6px;
        font-size: 0.90rem;
        line-height: 1.35;
        color: var(--text-color);
    }
    .kpi-card {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-top: 4px solid #98A2B3;
        border-radius: 6px;
        padding: 8px 11px 5px 11px;
        height: 100%;
    }
    .kpi-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 4px;
        margin-bottom: 2px;
    }
    .kpi-title {
        font-size: 0.74rem;
        font-weight: 700;
        color: var(--text-color);
        opacity: 0.82;
        text-transform: uppercase;
        letter-spacing: 0.02em;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .badge-loss {
        background: rgba(240, 68, 56, 0.16);
        color: #F04438;
        border: 1px solid rgba(240, 68, 56, 0.45);
        border-radius: 999px;
        padding: 1px 7px;
        font-size: 0.67rem;
        font-weight: 700;
        white-space: nowrap;
    }
    .badge-gain {
        background: rgba(18, 183, 106, 0.16);
        color: #12B76A;
        border: 1px solid rgba(18, 183, 106, 0.45);
        border-radius: 999px;
        padding: 1px 7px;
        font-size: 0.67rem;
        font-weight: 700;
        white-space: nowrap;
    }
    .kpi-value {
        font-size: 1.40rem;
        font-weight: 700;
        line-height: 1.15;
    }
    .kpi-delta {
        font-size: 0.74rem;
        color: var(--text-color);
        opacity: 0.78;
        margin-top: 2px;
        margin-bottom: 2px;
    }
    .footer-bar {
        font-size: 0.75rem;
        color: var(--text-color);
        opacity: 0.88;
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 5px;
        padding: 6px 12px;
        margin-top: 4px;
        text-align: center;
        line-height: 1.35;
    }
    .section-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: var(--text-color);
        margin-bottom: 3px;
        padding-bottom: 3px;
        border-bottom: 2px solid rgba(128, 128, 128, 0.28);
    }
    .method-warn {
        background: rgba(247, 144, 9, 0.14);
        border-left: 4px solid #F79009;
        padding: 6px 10px;
        border-radius: 4px;
        font-size: 0.80rem;
        color: var(--text-color);
        margin-bottom: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Tải dữ liệu từ kho `bi_mart`
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


def make_sparkline_svg(values: list[float], stroke_color: str = "#98A2B3", width: int = 210, height: int = 26) -> str:
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


def render_tagged_kpi_card(
    title: str,
    tag_type: str,
    big_value: str,
    delta_text: str,
    spark_vals: list[float],
    status: str = "neutral",
) -> None:
    """Thẻ KPI tích hợp nhãn màu 'Thiệt hại' hoặc 'Lợi ích', thích ứng Sáng/Tối."""
    badge_html = (
        '<span class="badge-loss">● Thiệt hại</span>'
        if tag_type == "loss"
        else '<span class="badge-gain">● Lợi ích</span>'
    )
    border_map = {"critical": COLOR_RED, "warning": COLOR_AMBER, "good": COLOR_GREEN, "neutral": COLOR_PRIMARY}
    bg_map = {
        "critical": "rgba(240, 68, 56, 0.08)",
        "warning": "rgba(247, 144, 9, 0.08)",
        "good": "rgba(18, 183, 106, 0.08)",
        "neutral": "var(--secondary-background-color)",
    }
    val_map = {"critical": COLOR_RED, "warning": COLOR_AMBER, "good": COLOR_GREEN, "neutral": "var(--text-color)"}

    top_color = border_map.get(status, COLOR_SLATE)
    card_bg = bg_map.get(status, "var(--secondary-background-color)")
    val_color = val_map.get(status, "var(--text-color)")
    svg = make_sparkline_svg(spark_vals, stroke_color=top_color)

    st.markdown(
        f"""
        <div class="kpi-card" style="border-top-color: {top_color}; background: {card_bg};">
            <div class="kpi-head">
                <div class="kpi-title">{title}</div>
                {badge_html}
            </div>
            <div class="kpi-value" style="color: {val_color};">{big_value}</div>
            <div class="kpi-delta">{delta_text}</div>
            <div style="margin-top:2px;">{svg}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_shared_footer() -> None:
    """Chân trang dùng chung cho CẢ HAI TRANG với một định nghĩa nền thống nhất."""
    st.markdown(
        f"""
        <div class="footer-bar">
            <b>Định nghĩa nền (Baseline):</b> {BASELINE_DEF_TEXT}.
            &nbsp;·&nbsp; <b>Nguồn:</b> IMF PortWatch (28 điểm nghẽn hàng hải), U.S. EIA API v2 (Brent Europe FOB & Diesel ULSD USGC FOB).
            &nbsp;·&nbsp; <b>Giới hạn:</b> Diesel ULSD là chỉ báo proxy (không phải giá bunker cảng); kho dữ liệu không có cước vận tải (Freight) & phụ phí BAF.
        </div>
        """,
        unsafe_allow_html=True,
    )


def add_event_bands_with_names(
    fig: go.Figure,
    dim_events: pd.DataFrame,
    win_min: pd.Timestamp,
    win_max: pd.Timestamp,
    row: int | None = None,
    col: int | None = None,
) -> None:
    """Đánh dấu vùng sự kiện trên biểu đồ bằng TÊN TIẾNG VIỆT NGẮN."""
    ev_colors = {
        "EVT_01": "rgba(247, 144, 9, 0.16)",
        "EVT_02": "rgba(247, 144, 9, 0.12)",
        "EVT_03": "rgba(240, 68, 56, 0.08)",
        "EVT_04": "rgba(240, 68, 56, 0.17)",
    }
    for _, ev in dim_events.iterrows():
        ev_s = max(ev["start_date"], win_min)
        ev_e = min(ev["end_date"], win_max)
        if ev_e >= win_min and ev_s <= win_max:
            kwargs = dict(
                x0=ev_s,
                x1=ev_e,
                fillcolor=ev_colors.get(ev["event_id"], "rgba(150,150,150,0.12)"),
                line_width=0,
                annotation_text=ev["event_short_label_vi"],
                annotation_position="top left",
                annotation_font_size=10,
            )
            if row is not None and col is not None:
                fig.add_vrect(**kwargs, row=row, col=col)
            else:
                fig.add_vrect(**kwargs)


def parse_calendar_range(date_val, default_start: date, default_end: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Chuẩn hóa kết quả từ bộ lọc lịch quét khoảng thời gian (Calendar range picker)."""
    if isinstance(date_val, (list, tuple)):
        if len(date_val) == 2:
            d0, d1 = date_val[0], date_val[1]
            return (pd.Timestamp(min(d0, d1)), pd.Timestamp(max(d0, d1)))
        if len(date_val) == 1:
            d0 = pd.Timestamp(date_val[0])
            return d0, max(d0, pd.Timestamp(default_end))
    elif date_val is not None:
        d0 = pd.Timestamp(date_val)
        return d0, max(d0, pd.Timestamp(default_end))
    return pd.Timestamp(default_start), pd.Timestamp(default_end)


def calc_legend_top_margin(n_traces: int, base_top: int = 28) -> int:
    """Tính khoảng trống phía trên để chú giải tự xuống dòng không đè lên tiêu đề biểu đồ."""
    legend_rows = max(1, math.ceil(n_traces / 4))
    return base_top + (legend_rows - 1) * 20


# ---------------------------------------------------------------------------
# Khởi tạo dữ liệu & Độ tươi
# ---------------------------------------------------------------------------
data = load_bi_mart_data()
dim_chokepoints = data["dim_chokepoints"]
dim_events = data["dim_events"]
fact_energy = data["fact_energy"]
fact_transit = data["fact_transit"]
fact_regime = data["fact_regime"]
fact_rerouting = data["fact_rerouting"]
fact_outlier = data["fact_outlier"]

min_obs_ts = fact_transit["observation_date"].min()
max_obs_ts = fact_transit["observation_date"].max()
min_obs_date = min_obs_ts.date()
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

all_chokepoint_names = dim_chokepoints.sort_values("baseline_n_total", ascending=False)["portname"].tolist()
default_focus_ports = ["Bab el-Mandeb Strait", "Suez Canal", "Strait of Hormuz"]


# ---------------------------------------------------------------------------
# SIDEBAR BÊN TRÁI (Mặc định thu gọn, bấm '>' để mở toàn bộ điều hướng & bộ lọc)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🧭 Điều hướng & Bộ lọc")
    page = st.radio(
        "Chọn trang hiển thị",
        options=[
            "Trang 1 · Tổng quan Điều hành",
            "Trang 2 · Phân tích Điểm nghẽn",
        ],
        index=0,
    )

    st.divider()

    cal_val = st.date_input(
        "📅 Khoảng thời gian (Quét trên lịch)",
        value=(date(2023, 11, 19), max_obs_date),
        min_value=min_obs_date,
        max_value=max_obs_date,
        format="DD/MM/YYYY",
        key="shared_calendar_range",
    )
    win_start, win_end = parse_calendar_range(cal_val, date(2023, 11, 19), max_obs_date)
    win_desc = f"{win_start.strftime('%d/%m/%Y')} – {win_end.strftime('%d/%m/%Y')}"

    selected_ports = st.multiselect(
        "📍 Chọn điểm nghẽn theo dõi",
        options=all_chokepoint_names,
        default=default_focus_ports,
        key="shared_ports_multiselect",
    )

    if page.startswith("Trang 2"):
        vessel_choice = st.radio(
            "🚢 Loại tàu phân tích",
            options=["Tổng", "Tanker", "Container"],
            horizontal=True,
            key="p2_vessel_choice",
        )
    else:
        vessel_choice = "Tổng"

    st.divider()
    st.markdown(
        f"""
        <div style="font-size:0.78rem; color:var(--text-color); opacity:0.86; line-height:1.45;">
            <b>Trạng thái dữ liệu:</b><br/>
            Cập nhật đến: <code>{max_obs_date.strftime('%d/%m/%Y')}</code><br/>
            <span style="color:{fresh_color}; font-weight:700;">{fresh_label}</span>
            <hr style="margin:6px 0; border-color:rgba(128,128,128,0.25);"/>
            <b>Định nghĩa nền (Baseline):</b><br/>
            {BASELINE_DEF_TEXT}
        </div>
        """,
        unsafe_allow_html=True,
    )


if not selected_ports:
    st.warning("👈 Vui lòng mở thanh điều hướng bên trái (bấm `>`) và chọn ít nhất 1 điểm nghẽn để hiển thị dữ liệu.")
    render_shared_footer()
    st.stop()


# ===========================================================================
# TRANG 1: BÁO CÁO TỔNG QUAN CHO BAN ĐIỀU HÀNH
# ===========================================================================
if page.startswith("Trang 1"):
    p1_start, p1_end, p1_window_desc = win_start, win_end, win_desc
    selected_ports_p1 = selected_ports

    df_rr_win = fact_rerouting[
        (fact_rerouting["observation_date"] >= p1_start) & (fact_rerouting["observation_date"] <= p1_end)
    ].copy()
    df_en_win = fact_energy[
        (fact_energy["calendar_date"] >= p1_start) & (fact_energy["calendar_date"] <= p1_end)
    ].copy()
    df_tr_win = fact_transit[
        (fact_transit["observation_date"] >= p1_start) & (fact_transit["observation_date"] <= p1_end)
    ].copy()

    base_map = dim_chokepoints.set_index("portname")["baseline_n_total"].to_dict()
    pre_en = fact_energy[(fact_energy["calendar_date"] >= BASELINE_START) & (fact_energy["calendar_date"] <= BASELINE_END)]
    pre_rr = fact_rerouting[
        (fact_rerouting["observation_date"] >= BASELINE_START) & (fact_rerouting["observation_date"] <= BASELINE_END)
    ]
    base_brent = float(pre_en["brent_usd_per_bbl"].mean())
    base_cape = float(base_map["Cape of Good Hope"])
    base_cape_share = float(pre_rr["cape_rerouting_share_total_pct"].mean())

    # Tính chỉ số riêng cho các điểm nghẽn được chọn
    df_sel_tr = df_tr_win[df_tr_win["portname"].isin(selected_ports_p1)].copy()
    sel_stats = (
        df_sel_tr.groupby("portname")
        .agg(
            avg_flow=("n_total", "mean"),
            pct_vs_base=("pct_vs_baseline_total", "mean"),
        )
        .reset_index()
        .sort_values("pct_vs_base")
    )
    group_avg_pct = float(sel_stats["pct_vs_base"].mean())
    worst_sel_row = sel_stats.iloc[0]
    worst_port_name = str(worst_sel_row["portname"])
    worst_port_pct = float(worst_sel_row["pct_vs_base"])

    # Cảnh báo High/Critical toàn hệ thống (trong ngày cuối của khoảng lịch chọn)
    end_tr = fact_transit[fact_transit["observation_date"] == df_tr_win["observation_date"].max()].copy()
    alert_ports = end_tr[end_tr["daily_alert_severity"].isin(["High", "Critical"])].sort_values(
        "pct_vs_baseline_total"
    )
    n_alert_ports = len(alert_ports)
    top3_alert_str = (
        ", ".join(
            f"{r['portname'].replace(' Strait', '').replace(' Canal', '')} ({r['pct_vs_baseline_total']:+.0f}%)"
            for _, r in alert_ports.head(3).iterrows()
        )
        or "Không có điểm nghẽn vượt ngưỡng"
    )

    cape_win_avg = float(df_rr_win["cape_n_total"].mean())
    cape_pct_vs_base = float(df_tr_win.loc[df_tr_win["portname"] == "Cape of Good Hope", "pct_vs_baseline_total"].mean())
    cape_share_win = float(df_rr_win["cape_rerouting_share_total_pct"].mean())
    cape_share_delta = cape_share_win - base_cape_share

    latest_en = df_en_win.iloc[-1] if not df_en_win.empty else fact_energy.iloc[-1]
    latest_brent = float(latest_en["brent_usd_per_bbl"])
    brent_ref_ts = latest_en["calendar_date"] - pd.Timedelta(days=30)
    brent_30d_series = fact_energy.loc[fact_energy["calendar_date"] <= brent_ref_ts, "brent_usd_per_bbl"]
    brent_30d_ref = float(brent_30d_series.iloc[-1]) if not brent_30d_series.empty else base_brent
    brent_30d_pct = (latest_brent - brent_30d_ref) * 100.0 / brent_30d_ref
    latest_vol_30d = float(latest_en["brent_volatility_30d"])
    brent_vs_base_pct = (latest_brent - base_brent) * 100.0 / base_brent

    # [A] Câu kết luận tự sinh
    if group_avg_pct <= -25.0 or worst_port_pct <= -35.0 or n_alert_ports >= 5:
        banner_bg, banner_border, severity_tag = COLOR_BG_RED, COLOR_RED, "CẢNH BÁO CAO"
    elif group_avg_pct <= -10.0 or n_alert_ports >= 2:
        banner_bg, banner_border, severity_tag = COLOR_BG_AMBER, COLOR_AMBER, "CẢNH BÁO TRUNG BÌNH"
    else:
        banner_bg, banner_border, severity_tag = COLOR_BG_GREEN, COLOR_GREEN, "ỔN ĐỊNH"

    auto_conclusion = (
        f"<b>[{severity_tag} · {p1_window_desc}]</b> "
        f"<b>{n_alert_ports}/28 điểm nghẽn</b> đang cảnh báo (nặng nhất toàn cầu: <b>{top3_alert_str}</b>); "
        f"Nhóm đang chọn ({len(selected_ports_p1)} điểm) lệch TB <b>{group_avg_pct:+.1f}%</b> vs nền; "
        f"<b>{cape_share_win:.1f}%</b> tàu Á–Âu đi vòng Mũi Hảo Vọng; "
        f"Brent <b>${latest_brent:.2f}/bbl</b> ({brent_30d_pct:+.1f}% 30d)."
    )

    st.markdown(
        f"""
        <div class="exec-banner" style="background:{banner_bg}; border-left-color:{banner_border};">
            <div>{auto_conclusion}</div>
            <div style="font-size:0.79rem; font-weight:600; opacity:0.9;">
                Dữ liệu đến: <code>{max_obs_date.strftime('%d/%m/%Y')}</code> &nbsp;
                <span style="color:{fresh_color}; font-weight:700;">{fresh_label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Thẻ KPI thích ứng theo đúng các điểm nghẽn đang chọn + Brent + Thẻ lợi ích duy nhất (Cape)
    step_s = max(1, len(df_en_win) // 55)
    if len(selected_ports_p1) <= 2:
        kpi_cols = st.columns(len(selected_ports_p1) + 2)
        for idx, pname in enumerate(selected_ports_p1):
            p_sub = df_sel_tr[df_sel_tr["portname"] == pname].sort_values("observation_date")
            p_pct = float(p_sub["pct_vs_baseline_total"].mean())
            p_avg = float(p_sub["n_total"].mean())
            p_base = float(base_map[pname])
            sp_vals = ((p_sub["n_total_ma7"] - p_base) * 100.0 / p_base).iloc[::step_s].tolist()
            tag_t = "loss" if p_pct < 0 else "gain"
            st_lvl = "critical" if p_pct <= -30 else ("warning" if p_pct <= -10 else "good")
            with kpi_cols[idx]:
                render_tagged_kpi_card(
                    title=pname,
                    tag_type=tag_t,
                    big_value=f"{p_pct:+.1f}%",
                    delta_text=f"TB kỳ: {p_avg:.1f} tàu/ng vs nền {p_base:.1f}",
                    spark_vals=sp_vals,
                    status=st_lvl,
                )
        col_brent, col_cape = kpi_cols[-2], kpi_cols[-1]
    else:
        kpi_cols = st.columns(4)
        # Card 1: Điểm giảm sâu nhất trong nhóm chọn
        p_worst_sub = df_sel_tr[df_sel_tr["portname"] == worst_port_name].sort_values("observation_date")
        p_worst_base = float(base_map[worst_port_name])
        sp_worst = ((p_worst_sub["n_total_ma7"] - p_worst_base) * 100.0 / p_worst_base).iloc[::step_s].tolist()
        with kpi_cols[0]:
            render_tagged_kpi_card(
                title=f"Nặng nhất: {worst_port_name}",
                tag_type="loss" if worst_port_pct < 0 else "gain",
                big_value=f"{worst_port_pct:+.1f}%",
                delta_text=f"TB kỳ: {float(worst_sel_row['avg_flow']):.1f} vs nền {p_worst_base:.1f} tàu/ng",
                spark_vals=sp_worst,
                status="critical" if worst_port_pct <= -30 else ("warning" if worst_port_pct <= -10 else "good"),
            )
        # Card 2: Trung bình nhóm chọn
        grp_ts = df_sel_tr.groupby("observation_date")["pct_vs_baseline_total"].mean().sort_index()
        with kpi_cols[1]:
            render_tagged_kpi_card(
                title=f"TB nhóm chọn ({len(selected_ports_p1)} điểm)",
                tag_type="loss" if group_avg_pct < 0 else "gain",
                big_value=f"{group_avg_pct:+.1f}%",
                delta_text="Chênh lệch lưu lượng TB so với nền",
                spark_vals=grp_ts.iloc[::step_s].tolist(),
                status="critical" if group_avg_pct <= -25 else ("warning" if group_avg_pct <= -10 else "good"),
            )
        col_brent, col_cape = kpi_cols[2], kpi_cols[3]

    with col_brent:
        sp_brent = df_en_win["brent_ma7"].iloc[::step_s].tolist()
        render_tagged_kpi_card(
            title="Giá dầu Brent ($/bbl)",
            tag_type="loss",
            big_value=f"${latest_brent:.2f}",
            delta_text=f"30d: {brent_30d_pct:+.1f}% · vs nền: {brent_vs_base_pct:+.1f}% · Vol {latest_vol_30d:.2f}%",
            spark_vals=sp_brent,
            status="critical" if latest_brent >= 100 else ("warning" if brent_30d_pct >= 10 else "neutral"),
        )

    with col_cape:
        sp_cape = ((df_rr_win["cape_ma7_total"] - base_cape) * 100.0 / base_cape).iloc[::step_s].tolist()
        render_tagged_kpi_card(
            title="Tuyến đi vòng Mũi Hảo Vọng",
            tag_type="gain",
            big_value=f"{cape_pct_vs_base:+.1f}%",
            delta_text=f"{base_cape:.0f} → {cape_win_avg:.0f} tàu/ng · Hấp thụ {cape_share_win:.1f}%",
            spark_vals=sp_cape,
            status="good" if cape_pct_vs_base >= 20 else "neutral",
        )

    # Biểu đồ chính Trang 1: Chạy riêng theo đúng danh sách selected_ports_p1 & TỰ RESIZE theo số lượng đường
    n_p1_traces = len(selected_ports_p1)
    p1_height = min(740, max(370, 325 + n_p1_traces * 24 + calc_legend_top_margin(n_p1_traces + 2, base_top=0)))

    fig_c = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.09,
        row_heights=[0.55, 0.45],
        subplot_titles=(
            f"Lưu lượng {n_p1_traces} điểm nghẽn đang chọn (% lệch MA7 so với nền 2021–2022)",
            "Đồng biến động Giá dầu Brent & Diesel ULSD proxy ($/bbl)",
        ),
    )

    for i, pname in enumerate(selected_ports_p1):
        sub_p = df_sel_tr[df_sel_tr["portname"] == pname].sort_values("observation_date")
        p_base = float(base_map[pname])
        y_pct = (sub_p["n_total_ma7"] - p_base) * 100.0 / p_base if p_base > 0 else 0.0
        fig_c.add_trace(
            go.Scatter(
                x=sub_p["observation_date"],
                y=y_pct,
                name=pname,
                line=dict(color=TRACE_PALETTE[i % len(TRACE_PALETTE)], width=2.0),
            ),
            row=1,
            col=1,
        )
    fig_c.add_hline(y=0, line_dash="dot", line_color=COLOR_SLATE, row=1, col=1)

    fig_c.add_trace(
        go.Scatter(
            x=df_en_win["calendar_date"],
            y=df_en_win["brent_usd_per_bbl"],
            name="Brent ($/bbl)",
            line=dict(color=COLOR_PRIMARY, width=2.2),
        ),
        row=2,
        col=1,
    )
    fig_c.add_trace(
        go.Scatter(
            x=df_en_win["calendar_date"],
            y=df_en_win["ulsd_usd_per_bbl"],
            name="Diesel ULSD proxy ($/bbl = $/gal × 42)",
            line=dict(color=COLOR_TEAL, width=1.7, dash="dot"),
        ),
        row=2,
        col=1,
    )

    add_event_bands_with_names(fig_c, dim_events, win_min=p1_start, win_max=p1_end)

    fig_c.update_layout(
        height=p1_height,
        margin=dict(l=8, r=8, t=calc_legend_top_margin(n_p1_traces + 2, base_top=32), b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=10.5)),
        hovermode="x unified",
    )
    fig_c.update_annotations(font_size=11.5)
    fig_c.update_xaxes(gridcolor=GRID_COLOR)
    fig_c.update_yaxes(title_text="% vs nền", gridcolor=GRID_COLOR, row=1, col=1, title_font=dict(size=10))
    fig_c.update_yaxes(title_text="USD / bbl", gridcolor=GRID_COLOR, row=2, col=1, title_font=dict(size=10))
    st.plotly_chart(fig_c, width="stretch", config={"displayModeBar": False})

    render_shared_footer()


# ===========================================================================
# TRANG 2: PHÂN TÍCH ĐIỂM NGHẼN, BẢN ĐỒ LƯU LƯỢNG & GIÁ NĂNG LƯỢNG
# ===========================================================================
else:
    st_start, st_end = win_start, win_end
    selected_ports_p2 = selected_ports
    vessel_cfg = {
        "Tổng": ("n_total", "baseline_n_total", "baseline_sd_n_total", "Tổng số tàu"),
        "Tanker": ("n_tanker", "baseline_n_tanker", "baseline_sd_n_tanker", "Tàu chở dầu (Tanker)"),
        "Container": ("n_container", "baseline_n_container", "baseline_sd_n_container", "Tàu Container"),
    }
    v_col, v_base_col, v_sd_col, v_desc = vessel_cfg[vessel_choice]

    base_v_map = dim_chokepoints.set_index("portname")[v_base_col].to_dict()
    sd_v_map = dim_chokepoints.set_index("portname")[v_sd_col].to_dict()

    # Dữ liệu cho toàn bộ 28 điểm nghẽn trong khoảng lịch chọn (phục vụ bản đồ toàn cầu) & tập con đã chọn
    df_win_all = fact_transit[
        (fact_transit["observation_date"] >= st_start) & (fact_transit["observation_date"] <= st_end)
    ].copy()
    df_win_all["v_pct_base"] = df_win_all.apply(
        lambda r: (r[v_col] - base_v_map[r["portname"]]) * 100.0 / base_v_map[r["portname"]]
        if base_v_map.get(r["portname"], 0) > 0
        else np.nan,
        axis=1,
    )

    df_win_sel = df_win_all[df_win_all["portname"].isin(selected_ports_p2)].copy()
    port_order = (
        df_win_sel.groupby("portname")["v_pct_base"]
        .mean()
        .reindex(selected_ports_p2)
        .sort_values(ascending=True)
        .index.tolist()
    )

    # -----------------------------------------------------------------------
    # HÀNG TRÊN: BẢN ĐỒ NHIỆT THEO TUẦN  |  DIỄN BIẾN LƯU LƯỢNG VS DẢI NỀN & AIS
    # -----------------------------------------------------------------------
    top_c1, top_c2 = st.columns([1.0, 1.15])

    with top_c1:
        st.markdown(
            f'<div class="section-title">Biến động lưu lượng theo tuần tại các điểm nghẽn đã chọn ({v_desc})</div>',
            unsafe_allow_html=True,
        )
        df_hm = df_win_sel.copy()
        df_hm["week_start"] = df_hm["observation_date"].dt.to_period("W").apply(lambda r: r.start_time)
        hm_piv = (
            df_hm.groupby(["portname", "week_start"])["v_pct_base"]
            .mean()
            .unstack("week_start")
            .reindex(port_order)
            .dropna(how="all")
            .round(1)
        )

        # Tự co giãn chiều cao Heatmap theo số lượng điểm nghẽn được chọn
        n_hm_rows = len(hm_piv.index)
        hm_height = min(680, max(210, 115 + n_hm_rows * 36))

        fig_hm = go.Figure(
            data=go.Heatmap(
                z=hm_piv.values,
                x=hm_piv.columns,
                y=hm_piv.index,
                colorscale=[
                    [0.0, "#D92D20"],
                    [0.32, "#F79009"],
                    [0.50, "#94A3B8"],
                    [0.75, "#32D583"],
                    [1.0, "#039855"],
                ],
                zmin=-80,
                zmax=80,
                colorbar=dict(title="% nền", thickness=10, len=0.9),
                hovertemplate="Điểm nghẽn: %{y}<br>Tuần: %{x|%d/%m/%Y}<br>Lệch vs nền: %{z:+.1f}%<extra></extra>",
            )
        )
        fig_hm.update_layout(
            height=hm_height,
            margin=dict(l=4, r=4, t=8, b=4),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(autorange="reversed", tickfont=dict(size=10.5)),
            xaxis=dict(tickfont=dict(size=9.5)),
        )
        st.plotly_chart(fig_hm, width="stretch", config={"displayModeBar": False})

    with top_c2:
        # Diễn biến lưu lượng thực tế vs dải nền & chấm xám nghi lỗi AIS (tự resize theo số lượng đại lượng)
        n_sel = len(selected_ports_p2)
        q2_height = min(680, max(280, 235 + n_sel * 26 + calc_legend_top_margin(n_sel + 2, 0)))

        if n_sel == 1:
            single_port = selected_ports_p2[0]
            st.markdown(
                f'<div class="section-title">Diễn biến lưu lượng tại <code>{single_port}</code> so với dải nền & cảnh báo nghi lỗi AIS</div>',
                unsafe_allow_html=True,
            )
            sel_base_mean = float(base_v_map[single_port])
            sel_base_sd = float(sd_v_map[single_port]) if pd.notna(sd_v_map[single_port]) else 0.0
            band_low = max(0.0, sel_base_mean - sel_base_sd)
            band_high = sel_base_mean + sel_base_sd

            df_q2_tr = fact_transit[
                (fact_transit["portname"] == single_port)
                & (fact_transit["observation_date"] >= st_start)
                & (fact_transit["observation_date"] <= st_end)
            ][["observation_date", v_col]].copy()
            df_q2_lbl = fact_outlier[fact_outlier["portname"] == single_port][
                ["observation_date", "chokepoint_label_code"]
            ]
            df_q2 = pd.merge(df_q2_tr, df_q2_lbl, on="observation_date", how="left").sort_values("observation_date")
            df_q2["v_ma7"] = df_q2[v_col].rolling(7, min_periods=1).mean()
            df_q2_glitch = df_q2[df_q2["chokepoint_label_code"] == "L10"]

            fig_q2 = go.Figure()
            fig_q2.add_trace(
                go.Scatter(
                    x=pd.concat([df_q2["observation_date"], df_q2["observation_date"][::-1]]),
                    y=[band_high] * len(df_q2) + [band_low] * len(df_q2),
                    fill="toself",
                    fillcolor="rgba(152, 162, 179, 0.22)",
                    line=dict(color="rgba(255,255,255,0)"),
                    name=f"Dải nền 2021–2022 (±1 SD: {band_low:.0f}–{band_high:.0f})",
                    hoverinfo="skip",
                )
            )
            fig_q2.add_hline(
                y=sel_base_mean,
                line_dash="dash",
                line_color=COLOR_SLATE,
                annotation_text=f"Nền TB: {sel_base_mean:.1f}",
                annotation_position="bottom right",
                annotation_font_size=10,
            )
            fig_q2.add_trace(
                go.Scatter(
                    x=df_q2["observation_date"],
                    y=df_q2[v_col],
                    name="Lưu lượng ngày",
                    line=dict(color="rgba(148, 163, 184, 0.45)", width=1.0),
                )
            )
            fig_q2.add_trace(
                go.Scatter(
                    x=df_q2["observation_date"],
                    y=df_q2["v_ma7"],
                    name=f"MA7 ({v_desc})",
                    line=dict(color=COLOR_PRIMARY, width=2.3),
                )
            )
            fig_q2.add_trace(
                go.Scatter(
                    x=df_q2_glitch["observation_date"],
                    y=df_q2_glitch[v_col],
                    mode="markers",
                    name=f"Nghi lỗi AIS (L10: {len(df_q2_glitch)} ngày)",
                    marker=dict(color=COLOR_GRAY_DOT, size=7, symbol="circle", line=dict(color="#FFFFFF", width=0.8)),
                )
            )
            y_title_q2 = "Tàu / ngày"
        else:
            st.markdown(
                f'<div class="section-title">Diễn biến lưu lượng nhóm {n_sel} điểm nghẽn đã chọn (% lệch MA7 so với nền & nghi lỗi AIS)</div>',
                unsafe_allow_html=True,
            )
            df_q2_lbl_all = fact_outlier[
                (fact_outlier["portname"].isin(selected_ports_p2))
                & (fact_outlier["observation_date"] >= st_start)
                & (fact_outlier["observation_date"] <= st_end)
                & (fact_outlier["chokepoint_label_code"] == "L10")
            ][["observation_date", "portname"]].copy()

            fig_q2 = go.Figure()
            glitch_x, glitch_y, glitch_txt = [], [], []
            for idx, pname in enumerate(port_order):
                sub = df_win_sel[df_win_sel["portname"] == pname].sort_values("observation_date").copy()
                pbase = float(base_v_map.get(pname, 0.0))
                sub["ma7"] = sub[v_col].rolling(7, min_periods=1).mean()
                sub["pct_ma7"] = (sub["ma7"] - pbase) * 100.0 / pbase if pbase > 0 else np.nan
                fig_q2.add_trace(
                    go.Scatter(
                        x=sub["observation_date"],
                        y=sub["pct_ma7"],
                        name=pname,
                        line=dict(color=TRACE_PALETTE[idx % len(TRACE_PALETTE)], width=2.0),
                    )
                )
                g_sub = sub.merge(df_q2_lbl_all[df_q2_lbl_all["portname"] == pname], on="observation_date", how="inner")
                if not g_sub.empty:
                    glitch_x.extend(g_sub["observation_date"].tolist())
                    glitch_y.extend(g_sub["pct_ma7"].tolist())
                    glitch_txt.extend([pname] * len(g_sub))

            fig_q2.add_hline(y=0, line_dash="dot", line_color=COLOR_SLATE, annotation_text="Nền (0%)", annotation_font_size=10)
            fig_q2.add_trace(
                go.Scatter(
                    x=glitch_x,
                    y=glitch_y,
                    text=glitch_txt,
                    mode="markers",
                    name=f"Nghi lỗi AIS (L10: {len(glitch_x)} điểm)",
                    marker=dict(color=COLOR_GRAY_DOT, size=7, symbol="circle", line=dict(color="#FFFFFF", width=0.8)),
                    hovertemplate="%{text}<br>Ngày: %{x|%d/%m/%Y}<br>Lệch nền: %{y:+.1f}% (Nghi lỗi AIS)<extra></extra>",
                )
            )
            y_title_q2 = "% lệch MA7 vs nền"

        add_event_bands_with_names(fig_q2, dim_events, win_min=st_start, win_max=st_end)
        fig_q2.update_layout(
            height=q2_height,
            margin=dict(l=6, r=6, t=calc_legend_top_margin(n_sel + 2, 16), b=6),
            yaxis_title=y_title_q2,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=9.5)),
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_q2.update_xaxes(gridcolor=GRID_COLOR)
        fig_q2.update_yaxes(gridcolor=GRID_COLOR)
        st.plotly_chart(fig_q2, width="stretch", config={"displayModeBar": False})

    # -----------------------------------------------------------------------
    # HÀNG DƯỚI: BẢN ĐỒ PHÂN BỐ LƯU LƯỢNG BẰNG DẤU CHẤM  |  ĐỒNG BIẾN ĐỘNG GIÁ
    # -----------------------------------------------------------------------
    bot_c1, bot_c2 = st.columns([1.05, 1.10])

    with bot_c1:
        st.markdown(
            f'<div class="section-title">Bản đồ phân bố lưu lượng & biến động tại các điểm nghẽn ({v_desc})</div>',
            unsafe_allow_html=True,
        )
        map_agg = (
            df_win_all.groupby("portname", as_index=False)
            .agg(avg_flow=(v_col, "mean"), avg_pct=("v_pct_base", "mean"))
            .merge(dim_chokepoints[["portname", "latitude", "longitude", "maritime_region"]], on="portname", how="left")
        )
        map_agg["is_selected"] = map_agg["portname"].isin(selected_ports_p2)
        map_agg["avg_pct_clean"] = map_agg["avg_pct"].fillna(0.0).clip(-80, 80)

        # Quy mô chấm tỉ lệ trực tiếp theo lưu lượng thực tế
        max_flow = max(1.0, float(map_agg["avg_flow"].max()))
        map_agg["dot_size"] = 10.0 + (map_agg["avg_flow"] / max_flow) * 28.0

        unsel_df = map_agg[~map_agg["is_selected"]]
        sel_df = map_agg[map_agg["is_selected"]]

        fig_map = go.Figure()
        # Các điểm nghẽn còn lại làm nền bối cảnh (chấm mờ nhỏ hơn)
        if not unsel_df.empty:
            fig_map.add_trace(
                go.Scattergeo(
                    lon=unsel_df["longitude"],
                    lat=unsel_df["latitude"],
                    text=unsel_df["portname"],
                    customdata=np.stack([unsel_df["avg_flow"], unsel_df["avg_pct_clean"]], axis=-1),
                    mode="markers",
                    name="Điểm nghẽn khác (tham chiếu)",
                    marker=dict(
                        size=unsel_df["dot_size"] * 0.72,
                        color=unsel_df["avg_pct_clean"],
                        colorscale=[[0.0, "#F04438"], [0.45, "#F79009"], [0.55, "#94A3B8"], [1.0, "#12B76A"]],
                        cmin=-70,
                        cmax=70,
                        opacity=0.35,
                        line=dict(width=0.6, color="rgba(148,163,184,0.6)"),
                    ),
                    hovertemplate="<b>%{text}</b><br>TB lưu lượng: %{customdata[0]:.1f} tàu/ng<br>So với nền: %{customdata[1]:+.1f}%<extra></extra>",
                )
            )

        # Các điểm nghẽn đang được chọn trong bộ lọc (chấm đậm nổi bật kèm tên)
        fig_map.add_trace(
            go.Scattergeo(
                lon=sel_df["longitude"],
                lat=sel_df["latitude"],
                text=sel_df.apply(lambda r: f"{r['portname']} ({r['avg_pct_clean']:+.0f}%)", axis=1),
                customdata=np.stack([sel_df["avg_flow"], sel_df["avg_pct_clean"]], axis=-1),
                mode="markers+text",
                textposition="top center",
                textfont=dict(size=9.5),
                name=f"Đang chọn ({len(sel_df)} điểm)",
                marker=dict(
                    size=sel_df["dot_size"],
                    color=sel_df["avg_pct_clean"],
                    colorscale=[[0.0, "#F04438"], [0.45, "#F79009"], [0.55, "#94A3B8"], [1.0, "#12B76A"]],
                    cmin=-70,
                    cmax=70,
                    opacity=0.95,
                    colorbar=dict(title="% nền", thickness=10, len=0.78),
                    line=dict(width=2.0, color="#2E90FA"),
                ),
                hovertemplate="<b>%{text}</b><br>TB lưu lượng: %{customdata[0]:.1f} tàu/ng<br>So với nền: %{customdata[1]:+.1f}%<extra></extra>",
            )
        )

        map_height = min(540, max(350, 325 + len(sel_df) * 12))
        fig_map.update_layout(
            height=map_height,
            margin=dict(l=4, r=4, t=8, b=4),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0, font=dict(size=9.5)),
            geo=dict(
                projection_type="natural earth",
                showland=True,
                landcolor="rgba(148, 163, 184, 0.22)",
                showcoastlines=True,
                coastlinecolor="rgba(148, 163, 184, 0.55)",
                showcountries=True,
                countrycolor="rgba(148, 163, 184, 0.25)",
                showocean=True,
                oceancolor="rgba(0,0,0,0)",
                bgcolor="rgba(0,0,0,0)",
                lataxis=dict(range=[-58, 72]),
            ),
        )
        st.plotly_chart(fig_map, width="stretch", config={"displayModeBar": False})
        st.caption("Kích thước dấu chấm tỉ lệ với lưu lượng tàu/ngày; màu đỏ/vàng thể hiện mức sụt giảm so với nền, màu xanh là tăng.")

    with bot_c2:
        st.markdown(
            '<div class="section-title">Đồng biến động lưu lượng điểm nghẽn đã chọn và giá nhiên liệu (chuẩn hóa = 100 tại đầu kỳ)</div>',
            unsafe_allow_html=True,
        )
        df_en_p2 = fact_energy[
            (fact_energy["calendar_date"] >= st_start) & (fact_energy["calendar_date"] <= st_end)
        ].sort_values("calendar_date").copy()

        # Tự resize theo số lượng đại lượng vẽ
        n_q4_traces = len(port_order) + 2
        q4_height = min(560, max(320, 275 + len(port_order) * 20 + calc_legend_top_margin(n_q4_traces, 0)))

        fig_q4 = go.Figure()
        for idx, pname in enumerate(port_order):
            sub_q4 = df_win_sel[df_win_sel["portname"] == pname].sort_values("observation_date").copy()
            sub_q4["v_ma7"] = sub_q4[v_col].rolling(7, min_periods=1).mean()
            first_valid = sub_q4["v_ma7"].loc[sub_q4["v_ma7"] > 0]
            ref_v = float(first_valid.iloc[0]) if not first_valid.empty else 1.0
            sub_q4["idx_flow"] = (sub_q4["v_ma7"] / ref_v) * 100.0
            fig_q4.add_trace(
                go.Scatter(
                    x=sub_q4["observation_date"],
                    y=sub_q4["idx_flow"],
                    name=f"{pname} (Idx)",
                    line=dict(color=TRACE_PALETTE[idx % len(TRACE_PALETTE)], width=1.9),
                )
            )

        brent_ref = float(df_en_p2["brent_usd_per_bbl"].iloc[0]) if not df_en_p2.empty else 1.0
        ulsd_ref = float(df_en_p2["ulsd_usd_per_gal"].iloc[0]) if not df_en_p2.empty else 1.0
        fig_q4.add_trace(
            go.Scatter(
                x=df_en_p2["calendar_date"],
                y=(df_en_p2["brent_usd_per_bbl"] / brent_ref) * 100.0,
                name="Brent (Idx = 100)",
                line=dict(color=COLOR_PRIMARY, width=2.4),
            )
        )
        fig_q4.add_trace(
            go.Scatter(
                x=df_en_p2["calendar_date"],
                y=(df_en_p2["ulsd_usd_per_gal"] / ulsd_ref) * 100.0,
                name="Diesel ULSD (Idx = 100)",
                line=dict(color=COLOR_TEAL, width=1.9, dash="dot"),
            )
        )
        fig_q4.add_hline(y=100, line_dash="dot", line_color=COLOR_SLATE)
        add_event_bands_with_names(fig_q4, dim_events, win_min=st_start, win_max=st_end)

        fig_q4.update_layout(
            height=q4_height,
            margin=dict(l=6, r=6, t=calc_legend_top_margin(n_q4_traces, 16), b=6),
            yaxis_title="Chỉ số chuẩn hóa (Đầu kỳ = 100)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=9.5)),
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_q4.update_xaxes(gridcolor=GRID_COLOR)
        fig_q4.update_yaxes(gridcolor=GRID_COLOR)
        st.plotly_chart(fig_q4, width="stretch", config={"displayModeBar": False})
        st.caption("⚠️ Chỉ số trên phản ánh *đồng biến động* trong khoảng lịch đã chọn, **không kết luận quan hệ nhân quả**.")

    # -----------------------------------------------------------------------
    # [MỞ RỘNG] BỎ CRACK SPREAD — GIỮ TƯƠNG QUAN ĐỘ TRỄ, MÔ PHỎNG CHI PHÍ, CHẤT LƯỢNG DỮ LIỆU
    # -----------------------------------------------------------------------
    with st.expander("🔧 Mở rộng: Tương quan có độ trễ · Mô phỏng chi phí đi vòng (giả định) · Chất lượng dữ liệu"):
        ext_tabs = st.tabs(
            [
                "📉 Tương quan có độ trễ (Chuỗi sai phân dừng)",
                "🧮 Mô phỏng chi phí đi vòng (Theo giả định)",
                "🔬 Chất lượng dữ liệu (AIS L10 & Ngày điền khuyết)",
            ]
        )

        # Tab 1: Tương quan có độ trễ trên chuỗi sai phân dừng Δ7
        with ext_tabs[0]:
            st.markdown(
                """
                <div class="method-warn">
                    ⚠️ <b>Cảnh báo phương pháp:</b> Tương quan tính trên <b>chuỗi sai phân tuần dừng I(0) (Δ7)</b>
                    để tránh tương quan giả của chuỗi mức giá I(1); chỉ phản ánh <b>đồng biến động</b>, không phải nhân quả.
                </div>
                """,
                unsafe_allow_html=True,
            )
            corr_port = (
                st.selectbox("Chọn 1 điểm nghẽn trong nhóm để xem độ trễ", options=port_order, index=0)
                if len(port_order) > 1
                else port_order[0]
            )
            df_reg_p = fact_regime[
                (fact_regime["portname"] == corr_port)
                & (fact_regime["observation_date"] >= st_start)
                & (fact_regime["observation_date"] <= st_end)
            ].copy()

            flow_diff_col = "n_tanker_diff_7d" if vessel_choice == "Tanker" else "n_total_diff_7d"
            roll_brent_col = "rolling_corr_90d_diff7d_brent" if vessel_choice == "Tanker" else "rolling_corr_90d_total_diff7d_brent"
            roll_ulsd_col = "rolling_corr_90d_diff7d_ulsd" if vessel_choice == "Tanker" else "rolling_corr_90d_total_diff7d_ulsd"

            lags = list(range(-14, 15))
            ccf_b, ccf_u = [], []
            for k in lags:
                sf = df_reg_p[flow_diff_col]
                ccf_b.append(float(sf.corr(df_reg_p["brent_diff_7d"].shift(-k))) if sf.notna().sum() > 20 else 0.0)
                ccf_u.append(float(sf.corr(df_reg_p["ulsd_diff_7d"].shift(-k))) if sf.notna().sum() > 20 else 0.0)

            fig_lag = make_subplots(
                rows=1,
                cols=2,
                column_widths=[0.56, 0.44],
                subplot_titles=(
                    f"Tương quan lăn 90d trên Δ7 ({corr_port})",
                    "Tương quan trễ (Lag k = -14..+14 ngày)",
                ),
            )
            fig_lag.add_trace(
                go.Scatter(x=df_reg_p["observation_date"], y=df_reg_p[roll_brent_col], name="Corr 90d vs Brent Δ7", line=dict(color=COLOR_PRIMARY, width=1.8)),
                row=1, col=1,
            )
            fig_lag.add_trace(
                go.Scatter(x=df_reg_p["observation_date"], y=df_reg_p[roll_ulsd_col], name="Corr 90d vs ULSD Δ7", line=dict(color=COLOR_TEAL, width=1.6)),
                row=1, col=1,
            )
            fig_lag.add_hline(y=0, line_dash="dot", line_color=COLOR_SLATE, row=1, col=1)
            fig_lag.add_trace(go.Bar(x=lags, y=ccf_b, name="CCF Brent Δ7", marker_color=COLOR_PRIMARY), row=1, col=2)
            fig_lag.add_trace(go.Bar(x=lags, y=ccf_u, name="CCF ULSD Δ7", marker_color=COLOR_TEAL), row=1, col=2)
            fig_lag.update_layout(height=260, margin=dict(l=6, r=6, t=26, b=6), barmode="group", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
            fig_lag.update_xaxes(gridcolor=GRID_COLOR)
            fig_lag.update_yaxes(gridcolor=GRID_COLOR)
            st.plotly_chart(fig_lag, width="stretch", config={"displayModeBar": False})

        # Tab 2: Mô phỏng chi phí nhiên liệu đi vòng (theo giả định)
        with ext_tabs[1]:
            st.caption(
                "⚠️ **Ước tính theo giả định, không phải số đo:** Kho dữ liệu không chứa cước tàu, phụ phí BAF hay mức tiêu hao thực tế. "
                "Người dùng tự điều chỉnh giả định để quy đổi tham khảo:"
            )
            s_c1, s_c2, s_c3 = st.columns(3)
            with s_c1:
                extra_days = st.slider(
                    "Số ngày đi vòng thêm",
                    min_value=5,
                    max_value=18,
                    value=10,
                    help="Nguồn giả định: UNCTAD (2024) ước tính hải trình Á–Âu vòng Mũi Hảo Vọng tăng thêm ~10–14 ngày.",
                )
            with s_c2:
                tons_per_day = st.slider(
                    "Tiêu hao (tấn/ngày)",
                    min_value=20,
                    max_value=120,
                    value=45,
                    help="Nguồn giả định: IMO Fourth GHG Study (2020) cho tàu thương mại cỡ trung.",
                )
            with s_c3:
                proxy_ton = round(float(fact_energy["ulsd_usd_per_gal"].iloc[-1]) * 315.0, -1)
                fuel_price_ton = st.slider(
                    "Giá nhiên liệu ($/tấn)",
                    min_value=400,
                    max_value=1200,
                    value=int(min(max(proxy_ton, 400), 1200)),
                    step=10,
                    help="Quy đổi xấp xỉ từ giá ULSD mới nhất (1 tấn ≈ 315 gallon).",
                )
            est_cost = extra_days * tons_per_day * fuel_price_ton
            st.markdown(
                f"👉 **Chi phí nhiên liệu tăng thêm ước tính (theo giả định):** "
                f"`${est_cost:,.0f} / chuyến` (`{extra_days} ngày × {tons_per_day} tấn/ngày × ${fuel_price_ton}/tấn`)."
            )

        # Tab 3: Chất lượng dữ liệu (Lỗi AIS L10 + Forward-fill)
        with ext_tabs[2]:
            q_c1, q_c2 = st.columns([1.1, 1.3])
            with q_c1:
                total_days = len(fact_energy)
                brent_ff = int(fact_energy["brent_is_ffill"].sum())
                ulsd_ff = int(fact_energy["ulsd_is_ffill"].sum())
                df_l10 = fact_outlier[
                    (fact_outlier["chokepoint_label_code"] == "L10")
                    & (fact_outlier["portname"].isin(selected_ports_p2))
                ].sort_values("observation_date", ascending=False)
                st.markdown(
                    f"""
                    - **Lỗi cảm biến AIS trong nhóm điểm nghẽn đã chọn (`L10`):** `{len(df_l10):,}` bản ghi `port-days`
                      (lưu lượng `n_total > 0` nhưng `capacity = 0` hoặc đóng băng tín hiệu).
                    - **Ngày điền khuyết giá (`is_forward_filled = TRUE`):** Brent `{brent_ff:,}/{total_days:,}` ngày (`{brent_ff*100/total_days:.1f}%`),
                      ULSD `{ulsd_ff:,}/{total_days:,}` ngày (`{ulsd_ff*100/total_days:.1f}%`). Các ngày này tạo lợi suất 1 ngày bằng `0%` nên hệ thống
                      chỉ kiểm định ngoại lai trên phiên giao dịch thực (`is_ffill = FALSE`).
                    """
                )
                st.dataframe(
                    df_l10[
                        [
                            "observation_date",
                            "portname",
                            "n_total",
                            "capacity",
                            "is_ais_dwt_reporting_anomaly",
                            "is_flatline_telemetry_anomaly",
                        ]
                    ].head(100),
                    width="stretch",
                    hide_index=True,
                    height=180,
                )

            with q_c2:
                df_ff = fact_energy.tail(90).copy()
                df_ff["ret_1d"] = df_ff["brent_usd_per_bbl"].pct_change().fillna(0.0) * 100.0
                obs_pts = df_ff[~df_ff["brent_is_ffill"]]
                ff_pts = df_ff[df_ff["brent_is_ffill"]]

                fig_ff = make_subplots(
                    rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10, row_heights=[0.55, 0.45],
                    subplot_titles=("Giá Brent 90 ngày gần nhất", "Lợi suất ΔP 1 ngày (%) — Ngày điền khuyết = 0%"),
                )
                fig_ff.add_trace(go.Scatter(x=df_ff["calendar_date"], y=df_ff["brent_usd_per_bbl"], name="Giá Brent", line=dict(color=COLOR_SLATE, width=1.4)), row=1, col=1)
                fig_ff.add_trace(go.Scatter(x=ff_pts["calendar_date"], y=ff_pts["brent_usd_per_bbl"], mode="markers", name="Ngày điền khuyết LOCF", marker=dict(color=COLOR_AMBER, size=6, symbol="diamond")), row=1, col=1)
                fig_ff.add_trace(go.Bar(x=obs_pts["calendar_date"], y=obs_pts["ret_1d"], name="Phiên thực (ΔP ≠ 0)", marker_color=COLOR_PRIMARY), row=2, col=1)
                fig_ff.add_trace(go.Scatter(x=ff_pts["calendar_date"], y=ff_pts["ret_1d"], mode="markers", name="Điền khuyết (ΔP = 0%)", marker=dict(color=COLOR_AMBER, size=6, symbol="diamond")), row=2, col=1)
                fig_ff.update_layout(height=275, margin=dict(l=6, r=6, t=22, b=6), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
                fig_ff.update_xaxes(gridcolor=GRID_COLOR)
                fig_ff.update_yaxes(gridcolor=GRID_COLOR)
                st.plotly_chart(fig_ff, width="stretch", config={"displayModeBar": False})

    render_shared_footer()
