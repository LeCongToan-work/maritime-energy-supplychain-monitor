-- Van de 2 - Phuong an 2A: Causal Forward-Fill (LOCF) tren calendar spine 365 ngay/nam.
-- Ngay nghi/cuoi tuan lay gia dong cua phien giao dich gan nhat TRUOC do (khong dung gia tuong lai
-- -> khong data leakage). Ngay truoc phien dau tien cua moi series de NULL, khong back-fill.
with spine as (

    select cast(d as date) as calendar_date
    from generate_series(
        (select min(observation_date) from {{ ref('stg_imf_chokepoint_daily') }}),
        (select max(observation_date) from {{ ref('stg_imf_chokepoint_daily') }}),
        interval 1 day
    ) as t(d)

),

series_dim as (

    select distinct series, duoarea, area_name, product, product_name, units
    from {{ ref('stg_eia_energy_prices') }}

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
    left join {{ ref('stg_eia_energy_prices') }} p
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
