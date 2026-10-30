select
    products.product_id,
    products.sku,
    products.product_name,
    products.product_slug,
    products.list_price,
    products.stock_quantity         as storefront_stock_qty,
    products.is_active,
    categories.category_id,
    categories.category_name,
    categories.root_category_name,
    categories.category_path,
    products.created_at,
    products.updated_at
from {{ ref('slv_eshop__products') }} as products
left join {{ ref('slv_eshop__categories') }} as categories
    on products.category_id = categories.category_id
