{{ config(materialized='table') }}
select
    language,
    count(distinct repo_full_name)                                         as repos,
    sum(bytes_of_code)                                                     as bytes_total,
    sum(bytes_of_code)::float / nullif(sum(sum(bytes_of_code)) over (), 0) as share
from {{ ref('stg_languages') }}
group by 1
