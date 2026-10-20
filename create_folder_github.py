import os
from pathlib import Path

# 1. Định nghĩa danh sách toàn bộ các thư mục cần tạo
DIRECTORIES = [
    ".github/workflows",
    "config",
    "data/raw",
    "data/seeds",
    "src/utils",
    "src/ingest",
    "dbt_maritime/models/staging",
    "dbt_maritime/models/intermediate",
    "dbt_maritime/models/marts/core",
    "dbt_maritime/models/marts/bi_analytics",
    "dbt_maritime/seeds",
    "dbt_maritime/tests",
    "dbt_maritime/macros",
    "dashboard/pages",
    "dashboard/components",
    "docs",
]

# 2. Định nghĩa nội dung mặc định cho các file cốt lõi
FILES_CONTENT = {
    ".gitignore": """# Environment & Secrets
.venv/
venv/
.env
*.pyc
__pycache__/

# Raw Data & Local Database
data/raw/*.parquet
data/raw/*.csv
*.duckdb
*.duckdb.wal

# dbt Artifacts
dbt_maritime/target/
dbt_maritime/dbt_packages/
dbt_maritime/logs/
""",

    ".env.example": """# U.S. Energy Information Administration API Key (https://www.eia.gov/opendata/register.php)
EIA_API_KEY=your_eia_api_key_here

# MotherDuck Token (Optional - Để trống nếu chạy DuckDB local)
MOTHERDUCK_TOKEN=
""",

    "requirements.txt": """requests>=2.31.0
pandas>=2.2.0
pyarrow>=15.0.0
python-dotenv>=1.0.1
pyyaml>=6.0.1
duckdb>=1.0.0
dbt-core>=1.8.0
dbt-duckdb>=1.8.0
streamlit>=1.35.0
plotly>=5.22.0
""",

    "config/sources_config.yaml": """imf_portwatch:
  chokepoint_daily_url: "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Chokepoints_Data/FeatureServer/0/query"
  ports_daily_url: "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services/Daily_Ports_Data/FeatureServer/0/query"
  batch_size: 2000
  timeout_seconds: 30
  max_retries: 3

eia_energy:
  base_url: "https://api.eia.gov/v2/petroleum/pri/spt/data/"
  series:
    brent_crude: "RBRTE"
    ulsd_diesel: "EER_EPD2DXL0_PF4_RGC_DPG"
  start_date: "2019-01-01"
""",

    "data/seeds/geopolitical_events.csv": """event_id,event_name,start_date,end_date,primary_chokepoint,event_category,severity_level,description
EVT_01,Ever Given Suez Canal Blockage,2021-03-23,2021-03-29,Suez Canal,Operational Accident,High,Tau container Ever Given mac can lam tac nghen kenh dao Suez trong 6 ngay
EVT_02,Panama Canal Severe Drought Restrictions,2023-07-30,2024-05-15,Panama Canal,Climate & Weather,High,Han han El Nino khien muc nuoc ho Gatun giam ky luc buoc gioi han so luot tau qua kenh
EVT_03,Red Sea & Bab el-Mandeb Maritime Crisis,2023-11-19,2026-10-19,Bab el-Mandeb Strait,Geopolitical Conflict,Critical,Cac cuoc tan cong tau thuong mai tren Bien Do buoc cac hang tau doi tuyen vong qua Mui Hao Vong
EVT_04,Middle East Escalation & Hormuz Disruption,2026-02-28,2026-10-19,Strait of Hormuz,Geopolitical Conflict,Critical,Cang thang quan su tai Trung Dong tu cuoi thang 2/2026 gay gian doan luu thong tau Tanker va nhieu AIS tai Hormuz
""",

    "dbt_maritime/dbt_project.yml": """name: 'dbt_maritime'
version: '1.0.0'
config-version: 2

profile: 'dbt_maritime'

model-paths: ["models"]
seed-paths: ["seeds"]
test-paths: ["tests"]
macro-paths: ["macros"]

clean-targets:
  - "target"
  - "dbt_packages"

models:
  dbt_maritime:
    staging:
      +materialized: view
    intermediate:
      +materialized: view
    marts:
      +materialized: table
""",

    "dbt_maritime/profiles.yml": """dbt_maritime:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: '../data/maritime_dwh.duckdb'
      threads: 4
    prod_motherduck:
      type: duckdb
      path: 'md:maritime_dwh'
      threads: 4
""",

    "src/__init__.py": "",
    "src/utils/__init__.py": "",
    "src/ingest/__init__.py": "",
    "src/ingest/ingest_imf_portwatch.py": "# Paste code ingest_imf_portwatch.py tại đây\n",
    "src/ingest/ingest_eia_energy.py": "# Paste code ingest_eia_energy.py tại đây\n",
    "dashboard/app.py": "# Entry point cho Streamlit Dashboard\n",
}


def build_project_structure():
    base_dir = Path.cwd()
    print(f" Đang khởi tạo cấu trúc dự án tại: {base_dir}\n")

    # Tạo các thư mục
    for folder in DIRECTORIES:
        dir_path = base_dir / folder
        dir_path.mkdir(parents=True, exist_ok=True)
        # Tạo file .gitkeep để Git theo dõi cả các thư mục rỗng
        gitkeep = dir_path / ".gitkeep"
        if not any(dir_path.iterdir()):
            gitkeep.touch()
        print(f" Đã tạo thư mục: {folder}/")

    print("-" * 50)

    # Tạo các file và ghi nội dung
    for file_rel_path, content in FILES_CONTENT.items():
        file_path = base_dir / file_rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.write_text(content, encoding="utf-8")
            print(f" Đã tạo file:    {file_rel_path}")
        else:
            print(f"⏭ Bỏ qua (đã có): {file_rel_path}")

    # Copy luôn file seed sang thư mục dbt_maritime/seeds
    seed_src = base_dir / "data/seeds/geopolitical_events.csv"
    seed_dst = base_dir / "dbt_maritime/seeds/geopolitical_events.csv"
    if seed_src.exists() and not seed_dst.exists():
        seed_dst.write_text(seed_src.read_text(encoding="utf-8"), encoding="utf-8")
        print(" Đã đồng bộ:     dbt_maritime/seeds/geopolitical_events.csv")

    print("\n Hoàn tất 100%! Cấu trúc GitHub Repository đã sẵn sàng.")


if __name__ == "__main__":
    build_project_structure()