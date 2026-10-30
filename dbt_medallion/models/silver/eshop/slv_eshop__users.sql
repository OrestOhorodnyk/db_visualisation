select
    id                                      as user_id,
    lower(trim(email))                      as email,
    trim(first_name)                        as first_name,
    trim(last_name)                         as last_name,
    trim(first_name) || ' ' || trim(last_name) as full_name,
    nullif(trim(phone), '')                 as phone,
    lower(trim(role))                       as user_role,
    created_at,
    updated_at
from {{ ref('brz_eshop__users') }}
