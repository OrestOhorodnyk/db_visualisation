select
    lines.inbound_line_id,
    shipments.inbound_shipment_id,
    shipments.receipt_number,
    shipments.shipment_status,
    warehouses.warehouse_id,
    warehouses.warehouse_code,
    suppliers.supplier_id,
    suppliers.supplier_name,
    items.item_id,
    items.sku,
    lots.lot_number,
    shipments.expected_at,
    shipments.received_at,
    date_diff('minute', shipments.expected_at, shipments.received_at) as arrival_delay_minutes,
    lines.expected_qty,
    lines.received_qty,
    lines.variance_qty,
    round(lines.received_qty / nullif(lines.expected_qty, 0), 4)      as receipt_fill_rate,
    shipments.shipment_status = 'completed' and lines.variance_qty < 0 as is_short_delivery
from {{ ref('slv_wh__inbound_shipment_lines') }} as lines
inner join {{ ref('slv_wh__inbound_shipments') }} as shipments
    on lines.inbound_shipment_id = shipments.inbound_shipment_id
inner join {{ ref('slv_wh__warehouses') }} as warehouses
    on shipments.warehouse_id = warehouses.warehouse_id
inner join {{ ref('slv_wh__suppliers') }} as suppliers
    on shipments.supplier_id = suppliers.supplier_id
inner join {{ ref('slv_wh__items') }} as items
    on lines.item_id = items.item_id
left join {{ ref('slv_wh__item_lots') }} as lots
    on lines.lot_id = lots.lot_id
