# Tài liệu Đồng bộ Kho Dữ liệu MotherDuck Cloud & Quy trình Kiểm định CI/CD

**Module chính:**
- [`src/load/load_to_motherduck.py`](file:///e:/maritime-energy-supplychain-monitor/src/load/load_to_motherduck.py) (Bộ tải & đồng bộ dữ liệu đa tầng DuckDB Local & MotherDuck Cloud)
- [`src/utils/validate_pipeline_outputs.py`](file:///e:/maritime-energy-supplychain-monitor/src/utils/validate_pipeline_outputs.py) (Cổng kiểm định chất lượng Pre-load Quality Gate)
- [`.github/workflows/ci_check.yml`](file:///e:/maritime-energy-supplychain-monitor/.github/workflows/ci_check.yml) (Quy trình kiểm thử tích hợp liên tục CI)
- [`.github/workflows/daily_elt_pipeline.yml`](file:///e:/maritime-energy-supplychain-monitor/.github/workflows/daily_elt_pipeline.yml) (Quy trình ELT & đồng bộ đám mây hàng ngày)

---

## 1. Bối cảnh & Mục tiêu Kiến trúc

Dự án Giám sát Chuỗi cung ứng Năng lượng Hàng hải cần phục vụ đồng thời hai môi trường:
1. **Phân tích Cục bộ (Offline Analytics):** Chạy nhanh, không phụ thuộc internet, lưu trữ trong file nhị phân [`data/maritime_dwh.duckdb`](file:///e:/maritime-energy-supplychain-monitor/data/maritime_dwh.duckdb) và các file định dạng cột Parquet (`data/gold/*.parquet`).
2. **Triển khai Đám mây (Cloud Deployment):** Cung cấp backend dữ liệu cho Dashboard Streamlit Community Cloud thông qua kết nối **MotherDuck Cloud (`md:maritime_dwh`)**, bảo đảm không vượt ngưỡng tài nguyên miễn phí (Free Tier Storage < 10 GB) và duy trì tính toàn vẹn khóa ngoại (Referential Integrity).

Để đáp ứng mục tiêu trên, module `src/load/load_to_motherduck.py` và cổng kiểm tra `src/utils/validate_pipeline_outputs.py` được xây dựng nhằm tạo ra cầu nối dữ liệu chuẩn hóa, có kiểm soát và tự động hóa cao.

---

## 2. Đặc tả Cấu trúc Bảng & Ràng buộc Khóa (TABLE_SPECS)

Kho dữ liệu tổ chức theo 3 schema chuẩn kiến trúc Medallion, bao gồm **14 bảng** và **30 ràng buộc Khóa chính (Primary Key) & Khóa ngoại (Foreign Key)**:

### 2.1. Tầng Bronze (`raw`)
- `raw.eia_energy_prices_daily`: Dữ liệu thô giá dầu EIA. `PK(series, period)`.
- `raw.imf_chokepoint_daily`: Dữ liệu thô lưu lượng điểm nghẽn IMF PortWatch. `PK(portid, date)`.

### 2.2. Tầng Silver (`silver`)
- `silver.dim_date`: Bảng chiều thời gian chuẩn hóa 365 ngày (`2021-01-01` đến `2026-11-01`). `PK(date)`.
- `silver.stg_imf_chokepoints`: Bảng staging điểm nghẽn đã làm sạch, xử lý Causal LOCF và chuẩn hóa DWT. `PK(portid, date)`, `FK(date) -> silver.dim_date(date)`.
- `silver.stg_eia_energy_prices`: Bảng staging giá năng lượng đã đồng bộ lịch giao dịch và điền khuyết. `PK(series, period_date)`, `FK(period_date) -> silver.dim_date(date)`.

### 2.3. Tầng Gold / BI Mart (`gold` & `bi_mart`)
Tất cả các bảng trong schema `gold` được ánh xạ view/schema tương đương sang `bi_mart` để phục vụ trực tiếp Streamlit:
1. `gold.dim_chokepoints`: 28 điểm nghẽn hàng hải, tọa độ, phân vùng, vai trò kinh tế. `PK(chokepoint_id)`.
2. `gold.dim_geopolitical_events`: 4 sự kiện địa chính trị trọng đại (`EVT_01`–`EVT_04`). `PK(event_id)`.
3. `gold.dim_chokepoint_rerouting_map`: Bản đồ cặp tuyến thay thế (`Bab el-Mandeb` $\leftrightarrow$ `Cape of Good Hope`, ...). `PK(primary_chokepoint_id, alternative_chokepoint_id)`.
4. `gold.fact_energy_prices_daily`: Chuỗi giá hàng ngày, biến đổi dừng $I(0)$, biên lọc dầu Crack Spread. `PK(date)`, `FK(date) -> silver.dim_date(date)`.
5. `gold.fact_chokepoint_transit_daily`: Lưu lượng tàu, trọng tải DWT, mức cảnh báo, phân loại loại tàu. `PK(chokepoint_id, date)`, `FK(chokepoint_id) -> gold.dim_chokepoints`, `FK(date) -> silver.dim_date`.
6. `gold.fact_chokepoint_energy_regime_daily`: Phân tích cơ chế đồng biến động và tương quan trượt 90 ngày trên chuỗi dừng $I(0)$. `PK(chokepoint_id, date)`.
7. `gold.fact_red_sea_cape_rerouting_daily`: Chỉ số đo lường mức độ chuyển dịch tuyến hàng hải Biển Đỏ sang Mũi Hảo Vọng. `PK(date)`.
8. `gold.fact_outlier_consensus_labeled_daily`: Kết quả phân loại bất thường đồng thuận kép `L00`–`L10` (Cú sốc ngắn hạn, Dịch chuyển cấu trúc, Lỗi cảm biến). `PK(chokepoint_id, date)`.

---

## 3. Thứ tự Thực thi & Nguyên tắc Toàn vẹn (Dependency Management)

Để tránh lỗi vi phạm ràng buộc toàn vẹn khóa ngoại trong cơ sở dữ liệu quan hệ, quy trình đồng bộ thực hiện theo 2 chiều chặt chẽ:

1. **Chiều xóa (Drop Order - Con trước, Cha sau):**
   - Xóa các bảng Fact/Mart trước: `fact_outlier_consensus_labeled_daily` $\rightarrow$ `fact_chokepoint_energy_regime_daily` $\rightarrow$ `fact_chokepoint_transit_daily` $\rightarrow$ `fact_energy_prices_daily` $\rightarrow$ ...
   - Xóa các bảng Dimension sau: `dim_chokepoints` $\rightarrow$ `dim_date` $\rightarrow$ `raw.*`.
2. **Chiều tạo & nạp (Create & Load Order - Cha trước, Con sau):**
   - Tạo và nạp các bảng Dimension và Staging độc lập trước (`silver.dim_date`, `gold.dim_chokepoints`, `gold.dim_geopolitical_events`).
   - Tạo và nạp các bảng Fact/Mart phụ thuộc sau, khai báo rõ ràng mệnh đề `REFERENCES parent_table(key_column)`.
3. **Đối chiếu số lượng dòng (Row-count reconciliation):**
   - Sau khi `INSERT INTO ... SELECT * FROM read_parquet(...)`, tập lệnh tự động đếm số dòng trong DuckDB/MotherDuck và so sánh với file Parquet nguồn. Bất kỳ sự chênh lệch nào đều kích hoạt cảnh báo `CRITICAL`.

---

## 4. Cổng Kiểm định Chất lượng Dữ liệu (Pre-load Gate)

Trước khi gửi bất kỳ lệnh DDL nào lên MotherDuck Cloud, tập lệnh [`src/utils/validate_pipeline_outputs.py`](file:///e:/maritime-energy-supplychain-monitor/src/utils/validate_pipeline_outputs.py) đóng vai trò cổng kiểm soát chất lượng nghiêm ngặt:

- **Kiểm tra sự tồn tại:** Đảm bảo toàn bộ 14 file Parquet nguồn đều hiện diện trên đĩa.
- **Kiểm tra rỗng:** File Parquet có kích thước > 0 byte và số dòng `COUNT(*) > 0`.
- **Kiểm tra tính toàn vẹn nghiệp vụ:**
  - Bảng Staging EIA: Kiểm tra không có giá trị `NULL` trong các trường cốt lõi `area_name`, `period_date`, `price_value`.
  - Bảng Staging IMF: Kiểm tra không có bản ghi nào bị trùng lặp cặp khóa `(portid, date)`.
  - Bảng Gold Dim Chokepoint: Kiểm tra đủ `28` điểm nghẽn với tọa độ địa lý hợp lệ (`latitude` trong `[-90, 90]`, `longitude` trong `[-180, 180]`).
- **Mã phản hồi chuẩn hóa:** Thoát mã lỗi `1` nếu có vi phạm chất lượng, ngăn chặn tuyệt đối việc đẩy dữ liệu bẩn hoặc thiếu sót lên Cloud.

---

## 5. Tự động hóa CI/CD với GitHub Actions

Hệ thống được giám sát và cập nhật tự động thông qua 2 workflow GitHub Actions:

### 5.1. Workflow `ci_check.yml` (Kiểm thử mã nguồn & Cấu hình)
- **Kích hoạt:** Mỗi khi có commit đẩy lên nhánh `main`, `feature/streamlit-dashboard` hoặc khi mở Pull Request.
- **Nhiệm vụ:**
  - Kiểm tra cú pháp toàn bộ module Python trong `src/` và `app/` bằng `compileall`.
  - Kiểm tra tính hợp lệ của cấu hình YAML `config/sources_config.yaml`.
  - Kiểm tra độ toàn vẹn của các file dữ liệu danh mục tĩnh `dbt_maritime/seeds/*.csv`.
  - Xác nhận danh sách `TABLE_SPECS` đủ 14 bảng và mã lỗi giới hạn dung lượng được thiết lập đúng.

### 5.2. Workflow `daily_elt_pipeline.yml` (Đồng bộ hàng ngày & Giám sát Quota)
- **Kích hoạt:** Lịch biểu Cron chạy vào `23:00 UTC` mỗi ngày (tương đương `06:00 sáng` giờ Việt Nam UTC+7) hoặc kích hoạt thủ công qua `workflow_dispatch`.
- **Các bước thực thi tuần tự:**
  1. `actions/checkout@v4` và thiết lập Python 3.11.
  2. Xác minh các biến bí mật môi trường `EIA_API_KEY` và `MOTHERDUCK_TOKEN`.
  3. Chạy Ingestion tầng Bronze (IMF PortWatch & U.S. EIA API).
  4. Chạy Cleansing tầng Silver (Causal LOCF & DWT normalization).
  5. Xây dựng Gold BI Marts và thuật toán phân loại Outlier đồng thuận kép `L00`–`L10`.
  6. Chạy Cổng kiểm tra Pre-load Gate `validate_pipeline_outputs.py`.
  7. Thực hiện tải và đồng bộ lên MotherDuck Cloud kèm cơ chế kiểm tra giới hạn dung lượng an toàn (Stop Threshold 9.0 GB / 10.0 GB).

---

## 6. Hướng dẫn Vận hành & Lệnh Thực thi Cục bộ

```powershell
# 1. Chạy kiểm định toàn vẹn file đầu ra Parquet trước khi nạp
venv\Scripts\python.exe -m src.utils.validate_pipeline_outputs

# 2. Đồng bộ toàn bộ dữ liệu vào Local DuckDB (data/maritime_dwh.duckdb)
venv\Scripts\python.exe -m src.load.load_to_motherduck --local

# 3. Đồng bộ toàn bộ dữ liệu lên MotherDuck Cloud (Yêu cầu MOTHERDUCK_TOKEN trong .env)
venv\Scripts\python.exe -m src.load.load_to_motherduck
```
