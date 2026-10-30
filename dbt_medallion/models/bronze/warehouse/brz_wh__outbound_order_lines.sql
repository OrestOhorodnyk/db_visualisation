select
    id,
    outbound_order_id,
    item_id,
    requested_qty,
    allocated_qty,
    picked_qty,
    current_timestamp as _loaded_at,
    'raw_wh__outbound_order_lines' as _source_table
from {{ ref('raw_wh__outbound_order_lines') }}
