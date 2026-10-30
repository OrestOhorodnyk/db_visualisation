select
    movements.movement_id,
    movements.moved_at,
    cast(movements.moved_at as date)    as movement_date,
    movements.movement_type,
    movements.item_id,
    items.sku,
    movements.lot_id,
    lots.lot_number,
    movements.from_location_id,
    from_loc.location_code              as from_location_code,
    movements.to_location_id,
    to_loc.location_code                as to_location_code,
    coalesce(to_loc.warehouse_id, from_loc.warehouse_id)     as warehouse_id,
    coalesce(to_loc.warehouse_code, from_loc.warehouse_code) as warehouse_code,
    movements.quantity,
    case
        when movements.movement_type in ('inbound_receipt', 'adjustment_plus') then movements.quantity
        when movements.movement_type in ('outbound_pick', 'adjustment_minus') then -movements.quantity
        else 0
    end                                 as stock_impact_qty,
    movements.reference_doc,
    movements.performed_by
from {{ ref('slv_wh__stock_movements') }} as movements
inner join {{ ref('slv_wh__items') }} as items
    on movements.item_id = items.item_id
left join {{ ref('slv_wh__item_lots') }} as lots
    on movements.lot_id = lots.lot_id
left join {{ ref('slv_wh__storage_locations') }} as from_loc
    on movements.from_location_id = from_loc.location_id
left join {{ ref('slv_wh__storage_locations') }} as to_loc
    on movements.to_location_id = to_loc.location_id
