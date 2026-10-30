select
    id,
    item_id,
    lot_id,
    from_location_id,
    to_location_id,
    type,
    quantity,
    reference_doc,
    performed_by,
    created_at,
    current_timestamp as _loaded_at,
    'raw_wh__stock_movements' as _source_table
from {{ ref('raw_wh__stock_movements') }}
