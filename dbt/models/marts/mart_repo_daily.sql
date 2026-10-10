{{ config(materialized='table') }}
-- Dense daily grain per repository (zero-filled) - the input for time-series analytics.
with bounds as (
    select repo_full_name, min(activity_date) as first_day, greatest(max(activity_date), current_date) as last_day
    from {{ ref('int_daily_activity') }}
    group by 1
),
grid as (
    select b.repo_full_name, gs::date as activity_date
    from bounds b
    cross join lateral generate_series(b.first_day, b.last_day, interval '1 day') gs
)
select
    g.repo_full_name,
    g.activity_date,
    coalesce(a.commits, 0)         as commits,
    coalesce(a.issues_opened, 0)   as issues_opened,
    coalesce(a.issues_closed, 0)   as issues_closed,
    coalesce(a.prs_opened, 0)      as prs_opened,
    coalesce(a.prs_merged, 0)      as prs_merged,
    coalesce(a.releases, 0)        as releases,
    coalesce(a.stars_gained, 0)    as stars_gained,
    sum(coalesce(a.stars_gained, 0)) over (partition by g.repo_full_name order by g.activity_date) as cumulative_stars_observed,
    r.data_source
from grid g
left join {{ ref('int_daily_activity') }} a on a.repo_full_name = g.repo_full_name and a.activity_date = g.activity_date
left join {{ ref('stg_repositories') }} r on r.full_name = g.repo_full_name
