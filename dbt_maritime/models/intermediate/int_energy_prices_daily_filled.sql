-- Van de 2 - Phuong an 2A: Causal Forward-Fill (LOCF) tren calendar spine 365 ngay/nam.
-- Ngay nghi/cuoi tuan lay gia dong cua phien giao dich gan nhat TRUOC do (khong dung gia tuong lai
-- -> khong data leakage).
-- Rieng 3 ngay nghi Tet Duong lich & cuoi tuan dau nam 2021 (2021-01-01 .. 2021-01-03),
-- trace back phien giao dich cuoi cung cua nam 2020 (2020-12-31) tu EIA API v2:
--   RBRTE = 51.22 $/BBL, EER_EPD2DXL0_PF4_RGC_DPG = 1.432 $/GAL.
with min_max_dates as (

    select
        min(observation_date) as min_obs_date,
        max(observation_date) as max_obs_date
    from {{ ref('stg_imf_chokepoint_daily') }}

),

spine as (

    select cast(d as date) as calendar_date
    from generate_series(
        date '2020-12-31',
        (select max_obs_date from min_max_dates),
        interval 1 day
    ) as t(d)

),

series_dim as (

    select distinct series, duoarea, area_name, product, product_name, units
    from {{ ref('stg_eia_energy_prices') }}

),

eia_with_traceback as (

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

),

grid as (

    select s.calendar_date, d.*
    from spine s
    cross join series_dim d

),

joined as (

    select
        g.calendar_date,
        g.series,
        g.duoarea,
        g.area_name,
        g.product,
        g.product_name,
        g.units,
        p.price_value                                   as price_value_observed,
        case when p.price_value is not null then g.calendar_date end as trading_date
    from grid g
    left join eia_with_traceback p
        on p.series = g.series
        and p.period_date = g.calendar_date

),

filled as (

    select
        *,
        last_value(price_value_observed ignore nulls) over w as price_value,
        last_value(trading_date ignore nulls) over w         as last_trading_date
    from joined
    window w as (
        partition by series
        order by calendar_date
        rows between unbounded preceding and current row
    )

)

select
    calendar_date,
    series,
    duoarea,
    area_name,
    product,
    product_name,
    units,
    price_value,
    price_value_observed,
    last_trading_date,
    price_value_observed is null and price_value is not null as is_forward_filled,
    date_diff('day', last_trading_date, calendar_date)        as days_since_last_trade
from filled
where calendar_date >= (select min_obs_date from min_max_dates)
