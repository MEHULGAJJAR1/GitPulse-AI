{{ config(materialized='table') }}
with latest as (
    select distinct on (natural_key) natural_key, payload
    from {{ source('raw', 'github_payloads') }}
    where entity_type = 'language'
    order by natural_key, fetched_at desc, id desc
)
select
    natural_key                                             as repo_full_name,
    kv.key                                                  as language,
    kv.value::bigint                                        as bytes_of_code
from latest, jsonb_each_text(payload->'languages') as kv
