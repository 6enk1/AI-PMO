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

export interface ImportAnalyze {
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
  created_tasks: number;
  created_people: number;
  created_issues: number;
  created_dependencies: number;
  created_milestones: number;
  skipped_rows: number;
  warnings: string[];
}
