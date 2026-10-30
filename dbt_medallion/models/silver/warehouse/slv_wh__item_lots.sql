select
    id                                                  as lot_id,
    item_id,
    upper(trim(lot_number))                             as lot_number,
    manufactured_date,
    expiration_date,
    date_diff('day', current_date, expiration_date)     as days_to_expiry,
    coalesce(expiration_date < current_date, false)     as is_expired,
    created_at
from {{ ref('brz_wh__item_lots') }}
