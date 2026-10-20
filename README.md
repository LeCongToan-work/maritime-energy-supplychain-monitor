<div align="center">

# MARITIME SUPPLY CHAIN & ENERGY PRICE MONITOR
### End-to-End Cloud-Native Lakehouse, Automated ELT Pipeline, Maritime Chokepoints & Fossil Fuel Analytics

**Dự án Portfolio Kỹ thuật Dữ liệu — Chuyên ngành Xử lý Dữ liệu**  
*Tác giả: **Lê Công Toàn***

<p align="center">
  <a href="https://www.python.org/" target="_blank">
    <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  </a>
  <a href="https://duckdb.org/" target="_blank">
    <img src="https://img.shields.io/badge/DuckDB-Embedded_DWH-FFD43F?style=for-the-badge&logo=duckdb&logoColor=black" alt="DuckDB">
  </a>
  <a href="https://motherduck.com/" target="_blank">
    <img src="https://img.shields.io/badge/MotherDuck-Cloud_Lakehouse-7B61FF?style=for-the-badge&logo=databricks&logoColor=white" alt="MotherDuck">
  </a>
  <a href="https://www.getdbt.com/" target="_blank">
    <img src="https://img.shields.io/badge/dbt_Core-Transformations-FF694B?style=for-the-badge&logo=dbt&logoColor=white" alt="dbt Core">
  </a>
  <a href="https://streamlit.io/" target="_blank">
    <img src="https://img.shields.io/badge/Streamlit-Interactive_BI-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit">
  </a>
  <a href="https://arrow.apache.org/" target="_blank">
    <img src="https://img.shields.io/badge/Apache_Parquet-Raw_Storage-006885?style=for-the-badge&logo=apache-parquet&logoColor=white" alt="Parquet">
  </a>
</p>

</div>

---

## MỤC LỤC TỔNG QUAN

1. [Bối Cảnh Dự Án & Bản Chất Miền Nghiệp Vụ (Maritime Supply Chain Domain)](#1-bối-cảnh-dự-án--bản-chất-miền-nghiệp-vụ-maritime-supply-chain-domain)
2. [Kiến Trúc Đường Ống Dữ Liệu ELT (Data Architecture)](#2-kiến-trúc-đường-ống-dữ-liệu-elt-data-architecture)
3. [Mô Hình Dữ Liệu Kho (Data Warehouse & dbt Modeling)](#3-mô-hình-dữ-liệu-kho-data-warehouse--dbt-modeling)
4. [Giải Pháp Kỹ Thuật Dữ Liệu & Tự Động Hóa (Data Engineering & Automation)](#4-giải-pháp-kỹ-thuật-dữ-liệu--tự-động-hóa-data-engineering--automation)
5. [Hệ Thống Trực Quan Hóa Quản Trị (Streamlit Dashboard)](#5-hệ-thống-trực-quan-hóa-quản-trị-streamlit-dashboard)
6. [Hướng Dẫn Cài Đặt & Vận Hành (Quickstart)](#6-hướng-dẫn-cài-đặt--vận-hành-quickstart)
7. [Danh Mục Tài Liệu & Tuân Thủ Bản Quyền (Attribution & Compliance)](#7-danh-mục-tài-liệu--tuân-thủ-bản-quyền-attribution--compliance)

---

## 1. Bối Cảnh Dự Án & Bản Chất Miền Nghiệp Vụ (Maritime Supply Chain Domain)

```mermaid
flowchart LR
    classDef chokeClass fill:#e3f2fd,stroke:#1976d2,stroke-width:1.5px,color:#0d47a1,rx:6px,ry:6px;
    classDef energyClass fill:#fff9c4,stroke:#fbc02d,stroke-width:1.5px,color:#f57f17,rx:6px,ry:6px;
    classDef modelClass fill:#ede7f6,stroke:#7e57c2,stroke-width:1.5px,color:#4a148c,rx:6px,ry:6px;

    Choke["<b>1. ĐIỂM NGHẼN HÀNG HẢI</b><br/>28 Chokepoints (IMF PortWatch)<br/>Container, Tanker & Cargo Transit"]:::chokeClass
    Energy["<b>2. THỊ TRƯỜNG NĂNG LƯỢNG</b><br/>U.S. EIA Spot Prices<br/>Brent Crude & ULSD Diesel"]:::energyClass
    Correlation["<b>3. PHÂN TÍCH TƯƠNG QUAN</b><br/>Đứt gãy cung ứng & Biến động giá<br/>Khoảng thời gian 5 năm (2021-2026)"]:::modelClass

    Choke -->|Ảnh hưởng lưu lượng| Correlation
    Energy -->|Biến động chi phí| Correlation
