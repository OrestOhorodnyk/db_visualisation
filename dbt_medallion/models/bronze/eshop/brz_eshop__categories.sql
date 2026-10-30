select
    id,
    parent_id,
    name,
    slug,
    description,
    current_timestamp as _loaded_at,
    'raw_eshop__categories' as _source_table
from {{ ref('raw_eshop__categories') }}
