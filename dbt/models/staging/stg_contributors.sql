{{ config(materialized='table') }}
select distinct on (natural_key)
    split_part(natural_key, '@', 1)                         as repo_full_name,
    payload->>'login'                                       as login,
    coalesce((payload->>'contributions')::int, 0)           as contributions
from {{ source('raw', 'github_payloads') }}
where entity_type = 'contributor'
order by natural_key, fetched_at desc, id desc
