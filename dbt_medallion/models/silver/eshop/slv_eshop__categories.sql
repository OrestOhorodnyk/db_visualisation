with recursive category_tree as (

    select
        id,
        parent_id,
        name,
        slug,
        description,
        0                       as depth,
        name                    as root_category_name,
        cast(name as varchar)   as category_path
    from {{ ref('brz_eshop__categories') }}
    where parent_id is null

    union all

    select
        child.id,
        child.parent_id,
        child.name,
        child.slug,
        child.description,
        parent.depth + 1,
        parent.root_category_name,
        parent.category_path || ' > ' || child.name
    from {{ ref('brz_eshop__categories') }} as child
    inner join category_tree as parent
        on child.parent_id = parent.id

)

select
    id                  as category_id,
    parent_id           as parent_category_id,
    name                as category_name,
    lower(trim(slug))   as category_slug,
    description         as category_description,
    depth               as category_depth,
    root_category_name,
    category_path,
    parent_id is null   as is_root
from category_tree
