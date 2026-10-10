{{ config(materialized='table') }}
-- Weekly pull-request merge cycle time per repository.
select
    repo_full_name,
    merged_week                                                        as week_start,
    count(*)                                                           as merged_prs,
    percentile_cont(0.5) within group (order by merge_hours)           as median_merge_hours,
    percentile_cont(0.9) within group (order by merge_hours)           as p90_merge_hours
from {{ ref('int_pr_cycle_times') }}
where merged_week is not null
group by 1, 2
