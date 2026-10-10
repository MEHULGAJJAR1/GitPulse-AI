{{ config(materialized='table') }}
select distinct on (natural_key)
    split_part(natural_key, '@', 1)                         as repo_full_name,
    payload->>'sha'                                         as sha,
    payload->'author'->>'login'                             as author_login,
    payload->'commit'->'author'->>'name'                    as author_name,
    (payload->'commit'->'author'->>'date')::timestamptz     as committed_at,
    split_part(coalesce(payload->'commit'->>'message', ''), chr(10), 1) as message_headline,
    source_system                                           as data_source
from {{ source('raw', 'github_payloads') }}
where entity_type = 'commit'
order by natural_key, fetched_at desc, id desc
