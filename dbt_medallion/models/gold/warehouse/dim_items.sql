with lots as (

    select
        item_id,
        count(*)                                as lots_count,
        min(expiration_date) filter (where not is_expired) as next_expiration_date
    from {{ ref('slv_wh__item_lots') }}
    group by item_id

)

select
    items.item_id,
    items.sku,
    items.barcode,
    items.item_name,
    items.uom,
    items.gross_weight_kg,
    items.volume_m3,
    items.min_stock_level,
    items.is_lot_tracked,
    coalesce(lots.lots_count, 0)    as lots_count,
    lots.next_expiration_date,
    items.created_at
from {{ ref('slv_wh__items') }} as items
left join lots
    on items.item_id = lots.item_id
