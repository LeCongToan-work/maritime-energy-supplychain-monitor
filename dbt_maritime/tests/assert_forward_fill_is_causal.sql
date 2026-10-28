-- Causal check: gia forward-fill phai bang gia cua dung phien giao dich last_trading_date, khong duoc lay tu tuong lai.
select f.*
from {{ ref('int_energy_prices_daily_filled') }} f
left join {{ ref('stg_eia_energy_prices') }} p
    on p.series = f.series
    and p.period_date = f.last_trading_date
where f.is_forward_filled
  and (f.last_trading_date >= f.calendar_date
       or p.price_value is distinct from f.price_value)
