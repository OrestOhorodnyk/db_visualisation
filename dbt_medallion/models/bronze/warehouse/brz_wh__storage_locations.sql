select
    id,
    zone_id,
    location_code,
    aisle,
    rack,
    level,
    bin,
    max_weight_kg,
    max_volume_m3,
    is_blocked,
    current_timestamp as _loaded_at,
    'raw_wh__storage_locations' as _source_table
from {{ ref('raw_wh__storage_locations') }}
