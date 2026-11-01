# BÁO CÁO KẾT QUẢ PHÁT HIỆN, KIỂM CHỨNG ĐỒNG THUẬN KÉP VÀ PHÂN LOẠI GÁN NHÃN OUTLIER (`gold.mart_outlier_consensus_labeled_daily`)

## 1. Cơ Sở Học Thuật & Tài Liệu Tham Khảo

Hệ thống phát hiện và phân loại gán nhãn ngoại lai (Outlier) trên dữ liệu chuỗi cung ứng hàng hải (`IMF PortWatch`, `59,276` dòng) và giá năng lượng (`U.S. EIA`, `2,117` ngày) được thực hiện dựa trên 7 công trình nghiên cứu học thuật:

1. **Iglewicz, B., & Hoaglin, D. C. (1993)** — *"How to Detect and Handle Outliers"*, *The ASQC Basic References in Quality Control: Statistical Techniques*, Vol. 16.
   - Phương pháp **Modified Z-Score ($M_t$)** dựa trên Trung vị (`Median`) và Độ lệch tuyệt đối trung vị (`MAD`):
     $$M_t = \frac{0.6745 \times (x_t - \text{Median}_W(x))}{\text{MAD}_W(x)}, \quad \text{với } \text{MAD}_W(x) = \text{Median}_W\big(|x - \text{Median}_W(x)|\big)$$
   - Ngưỡng xác định ngoại lai: $|M_t| > 3.5$.
2. **Tukey, J. W. (1977)** — *"Exploratory Data Analysis"*, Addison-Wesley Publishing.
   - Phương pháp **Hàng rào Tứ phân vị Phi tham số (*Tukey Interquartile Range Fence*)** dựa trên phân vị thứ 25 ($Q_1$) và thứ 75 ($Q_3$):
     $$\text{IQR}_W(x) = Q_{0.75, W}(x) - Q_{0.25, W}(x), \quad \text{Fence}_W = \big[Q_{0.25, W} - 2.0\cdot\text{IQR}_W,\; Q_{0.75, W} + 2.0\cdot\text{IQR}_W\big]$$
3. **Tsay, R. S. (1988)** — *"Outliers, Level Shifts, and Variance Changes in Time Series"*, *Journal of Forecasting*, 7(1), 1–20; và **Chen, C., & Liu, L.-M. (1993)** — *"Joint Estimation of Model Parameters and Outlier Effects in Time Series"*, *Journal of the American Statistical Association (JASA)*, 88(421), 284–297.
   - Khung 4 nhãn cấu trúc động học chuỗi thời gian: **`AO` (*Additive Outlier*)**, **`IO` (*Innovational Outlier*)**, **`TC` (*Temporary Change*)**, và **`LS` (*Level Shift*)**.
4. **Charles, A., & Darné, O. (2005; 2014)** — *"Outlier Detection in GARCH Models"* (*Econometric Reviews*, 24(2), 137–174) & *"Volatility Persistence in Crude Oil Markets"* (*Energy Policy*, 65, 729–742).
   - Phân biệt `AO` (xung giá đơn lẻ đảo chiều ở phiên kế tiếp) và `IO` (cú sốc thông tin lan truyền sang các phiên sau) trên chuỗi lợi suất giá dầu Brent và Diesel.
5. **Chandola, V., Banerjee, A., & Kumar, V. (2009)** — *"Anomaly Detection: A Survey"*, *ACM Computing Surveys (CSUR)*, 41(3), Article 15; và **Blázquez-García, A. et al. (2021)** — *"A Review on Outlier/Anomaly Detection in Time Series Data"*, *ACM Computing Surveys (CSUR)*, 54(3), Article 56.
   - Khung 3 nhãn hình thái dữ liệu: **`Point Anomaly`**, **`Contextual Anomaly`**, và **`Collective (Subsequence) Anomaly`**.
6. **Riveiro, M., Pallotta, G., & Vespe, M. (2018)** — *"Maritime Anomaly Detection: A Review"* (*WIREs Data Mining and Knowledge Discovery*, 8(5), e1266); và **Wolsing, K. et al. (2022)** — *"Anomaly Detection in Maritime AIS Tracks: A Review of Recent Approaches"* (*Journal of Marine Science and Engineering*, 10(1), 112).
   - Phân loại dị thường tín hiệu AIS: `Data-Level Reporting Anomaly` (khuyết bản tin tĩnh AIS Type 5 hoặc tắt phát đáp AIS *go-dark*) và `Route / Spatial Deviation Anomaly`.
7. **Verschuur, J., Koks, E. E., & Hall, J. W. (2022; 2023)** & **IMF PortWatch Methodology (Arslanalp et al., 2023/2024)**.
   - Nhận diện đóng luồng hàng hải ngắn hạn do bão nhiệt đới (*Environmental Port Closure*) và tái định tuyến qua Mũi Hảo Vọng (*Spatial Rerouting*).

---

## 2. Quy Tắc Kiểm Chứng Đồng Thuận Kép (*Dual-Method Consensus Rule*)

Một quan sát tại thời điểm $t$ chỉ được xác nhận là **Outlier Đồng thuận Kép (`Confirmed Consensus Outlier`)** khi cả hai phương pháp độc lập (`Modified Z-Score MAD` và `Tukey IQR Fence`) cùng vượt ngưỡng:

$$\text{Is\_Consensus\_Outlier}(t) = \mathbb{I}\Big(|M_t^{\text{MAD}}| > 3.5\Big) \;\land\; \mathbb{I}\Big(x_t \notin \big[Q_{0.25, W} - 2.0\cdot\text{IQR}_W,\; Q_{0.75, W} + 2.0\cdot\text{IQR}_W\big]\Big)$$

Các trường hợp chỉ vượt ngưỡng ở 1 trong 2 phương pháp ($\text{PP1} \oplus \text{PP2}$) được phân loại là nhiễu biên và bị loại bỏ khỏi tập Outlier chính thức.

---

## 3. Kết Quả Kiểm Tra Lớp 1: Quy Tắc Vật Lý & Bảo Toàn Kỹ Thuật (*Domain Hard Rules*)

| Hạng mục Kiểm tra Quy tắc Cứng | Tập dữ liệu | Số dòng ghi nhận | Chi tiết Kết quả Thực nghiệm |
| :--- | :---: | :---: | :--- |
| **1. Giá trị âm phi vật lý** (`n_total < 0`, `capacity < 0`, `price <= 0`) | Chokepoint (`59,276`) & EIA (`2,117`) | **`0` dòng** | Không có giá trị âm hoặc giá bằng `0` trên toàn bộ tập dữ liệu. |
| **2. Bảo toàn tổng số lượt tàu** (`n_total != sum(n_i)`) | Chokepoint (`59,276`) | **`0` dòng** | Tổng số lượt tàu khớp 100% với tổng 5 chủng loại tàu thành phần. |
| **3. Bảo toàn tổng trọng tải DWT** (`capacity != sum(capacity_i)`) | Chokepoint (`59,276`) | **`0` dòng** | Sau chuẩn hóa Phương án 3A, toàn bộ `59,276` dòng khớp tuyệt đối (trước chuẩn hóa có `26,898` dòng lệch làm tròn `<= 1 DWT`). |
| **4. Bản ghi có tàu nhưng DWT = 0** (`n_total > 0 AND capacity = 0`) | Chokepoint (`59,276`) | **`312` dòng** (`0.53%`) | Xảy ra khi chỉ có `1–6` tàu nhỏ đi qua eo biển (`Bering Strait` 183 dòng, `Magellan` 51 dòng, `Kerch` 50 dòng, `Hormuz` 11 dòng, `Balabac` 6 dòng, `Torres` 4 dòng, `Ombai` 3 dòng, `Bohai`, `Korea`, `Luzon`, `Bosporus` mỗi cảng 1 dòng) nhưng thiếu trường DWT trong bản tin tĩnh AIS Type 5. |
| **5. Điểm nghẽn lớn (`baseline >= 20` tàu/ngày) có `n_total = 0`** | Chokepoint (`59,276`) | **`287` ngày** | Ghi nhận tại 3 điểm nghẽn: `Kerch Strait` (`271` ngày từ `2022-03-20` đến `2026-10-18`), `Strait of Hormuz` (`14` ngày từ `2026-03-04` đến `2026-10-17`), và `Luzon Strait` (`2` ngày: `2021-10-11` và `2025-09-22`). |

---

## 4. Kết Quả Phát Hiện & Gán Nhãn Outlier Giá Năng Lượng (`Brent`, `ULSD`, `Crack Spread`)

Kiểm định được thực hiện trên các phiên giao dịch thực (`is_ffill == False`) với cửa sổ trượt nhân quả $W = 63$ phiên giao dịch (~1 quý):

### 4.1. Thống kê Đồng thuận Kép và Phân loại Nhãn `AO` / `IO` trên Giá Năng lượng

| Biến số Năng lượng (Chuỗi dừng $I(0)$) | Số phiên giao dịch thực ($N$) | PP1: Modified Z-Score ($\|M_t\| > 3.5$) | PP2: Tukey IQR Fence ($k = 2.0$) | **Đồng thuận Kép (`PP1 AND PP2`)** | Số phiên bị loại bỏ (`PP1 XOR PP2`) | Nhãn **`AO` (*Additive Outlier*)** | Nhãn **`IO` (*Innovational Outlier*)** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`brent_log_ret_1d (%)`** | `1,458` | `26` | `35` | **`25` (`1.71%`)** | `11` (`-30.6%`) | `4` phiên | `21` phiên |
| **`ulsd_log_ret_1d (%)`** | `1,441` | `23` | `31` | **`23` (`1.60%`)** | `8` (`-25.8%`) | `5` phiên | `18` phiên |
| **`crack_diff_1d ($/BBL)`** | `1,458` | `37` | `41` | **`34` (`2.33%`)** | `10` (`-22.7%`) | `9` phiên | `25` phiên |

### 4.2. Danh sách các Phiên Outlier Giá Năng lượng có Biên độ Lớn nhất

| Ngày | Chỉ số Năng lượng | Mức giá | Biến động 1 ngày | Điểm `ModZ_MAD` | Điểm `IQR_Exceed` | Nhãn Động học (`energy_ts_label`) | Sự kiện Thực tế Tương ứng |
| :---: | :--- | :---: | :---: | :---: | :---: | :--- | :--- |
| `2021-11-29` | `crack_diff_1d` | `$13.94/bbl` | `-$10.76/bbl` | `-16.27` | `-9.67x` | **`IO` (Innovational Outlier)** | Điều chỉnh biên lọc dầu phiên Thứ Hai sau kỳ nghỉ Lễ Tạ ơn Mỹ. |
| `2021-11-26` | `crack_diff_1d` | `$24.69/bbl` | `+$9.68/bbl` | `+14.62` | `+7.93x` | **`AO` (Additive Outlier)** | Xung lệch giá 1 phiên ngày Thứ Sáu sau Lễ Tạ ơn khi giá Brent sập trước ULSD. |
| `2021-11-26` | `brent_log_ret_1d` | `$72.37/bbl` | `-12.55%` | `-7.54` | `-3.64x` | **`IO` (Innovational Outlier)** | WHO công bố biến chủng COVID-19 Omicron (B.1.1.529) tại Nam Phi. |
| `2022-03-08` | `crack_diff_1d` | `$55.11/bbl` | `+$16.25/bbl` | `+10.50` | `+6.75x` | **`AO` (Additive Outlier)** | Mỹ và Anh công bố lệnh cấm nhập khẩu dầu mỏ từ Nga. |
| `2022-03-09` | `ulsd_log_ret_1d` | `$3.568/gal` | `-22.83%` | `-11.19` | `-6.14x` | **`IO` (Innovational Outlier)** | Nhịp điều chỉnh mạnh của dầu Diesel và Brent (`-13.31%`, `ModZ = -6.93`) sau đỉnh ngày 08/03/2022. |
| `2022-04-29` | `crack_diff_1d` | `$90.26/bbl` | `-$26.39/bbl` | `-8.42` | `-3.72x` | **`IO` (Innovational Outlier)** | Ngày đáo hạn hợp đồng tương lai NYMEX ULSD tháng 5/2022 sau đợt *short squeeze* đẩy Crack Spread lên đỉnh `$116.65/bbl` ngày 28/04/2022. |
| `2022-11-01` | `crack_diff_1d` | `$56.16/bbl` | `-$37.98/bbl` | `-9.02` | `-3.51x` | **`IO` (Innovational Outlier)** | Chuyển kỳ hạn hợp đồng NYMEX ULSD tháng 11/2022 khi giải tỏa tồn kho vùng Đông Bắc Mỹ. |
| `2026-03-04` | `crack_diff_1d` | `$58.43/bbl` | `+$13.77/bbl` | `+8.49` | `+3.39x` | **`IO` (Innovational Outlier)** | Lưu lượng tàu qua Eo biển Hormuz rơi về `0` tàu (`EVT_04`). |
| `2026-03-09` | `crack_diff_1d` | `$40.81/bbl` | `-$16.00/bbl` | `-9.05` | `-4.44x` | **`AO` (Additive Outlier)** | Dao động co giật 1 phiên trong giai đoạn đầu khủng hoảng Hormuz. |
| `2026-03-11` | `crack_diff_1d` | `$61.02/bbl` | `+$13.35/bbl` | `+7.49` | `+2.87x` | **`AO` (Additive Outlier)** | Đợt tăng vọt biên lọc dầu tuần thứ hai của sự kiện phong tỏa Hormuz. |

---

## 5. Kết Quả Phát Hiện & Gán Nhãn Tự Động (`L00`..`L10`) Trên 28 Điểm Nghẽn Hàng Hải (`59,276` Dòng)

### 5.1. Thống kê Đồng thuận Kép trên Lưu lượng 28 Điểm nghẽn

| Cấp độ Kiểm định Lưu lượng Tàu | PP1: Modified Z-Score ($\|M\| > 3.5$) | PP2: Tukey IQR Fence ($k = 2.0$) | **Đồng thuận Kép (`PP1 AND PP2`)** | Số dòng bị loại bỏ (`PP1 XOR PP2`) |
| :--- | :---: | :---: | :---: | :---: |
| **1. Cú sốc Ngắn hạn $I(0)$ (`n_total_diff_7d`, cửa sổ 90 ngày)** | `642` dòng (`1.08%`) | `769` dòng (`1.30%`) | **`578` dòng (`0.98%`)** | `255` dòng (`-30.6%` nhiễu) |
| **2. Đứt gãy Cấu trúc (`n_total_ma7` vs Baseline `2021–2022`)** | `4,046` dòng (`6.83%`) | `3,515` dòng (`5.93%`) | **`3,359` dòng (`5.67%`)** | `843` dòng (lọc `640` ngày nhiễu tại `Bering Strait`) |
| **Tổng hợp hợp nhất (`is_chokepoint_consensus_outlier`)** | — | — | **`3,814` dòng (`6.43%`)** | — |

### 5.2. Phân phối 11 Mã Nhãn Tự Động (`L00` $\rightarrow$ `L10`) trong Bảng `gold.mart_outlier_consensus_labeled_daily`

| Mã Nhãn | Nhãn Chuỗi thời gian<br>*(Tsay 1988; Chen & Liu 1993)* | Nhãn Hình thái<br>*(Chandola 2009; Blázquez-García 2021)* | Nhãn Nghiệp vụ Hàng hải & Năng lượng<br>*(Wolsing 2022; Verschuur & IMF PortWatch)* | Số dòng (`port-days`) | Số cảng | `%` Lệch TB vs Baseline | `Min Shock ModZ` | `Max Struct ModZ` |
| :-: | :--- | :--- | :--- | ---: | :-: | ---: | ---: | ---: |
| **`L00`** | `NONE` | `Normal Observation` | `L00: Normal Maritime Flow` | `55,179` | `28` | `-1.30%` | `-5.441` | `+17.922` |
| **`L01`** | `LS (Level Shift)` | `Collective (Subsequence) Anomaly` | `L01: Origin Energy Export Hub Blockade / Supply Shock` | `274` | `2` | `-83.65%` | `-9.545` | `-3.511` |
| **`L01`** | `IO (Innovational Outlier)` | `Contextual Anomaly` | `L01: Origin Energy Export Hub Acute Disruption Shock` | `20` | `4` | `-24.85%` | `-15.955` | `-0.008` |
| **`L02`** | `LS (Level Shift)` | `Collective (Subsequence) Anomaly` | `L02: Macro Demand Collapse / Recession Shock` | `23` | `5` | `-53.57%` | `-2.255` | `-3.568` |
| **`L03`** | `LS (Level Shift)` | `Collective (Subsequence) Anomaly` | `L03: Sustained Corridor Restriction (Geopolitical / Climate)` | `1,300` | `7` | `-42.91%` | `-6.948` | `-3.501` |
| **`L04`** | `LS (Level Shift)` | `Collective (Subsequence) Anomaly` | `L04: Spatial Rerouting Surge (Detour Absorption)` | `1,159` | `3` | `+90.76%` | `-6.820` | `+18.129` |
| **`L05`** | `TC (Temporary Change)` | `Collective (Subsequence) Anomaly` | `L05: Post-Crisis Route Normalization Transition` | `16` | `4` | `+48.55%` | `-8.273` | `+10.689` |
| **`L06`** | `TC (Temporary Change)` | `Contextual Anomaly` | `L06: Pre-Sanction / Front-Loading Transit Surge` | `3` | `2` | `+9.21%` | `+1.594` | `+3.783` |
| **`L07`** | `TC (Temporary Change)` | `Collective (Subsequence) Anomaly` | `L07: Acute Operational Blockage (Short-Term Canal Halt)` | `220` | `11` | `-52.84%` | `-22.933` | `-0.428` |
| **`L08`** | `AO (Additive Outlier)` | `Point Anomaly` | `L08: Environmental Typhoon / Severe Weather Closure` | `4` | `2` | `-98.25%` | `-5.214` | `-0.652` |
| **`L09`** | `IO (Innovational Outlier)` | `Contextual Anomaly` | `L09: Short-Term Weather / Convoy Bunching Shock` | `385` | `27` | `+26.68%` | `-6.430` | `+17.200` |
| **`L09`** | `LS (Level Shift)` | `Contextual / Collective Anomaly` | `L09: Regional Trade Volume Shift / Seasonal Regime` | `410` | `15` | `+75.00%` | `-6.763` | `+32.376` |
| **`L10`** | `DATA_ANOMALY` | `Data-Level Reporting Anomaly` | `L10: Telemetry Glitch / AIS Missing DWT / Flatline` | `283` | `7` | `+32.13%` | `-2.800` | `+17.922` |

### 5.3. Kết quả Thống kê theo Top 15 Điểm nghẽn Hàng hải

| Điểm nghẽn (`portname`) | Vai trò (`chokepoint_role`) | Cú sốc $I(0)$ (`PP1 MAD`) | Cú sốc $I(0)$ (`PP2 IQR`) | **Đồng thuận Cú sốc $I(0)$** | Cấu trúc (`PP1 MAD`) | Cấu trúc (`PP2 IQR`) | **Đồng thuận Cấu trúc** | `Min Struct ModZ` | `Max Struct ModZ` |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `Cape of Good Hope` | `Rerouting Alternative` | `32` | `39` | **`31`** | `1,028` | `1,030` | **`1,028`** | `-1.79` | `+18.13` |
| `Bab el-Mandeb Strait` | `Global Transit Corridor` | `25` | `30` | **`25`** | `995` | `1,006` | **`995`** | `-6.08` | `+3.29` |
| `Strait of Hormuz` | `Origin Energy Export Hub` | `28` | `35` | **`26`** | `231` | `233` | **`231`** | `-7.59` | `+2.35` |
| `Panama Canal` | `Global Transit Corridor` | `10` | `9` | **`7`** | `233` | `264` | **`233`** | `-8.07` | `+2.91` |
| `Suez Canal` | `Global Transit Corridor` | `23` | `32` | **`23`** | `174` | `174` | **`174`** | `-6.28` | `+2.95` |
| `Yucatan Channel` | `Regional Maritime Passage` | `18` | `23` | **`17`** | `167` | `191` | **`167`** | `-4.24` | `+6.93` |
| `Sunda Strait` | `Rerouting Alternative` | `3` | `2` | **`2`** | `144` | `99` | **`99`** | `-2.52` | `+5.15` |
| `Bering Strait` | `Regional Maritime Passage` | `68` | `126` | **`57`** | `688` | `48` | **`48`** | `-0.67` | `+32.38` |
| `Makassar Strait` | `Regional Maritime Passage` | `14` | `19` | **`12`** | `92` | `109` | **`92`** | `-7.53` | `+4.14` |
| `Korea Strait` | `Global Transit Corridor` | `25` | `28` | **`24`** | `79` | `91` | **`79`** | `-5.36` | `+5.22` |
| `Kerch Strait` | `Origin Energy Export Hub` | `94` | `84` | **`75`** | `0` | `0` | **`0`** | `-1.48` | `+2.50` |
| `Bosporus Strait` | `Origin Energy Export Hub` | `18` | `20` | **`15`** | `57` | `63` | **`57`** | `-5.94` | `+2.31` |
| `Bohai Strait` | `Regional Maritime Passage` | `47` | `55` | **`41`** | `36` | `47` | **`36`** | `-5.96` | `+2.99` |
| `Taiwan Strait` | `Global Transit Corridor` | `52` | `61` | **`52`** | `10` | `14` | **`10`** | `-5.90` | `+3.32` |
| `Luzon Strait` | `Regional Maritime Passage` | `49` | `56` | **`46`** | `9` | `8` | **`8`** | `-4.22` | `+4.19` |

---

## 6. Cấu Trúc & Trạng Thái Bảng BI Mart `gold.mart_outlier_consensus_labeled_daily`

Bảng BI Mart kết quả đã được khởi tạo tại DuckDB local (`data/maritime_dwh.duckdb`), xuất file Parquet (`data/gold/mart_outlier_consensus_labeled_daily.parquet`) và đồng bộ lên **MotherDuck Cloud (`maritime_dwh.gold.mart_outlier_consensus_labeled_daily`)**:

- **Tên bảng trên MotherDuck Cloud:** `maritime_dwh.gold.mart_outlier_consensus_labeled_daily`
- **File Parquet local:** `data/gold/mart_outlier_consensus_labeled_daily.parquet`
- **Số dòng & Số cột:** `59,276 dòng` $\times$ `63 cột`
- **Dung lượng Parquet:** `2,486.5 KB` (`~2.43 MB`)
- **Nhóm trường chính trong bảng (`63 cột`):**
  1. **Định danh & Vai trò Điểm nghẽn (`8 cột`):** `observation_date`, `portid`, `portname`, `maritime_region`, `chokepoint_role`, `is_primary_oil_route`, `baseline_n_total`, `baseline_n_tanker`.
  2. **Chỉ số Lưu lượng & Trọng tải (`13 cột`):** `n_total`, `n_tanker`, `capacity`, `capacity_tanker`, `n_total_ma7`, `n_tanker_ma7`, `n_total_diff_1d`, `n_total_diff_7d`, `n_tanker_diff_7d`, `pct_vs_baseline_total`, `pct_vs_baseline_tanker`, `n_total_zscore_90d`, `n_tanker_zscore_90d`.
  3. **Chỉ số Kiểm định Đồng thuận Kép Điểm nghẽn (`14 cột`):** `shock_mod_z_90d`, `shock_iqr_exceed_90d`, `is_shock_mad_outlier`, `is_shock_iqr_outlier`, `is_shock_consensus_outlier`, `struct_mod_z_base`, `struct_iqr_exceed_base`, `is_struct_mad_outlier`, `is_struct_iqr_outlier`, `is_struct_consensus_outlier`, `is_chokepoint_consensus_outlier`, `consensus_run_days`, `is_ais_dwt_reporting_anomaly`, `is_flatline_telemetry_anomaly`.
  4. **Chỉ số Bối cảnh Mạng lưới & Giá Năng lượng (`22 cột`):** `n_corridors_depressed`, `cape_struct_mod_z`, `brent_usd_per_bbl`, `ulsd_usd_per_gal`, `ulsd_usd_per_bbl`, `diesel_brent_crack_bbl`, `brent_log_ret_1d`, `ulsd_log_ret_1d`, `crack_diff_1d`, `brent_change_30d_pct`, `brent_mod_z_63d`, `brent_iqr_exceed_63d`, `is_brent_consensus_outlier`, `ulsd_mod_z_63d`, `ulsd_iqr_exceed_63d`, `is_ulsd_consensus_outlier`, `crack_mod_z_63d`, `crack_iqr_exceed_63d`, `is_crack_consensus_outlier`, `is_any_energy_consensus_outlier`, `energy_ts_label`, `energy_domain_label`.
  5. **Bộ Nhãn Phân loại Outlier Đa chiều (`6 cột`):** `active_event_id`, `regime_type`, `chokepoint_label_code` (`L00`..`L10`), `chokepoint_ts_label` (`AO`, `IO`, `TC`, `LS`, `DATA_ANOMALY`), `chokepoint_acm_label` (`Point`, `Contextual`, `Collective`, `Data-Level`), `chokepoint_domain_label`.
