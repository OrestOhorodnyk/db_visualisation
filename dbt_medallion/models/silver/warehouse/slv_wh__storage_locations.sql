with locations as (

    select * from {{ ref('brz_wh__storage_locations') }}

),

zones as (

    select * from {{ ref('slv_wh__warehouse_zones') }}

),

warehouses as (

    select * from {{ ref('slv_wh__warehouses') }}

)

select
    locations.id                        as location_id,
    upper(trim(locations.location_code)) as location_code,
    locations.aisle,
    locations.rack,
    locations.level,
    locations.bin,
    locations.max_weight_kg,
    locations.max_volume_m3,
    locations.is_blocked,
    zones.zone_id,
    zones.zone_code,
    zones.zone_name,
    zones.zone_type,
    warehouses.warehouse_id,
    warehouses.warehouse_code,
    warehouses.warehouse_name,
    warehouses.is_active                as is_warehouse_active,
    (
        not locations.is_blocked
        and warehouses.is_active
        and zones.zone_type in ('bulk_storage', 'picking', 'cold_storage')
    )                                   as is_sellable
from locations
inner join zones
    on locations.zone_id = zones.zone_id
inner join warehouses
    on zones.warehouse_id = warehouses.warehouse_id
