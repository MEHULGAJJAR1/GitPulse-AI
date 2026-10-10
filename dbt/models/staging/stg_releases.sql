{{ config(materialized='table') }}
select distinct on (natural_key)
    split_part(natural_key, '@', 1)                         as repo_full_name,
    payload->>'tag_name'                                    as tag_name,
    payload->>'name'                                        as release_name,
    (payload->>'published_at')::timestamptz                 as published_at,
    coalesce((payload->>'prerelease')::boolean, false)      as is_prerelease,
    source_system                                           as data_source
from {{ source('raw', 'github_payloads') }}
where entity_type = 'release'
order by natural_key, fetched_at desc, id desc
