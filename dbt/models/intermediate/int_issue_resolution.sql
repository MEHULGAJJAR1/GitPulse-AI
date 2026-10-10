{{ config(materialized='table') }}
-- Issue resolution and aging. Open issues carry an age in days relative to now().
select
    repo_full_name,
    number,
    state,
    created_at,
    closed_at,
    case when closed_at is not null then extract(epoch from (closed_at - created_at)) / 3600.0 end as close_hours,
    case when state = 'open' then extract(epoch from (now() - created_at)) / 86400.0 end            as open_age_days
from {{ ref('stg_issues') }}
