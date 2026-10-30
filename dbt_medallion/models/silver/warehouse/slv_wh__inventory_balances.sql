select
    id                                      as balance_id,
    location_id,
    item_id,
    lot_id,
    quantity_on_hand,
    quantity_allocated,
    quantity_on_hand - quantity_allocated   as quantity_available,
    updated_at
from {{ ref('brz_wh__inventory_balances') }}
