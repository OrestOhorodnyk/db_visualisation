select
    payments.payment_id,
    payments.order_id,
    orders.order_number,
    orders.user_id                                          as customer_id,
    payments.transaction_id,
    payments.payment_provider,
    payments.payment_method,
    payments.payment_status,
    payments.payment_status = 'completed'                   as is_successful,
    payments.amount,
    payments.currency,
    payments.initiated_at,
    payments.paid_at,
    date_diff('second', payments.initiated_at, payments.paid_at) as seconds_to_capture
from {{ ref('slv_eshop__payments') }} as payments
inner join {{ ref('slv_eshop__orders') }} as orders
    on payments.order_id = orders.order_id
