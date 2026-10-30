select
    lines.outbound_line_id,
    orders.outbound_order_id,
    orders.outbound_order_number,
    orders.external_order_ref,
    orders.outbound_status,
    orders.priority,
    warehouses.warehouse_id,
    warehouses.warehouse_code,
    items.item_id,
    items.sku,
    lines.requested_qty,
    lines.allocated_qty,
    lines.picked_qty,
    round(lines.allocated_qty / nullif(lines.requested_qty, 0), 4)   as allocation_rate,
    round(lines.picked_qty / nullif(lines.requested_qty, 0), 4)      as fill_rate,
    lines.picked_qty >= lines.requested_qty                          as is_fully_picked,
    orders.created_at,
    orders.shipped_at,
    round(date_diff('minute', orders.created_at, orders.shipped_at) / 60.0, 2) as hours_to_ship
from {{ ref('slv_wh__outbound_order_lines') }} as lines
inner join {{ ref('slv_wh__outbound_orders') }} as orders
    on lines.outbound_order_id = orders.outbound_order_id
inner join {{ ref('slv_wh__warehouses') }} as warehouses
    on orders.warehouse_id = warehouses.warehouse_id
inner join {{ ref('slv_wh__items') }} as items
    on lines.item_id = items.item_id
