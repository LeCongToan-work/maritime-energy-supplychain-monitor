# TỪ ĐIỂN DỮ LIỆU: LƯU LƯỢNG ĐIỂM NGHẼN HÀNG HẢI (IMF PORTWATCH)

## 1. Thông Tin Chung Về Tập Dữ Liệu
* **Tên file vật lý (Bronze Layer):** `data/raw/imf_chokepoint_daily_raw.parquet`
* **Nguồn cung cấp:** Nền tảng **IMF PortWatch** (Sáng kiến hợp tác giữa Quỹ Tiền tệ Quốc tế IMF và Đại học Oxford), truy xuất qua cổng Esri ArcGIS FeatureServer REST API.
* **Phương pháp thu thập gốc:** Tổng hợp từ tín hiệu Hệ thống Nhận dạng Tự động (**AIS** — *Automatic Identification System*) phát qua vệ tinh của toàn bộ đội tàu thương mại toàn cầu đi qua ranh giới địa lý (geofencing polygons) của **28 điểm nghẽn hàng hải chiến lược** (Kênh đào Suez, Kênh đào Panama, Eo biển Hormuz, Eo biển Malacca, Bab el-Mandeb,...).
* **Độ mịn dữ liệu (Grain):** Theo ngày lịch biểu liên tục ($365\,\text{ngày/năm}$) tại từng điểm nghẽn hàng hải.

---

## 2. Chi Tiết Các Trường Dữ Liệu (Schema Definition)

Tập dữ liệu bao gồm **22 trường dữ liệu**, được chia thành 4 nhóm chức năng nghiệp vụ:

### Nhóm A: Các Trường Thời Gian & Định Danh Điểm Nghẽn

| STT | Tên Trường (Field Name) | Kiểu Dữ Liệu (Bronze) | Kiểu Đích (Silver/dbt) | Giải Thích Chi Tiết & Giá Trị Thực Tế Trong File |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `date` | `object` (`str`) | `DATE` | Ngày quan trắc lưu lượng tàu đi qua điểm nghẽn (định dạng `YYYY-MM-DD`, ví dụ: `2021-01-01`, `2024-06-22`). Dữ liệu ghi nhận liên tục mọi ngày trong năm. |
| 2 | `year` | `int64` | `INTEGER` | Năm quan trắc (trích xuất từ trường `date`, ví dụ: `2021` đến `2026`). |
| 3 | `month` | `int64` | `INTEGER` | Tháng quan trắc trong năm (từ `1` đến `12`). |
| 4 | `day` | `int64` | `INTEGER` | Ngày quan trắc trong tháng (từ `1` đến `31`). |
| 5 | `portid` | `object` (`str`) | `VARCHAR` | Mã định danh duy nhất của điểm nghẽn hàng hải trên hệ thống IMF PortWatch (ví dụ: `chokepoint1`, `chokepoint2`,... đến `chokepoint28`). |
| 6 | `portname` | `object` (`str`) | `VARCHAR` | Tên thương mại quốc tế của điểm nghẽn hàng hải chiến lược (ví dụ: `Suez Canal`, `Panama Canal`, `Strait of Hormuz`). |

### Nhóm B: Các Trường Số Lượng Tàu Đi Qua (`n_*` — Daily Vessel Transit Counts)
Phản ánh số lượt tàu thương mại thực tế hoàn tất hành trình đi qua điểm nghẽn trong ngày, được phân loại theo từng chủng loại tàu:

| STT | Tên Trường (Field Name) | Kiểu Dữ Liệu (Bronze) | Giải Thích Chi Tiết Theo Chuẩn Nghiệp Vụ Hàng Hải (IMF PortWatch) |
| :---: | :--- | :---: | :--- |
| 7 | `n_container` | `int64` | Số lượng **tàu chở container** (*Container ships* — chuyên chở hàng hóa tiêu dùng, linh kiện công nghiệp đóng trong thùng container tiêu chuẩn) đi qua điểm nghẽn trong ngày. |
| 8 | `n_dry_bulk` | `int64` | Số lượng **tàu chở hàng rời khô** (*Dry bulk carriers* — chuyên chở nguyên liệu thô không đóng gói như than đá, quặng sắt, ngũ cốc, phân bón). |
| 9 | `n_general_cargo` | `int64` | Số lượng **tàu chở hàng bách hóa tổng hợp** (*General cargo vessels* — chở máy móc, thiết bị siêu trường siêu trọng, hàng đóng kiện không dùng container tiêu chuẩn). |
| 10 | `n_roro` | `int64` | Số lượng **tàu Ro-Ro** (*Roll-on/Roll-off* — loại tàu thiết kế có cầu dẫn để các phương tiện tự hành như ô tô, xe tải, rơ-moóc chạy trực tiếp lên và xuống tàu). |
| 11 | `n_tanker` | `int64` | Số lượng **tàu chở dầu và chất lỏng** (*Tankers* — chuyên chở dầu thô, xăng dầu tinh chế, khí hóa lỏng LNG/LPG, hóa chất). **Đây là biến số có mối liên hệ trực tiếp nhất tới biến động giá năng lượng của EIA.** |
| 12 | `n_cargo` | `int64` | Tổng số lượng **tàu chở hàng khô nói chung** (nhóm tổng hợp gồm `n_container + n_dry_bulk + n_general_cargo + n_roro`, tức không bao gồm tàu chở dầu `n_tanker` theo quy ước phân tổ của IMF PortWatch). |
| 13 | `n_total` | `int64` | **Tổng số lượng tất cả các tàu thương mại** đi qua điểm nghẽn trong ngày ($\text{n\_total} = \text{n\_cargo} + \text{n\_tanker}$). |

### Nhóm C: Các Trường Sức Chứa / Trọng Tải Thông Qua (`capacity_*` — Vessel Transit Capacity)
Theo tài liệu phương pháp luận của IMF PortWatch, các trường `capacity_*` phản ánh tổng khối lượng hàng hóa hoặc trọng tải ước tính (đo bằng đơn vị **Tấn trọng tải toàn phần — Deadweight Tonnage / DWT** hoặc khối lượng hàng hóa chuyên chở ước tính dựa trên kích thước tàu và mớn nước từ tín hiệu AIS) của các tàu đi qua điểm nghẽn:

| STT | Tên Trường (Field Name) | Kiểu Dữ Liệu (Bronze) | Giải Thích Chi Tiết Theo Chuẩn Nghiệp Vụ Hàng Hải (IMF PortWatch) |
| :---: | :--- | :---: | :--- |
| 14 | `capacity_container` | `int64` | Tổng trọng tải/sức chứa của đội **tàu container** đi qua điểm nghẽn trong ngày. |
| 15 | `capacity_dry_bulk` | `int64` | Tổng trọng tải của đội **tàu chở hàng rời khô** (Dry bulk) đi qua điểm nghẽn trong ngày. |
| 16 | `capacity_general_cargo` | `int64` | Tổng trọng tải của đội **tàu chở hàng bách hóa tổng hợp** đi qua điểm nghẽn trong ngày. |
| 17 | `capacity_roro` | `int64` | Tổng trọng tải của đội **tàu Ro-Ro** (chở phương tiện/xe hơi) đi qua điểm nghẽn trong ngày. |
| 18 | `capacity_tanker` | `int64` | Tổng trọng tải của đội **tàu chở dầu và nhiên liệu (Tanker)** đi qua điểm nghẽn trong ngày. *Chỉ số này phản ánh sát thực tế quy mô nguồn cung dầu mỏ/nhiên liệu lưu thông qua điểm nghẽn hơn là chỉ đếm số lượng tàu (`n_tanker`).* |
| 19 | `capacity_cargo` | `int64` | Tổng trọng tải của nhóm **tàu chở hàng khô (`n_cargo`)** đi qua điểm nghẽn trong ngày. |
| 20 | `capacity` | `int64` | **Tổng trọng tải toàn bộ đội tàu thương mại** (*Total Capacity across all vessel types*) đi qua điểm nghẽn trong ngày ($\text{capacity} = \text{capacity\_cargo} + \text{capacity\_tanker}$). |

### Nhóm D: Các Trường Quản Trị Hệ Thống (System & Audit Metadata)

| STT | Tên Trường (Field Name) | Kiểu Dữ Liệu (Bronze) | Giải Thích Chi Tiết |
| :---: | :--- | :---: | :--- |
| 21 | `ObjectId` | `int64` | Khóa chính tự tăng (System Row ID) được sinh ra tự động bởi nền tảng cơ sở dữ liệu không gian **Esri ArcGIS FeatureServer** của IMF PortWatch khi trả kết quả qua REST API. |
| 22 | `_ingested_at_utc` | `object` (`str`) | Dấu thời gian (Timestamp UTC) ghi nhận thời điểm script Python hoàn tất việc tải bản ghi này về tầng Bronze (ví dụ: `2026-10-20T00:21:38.552026+00:00`). |