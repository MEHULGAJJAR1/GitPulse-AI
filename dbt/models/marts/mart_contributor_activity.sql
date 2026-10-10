{{ config(materialized='table') }}
-- Per repository and contributor: commit volume, recency and share (for rankings and bus-factor).
with c as (
    select repo_full_name, coalesce(author_login, 'unknown') as login, committed_at
    from {{ ref('stg_commits') }}
),
per as (
    select repo_full_name, login,
           count(*)                                                          as commits_total,
           count(*) filter (where committed_at >= now() - interval '30 days') as commits_30d,
           count(distinct (committed_at at time zone 'UTC')::date)           as active_days,
           min(committed_at)                                                 as first_commit_at,
           max(committed_at)                                                 as last_commit_at
    from c group by 1, 2
)
select
    p.*,
    p.commits_total::float / nullif(sum(p.commits_total) over (partition by p.repo_full_name), 0) as share_of_commits,
    rank() over (partition by p.repo_full_name order by p.commits_total desc)                    as rank_in_repo
from per p
