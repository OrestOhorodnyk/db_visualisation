with eshop_orders as (

    select * from {{ ref('slv_eshop__orders') }}

),

outbound_orders as (

    select
        orders.*,
        warehouses.warehouse_code
    from {{ ref('slv_wh__outbound_orders') }} as orders
    inner join {{ ref('slv_wh__warehouses') }} as warehouses
        on orders.warehouse_id = warehouses.warehouse_id

),

joined as (

    select
        coalesce(eshop_orders.order_number, outbound_orders.outbound_order_number) as fulfillment_key,
        eshop_orders.order_id,
        eshop_orders.order_number,
        eshop_orders.user_id                    as customer_id,
        eshop_orders.order_status               as eshop_status,
        eshop_orders.ordered_at,
        eshop_orders.total_amount,
        outbound_orders.outbound_order_id,
        outbound_orders.outbound_order_number,
        outbound_orders.external_order_ref,
        outbound_orders.warehouse_id,
        outbound_orders.warehouse_code,
        outbound_orders.outbound_status         as warehouse_status,
        outbound_orders.priority,
        outbound_orders.created_at              as warehouse_received_at,
        outbound_orders.shipped_at
    from eshop_orders
    full outer join outbound_orders
        on eshop_orders.order_number = outbound_orders.external_order_ref

),

with_issues as (

    select
        *,
        case
            when order_id is not null and outbound_order_id is not null then 'matched'
            when order_id is not null then 'eshop_only'
            else 'warehouse_only'
        end                                                                 as match_status,
        round(date_diff('minute', ordered_at, warehouse_received_at) / 60.0, 2) as order_to_warehouse_hours,
        round(date_diff('minute', ordered_at, shipped_at) / 60.0, 2)        as order_to_ship_hours,
        case
            when eshop_status in ('paid', 'processing') and outbound_order_id is null
                then 'missing_outbound_order'
            when eshop_status in ('shipped', 'delivered') and warehouse_status is distinct from 'completed'
                then 'shipped_without_warehouse_completion'
            when eshop_status = 'cancelled' and warehouse_status <> 'cancelled'
                then 'cancelled_but_still_in_warehouse'
            when warehouse_status = 'completed' and eshop_status in ('pending', 'paid', 'processing')
                then 'warehouse_shipped_status_not_updated'
        end                                                                 as status_issue
    from joined

)

select
    *,
    status_issue is not null as needs_attention
from with_issues
