-- Sai so lam tron IMF chi duoc phep toi da k-1 don vi (k = so cot thanh phan): 3 tan voi 4 nhom tau hang, 1 tan voi cargo + tanker.
-- Vuot nguong nay la loi du lieu that, khong phai sai so lam tron.
select *
from {{ ref('stg_imf_chokepoint_daily') }}
where capacity_cargo_rounding_diff > 3
   or capacity_rounding_diff > 1
