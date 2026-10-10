export type Role = "viewer" | "analyst" | "admin";
export type DataSource = "github" | "synthetic";

export interface DataMode {
  mode: "live" | "synthetic" | "mixed" | "empty";
  github_repos: number;
  synthetic_repos: number;
}

export interface Overview {
  data_mode: DataMode;
  generated_at: string;
  window: { days: number; end: string };
  kpis: {
    repositories: number;
    stars_total: number;
    stars_gained_window: number;
    commits_window: number;
    commits_previous_window: number;
    commit_change_pct: number | null;
    open_issues: number;
    open_prs: number;
    prs_merged_window: number;
    issues_closed_window: number;
    median_merge_hours: number | null;
    median_issue_close_hours: number | null;
    avg_health_score: number | null;
    contributors_total: number;
    anomalies_last_14_days: number;
  };
  timeline: TimelinePoint[];
  languages: LanguageRow[];
  leaderboard: LeaderRow[];
  health_distribution: Record<string, number>;
  recent_anomalies: Anomaly[];
}

export interface TimelinePoint {
  date: string;
  commits: number;
  issues_opened: number;
  issues_closed: number;
  prs_opened: number;
  prs_merged: number;
  stars_gained: number;
}

export interface LanguageRow {
  language: string;
  repos: number;
  bytes_total: number;
  share: number;
}

export interface LeaderRow {
  repo_full_name: string;
  language: string | null;
  stars: number;
  commits_window: number;
  prs_merged_window: number;
  issues_closed_window: number;
  health_score: number;
  grade: string;
  data_source: DataSource;
}

export interface Anomaly {
  repo_full_name?: string;
  date: string;
  value: number;
  expected: number | null;
  z_score: number;
  type: "spike" | "decline" | "sudden_decline";
  severity: "low" | "medium" | "high";
  corroborated_by_isolation_forest: boolean | null;
  explanation: string;
}

export interface RepoListItem {
  repo_full_name: string;
  owner: string;
  name: string;
  language: string | null;
  stars: number;
  forks: number;
  open_issues: number;
  prs_open: number;
  commits_window: number;
  commits_30d: number;
  contributors: number;
  median_merge_hours: number | null;
  days_since_push: number | null;
  health_score: number;
  grade: string;
  data_source: DataSource;
  is_private: boolean;
  pushed_at: string | null;
}

export interface Paged<T> {
  total: number;
  page: number;
  page_size: number;
  pages?: number;
  items: T[];
}

export interface HealthComponent {
  raw: number | null;
  score: number;
  weight: number;
  contribution: number;
  explanation: string;
}

export interface Health {
  repo_full_name: string;
  score: number;
  grade: string;
  confidence: "high" | "medium" | "low";
  components: Record<string, HealthComponent>;
  weakest_component: string;
  data_gaps: string[];
  method: string;
}

export interface RepoSummary {
  repo_full_name: string;
  owner: string;
  name: string;
  language: string | null;
  data_source: DataSource;
  is_private: boolean;
  stars: number;
  forks: number;
  open_issues_count: number;
  pushed_at: string | null;
  days_since_push: number | null;
  commits_total: number;
  commits_30d: number;
  commits_90d: number;
  commit_authors: number;
  last_commit_at: string | null;
  issues_open: number;
  issues_closed_30d: number;
  median_issue_close_hours: number | null;
  pct_issues_closed_7d: number | null;
  avg_open_issue_age_days: number | null;
  prs_total: number;
  prs_open: number;
  prs_merged_30d: number;
  median_merge_hours: number | null;
  p90_merge_hours: number | null;
  releases_count: number;
  last_release_at: string | null;
  contributors_count: number;
  stargazers_observed: number;
  branches_count: number;
  commits_window: number;
  stars_gained_window: number;
  prs_merged_window: number;
  issues_closed_window: number;
}

export interface Forecast {
  status: "ok" | "insufficient_data";
  reason?: string;
  model?: string;
  history_points: number;
  required_points?: number;
  horizon_days?: number;
  history?: { date: string; value: number; is_prediction: false }[];
  forecast?: {
    date: string;
    is_prediction: true;
    predicted: number;
    lower_80: number;
    upper_80: number;
    lower_95: number;
    upper_95: number;
    predicted_cumulative?: number;
  }[];
  evaluation?: {
    holdout_days: number;
    model_mae: number;
    model_rmse: number;
    model_mape_pct: number | null;
    interval_coverage_80: number | null;
    baseline: string;
    baseline_mae: number;
    improvement_over_baseline_pct: number | null;
  };
  reliability?: "good" | "moderate" | "low" | "very_low";
  disclaimer: string;
}

export interface Insight {
  id: string;
  category: "trend" | "anomaly" | "risk" | "opportunity" | "forecast";
  severity: "high" | "medium" | "info" | "low";
  title: string;
  evidence: string;
  recommendation: string;
  source: string[];
  repo_full_name?: string;
}

export interface RepoAnalysis {
  repo_full_name: string;
  window_days: number;
  metric: string;
  descriptive: Record<string, number>;
  moving_averages: { date: string; value: number; ma7: number | null; ma28: number | null }[];
  trend: { status: string; reason?: string; slope_per_week?: number; pct_change_over_window?: number; direction?: string; p_value?: number; r_squared?: number };
  seasonality: { status: string; strength?: number | null; peak_day?: string; lowest_day?: string; interpretation?: string;
    weekday_profile?: { day: string; mean: number; index: number }[]; reason?: string };
  forecast: Forecast;
  anomalies: { status: string; reason?: string; method?: string; count?: number; anomalies: Anomaly[] };
  changepoints: { status: string; reason?: string; changepoints: { date: string; mean_before: number; mean_after: number; relative_change_pct: number | null; direction: string; p_value: number }[] };
  correlation: { status: string; reason?: string; pairs: { metric_a: string; metric_b: string; pearson_r: number; spearman_rho: number; strength: string; significant: boolean; note: string }[] };
  contributor_patterns: { status: string; reason?: string; top_contributor?: string; top_share_pct?: number; gini?: number; bus_factor_50pct?: number; pattern?: string; interpretation?: string; contributors?: number };
  health: Health;
  insights: Insight[];
  data_source: DataSource;
  is_synthetic: boolean;
}

export interface Notification {
  id: string;
  type: "anomaly" | "pipeline";
  severity: "high" | "medium" | "low" | "info";
  title: string;
  message: string;
  created_at: string | null;
  link: string;
}

export interface Run {
  id: number;
  trigger: string;
  status: "queued" | "running" | "succeeded" | "partial" | "failed";
  stage: string | null;
  targets: { mode?: string; targets?: string[] } | null;
  stats: Record<string, any> | null;
  error: string | null;
  requested_by: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds?: number;
}

export interface LogLine {
  id: number;
  ts: string;
  level: "INFO" | "WARNING" | "ERROR";
  stage: string | null;
  message: string;
}

export interface QualityCheck {
  run_id: number;
  check_name: string;
  model: string;
  severity: string;
  status: "pass" | "fail" | "warn";
  failing_rows: number;
  detail: string | null;
  checked_at: string | null;
}

export interface Target {
  id: number;
  kind: "repo" | "user" | "org";
  name: string;
  enabled: boolean;
  created_at: string | null;
  last_synced_at: string | null;
}

export interface Page<T> {
  total: number;
  page: number;
  page_size: number;
  pages?: number;
  items: T[];
}

export interface CommitRow {
  sha: string;
  author_login: string | null;
  author_name: string | null;
  committed_at: string;
  message_headline: string;
  data_source: DataSource;
}

export interface IssueRow {
  number: number;
  title: string;
  state: string;
  author_login: string | null;
  created_at: string;
  closed_at: string | null;
  comments: number;
  labels: string[] | null;
  close_hours: number | null;
  open_age_days: number | null;
}

export interface PullRow {
  number: number;
  title: string;
  state: string;
  author_login: string | null;
  created_at: string;
  merged_at: string | null;
  closed_at: string | null;
  is_draft: boolean;
  base_ref: string | null;
  head_ref: string | null;
  merge_hours: number | null;
}

export interface TimeseriesRow {
  activity_date: string;
  commits: number;
  issues_opened: number;
  issues_closed: number;
  prs_opened: number;
  prs_merged: number;
  releases: number;
  stars_gained: number;
  cumulative_stars_observed: number;
}

export interface ContributorRow {
  rank?: number;
  login: string;
  commits_total: number;
  commits_30d: number;
  active_days: number;
  share_of_commits?: number;
  rank_in_repo?: number;
  repos?: number;
  /** commits_window = counted from commits in the sync window; contributions_all_time = GitHub's lifetime count; mixed = both. */
  basis?: "commits_window" | "contributions_all_time" | "mixed";
  first_commit_at?: string | null;
  last_commit_at: string | null;
}

export interface ContributorDetail {
  login: string;
  repos: { repo_full_name: string; commits_total: number; commits_30d: number; active_days: number; share_of_commits: number }[];
  daily: { date: string; commits: number }[];
}

export interface PrCycle {
  days: number;
  repo: string | null;
  distribution: {
    count: number; median_hours: number | null; p90_hours: number | null; mean_hours: number | null;
    within_24h_pct: number | null; over_7d_pct: number | null;
    histogram: { bucket: string; count: number }[];
  };
  weekly: { week: string; merged_prs: number; median_merge_hours: number | null; p90_merge_hours: number | null }[];
  status: string;
}

export interface IssueAging {
  repo: string | null;
  open_issues: number;
  buckets: { age_bucket: string; bucket_order: number; open_issues: number }[];
  resolution: { closed_count: number; median_close_days: number | null; p90_close_days: number | null; closed_within_7d_pct: number | null };
  status: string;
}

export interface PortfolioInsights {
  repos: number;
  low_health: string[];
  stale: string[];
  outliers: {
    status: string;
    outliers: { repo_full_name: string; metric: string; value: number; direction: string; fence: [number, number] }[];
    method: string;
  };
  clusters: {
    status: string;
    reason?: string;
    k?: number;
    features?: string[];
    clusters?: { cluster: number; repos: string[]; size: number }[];
    note?: string;
  };
}

export interface AnomalyResponse {
  status: string;
  window_days: number;
  repos_scanned: number;
  repos_skipped_insufficient_history: number;
  count: number;
  metric: string;
  anomalies: Anomaly[];
}

export interface HealthItem extends Health {
  stars: number;
  language: string | null;
  data_source: DataSource;
}

export interface AskResponse {
  question: string;
  answer: string;
  intent: string;
  mode: "rule_based" | "llm";
  llm_used: boolean;
  grounded_in: string[];
  repositories: string[];
  note: string;
}

export interface AiStatus {
  provider: string;
  model: string | null;
  enabled: boolean;
  base_url_host: string;
  fallback: string;
  note: string;
}

export interface PipelineStatus {
  running: { id: number; status: string; stage: string | null; created_at: string | null; started_at: string | null } | null;
  last_run: Run | null;
  targets: { enabled: number; total: number };
  scheduler_minutes: number;
  github_token_configured: boolean;
  data_mode: DataMode;
}

export interface MeResponse {
  role: Role;
  can_see_private_repos: boolean;
  private_repos_enabled: boolean;
  llm: { enabled: boolean; provider: string; model: string | null };
}

export interface ExportMeta {
  dataset: string;
  generated_at: string;
  row_count: number;
  truncated: boolean;
  data_mode: DataMode;
  columns: string[];
  window_days: number;
  source: string;
}
