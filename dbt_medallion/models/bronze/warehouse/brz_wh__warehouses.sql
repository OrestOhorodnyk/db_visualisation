select
    id,
    code,
    name,
    address,
    is_active,
    created_at,
    current_timestamp as _loaded_at,
    'raw_wh__warehouses' as _source_table
from {{ ref('raw_wh__warehouses') }}
