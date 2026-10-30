select
    id                                  as payment_id,
    order_id,
    nullif(trim(transaction_id), '')    as transaction_id,
    nullif(trim(provider), '')          as payment_provider,
    lower(trim(method))                 as payment_method,
    lower(trim(status))                 as payment_status,
    amount,
    upper(trim(currency))               as currency,
    paid_at,
    created_at                          as initiated_at
from {{ ref('brz_eshop__payments') }}
