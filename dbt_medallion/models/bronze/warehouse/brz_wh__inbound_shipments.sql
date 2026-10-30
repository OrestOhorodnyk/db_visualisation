select
    id,
    receipt_number,
    warehouse_id,
    supplier_id,
    status,
    expected_at,
    received_at,
    created_at,
    current_timestamp as _loaded_at,
    'raw_wh__inbound_shipments' as _source_table
from {{ ref('raw_wh__inbound_shipments') }}
