{{ config(materialized='table') }}
select distinct on (natural_key)
    split_part(natural_key, '#', 1)                         as repo_full_name,
    (payload->>'number')::int                               as number,
    payload->>'title'                                       as title,
    payload->>'state'                                       as state,
    payload->'user'->>'login'                               as author_login,
    (payload->>'created_at')::timestamptz                   as created_at,
    (payload->>'updated_at')::timestamptz                   as updated_at,
    (payload->>'closed_at')::timestamptz                    as closed_at,
    (payload->>'merged_at')::timestamptz                    as merged_at,
    coalesce((payload->>'draft')::boolean, false)           as is_draft,
    payload->'base'->>'ref'                                 as base_ref,
    payload->'head'->>'ref'                                 as head_ref,
    (payload->>'additions')::int                            as additions,
    (payload->>'deletions')::int                            as deletions,
    source_system                                           as data_source
from {{ source('raw', 'github_payloads') }}
where entity_type = 'pull_request'
order by natural_key, fetched_at desc, id desc
