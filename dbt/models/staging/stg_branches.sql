{{ config(materialized='table') }}
select distinct on (natural_key)
    split_part(natural_key, '@', 1)                         as repo_full_name,
    payload->>'name'                                        as branch_name,
    coalesce((payload->>'protected')::boolean, false)       as is_protected
from {{ source('raw', 'github_payloads') }}
where entity_type = 'branch'
order by natural_key, fetched_at desc, id desc
