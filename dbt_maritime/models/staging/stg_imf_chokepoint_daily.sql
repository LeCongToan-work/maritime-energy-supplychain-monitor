-- Van de 3 - Phuong an 3A: IMF lam tron doc lap tung cot tong (floor/round) nen
-- capacity_cargo va capacity lech 1-3 tan DWT so voi tong thanh phan.
-- Tinh lai tu cac cot thanh phan de bieu do stacked cong khop tung don vi; giu cot goc de doi chieu.
with source as (

    select * from read_parquet('{{ var("raw_dir", "../data/raw") }}/imf_chokepoint_daily_raw.parquet')

),

typed as (

    select
        try_cast(date as date)              as observation_date,
        portid,
        portname,
        n_container,
        n_dry_bulk,
        n_general_cargo,
        n_roro,
        n_tanker,
        n_cargo,
        n_total,
        capacity_container,
        capacity_dry_bulk,
        capacity_general_cargo,
        capacity_roro,
        capacity_tanker,
        capacity_cargo                      as capacity_cargo_raw,
        capacity                            as capacity_raw,
        ObjectId                            as object_id,
        try_cast(_ingested_at_utc as timestamptz) as ingested_at_utc
    from source

),

final as (

    select
        *,
        capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro
            as capacity_cargo,
        capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro
            + capacity_tanker
            as capacity,
        abs(capacity_cargo_raw
            - (capacity_container + capacity_dry_bulk + capacity_general_cargo + capacity_roro))
            as capacity_cargo_rounding_diff,
        abs(capacity_raw
            - (capacity_cargo_raw + capacity_tanker))
            as capacity_rounding_diff
    from typed

)

select * from final
