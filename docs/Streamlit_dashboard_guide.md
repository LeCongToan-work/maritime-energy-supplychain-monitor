# Tài liệu Tổng quan & Hướng dẫn Sử dụng Streamlit Dashboard

**Ứng dụng:** Maritime & Energy Supply Chain Monitor (`app/streamlit_app.py`)  
**Nhánh phát triển:** `feature/streamlit-dashboard`  
**Nguồn dữ liệu:** Kho dữ liệu `bi_mart` trong DuckDB (`data/maritime_dwh.duckdb`) / Parquet (`data/gold/*.parquet`), đồng bộ từ **IMF PortWatch** (28 điểm nghẽn hàng hải) và **U.S. EIA API v2** (giá dầu thô Brent & dầu diesel ULSD), cập nhật giai đoạn `01/01/2021 – 01/11/2026` (`59.668` bản ghi ngày–điểm nghẽn).

---

## 1. Mục tiêu & Đối tượng phục vụ

Dashboard được tách thành **2 trang độc lập**, thiết kế theo nguyên tắc **thông tin đi từ tổng quan điều hành đến phân tích vận hành chi tiết**, với các chức năng chọn và bộ lọc tập trung gọn trong **thanh điều hướng bên trái (`Sidebar`)**:

| Trang | Đối tượng phục vụ | Câu hỏi cốt lõi cần trả lời |
| :--- | :--- | :--- |
| **Trang 1 · Tổng quan Điều hành** | **Ban điều hành / Lãnh đạo doanh nghiệp** (Giám đốc Chuỗi cung ứng, Giám đốc Logistics, Quản lý Mua hàng Năng lượng) | Hệ thống hàng hải có đang gặp vấn đề không? Nặng nhất ở đâu? Mức độ sụt giảm lưu lượng (thiệt hại) và mức hấp thụ sang tuyến vòng (lợi ích) cùng biến động giá dầu ra sao? |
| **Trang 2 · Phân tích Điểm nghẽn** | **Cấp vận hành & Phân tích chuyên sâu** (Chuyên viên Kế hoạch tuyến vận tải, Chuyên viên Quản trị Rủi ro Logistics, Chuyên viên Phân tích Dữ liệu) | Diễn biến theo tuần của từng điểm nghẽn ra sao? Điểm nào là biến động thật hay nghi lỗi cảm biến AIS? Lưu lượng phân bố trên bản đồ thế giới thế nào và có đồng biến động với giá nhiên liệu trong khoảng lịch đang xét hay không? |

---

## 2. Thanh điều hướng & Bộ lọc hợp nhất (Left Sidebar)

Thanh điều hướng đặt bên trái và **mặc định thu gọn (`collapsed`)** để nhường tối đa không gian hiển thị cho biểu đồ. Khi bấm nút mở rộng (`>`), người dùng điều khiển toàn bộ Dashboard qua 4 thành phần dùng chung giữa cả 2 trang:

1. **Chọn trang hiển thị:** Chuyển qua lại giữa `Trang 1 · Tổng quan Điều hành` và `Trang 2 · Phân tích Điểm nghẽn`.
2. **📅 Khoảng thời gian (Quét trên lịch):** Bộ chọn lịch (`st.date_input`, định dạng `DD/MM/YYYY`) cho phép quét trực tiếp ngày bắt đầu – kết thúc trên lịch (`01/01/2021` – `01/11/2026`). Khoảng thời gian chọn được đồng bộ tự động giữa Trang 1 và Trang 2.
3. **📍 Chọn điểm nghẽn theo dõi:** Danh sách chọn đa điểm (`st.multiselect`) gồm toàn bộ **28 điểm nghẽn hàng hải** (mặc định: `Bab el-Mandeb Strait`, `Suez Canal`, `Strait of Hormuz`). Toàn bộ thẻ KPI và biểu đồ trên cả 2 trang chạy riêng theo đúng nhóm điểm nghẽn đã chọn.
4. **🚢 Loại tàu phân tích *(chỉ hiện ở Trang 2)*:** Chọn xem theo `Tổng số tàu (Tổng)`, `Tàu chở dầu (Tanker)` hoặc `Tàu Container`.

Cuối thanh điều hướng hiển thị cố định **Trạng thái độ tươi dữ liệu** (`Dữ liệu đến ngày ...` kèm nhãn màu xanh/vàng/đỏ) và **Định nghĩa nền thống nhất (`01/01/2021 – 31/12/2022`)**.

---

## 3. Chi tiết chức năng từng trang

### 3.1. Trang 1 · Tổng quan Điều hành (`Executive Overview`)

1. **Banner kết luận tự sinh & Độ tươi dữ liệu:**
   - Tự động sinh câu tóm tắt 1 dòng từ dữ liệu trong khoảng lịch chọn, tô màu nền/viền theo mức độ nghiêm trọng (`CẢNH BÁO CAO` / `CẢNH BÁO TRUNG BÌNH` / `ỔN ĐỊNH`).
   - Gộp sẵn số điểm nghẽn đang ở mức cảnh báo `High`/`Critical` trên tổng `28` điểm nghẽn kèm **Top 3 điểm nghẽn giảm sâu nhất**, phần trăm lệch nền của nhóm đang chọn, tỷ trọng tàu Á–Âu đi vòng Mũi Hảo Vọng và giá dầu Brent.
2. **Hệ thống thẻ KPI gắn nhãn `● Thiệt hại` / `● Lợi ích`:**
   - **Thẻ điểm nghẽn đang chọn (tự thích ứng):** Hiển thị thẻ riêng cho từng điểm nếu chọn `≤ 2` điểm, hoặc hiển thị thẻ *Điểm nặng nhất trong nhóm* + *Trung bình nhóm chọn* nếu chọn `≥ 3` điểm. Mỗi thẻ gồm số `% vs nền`, so sánh tàu/ngày, nhãn màu `● Thiệt hại` / `● Lợi ích` và biểu đồ sparkline SVG nội tuyến.
   - **Thẻ Giá dầu Brent (`$/bbl` — `● Thiệt hại`):** Giá hiện tại, `%` thay đổi 30 ngày, `%` so với nền `2021–2022` và biến động 30 ngày (`brent_volatility_30d`).
   - **Thẻ Tuyến đi vòng Mũi Hảo Vọng (`● Lợi ích` duy nhất):** Đo lường trực tiếp lưu lượng tăng thêm tại Mũi Hảo Vọng (`%` so với nền, số tàu/ngày) và tỷ trọng hấp thụ trên hành lang Á–Âu.
3. **Biểu đồ chính 2 tầng chung trục thời gian (tự động co giãn kích thước):**
   - **Tầng trên:** Vẽ `% lệch MA7 so với nền` của đúng các điểm nghẽn đang chọn. Chiều cao biểu đồ và lề chú giải tự động co giãn tương ứng với số lượng đường được chọn.
   - **Tầng dưới:** Vẽ diễn biến giá dầu thô **Brent (`$/bbl`)** và **Diesel ULSD proxy (`$/bbl`)**, đánh dấu các vùng sự kiện lịch sử bằng **tên tiếng Việt ngắn** (*Ever Given, 03/2021*; *Hạn hán Panama, 07/2023*; *Biển Đỏ, 11/2023*; *Hormuz, 02/2026*).

---

### 3.2. Trang 2 · Phân tích Điểm nghẽn (`Operational & Risk Analytics`)

Trang 2 hiển thị 4 khối phân tích trực quan chạy đồng bộ theo **Khoảng lịch quét**, **Nhóm điểm nghẽn đang chọn** và **Loại tàu**, cùng 1 mục mở rộng kỹ thuật:

1. **Biến động lưu lượng theo tuần (Heatmap):**
   - Hiển thị `% lệch so với nền` theo từng tuần cho các điểm nghẽn đã chọn, sắp xếp từ điểm giảm sâu nhất đến điểm tăng mạnh nhất. Chiều cao tự co giãn theo số dòng điểm nghẽn.
2. **Diễn biến lưu lượng thực tế so với dải nền & cảnh báo nghi lỗi AIS:**
   - **Khi chọn 1 điểm nghẽn:** Vẽ lưu lượng ngày, đường trung bình 7 ngày (`MA7`), **dải nền `2021–2022` ($\pm 1$ độ lệch chuẩn)** và đường nền trung bình nét đứt.
   - **Khi chọn $\ge 2$ điểm nghẽn:** Quy đổi về cùng thang `% lệch MA7 so với nền` để so sánh trực tiếp giữa các eo biển có quy mô khác nhau.
   - **Chấm xám (`Nghi lỗi AIS — nhãn L10`):** Đánh dấu các ngày có lưu lượng nhưng thiếu dữ liệu trọng tải AIS (`capacity = 0`) hoặc đóng băng tín hiệu để tránh nhầm lẫn với sự cố tắc nghẽn thật.
3. **Bản đồ phân bố lưu lượng & biến động tại các điểm nghẽn (Scattergeo Map):**
   - Thể hiện toàn bộ 28 điểm nghẽn bằng các **dấu chấm trên bản đồ thế giới** (tọa độ từ `bi_mart.dim_chokepoints`).
   - **Kích thước chấm** tỉ lệ thuận với lưu lượng tàu trung bình/ngày trong khoảng lịch chọn; **màu sắc** thể hiện mức tăng/giảm `% vs nền` (đỏ/vàng = giảm, xanh = tăng); nhóm điểm nghẽn đang chọn được làm nổi bật kèm nhãn tên và `%` trực tiếp trên bản đồ.
4. **Đồng biến động lưu lượng điểm nghẽn đã chọn và giá nhiên liệu (chuẩn hóa = 100):**
   - Chuẩn hóa lưu lượng `MA7` của các điểm nghẽn đã chọn cùng giá **Brent** và **Diesel ULSD** về gốc `100` tại ngày đầu khoảng lịch chọn, giúp đối chiếu trực quan biến động tương đối quanh các vùng sự kiện.
   - Kèm ghi chú bắt buộc: *Chỉ phản ánh đồng biến động trong khoảng lịch đã chọn, không kết luận quan hệ nhân quả.*
5. **Mục mở rộng kỹ thuật (`🔧 Mở rộng`):**
   - **Tương quan có độ trễ (Chuỗi sai phân dừng $\Delta_7$):** Biểu đồ tương quan lăn 90 ngày và tương quan trễ (`Lag k = -14..+14` ngày) tính trên chuỗi sai phân dừng $I(0)$ để tránh tương quan giả.
   - **Mô phỏng chi phí đi vòng (Theo giả định):** 3 thanh trượt giả định (*Số ngày đi vòng thêm*, *Tiêu hao tấn/ngày*, *Giá nhiên liệu $/tấn*), ghi rõ là ước tính theo giả định tham khảo (`UNCTAD 2024`, `IMO 2020`), không phải số đo thực tế từ kho dữ liệu.
   - **Chất lượng dữ liệu (AIS `L10` & Ngày điền khuyết `is_forward_filled`):** Bảng tra cứu các ngày nghi lỗi cảm biến `L10` trong nhóm đang chọn và biểu đồ minh họa các ngày cuối tuần/ngày lễ điền khuyết giá LOCF tạo ra lợi suất ngày `0%`.

---

## 4. Chân trang thống nhất & Khả năng tương thích giao diện

- **Một định nghĩa nền duy nhất ở chân cả 2 trang:** *Trung bình ngày giai đoạn chuẩn 2 năm: `01/01/2021 – 31/12/2022` (730 ngày)*, kèm nguồn dữ liệu và giới hạn đo lường (*Diesel ULSD là chỉ báo proxy, không phải giá bunker cảng; kho dữ liệu không có cước vận tải Freight và phụ phí BAF*).
- **Hỗ trợ cả Chế độ Sáng (Light Mode) & Chế độ Tối (Dark Mode):** Toàn bộ thẻ CSS dùng biến chủ đề của Streamlit (`var(--text-color)`, `var(--secondary-background-color)`), biểu đồ Plotly và bản đồ dùng nền trong suốt cùng bảng màu tương phản cao.

---

## 5. Cách khởi chạy cục bộ

```powershell
venv\Scripts\streamlit.exe run app/streamlit_app.py
```
