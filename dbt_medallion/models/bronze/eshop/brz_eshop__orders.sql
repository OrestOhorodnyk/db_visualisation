select
    id,
    order_number,
    user_id,
    shipping_address_id,
    status,
    total_amount,
    shipping_cost,
    customer_notes,
    created_at,
    updated_at,
    current_timestamp as _loaded_at,
    'raw_eshop__orders' as _source_table
from {{ ref('raw_eshop__orders') }}
