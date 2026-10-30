select
    id                                      as supplier_id,
    trim(name)                              as supplier_name,
    nullif(upper(trim(tax_id)), '')         as tax_id,
    nullif(lower(trim(contact_email)), '')  as contact_email,
    nullif(trim(phone), '')                 as phone
from {{ ref('brz_wh__suppliers') }}
