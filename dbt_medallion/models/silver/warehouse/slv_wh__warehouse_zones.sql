select
    id                  as zone_id,
    warehouse_id,
    upper(trim(code))   as zone_code,
    trim(name)          as zone_name,
    lower(trim(type))   as zone_type
from {{ ref('brz_wh__warehouse_zones') }}
