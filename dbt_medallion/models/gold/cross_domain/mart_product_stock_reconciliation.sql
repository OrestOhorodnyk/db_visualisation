with products as (

    select * from {{ ref('dim_products') }}

),

warehouse_stock as (

    select
        items.item_id,
        items.sku,
        items.item_name,
        items.min_stock_level,
        coalesce(sum(inventory.quantity_on_hand), 0)    as warehouse_on_hand_qty,
        coalesce(sum(inventory.quantity_allocated), 0)  as warehouse_allocated_qty,
        coalesce(sum(inventory.quantity_sellable), 0)   as warehouse_sellable_qty
    from {{ ref('dim_items') }} as items
    left join {{ ref('fct_inventory_snapshot') }} as inventory
        on items.item_id = inventory.item_id
    group by all

)

select
    coalesce(products.sku, warehouse_stock.sku)             as sku,
    products.product_id,
    warehouse_stock.item_id,
    coalesce(products.product_name, warehouse_stock.item_name) as product_name,
    products.category_path,
    products.is_active,
    products.storefront_stock_qty,
    warehouse_stock.warehouse_on_hand_qty,
    warehouse_stock.warehouse_allocated_qty,
    warehouse_stock.warehouse_sellable_qty,
    warehouse_stock.min_stock_level,
    products.storefront_stock_qty - warehouse_stock.warehouse_sellable_qty as stock_diff_qty,
    case
        when warehouse_stock.item_id is null then 'missing_in_warehouse'
        when products.product_id is null then 'not_sold_online'
        when products.storefront_stock_qty = warehouse_stock.warehouse_sellable_qty then 'in_sync'
        when products.storefront_stock_qty > warehouse_stock.warehouse_sellable_qty then 'oversold_risk'
        else 'understated_online'
    end                                                     as reconciliation_status
from products
full outer join warehouse_stock
    on products.sku = warehouse_stock.sku
