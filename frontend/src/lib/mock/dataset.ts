/**
 * バックエンド無しでUIを触るための擬似データ。
 *
 * NEXT_PUBLIC_MOCK=1 のときだけ使われる。実際の分析エンジン（Python側）とは
 * 別物で、Risk Score などは画面確認用に単純化した式で埋めている。
 */
import type { Issue, Milestone, Person, Project, Task } from "../types";

export interface MockConfig {
  /** ストレス用プロジェクトのTask件数 */
  stressTasks: number;
  /** ストレス用プロジェクトのタスク名の文字数 */
  labelLength: number;
}

export function readMockConfig(): MockConfig {
  const toInt = (value: string | undefined, fallback: number) => {
    const parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback;
  };
  return {
    stressTasks: toInt(process.env.NEXT_PUBLIC_MOCK_TASKS, 200),
    labelLength: toInt(process.env.NEXT_PUBLIC_MOCK_LABEL_LENGTH, 40),
  };
}

/** 実行するたびに同じデータになるよう、乱数は固定シードで回す */
function seeded(seed: number): () => number {
  let state = seed;
  return () => {
    state = (state * 1664525 + 1013904223) % 4294967296;
    return state / 4294967296;
  };
}

const DAY = 86400000;

export function isoDate(offsetDays: number, base = new Date()): string {
  const date = new Date(base.getTime() + offsetDays * DAY);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export interface MockStore {
  projects: Project[];
  people: Person[];
  tasks: Task[];
  issues: Issue[];
  milestones: Milestone[];
  sequence: number;
}

const OWNERS = [
  { name: "佐藤 健一", role: "PM" },
  { name: "田中 美咲", role: "開発リード" },
  { name: "鈴木 大輔", role: "アーキテクト" },
  { name: "高橋 由紀", role: "QAリード" },
  { name: "山田 太郎", role: "業務担当" },
  { name: "ラミレス・アレクサンドラ", role: "外部ベンダー窓口（長い氏名の確認用）" },
];

const STATUSES: Task["status"][] = ["not_started", "in_progress", "blocked", "done"];
const PRIORITIES: Task["priority"][] = ["low", "medium", "high", "critical"];

/** 指定文字数のタスク名を作る（長いラベルの折り返し確認用） */
function longTitle(index: number, length: number): string {
  const body = `基幹システム刷新に伴う${index}番目の業務プロセス再設計および関連ドキュメント整備作業`;
  return body.length >= length ? body.slice(0, length) : body.padEnd(length, "・");
}

function baseTask(id: number, projectId: number, title: string): Task {
  return {
    id,
    project_id: projectId,
    code: `T-${String(id).padStart(3, "0")}`,
    title,
    description: null,
    parent_task_id: null,
    owner_id: null,
    owner_name: null,
    parent_task_title: null,
    category: null,
    path_titles: [],
    depth: 0,
    child_count: 0,
    is_summary: false,
    effective_progress: 0,
    effective_start: null,
    effective_end: null,
    planned_start: null,
    planned_end: null,
    actual_start: null,
    actual_end: null,
    progress: 0,
    status: "not_started",
    priority: "medium",
    estimated_hours: null,
    notes: null,
    predecessor_task_ids: [],
    successor_task_ids: [],
    child_task_ids: [],
    issue_ids: [],
    open_issue_count: 0,
    is_overdue: false,
    days_overdue: 0,
    days_to_due: null,
    expected_progress: 0,
    progress_gap: 0,
    risk_score: 0,
    risk_level: "low",
    total_float: null,
    is_critical_path: false,
  };
}

/** 予定日・進捗から、画面表示に必要な派生値を埋める */
export function decorate(tasks: Task[]): Task[] {
  const byId = new Map(tasks.map((task) => [task.id, task]));
  const today = new Date();
  const todayISO = isoDate(0, today);

  tasks.forEach((task) => {
    task.child_task_ids = tasks.filter((t) => t.parent_task_id === task.id).map((t) => t.id);
    task.child_count = task.child_task_ids.length;
    task.is_summary = task.child_count > 0;
    const parent = task.parent_task_id ? byId.get(task.parent_task_id) : null;
    task.parent_task_title = parent?.title ?? null;
    task.path_titles = parent ? [parent.title] : [];
    task.category = parent?.title ?? null;
    task.depth = parent ? 1 : 0;
  });

  tasks.forEach((task) => {
    const children = task.child_task_ids.map((id) => byId.get(id)!).filter(Boolean);
    const active = task.status !== "done" && task.status !== "cancelled";
    const end = task.planned_end;
    const start = task.planned_start;

    if (task.is_summary) {
      const starts = children.map((c) => c.planned_start).filter(Boolean) as string[];
      const ends = children.map((c) => c.planned_end).filter(Boolean) as string[];
      task.effective_start = task.planned_start ?? (starts.length ? starts.sort()[0] : null);
      task.effective_end = task.planned_end ?? (ends.length ? ends.sort().slice(-1)[0] : null);
      task.effective_progress =
        task.progress ||
        (children.length
          ? Math.round(children.reduce((sum, c) => sum + c.progress, 0) / children.length)
          : 0);
    } else {
      task.effective_start = start;
      task.effective_end = end;
      task.effective_progress = task.progress;
    }

    if (end) {
      const days = Math.round((new Date(end).getTime() - new Date(todayISO).getTime()) / DAY);
      task.days_to_due = days;
      task.is_overdue = active && days < 0;
      task.days_overdue = task.is_overdue ? Math.abs(days) : 0;
    }
    if (start && end && active) {
      const span = new Date(end).getTime() - new Date(start).getTime();
      const elapsed = new Date(todayISO).getTime() - new Date(start).getTime();
      task.expected_progress = span > 0 ? Math.max(0, Math.min(100, Math.round((elapsed / span) * 100))) : 0;
      task.progress_gap = Math.round(task.expected_progress - task.progress);
    }

    let score = 0;
    if (task.is_overdue) score += Math.min(40, 12 + task.days_overdue * 3.5);
    if (task.progress_gap > 5) score += Math.min(25, task.progress_gap * 0.35);
    if (!task.owner_id && active) score += 8;
    if (task.status === "blocked") score += 8;
    if (task.priority === "critical") score += 6;
    else if (task.priority === "high") score += 3;
    task.risk_score = active ? Math.round(Math.min(100, score)) : 0;
    task.risk_level =
      task.risk_score >= 80 ? "critical" : task.risk_score >= 60 ? "high" : task.risk_score >= 35 ? "medium" : "low";
  });

  tasks.forEach((task) => {
    task.successor_task_ids = tasks
      .filter((t) => t.predecessor_task_ids.includes(task.id))
      .map((t) => t.id);
  });
  return tasks;
}

export function buildStore(config: MockConfig): MockStore {
  const random = seeded(20260904);
  const projects: Project[] = [];
  const people: Person[] = [];
  const tasks: Task[] = [];
  const issues: Issue[] = [];
  const milestones: Milestone[] = [];
  let id = 0;
  const next = () => ++id;

  // ---- プロジェクト1: 実務に近いサイズ ----------------------------------
  const main: Project = {
    id: 1,
    name: "基幹システム刷新 PJ (モック)",
    description: "バックエンド無しで画面を確認するための擬似データです。",
    start_date: isoDate(-60),
    end_date: isoDate(60),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  projects.push(main);

  OWNERS.forEach((owner, index) => {
    people.push({
      id: index + 1,
      project_id: main.id,
      name: owner.name,
      role: owner.role,
      email: null,
      capacity_tasks: index === 1 ? 4 : 8,
      assigned_task_count: 0,
      open_task_count: 0,
      overdue_task_count: 0,
      high_risk_task_count: 0,
      critical_task_count: 0,
      due_this_week_count: 0,
      open_issue_count: 0,
      average_progress: 0,
      load_ratio: 0,
      load_level: "normal",
      task_ids: [],
    });
  });

  // カテゴリには「達成したいゴール」を持たせる（WBSテンプレートの「このカテゴリのゴール」）
  const phases: Array<[string, string]> = [
    ["要件フェーズ", "現場が使える業務フローに合意が取れていて、開発に着手できる状態にする"],
    ["設計フェーズ", "画面・API・DBの仕様が確定し、実装を並行で進められる状態にする"],
    ["開発フェーズ", "本番相当のデータで主要業務が一通り動く状態にする"],
    ["テストフェーズ", "現場が自分たちで操作して、本番移行の判断ができる状態にする"],
  ];
  const phaseIds: number[] = [];
  phases.forEach(([title, goal], index) => {
    const task = baseTask(next(), main.id, title);
    task.code = `P-${index + 1}`;
    task.description = goal;
    task.status = index < 2 ? "in_progress" : "not_started";
    tasks.push(task);
    phaseIds.push(task.id);
  });

  const leaves: Array<[string, number, number, number, number, Task["status"], Task["priority"]]> = [
    ["現行業務調査", 0, -50, -40, 100, "done", "high"],
    ["業務要件ヒアリング", 0, -39, -30, 100, "done", "high"],
    ["要件定義書作成", 0, -29, -18, 100, "done", "critical"],
    ["基本設計", 1, -18, -2, 95, "in_progress", "high"],
    ["API仕様確定", 1, -16, -4, 60, "in_progress", "critical"],
    ["DB設計", 1, -16, -1, 80, "in_progress", "high"],
    ["画面設計", 1, -12, 2, 40, "in_progress", "medium"],
    ["共通基盤構築", 2, -5, 5, 30, "in_progress", "high"],
    ["バックエンド実装", 2, 0, 18, 0, "not_started", "high"],
    ["フロントエンド実装", 2, 2, 20, 0, "not_started", "high"],
    ["バッチ開発", 2, 5, 22, 0, "blocked", "medium"],
    ["外部連携開発", 2, 8, 25, 0, "not_started", "critical"],
    ["単体テスト", 3, 20, 28, 0, "not_started", "medium"],
    ["結合テスト", 3, 28, 38, 0, "not_started", "high"],
    ["総合テスト", 3, 38, 50, 0, "not_started", "high"],
    ["受入テスト支援", 3, 50, 58, 0, "not_started", "medium"],
  ];

  let previous: Task | null = null;
  leaves.forEach(([title, phase, start, end, progress, status, priority], index) => {
    const task = baseTask(next(), main.id, title);
    task.parent_task_id = phaseIds[phase];
    task.planned_start = isoDate(start);
    task.planned_end = isoDate(end);
    task.progress = progress;
    task.status = status;
    task.priority = priority;
    task.estimated_hours = 4 + Math.round(random() * 16);
    // 一部は担当未設定のまま（Owner未設定の見え方を確認するため）
    const ownerIndex = index % 7;
    if (ownerIndex < 6) {
      task.owner_id = ownerIndex + 1;
      task.owner_name = OWNERS[ownerIndex].name;
    }
    if (status !== "not_started") task.actual_start = task.planned_start;
    if (status === "done") task.actual_end = isoDate(end + 1);
    if (previous && index % 3 !== 0) task.predecessor_task_ids = [previous.id];
    previous = task;
    tasks.push(task);
  });

  const issueSeeds: Array<[string, string, Issue["severity"], Issue["status"], number, number | null]> = [
    ["顧客からのAPI仕様回答待ち", "外部連携APIの認証方式について回答が届いていない。", "high", "open", 9, -2],
    ["移行元データに重複レコードあり", "旧システムのマスタに重複がある。", "high", "in_progress", 10, 3],
    ["性能要件が未確定", "同時接続数の目標値が決まっていない。", "medium", "open", 11, 5],
    ["レビュー担当者が未定", "設計レビューの実施者が決まっていない。", "low", "open", 8, null],
  ];
  issueSeeds.forEach(([title, description, severity, status, taskId, due], index) => {
    const task = tasks.find((t) => t.id === taskId);
    issues.push({
      id: index + 1,
      project_id: main.id,
      code: `I-${String(index + 1).padStart(3, "0")}`,
      task_id: task?.id ?? null,
      task_title: task?.title ?? null,
      task_category: task?.category ?? null,
      title,
      description,
      severity,
      owner_id: index === 3 ? null : (index % 5) + 1,
      owner_name: index === 3 ? null : OWNERS[index % 5].name,
      raised_on: isoDate(-10 + index),
      due_date: due === null ? null : isoDate(due),
      status,
      action_plan: null,
      resolution: null,
      is_overdue: due !== null && due < 0 && status !== "resolved",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  milestones.push(
    {
      id: 1, project_id: main.id, title: "内部リリース判定", description: null,
      due_date: isoDate(12), status: "pending", days_remaining: 12, at_risk: true,
    },
    {
      id: 2, project_id: main.id, title: "本番リリース", description: null,
      due_date: isoDate(45), status: "pending", days_remaining: 45, at_risk: false,
    },
  );

  // ---- プロジェクト2: 件数と長いラベルのストレス確認 ---------------------
  const stress: Project = {
    id: 2,
    name: `ストレス確認 PJ (${config.stressTasks}件・${config.labelLength}文字ラベル)`,
    description: "件数と長いラベルで崩れ方を見るためのプロジェクト。",
    start_date: isoDate(-30),
    end_date: isoDate(120),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  projects.push(stress);

  OWNERS.forEach((owner, index) => {
    people.push({
      ...people[index],
      id: 100 + index,
      project_id: stress.id,
      name: owner.name,
      capacity_tasks: 10,
    });
  });

  const stressPhases = ["第1バッチ", "第2バッチ", "第3バッチ", "第4バッチ", "第5バッチ"];
  const stressPhaseIds: number[] = [];
  stressPhases.forEach((title, index) => {
    const task = baseTask(next(), stress.id, `${title}: ${longTitle(index + 1, config.labelLength)}`);
    task.code = `S-P${index + 1}`;
    task.status = "in_progress";
    tasks.push(task);
    stressPhaseIds.push(task.id);
  });

  for (let index = 0; index < config.stressTasks; index += 1) {
    const task = baseTask(next(), stress.id, longTitle(index + 1, config.labelLength));
    task.parent_task_id = stressPhaseIds[index % stressPhaseIds.length];
    const start = -25 + Math.floor(random() * 110);
    task.planned_start = isoDate(start);
    task.planned_end = isoDate(start + 3 + Math.floor(random() * 20));
    task.progress = Math.floor(random() * 101);
    task.status = STATUSES[Math.floor(random() * STATUSES.length)];
    task.priority = PRIORITIES[Math.floor(random() * PRIORITIES.length)];
    task.estimated_hours = Math.round(random() * 40);
    task.notes = index % 9 === 0 ? longTitle(index, config.labelLength) : null;
    if (index % 5 !== 0) {
      const ownerIndex = index % OWNERS.length;
      task.owner_id = 100 + ownerIndex;
      task.owner_name = OWNERS[ownerIndex].name;
    }
    if (task.status !== "not_started") task.actual_start = task.planned_start;
    if (task.status === "done") {
      task.progress = 100;
      task.actual_end = task.planned_end;
    }
    tasks.push(task);
  }

  for (let index = 0; index < 40; index += 1) {
    const task = tasks.filter((t) => t.project_id === stress.id)[index * 3 + 5];
    if (!task) continue;
    issues.push({
      id: 1000 + index,
      project_id: stress.id,
      code: `I-${String(index + 1).padStart(3, "0")}`,
      task_id: task.id,
      task_title: task.title,
      task_category: task.category,
      title: longTitle(index + 1, config.labelLength),
      description: longTitle(index + 1, config.labelLength * 3),
      severity: (["low", "medium", "high", "critical"] as const)[index % 4],
      owner_id: 100 + (index % OWNERS.length),
      owner_name: OWNERS[index % OWNERS.length].name,
      raised_on: isoDate(-20 + index),
      due_date: isoDate(-5 + index),
      status: index % 3 === 0 ? "open" : index % 3 === 1 ? "in_progress" : "resolved",
      action_plan: null,
      resolution: null,
      is_overdue: index < 5,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  }

  milestones.push({
    id: 3, project_id: stress.id, title: longTitle(1, config.labelLength), description: null,
    due_date: isoDate(30), status: "pending", days_remaining: 30, at_risk: true,
  });

  decorate(tasks);
  return { projects, people, tasks, issues, milestones, sequence: id + 1 };
}
