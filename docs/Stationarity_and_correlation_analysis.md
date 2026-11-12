# TÀI LIỆU KỸ THUẬT & BÁO CÁO KẾT QUẢ: KIỂM ĐỊNH TÍNH DỪNG (STATIONARITY) & PHÂN TÍCH TƯƠNG QUAN (CORRELATION ANALYSIS)

## 1. Thông Tin Chung Về Script

* **Tên file vật lý:** `src/utils/stationarity_correlation_checker.py`
* **Dữ liệu đầu vào:**
  * `data/processed/maritime_energy_daily_joined.parquet` (`59,276 dòng` = `28 điểm nghẽn` $\times$ `2,117 ngày`, từ `2021-01-01` đến `2026-10-18`).
  * `data/seeds/geopolitical_events.csv` (4 sự kiện địa chính trị & khí hậu trọng điểm).
* **Cách chạy:**
  ```powershell
  venv\Scripts\python.exe -m src.utils.stationarity_correlation_checker
  ```
* **7 Hạng mục kiểm định tự động trong script:**
  1. `[1] KIEM DINH TINH DUNG - CHUOI GIA NANG LUONG`: Kiểm định ADF & KPSS trên chuỗi gốc $I(1)$, sai phân bậc 1 ($\Delta P_t$), Log-Return và biên lọc dầu Crack Spread ($\text{ULSD}\times 42 - \text{Brent}$).
  2. `[2] KIEM DINH TINH DUNG - 28 DIEM NGHEN HANG HAI`: Kiểm định ADF & KPSS trên chuỗi gốc và sai phân bậc 1 cho toàn bộ 28 điểm nghẽn.
  3. `[3] TUONG QUAN NOI TAI BRENT vs ULSD`: Hệ số tương quan Pearson $r$, Spearman $\rho$, thống kê $t$ và $p$-value ở 4 cấp độ biến đổi.
  4. `[4] TUONG QUAN GIA DAU vs 28 CHOKEPOINTS`: Đối chiếu tương quan trên chuỗi gốc (Level) với tương quan trên chuỗi dừng ($\Delta_7$ của trung bình trượt 7 ngày).
  5. `[5] PHAN TICH THEO CHE DO SU KIEN DIA CHINH TRI`: Định lượng mức độ sụt giảm lưu lượng tàu, mức tăng giá dầu và hệ số tương quan trong 4 cuộc khủng hoảng (`EVT_01` $\rightarrow$ `EVT_04`).
  6. `[6] MA TRAN TUONG QUAN DOI TUYEN HANG HAI`: Định lượng hiệu ứng thay thế tuyến giữa `Suez Canal / Bab el-Mandeb` và `Cape of Good Hope`.
  7. `[7] KIEM DINH NHAN QUA GRANGER TREN CHUOI DUNG`: Kiểm định Granger Causality F-test (độ trễ 7 ngày) theo cả hai chiều giữa Lưu lượng tàu và Giá năng lượng.

---

## 2. Cơ Sở Phương Pháp Luận Kinh Tế Lượng

### 2.1. Kiểm định Kép về Tính Dừng (Confirmatory Analysis: ADF + KPSS)
Theo **Kwiatkowski, Phillips, Schmidt, & Shin (1992)** (*Journal of Econometrics*), việc sử dụng kết hợp cả hai kiểm định có giả thuyết gốc đối lập nhau giúp loại bỏ sai lầm loại I và loại II khi chuỗi thời gian có đứt gãy cấu trúc (*Structural Breaks*):
* **Kiểm định ADF (Augmented Dickey-Fuller — chọn độ trễ tối ưu theo AIC):**
  $$\Delta y_t = \alpha + \beta y_{t-1} + \sum_{i=1}^{p} \gamma_i \Delta y_{t-i} + \varepsilon_t$$
  * $H_0: \beta = 0$ (Chuỗi có nghiệm đơn vị — **Không dừng** $I(1)$).
  * $H_1: \beta < 0$ (Chuỗi **Dừng** $I(0)$).
  * Giá trị tới hạn MacKinnon (2010): Mức $1\% = -3.434$; Mức $5\% = -2.863$; Mức $10\% = -2.568$.
* **Kiểm định KPSS (Kwiatkowski-Phillips-Schmidt-Shin — Newey-West Bartlett kernel):**
  $$\text{KPSS} = \frac{1}{T^2 \hat{\sigma}^2_{\infty}} \sum_{t=1}^{T} S_t^2, \quad S_t = \sum_{i=1}^{t} (y_i - \bar{y})$$
  * $H_0$: Chuỗi **Dừng** quanh mức trung binh (*Level Stationary* $I(0)$).
  * $H_1$: Chuỗi **Không dừng** (*Unit Root / Structural Drift*).
  * Giá trị tới hạn KPSS (1992): Mức $10\% = 0.347$; Mức $5\% = 0.463$; Mức $1\% = 0.739$.
* **Quy tắc xác nhận:** Một chuỗi chỉ được kết luận là **Dừng ($I(0)$)** ở mức ý nghĩa $5\%$ khi thỏa mãn đồng thời $\text{ADF Stat} < -2.863$ **VÀ** $\text{KPSS Stat} < 0.463$.

---

## 3. Kết Quả Kiểm Định Tính Dừng (Stationarity Results)

### 3.1. Nhóm Giá Năng lượng (U.S. EIA)

| Chuỗi dữ liệu | Mean | Std | Min | Max | ADF Stat | Lag | KPSS Stat | Kết luận (5%) |
| :--- | ---: | ---: | ---: | ---: | ---: | :---: | ---: | :--- |
| `Brent Crude ($/BBL) - Level` | 82.842 | 15.938 | 50.370 | 138.210 | `-2.7308` | 23 | `1.1426` | **KHÔNG DỪNG — $I(1)$** |
| `Brent Crude - Diff 1d` | 0.036 | 2.074 | -18.000 | 20.690 | `-8.4202` | 22 | `0.0921` | **DỪNG — $I(0)$** |
| `Brent Crude - Log-Return (%)` | 0.044 | 2.186 | -16.763 | 16.568 | `-8.7371` | 22 | `0.1055` | **DỪNG — $I(0)$** |
| `ULSD Diesel ($/GAL) - Level` | 2.720 | 0.765 | 1.397 | 5.296 | `-1.5250` | 12 | `1.8407` | **KHÔNG DỪNG — $I(1)$** |
| `ULSD Diesel - Diff 1d` | 0.002 | 0.080 | -0.915 | 0.546 | `-14.9919` | 11 | `0.1044` | **DỪNG — $I(0)$** |
| `ULSD Diesel - Log-Return (%)` | 0.059 | 2.385 | -22.829 | 12.539 | `-42.0653` | 0 | `0.1237` | **DỪNG — $I(0)$** |
| `Diesel-Brent Crack ($/BBL)` | 31.417 | 19.571 | 7.562 | 116.652 | `-2.4902` | 5 | `2.7654` | **KHÔNG DỪNG — $I(1)$** |
| `Diesel-Brent Crack - Diff 1d` | 0.032 | 2.735 | -37.982 | 19.312 | `-23.3235` | 4 | `0.0487` | **DỪNG — $I(0)$** |

### 3.2. Nhóm 28 Điểm Nghẽn Hàng Hải (IMF PortWatch)

| Port ID | Tên Điểm Nghẽn | `n_total` ADF | `n_total` KPSS | `n_tanker` ADF | `n_tanker` KPSS | `Diff1` ADF | `Diff1` KPSS | Kết luận Gốc $\rightarrow$ Diff1 |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| `chokepoint1` | Suez Canal | `-1.1493` | `11.7875` | `-1.9042` | `4.9263` | `-14.6420` | `0.0062` | **$I(1) \rightarrow I(0)$** |
| `chokepoint2` | Panama Canal | `-3.8087` | `2.9087` | `-4.0696` | `1.2703` | `-14.5758` | `0.0039` | **$I(1) \rightarrow I(0)$** |
| `chokepoint3` | Bosporus Strait | `-2.1528` | `4.1349` | `-3.2538` | `2.1829` | `-14.9983` | `0.0048` | **$I(1) \rightarrow I(0)$** |
| `chokepoint4` | Bab el-Mandeb Strait | `-0.7513` | `13.3565` | `-1.2027` | `10.1477` | `-15.9480` | `0.0078` | **$I(1) \rightarrow I(0)$** |
| `chokepoint5` | Malacca Strait | `-2.0516` | `13.2917` | `-2.3960` | `4.2323` | `-14.0042` | `0.0060` | **$I(1) \rightarrow I(0)$** |
| `chokepoint6` | Strait of Hormuz | `-1.0885` | `6.4853` | `-0.8319` | `8.1106` | `-14.1941` | `0.0249` | **$I(1) \rightarrow I(0)$** |
| `chokepoint7` | Cape of Good Hope | `-1.1794` | `17.6057` | `-1.9296` | `12.1113` | `-16.9289` | `0.0047` | **$I(1) \rightarrow I(0)$** |
| `chokepoint8` | Gibraltar Strait | `-3.7922` | `1.9575` | `-3.8204` | `4.1885` | `-15.2336` | `0.0075` | **$I(1) \rightarrow I(0)$** |
| `chokepoint9` | Dover Strait | `-6.1490` | `1.6307` | `-4.0879` | `3.9883` | `-16.0465` | `0.0037` | **$I(1) \rightarrow I(0)$** |
| `chokepoint10` | Oresund Strait | `-4.3830` | `6.7796` | `-5.0925` | `2.6009` | `-15.7966` | `0.0079` | **$I(1) \rightarrow I(0)$** |
| `chokepoint11` | Taiwan Strait | `-5.4402` | `1.5748` | `-4.6880` | `8.6342` | `-15.1170` | `0.0030` | **$I(1) \rightarrow I(0)$** |
| `chokepoint12` | Korea Strait | `-4.0756` | `5.0611` | `-3.8673` | `9.1169` | `-15.3427` | `0.0064` | **$I(1) \rightarrow I(0)$** |
| `chokepoint13` | Tsugaru Strait | `-4.2504` | `0.4342` | `-7.6820` | `1.6136` | `-14.9679` | `0.0033` | **$I(1) \rightarrow I(0)$** |
| `chokepoint14` | Luzon Strait | `-6.0360` | `0.6800` | `-5.6951` | `2.2523` | `-14.4968` | `0.0036` | **$I(1) \rightarrow I(0)$** |
| `chokepoint15` | Lombok Strait | `-12.6397` | `0.7923` | `-48.7480` | `4.2910` | `-16.2584` | `0.0054` | **$I(1) \rightarrow I(0)$** |
| `chokepoint16` | Ombai Strait | `-44.9468` | `2.0719` | `-35.3504` | `1.8438` | `-16.4659` | `0.0026` | **$I(1) \rightarrow I(0)$** |
| `chokepoint17` | Bohai Strait | `-4.7221` | `8.5141` | `-4.5261` | `3.6093` | `-16.4161` | `0.0030` | **$I(1) \rightarrow I(0)$** |
| `chokepoint18` | Torres Strait | `-22.2651` | `0.7065` | `-46.1905` | `0.3261` | `-17.3353` | `0.0028` | **$I(0) \rightarrow I(0)$** |
| `chokepoint19` | Sunda Strait | `-3.2068` | `12.5248` | `-4.9594` | `6.0511` | `-15.2406` | `0.0029` | **$I(1) \rightarrow I(0)$** |
| `chokepoint20` | Makassar Strait | `-4.4856` | `4.5627` | `-5.4900` | `2.1422` | `-15.3829` | `0.0063` | **$I(1) \rightarrow I(0)$** |
| `chokepoint21` | Magellan Strait | `-4.8854` | `1.1156` | `-20.5685` | `1.4036` | `-14.5675` | `0.0050` | **$I(1) \rightarrow I(0)$** |
| `chokepoint22` | Yucatan Channel | `-3.9111` | `9.6617` | `-3.1297` | `11.2738` | `-15.3492` | `0.0044` | **$I(1) \rightarrow I(0)$** |
| `chokepoint23` | Windward Passage | `-7.4177` | `0.4388` | `-30.8770` | `2.5408` | `-16.2082` | `0.0033` | **$I(1) \rightarrow I(0)$** |
| `chokepoint24` | Mona Passage | `-6.9342` | `1.9968` | `-9.3385` | `0.8999` | `-15.1748` | `0.0035` | **$I(1) \rightarrow I(0)$** |
| `chokepoint25` | Balabac Strait | `-7.1282` | `1.4381` | `-8.9567` | `1.8491` | `-15.5513` | `0.0029` | **$I(1) \rightarrow I(0)$** |
| `chokepoint26` | Bering Strait | `-2.0456` | `1.4133` | `-1.8865` | `1.3708` | `-12.5031` | `0.0049` | **$I(1) \rightarrow I(0)$** |
| `chokepoint27` | Mindoro Strait | `-3.0857` | `6.0462` | `-3.9269` | `3.0505` | `-16.1207` | `0.0028` | **$I(1) \rightarrow I(0)$** |
| `chokepoint28` | Kerch Strait | `-1.9996` | `10.2198` | `-2.0727` | `10.8032` | `-13.2063` | `0.0041` | **$I(1) \rightarrow I(0)$** |

* **Tổng kết `n_tanker`:** Trên chuỗi gốc chỉ có `1/28` điểm nghẽn dừng (`Torres Strait`); `27/28` điểm nghẽn không dừng do xu hướng và đứt gãy cấu trúc. Sau khi lấy **sai phân bậc 1 ($\Delta X_t$)**, **28/28 điểm nghẽn (100%) đạt tính dừng tuyệt đối**.

---

## 4. Kết Quả Phân Tích Tương Quan & Nhân Quả Granger

### 4.1. Tương quan nội tại giữa Brent Crude và ULSD Diesel

| Cấp độ biến đổi | Số quan sát ($N$) | Pearson $r$ | Spearman $\rho$ | $t$-stat | $p$-value |
| :--- | ---: | ---: | ---: | ---: | :---: |
| Chuỗi gốc (`Level - I(1)`) | 2,114 | `+0.8822` | `+0.8912` | `+86.11` | `< 0.0001` |
| Sai phân 1 ngày (`Diff 1d - I(0)`) | 2,113 | `+0.5778` | `+0.5359` | `+32.52` | `< 0.0001` |
| Log-Return 1 ngày (`I(0)`) | 2,113 | `+0.6117` | `+0.5556` | `+35.52` | `< 0.0001` |
| Biến động 7 ngày (`Diff 7d - I(0)`) | 2,107 | `+0.6455` | `+0.6679` | `+38.78` | `< 0.0001` |

---

### 4.2. Tương quan giữa Giá Dầu và Lưu lượng qua các Điểm Nghẽn Trọng Yếu

| Điểm nghẽn (Chokepoint) | TB Tàu/ngày (`Tot` / `Tkr`) | $r(\text{Brent}, \text{Tot})$ | $r(\text{Brent}, \text{Tkr})$ | $r(\text{ULSD}, \text{Tot})$ | $r(\text{ULSD}, \text{Tkr})$ | $r_{\Delta 7}(\text{Brent}, \text{Tkr})$ |
| :--- | :---: | ---: | ---: | ---: | ---: | ---: |
| **Strait of Hormuz** | 79.1 / 46.9 | **`-0.2321`** | **`-0.1869`** | **`-0.3972`** | **`-0.3598`** | `-0.0205` |
| **Bosporus Strait** | 92.7 / 23.0 | **`-0.2388`** | `-0.1274` | **`-0.3396`** | **`-0.1952`** | `-0.0571` |
| **Oresund Strait** | 46.6 / 11.5 | **`-0.2091`** | `-0.1336` | **`-0.2587`** | **`-0.1834`** | `+0.0098` |
| **Kerch Strait** | 17.1 / 4.4 | **`-0.1933`** | `-0.1426` | **`-0.2445`** | **`-0.1990`** | `-0.0139` |
| **Bohai Strait** | 177.5 / 36.7 | `-0.0935` | `-0.1133` | `-0.1375` | `-0.1084` | `+0.0103` |
| **Taiwan Strait** | 239.8 / 53.0 | `-0.0840` | `-0.0805` | `-0.1080` | `-0.1249` | `+0.0120` |
| **Cape of Good Hope** | 67.0 / 14.0 | `-0.1127` | `-0.0539` | `-0.0410` | `-0.0338` | `-0.0210` |
| **Panama Canal** | 30.8 / 12.6 | `+0.0538` | `+0.0919` | `+0.0811` | `+0.1265` | `-0.0480` |
| **Bab el-Mandeb Strait** | 50.4 / 17.1 | `+0.1485` | `+0.1507` | `+0.1035` | `+0.1254` | `-0.0466` |
| **Malacca Strait** | 211.4 / 78.6 | `+0.0461` | `+0.0305` | `+0.1360` | `+0.0483` | `-0.0337` |
| **Suez Canal** | 53.3 / 18.0 | `+0.2029` | `+0.1897` | `+0.1722` | `+0.2159` | `-0.0270` |

* **Nhận định:** Các điểm nghẽn xuất khẩu dầu mỏ trực tiếp (`Strait of Hormuz`, `Bosporus Strait`, `Oresund Strait`, `Kerch Strait`) có tương quan nghịch rõ rệt với giá dầu và đặc biệt mạnh với giá Diesel ULSD (`-0.3972` tại Hormuz). Khi chuyển sang biến động tuần đã dừng ($\Delta_7$), tương quan toàn mẫu tiến về $0$, khẳng định mối liên hệ giữa Chokepoint và Giá Dầu mang bản chất **Chuyển dịch Chế độ (*Regime-Switching*)** — chỉ kích hoạt khi xảy ra cú sốc đứt gãy nguồn cung.

---

### 4.3. Phân tích theo Chế độ Sự kiện Địa chính trị (`EVT_01` – `EVT_04`)

| ID | Sự kiện | Điểm nghẽn chính | Số ngày | $\Delta$ Tàu chở dầu | $\Delta$ Giá Brent | $r(\text{Tanker}, \text{Brent})$ trong sự kiện |
| :---: | :--- | :--- | ---: | ---: | ---: | ---: |
| `EVT_01` | Ever Given Suez Canal Blockage | Suez Canal | 7 | `-75.9%` | `+3.2%` | Ngắn hạn (7 ngày) |
| `EVT_02` | Panama Canal Severe Drought | Panama Canal | 291 | `-17.6%` | `+7.9%` | `+0.3823` |
| `EVT_03` | Red Sea & Bab el-Mandeb Crisis | Bab el-Mandeb Strait | 1,065 | `-53.0%` | `-4.6%` | `+0.0089` (Đổi tuyến qua châu Phi) |
| `EVT_04` | Middle East & Hormuz Disruption | Strait of Hormuz | 233 | **`-93.5%`** | **`+55.2%`** | **`-0.4398`** (`n_total`: **`-0.4500`**) |

---

### 4.4. Ma trận Tương quan Đổi tuyến Hàng hải (Rerouting Substitution Matrix)

| Cặp Điểm Nghẽn | Biến số | Pearson $r$ | Spearman $\rho$ | $t$-stat |
| :--- | :--- | ---: | ---: | ---: |
| `Suez Canal <-> Bab el-Mandeb Strait` | `n_total` | **`+0.8087`** | **`+0.7907`** | `+63.23` |
| `Bab el-Mandeb Strait <-> Cape of Good Hope` | `n_total` | **`-0.7265`** | **`-0.7088`** | `-48.62` |
| `Suez Canal <-> Cape of Good Hope` | `n_total` | **`-0.6526`** | **`-0.6728`** | `-39.61` |
| `Bab el-Mandeb Strait <-> Cape of Good Hope` | `n_tanker` | **`-0.5289`** | **`-0.5730`** | `-28.66` |
| `Suez Canal <-> Cape of Good Hope` | `n_tanker` | **`-0.3446`** | **`-0.3630`** | `-16.88` |

---

### 4.5. Kiểm định Nhân quả Granger trên Chuỗi Dừng ($\text{Lag} = 7\,\text{ngày}$, $F_{0.05} = 2.01, F_{0.10} = 1.72$)

| Điểm Nghẽn | $F(\text{Flow} \rightarrow \text{Brent})$ | $F(\text{Tanker} \rightarrow \text{Brent})$ | $F(\text{Tanker} \rightarrow \text{ULSD})$ | $F(\text{Brent} \rightarrow \text{Flow})$ | Kết luận |
| :--- | ---: | ---: | ---: | ---: | :--- |
| **Cape of Good Hope** | `0.399` | `1.580` | **`2.491`** | `0.551` | **`Tanker -> ULSD` (Có ý nghĩa ở mức 5%)** |
| **Bosporus Strait** | **`2.101`** | `1.562` | `0.954` | `0.359` | **`Flow -> Brent` (Có ý nghĩa ở mức 5%)** |
| **Strait of Hormuz** | **`1.920`** | **`1.749`** | `1.438` | `0.312` | **`Flow/Tanker -> Brent` (Có ý nghĩa ở mức 10%)** |
| **Gibraltar Strait** | `0.925` | **`1.774`** | `0.918` | `0.485` | **`Tanker -> Brent` (Có ý nghĩa ở mức 10%)** |
| **Suez / Bab el-Mandeb / Malacca / Panama** | `0.44 – 1.33` | `0.37 – 1.24` | `0.96 – 1.53` | `0.35 – 1.36` | Không có nhân quả tuyến tính ngắn hạn toàn mẫu |
