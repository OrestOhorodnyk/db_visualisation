select
    id                      as order_item_id,
    order_id,
    product_id,
    quantity,
    unit_price,
    quantity * unit_price   as line_amount
from {{ ref('brz_eshop__order_items') }}
