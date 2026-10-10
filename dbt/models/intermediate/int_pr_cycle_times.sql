{{ config(materialized='table') }}
-- Pull-request cycle time: hours from creation to merge for merged PRs.
select
    repo_full_name,
    number,
    author_login,
    created_at,
    merged_at,
    extract(epoch from (merged_at - created_at)) / 3600.0   as merge_hours,
    date_trunc('week', merged_at)::date                     as merged_week
from {{ ref('stg_pull_requests') }}
where merged_at is not null
