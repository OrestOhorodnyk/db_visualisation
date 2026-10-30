select
    id                          as inbound_shipment_id,
    upper(trim(receipt_number)) as receipt_number,
    warehouse_id,
    supplier_id,
    lower(trim(status))         as shipment_status,
    expected_at,
    received_at,
    created_at
from {{ ref('brz_wh__inbound_shipments') }}
