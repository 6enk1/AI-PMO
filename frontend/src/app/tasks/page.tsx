"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useProjects } from "@/components/ProjectProvider";
import { TaskFormModal } from "@/components/TaskFormModal";
import { Badge, Card, EmptyState, ErrorBanner, Loading, ProgressBar } from "@/components/ui";
import { api } from "@/lib/api";
import {
  PRIORITY_LABELS,
  STATUS_LABELS,
  formatFullDate,
  riskClass,
  statusClass,
} from "@/lib/format";
import type { Person, Task, TaskStatus } from "@/lib/types";

const SORTS = [
  { value: "planned_end", label: "終了予定日" },
  { value: "planned_start", label: "開始予定日" },
  { value: "risk_score", label: "Risk Score" },
  { value: "progress", label: "進捗率" },
  { value: "priority", label: "Priority" },
  { value: "status", label: "Status" },
  { value: "code", label: "Task ID" },
  { value: "title", label: "タスク名" },
];

export default function TasksPage() {
  const { projectId } = useProjects();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Task | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [filters, setFilters] = useState({
    q: "",
    status: [] as string[],
    priority: [] as string[],
    owner_id: "",
    category_task_id: "",
    overdue: false,
    risk_min: "",
    sort: "planned_end",
    order: "asc",
  });

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [taskList, peopleList] = await Promise.all([
        api.listTasks(projectId, {
          q: filters.q,
          status: filters.status,
          priority: filters.priority,
          owner_id: filters.owner_id || undefined,
          category_task_id: filters.category_task_id || undefined,
          overdue: filters.overdue,
          risk_min: filters.risk_min || undefined,
          sort: filters.sort,
          order: filters.order,
        }),
        api.listPeople(projectId),
      ]);
      setTasks(taskList);
      setPeople(peopleList);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  }, [projectId, filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const allTasks = useMemo(() => tasks, [tasks]);

  // 子を持つTaskをカテゴリ候補として扱う（フィルタが効いている間も選択肢を保つ）
  const [categories, setCategories] = useState<Task[]>([]);
  useEffect(() => {
    if (!projectId) return;
    void api
      .listTasks(projectId, { sort: "code", order: "asc" })
      .then((all) => setCategories(all.filter((task) => task.child_task_ids.length > 0)))
      .catch(() => setCategories([]));
  }, [projectId, tasks.length]);

  async function quickUpdate(task: Task, payload: Record<string, unknown>) {
    try {
      await api.updateTask(task.id, payload);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新に失敗しました");
    }
  }

  async function remove(task: Task) {
    if (!window.confirm(`「${task.title}」を削除します。よろしいですか？`)) return;
    await api.deleteTask(task.id);
    await load();
  }

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  if (!projectId) return <EmptyState title="プロジェクトを選択してください" />;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Task Management</h1>
          <p className="text-sm text-ink-500">{tasks.length} 件表示中</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => {
            setEditing(null);
            setShowForm(true);
          }}
        >
          ＋ Task新規作成
        </button>
      </header>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <span className="label">検索</span>
            <input
              className="input"
              placeholder="タスク名 / ID / 備考"
              value={filters.q}
              onChange={(event) => setFilters({ ...filters, q: event.target.value })}
            />
          </div>
          <div>
            <span className="label">担当者</span>
            <select
              className="input"
              value={filters.owner_id}
              onChange={(event) => setFilters({ ...filters, owner_id: event.target.value })}
            >
              <option value="">すべて</option>
              {people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <span className="label">カテゴリ（親タスク）</span>
            <select
              className="input"
              value={filters.category_task_id}
              onChange={(event) => setFilters({ ...filters, category_task_id: event.target.value })}
            >
              <option value="">すべて</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {"　".repeat(category.depth)}
                  {category.title}
                </option>
              ))}
            </select>
          </div>
          <div>
            <span className="label">Risk Score下限</span>
            <input
              type="number"
              className="input w-28"
              value={filters.risk_min}
              onChange={(event) => setFilters({ ...filters, risk_min: event.target.value })}
            />
          </div>
          <div>
            <span className="label">並び替え</span>
            <div className="flex gap-2">
              <select
                className="input"
                value={filters.sort}
                onChange={(event) => setFilters({ ...filters, sort: event.target.value })}
              >
                {SORTS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select
                className="input w-24"
                value={filters.order}
                onChange={(event) => setFilters({ ...filters, order: event.target.value })}
              >
                <option value="asc">昇順</option>
                <option value="desc">降順</option>
              </select>
            </div>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <button
              key={value}
              className={`badge ${
                filters.status.includes(value)
                  ? "border-ink-900 bg-ink-900 text-white"
                  : "border-slate-200 bg-white text-ink-600"
              }`}
              onClick={() => setFilters({ ...filters, status: toggle(filters.status, value) })}
            >
              {label}
            </button>
          ))}
          <span className="mx-1 text-slate-300">|</span>
          {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
            <button
              key={value}
              className={`badge ${
                filters.priority.includes(value)
                  ? "border-ink-900 bg-ink-900 text-white"
                  : "border-slate-200 bg-white text-ink-600"
              }`}
              onClick={() => setFilters({ ...filters, priority: toggle(filters.priority, value) })}
            >
              優先度{label}
            </button>
          ))}
          <span className="mx-1 text-slate-300">|</span>
          <button
            className={`badge ${
              filters.overdue ? "border-rose-500 bg-rose-500 text-white" : "border-slate-200 bg-white text-ink-600"
            }`}
            onClick={() => setFilters({ ...filters, overdue: !filters.overdue })}
          >
            期限超過のみ
          </button>
          <button
            className="badge border-slate-200 bg-white text-ink-500"
            onClick={() =>
              setFilters({
                q: "",
                status: [],
                priority: [],
                owner_id: "",
                category_task_id: "",
                overdue: false,
                risk_min: "",
                sort: "planned_end",
                order: "asc",
              })
            }
          >
            条件クリア
          </button>
        </div>
      </Card>

      {error && <ErrorBanner message={error} />}
      {loading && tasks.length === 0 ? (
        <Loading />
      ) : tasks.length === 0 ? (
        <EmptyState title="該当するTaskがありません" hint="条件を変更するか、新規作成してください。" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[1100px]">
            <thead className="bg-slate-50">
              <tr>
                <th className="th">ID</th>
                <th className="th">カテゴリ</th>
                <th className="th">タスク名</th>
                <th className="th">担当</th>
                <th className="th">予定</th>
                <th className="th">実績</th>
                <th className="th w-40">進捗</th>
                <th className="th">Status</th>
                <th className="th">優先度</th>
                <th className="th">Risk</th>
                <th className="th">依存</th>
                <th className="th"></th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr key={task.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                  <td className="td whitespace-nowrap text-xs text-ink-500">{task.code}</td>
                  <td className="td w-[150px] max-w-[150px]">
                    {task.path_titles.length > 0 ? (
                      <button
                        className="truncate text-left text-xs text-ink-600 hover:underline"
                        title={task.path_titles.join(" / ")}
                        onClick={() =>
                          setFilters({ ...filters, category_task_id: String(task.parent_task_id) })
                        }
                      >
                        <span className="block truncate font-medium">{task.category}</span>
                        {task.path_titles.length > 1 && (
                          <span className="block truncate text-[11px] text-ink-400">
                            {task.path_titles.slice(1).join(" / ")}
                          </span>
                        )}
                      </button>
                    ) : task.child_count > 0 ? (
                      <button
                        onClick={() => setFilters({ ...filters, category_task_id: String(task.id) })}
                      >
                        <Badge className="whitespace-nowrap border-indigo-200 bg-indigo-50 text-indigo-700">
                          カテゴリ 子{task.child_count}
                        </Badge>
                      </button>
                    ) : (
                      <span className="text-xs text-ink-300">—</span>
                    )}
                  </td>
                  <td className="td min-w-[220px]">
                    <button
                      className="text-left font-medium hover:underline"
                      onClick={() => {
                        setEditing(task);
                        setShowForm(true);
                      }}
                    >
                      {task.title}
                    </button>
                    <div className="mt-0.5 flex flex-wrap gap-1">
                      {task.is_overdue && (
                        <Badge className="border-rose-200 bg-rose-50 text-rose-700">
                          {task.days_overdue}日超過
                        </Badge>
                      )}
                      {task.is_critical_path && (
                        <Badge className="border-indigo-200 bg-indigo-50 text-indigo-700">CP</Badge>
                      )}
                      {task.open_issue_count > 0 && (
                        <Badge className="border-amber-200 bg-amber-50 text-amber-700">
                          Issue {task.open_issue_count}
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="td whitespace-nowrap">
                    <select
                      className="w-28 rounded border border-transparent bg-transparent px-1 py-0.5 text-sm hover:border-slate-300"
                      value={task.owner_id ?? ""}
                      onChange={(event) =>
                        void quickUpdate(task, {
                          owner_id: event.target.value ? Number(event.target.value) : null,
                        })
                      }
                    >
                      <option value="">未設定</option>
                      {people.map((person) => (
                        <option key={person.id} value={person.id}>
                          {person.name}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="td whitespace-nowrap text-xs tabular-nums">
                    {formatFullDate(task.planned_start)}
                    <br />
                    <span className={task.is_overdue ? "text-rose-600" : ""}>
                      {formatFullDate(task.planned_end)}
                    </span>
                  </td>
                  <td className="td whitespace-nowrap text-xs tabular-nums text-ink-500">
                    {formatFullDate(task.actual_start)}
                    <br />
                    {formatFullDate(task.actual_end)}
                  </td>
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <ProgressBar value={task.progress} expected={task.expected_progress} />
                      <span className="w-10 shrink-0 text-right text-xs tabular-nums">
                        {task.progress.toFixed(0)}%
                      </span>
                    </div>
                    {task.progress_gap > 5 && (
                      <p className="mt-0.5 text-[11px] text-rose-600">想定より {task.progress_gap.toFixed(0)}pt 遅れ</p>
                    )}
                  </td>
                  <td className="td">
                    <select
                      className={`badge ${statusClass(task.status)}`}
                      value={task.status}
                      onChange={(event) => void quickUpdate(task, { status: event.target.value as TaskStatus })}
                    >
                      {Object.entries(STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="td text-xs">{PRIORITY_LABELS[task.priority]}</td>
                  <td className="td">
                    <div className="flex items-center gap-2">
                      <span className={`inline-block h-2 w-2 rounded-full ${riskClass(task.risk_score)}`} />
                      <span className="text-xs tabular-nums">{task.risk_score.toFixed(0)}</span>
                    </div>
                  </td>
                  <td className="td text-xs text-ink-500">
                    {task.predecessor_task_ids.length > 0 && `先行 ${task.predecessor_task_ids.length}`}
                    {task.successor_task_ids.length > 0 && ` 後続 ${task.successor_task_ids.length}`}
                  </td>
                  <td className="td whitespace-nowrap text-right">
                    <button
                      className="text-xs text-ink-500 hover:text-ink-900"
                      onClick={() => {
                        setEditing(task);
                        setShowForm(true);
                      }}
                    >
                      編集
                    </button>
                    <button className="ml-3 text-xs text-rose-500 hover:text-rose-700" onClick={() => void remove(task)}>
                      削除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <TaskFormModal
          projectId={projectId}
          task={editing}
          tasks={allTasks}
          people={people}
          onClose={() => setShowForm(false)}
          onSaved={() => void load()}
        />
      )}
    </div>
  );
}
