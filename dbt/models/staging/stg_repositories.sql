{{ config(materialized='table') }}
-- Latest version of every repository payload (one row per repository).
with latest as (
    select distinct on (natural_key) natural_key, source_system, payload, fetched_at
    from {{ source('raw', 'github_payloads') }}
    where entity_type = 'repository'
    order by natural_key, fetched_at desc, id desc
)
select
    natural_key                                             as full_name,
    payload->'owner'->>'login'                              as owner,
    payload->>'name'                                        as name,
    payload->>'description'                                 as description,
    payload->>'language'                                    as language,
    (payload->>'stargazers_count')::int                     as stars,
    (payload->>'forks_count')::int                          as forks,
    (payload->>'open_issues_count')::int                    as open_issues_count,
    (payload->>'watchers_count')::int                       as watchers,
    coalesce((payload->>'private')::boolean, false)         as is_private,
    coalesce((payload->>'fork')::boolean, false)            as is_fork,
    coalesce((payload->>'archived')::boolean, false)        as is_archived,
    payload->>'default_branch'                              as default_branch,
    (payload->>'created_at')::timestamptz                   as created_at,
    (payload->>'pushed_at')::timestamptz                    as pushed_at,
    (payload->>'updated_at')::timestamptz                   as updated_at,
    payload->>'html_url'                                    as html_url,
    payload->'license'->>'spdx_id'                          as license,
    source_system                                           as data_source,
    fetched_at
from latest
