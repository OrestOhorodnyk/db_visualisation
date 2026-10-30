with orders as (

    select * from {{ ref('slv_eshop__orders') }}

),

item_totals as (

    select
        order_id,
        count(*)            as line_count,
        sum(quantity)       as units_count,
        sum(line_amount)    as items_amount
    from {{ ref('slv_eshop__order_items') }}
    group by order_id

),

payment_totals as (

    select
        order_id,
        count(*)                                                        as payment_attempts,
        coalesce(sum(amount) filter (where payment_status = 'completed'), 0) as paid_amount,
        coalesce(sum(amount) filter (where payment_status = 'refunded'), 0)  as refunded_amount,
        arg_max(payment_status, initiated_at)                           as latest_payment_status,
        arg_max(payment_method, initiated_at)                           as latest_payment_method,
        max(paid_at)                                                    as last_paid_at
    from {{ ref('slv_eshop__payments') }}
    group by order_id

),

addresses as (

    select * from {{ ref('slv_eshop__user_addresses') }}

)

select
    orders.order_id,
    orders.order_number,
    orders.user_id                                      as customer_id,
    orders.shipping_address_id,
    addresses.country                                   as ship_country,
    addresses.city                                      as ship_city,
    orders.order_status,
    orders.is_cancelled,
    orders.ordered_at,
    cast(orders.ordered_at as date)                     as order_date,
    coalesce(item_totals.line_count, 0)                 as line_count,
    coalesce(item_totals.units_count, 0)                as units_count,
    coalesce(item_totals.items_amount, 0)               as items_amount,
    orders.shipping_cost,
    orders.total_amount,
    coalesce(item_totals.items_amount, 0) + orders.shipping_cost = orders.total_amount
                                                        as is_total_consistent,
    coalesce(payment_totals.payment_attempts, 0)        as payment_attempts,
    coalesce(payment_totals.paid_amount, 0)             as paid_amount,
    coalesce(payment_totals.refunded_amount, 0)         as refunded_amount,
    orders.total_amount - coalesce(payment_totals.paid_amount, 0)
                                                        as outstanding_amount,
    coalesce(payment_totals.paid_amount, 0) >= orders.total_amount
                                                        as is_fully_paid,
    payment_totals.latest_payment_status,
    payment_totals.latest_payment_method,
    payment_totals.last_paid_at
from orders
left join item_totals
    on orders.order_id = item_totals.order_id
left join payment_totals
    on orders.order_id = payment_totals.order_id
left join addresses
    on orders.shipping_address_id = addresses.address_id
