{{ config(materialized='table') }}
select distinct on (natural_key)
    split_part(natural_key, '@', 1)                         as repo_full_name,
    payload->'user'->>'login'                               as login,
    (payload->>'starred_at')::timestamptz                   as starred_at,
    source_system                                           as data_source
from {{ source('raw', 'github_payloads') }}
where entity_type = 'stargazer'
order by natural_key, fetched_at desc, id desc
