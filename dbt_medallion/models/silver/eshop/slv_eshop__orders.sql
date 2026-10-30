select
    id                              as order_id,
    upper(trim(order_number))       as order_number,
    user_id,
    shipping_address_id,
    lower(trim(status))             as order_status,
    total_amount,
    shipping_cost,
    total_amount - shipping_cost    as items_amount_declared,
    nullif(trim(customer_notes), '') as customer_notes,
    lower(trim(status)) = 'cancelled' as is_cancelled,
    created_at                      as ordered_at,
    updated_at
from {{ ref('brz_eshop__orders') }}
