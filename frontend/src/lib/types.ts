export type TaskStatus = "not_started" | "in_progress" | "blocked" | "done" | "cancelled";
export type TaskPriority = "low" | "medium" | "high" | "critical";
export type IssueStatus = "open" | "in_progress" | "resolved" | "closed";
export type Severity = "low" | "medium" | "high" | "critical";

export interface Project {
  id: number;
  name: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
  updated_at: string;
  task_count?: number;
  open_task_count?: number;
  overdue_task_count?: number;
  open_issue_count?: number;
}

export interface Task {
  id: number;
  project_id: number;
  code: string | null;
  title: string;
  description: string | null;
  parent_task_id: number | null;
  owner_id: number | null;
  owner_name: string | null;
  parent_task_title: string | null;
  category: string | null;
  path_titles: string[];
  depth: number;
  child_count: number;
  is_summary: boolean;
  effective_progress: number;
  effective_start: string | null;
  effective_end: string | null;
  planned_start: string | null;
  planned_end: string | null;
  actual_start: string | null;
  actual_end: string | null;
  progress: number;
  status: TaskStatus;
  priority: TaskPriority;
  estimated_hours: number | null;
  notes: string | null;
  predecessor_task_ids: number[];
  successor_task_ids: number[];
  child_task_ids: number[];
  issue_ids: number[];
  open_issue_count: number;
  is_overdue: boolean;
  days_overdue: number;
  days_to_due: number | null;
  expected_progress: number;
  progress_gap: number;
  risk_score: number;
  risk_level: "low" | "medium" | "high" | "critical";
  total_float: number | null;
  is_critical_path: boolean;
}

export interface Person {
  id: number;
  project_id: number;
  name: string;
  role: string | null;
  email: string | null;
  capacity_tasks: number;
  assigned_task_count: number;
  open_task_count: number;
  overdue_task_count: number;
  high_risk_task_count: number;
  critical_task_count: number;
  due_this_week_count: number;
  open_issue_count: number;
  average_progress: number;
  load_ratio: number;
  load_level: "light" | "normal" | "high" | "overloaded";
  task_ids: number[];
}

export interface Issue {
  id: number;
  project_id: number;
  code: string | null;
  task_id: number | null;
  task_title: string | null;
  task_category: string | null;
  title: string;
  description: string | null;
  severity: Severity;
  owner_id: number | null;
  owner_name: string | null;
  raised_on: string | null;
  due_date: string | null;
  status: IssueStatus;
  action_plan: string | null;
  resolution: string | null;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
}

export interface Milestone {
  id: number;
  project_id: number;
  title: string;
  description: string | null;
  due_date: string | null;
  status: "pending" | "achieved" | "missed";
  days_remaining: number | null;
  at_risk: boolean;
}

export interface Evidence {
  label: string;
  detail: string;
}

export interface RecommendedAction {
  action: string;
  why: string;
  effort: string;
  owner_hint: string | null;
}

export interface Finding {
  id: string;
  category: "hidden_issue" | "delay_risk" | "delay_action";
  finding_type: string;
  title: string;
  severity: Severity;
  confidence: number;
  risk_score: number | null;
  task_id: number | null;
  task_title: string | null;
  task_category: string | null;
  person_id: number | null;
  person_name: string | null;
  explanation: string;
  reasoning_summary: string;
  evidence: Evidence[];
  impact: string;
  cause_hypothesis: string | null;
  cause_category: string | null;
  recommended_actions: RecommendedAction[];
  recommended_action: string | null;
  recommended_action_why: string | null;
  source: string;
}

export interface RiskFactor {
  key: string;
  label: string;
  points: number;
  detail: string;
}

export interface TaskRisk {
  task_id: number;
  task_code: string | null;
  task_title: string;
  task_category: string | null;
  owner_name: string | null;
  planned_end: string | null;
  progress: number;
  status: string;
  priority: string;
  risk_score: number;
  risk_level: string;
  days_overdue: number;
  days_to_due: number | null;
  factors: RiskFactor[];
  reasons: string[];
  impact: string;
  recommended_action: string | null;
}

export interface FocusItem {
  kind: string;
  ref_id: number | null;
  title: string;
  detail: string;
  severity: Severity;
  score: number;
  link: string | null;
}

export interface Dashboard {
  project: Project;
  as_of: string;
  health_score: number;
  health_label: string;
  health_breakdown: { key: string; label: string; penalty: number; detail: string }[];
  total_tasks: number;
  open_tasks: number;
  done_tasks: number;
  overdue_tasks: number;
  high_risk_tasks: number;
  hidden_issue_count: number;
  open_issue_count: number;
  critical_issue_count: number;
  unassigned_tasks: number;
  average_progress: number;
  schedule_variance_days: number;
  next_milestone: Milestone | null;
  milestones: Milestone[];
  focus_items: FocusItem[];
}

export interface AIPMOResponse {
  project_id: number;
  as_of: string;
  generated_at: string;
  llm_used: boolean;
  llm_note: string | null;
  hidden_issues: Finding[];
  delay_risks: TaskRisk[];
  delay_actions: Finding[];
  recommended_actions: Finding[];
}

export interface ImportSheetInfo {
  name: string;
  row_count: number;
  header_row: number;
  columns: string[];
}

export type ContentKind = "wbs" | "issues" | "mixed" | "unknown";

export interface ImportAnalyze {
  content_kind: ContentKind;
  content_confidence: number;
  content_evidence: string[];
  has_task_data: boolean;
  has_issue_text: boolean;
  token: string;
  filename: string;
  sheets: ImportSheetInfo[];
  selected_sheet: string;
  header_row: number;
  columns: string[];
  mapping: Record<string, string | null>;
  mapping_candidates: { field: string; column: string | null; confidence: number; reason: string | null }[];
  unmapped_columns: string[];
  preview: Record<string, unknown>[];
  raw_preview: Record<string, string>[];
  warnings: string[];
  known_fields: { field: string; label: string }[];
}

export interface ImportResult {
  project_id: number;
  project_name: string;
  match_by: string;
  created_tasks: number;
  updated_tasks: number;
  unchanged_tasks: number;
  created_people: number;
  created_issues: number;
  created_dependencies: number;
  created_milestones: number;
  skipped_rows: number;
  warnings: string[];
}

export interface CategorySuggestion {
  task_id: number;
  task_code: string | null;
  task_title: string;
  current_category: string | null;
  suggested_category: string;
  existing_category_id: number | null;
  confidence: number;
  reason: string;
  source: string;
}

export interface CategorySuggestResponse {
  project_id: number;
  llm_used: boolean;
  llm_note: string | null;
  existing_categories: { task_id: number; title: string }[];
  suggestions: CategorySuggestion[];
  unmatched_task_ids: number[];
}

export interface CategoryApplyResult {
  updated_tasks: number;
  created_categories: string[];
  skipped: string[];
}

export type MatchBy = "auto" | "code" | "title" | "none";

export interface ImportRowChange {
  field: string;
  label: string;
  before: string | null;
  after: string | null;
}

export interface ImportRowPlan {
  row_index: number;
  title: string;
  code: string | null;
  action: "create" | "update" | "unchanged" | "skip";
  matched_task_id: number | null;
  matched_task_title: string | null;
  matched_by: string | null;
  changes: ImportRowChange[];
}

export interface ImportPlan {
  match_by: string;
  create_count: number;
  update_count: number;
  unchanged_count: number;
  skipped_rows: number;
  rows: ImportRowPlan[];
  missing_in_file: { task_id: number; title: string }[];
}

// --- 課題インポートの自動判定 ------------------------------------------------
export type TriageLabel = "issue" | "uncertain" | "not_issue";
export type SeverityEstimate = "高" | "中" | "低" | "不明";

export interface TriageTaskCandidate {
  task_id: number | null;
  title: string;
  score: number;
}

export interface TriageItem {
  id: string;
  row_index: number | null;
  part_index: number;
  source_text: string;
  statement: string;
  label: TriageLabel;
  confidence: number;
  title: string;
  description: string;
  severity_estimate: SeverityEstimate;
  severity: Severity;
  reasons: string[];
  related_task_candidates: TriageTaskCandidate[];
  due_date: string | null;
  split: boolean;
  source: string;
}

export interface IssueAnalyzeResponse {
  llm_used: boolean;
  llm_note: string | null;
  counts: Record<string, number>;
  items: TriageItem[];
}

export interface IssueBulkCreateResult {
  created: number;
  issue_ids: number[];
  skipped: string[];
}

export interface ImportIssueRow {
  row_index: number | null;
  text: string;
  task_hint: string | null;
  severity_hint: string | null;
  due_date: string | null;
}

export interface ImportIssueRowsResponse {
  text_column: string | null;
  rows: ImportIssueRow[];
  available_columns: string[];
}
