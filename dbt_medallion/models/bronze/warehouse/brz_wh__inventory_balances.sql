select
    id,
    location_id,
    item_id,
    lot_id,
    quantity_on_hand,
    quantity_allocated,
    updated_at,
    current_timestamp as _loaded_at,
    'raw_wh__inventory_balances' as _source_table
from {{ ref('raw_wh__inventory_balances') }}
