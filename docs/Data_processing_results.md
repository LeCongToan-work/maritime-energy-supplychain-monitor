# BÁO CÁO KẾT QUẢ: XỬ LÝ DỮ LIỆU THEO PHƯƠNG ÁN 1A, 2A, 3A

## 1. Thông Tin Chung

* **Công cụ:** dbt Core 1.12.6 + dbt-duckdb 1.11.0, chạy trên DuckDB local (`target: dev`, file `data/maritime_dwh.duckdb`).
* **Nguồn đầu vào (Bronze):** `data/raw/eia_energy_prices_daily_raw.parquet` (2,899 dòng) và `data/raw/imf_chokepoint_daily_raw.parquet` (59,276 dòng).
* **Cách chạy:**
  ```powershell
  cd dbt_maritime
  ..\venv\Scripts\dbt.exe build --select stg_eia_energy_prices stg_imf_chokepoint_daily int_energy_prices_daily_filled
  ```
* **Kết quả chạy:** `PASS=13 WARN=0 ERROR=0` (3 view model + 10 data test).
* **Các file đã tạo:**
  | Phương án | File | Tầng |
  | :---: | :--- | :---: |
  | 1A | `dbt_maritime/models/staging/stg_eia_energy_prices.sql` | Silver / Staging |
  | 3A | `dbt_maritime/models/staging/stg_imf_chokepoint_daily.sql` | Silver / Staging |
  | 2A | `dbt_maritime/models/intermediate/int_energy_prices_daily_filled.sql` | Intermediate |
  | Test | `dbt_maritime/models/schema.yml`, `tests/assert_imf_capacity_rounding_within_tolerance.sql`, `tests/assert_forward_fill_is_causal.sql` | Test |
  | 3A | `src/utils/data_quality_checker.py` (thêm dung sai làm tròn) | Data Quality |

---

## 2. Phương Án 1A: Điền `area-name` Ở Tầng Staging

### 2.1. Cách làm
* Tầng Bronze giữ nguyên `"NA"`. Trường gốc được đổi tên thành `area_name_raw`, trường mới `area_name` được map từ `duoarea`:
  * `ZEU` $\rightarrow$ `Europe`
  * `RGC` $\rightarrow$ `U.S. Gulf Coast`
  * Mã khác $\rightarrow$ `NULLIF(area_name_raw, 'NA')`, tức giữ `NULL` thay vì để chuỗi `"NA"`. Nếu EIA thêm mã vùng mới, dòng đó sẽ lộ ra trong test `not_null` thay vì lọt âm thầm.
* Đồng thời ép kiểu: `period_date` $\rightarrow$ `DATE`, `price_value` $\rightarrow$ `DOUBLE`, `ingested_at_utc` $\rightarrow$ `TIMESTAMPTZ`.

### 2.2. Kết quả

| `duoarea` | `area_name_raw` | `area_name` (sau xử lý) | Số dòng |
| :---: | :---: | :--- | ---: |
| `RGC` | `NA` | `U.S. Gulf Coast` | 1,441 |
| `ZEU` | `NA` | `Europe` | 1,458 |

* `area_name` hết `NULL` trên `2,899/2,899` dòng, chỉ còn 2 giá trị hợp lệ. Hai test `not_null` và `accepted_values` đều PASS.
* Các dòng có `area_name_raw = 'NA'` ở cả 2 nhóm đều được map đúng. Số dòng mỗi nhóm khớp 100% với số dòng mỗi series trong Bronze (1,441 và 1,458).

---

## 3. Phương Án 2A: Causal Forward-Fill Trên Calendar Spine

### 3.1. Cách làm
* Tạo trục lịch liên tục từ `min` đến `max` của `observation_date` trong IMF PortWatch ($2021\text{-}01\text{-}01 \rightarrow 2026\text{-}10\text{-}18$, `2,117` ngày), nhân chéo với 2 series giá.
* Join giá quan sát được vào trục lịch, sau đó `last_value(... ignore nulls)` theo cửa sổ `unbounded preceding -> current row`. Cửa sổ chỉ nhìn về quá khứ nên không có rò rỉ dữ liệu tương lai.
* Các cột kiểm toán đi kèm:
  * `price_value_observed`: giá gốc, `NULL` ở ngày không giao dịch.
  * `is_forward_filled`: cờ đánh dấu ngày được điền.
  * `last_trading_date` và `days_since_last_trade`: ngày giao dịch gần nhất và khoảng cách đến ngày hiện tại.

### 3.2. Kết quả

| Series | Số ngày lịch | Ngày có giao dịch | Ngày được điền | Ngày `NULL` đầu kỳ | Khoảng cách điền tối đa |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `RBRTE` (Europe) | 2,117 | 1,458 | 656 | 3 | 4 ngày |
| `EER_EPD2DXL0_PF4_RGC_DPG` (U.S. Gulf Coast) | 2,117 | 1,441 | 673 | 3 | 4 ngày |

* Bảng `int_energy_prices_daily_filled` có `4,234` dòng (= 2 series $\times$ 2,117 ngày).
* **Phân bố khoảng cách điền** (`days_since_last_trade`):

  | Series | 1 ngày | 2 ngày | 3 ngày | 4 ngày |
  | :--- | ---: | ---: | ---: | ---: |
  | `RBRTE` | 311 | 302 | 32 | 11 |
  | `EER_EPD2DXL0_PF4_RGC_DPG` | 321 | 302 | 48 | 2 |

* **Ví dụ Brent Thứ Sáu $\rightarrow$ Thứ Hai (`2021-01-08` đến `2021-01-11`):**

  | Ngày | Thứ | Giá gốc | Giá sau xử lý | Ngày giao dịch gần nhất | Đã điền |
  | :--- | :--- | ---: | ---: | :--- | :---: |
  | 2021-01-08 | Friday | 55.51 | 55.51 | 2021-01-08 | Không |
  | 2021-01-09 | Saturday | `NaN` | 55.51 | 2021-01-08 | Có |
  | 2021-01-10 | Sunday | `NaN` | 55.51 | 2021-01-08 | Có |
  | 2021-01-11 | Monday | 54.84 | 54.84 | 2021-01-11 | Không |

* Test `assert_forward_fill_is_causal` PASS: mọi dòng được điền đều có `last_trading_date` nhỏ hơn `calendar_date` và giá đúng bằng giá của phiên đó.

---

## 4. Phương Án 3A: Dung Sai Làm Tròn Và Tính Lại Trọng Tải

### 4.1. Cách làm
* **Tầng Staging:** tính lại `capacity_cargo = capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro` và `capacity = capacity_cargo + capacity_tanker`. Giá trị gốc của IMF được giữ ở `capacity_cargo_raw` và `capacity_raw`, kèm 2 cột chênh lệch `capacity_cargo_rounding_diff` và `capacity_rounding_diff`.
* **Test dbt** `assert_imf_capacity_rounding_within_tolerance`: báo lỗi nếu chênh lệch gốc vượt $3$ tấn (4 nhóm tàu hàng) hoặc vượt $1$ tấn (cargo + tanker).
* **`data_quality_checker.py`:** quy tắc `capacity_cargo` dùng dung sai $3$ tấn và quy tắc `capacity` dùng dung sai $1$ tấn.

### 4.2. Kết quả

| Chênh lệch gốc (tấn) | `capacity_cargo` (số dòng) | `capacity` (số dòng) |
| :---: | ---: | ---: |
| 0 | 14,702 | 32,378 |
| 1 | 28,071 | 26,898 |
| 2 | 15,251 | 0 |
| 3 | 1,252 | 0 |
| $> 3$ | 0 | 0 |

* Sau khi tính lại: số dòng vi phạm `capacity_cargo` là `0/59,276`, `capacity` là `0/59,276`.
* Mức thay đổi lớn nhất so với giá trị gốc IMF trên một dòng là $4$ tấn, tổng thay đổi chiếm $0.000069\%$ tổng trọng tải.
* Ví dụ `2023-05-20`, `chokepoint1`: `capacity_cargo` gốc `2,740,007` $\rightarrow$ `2,740,005`; `capacity` gốc `4,243,411` $\rightarrow$ `4,243,409`.
* Chạy lại `data_quality_checker.py` sau khi thêm dung sai: IMF PortWatch còn `0` lỗi (trước đó 2 lỗi `capacity_cargo` và `capacity`). EIA vẫn báo 1 lỗi `area-name` ở Bronze, đúng như thiết kế vì phương án 1A giữ nguyên Bronze và chỉ sửa ở Staging.

---

## 5. Các Điểm Cần Đánh Giá

1. **4 ngày cuối kỳ là giá "cũ", không phải giá quan sát.** File EIA kết thúc ở `2026-10-14`, còn IMF PortWatch đến `2026-10-18`. Trục lịch lấy theo IMF nên các ngày `2026-10-15` đến `2026-10-18` đều mang giá của `2026-10-14` (`days_since_last_trade` từ 1 đến 4). Nếu dùng các ngày này để tính tương quan sát mốc cuối thì nên lọc `days_since_last_trade <= 3` hoặc cắt trục lịch tại ngày cuối của EIA.
2. **3 ngày đầu kỳ (`2021-01-01` đến `2021-01-03`) có giá `NULL`.** EIA bắt đầu từ `2021-01-04` nên không có giá trước đó để điền. Phương án 2A không back-fill nên các ngày này `NULL`, để tránh dùng giá tương lai.
3. **Số liệu thực tế khác với ước tính trong note trước:**
   * Ngày cuối tuần được điền là `604` ngày mỗi series (note ước tính khoảng 630).
   * Chênh lệch giữa 2 series là `17` ngày (`673 - 656`), khớp với `1,458 - 1,441`. Phần lớn ngày lễ khác nhau rơi vào ngày làm việc: `52` ngày (Brent) và `69` ngày (Diesel).
4. **Dung sai $3$ và $1$ tấn bám sát cận lý thuyết $k-1$,** chặt hơn con số $\pm 4$ và $\pm 2$ nêu trong note trước. Dữ liệu thực tế đạt đúng cận ($3$ tấn cho 4 nhóm, $1$ tấn cho 2 nhóm), cho thấy IMF đã cắt phần thập phân từng cột. Nếu muốn nới thêm khoảng đệm thì chỉ cần sửa hằng số trong test và checker.
5. **`capacity` tính lại thấp hơn giá trị gốc tối đa 4 tấn.** Vì IMF cắt phần thập phân từng cột, tổng các thành phần luôn $\le$ tổng thực. Sai lệch này không đáng kể ($0.000069\%$) nhưng nếu cần khớp tuyệt đối với số liệu công bố của IMF thì có thể giữ `capacity_raw`.
6. **Model đang là `view` đọc trực tiếp file Parquet bằng đường dẫn tương đối `../data/raw`,** nên các lệnh truy vấn phải chạy từ thư mục `dbt_maritime`. Khi chuyển sang MotherDuck (`prod_motherduck`) nên đổi sang `source()` trỏ vào các bảng `raw.*` đã nạp lên cloud.
7. **Mới xử lý đúng 3 vấn đề đã chọn.** Chưa có tầng `marts`, chưa nối dữ liệu tàu biển với giá năng lượng, chưa dùng bảng seed `geopolitical_events`.
