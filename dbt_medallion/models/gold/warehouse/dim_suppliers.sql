with shipments as (

    select
        supplier_id,
        count(*)                                                as shipments_count,
        count(*) filter (where shipment_status = 'completed')   as completed_shipments_count,
        max(received_at)                                        as last_received_at
    from {{ ref('slv_wh__inbound_shipments') }}
    group by supplier_id

)

select
    suppliers.supplier_id,
    suppliers.supplier_name,
    suppliers.tax_id,
    suppliers.contact_email,
    suppliers.phone,
    coalesce(shipments.shipments_count, 0)              as shipments_count,
    coalesce(shipments.completed_shipments_count, 0)    as completed_shipments_count,
    shipments.last_received_at
from {{ ref('slv_wh__suppliers') }} as suppliers
left join shipments
    on suppliers.supplier_id = shipments.supplier_id
