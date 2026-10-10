{{ config(materialized='table') }}
-- Long-form activity events pivoted to one row per repository and day.
with events as (
    select repo_full_name as repo, (committed_at at time zone 'UTC')::date as d, 'commits' as m
      from {{ ref('stg_commits') }} where committed_at is not null
    union all select repo_full_name, (created_at at time zone 'UTC')::date, 'issues_opened' from {{ ref('stg_issues') }}
    union all select repo_full_name, (closed_at at time zone 'UTC')::date, 'issues_closed' from {{ ref('stg_issues') }} where closed_at is not null
    union all select repo_full_name, (created_at at time zone 'UTC')::date, 'prs_opened' from {{ ref('stg_pull_requests') }}
    union all select repo_full_name, (merged_at at time zone 'UTC')::date, 'prs_merged' from {{ ref('stg_pull_requests') }} where merged_at is not null
    union all select repo_full_name, (published_at at time zone 'UTC')::date, 'releases' from {{ ref('stg_releases') }} where published_at is not null
    union all select repo_full_name, (starred_at at time zone 'UTC')::date, 'stars_gained' from {{ ref('stg_stargazers') }}
)
select
    repo                                                     as repo_full_name,
    d                                                        as activity_date,
    count(*) filter (where m = 'commits')                    as commits,
    count(*) filter (where m = 'issues_opened')              as issues_opened,
    count(*) filter (where m = 'issues_closed')              as issues_closed,
    count(*) filter (where m = 'prs_opened')                 as prs_opened,
    count(*) filter (where m = 'prs_merged')                 as prs_merged,
    count(*) filter (where m = 'releases')                   as releases,
    count(*) filter (where m = 'stars_gained')               as stars_gained
from events
where d is not null
group by 1, 2
