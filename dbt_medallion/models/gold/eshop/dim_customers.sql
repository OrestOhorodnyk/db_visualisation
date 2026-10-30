with users as (

    select * from {{ ref('slv_eshop__users') }}
    where user_role = 'customer'

),

default_addresses as (

    select *
    from {{ ref('slv_eshop__user_addresses') }}
    qualify row_number() over (
        partition by user_id
        order by is_default desc, address_id
    ) = 1

),

order_stats as (

    select
        user_id,
        count(*)                                                    as orders_count,
        count(*) filter (where not is_cancelled)                    as valid_orders_count,
        coalesce(sum(total_amount) filter (where not is_cancelled), 0) as lifetime_revenue,
        min(ordered_at)                                             as first_ordered_at,
        max(ordered_at)                                             as last_ordered_at
    from {{ ref('slv_eshop__orders') }}
    group by user_id

)

select
    users.user_id                               as customer_id,
    users.email,
    users.first_name,
    users.last_name,
    users.full_name,
    users.phone,
    default_addresses.country                   as default_country,
    default_addresses.city                      as default_city,
    default_addresses.postal_code               as default_postal_code,
    coalesce(order_stats.orders_count, 0)       as orders_count,
    coalesce(order_stats.valid_orders_count, 0) as valid_orders_count,
    coalesce(order_stats.lifetime_revenue, 0)   as lifetime_revenue,
    order_stats.first_ordered_at,
    order_stats.last_ordered_at,
    case
        when order_stats.valid_orders_count is null or order_stats.valid_orders_count = 0 then 'prospect'
        when order_stats.valid_orders_count = 1 then 'one_time'
        else 'repeat'
    end                                         as customer_segment,
    users.created_at                            as registered_at
from users
left join default_addresses
    on users.user_id = default_addresses.user_id
left join order_stats
    on users.user_id = order_stats.user_id
