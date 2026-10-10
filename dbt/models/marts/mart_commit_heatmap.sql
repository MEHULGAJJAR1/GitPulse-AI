{{ config(materialized='table') }}
-- Developer contribution heatmap: commits by ISO weekday (1=Mon) and UTC hour.
select
    repo_full_name,
    extract(isodow from committed_at at time zone 'UTC')::int as weekday,
    extract(hour from committed_at at time zone 'UTC')::int   as hour_utc,
    count(*)                                                  as commits
from {{ ref('stg_commits') }}
where committed_at is not null
group by 1, 2, 3
