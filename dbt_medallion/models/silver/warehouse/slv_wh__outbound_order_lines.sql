select
    id              as outbound_line_id,
    outbound_order_id,
    item_id,
    requested_qty,
    allocated_qty,
    picked_qty
from {{ ref('brz_wh__outbound_order_lines') }}
