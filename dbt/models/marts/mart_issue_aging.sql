{{ config(materialized='table') }}
-- Backlog of open issues by age bucket (per repository).
select
    repo_full_name,
    case
        when open_age_days <= 7   then '0-7 days'
        when open_age_days <= 30  then '8-30 days'
        when open_age_days <= 90  then '31-90 days'
        else '90+ days'
    end                                  as age_bucket,
    case
        when open_age_days <= 7   then 1
        when open_age_days <= 30  then 2
        when open_age_days <= 90  then 3
        else 4
    end                                  as bucket_order,
    count(*)                             as open_issues
from {{ ref('int_issue_resolution') }}
where state = 'open'
group by 1, 2, 3
