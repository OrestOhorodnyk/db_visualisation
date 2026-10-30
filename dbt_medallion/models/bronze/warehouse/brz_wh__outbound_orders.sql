select
    id,
    order_number,
    warehouse_id,
    external_order_ref,
    status,
    priority,
    shipped_at,
    created_at,
    current_timestamp as _loaded_at,
    'raw_wh__outbound_orders' as _source_table
from {{ ref('raw_wh__outbound_orders') }}
