select
    id,
    email,
    password_hash,
    first_name,
    last_name,
    phone,
    role,
    created_at,
    updated_at,
    current_timestamp as _loaded_at,
    'raw_eshop__users' as _source_table
from {{ ref('raw_eshop__users') }}
