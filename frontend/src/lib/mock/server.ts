/**
 * NEXT_PUBLIC_MOCK=1 のときに fetch を置き換える擬似APIサーバー。
 *
 * バックエンド（FastAPI）を起動せずに画面を触るためのもので、MSWのような
 * Service Worker は使わず、api.ts の request() の中で分岐している。
 * 状態はメモリ上にだけ持つので、リロードすると初期データに戻る。
 */
import type {
  AIPMOResponse,
  CategorySuggestResponse,
  Dashboard,
  Finding,
  ImportAnalyze,
  Issue,
  Milestone,
  Person,
  Task,
  TaskRisk,
} from "../types";
import { buildStore, decorate, isoDate, readMockConfig, type MockStore } from "./dataset";

export const MOCK_ENABLED = process.env.NEXT_PUBLIC_MOCK === "1";

let store: MockStore | null = null;
function db(): MockStore {
  if (!store) store = buildStore(readMockConfig());
  return store;
}

const ACTIVE: Task["status"][] = ["not_started", "in_progress", "blocked"];
const SEVERITY_RANK: Record<string, number> = { critical: 3, high: 2, medium: 1, low: 0 };

function projectTasks(projectId: number): Task[] {
  return db().tasks.filter((task) => task.project_id === projectId);
}

function isActive(task: Task): boolean {
  return ACTIVE.includes(task.status);
}

function refresh(projectId: number): void {
  decorate(projectTasks(projectId));
  db().people
    .filter((person) => person.project_id === projectId)
    .forEach((person) => {
      const owned = projectTasks(projectId).filter((task) => task.owner_id === person.id);
      const open = owned.filter(isActive);
      person.assigned_task_count = owned.length;
      person.open_task_count = open.length;
      person.overdue_task_count = open.filter((task) => task.is_overdue).length;
      person.high_risk_task_count = open.filter((task) => task.risk_score >= 70).length;
      person.critical_task_count = open.filter((t) => t.priority === "high" || t.priority === "critical").length;
      person.due_this_week_count = open.filter((t) => (t.days_to_due ?? 99) >= 0 && (t.days_to_due ?? 99) <= 7).length;
      person.open_issue_count = db().issues.filter(
        (issue) => issue.owner_id === person.id && issue.status !== "resolved" && issue.status !== "closed",
      ).length;
      person.average_progress = open.length
        ? Math.round(open.reduce((sum, task) => sum + task.progress, 0) / open.length)
        : 0;
      person.load_ratio = Math.round((open.length / Math.max(1, person.capacity_tasks)) * 100) / 100;
      person.load_level =
        person.load_ratio >= 1 ? "overloaded" : person.load_ratio >= 0.75 ? "high" : person.load_ratio >= 0.4 ? "normal" : "light";
    });
}

function finding(index: number, task: Task, type: string, title: string, severity: Finding["severity"]): Finding {
  return {
    id: `hidden_issue-${index}`,
    category: "hidden_issue",
    finding_type: type,
    title,
    severity,
    confidence: 0.8,
    risk_score: task.risk_score,
    task_id: task.id,
    task_title: task.title,
    task_category: task.category,
    person_id: task.owner_id,
    person_name: task.owner_name,
    explanation: `${title}。モックデータのため、根拠は簡略化した計算で生成しています。`,
    reasoning_summary: `検出ルール「${type}」が条件を満たしたため ${severity} と判定した（モック）。`,
    evidence: [
      { label: "予定終了日", detail: `${task.planned_end ?? "未設定"}（本日 ${isoDate(0)}）` },
      { label: "進捗", detail: `${task.progress}%（想定 ${task.expected_progress}%）` },
      { label: "担当", detail: task.owner_name ?? "未設定" },
    ],
    impact: "後続タスクの着手判断ができず、遅延が下流へ連鎖する。",
    cause_hypothesis: null,
    cause_category: null,
    recommended_actions: [
      { action: "残作業を洗い出し、完了予定日を確定する", why: "現在の期日が実態と乖離しているため", effort: "low", owner_hint: null },
      { action: "担当者を追加投入する", why: "残日数では単独消化が難しいため", effort: "high", owner_hint: null },
    ],
    recommended_action: "残作業を洗い出し、完了予定日を確定する",
    recommended_action_why: "現在の期日が実態と乖離しているため",
    source: "rules",
  };
}

function buildDashboard(projectId: number): Dashboard {
  refresh(projectId);
  const tasks = projectTasks(projectId);
  const active = tasks.filter(isActive);
  const overdue = active.filter((task) => task.is_overdue);
  const highRisk = active.filter((task) => task.risk_score >= 60);
  const issues = db().issues.filter((issue) => issue.project_id === projectId);
  const open = issues.filter((issue) => issue.status !== "resolved" && issue.status !== "closed");
  const milestones = db().milestones.filter((milestone) => milestone.project_id === projectId);
  const project = db().projects.find((p) => p.id === projectId)!;
  const score = Math.max(0, 100 - overdue.length * 4 - highRisk.length * 2 - open.length);

  return {
    project,
    as_of: isoDate(0),
    health_score: score,
    health_label: score >= 80 ? "良好" : score >= 60 ? "注意" : score >= 40 ? "要対応" : "危険",
    health_breakdown: [
      { key: "overdue", label: "期限超過Task", penalty: overdue.length * 4, detail: `未完了 ${active.length} 件中 ${overdue.length} 件が期限超過` },
      { key: "high_risk", label: "高リスクTask", penalty: highRisk.length * 2, detail: `Risk Score 60以上が ${highRisk.length} 件` },
      { key: "issues", label: "未解決Issue", penalty: open.length, detail: `未解決 ${open.length} 件` },
    ],
    total_tasks: tasks.length,
    open_tasks: active.length,
    done_tasks: tasks.filter((task) => task.status === "done").length,
    overdue_tasks: overdue.length,
    high_risk_tasks: highRisk.length,
    hidden_issue_count: Math.min(20, overdue.length + highRisk.length),
    open_issue_count: open.length,
    critical_issue_count: open.filter((issue) => issue.severity === "high" || issue.severity === "critical").length,
    unassigned_tasks: active.filter((task) => !task.owner_id && !task.is_summary).length,
    average_progress: tasks.length
      ? Math.round(tasks.reduce((sum, task) => sum + task.progress, 0) / tasks.length)
      : 0,
    schedule_variance_days: 1.8,
    next_milestone: milestones[0] ?? null,
    milestones,
    focus_items: [
      ...overdue.slice(0, 5).map((task) => ({
        kind: "overdue_task",
        ref_id: task.id,
        title: `期限超過 ${task.days_overdue} 日: ${task.title}`,
        detail: `担当 ${task.owner_name ?? "未設定"} / 進捗 ${task.progress}% / Risk ${task.risk_score}`,
        severity: (task.days_overdue >= 7 ? "critical" : "high") as Finding["severity"],
        score: 90 + task.days_overdue,
        link: "/tasks",
      })),
      ...open
        .filter((issue) => issue.severity === "high" || issue.severity === "critical")
        .slice(0, 4)
        .map((issue) => ({
          kind: "issue",
          ref_id: issue.id,
          title: `重要Issue: ${issue.title}`,
          detail: `Severity ${issue.severity} / 担当 ${issue.owner_name ?? "未設定"}`,
          severity: issue.severity,
          score: 70,
          link: "/issues",
        })),
    ].slice(0, 10),
  };
}

function buildAiPmo(projectId: number): AIPMOResponse {
  refresh(projectId);
  const active = projectTasks(projectId).filter(isActive);
  const hidden = active
    .filter((task) => task.is_overdue || task.risk_score >= 60)
    .slice(0, 12)
    .map((task, index) =>
      finding(
        index,
        task,
        task.is_overdue ? "overdue_status_unchanged" : "due_soon_low_progress",
        task.is_overdue
          ? `期限超過 ${task.days_overdue} 日でStatus未更新: ${task.title}`
          : `期限まで${task.days_to_due}日で進捗${task.progress}%: ${task.title}`,
        task.days_overdue >= 7 ? "critical" : "high",
      ),
    );
  const risks: TaskRisk[] = active
    .filter((task) => task.risk_score >= 40)
    .sort((a, b) => b.risk_score - a.risk_score)
    .slice(0, 30)
    .map((task) => ({
      task_id: task.id,
      task_code: task.code,
      task_title: task.title,
      task_category: task.category,
      owner_name: task.owner_name,
      planned_end: task.planned_end,
      progress: task.progress,
      status: task.status,
      priority: task.priority,
      risk_score: task.risk_score,
      risk_level: task.risk_level,
      days_overdue: task.days_overdue,
      days_to_due: task.days_to_due,
      factors: [
        { key: "overdue", label: "期限超過", points: Math.min(40, task.days_overdue * 3.5), detail: `予定終了日 ${task.planned_end} を ${task.days_overdue} 日超過` },
        { key: "progress_gap", label: "進捗遅れ", points: Math.max(0, task.progress_gap * 0.35), detail: `想定 ${task.expected_progress}% に対し実績 ${task.progress}%` },
      ].filter((factor) => factor.points > 0),
      reasons: [`期限超過: ${task.days_overdue} 日`, `進捗差: ${task.progress_gap}pt`],
      impact: "後続タスクの着手が遅れ、マイルストーン達成が危うくなる。",
      recommended_action: "残作業を洗い出し、完了予定日を確定する",
    }));
  const actions = hidden.slice(0, 8).map((item, index) => ({
    ...item,
    id: `delay_action-${index}`,
    category: "delay_action" as const,
    finding_type: "delay_diagnosis",
    cause_category: "依存Task遅延",
    cause_hypothesis: "前工程が完了していないため着手・完了できていない",
  }));

  return {
    project_id: projectId,
    as_of: isoDate(0),
    generated_at: new Date().toISOString(),
    llm_used: false,
    llm_note: "モックモードで動作しています（NEXT_PUBLIC_MOCK=1）。実際の分析はPythonバックエンドが行います。",
    hidden_issues: hidden,
    delay_risks: risks,
    delay_actions: actions,
    recommended_actions: [...hidden, ...actions].slice(0, 10),
  };
}

const IMPORT_SAMPLE: ImportAnalyze = {
  content_kind: "mixed",
  content_confidence: 0.8,
  content_evidence: [
    "タスク用の列に値がある: 開始予定日、終了予定日、進捗率、Status",
    "課題列「課題」に 3 行の記述（うち 3 行は自由記述）",
  ],
  has_task_data: true,
  has_issue_text: true,
  token: "mock-token",
  filename: "wbs_sample_v1.xlsx",
  sheets: [{ name: "WBS", row_count: 27, header_row: 3, columns: [] }],
  selected_sheet: "WBS",
  header_row: 3,
  columns: ["No", "作業内容", "担当", "着手日", "期限", "進捗", "状態", "重要度", "先行作業", "課題", "備考"],
  mapping: {
    code: "No", title: "作業内容", owner: "担当", planned_start: "着手日", planned_end: "期限",
    progress: "進捗", status: "状態", priority: "重要度", dependency: "先行作業", issue: "課題", notes: "備考",
    parent: null, description: null, actual_start: null, actual_end: null, milestone: null, estimated_hours: null,
  },
  mapping_candidates: [
    { field: "title", column: "作業内容", confidence: 1, reason: "完全一致: 「作業内容」" },
    { field: "owner", column: "担当", confidence: 1, reason: "完全一致: 「担当」" },
  ],
  unmapped_columns: [],
  preview: [
    { code: "1.1", title: "現行業務調査", owner: "山田 太郎", planned_start: isoDate(-50), planned_end: isoDate(-40), progress: 100, status: "done", priority: "high", dependency: [], issue: null },
    { code: "1.2", title: "業務要件ヒアリング", owner: "山田 太郎", planned_start: isoDate(-39), planned_end: isoDate(-30), progress: 100, status: "done", priority: "high", dependency: ["現行業務調査"], issue: null },
    { code: "2.2", title: "API仕様確定", owner: "佐藤 健一", planned_start: isoDate(-16), planned_end: isoDate(-4), progress: 60, status: "in_progress", priority: "critical", dependency: ["要件定義書作成"], issue: "顧客からのAPI仕様回答待ち" },
  ],
  raw_preview: [],
  warnings: ["モックモードのため、実際のファイル解析は行われません。"],
  known_fields: [
    { field: "code", label: "Task ID / WBS No" }, { field: "title", label: "タスク名" },
    { field: "parent", label: "親タスク" }, { field: "description", label: "詳細" },
    { field: "owner", label: "担当者" }, { field: "planned_start", label: "開始予定日" },
    { field: "planned_end", label: "終了予定日" }, { field: "actual_start", label: "実績開始日" },
    { field: "actual_end", label: "実績終了日" }, { field: "progress", label: "進捗率" },
    { field: "status", label: "Status" }, { field: "priority", label: "Priority" },
    { field: "dependency", label: "依存関係" }, { field: "issue", label: "課題" },
    { field: "notes", label: "備考" }, { field: "milestone", label: "マイルストーン" },
    { field: "estimated_hours", label: "工数" },
  ],
};


/** デモ用の課題リスト（先方が書いた雑多な文章のイメージ） */
const MOCK_ISSUE_ROWS = [
  { row_index: 0, text: "特にありません。予定通り終わりました", task_hint: "現行業務調査", severity_hint: null, due_date: null },
  { row_index: 1, text: "経営層の意思決定がまだ出ていません。承認会議が延期になっており、後続が止まります", task_hint: "改善方針策定", severity_hint: null, due_date: null },
  { row_index: 2, text: "・帳票の出力仕様が決まっていない\n・外部連携の認証方式について先方の回答待ち", task_hint: "システム要件定義", severity_hint: null, due_date: isoDate(10) },
  { row_index: 3, text: "見積が1社しか届いていません。至急、他社にも催促が必要です", task_hint: "ベンダー選定", severity_hint: "高", due_date: isoDate(3) },
  { row_index: 4, text: "検討中", task_hint: "社内教育資料作成", severity_hint: null, due_date: null },
  { row_index: 5, text: "ありがとうございました。引き続きよろしくお願いします", task_hint: "課題整理", severity_hint: null, due_date: null },
];

const MOCK_ISSUE_WORDS = ["決まっていない", "回答待ち", "止まり", "延期", "ていません", "エラー", "至急", "催促", "遅れ", "できない"];
const MOCK_REPORT_WORDS = ["特にありません", "完了しました", "終わりました", "ありがとうございました", "よろしくお願いします", "順調"];

/** バックエンドの判定を模した簡易版（デモ表示用。実ロジックはPython側） */
function triageMock(
  text: string,
  rowIndex: number,
  hint: { severity_hint?: string | null; due_date?: string | null } = {},
) {
  const statements = text
    .split(/[\n]+/)
    .flatMap((line) => (line.split("。").length > 2 ? line.split("。") : [line]))
    .map((line) => line.replace(/^[・\-*]\s*/, "").trim())
    .filter((line) => line.length >= 3);

  return (statements.length ? statements : [text]).map((statement, partIndex) => {
    const issueHits = MOCK_ISSUE_WORDS.filter((w) => statement.includes(w));
    const reportHits = MOCK_REPORT_WORDS.filter((w) => statement.includes(w));
    const label =
      issueHits.length && !reportHits.length
        ? "issue"
        : reportHits.length && !issueHits.length
          ? "not_issue"
          : "uncertain";
    const severity =
      hint.severity_hint === "高" || statement.includes("至急")
        ? "high"
        : hint.severity_hint === "低"
          ? "low"
          : "medium";
    return {
      id: `r${rowIndex}-${partIndex}-0`,
      row_index: rowIndex,
      part_index: partIndex,
      source_text: text,
      statement,
      label,
      confidence: label === "issue" ? 0.75 : label === "not_issue" ? 0.85 : 0.4,
      title: label === "not_issue" ? "" : statement.slice(0, 28),
      description: label === "not_issue" ? "" : statement,
      severity_estimate: label === "issue" ? (severity === "high" ? "高" : "中") : "不明",
      severity,
      reasons: [
        issueHits.length ? `課題を示す語: ${issueHits.join("、")}` : "",
        reportHits.length ? `報告を示す語: ${reportHits.join("、")}` : "",
        hint.severity_hint ? `記入された重要度「${hint.severity_hint}」を使用` : "",
      ].filter(Boolean),
      related_task_candidates: [],
      due_date: hint.due_date ?? null,
      split: statements.length > 1,
      source: "rules",
    };
  });
}

function parseQuery(path: string): [string, URLSearchParams] {
  const [base, search] = path.split("?");
  return [base, new URLSearchParams(search ?? "")];
}

function ok<T>(value: T): Promise<T> {
  // ネットワーク往復の代わりに1フレーム分だけ遅らせる（ローディング表示の確認用）
  return new Promise((resolve) => setTimeout(() => resolve(value), 60));
}

export function handleMock<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) : {};
  const [route, query] = parseQuery(path);
  const data = db();
  const segments = route.split("/").filter(Boolean); // api, projects, 1, tasks ...
  const projectId = Number(segments[2]);
  const resource = segments[3];
  const asAny = <V,>(value: V) => ok(value as unknown as T);

  // ---- projects ----------------------------------------------------------
  if (route === "/api/projects" && method === "GET") {
    return asAny(
      data.projects.map((project) => {
        const tasks = projectTasks(project.id);
        return {
          ...project,
          task_count: tasks.length,
          open_task_count: tasks.filter(isActive).length,
          overdue_task_count: tasks.filter((task) => task.is_overdue).length,
          open_issue_count: data.issues.filter((i) => i.project_id === project.id && i.status === "open").length,
        };
      }),
    );
  }
  if (route === "/api/projects" && method === "POST") {
    const project = {
      id: data.sequence++, name: body.name, description: body.description ?? null,
      start_date: body.start_date ?? null, end_date: body.end_date ?? null,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    data.projects.push(project);
    return asAny(project);
  }
  if (segments[1] === "projects" && segments.length === 3 && method === "PATCH") {
    const project = data.projects.find((p) => p.id === projectId)!;
    Object.assign(project, body);
    return asAny(project);
  }
  if (segments[1] === "projects" && segments.length === 3 && method === "DELETE") {
    data.projects = data.projects.filter((p) => p.id !== projectId);
    return asAny(undefined);
  }
  if (resource === "dashboard") return asAny(buildDashboard(projectId));
  if (resource === "ai-pmo") return asAny(buildAiPmo(projectId));
  if (resource === "risks") return asAny(buildAiPmo(projectId).delay_risks);
  if (resource === "hidden-issues") return asAny(buildAiPmo(projectId).hidden_issues);
  if (resource === "llm-status") {
    return asAny({ llm_available: false, model: null, note: "モックモードのため、LLMは呼び出しません。" });
  }

  // ---- tasks -------------------------------------------------------------
  if (resource === "tasks" && method === "GET") {
    refresh(projectId);
    let tasks = projectTasks(projectId);
    const statuses = query.getAll("status");
    const priorities = query.getAll("priority");
    if (statuses.length) tasks = tasks.filter((task) => statuses.includes(task.status));
    if (priorities.length) tasks = tasks.filter((task) => priorities.includes(task.priority));
    if (query.get("owner_id")) tasks = tasks.filter((task) => task.owner_id === Number(query.get("owner_id")));
    if (query.get("unassigned")) tasks = tasks.filter((task) => !task.owner_id);
    if (query.get("overdue")) tasks = tasks.filter((task) => task.is_overdue);
    if (query.get("risk_min")) tasks = tasks.filter((task) => task.risk_score >= Number(query.get("risk_min")));
    if (query.get("category_task_id")) {
      const id = Number(query.get("category_task_id"));
      tasks = tasks.filter((task) => task.id === id || task.parent_task_id === id);
    }
    if (query.get("parent_task_id")) {
      tasks = tasks.filter((task) => task.parent_task_id === Number(query.get("parent_task_id")));
    }
    if (query.get("leaves_only")) tasks = tasks.filter((task) => !task.is_summary);
    const needle = (query.get("q") ?? "").toLowerCase();
    if (needle) {
      tasks = tasks.filter(
        (task) => task.title.toLowerCase().includes(needle) || (task.code ?? "").toLowerCase().includes(needle),
      );
    }
    const sort = query.get("sort") ?? "planned_end";
    const direction = query.get("order") === "desc" ? -1 : 1;
    const key = (task: Task): string | number =>
      sort === "risk_score" ? task.risk_score
      : sort === "progress" ? task.progress
      : sort === "title" ? task.title
      : sort === "status" ? task.status
      : sort === "code" ? task.code ?? ""
      : sort === "priority" ? ["low", "medium", "high", "critical"].indexOf(task.priority)
      : (task[sort as "planned_end" | "planned_start"] ?? "9999-12-31");
    tasks = [...tasks].sort((a, b) => (key(a) > key(b) ? direction : key(a) < key(b) ? -direction : 0));
    return asAny(tasks);
  }
  if (resource === "tasks" && method === "POST") {
    const task: Task = {
      ...(data.tasks.find(() => false) ?? ({} as Task)),
      ...body,
      id: data.sequence++,
      project_id: projectId,
      code: body.code || `T-${String(data.sequence).padStart(3, "0")}`,
      owner_name: data.people.find((person) => person.id === body.owner_id)?.name ?? null,
      predecessor_task_ids: body.predecessor_task_ids ?? [],
      successor_task_ids: [],
      child_task_ids: [],
      issue_ids: [],
      open_issue_count: 0,
      path_titles: [],
    };
    data.tasks.push(task);
    refresh(projectId);
    return asAny(task);
  }
  if (segments[1] === "tasks" && segments.length === 3) {
    const taskId = Number(segments[2]);
    const task = data.tasks.find((t) => t.id === taskId);
    if (!task) return Promise.reject(new Error("Task not found"));
    if (method === "DELETE") {
      data.tasks = data.tasks.filter((t) => t.id !== taskId);
      refresh(task.project_id);
      return asAny(undefined);
    }
    if (method === "PATCH") {
      Object.assign(task, body);
      if ("owner_id" in body) {
        task.owner_name = data.people.find((person) => person.id === body.owner_id)?.name ?? null;
      }
      if (body.status === "done") task.progress = 100;
      refresh(task.project_id);
      return asAny(task);
    }
    refresh(task.project_id);
    return asAny(task);
  }

  // ---- people ------------------------------------------------------------
  if (resource === "people" && method === "GET") {
    refresh(projectId);
    return asAny(data.people.filter((person) => person.project_id === projectId));
  }
  if (resource === "people" && method === "POST") {
    const person: Person = {
      id: data.sequence++, project_id: projectId, name: body.name, role: body.role ?? null,
      email: body.email ?? null, capacity_tasks: body.capacity_tasks ?? 8,
      assigned_task_count: 0, open_task_count: 0, overdue_task_count: 0, high_risk_task_count: 0,
      critical_task_count: 0, due_this_week_count: 0, open_issue_count: 0, average_progress: 0,
      load_ratio: 0, load_level: "light", task_ids: [],
    };
    data.people.push(person);
    return asAny(person);
  }
  if (segments[1] === "people" && segments.length === 3) {
    const personId = Number(segments[2]);
    if (method === "DELETE") {
      data.people = data.people.filter((person) => person.id !== personId);
      return asAny(undefined);
    }
    const person = data.people.find((p) => p.id === personId)!;
    Object.assign(person, body);
    return asAny(person);
  }

  // ---- issues ------------------------------------------------------------
  if (resource === "issues" && method === "GET") {
    let issues = data.issues.filter((issue) => issue.project_id === projectId);
    const statuses = query.getAll("status");
    const severities = query.getAll("severity");
    if (statuses.length) issues = issues.filter((issue) => statuses.includes(issue.status));
    if (severities.length) issues = issues.filter((issue) => severities.includes(issue.severity));
    if (query.get("open_only")) issues = issues.filter((i) => i.status !== "resolved" && i.status !== "closed");
    if (query.get("owner_id")) issues = issues.filter((i) => i.owner_id === Number(query.get("owner_id")));
    if (query.get("task_id")) issues = issues.filter((i) => i.task_id === Number(query.get("task_id")));
    const needle = (query.get("q") ?? "").toLowerCase();
    if (needle) issues = issues.filter((issue) => issue.title.toLowerCase().includes(needle));
    issues = [...issues].sort((a, b) => SEVERITY_RANK[b.severity] - SEVERITY_RANK[a.severity]);
    return asAny(issues);
  }
  if (resource === "issues" && method === "POST") {
    const task = data.tasks.find((t) => t.id === body.task_id);
    const issue: Issue = {
      id: data.sequence++, project_id: projectId, code: `I-${data.sequence}`, task_id: body.task_id ?? null,
      task_title: task?.title ?? null, task_category: task?.category ?? null, title: body.title,
      description: body.description ?? null, severity: body.severity ?? "medium",
      owner_id: body.owner_id ?? null,
      owner_name: data.people.find((person) => person.id === body.owner_id)?.name ?? null,
      raised_on: body.raised_on ?? null, due_date: body.due_date ?? null, status: body.status ?? "open",
      action_plan: body.action_plan ?? null, resolution: body.resolution ?? null, is_overdue: false,
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    data.issues.push(issue);
    return asAny(issue);
  }
  if (segments[1] === "issues" && segments.length === 3) {
    const issueId = Number(segments[2]);
    if (method === "DELETE") {
      data.issues = data.issues.filter((issue) => issue.id !== issueId);
      return asAny(undefined);
    }
    const issue = data.issues.find((i) => i.id === issueId)!;
    Object.assign(issue, body);
    if ("owner_id" in body) {
      issue.owner_name = data.people.find((person) => person.id === body.owner_id)?.name ?? null;
    }
    return asAny(issue);
  }

  // ---- milestones --------------------------------------------------------
  if (resource === "milestones" && method === "GET") {
    return asAny(data.milestones.filter((milestone) => milestone.project_id === projectId));
  }
  if (resource === "milestones" && method === "POST") {
    const milestone: Milestone = {
      id: data.sequence++, project_id: projectId, title: body.title, description: null,
      due_date: body.due_date ?? null, status: "pending", days_remaining: null, at_risk: false,
    };
    data.milestones.push(milestone);
    return asAny(milestone);
  }
  if (resource === "milestones" && method === "DELETE") {
    const milestoneId = Number(segments[4]);
    data.milestones = data.milestones.filter((milestone) => milestone.id !== milestoneId);
    return asAny(undefined);
  }

  // ---- categories --------------------------------------------------------
  if (resource === "categories" && segments[4] === "suggest") {
    refresh(projectId);
    const targets = projectTasks(projectId).filter((task) => !task.is_summary && !task.parent_task_id);
    const response: CategorySuggestResponse = {
      project_id: projectId,
      llm_used: false,
      llm_note: "モックモードのため、キーワード辞書による簡易分類を返しています。",
      existing_categories: projectTasks(projectId)
        .filter((task) => task.is_summary)
        .map((task) => ({ task_id: task.id, title: task.title })),
      suggestions: targets.slice(0, 20).map((task) => ({
        task_id: task.id,
        task_code: task.code,
        task_title: task.title,
        current_category: task.category,
        suggested_category: task.title.includes("テスト") ? "テスト" : task.title.includes("設計") ? "設計" : "開発・実装",
        existing_category_id: null,
        confidence: 0.8,
        reason: "キーワード一致（モック）",
        source: "rules",
      })),
      unmatched_task_ids: [],
    };
    return asAny(response);
  }
  if (resource === "categories" && segments[4] === "apply") {
    const created: string[] = [];
    (body.assignments ?? []).forEach((assignment: { task_id: number; category_name: string }) => {
      let parent = data.tasks.find(
        (task) => task.project_id === projectId && task.title === assignment.category_name,
      );
      if (!parent) {
        parent = { ...db().tasks[0], id: data.sequence++, project_id: projectId, title: assignment.category_name,
          code: `C-${data.sequence}`, parent_task_id: null, owner_id: null, owner_name: null,
          planned_start: null, planned_end: null, actual_start: null, actual_end: null, progress: 0,
          status: "not_started", predecessor_task_ids: [], successor_task_ids: [], child_task_ids: [] };
        data.tasks.push(parent);
        created.push(assignment.category_name);
      }
      const task = data.tasks.find((t) => t.id === assignment.task_id);
      if (task) task.parent_task_id = parent.id;
    });
    refresh(projectId);
    return asAny({ updated_tasks: (body.assignments ?? []).length, created_categories: created, skipped: [] });
  }

  // ---- 課題インポートの自動判定 -------------------------------------------
  if (route === "/api/imports/issue-rows") {
    return asAny({
      text_column: "課題・気になること",
      available_columns: IMPORT_SAMPLE.columns,
      rows: MOCK_ISSUE_ROWS,
    });
  }
  if (route === "/api/issues/analyze") {
    const rows: {
      row_index?: number;
      text: string;
      severity_hint?: string | null;
      due_date?: string | null;
    }[] = body.rows ?? MOCK_ISSUE_ROWS;
    const items = rows.flatMap((row, index) =>
      triageMock(row.text, row.row_index ?? index, {
        severity_hint: row.severity_hint,
        due_date: row.due_date,
      }),
    );
    const counts = {
      issue: items.filter((i) => i.label === "issue").length,
      uncertain: items.filter((i) => i.label === "uncertain").length,
      not_issue: items.filter((i) => i.label === "not_issue").length,
    };
    return asAny({
      llm_used: false,
      llm_note: "デモモードのため、簡易なキーワード判定の結果を表示しています。",
      counts,
      items,
    });
  }
  if (route === "/api/issues/bulk_create") {
    const items: {
      title: string;
      description?: string;
      severity?: string;
      due_date?: string | null;
      task_id?: number | null;
    }[] = body.items ?? [];
    const ids: number[] = [];
    items.forEach((item) => {
      const task = data.tasks.find((t) => t.id === item.task_id);
      const id = data.sequence++;
      ids.push(id);
      data.issues.push({
        id,
        project_id: body.project_id,
        code: `I-${String(data.issues.length + 1).padStart(3, "0")}`,
        task_id: task?.id ?? null,
        task_title: task?.title ?? null,
        task_category: task?.category ?? null,
        title: item.title,
        description: item.description ?? null,
        severity: (item.severity as Issue["severity"]) ?? "medium",
        owner_id: null,
        owner_name: null,
        raised_on: isoDate(0),
        due_date: item.due_date ?? null,
        status: "open",
        action_plan: null,
        resolution: null,
        is_overdue: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    });
    return asAny({ created: ids.length, issue_ids: ids, skipped: [] });
  }

  // ---- imports -----------------------------------------------------------
  if (route.startsWith("/api/imports")) {
    if (route.endsWith("/plan")) {
      return asAny({
        match_by: "auto", create_count: 2, update_count: 4, unchanged_count: 23, skipped_rows: 0,
        rows: [
          { row_index: 0, title: "基本設計", code: "2.1", action: "update", matched_task_id: 1,
            matched_task_title: "基本設計", matched_by: "code",
            changes: [{ field: "progress", label: "進捗率", before: "95.0", after: "100.0" }] },
          { row_index: 1, title: "性能テスト環境構築", code: "3.6", action: "create", matched_task_id: null,
            matched_task_title: null, matched_by: null, changes: [] },
        ],
        missing_in_file: [],
      });
    }
    if (route.endsWith("/commit")) {
      return asAny({
        project_id: 1, project_name: "基幹システム刷新 PJ (モック)", match_by: "none",
        created_tasks: 27, updated_tasks: 0, unchanged_tasks: 0, created_people: 5, created_issues: 4,
        created_dependencies: 18, created_milestones: 2, skipped_rows: 0,
        warnings: ["モックモードのため、実際には登録されていません。"],
      });
    }
    return asAny(IMPORT_SAMPLE);
  }

  return Promise.reject(new Error(`モックAPIが未対応のリクエストです: ${method} ${route}`));
}
