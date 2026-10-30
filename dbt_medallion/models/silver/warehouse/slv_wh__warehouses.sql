select
    id                  as warehouse_id,
    upper(trim(code))   as warehouse_code,
    trim(name)          as warehouse_name,
    trim(address)       as warehouse_address,
    is_active,
    created_at
from {{ ref('brz_wh__warehouses') }}
