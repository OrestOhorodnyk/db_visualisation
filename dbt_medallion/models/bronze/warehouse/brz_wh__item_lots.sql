select
    id,
    item_id,
    lot_number,
    manufactured_date,
    expiration_date,
    created_at,
    current_timestamp as _loaded_at,
    'raw_wh__item_lots' as _source_table
from {{ ref('raw_wh__item_lots') }}
