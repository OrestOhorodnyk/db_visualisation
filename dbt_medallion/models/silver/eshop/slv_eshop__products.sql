select
    id                  as product_id,
    category_id,
    upper(trim(sku))    as sku,
    trim(name)          as product_name,
    lower(trim(slug))   as product_slug,
    description         as product_description,
    price               as list_price,
    stock_quantity,
    is_active,
    created_at,
    updated_at
from {{ ref('brz_eshop__products') }}
