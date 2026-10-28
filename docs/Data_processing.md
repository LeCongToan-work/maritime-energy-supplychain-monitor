# TÀI LIỆU KỸ THUẬT: TIẾN TRÌNH XỬ LÝ DỮ LIỆU (DATA PROCESSING PIPELINE)

## 1. Thông Tin Chung

* **Kiến trúc:** Triển khai theo mô hình Lakehouse / Medallion Architecture (Bronze $\rightarrow$ Silver/Intermediate) kết hợp **dbt Core (1.12.6)**, **dbt-duckdb (1.11.0)** và script trích xuất Python thuần **DuckDB**.
* **Môi trường thực thi:** DuckDB Local DWH (`data/maritime_dwh.duckdb`) và đồng bộ lên **MotherDuck Cloud** (`maritime_dwh`).
* **Nguồn đầu vào (Bronze Layer):**
  * `data/raw/eia_energy_prices_daily_raw.parquet` (2,899 dòng $\times$ 12 cột)
  * `data/raw/imf_chokepoint_daily_raw.parquet` (59,276 dòng $\times$ 22 cột)
* **Kết quả kiểm thử dbt:** `PASS=13 WARN=0 ERROR=0` (3 view models, 10 data tests).
* **Các file thành phần trong hệ thống:**
  | Phương án | File thành phần | Tầng dữ liệu | Vai trò |
  | :---: | :--- | :---: | :--- |
  | **1A** | `dbt_maritime/models/staging/stg_eia_energy_prices.sql` | Silver / Staging | Xử lý khuyết thiếu `area-name`, chuẩn hóa schema & ép kiểu an toàn |
  | **3A** | `dbt_maritime/models/staging/stg_imf_chokepoint_daily.sql` | Silver / Staging | Chuẩn hóa tải trọng tàu (`capacity`), khắc phục sai số làm tròn số nguyên |
  | **2A** | `dbt_maritime/models/intermediate/int_energy_prices_daily_filled.sql` | Silver / Intermediate | Đồng bộ lệch pha chu kỳ giao dịch bằng **Causal Forward-Fill (LOCF)** |
  | **Pipeline**| `src/process/process_data.py` | Python Pipeline | Script tự động hóa xuất các dataset vật lý ra thư mục `data/processed/` |
  | **Cloud** | `src/load/load_to_motherduck.py` | Cloud Loader | Đẩy toàn bộ tầng Bronze và Silver lên cơ sở dữ liệu MotherDuck |
  | **Audit** | `dbt_maritime/tests/*` & `dbt_maritime/models/schema.yml` | Quality Assurance | Bộ 10 data tests xác thực tính toàn vẹn và phi rò rỉ dữ liệu (*No Data Leakage*) |

---

## 2. Phương Án 1A: Xử Lý Khuyết Thiếu Cột `area-name` (EIA Energy Prices)

### 2.1. Bản chất nghiệp vụ & Phương pháp xử lý
* Cột `area-name` gốc từ API EIA v2 trả về chuỗi `"NA"` ở 100% các dòng do thiếu mapping cấp khu vực. Bản chất các chuỗi giá tại đây là giá giao ngay tại cảng bốc hàng (**Spot Price FOB - Free on Board**), phản ánh trung tâm xuất khẩu và định giá (*Loading Port / Pricing Hub*).
* Căn cứ vào nguyên lý **Deterministic / Deductive Imputation** (Fellegi & Holt, 1976), vì tồn tại phụ thuộc hàm 1–1 ($\text{duoarea} \rightarrow \text{area-name}$), giá trị được phục hồi chính xác 100% tại tầng Staging dựa trên mã vùng `duoarea`:
  * `duoarea = 'ZEU'` $\rightarrow$ `area_name = 'Europe'` (Cụm mỏ Biển Bắc: Sullom Voe, Hound Point, Ekofisk...)
  * `duoarea = 'RGC'` $\rightarrow$ `area_name = 'U.S. Gulf Coast'` (Cụm lọc hóa dầu Vịnh Mexico - PADD 3)
  * Các mã khác (nếu xuất hiện trong tương lai) $\rightarrow$ `NULLIF(area_name_raw, 'NA')`.
* Tầng Bronze được bảo toàn nguyên vẹn tính bất biến của dữ liệu thô. Đồng thời, các trường dữ liệu được ép kiểu tường minh: `period_date` (`DATE`), `price_value` (`DOUBLE`), `ingested_at_utc` (`TIMESTAMPTZ`).

### 2.2. Kết quả thực thi

| `duoarea` | `area_name_raw` (Bronze) | `area_name` (Silver Staging) | Số lượng bản ghi | Tỷ lệ làm sạch |
| :---: | :---: | :--- | ---: | :---: |
| `RGC` | `NA` | `U.S. Gulf Coast` | 1,441 | 100% |
| `ZEU` | `NA` | `Europe` | 1,458 | 100% |

* **Đánh giá kiểm định:** Cột `area_name` đạt 0% NULL trên toàn bộ `2,899/2,899` dòng. Vượt qua đồng thời hai kiểm thử dbt: `not_null` và `accepted_values`.

---

## 3. Phương Án 2A: Khắc Phục Lệch Pha Chu Kỳ Giao Dịch Bằng Causal Forward-Fill (LOCF)

### 3.1. Bản chất nghiệp vụ & Phương pháp xử lý
* Tàu biển vận hành liên tục $365\,\text{ngày/năm}$, trong khi thị trường năng lượng nghỉ giao dịch vào Thứ Bảy, Chủ Nhật và các ngày nghỉ lễ tài chính khác nhau giữa Anh và Mỹ (gây ra khoảng 630+ ngày không có mức giá giao ngay).
* Áp dụng phương pháp **Causal Forward-Fill / Last Observation Carried Forward (LOCF)** (Baumeister & Kilian, 2015; Hamilton, 2009) trên trục thời gian liên tục (`Calendar Spine` từ `2021-01-01` đến `2026-10-18`, gồm 2,117 ngày):
  * Mức giá của ngày nghỉ được điền bằng mức giá đóng cửa của phiên giao dịch liền kề trước đó ($P_t = P_{t-1}$).
  * Cửa sổ Window Function giới hạn nghiêm ngặt `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, đảm bảo thông tin thời gian thực và ngăn chặn hoàn toàn rò rỉ dữ liệu tương lai (*No Look-Ahead Bias / No Data Leakage*).
  * Ba ngày đầu kỳ (`2021-01-01` đến `2021-01-03`) trước khi thị trường mở cửa phiên đầu năm (`2021-01-04`) được giữ `NULL` tự nhiên, tuyệt đối không dùng giá tương lai để back-fill.

### 3.2. Kết quả thực thi

| Chuỗi dữ liệu (Series) | Khu vực định giá | Tổng số ngày lịch | Số ngày có giao dịch thực | Số ngày được Forward-fill | Số ngày NULL đầu kỳ | Khoảng cách điền tối đa |
| :--- | :--- | ---: | ---: | ---: | ---: | :---: |
| `RBRTE` (Brent Crude) | Europe | 2,117 | 1,458 | 656 | 3 | 4 ngày |
| `EER_EPD2DXL0_PF4_RGC_DPG` (ULSD) | U.S. Gulf Coast | 2,117 | 1,441 | 673 | 3 | 4 ngày |

* **Phân bố khoảng cách ngày điền khuyết (`days_since_last_trade`):**
  * Khoảng cách 1 ngày (Thứ Bảy, ngày lễ đơn lẻ): 311 ngày (Brent), 321 ngày (Diesel).
  * Khoảng cách 2 ngày (Chủ Nhật): 302 ngày (cả hai chuỗi).
  * Khoảng cách 3–4 ngày (Kỳ nghỉ lễ kéo dài / Bank Holidays): 43 ngày (Brent), 50 ngày (Diesel).
* **Minh họa chu kỳ chuyển tiếp thực tế (Dầu Brent Biển Bắc):**

  | Ngày quan sát | Thứ trong tuần | Giá thực tế (`observed`) | Giá mô hình (`price_value`) | Phiên giao dịch cơ sở | Trạng thái điền khuyết |
  | :--- | :--- | ---: | ---: | :---: | :---: |
  | `2021-01-08` | Friday | 55.51 \$/BBL | 55.51 \$/BBL | `2021-01-08` | Nguyên bản |
  | `2021-01-09` | Saturday | `NaN` | 55.51 \$/BBL | `2021-01-08` | Forward-Filled |
  | `2021-01-10` | Sunday | `NaN` | 55.51 \$/BBL | `2021-01-08` | Forward-Filled |
  | `2021-01-11` | Monday | 54.84 \$/BBL | 54.84 \$/BBL | `2021-01-11` | Nguyên bản |

* **Đánh giá kiểm định:** Kiểm thử dbt `assert_forward_fill_is_causal` vượt qua 100%, bảo đảm không có bất kỳ bản ghi nào lấy giá từ mốc thời gian tương lai.

---

## 4. Phương Án 3A: Chuẩn Hóa Ràng Buộc Tải Trọng Tàu & Dung Sai Làm Tròn (IMF PortWatch)

### 4.1. Bản chất nghiệp vụ & Phương pháp xử lý
* Dữ liệu tải trọng của IMF PortWatch được tính toán từ tín hiệu AIS và mô hình số thực ước tính tải trọng mớn nước (Cerdeiro et al., 2020). Khi xuất bản sang tầng phân phối dạng số nguyên, việc làm tròn độc lập từng trường tổng tạo ra sai số làm tròn tự nhiên:
  $$\text{round}(a + b + c + d) \neq \text{round}(a) + \text{round}(b) + \text{round}(c) + \text{round}(d)$$
  Sai số lý thuyết tối đa là $k - 1$ đơn vị (với $k=4$ nhóm tàu hàng khô, sai số tối đa là 3 tấn; với $k=2$ nhóm cargo + tanker, sai số tối đa là 1 tấn).
* **Giải pháp tầng Silver:**
  * Tính toán lại chính xác:
    $$\text{capacity\_cargo} = \text{capacity\_container} + \text{capacity\_dry\_bulk} + \text{capacity\_general\_cargo} + \text{capacity\_roro}$$
    $$\text{capacity} = \text{capacity\_cargo} + \text{capacity\_tanker}$$
  * Bảo toàn giá trị gốc từ nhà cung cấp tại `capacity_cargo_raw` và `capacity_raw`.
  * Bổ sung trường kiểm toán sai số `capacity_cargo_rounding_diff` và `capacity_rounding_diff`.
  * Cập nhật bộ kiểm tra `data_quality_checker.py` và dbt test `assert_imf_capacity_rounding_within_tolerance` với ngưỡng dung sai chuẩn ($\le 3$ tấn và $\le 1$ tấn).

### 4.2. Kết quả thực thi

| Độ lệch làm tròn phát hiện (`diff` - tấn DWT) | Số dòng ghi nhận ở `capacity_cargo` | Số dòng ghi nhận ở `capacity` | Tỷ lệ phân bố |
| :---: | ---: | ---: | :---: |
| 0 tấn | 14,702 | 32,378 | 54.6% (tổng thể) |
| 1 tấn | 28,071 | 26,898 | 45.4% (tổng thể) |
| 2 tấn | 15,251 | 0 | Phù hợp lý thuyết |
| 3 tấn | 1,252 | 0 | Phù hợp lý thuyết |
| $> 3$ tấn (Lỗi dữ liệu bất thường) | **0** | **0** | **Tuyệt đối không có** |

* **Đánh giá sau khi chuẩn hóa:**
  * Số dòng vi phạm logic cộng dồn sau xử lý: **`0 / 59,276` dòng (0%)**. Đảm bảo các biểu đồ phân rã tỷ trọng (Stacked Charts) trên Dashboard khớp chính xác 100% từng đơn vị.
  * Mức biến động tải trọng so với số liệu gốc chỉ chiếm $0.000069\%$ tổng khối lượng hàng hải toàn cầu, hoàn toàn không làm sai lệch xu hướng vĩ mô.

---

## 5. Danh Mục Dữ Liệu Tầng Đã Xử Lý (Physical Processed Layer)

Toàn bộ logic trên đã được thực thi và kết xuất thành công thành các tệp Parquet chuẩn hóa tại thư mục vật lý `data/processed/`:

| Tên tệp vật lý | Bảng tương ứng trong DuckDB / MotherDuck | Số lượng dòng | Kích thước lưu trữ |
| :--- | :--- | ---: | ---: |
| `eia_energy_prices_staging.parquet` | `silver.stg_eia_energy_prices` | 2,899 | 26.4 KB |
| `eia_energy_prices_daily_filled.parquet` | `silver.int_energy_prices_daily_filled` | 4,234 | 53.4 KB |
| `imf_chokepoint_daily_processed.parquet` | `silver.stg_imf_chokepoint_daily` | 59,276 | 2,924.0 KB |
| `maritime_energy_daily_joined.parquet` | `silver.int_maritime_energy_daily_joined` | 59,276 | 3,041.2 KB |
