import pandas as pd

df = pd.read_parquet("data/raw/eia_energy_prices_daily_raw.parquet")

# In ra các khoảng thời gian nhỏ nhất và lớn nhất của từng series để kiểm tra
print(df.groupby("series")["period"].agg(["min", "max", "count"]))