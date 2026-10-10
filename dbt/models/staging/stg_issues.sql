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
    coalesce((payload->>'comments')::int, 0)                as comments,
    array(select l->>'name' from jsonb_array_elements(coalesce(payload->'labels', '[]'::jsonb)) l) as labels,
    source_system                                           as data_source
from {{ source('raw', 'github_payloads') }}
where entity_type = 'issue'
order by natural_key, fetched_at desc, id desc
