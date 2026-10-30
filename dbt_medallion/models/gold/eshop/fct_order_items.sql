select
    items.order_item_id,
    items.order_id,
    orders.order_number,
    orders.user_id                              as customer_id,
    items.product_id,
    products.sku,
    orders.ordered_at,
    cast(orders.ordered_at as date)             as order_date,
    orders.order_status,
    orders.is_cancelled,
    items.quantity,
    items.unit_price,
    items.line_amount,
    products.list_price                         as current_list_price,
    products.list_price - items.unit_price      as price_change_since_order
from {{ ref('slv_eshop__order_items') }} as items
inner join {{ ref('slv_eshop__orders') }} as orders
    on items.order_id = orders.order_id
inner join {{ ref('slv_eshop__products') }} as products
    on items.product_id = products.product_id
