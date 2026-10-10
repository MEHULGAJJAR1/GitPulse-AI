{{ config(materialized='table') }}
-- One row per repository: the KPI inputs used by the health score (see ml_analytics/health.py).
with commits as (
    select repo_full_name,
           count(*)                                                       as commits_total,
           count(*) filter (where committed_at >= now() - interval '30 days') as commits_30d,
           count(*) filter (where committed_at >= now() - interval '90 days') as commits_90d,
           max(committed_at)                                              as last_commit_at,
           count(distinct author_login)                                   as commit_authors
    from {{ ref('stg_commits') }} group by 1
),
issues as (
    select repo_full_name,
           count(*) filter (where state = 'open')                         as issues_open,
           count(*) filter (where state = 'closed' and closed_at >= now() - interval '30 days') as issues_closed_30d,
           percentile_cont(0.5) within group (order by close_hours)       as median_issue_close_hours,
           avg(case when close_hours <= 168 then 1.0 else 0.0 end) filter (where close_hours is not null) as pct_issues_closed_7d,
           avg(open_age_days) filter (where state = 'open')               as avg_open_issue_age_days
    from {{ ref('int_issue_resolution') }} group by 1
),
prs as (
    select repo_full_name,
           count(*)                                                       as prs_total,
           count(*) filter (where state = 'open')                         as prs_open,
           count(*) filter (where merged_at >= now() - interval '30 days') as prs_merged_30d
    from {{ ref('stg_pull_requests') }} group by 1
),
merge_times as (
    select repo_full_name,
           percentile_cont(0.5) within group (order by merge_hours) as median_merge_hours,
           percentile_cont(0.9) within group (order by merge_hours) as p90_merge_hours
    from {{ ref('int_pr_cycle_times') }} group by 1
),
releases as (
    select repo_full_name, count(*) as releases_count, max(published_at) as last_release_at
    from {{ ref('stg_releases') }} group by 1
),
contributors as (
    select repo_full_name, count(*) as contributors_count from {{ ref('stg_contributors') }} group by 1
),
stars as (
    select repo_full_name, count(*) as stargazers_observed from {{ ref('stg_stargazers') }} group by 1
),
branches as (
    select repo_full_name, count(*) as branches_count from {{ ref('stg_branches') }} group by 1
),
langs as (
    select repo_full_name, max(language) filter (where bytes_of_code = mx) as primary_language
    from (select l.*, max(bytes_of_code) over (partition by repo_full_name) as mx from {{ ref('stg_languages') }} l) t
    group by 1
)
select
    r.full_name                                               as repo_full_name,
    r.owner,
    r.name,
    coalesce(lg.primary_language, r.language)                 as language,
    r.data_source,
    r.is_private,
    r.is_fork,
    r.is_archived,
    r.stars,
    r.forks,
    r.open_issues_count,
    r.pushed_at,
    extract(epoch from (now() - r.pushed_at)) / 86400.0       as days_since_push,
    coalesce(c.commits_total, 0)                              as commits_total,
    coalesce(c.commits_30d, 0)                                as commits_30d,
    coalesce(c.commits_90d, 0)                                as commits_90d,
    coalesce(c.commit_authors, 0)                             as commit_authors,
    c.last_commit_at,
    coalesce(i.issues_open, 0)                                as issues_open,
    coalesce(i.issues_closed_30d, 0)                          as issues_closed_30d,
    i.median_issue_close_hours,
    i.pct_issues_closed_7d,
    i.avg_open_issue_age_days,
    coalesce(p.prs_total, 0)                                  as prs_total,
    coalesce(p.prs_open, 0)                                   as prs_open,
    coalesce(p.prs_merged_30d, 0)                             as prs_merged_30d,
    m.median_merge_hours,
    m.p90_merge_hours,
    coalesce(rel.releases_count, 0)                           as releases_count,
    rel.last_release_at,
    coalesce(ct.contributors_count, 0)                        as contributors_count,
    coalesce(s.stargazers_observed, 0)                        as stargazers_observed,
    coalesce(b.branches_count, 0)                             as branches_count
from {{ ref('stg_repositories') }} r
left join commits c on c.repo_full_name = r.full_name
left join issues i on i.repo_full_name = r.full_name
left join prs p on p.repo_full_name = r.full_name
left join merge_times m on m.repo_full_name = r.full_name
left join releases rel on rel.repo_full_name = r.full_name
left join contributors ct on ct.repo_full_name = r.full_name
left join stars s on s.repo_full_name = r.full_name
left join branches b on b.repo_full_name = r.full_name
left join langs lg on lg.repo_full_name = r.full_name
