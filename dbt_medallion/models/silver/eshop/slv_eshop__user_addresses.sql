select
    id                              as address_id,
    user_id,
    trim(country)                   as country,
    trim(city)                      as city,
    trim(street_address)            as street_address,
    nullif(trim(postal_code), '')   as postal_code,
    coalesce(is_default, false)     as is_default
from {{ ref('brz_eshop__user_addresses') }}
