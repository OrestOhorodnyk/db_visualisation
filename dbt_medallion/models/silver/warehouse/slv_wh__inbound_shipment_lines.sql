select
    id                              as inbound_line_id,
    shipment_id                     as inbound_shipment_id,
    item_id,
    lot_id,
    expected_qty,
    received_qty,
    received_qty - expected_qty     as variance_qty
from {{ ref('brz_wh__inbound_shipment_lines') }}
