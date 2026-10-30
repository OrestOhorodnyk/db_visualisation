select
    id,
    name,
    tax_id,
    contact_email,
    phone,
    current_timestamp as _loaded_at,
    'raw_wh__suppliers' as _source_table
from {{ ref('raw_wh__suppliers') }}
