with locations as (

    select
        warehouse_id,
        count(distinct zone_id)                     as zones_count,
        count(*)                                    as locations_count,
        count(*) filter (where is_blocked)          as blocked_locations_count,
        count(*) filter (where is_sellable)         as sellable_locations_count,
        sum(max_volume_m3)                          as total_capacity_m3
    from {{ ref('slv_wh__storage_locations') }}
    group by warehouse_id

)

select
    warehouses.warehouse_id,
    warehouses.warehouse_code,
    warehouses.warehouse_name,
    warehouses.warehouse_address,
    warehouses.is_active,
    coalesce(locations.zones_count, 0)              as zones_count,
    coalesce(locations.locations_count, 0)          as locations_count,
    coalesce(locations.blocked_locations_count, 0)  as blocked_locations_count,
    coalesce(locations.sellable_locations_count, 0) as sellable_locations_count,
    locations.total_capacity_m3,
    warehouses.created_at
from {{ ref('slv_wh__warehouses') }} as warehouses
left join locations
    on warehouses.warehouse_id = locations.warehouse_id
