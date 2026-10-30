select
    id                                  as movement_id,
    item_id,
    lot_id,
    from_location_id,
    to_location_id,
    lower(trim(type))                   as movement_type,
    quantity,
    nullif(upper(trim(reference_doc)), '') as reference_doc,
    trim(performed_by)                  as performed_by,
    created_at                          as moved_at
from {{ ref('brz_wh__stock_movements') }}
