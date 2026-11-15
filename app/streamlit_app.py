"""
streamlit_app.py
----------------
Maritime & Energy Supply Chain Monitor — Streamlit Dashboard (2 Pages)
  - Trang 1: Báo cáo Tổng quan cho Ban điều hành
  - Trang 2: Phân tích Điểm nghẽn, Bản đồ Hành lang Đổi tuyến & Đồng biến động Giá Năng lượng (I(1) & I(0))
  - Thanh điều hướng Sidebar bên trái (mặc định thu gọn, bấm '>' để mở)
  - Cả 2 trang dùng chung Bộ lọc Lịch quét khoảng thời gian & Bộ lọc chọn điểm nghẽn
  - Biểu đồ tự động co giãn kích thước theo số lượng đại lượng được chọn
  - Tương thích cả Chế độ Sáng (Light Mode) & Chế độ Tối (Dark Mode)

Nguồn dữ liệu: MotherDuck (`md:maritime_dwh`, schema `bi_mart`) khi có `MOTHERDUCK_TOKEN`,
tự động fallback về DuckDB local (`data/maritime_dwh.duckdb`) hoặc Parquet (`data/gold/*.parquet`).
Chạy ứng dụng:
  venv\\Scripts\\streamlit.exe run app/streamlit_app.py
"""

from __future__ import annotations

from datetime import date
import logging
import math
import os
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
    page_title="Oil monitor",
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
    "#A78BFA",
    "#12B76A",
    "#F472B6",
    "#38BDF8",
    "#FB923C",
    "#4ADE80",
]

ROLE_VI_MAP = {
    "Origin Energy Export Hub": "Yết hầu xuất khẩu năng lượng (Không có tuyến biển thay thế)",
    "Global Transit Corridor": "Hành lang quá cảnh liên lục địa (Có tuyến đi vòng thay thế)",
    "Rerouting Alternative": "Tuyến đường vòng thay thế hấp thụ lưu lượng",
    "Regional Maritime Passage": "Eo biển hàng hải nội vùng",
}

ROLE_SHORT_VI = {
    "Origin Energy Export Hub": "Yết hầu xuất khẩu",
    "Global Transit Corridor": "Hành lang quá cảnh",
    "Rerouting Alternative": "Tuyến thay thế",
    "Regional Maritime Passage": "Eo biển khu vực",
}

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 2.8rem !important;
        padding-bottom: 0.65rem !important;
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
        max-width: 100% !important;
    }
    header[data-testid="stHeader"] {
        background: transparent !important;
        height: 2.5rem !important;
        z-index: 10 !important;
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
        margin-bottom: 2px;
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
    .corridor-box {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-left: 4px solid #14B8A6;
        border-radius: 5px;
        padding: 6px 10px;
        font-size: 0.78rem;
        color: var(--text-color);
        line-height: 1.4;
        margin-top: 2px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Tải dữ liệu từ kho `bi_mart` (Ưu tiên MotherDuck Cloud -> DuckDB Local -> Parquet)
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
MOTHERDUCK_DATABASE = os.getenv("MOTHERDUCK_DATABASE", "maritime_dwh")


def _get_motherduck_token() -> str | None:
    """Lấy MOTHERDUCK_TOKEN từ biến môi trường hoặc Streamlit Secrets (hỗ trợ .env cục bộ)."""
    token = os.getenv("MOTHERDUCK_TOKEN") or os.getenv("motherduck_token")
    if token:
        return token.strip()

    try:
        secret_token = st.secrets.get("MOTHERDUCK_TOKEN") or st.secrets.get("motherduck_token")
        if secret_token:
            return str(secret_token).strip()
    except Exception:
        pass

    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
        token = os.getenv("MOTHERDUCK_TOKEN") or os.getenv("motherduck_token")
        if token:
            return token.strip()
    except Exception:
        pass

    return None


def _fetch_bi_mart_from_duckdb(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    """Truy vấn đầy đủ 8 bảng `bi_mart` dùng chung cho cả MotherDuck Cloud và DuckDB Local."""
    return {
        "dim_chokepoints": con.execute("SELECT * FROM bi_mart.dim_chokepoints").fetchdf(),
        "dim_events": con.execute("SELECT * FROM bi_mart.dim_geopolitical_events ORDER BY start_date").fetchdf(),
        "dim_rerouting_map": con.execute(
            "SELECT * FROM bi_mart.dim_chokepoint_rerouting_map ORDER BY primary_portid"
        ).fetchdf(),
        "fact_energy": con.execute("SELECT * FROM bi_mart.fact_energy_prices_daily ORDER BY calendar_date").fetchdf(),
        "fact_transit": con.execute(
            "SELECT * FROM bi_mart.fact_chokepoint_transit_daily ORDER BY portid, observation_date"
        ).fetchdf(),
        "fact_regime": con.execute(
            "SELECT * FROM bi_mart.fact_chokepoint_energy_regime_daily ORDER BY portid, observation_date"
        ).fetchdf(),
        "fact_rerouting": con.execute(
            "SELECT * FROM bi_mart.fact_red_sea_cape_rerouting_daily ORDER BY observation_date"
        ).fetchdf(),
        "fact_outlier": con.execute(
            "SELECT * FROM bi_mart.fact_outlier_consensus_labeled_daily ORDER BY portid, observation_date"
        ).fetchdf(),
    }


@st.cache_data(ttl=1800)
def load_bi_mart_data() -> dict[str, pd.DataFrame]:
    dataset: dict[str, pd.DataFrame] | None = None
    md_token = _get_motherduck_token()

    # 1. Ưu tiên đọc từ MotherDuck Cloud
    if md_token:
        try:
            os.environ["motherduck_token"] = md_token
            con = duckdb.connect(f"md:{MOTHERDUCK_DATABASE}")
            try:
                dataset = _fetch_bi_mart_from_duckdb(con)
            finally:
                con.close()
        except Exception as exc:
            logger.warning(f"Không kết nối được MotherDuck ({exc}), thử fallback dữ liệu local.")

    # 2. Fallback 1: DuckDB Local
    if dataset is None and DUCKDB_PATH.exists():
        con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
        try:
            dataset = _fetch_bi_mart_from_duckdb(con)
        finally:
            con.close()

    # 3. Fallback 2: Parquet Gold Local
    if dataset is None:
        required_parquets = {
            "dim_chokepoints": GOLD_DIR / "dim_chokepoints.parquet",
            "dim_events": GOLD_DIR / "dim_geopolitical_events.parquet",
            "dim_rerouting_map": GOLD_DIR / "dim_chokepoint_rerouting_map.parquet",
            "fact_energy": GOLD_DIR / "fct_energy_prices_daily.parquet",
            "fact_transit": GOLD_DIR / "fct_chokepoint_transit_daily.parquet",
            "fact_regime": GOLD_DIR / "mart_chokepoint_energy_regime_daily.parquet",
            "fact_rerouting": GOLD_DIR / "mart_red_sea_cape_rerouting_daily.parquet",
            "fact_outlier": GOLD_DIR / "mart_outlier_consensus_labeled_daily.parquet",
        }
        if not all(p.exists() for p in required_parquets.values()):
            raise RuntimeError(
                "Không thể tải dữ liệu từ MotherDuck và không tìm thấy kho dữ liệu local. "
                "Vui lòng kiểm tra lại MOTHERDUCK_TOKEN trong Streamlit Secrets."
            )
        dataset = {key: pd.read_parquet(path) for key, path in required_parquets.items()}

    for key, col in [
        ("fact_energy", "calendar_date"),
        ("fact_transit", "observation_date"),
        ("fact_regime", "observation_date"),
        ("fact_rerouting", "observation_date"),
        ("fact_outlier", "observation_date"),
        ("dim_events", "start_date"),
        ("dim_events", "end_date"),
    ]:
        dataset[key][col] = pd.to_datetime(dataset[key][col])

    return dataset


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


def render_kpi_card(
    title: str,
    big_value: str,
    delta_text: str,
    spark_vals: list[float],
    status: str = "neutral",
) -> None:
    """Thẻ KPI gọn: Tiêu đề, số lớn, chênh lệch vs nền & sparkline thích ứng Sáng/Tối."""
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
            <div class="kpi-title">{title}</div>
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
            &nbsp;·&nbsp; <b>Phương pháp luận:</b> Kiểm định đồng thuận kép (Modified Z-Score MAD &gt; 3.5 ∧ Tukey IQR Fence); tương quan trượt 90 ngày tính trên chuỗi sai phân dừng I(0) (Δ7 ngày); loại trừ ngày nghỉ điền khuyết (LOCF) khi kiểm định cú sốc giá 1 ngày.
            &nbsp;·&nbsp; <b>Giới hạn:</b> Diesel ULSD là chỉ báo proxy (không phải giá bunker cảng); kho dữ liệu không có cước vận tải (Freight) &amp; phụ phí BAF.
        </div>
        """,
        unsafe_allow_html=True,
    )


def add_event_bands_with_names(
    fig: go.Figure,
    dim_events: pd.DataFrame,
    win_min: pd.Timestamp,
    win_max: pd.Timestamp,
    n_rows: int = 1,
) -> None:
    """Đánh dấu vùng sự kiện bằng TÊN TIẾNG VIỆT NGẮN, tự giãn tầng dọc khi trùng mốc để không đè chữ."""
    ev_colors = {
        "EVT_01": "rgba(247, 144, 9, 0.16)",
        "EVT_02": "rgba(247, 144, 9, 0.12)",
        "EVT_03": "rgba(240, 68, 56, 0.08)",
        "EVT_04": "rgba(240, 68, 56, 0.17)",
    }
    placed_anchors: list[tuple[pd.Timestamp, int]] = []
    for _, ev in dim_events.iterrows():
        ev_s = max(ev["start_date"], win_min)
        ev_e = min(ev["end_date"], win_max)
        if ev_e >= win_min and ev_s <= win_max:
            tier = 0
            while any(abs((ev_s - px).days) < 260 and t == tier for px, t in placed_anchors):
                tier += 1
            placed_anchors.append((ev_s, tier))

            fill_c = ev_colors.get(ev["event_id"], "rgba(150,150,150,0.12)")
            if n_rows > 1:
                for r in range(1, n_rows + 1):
                    if r == 1:
                        fig.add_vrect(
                            x0=ev_s,
                            x1=ev_e,
                            fillcolor=fill_c,
                            line_width=0,
                            annotation_text=ev["event_short_label_vi"],
                            annotation_position="top left",
                            annotation=dict(font_size=10, yshift=-2 - tier * 16),
                            row=r,
                            col=1,
                        )
                    else:
                        fig.add_vrect(x0=ev_s, x1=ev_e, fillcolor=fill_c, line_width=0, row=r, col=1)
            else:
                fig.add_vrect(
                    x0=ev_s,
                    x1=ev_e,
                    fillcolor=fill_c,
                    line_width=0,
                    annotation_text=ev["event_short_label_vi"],
                    annotation_position="top left",
                    annotation=dict(font_size=10, yshift=-2 - tier * 16),
                )


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
dim_rerouting_map = data["dim_rerouting_map"]
fact_energy = data["fact_energy"]
fact_transit = data["fact_transit"]
fact_regime = data["fact_regime"]
fact_rerouting = data["fact_rerouting"]
fact_outlier = data["fact_outlier"]

role_map = dim_chokepoints.set_index("portname")["chokepoint_role"].to_dict()
tanker_share_map = dim_chokepoints.set_index("portname")["avg_tanker_share_pct"].to_dict()

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
available_years = sorted(fact_transit["observation_date"].dt.year.unique().tolist())

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

    time_mode = st.radio(
        "⏱️ Cách chọn thời gian",
        options=["📅 Quét trên lịch", "🗓️ Chọn Năm & Tháng"],
        horizontal=True,
        key="shared_time_mode",
    )

    if time_mode == "🗓️ Chọn Năm & Tháng":
        col_y, col_m = st.columns(2)
        with col_y:
            sel_year = st.selectbox(
                "Năm",
                options=["Tất cả"] + [str(y) for y in available_years],
                index=len(available_years),  # Mặc định năm gần nhất
                key="shared_sel_year",
            )
        with col_m:
            month_opts = ["Tất cả"] + [f"Tháng {m:02d}" for m in range(1, 13)]
            sel_month = st.selectbox(
                "Tháng",
                options=month_opts,
                index=0,
                key="shared_sel_month",
            )

        if sel_year == "Tất cả":
            win_start = min_obs_ts
            win_end = max_obs_ts
        else:
            yr = int(sel_year)
            if sel_month == "Tất cả":
                win_start = pd.Timestamp(f"{yr}-01-01")
                win_end = min(pd.Timestamp(f"{yr}-12-31"), max_obs_ts)
            else:
                mo = int(sel_month.replace("Tháng ", ""))
                start_dt = pd.Timestamp(year=yr, month=mo, day=1)
                end_dt = (start_dt + pd.offsets.MonthEnd(1))
                win_start = max(start_dt, min_obs_ts)
                win_end = min(end_dt, max_obs_ts)
        win_desc = f"{win_start.strftime('%d/%m/%Y')} – {win_end.strftime('%d/%m/%Y')}"
    else:
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
    worst_port_role_vi = ROLE_SHORT_VI.get(role_map.get(worst_port_name, ""), "")

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

    latest_en = df_en_win.iloc[-1] if not df_en_win.empty else fact_energy.iloc[-1]
    latest_brent = float(latest_en["brent_usd_per_bbl"])
    latest_crack = float(latest_en["diesel_brent_crack_bbl"])
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
        f"Brent <b>${latest_brent:.2f}/bbl</b> ({brent_30d_pct:+.1f}% 30d) · Crack <b>${latest_crack:.2f}/bbl</b>."
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

    # Thẻ KPI thích ứng theo đúng các điểm nghẽn đang chọn (giữ nguyên cấu trúc ban đầu) + Brent + Mũi Hảo Vọng
    step_s = max(1, len(df_en_win) // 55)
    if len(selected_ports_p1) <= 2:
        kpi_cols = st.columns(len(selected_ports_p1) + 2)
        for idx, pname in enumerate(selected_ports_p1):
            p_sub = df_sel_tr[df_sel_tr["portname"] == pname].sort_values("observation_date")
            p_pct = float(p_sub["pct_vs_baseline_total"].mean())
            p_avg = float(p_sub["n_total"].mean())
            p_base = float(base_map[pname])
            p_role_short = ROLE_SHORT_VI.get(role_map.get(pname, ""), "")
            sp_vals = ((p_sub["n_total_ma7"] - p_base) * 100.0 / p_base).iloc[::step_s].tolist()
            st_lvl = "critical" if p_pct <= -30 else ("warning" if p_pct <= -10 else "good")
            with kpi_cols[idx]:
                render_kpi_card(
                    title=pname,
                    big_value=f"{p_pct:+.1f}%",
                    delta_text=f"{p_role_short} · TB: {p_avg:.1f} vs nền {p_base:.1f} tàu/ngày",
                    spark_vals=sp_vals,
                    status=st_lvl,
                )
        col_brent, col_cape = kpi_cols[-2], kpi_cols[-1]
    else:
        kpi_cols = st.columns(4)
        p_worst_sub = df_sel_tr[df_sel_tr["portname"] == worst_port_name].sort_values("observation_date")
        p_worst_base = float(base_map[worst_port_name])
        sp_worst = ((p_worst_sub["n_total_ma7"] - p_worst_base) * 100.0 / p_worst_base).iloc[::step_s].tolist()
        with kpi_cols[0]:
            render_kpi_card(
                title=f"Nặng nhất: {worst_port_name}",
                big_value=f"{worst_port_pct:+.1f}%",
                delta_text=f"{worst_port_role_vi} · TB: {float(worst_sel_row['avg_flow']):.1f} vs nền {p_worst_base:.1f} tàu/ngày",
                spark_vals=sp_worst,
                status="critical" if worst_port_pct <= -30 else ("warning" if worst_port_pct <= -10 else "good"),
            )
        grp_ts = df_sel_tr.groupby("observation_date")["pct_vs_baseline_total"].mean().sort_index()
        with kpi_cols[1]:
            render_kpi_card(
                title=f"TB nhóm chọn ({len(selected_ports_p1)} điểm)",
                big_value=f"{group_avg_pct:+.1f}%",
                delta_text="Chênh lệch lưu lượng TB so với nền 2021–2022",
                spark_vals=grp_ts.iloc[::step_s].tolist(),
                status="critical" if group_avg_pct <= -25 else ("warning" if group_avg_pct <= -10 else "good"),
            )
        col_brent, col_cape = kpi_cols[2], kpi_cols[3]

    with col_brent:
        sp_brent = df_en_win["brent_ma7"].iloc[::step_s].tolist()
        render_kpi_card(
            title="Giá dầu Brent ($/bbl)",
            big_value=f"${latest_brent:.2f}",
            delta_text=f"30d: {brent_30d_pct:+.1f}% · vs nền: {brent_vs_base_pct:+.1f}% · Vol {latest_vol_30d:.2f}%",
            spark_vals=sp_brent,
            status="critical" if latest_brent >= 100 else ("warning" if brent_30d_pct >= 10 else "neutral"),
        )

    with col_cape:
        sp_cape = ((df_rr_win["cape_ma7_total"] - base_cape) * 100.0 / base_cape).iloc[::step_s].tolist()
        render_kpi_card(
            title="Tuyến đi vòng Mũi Hảo Vọng",
            big_value=f"{cape_pct_vs_base:+.1f}%",
            delta_text=f"{base_cape:.0f} → {cape_win_avg:.0f} tàu/ngày · Hấp thụ {cape_share_win:.1f}%",
            spark_vals=sp_cape,
            status="good" if cape_pct_vs_base >= 20 else "neutral",
        )

    # Biểu đồ chính Trang 1: Chạy riêng theo đúng danh sách selected_ports_p1 & TỰ RESIZE theo số lượng đường
    n_p1_traces = len(selected_ports_p1)
    p1_height = min(760, max(395, 350 + n_p1_traces * 24 + calc_legend_top_margin(n_p1_traces + 3, base_top=0)))

    fig_c = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.10,
        row_heights=[0.55, 0.45],
        subplot_titles=(
            f"Lưu lượng {n_p1_traces} điểm nghẽn đang chọn (% lệch MA7 so với nền 2021–2022)",
            "Đồng biến động Giá dầu thô Brent, Diesel ULSD proxy & Biên lọc dầu Crack Spread ($/bbl)",
        ),
    )

    for i, pname in enumerate(selected_ports_p1):
        sub_p = df_sel_tr[df_sel_tr["portname"] == pname].sort_values("observation_date")
        p_base = float(base_map[pname])
        p_role_vi = ROLE_SHORT_VI.get(role_map.get(pname, ""), "")
        y_pct = (sub_p["n_total_ma7"] - p_base) * 100.0 / p_base if p_base > 0 else 0.0
        fig_c.add_trace(
            go.Scatter(
                x=sub_p["observation_date"],
                y=y_pct,
                name=f"{pname} ({p_role_vi})" if p_role_vi else pname,
                line=dict(color=TRACE_PALETTE[i % len(TRACE_PALETTE)], width=2.0),
                hovertemplate=f"<b>{pname}</b> ({p_role_vi})<br>Lệch MA7 vs nền: %{{y:+.1f}}%<extra></extra>",
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
    fig_c.add_trace(
        go.Scatter(
            x=df_en_win["calendar_date"],
            y=df_en_win["diesel_brent_crack_bbl"],
            name="Crack Spread (ULSD − Brent, $/bbl)",
            line=dict(color=COLOR_AMBER, width=1.5, dash="dash"),
        ),
        row=2,
        col=1,
    )

    add_event_bands_with_names(fig_c, dim_events, win_min=p1_start, win_max=p1_end, n_rows=2)

    fig_c.update_layout(
        height=p1_height,
        margin=dict(l=8, r=8, t=calc_legend_top_margin(n_p1_traces + 3, base_top=48), b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="right", x=1, font=dict(size=10.2)),
        hovermode="x unified",
    )
    fig_c.update_annotations(font_size=11.5)
    fig_c.update_xaxes(gridcolor=GRID_COLOR)
    fig_c.update_yaxes(title_text="% vs nền", gridcolor=GRID_COLOR, row=1, col=1, title_font=dict(size=10))
    fig_c.update_yaxes(title_text="USD / bbl", gridcolor=GRID_COLOR, row=2, col=1, title_font=dict(size=10))
    st.plotly_chart(fig_c, width="stretch", config={"displayModeBar": False})

    render_shared_footer()


# ===========================================================================
# TRANG 2: PHÂN TÍCH ĐIỂM NGHẼN, BẢN ĐỒ HÀNH LANG ĐỔI TUYẾN & GIÁ NĂNG LƯỢNG
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
    # HÀNG KPI TRANG 2: THEO ĐÚNG SỐ LƯỢNG TÀU, ĐỊA ĐIỂM & ĐỒNG BỘ NỘI DUNG 4 BIỂU ĐỒ PHÍA DƯỚI
    # -----------------------------------------------------------------------
    p2_step_s = max(1, len(df_win_sel) // (55 * max(1, len(selected_ports_p2))))
    worst_p2 = port_order[0] if port_order else ""
    best_p2 = port_order[-1] if port_order else ""

    p2_kpi_c1, p2_kpi_c2, p2_kpi_c3, p2_kpi_c4 = st.columns(4)

    with p2_kpi_c1:
        # KPI 1: Thể hiện điểm nghẽn giảm mạnh nhất (dẫn dắt Biểu đồ 1 & 2)
        w_df = df_win_sel[df_win_sel["portname"] == worst_p2].sort_values("observation_date")
        w_avg = float(w_df[v_col].mean()) if not w_df.empty else 0.0
        w_pct = float(w_df["v_pct_base"].mean()) if not w_df.empty else 0.0
        w_base = float(base_v_map.get(worst_p2, 0.0))
        w_role = ROLE_SHORT_VI.get(role_map.get(worst_p2, ""), "")
        w_sp = w_df[v_col].rolling(7, min_periods=1).mean().iloc[::p2_step_s].tolist()
        render_kpi_card(
            title=f"ĐIỂM NGHẼN NẶNG NHẤT: {worst_p2}",
            big_value=f"{w_avg:.1f} tàu/ngày",
            delta_text=f"Lệch vs nền: {w_pct:+.1f}% (Nền {w_base:.1f} tàu/ngày) · {w_role}",
            spark_vals=w_sp,
            status="critical" if w_pct <= -25 else ("warning" if w_pct <= -10 else "neutral"),
        )

    with p2_kpi_c2:
        # KPI 2: Thể hiện chất lượng dữ liệu & tín hiệu cảnh báo AIS (dẫn dắt Chấm xám / Vàng trên Biểu đồ 2)
        df_p2_out = fact_outlier[
            (fact_outlier["portname"].isin(selected_ports_p2))
            & (fact_outlier["observation_date"] >= st_start)
            & (fact_outlier["observation_date"] <= st_end)
        ]
        n_p2_glitch = int((df_p2_out["chokepoint_label_code"] == "L10").sum())
        n_p2_shocks = int(df_p2_out["is_shock_consensus_outlier"].fillna(False).sum())
        n_p2_struct = int(df_p2_out["is_struct_consensus_outlier"].fillna(False).sum())
        render_kpi_card(
            title=f"TÍN HIỆU CẢNH BÁO ({len(selected_ports_p2)} ĐIỂM)",
            big_value=f"{n_p2_shocks} cú sốc",
            delta_text=f"{n_p2_struct} ngày đổi chế độ · {n_p2_glitch} ngày nghi lỗi AIS (L10)",
            spark_vals=[0, n_p2_glitch, n_p2_shocks, n_p2_struct],
            status="warning" if (n_p2_shocks + n_p2_glitch) > 0 else "good",
        )

    with p2_kpi_c3:
        # KPI 3: Thể hiện hành lang đổi tuyến thay thế (dẫn dắt Bản đồ số 3)
        p2_reroutes = dim_rerouting_map[dim_rerouting_map["primary_portname"].isin(selected_ports_p2)]
        alt_names_p2 = [str(a) for a in p2_reroutes["alt_portname"].dropna().unique().tolist() if str(a).strip() != ""]
        if alt_names_p2:
            alt_df_p2 = fact_transit[
                (fact_transit["portname"].isin(alt_names_p2))
                & (fact_transit["observation_date"] >= st_start)
                & (fact_transit["observation_date"] <= st_end)
            ]
            alt_avg_flow = float(alt_df_p2[v_col].mean()) if not alt_df_p2.empty else 0.0
            alt_pct = float(alt_df_p2["pct_vs_baseline_total"].mean()) if not alt_df_p2.empty else 0.0
            render_kpi_card(
                title=f"TUYẾN THAY THẾ: {alt_names_p2[0]}",
                big_value=f"{alt_avg_flow:.1f} tàu/ngày",
                delta_text=f"Lưu lượng tăng {alt_pct:+.1f}% vs nền · Hấp thụ tải",
                spark_vals=alt_df_p2[v_col].rolling(7, min_periods=1).mean().iloc[::p2_step_s].tolist(),
                status="good" if alt_pct >= 20 else "neutral",
            )
        else:
            render_kpi_card(
                title="HÀNH LANG THAY THẾ TRÊN BIỂN",
                big_value="KHÔNG CÓ",
                delta_text="Yết hầu xuất khẩu độc đạo (Nguồn cung bị nghẽn trực tiếp)",
                spark_vals=[0, 0, 0, 0],
                status="critical",
            )

    with p2_kpi_c4:
        # KPI 4: Thể hiện liên hệ với giá năng lượng (dẫn dắt Biểu đồ số 4)
        latest_en_p2 = fact_energy[
            (fact_energy["calendar_date"] >= st_start) & (fact_energy["calendar_date"] <= st_end)
        ]
        brent_now = float(latest_en_p2["brent_usd_per_bbl"].iloc[-1]) if not latest_en_p2.empty else 0.0
        brent_first = float(latest_en_p2["brent_usd_per_bbl"].iloc[0]) if not latest_en_p2.empty else brent_now
        brent_chg = (brent_now - brent_first) * 100.0 / brent_first if brent_first > 0 else 0.0
        crack_now = float(latest_en_p2["diesel_brent_crack_bbl"].iloc[-1]) if not latest_en_p2.empty else 0.0
        render_kpi_card(
            title="GIÁ NĂNG LƯỢNG KỲ NÀY",
            big_value=f"${brent_now:.2f}",
            delta_text=f"So với đầu kỳ: {brent_chg:+.1f}% · Biên lọc dầu: ${crack_now:.2f}/thùng",
            spark_vals=latest_en_p2["brent_usd_per_bbl"].iloc[::p2_step_s].tolist(),
            status="critical" if brent_now >= 100 else ("warning" if brent_chg >= 10 else "neutral"),
        )

    # -----------------------------------------------------------------------
    # HÀNG TRÊN: BẢN ĐỒ NHIỆT THEO TUẦN  |  DIỄN BIẾN LƯU LƯỢNG VS DẢI NỀN & ĐỒNG THUẬN KÉP (L01-L10)
    # -----------------------------------------------------------------------
    top_c1, top_c2 = st.columns([1.0, 1.15])

    with top_c1:
        st.markdown(
            f'<div class="section-title">Lưu lượng tàu qua các điểm nghẽn đã chọn ({v_desc})</div>',
            unsafe_allow_html=True,
        )
        chart_mode_c1 = st.radio(
            "Kiểu biểu đồ",
            options=["📊 Biểu đồ Cột (Lưu lượng / So với nền)", "🗺️ Bản đồ nhiệt (Heatmap theo tuần)"],
            horizontal=True,
            key="p2_chart_mode_c1",
            label_visibility="collapsed",
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

        # Tính tổng/trung bình tàu theo tuần cho biểu đồ cột
        flow_piv = (
            df_hm.groupby(["portname", "week_start"])[v_col]
            .mean()
            .unstack("week_start")
            .reindex(port_order)
            .round(1)
        )

        n_hm_rows = len(port_order)
        hm_height = min(680, max(250, 150 + n_hm_rows * 36))

        if chart_mode_c1.startswith("📊"):
            fig_hm = go.Figure()
            for idx, pname in enumerate(port_order):
                if pname in flow_piv.index:
                    s_vals = flow_piv.loc[pname]
                    p_pct = hm_piv.loc[pname] if pname in hm_piv.index else None
                    color_bar = TRACE_PALETTE[idx % len(TRACE_PALETTE)]
                    role_sub = ROLE_SHORT_VI.get(role_map.get(pname, ""), "")
                    fig_hm.add_trace(
                        go.Bar(
                            x=flow_piv.columns,
                            y=s_vals.values,
                            name=f"{pname} [{role_sub}]" if role_sub else pname,
                            marker=dict(color=color_bar),
                            customdata=p_pct.values if p_pct is not None else [0] * len(s_vals),
                            hovertemplate=(
                                f"<b>{pname}</b><br>Tuần: %{{x|%d/%m/%Y}}<br>"
                                "Lưu lượng TB: <b>%{y:.1f} tàu/ngày</b><br>"
                                "So với nền: <b>%{customdata:+.1f}%</b><extra></extra>"
                            ),
                        )
                    )
            fig_hm.update_layout(
                height=hm_height,
                barmode="group",
                margin=dict(l=4, r=4, t=calc_legend_top_margin(n_hm_rows, 16), b=4),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=9.5)),
                yaxis=dict(title="Tàu / ngày (TB tuần)", gridcolor=GRID_COLOR, tickfont=dict(size=9.5)),
                xaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(size=9.5)),
                hovermode="x unified",
            )
        else:
            # Gắn thêm thông tin vai trò điểm nghẽn & tỷ trọng tàu dầu vào customdata trên Heatmap
            hm_y_labels = [
                f"{p} [{ROLE_SHORT_VI.get(role_map.get(p, ''), '')}]" for p in hm_piv.index
            ]
            hm_custom = np.array(
                [
                    [
                        f"{ROLE_VI_MAP.get(role_map.get(p, ''), '')} · Nền: {base_v_map.get(p, 0):.1f} tàu/ngày · Tỷ trọng Tanker: {tanker_share_map.get(p, 0):.1f}%"
                        for _ in hm_piv.columns
                    ]
                    for p in hm_piv.index
                ],
                dtype=object,
            )

            fig_hm = go.Figure(
                data=go.Heatmap(
                    z=hm_piv.values,
                    x=hm_piv.columns,
                    y=hm_y_labels,
                    customdata=hm_custom,
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
                    hovertemplate=(
                        "<b>%{y}</b><br>Tuần: %{x|%d/%m/%Y}<br>"
                        "Lệch vs nền 2021–22: <b>%{z:+.1f}%</b><br>%{customdata}<extra></extra>"
                    ),
                )
            )
            fig_hm.update_layout(
                height=hm_height,
                margin=dict(l=4, r=4, t=8, b=4),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(autorange="reversed", tickfont=dict(size=10.2)),
                xaxis=dict(tickfont=dict(size=9.5)),
            )
        st.plotly_chart(fig_hm, width="stretch", config={"displayModeBar": False})

    with top_c2:
        # Diễn biến lưu lượng thực tế vs dải nền + Cú sốc ngắn hạn I(0) (AO/IO/TC) + Nghi lỗi AIS (L10)
        n_sel = len(selected_ports_p2)
        q2_height = min(680, max(285, 240 + n_sel * 26 + calc_legend_top_margin(n_sel + 3, 0)))

        outlier_cols = [
            "observation_date",
            "portname",
            "chokepoint_label_code",
            "chokepoint_ts_label",
            "chokepoint_domain_label",
            "is_shock_consensus_outlier",
            "is_struct_consensus_outlier",
            "shock_mod_z_90d",
            "struct_mod_z_base",
        ]
        df_out_win = fact_outlier[
            (fact_outlier["portname"].isin(selected_ports_p2))
            & (fact_outlier["observation_date"] >= st_start)
            & (fact_outlier["observation_date"] <= st_end)
        ][outlier_cols].copy()

        if n_sel == 1:
            single_port = selected_ports_p2[0]
            single_role_vi = ROLE_SHORT_VI.get(role_map.get(single_port, ""), "")
            st.markdown(
                f'<div class="section-title">Diễn biến tại <code>{single_port}</code> ({single_role_vi}) vs dải nền &amp; phân loại bất thường (L01–L10)</div>',
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
            ][["observation_date", v_col, "n_total_zscore_90d"]].copy()
            df_q2 = pd.merge(
                df_q2_tr,
                df_out_win[df_out_win["portname"] == single_port],
                on="observation_date",
                how="left",
            ).sort_values("observation_date")
            df_q2["v_ma7"] = df_q2[v_col].rolling(7, min_periods=1).mean()

            df_q2_shock = df_q2[df_q2["is_shock_consensus_outlier"].fillna(False)]
            df_q2_glitch = df_q2[df_q2["chokepoint_label_code"] == "L10"]
            n_struct_days = int(df_q2["is_struct_consensus_outlier"].fillna(False).sum())

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
                annotation_text=f"Nền TB: {sel_base_mean:.1f} (LS: {n_struct_days} ngày)",
                annotation_position="bottom right",
                annotation_font_size=10,
            )
            fig_q2.add_trace(
                go.Bar(
                    x=df_q2["observation_date"],
                    y=df_q2[v_col],
                    name="Lưu lượng ngày (Cột)",
                    marker=dict(color="rgba(148, 163, 184, 0.45)", line=dict(width=0)),
                )
            )
            fig_q2.add_trace(
                go.Scatter(
                    x=df_q2["observation_date"],
                    y=df_q2["v_ma7"],
                    customdata=df_q2["chokepoint_domain_label"].fillna("L00: Normal Maritime Flow"),
                    name=f"MA7 ({v_desc})",
                    line=dict(color=COLOR_PRIMARY, width=2.3),
                    hovertemplate="MA7: %{y:.1f} tàu/ngày<br>Nhãn chế độ: %{customdata}<extra></extra>",
                )
            )
            fig_q2.add_trace(
                go.Scatter(
                    x=df_q2_shock["observation_date"],
                    y=df_q2_shock[v_col],
                    text=df_q2_shock["chokepoint_domain_label"],
                    mode="markers",
                    name=f"Cú sốc ngắn hạn I(0) (AO/IO/TC: {len(df_q2_shock)} ngày)",
                    marker=dict(color=COLOR_AMBER, size=7.5, symbol="diamond", line=dict(color="#FFFFFF", width=0.8)),
                    hovertemplate="Ngày: %{x|%d/%m/%Y}<br>Lưu lượng: %{y} tàu<br><b>%{text}</b><extra></extra>",
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
                f'<div class="section-title">Diễn biến nhóm {n_sel} điểm nghẽn (% lệch MA7 vs nền &amp; cú sốc đồng thuận kép L01–L10)</div>',
                unsafe_allow_html=True,
            )
            fig_q2 = go.Figure()
            shock_x, shock_y, shock_txt = [], [], []
            glitch_x, glitch_y, glitch_txt = [], [], []

            for idx, pname in enumerate(port_order):
                sub = df_win_sel[df_win_sel["portname"] == pname].sort_values("observation_date").copy()
                pbase = float(base_v_map.get(pname, 0.0))
                sub["ma7"] = sub[v_col].rolling(7, min_periods=1).mean()
                sub["pct_ma7"] = (sub["ma7"] - pbase) * 100.0 / pbase if pbase > 0 else np.nan
                sub_lbl = pd.merge(
                    sub,
                    df_out_win[df_out_win["portname"] == pname],
                    on=["observation_date", "portname"],
                    how="left",
                )
                fig_q2.add_trace(
                    go.Bar(
                        x=sub["observation_date"],
                        y=sub["pct_ma7"],
                        customdata=sub_lbl["chokepoint_domain_label"].fillna("L00: Normal Maritime Flow"),
                        name=pname,
                        marker=dict(color=TRACE_PALETTE[idx % len(TRACE_PALETTE)], opacity=0.75),
                        hovertemplate=f"<b>{pname}</b>: %{{y:+.1f}}%<br>%{{customdata}}<extra></extra>",
                    )
                )
                s_sub = sub_lbl[sub_lbl["is_shock_consensus_outlier"].fillna(False)]
                if not s_sub.empty:
                    shock_x.extend(s_sub["observation_date"].tolist())
                    shock_y.extend(s_sub["pct_ma7"].tolist())
                    shock_txt.extend(
                        [f"{pname} · {lbl}" for lbl in s_sub["chokepoint_domain_label"].tolist()]
                    )
                g_sub = sub_lbl[sub_lbl["chokepoint_label_code"] == "L10"]
                if not g_sub.empty:
                    glitch_x.extend(g_sub["observation_date"].tolist())
                    glitch_y.extend(g_sub["pct_ma7"].tolist())
                    glitch_txt.extend([pname] * len(g_sub))

            fig_q2.add_hline(
                y=0, line_dash="dot", line_color=COLOR_SLATE, annotation_text="Nền (0%)", annotation_font_size=10
            )
            fig_q2.add_trace(
                go.Scatter(
                    x=shock_x,
                    y=shock_y,
                    text=shock_txt,
                    mode="markers",
                    name=f"Cú sốc I(0) đồng thuận kép (AO/IO/TC: {len(shock_x)})",
                    marker=dict(color=COLOR_AMBER, size=7.5, symbol="diamond", line=dict(color="#FFFFFF", width=0.8)),
                    hovertemplate="%{text}<br>Ngày: %{x|%d/%m/%Y}<br>Lệch MA7: %{y:+.1f}%<extra></extra>",
                )
            )
            fig_q2.add_trace(
                go.Scatter(
                    x=glitch_x,
                    y=glitch_y,
                    text=glitch_txt,
                    mode="markers",
                    name=f"Nghi lỗi AIS (L10: {len(glitch_x)})",
                    marker=dict(color=COLOR_GRAY_DOT, size=7, symbol="circle", line=dict(color="#FFFFFF", width=0.8)),
                    hovertemplate="%{text}<br>Ngày: %{x|%d/%m/%Y}<br>Lệch nền: %{y:+.1f}% (Nghi lỗi AIS L10)<extra></extra>",
                )
            )
            y_title_q2 = "% lệch MA7 vs nền"

        add_event_bands_with_names(fig_q2, dim_events, win_min=st_start, win_max=st_end)
        fig_q2.update_layout(
            height=q2_height,
            barmode="group",
            margin=dict(l=6, r=6, t=calc_legend_top_margin(n_sel + 3, 16), b=6),
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
    # HÀNG DƯỚI: BẢN ĐỒ LƯU LƯỢNG & HÀNH LANG ĐỔI TUYẾN  |  ĐỒNG BIẾN ĐỘNG I(1) & TƯƠNG QUAN TRƯỢT I(0)
    # -----------------------------------------------------------------------
    bot_c1, bot_c2 = st.columns([1.05, 1.10])

    with bot_c1:
        st.markdown(
            f'<div class="section-title">Bản đồ phân bố lưu lượng, vai trò điểm nghẽn &amp; hành lang tuyến thay thế ({v_desc})</div>',
            unsafe_allow_html=True,
        )
        map_agg = (
            df_win_all.groupby("portname", as_index=False)
            .agg(avg_flow=(v_col, "mean"), avg_pct=("v_pct_base", "mean"))
            .merge(
                dim_chokepoints[
                    ["portname", "latitude", "longitude", "maritime_region", "chokepoint_role", "avg_tanker_share_pct"]
                ],
                on="portname",
                how="left",
            )
        )
        map_agg["role_vi"] = map_agg["chokepoint_role"].map(ROLE_SHORT_VI).fillna("")
        map_agg["is_selected"] = map_agg["portname"].isin(selected_ports_p2)
        map_agg["avg_pct_clean"] = map_agg["avg_pct"].fillna(0.0).clip(-80, 80)

        # Tìm các tuyến thay thế được ánh xạ từ các điểm nghẽn đang chọn (từ dim_chokepoint_rerouting_map)
        sel_reroute_rows = dim_rerouting_map[dim_rerouting_map["primary_portname"].isin(selected_ports_p2)].copy()
        mapped_alt_names = [
            str(a) for a in sel_reroute_rows["alt_portname"].dropna().unique().tolist() if str(a).strip() != ""
        ]
        map_agg["is_alt_route"] = map_agg["portname"].isin(mapped_alt_names) & (~map_agg["is_selected"])

        # Quy mô chấm tỉ lệ trực tiếp theo lưu lượng thực tế
        max_flow = max(1.0, float(map_agg["avg_flow"].max()))
        map_agg["dot_size"] = 10.0 + (map_agg["avg_flow"] / max_flow) * 28.0

        unsel_df = map_agg[~map_agg["is_selected"] & ~map_agg["is_alt_route"]]
        alt_df = map_agg[map_agg["is_alt_route"]]
        sel_df = map_agg[map_agg["is_selected"]]
        coord_lookup = map_agg.set_index("portname")[["latitude", "longitude", "avg_flow", "avg_pct_clean"]].to_dict(
            orient="index"
        )

        fig_map = go.Figure()

        # Vẽ đường kết nối hành lang đổi tuyến giữa Điểm nghẽn chính đang chọn <-> Tuyến thay thế
        corridor_summaries: list[str] = []
        line_lons: list[float | None] = []
        line_lats: list[float | None] = []
        for _, rmap in sel_reroute_rows.iterrows():
            p_name = str(rmap["primary_portname"])
            a_name = str(rmap["alt_portname"]) if pd.notna(rmap["alt_portname"]) else ""
            if a_name and p_name in coord_lookup and a_name in coord_lookup:
                p_info = coord_lookup[p_name]
                a_info = coord_lookup[a_name]
                line_lons.extend([p_info["longitude"], a_info["longitude"], None])
                line_lats.extend([p_info["latitude"], a_info["latitude"], None])

                p_base_v = float(base_v_map.get(p_name, 0.0))
                a_base_v = float(base_v_map.get(a_name, 0.0))
                comb_base = p_base_v + a_base_v
                comb_now = float(p_info["avg_flow"] + a_info["avg_flow"])
                comb_pct = (comb_now - comb_base) * 100.0 / comb_base if comb_base > 0 else 0.0
                alt_share = float(a_info["avg_flow"]) * 100.0 / comb_now if comb_now > 0 else 0.0
                corridor_summaries.append(
                    f"🔄 <b>{rmap['corridor_name_vi']}</b>: <code>{p_name}</code> ({p_info['avg_pct_clean']:+.1f}%) "
                    f"↔ <code>{a_name}</code> ({a_info['avg_pct_clean']:+.1f}%, chiếm <b>{alt_share:.1f}%</b> hành lang) "
                    f"· Tổng 2 tuyến: <b>{comb_now:.1f} tàu/ngày ({comb_pct:+.1f}% vs nền)</b>."
                )
            elif p_name in coord_lookup:
                p_info = coord_lookup[p_name]
                corridor_summaries.append(
                    f"⛔ <b>{rmap['corridor_name_vi']}</b> (<code>{p_name}</code>: {p_info['avg_pct_clean']:+.1f}% vs nền): "
                    f"<i>{rmap['rerouting_note_vi']}</i>"
                )

        if line_lons:
            fig_map.add_trace(
                go.Scattergeo(
                    lon=line_lons,
                    lat=line_lats,
                    mode="lines",
                    name="Hành lang đổi tuyến",
                    line=dict(width=1.8, color=COLOR_TEAL, dash="dot"),
                    hoverinfo="skip",
                )
            )

        # Các điểm nghẽn còn lại làm nền bối cảnh
        if not unsel_df.empty:
            fig_map.add_trace(
                go.Scattergeo(
                    lon=unsel_df["longitude"],
                    lat=unsel_df["latitude"],
                    text=unsel_df["portname"],
                    customdata=np.stack(
                        [unsel_df["avg_flow"], unsel_df["avg_pct_clean"], unsel_df["role_vi"], unsel_df["avg_tanker_share_pct"]],
                        axis=-1,
                    ),
                    mode="markers",
                    name="Điểm nghẽn khác",
                    marker=dict(
                        size=unsel_df["dot_size"] * 0.72,
                        color=unsel_df["avg_pct_clean"],
                        colorscale=[[0.0, "#F04438"], [0.45, "#F79009"], [0.55, "#94A3B8"], [1.0, "#12B76A"]],
                        cmin=-70,
                        cmax=70,
                        opacity=0.35,
                        line=dict(width=0.6, color="rgba(148,163,184,0.6)"),
                    ),
                    hovertemplate=(
                        "<b>%{text}</b> (%{customdata[2]})<br>"
                        "TB lưu lượng: %{customdata[0]:.1f} tàu/ngày (Tanker: %{customdata[3]:.1f}%)<br>"
                        "So với nền: %{customdata[1]:+.1f}%<extra></extra>"
                    ),
                )
            )

        # Các tuyến thay thế tương ứng với điểm nghẽn đang chọn
        if not alt_df.empty:
            fig_map.add_trace(
                go.Scattergeo(
                    lon=alt_df["longitude"],
                    lat=alt_df["latitude"],
                    text=alt_df.apply(lambda r: f"↪ {r['portname']} ({r['avg_pct_clean']:+.0f}%)", axis=1),
                    customdata=np.stack(
                        [alt_df["avg_flow"], alt_df["avg_pct_clean"], alt_df["role_vi"], alt_df["avg_tanker_share_pct"]],
                        axis=-1,
                    ),
                    mode="markers+text",
                    textposition="bottom center",
                    textfont=dict(size=9.2),
                    name="Tuyến thay thế ánh xạ",
                    marker=dict(
                        size=alt_df["dot_size"] * 0.90,
                        color=alt_df["avg_pct_clean"],
                        colorscale=[[0.0, "#F04438"], [0.45, "#F79009"], [0.55, "#94A3B8"], [1.0, "#12B76A"]],
                        cmin=-70,
                        cmax=70,
                        opacity=0.90,
                        line=dict(width=2.2, color=COLOR_TEAL),
                    ),
                    hovertemplate=(
                        "<b>%{text}</b> (%{customdata[2]})<br>"
                        "TB lưu lượng: %{customdata[0]:.1f} tàu/ngày (Tanker: %{customdata[3]:.1f}%)<br>"
                        "So với nền: %{customdata[1]:+.1f}%<extra></extra>"
                    ),
                )
            )

        # Các điểm nghẽn đang được chọn trong bộ lọc
        fig_map.add_trace(
            go.Scattergeo(
                lon=sel_df["longitude"],
                lat=sel_df["latitude"],
                text=sel_df.apply(lambda r: f"{r['portname']} ({r['avg_pct_clean']:+.0f}%)", axis=1),
                customdata=np.stack(
                    [sel_df["avg_flow"], sel_df["avg_pct_clean"], sel_df["role_vi"], sel_df["avg_tanker_share_pct"]],
                    axis=-1,
                ),
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
                hovertemplate=(
                    "<b>%{text}</b> (%{customdata[2]})<br>"
                    "TB lưu lượng: %{customdata[0]:.1f} tàu/ngày (Tanker: %{customdata[3]:.1f}%)<br>"
                    "So với nền: %{customdata[1]:+.1f}%<extra></extra>"
                ),
            )
        )

        map_height = min(560, max(360, 330 + len(sel_df) * 12))
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

        if corridor_summaries:
            st.markdown(
                f'<div class="corridor-box">{"<br/>".join(corridor_summaries[:3])}</div>',
                unsafe_allow_html=True,
            )

    with bot_c2:
        st.markdown(
            '<div class="section-title">Xu hướng biến động giá năng lượng và mức độ liên hệ với lưu lượng tàu</div>',
            unsafe_allow_html=True,
        )
        df_en_p2 = fact_energy[
            (fact_energy["calendar_date"] >= st_start) & (fact_energy["calendar_date"] <= st_end)
        ].sort_values("calendar_date").copy()
        df_reg_p2 = fact_regime[
            (fact_regime["portname"].isin(selected_ports_p2))
            & (fact_regime["observation_date"] >= st_start)
            & (fact_regime["observation_date"] <= st_end)
        ].sort_values("observation_date").copy()

        corr_brent_col = (
            "rolling_corr_90d_diff7d_brent"
            if vessel_choice == "Tanker"
            else "rolling_corr_90d_total_diff7d_brent"
        )
        corr_ulsd_col = (
            "rolling_corr_90d_diff7d_ulsd"
            if vessel_choice == "Tanker"
            else "rolling_corr_90d_total_diff7d_ulsd"
        )

        n_q4_traces = len(port_order) * 2 + 2
        q4_height = min(620, max(385, 330 + len(port_order) * 22 + calc_legend_top_margin(n_q4_traces, 0)))

        fig_q4 = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.11,
            row_heights=[0.56, 0.44],
            subplot_titles=(
                "Tốc độ tăng/giảm so với ngày đầu kỳ (Đầu kỳ = 100): Tàu chạy vs Giá dầu",
                "Mức độ biến động cùng chiều / ngược chiều giữa tàu và giá dầu (Trong 90 ngày)",
            ),
        )

        for idx, pname in enumerate(port_order):
            sub_q4 = df_win_sel[df_win_sel["portname"] == pname].sort_values("observation_date").copy()
            sub_q4["v_ma7"] = sub_q4[v_col].rolling(7, min_periods=1).mean()
            first_valid = sub_q4["v_ma7"].loc[sub_q4["v_ma7"] > 0]
            ref_v = float(first_valid.iloc[0]) if not first_valid.empty else 1.0
            sub_q4["idx_flow"] = (sub_q4["v_ma7"] / ref_v) * 100.0
            color_p = TRACE_PALETTE[idx % len(TRACE_PALETTE)]

            fig_q4.add_trace(
                go.Scatter(
                    x=sub_q4["observation_date"],
                    y=sub_q4["idx_flow"],
                    name=f"Lưu lượng {pname}",
                    line=dict(color=color_p, width=1.9),
                    hovertemplate=f"<b>{pname}</b>: %{{y:.1f}}% so với đầu kỳ<extra></extra>",
                ),
                row=1,
                col=1,
            )

            sub_reg = df_reg_p2[df_reg_p2["portname"] == pname].sort_values("observation_date")
            if not sub_reg.empty:
                fig_q4.add_trace(
                    go.Scatter(
                        x=sub_reg["observation_date"],
                        y=sub_reg[corr_brent_col],
                        customdata=sub_reg[corr_ulsd_col],
                        name=f"Mức liên hệ ({pname} vs Brent)",
                        line=dict(color=color_p, width=1.7, dash="solid"),
                        hovertemplate=(
                            f"<b>{pname}</b><br>Liên hệ với giá Brent: %{{y:+.2f}}<br>"
                            "Liên hệ với giá Diesel: %{customdata:+.2f}<br>"
                            "<i>(Âm = Tàu giảm thì giá tăng; Dương = Cùng tăng/giảm)</i><extra></extra>"
                        ),
                    ),
                    row=2,
                    col=1,
                )

        brent_ref = float(df_en_p2["brent_usd_per_bbl"].iloc[0]) if not df_en_p2.empty else 1.0
        ulsd_ref = float(df_en_p2["ulsd_usd_per_gal"].iloc[0]) if not df_en_p2.empty else 1.0
        fig_q4.add_trace(
            go.Scatter(
                x=df_en_p2["calendar_date"],
                y=(df_en_p2["brent_usd_per_bbl"] / brent_ref) * 100.0,
                customdata=df_en_p2["diesel_brent_crack_bbl"],
                name="Giá dầu Brent",
                line=dict(color=COLOR_PRIMARY, width=2.3),
                hovertemplate="Giá Brent: %{y:.1f}% so với đầu kỳ (Biên lọc dầu: $%{customdata:.2f}/thùng)<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig_q4.add_trace(
            go.Scatter(
                x=df_en_p2["calendar_date"],
                y=(df_en_p2["ulsd_usd_per_gal"] / ulsd_ref) * 100.0,
                name="Giá dầu Diesel",
                line=dict(color=COLOR_TEAL, width=1.8, dash="dot"),
                hovertemplate="Giá Diesel: %{y:.1f}% so với đầu kỳ<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig_q4.add_hline(y=100, line_dash="dot", line_color=COLOR_SLATE, row=1, col=1)
        fig_q4.add_hline(y=0, line_dash="dot", line_color=COLOR_SLATE, row=2, col=1)
        add_event_bands_with_names(fig_q4, dim_events, win_min=st_start, win_max=st_end, n_rows=2)

        fig_q4.update_layout(
            height=q4_height,
            margin=dict(l=6, r=6, t=calc_legend_top_margin(n_q4_traces, 38), b=6),
            legend=dict(orientation="h", yanchor="bottom", y=1.04, xanchor="right", x=1, font=dict(size=9.2)),
            hovermode="x unified",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_q4.update_annotations(font_size=10.8)
        fig_q4.update_xaxes(gridcolor=GRID_COLOR)
        fig_q4.update_yaxes(title_text="% so với ngày đầu", gridcolor=GRID_COLOR, row=1, col=1, title_font=dict(size=9.5))
        fig_q4.update_yaxes(
            title_text="Mức độ liên hệ (-1 đến +1)",
            range=[-1.0, 1.0],
            gridcolor=GRID_COLOR,
            row=2,
            col=1,
            title_font=dict(size=9.5),
        )
        st.plotly_chart(fig_q4, width="stretch", config={"displayModeBar": False})

    render_shared_footer()
