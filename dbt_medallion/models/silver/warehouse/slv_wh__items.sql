select
    id                              as item_id,
    upper(trim(sku))                as sku,
    nullif(trim(barcode), '')       as barcode,
    trim(name)                      as item_name,
    lower(trim(uom))                as uom,
    gross_weight_kg,
    volume_m3,
    min_stock_level,
    is_lot_tracked,
    created_at
from {{ ref('brz_wh__items') }}
