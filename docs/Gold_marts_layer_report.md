# BÁO CÁO KẾT QUẢ TRACEBACK DỮ LIỆU KHUYẾT ĐẦU KỲ & XÂY DỰNG TẦNG GOLD (`gold.*`)

## 1. Kết Quả Traceback & Xử Lý 3 Ngày Đầu Bị `NULL` (`2021-01-01` đến `2021-01-03`)

### 1.1. Nguyên nhân gốc rễ (Root Cause)
Trong bảng tích hợp `silver.int_maritime_energy_daily_joined` và `silver.int_energy_prices_daily_filled` trước đây, cả 2 cột giá năng lượng (`brent_usd_per_bbl` và `ulsd_usd_per_gal`) đều bị `NULL` trong 3 ngày đầu tiên của năm 2021 (`2021-01-01`, `2021-01-02`, `2021-01-03`, tương ứng `3 ngày × 28 điểm nghẽn = 84 dòng`):
1. Ngày `2021-01-01` là **Thứ Sáu (Nghỉ Tết Dương lịch — New Year's Day)**, thị trường giao dịch dầu mỏ giao ngay tại Châu Âu và Mỹ đóng cửa.
2. Ngày `2021-01-02` và `2021-01-03` là **Thứ Bảy và Chủ Nhật**. Phiên giao dịch đầu tiên của năm 2021 diễn ra vào **Thứ Hai `2021-01-04`**.
3. Do script thu thập ban đầu (`src/ingest/ingest_eia_energy.py`) đặt mốc `START_DATE = "2021-01-01"`, dữ liệu thô không chứa phiên giao dịch cuối cùng của năm 2020 (`2020-12-31`). Khi thuật toán **Causal Forward-Fill (`LAST_VALUE IGNORE NULLS`)** chạy từ `2021-01-01`, không có giá đóng cửa phía trước để chiếu sang 3 ngày nghỉ đầu năm.

### 1.2. Kết quả Traceback từ EIA API v2 (`2020-12-28` $\rightarrow$ `2020-12-31`)
Truy vấn ngược (Traceback) trực tiếp lên **U.S. EIA API v2** (`https://api.eia.gov/v2/petroleum/pri/spt/data/`) cho tuần giao dịch cuối cùng của năm 2020 thu được kết quả chính xác tuyệt đối:

| Ngày giao dịch (`period`) | Thứ trong tuần | Giá dầu thô Brent (`RBRTE`, `$/BBL`) | Giá dầu Diesel ULSD (`EER_EPD2DXL0_PF4_RGC_DPG`, `$/GAL`) | Ghi chú |
| :---: | :---: | :---: | :---: | :--- |
| `2020-12-28` | Thứ Hai | `50.88` | `1.427` | Phiên giao dịch bình thường |
| `2020-12-29` | Thứ Ba | `50.44` | `1.436` | Phiên giao dịch bình thường |
| `2020-12-30` | Thứ Tư | `50.74` | `1.436` | Phiên giao dịch bình thường |
| **`2020-12-31`** | **Thứ Năm** | **`51.22`** | **`1.432`** | **Phiên đóng cửa cuối cùng của năm 2020 (Mốc neo Causal Forward-Fill)** |
| `2021-01-01` | Thứ Sáu (Tết Dương lịch) | `51.22` *(Forward-Fill)* | `1.432` *(Forward-Fill)* | `last_trading_date = 2020-12-31`, `days_since_last_trade = 1` |
| `2021-01-02` | Thứ Bảy | `51.22` *(Forward-Fill)* | `1.432` *(Forward-Fill)* | `last_trading_date = 2020-12-31`, `days_since_last_trade = 2` |
| `2021-01-03` | Chủ Nhật | `51.22` *(Forward-Fill)* | `1.432` *(Forward-Fill)* | `last_trading_date = 2020-12-31`, `days_since_last_trade = 3` |
| `2021-01-04` | Thứ Hai | `50.37` *(Quan sát thực)* | `1.397` *(Quan sát thực)* | Phiên giao dịch đầu tiên của năm 2021 (`is_forward_filled = FALSE`) |

- **Kết quả kiểm chứng sau khi cập nhật `src/process/process_data.py`**:
  - Giữ nguyên vẹn 100% file gốc ở tầng Bronze (`data/raw/eia_energy_prices_daily_raw.parquet` — `2,899 dòng`).
  - Số lượng giá trị `NULL` của `brent_usd_per_bbl` và `ulsd_usd_per_gal` trong `silver.int_energy_prices_daily_filled` (`4,234 dòng`) và `silver.int_maritime_energy_daily_joined` (`59,276 dòng`) giảm về **`0` (`0.00%`)**.

---

## 2. Kết Quả Xây Dựng Schema Tầng `gold` (Marts Layer)

Script [`src/process/build_gold_marts.py`](file:///e:/maritime-energy-supplychain-monitor/src/process/build_gold_marts.py) đã được thực thi để tạo schema `gold` trong DuckDB (`data/maritime_dwh.duckdb`), xuất 6 file Parquet tại `data/gold/*.parquet` và đồng bộ toàn bộ 3 tầng (`raw`, `silver`, `gold` — tổng cộng 12 bảng) lên **MotherDuck Cloud (`maritime_dwh`)**.

### 2.1. Bảng tổng hợp dung lượng & số dòng các bảng tầng `gold`

| STT | Bảng trong DuckDB / MotherDuck | File Parquet (`data/gold/`) | Số dòng | Số cột | Kích thước | Vai trò kiến trúc |
| :-: | :--- | :--- | ---: | ---: | ---: | :--- |
| 1 | `gold.dim_chokepoints` | `dim_chokepoints.parquet` | `28` | `9` | `3.0 KB` | Bảng chiều Điểm nghẽn: Vùng địa lý, vai trò chuỗi cung ứng, tuyến dầu huyết mạch & đường cơ sở `2021–2022`. |
| 2 | `gold.dim_geopolitical_events` | `dim_geopolitical_events.parquet` | `4` | `10` | `2.6 KB` | Bảng chiều Sự kiện Địa chính trị & Khí hậu (`EVT_01` $\rightarrow$ `EVT_04`), gắn khóa ngoại `primary_portid`. |
| 3 | `gold.fct_energy_prices_daily` | `fct_energy_prices_daily.parquet` | `2,117` | `21` | `170.6 KB` | Bảng Fact Giá năng lượng: Quy đổi `ULSD ($/BBL)`, `Crack Spread`, trung bình trượt `MA7`, biến đổi dừng $I(0)$ (`diff_1d`, `diff_7d`, `log_ret_1d`) & độ biến động `volatility_30d`. |
| 4 | `gold.fct_chokepoint_transit_daily` | `fct_chokepoint_transit_daily.parquet` | `59,276` | `31` | `2,550.6 KB` | Bảng Fact Lưu lượng tàu: Tích hợp `MA7`, sai phân dừng $I(0)$, điểm dị thường `zscore_90d`, chế độ `regime_type` & cảnh báo tự động `daily_alert_severity`. |
| 5 | `gold.mart_chokepoint_energy_regime_daily` | `mart_chokepoint_energy_regime_daily.parquet` | `59,276` | `48` | `3,939.6 KB` | Bảng Mart phục vụ trực tiếp Dashboard: Tích hợp sẵn tương quan trượt 30 ngày & 90 ngày (`rolling_corr_30d`, `rolling_corr_90d`) theo từng chế độ. |
| 6 | `gold.mart_red_sea_cape_rerouting_daily` | `mart_red_sea_cape_rerouting_daily.parquet` | `2,117` | `29` | `143.7 KB` | Bảng Mart chuyên biệt: Đo lường tỷ lệ tái định tuyến Biển Đỏ sang Mũi Hảo Vọng và đối chiếu với Eo biển Hormuz. |

### 2.2. Kết quả đồng bộ 3 tầng (`raw`, `silver`, `gold`) lên MotherDuck Cloud (`maritime_dwh`)

Script [`src/load/load_to_motherduck.py`](file:///e:/maritime-energy-supplychain-monitor/src/load/load_to_motherduck.py) đã đẩy toàn bộ **12 bảng** (tổng dung lượng Parquet local `15.50 MB`) lên MotherDuck Cloud và đối chiếu khớp 100% số dòng giữa Local và Cloud:

```text
Tong dung luong Parquet local: 15.50 MB
Cac bang hien co trong maritime_dwh (MotherDuck Cloud):
  raw.eia_energy_prices_daily:                 2,899 dong x 12 cot  (OK - khop voi local)
  raw.imf_chokepoint_daily:                   59,276 dong x 22 cot  (OK - khop voi local)
  silver.stg_eia_energy_prices:                2,899 dong x 13 cot  (OK - khop voi local)
  silver.int_energy_prices_daily_filled:       4,234 dong x 15 cot  (OK - 0 NULLs)
  silver.stg_imf_chokepoint_daily:            59,276 dong x 26 cot  (OK - khop voi local)
  silver.int_maritime_energy_daily_joined:    59,276 dong x 32 cot  (OK - 0 NULLs)
  gold.dim_chokepoints:                           28 dong x  9 cot  (OK - khop voi local)
  gold.dim_geopolitical_events:                    4 dong x 10 cot  (OK - khop voi local)
  gold.fct_energy_prices_daily:                2,117 dong x 21 cot  (OK - khop voi local)
  gold.fct_chokepoint_transit_daily:          59,276 dong x 31 cot  (OK - khop voi local)
  gold.mart_chokepoint_energy_regime_daily:   59,276 dong x 48 cot  (OK - khop voi local)
  gold.mart_red_sea_cape_rerouting_daily:      2,117 dong x 29 cot  (OK - khop voi local)
```

---

## 3. Thống Kê Nghiệp Vụ Rút Ra Từ Tầng `gold`

### 3.1. Phân loại 28 điểm nghẽn trong `gold.dim_chokepoints`
| Phân nhóm vai trò (`chokepoint_role`) | Số điểm nghẽn | Số tuyến dầu mỏ chính (`is_primary_oil_route = TRUE`) | Lưu lượng tổng cơ sở (`baseline_n_total`, tàu/ngày) | Lưu lượng Tanker cơ sở (`baseline_n_tanker`, tàu/ngày) |
| :--- | :---: | :---: | :---: | :---: |
| `Global Transit Corridor` *(Hành lang quá cảnh liên lục địa)* | `8` | `8` | `139.9` | `43.4` |
| `Origin Energy Export Hub` *(Yết hầu xuất khẩu đầu nguồn)* | `4` | `3` | `66.3` | `24.2` |
| `Rerouting Alternative` *(Tuyến đường vòng thay thế)* | `4` | `2` | `27.9` | `7.3` |
| `Regional Maritime Passage` *(Eo biển khu vực)* | `12` | `4` | `42.9` | `10.3` |

### 3.2. Phân phối mức độ cảnh báo tự động (`daily_alert_severity`) trong `gold.fct_chokepoint_transit_daily`
| Chế độ (`regime_type`) | Mức cảnh báo tự động (`daily_alert_severity`) | Số dòng (`port-days`) | Ý nghĩa thực tế |
| :--- | :--- | ---: | :--- |
| **`Disruption Regime`** | `High` (`-30%` đến `-50%` hoặc `Z <= -2`) | `688` | Giai đoạn hạn hán Panama & nửa đầu khủng hoảng Biển Đỏ |
| **`Disruption Regime`** | `Critical` (`<= -50%` hoặc `Z <= -3`) | `680` | Đỉnh điểm phong tỏa Bab el-Mandeb (`-54.4%`) & sụp đổ Eo biển Hormuz (`-93.5%`) |
| **`Disruption Regime`** | `Moderate` / `Normal` / `Rerouting Surge` | `228` | Các ngày đầu/cuối sự kiện hoặc dao động ngắn hạn |
| **`Normal Regime`** | `Normal` | `35,139` | Trạng thái vận hành ổn định trên toàn mạng lưới |
| **`Normal Regime`** | `Moderate` / `High` / `Critical` | `15,700` | Các đợt giảm lưu lượng cục bộ do bão/thời tiết hoặc đứt gãy lan truyền (như kênh đào Suez bị ảnh hưởng dây chuyền từ Bab el-Mandeb) |
| **`Normal Regime`** | `Rerouting Surge` (`>= +30%` hoặc `Z >= +2`) | `6,841` | Sự tăng vọt lưu lượng tại **Mũi Hảo Vọng (`Cape of Good Hope`)** và các eo biển thay thế khi tàu bỏ tuyến Biển Đỏ |

### 3.3. Chỉ số Đổi tuyến Hàng hải trong `gold.mart_red_sea_cape_rerouting_daily`
| Giai đoạn (`red_sea_regime`) | Số ngày | Lưu lượng TB qua Bab el-Mandeb (tàu/ngày) | Lưu lượng TB qua Mũi Hảo Vọng (tàu/ngày) | Tỷ trọng tàu chọn Mũi Hảo Vọng (`cape_rerouting_share_total_pct`) | Tỷ trọng Tanker chọn Mũi Hảo Vọng (`cape_rerouting_share_tanker_pct`) | Crack Spread TB (`$/BBL`) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`Normal Transit`** *(Trước 19/11/2023)* | `1,052` | `66.6` | `46.4` | **`41.01%`** | **`32.19%`** | `$31.12` |
| **`Red Sea Crisis (Rerouting)`** *(Từ 19/11/2023)* | `1,065` | `34.5` | `87.3` | **`71.30%`** *(+30.29 điểm %)* | **`59.22%`** *(+27.03 điểm %)* | `$31.64` |
