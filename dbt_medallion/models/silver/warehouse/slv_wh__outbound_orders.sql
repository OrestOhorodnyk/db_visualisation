select
    id                                          as outbound_order_id,
    upper(trim(order_number))                   as outbound_order_number,
    warehouse_id,
    nullif(upper(trim(external_order_ref)), '') as external_order_ref,
    lower(trim(status))                         as outbound_status,
    priority,
    shipped_at,
    created_at
from {{ ref('brz_wh__outbound_orders') }}
