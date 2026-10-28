-- Van de 1 - Phuong an 1A: giu nguyen Bronze, sua area-name o tang Staging.
-- EIA API v2 tra cung 'NA' cho area-name. duoarea -> area-name la phu thuoc ham 1-1
-- nen map tu duoarea cho ket qua chinh xac 100% (Fellegi & Holt, 1976; EIA API v2 duoarea codes).
with source as (

    select * from read_parquet('{{ var("raw_dir", "../data/raw") }}/eia_energy_prices_daily_raw.parquet')

),

typed as (

    select
        try_cast(period as date)                    as period_date,
        duoarea,
        "area-name"                                 as area_name_raw,
        product,
        "product-name"                              as product_name,
        process,
        "process-name"                              as process_name,
        series,
        "series-description"                        as series_description,
        try_cast(value as double)                   as price_value,
        units,
        try_cast(_ingested_at_utc as timestamptz)   as ingested_at_utc
    from source

),

final as (

    select
        *,
        case duoarea
            when 'ZEU' then 'Europe'
            when 'RGC' then 'U.S. Gulf Coast'
            else nullif(area_name_raw, 'NA')
        end as area_name
    from typed

)

select * from final
