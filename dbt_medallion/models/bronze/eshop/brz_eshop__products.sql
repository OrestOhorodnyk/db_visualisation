select
    id,
    category_id,
    sku,
    name,
    slug,
    description,
    price,
    stock_quantity,
    is_active,
    created_at,
    updated_at,
    current_timestamp as _loaded_at,
    'raw_eshop__products' as _source_table
from {{ ref('raw_eshop__products') }}
