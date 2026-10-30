select
    id,
    user_id,
    country,
    city,
    street_address,
    postal_code,
    is_default,
    current_timestamp as _loaded_at,
    'raw_eshop__user_addresses' as _source_table
from {{ ref('raw_eshop__user_addresses') }}
