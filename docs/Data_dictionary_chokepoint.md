# TỪ ĐIỂN DỮ LIỆU: GIÁ NĂNG LƯỢNG GIAO NGAY HOA KỲ (U.S. EIA)

## 1. Thông Tin Chung Về Tập Dữ Liệu
* **Tên file vật lý (Bronze Layer):** `data/raw/eia_energy_prices_daily_raw.parquet`
* **Nguồn cung cấp:** Cơ quan Thông tin Năng lượng Hoa Kỳ (U.S. Energy Information Administration — EIA Open Data API v2).
* **Độ mịn dữ liệu (Grain):** Theo ngày giao dịch thương mại ($\sim 251\,\text{ngày/năm}$) đối với từng mặt hàng năng lượng.
* **Chiến lược lưu trữ tầng Bronze:** Toàn bộ **12 trường dữ liệu** được ép kiểu thành chuỗi (`pandas_type: object` / `numpy_type: str`) ngay tại bước Ingestion nhằm đảm bảo tính bất biến của dữ liệu thô và ngăn ngừa lỗi gãy đường ống (Schema Drift / Type Cast Error) khi API nguồn thay đổi định dạng.

---

## 2. Chi Tiết Các Trường Dữ Liệu (Schema Definition)

| STT | Tên Trường (Field Name) | Kiểu Dữ Liệu (Bronze) | Kiểu Đích (Silver/dbt) | Giải Thích Chi Tiết & Giá Trị Thực Tế Trong File |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `period` | `object` (`str`) | `DATE` | Ngày ghi nhận mức giá giao dịch trên thị trường (định dạng `YYYY-MM-DD`, ví dụ: `2021-01-04` đến `2026-10-14`). Chỉ bao gồm các ngày làm việc có giao dịch thương mại (không có Thứ Bảy, Chủ Nhật và ngày lễ tài chính). |
| 2 | `duoarea` | `object` (`str`) | `VARCHAR` | Mã định danh khu vực địa lý theo chuẩn phân loại của U.S. EIA (kết hợp vùng sản xuất hoặc thị trường tiêu thụ). |
| 3 | `area-name` | `object` (`str`) | `VARCHAR` | Tên đầy đủ của khu vực địa lý tương ứng với mã `duoarea` (ví dụ: khu vực Bờ Vịnh Hoa Kỳ — *U.S. Gulf Coast* hoặc Châu Âu — *Europe*). |
| 4 | `product` | `object` (`str`) | `VARCHAR` | Mã định danh mặt hàng năng lượng theo danh mục chuẩn của EIA. Trong tập dữ liệu gồm 2 mã:<br>• `EPCBRENT`: Dầu thô Brent.<br>• `EPD2DXL0`: Dầu Diesel hàm lượng lưu huỳnh cực thấp (ULSD). |
| 5 | `product-name` | `object` (`str`) | `VARCHAR` | Tên thương mại đầy đủ của mặt hàng năng lượng:<br>• `UK Brent Crude Oil`: Dầu thô Brent Biển Bắc (chuẩn định giá dầu thô quốc tế).<br>• `No 2 Diesel Low Sulfur (0-15 ppm)`: Dầu Diesel số 2 hàm lượng lưu huỳnh cực thấp từ $0 - 15\,\text{ppm}$ (nhiên liệu tiêu chuẩn cho vận tải hạng nặng và hàng hải). |
| 6 | `process` | `object` (`str`) | `VARCHAR` | Mã quy trình hoặc loại hình giao dịch thương mại theo chuẩn phân loại của EIA. |
| 7 | `process-name` | `object` (`str`) | `VARCHAR` | Tên loại hình giao dịch. Giá trị trong file là `Spot Price FOB` (Giá giao ngay tại cảng bốc hàng — *Free On Board*, mức giá thực tế tại điểm xuất phát chưa bao gồm chi phí bảo hiểm và cước vận chuyển đường biển). |
| 8 | `series` | `object` (`str`) | `VARCHAR` | Mã chuỗi dữ liệu duy nhất (Series ID) của EIA dùng làm khóa định danh khi truy vấn API:<br>• `RBRTE`: Chuỗi giá dầu thô Brent châu Âu.<br>• `EER_EPD2DXL0_PF4_RGC_DPG`: Chuỗi giá dầu Diesel ULSD tại vùng Vịnh Hoa Kỳ. |
| 9 | `series-description` | `object` (`str`) | `VARCHAR` | Mô tả chi tiết toàn diện về chuỗi dữ liệu kèm đơn vị đo lường:<br>• `Europe Brent Spot Price FOB (Dollars per Barrel)`<br>• `U.S. Gulf Coast Ultra-Low Sulfur No 2 Diesel Spot Price (Dollars per Gallon)` |
| 10 | `value` | `object` (`str`) | `DOUBLE` / `DECIMAL` | Mức giá giao dịch của mặt hàng năng lượng tại ngày tương ứng (ví dụ: `50.37`, `99.87` đối với dầu Brent; `1.397`, `3.16` đối với Diesel). |
| 11 | `units` | `object` (`str`) | `VARCHAR` | Đơn vị tiền tệ đo lường mức giá:<br>• `$/BBL`: Đô la Mỹ trên mỗi thùng dầu (*Barrel* $\approx 158{,}987\,\text{lít}$) áp dụng cho dầu thô Brent.<br>• `$/GAL`: Đô la Mỹ trên mỗi Gallon Mỹ ($\approx 3{,}785\,\text{lít}$) áp dụng cho dầu Diesel ULSD. |
| 12 | `_ingested_at_utc` | `object` (`str`) | `TIMESTAMPTZ` | Dấu thời gian (Timestamp) theo chuẩn múi giờ quốc tế UTC ghi nhận thời điểm script Python hoàn tất trích xuất bản ghi và lưu vào tầng Bronze (ví dụ: `2026-10-20T13:44:08.106740+00:00`). |

---

## 3. Lưu Ý Khi Biến Đổi Dữ Liệu Tại Tầng Silver/Gold (dbt Core)
1. **Ép kiểu an toàn (`TRY_CAST`):** Trường `value` cần được chuyển đổi sang kiểu số thực (`DOUBLE` hoặc `DECIMAL(10,3)`) và `period` chuyển sang kiểu `DATE`.
2. **Xử lý lệch pha lịch giao dịch (Causal Forward-Fill):** Do dữ liệu EIA nghỉ giao dịch vào cuối tuần và ngày lễ trong khi tàu biển di chuyển liên tục $365\,\text{ngày/năm}$, ở tầng Intermediate (`int_*`), mức giá năng lượng vào ngày nghỉ sẽ được điền khuyết bằng mức giá đóng cửa của ngày giao dịch liền trước đó ($\text{Forward-Fill}$) để phục vụ phân tích tương quan chuỗi thời gian mà không gây rò rỉ dữ liệu tương lai (*Data Leakage*).