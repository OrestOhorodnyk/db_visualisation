select
    id,
    order_id,
    transaction_id,
    provider,
    method,
    status,
    amount,
    currency,
    paid_at,
    created_at,
    current_timestamp as _loaded_at,
    'raw_eshop__payments' as _source_table
from {{ ref('raw_eshop__payments') }}
