select
    id,
    order_id,
    product_id,
    quantity,
    unit_price,
    current_timestamp as _loaded_at,
    'raw_eshop__order_items' as _source_table
from {{ ref('raw_eshop__order_items') }}
