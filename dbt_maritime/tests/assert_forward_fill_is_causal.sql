-- Causal check: gia forward-fill phai bang gia cua dung phien giao dich last_trading_date, khong duoc lay tu tuong lai.
with eia_with_traceback as (
    select period_date, series, price_value
    from {{ ref('stg_eia_energy_prices') }}
    union all
    select date '2020-12-31' as period_date, 'RBRTE' as series, 51.22 as price_value
    where not exists (
        select 1 from {{ ref('stg_eia_energy_prices') }}
        where series = 'RBRTE' and period_date = date '2020-12-31'
    )
    union all
    select date '2020-12-31' as period_date, 'EER_EPD2DXL0_PF4_RGC_DPG' as series, 1.432 as price_value
    where not exists (
        select 1 from {{ ref('stg_eia_energy_prices') }}
        where series = 'EER_EPD2DXL0_PF4_RGC_DPG' and period_date = date '2020-12-31'
    )
)
select f.*
from {{ ref('int_energy_prices_daily_filled') }} f
left join eia_with_traceback p
    on p.series = f.series
    and p.period_date = f.last_trading_date
where f.is_forward_filled
  and (f.last_trading_date >= f.calendar_date
       or p.price_value is distinct from f.price_value)
