with joined as (

    select
        balances.balance_id,
        balances.location_id,
        locations.location_code,
        locations.zone_type,
        locations.warehouse_id,
        locations.warehouse_code,
        locations.is_sellable,
        balances.item_id,
        items.sku,
        items.item_name,
        items.min_stock_level,
        balances.lot_id,
        lots.lot_number,
        lots.expiration_date,
        lots.days_to_expiry,
        balances.quantity_on_hand,
        balances.quantity_allocated,
        balances.quantity_available,
        case when locations.is_sellable then balances.quantity_available else 0 end
                                        as quantity_sellable,
        balances.updated_at
    from {{ ref('slv_wh__inventory_balances') }} as balances
    inner join {{ ref('slv_wh__storage_locations') }} as locations
        on balances.location_id = locations.location_id
    inner join {{ ref('slv_wh__items') }} as items
        on balances.item_id = items.item_id
    left join {{ ref('slv_wh__item_lots') }} as lots
        on balances.lot_id = lots.lot_id

)

select
    *,
    sum(quantity_sellable) over (partition by item_id)  as item_total_sellable_qty,
    sum(quantity_sellable) over (partition by item_id) < min_stock_level
                                                        as is_item_below_min_stock,
    coalesce(days_to_expiry <= 60, false)               as is_expiring_soon
from joined
