select
    id,
    sku,
    barcode,
    name,
    uom,
    gross_weight_kg,
    volume_m3,
    min_stock_level,
    is_lot_tracked,
    created_at,
    current_timestamp as _loaded_at,
    'raw_wh__items' as _source_table
from {{ ref('raw_wh__items') }}
