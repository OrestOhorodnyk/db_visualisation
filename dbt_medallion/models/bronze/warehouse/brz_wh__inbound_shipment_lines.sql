select
    id,
    shipment_id,
    item_id,
    lot_id,
    expected_qty,
    received_qty,
    current_timestamp as _loaded_at,
    'raw_wh__inbound_shipment_lines' as _source_table
from {{ ref('raw_wh__inbound_shipment_lines') }}
