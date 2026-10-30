select
    id,
    warehouse_id,
    code,
    name,
    type,
    current_timestamp as _loaded_at,
    'raw_wh__warehouse_zones' as _source_table
from {{ ref('raw_wh__warehouse_zones') }}
