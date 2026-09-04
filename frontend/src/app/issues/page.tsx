"use client";

import { useCallback, useEffect, useState } from "react";
import { useProjects } from "@/components/ProjectProvider";
import { Badge, Card, EmptyState, ErrorBanner, Field, Loading, Modal, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { ISSUE_STATUS_LABELS, SEVERITY_LABELS, formatFullDate, severityClass } from "@/lib/format";
import type { Issue, IssueStatus, Person, Severity, Task } from "@/lib/types";

const EMPTY_FORM = {
  title: "",
  description: "",
  severity: "medium" as Severity,
  status: "open" as IssueStatus,
  owner_id: "",
  task_id: "",
  raised_on: "",
  due_date: "",
  action_plan: "",
  resolution: "",
};

export default function IssuesPage() {
  const { projectId } = useProjects();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Issue | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [filters, setFilters] = useState({ q: "", severity: [] as string[], status: [] as string[], open_only: false });

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [issueList, taskList, peopleList] = await Promise.all([
        api.listIssues(projectId, {
          q: filters.q,
          severity: filters.severity,
          status: filters.status,
          open_only: filters.open_only,
        }),
        api.listTasks(projectId),
        api.listPeople(projectId),
      ]);
      setIssues(issueList);
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

  function openForm(issue: Issue | null) {
    setEditing(issue);
    setForm(
      issue
        ? {
            title: issue.title,
            description: issue.description ?? "",
            severity: issue.severity,
            status: issue.status,
            owner_id: issue.owner_id ? String(issue.owner_id) : "",
            task_id: issue.task_id ? String(issue.task_id) : "",
            raised_on: issue.raised_on ?? "",
            due_date: issue.due_date ?? "",
            action_plan: issue.action_plan ?? "",
            resolution: issue.resolution ?? "",
          }
        : EMPTY_FORM,
    );
    setShowForm(true);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId) return;
    const payload = {
      title: form.title,
      description: form.description || null,
      severity: form.severity,
      status: form.status,
      owner_id: form.owner_id ? Number(form.owner_id) : null,
      task_id: form.task_id ? Number(form.task_id) : null,
      raised_on: form.raised_on || null,
      due_date: form.due_date || null,
      action_plan: form.action_plan || null,
      resolution: form.resolution || null,
    };
    try {
      if (editing) await api.updateIssue(editing.id, payload);
      else await api.createIssue(projectId, payload);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    }
  }

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
  }

  if (!projectId) return <EmptyState title="プロジェクトを選択してください" />;

  const open = issues.filter((issue) => issue.status !== "resolved" && issue.status !== "closed");
  const overdue = open.filter((issue) => issue.is_overdue);
  const severe = open.filter((issue) => issue.severity === "high" || issue.severity === "critical");

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Issue Management</h1>
          <p className="text-sm text-ink-500">Taskとは独立した課題管理</p>
        </div>
        <button className="btn-primary" onClick={() => openForm(null)}>
          ＋ Issue新規登録
        </button>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="全Issue" value={issues.length} />
        <StatCard label="未解決" value={open.length} tone={open.length ? "warn" : "good"} />
        <StatCard label="高Severity" value={severe.length} tone={severe.length ? "danger" : "good"} />
        <StatCard label="期限超過" value={overdue.length} tone={overdue.length ? "danger" : "good"} />
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <span className="label">検索</span>
            <input
              className="input"
              placeholder="課題名 / 詳細"
              value={filters.q}
              onChange={(event) => setFilters({ ...filters, q: event.target.value })}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {Object.entries(SEVERITY_LABELS).map(([value, label]) => (
              <button
                key={value}
                className={`badge ${
                  filters.severity.includes(value)
                    ? "border-ink-900 bg-ink-900 text-white"
                    : "border-slate-200 bg-white text-ink-600"
                }`}
                onClick={() => setFilters({ ...filters, severity: toggle(filters.severity, value) })}
              >
                Severity{label}
              </button>
            ))}
            {Object.entries(ISSUE_STATUS_LABELS).map(([value, label]) => (
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
            <button
              className={`badge ${
                filters.open_only ? "border-amber-500 bg-amber-500 text-white" : "border-slate-200 bg-white text-ink-600"
              }`}
              onClick={() => setFilters({ ...filters, open_only: !filters.open_only })}
            >
              未解決のみ
            </button>
          </div>
        </div>
      </Card>

      {error && <ErrorBanner message={error} />}
      {loading && issues.length === 0 ? (
        <Loading />
      ) : issues.length === 0 ? (
        <EmptyState title="Issueがありません" hint="課題を登録すると、遅延リスク分析の根拠として利用されます。" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[1000px]">
            <thead className="bg-slate-50">
              <tr>
                <th className="th">ID</th>
                <th className="th">課題名</th>
                <th className="th">Severity</th>
                <th className="th">Owner</th>
                <th className="th">関連Task</th>
                <th className="th">発生日</th>
                <th className="th">期限</th>
                <th className="th">Status</th>
                <th className="th"></th>
              </tr>
            </thead>
            <tbody>
              {issues.map((issue) => (
                <tr key={issue.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                  <td className="td text-xs text-ink-500">{issue.code}</td>
                  <td className="td">
                    <button className="text-left font-medium hover:underline" onClick={() => openForm(issue)}>
                      {issue.title}
                    </button>
                    {issue.description && (
                      <p className="mt-0.5 max-w-md truncate text-xs text-ink-400">{issue.description}</p>
                    )}
                  </td>
                  <td className="td">
                    <Badge className={severityClass(issue.severity)}>{SEVERITY_LABELS[issue.severity]}</Badge>
                  </td>
                  <td className="td text-xs">{issue.owner_name ?? "未設定"}</td>
                  <td className="td max-w-[220px] text-xs text-ink-500">
                    {issue.task_title ? (
                      <>
                        {issue.task_category && (
                          <span className="block truncate text-[11px] text-ink-400">
                            {issue.task_category}
                          </span>
                        )}
                        <span className="block truncate">{issue.task_title}</span>
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="td text-xs tabular-nums">{formatFullDate(issue.raised_on)}</td>
                  <td className={`td text-xs tabular-nums ${issue.is_overdue ? "text-rose-600" : ""}`}>
                    {formatFullDate(issue.due_date)}
                  </td>
                  <td className="td">
                    <select
                      className="badge border-slate-200 bg-white text-ink-700"
                      value={issue.status}
                      onChange={async (event) => {
                        await api.updateIssue(issue.id, { status: event.target.value });
                        await load();
                      }}
                    >
                      {Object.entries(ISSUE_STATUS_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="td text-right">
                    <button className="text-xs text-ink-500 hover:text-ink-900" onClick={() => openForm(issue)}>
                      編集
                    </button>
                    <button
                      className="ml-3 text-xs text-rose-500 hover:text-rose-700"
                      onClick={async () => {
                        if (!window.confirm(`「${issue.title}」を削除しますか？`)) return;
                        await api.deleteIssue(issue.id);
                        await load();
                      }}
                    >
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
        <Modal title={editing ? `Issue編集: ${editing.title}` : "Issue新規登録"} onClose={() => setShowForm(false)} wide>
          <form className="space-y-4" onSubmit={submit}>
            <Field label="課題名 *">
              <input
                className="input"
                required
                value={form.title}
                onChange={(event) => setForm({ ...form, title: event.target.value })}
              />
            </Field>
            <Field label="詳細">
              <textarea
                className="input"
                rows={3}
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </Field>
            <div className="grid gap-3 md:grid-cols-4">
              <Field label="Severity">
                <select
                  className="input"
                  value={form.severity}
                  onChange={(event) => setForm({ ...form, severity: event.target.value as Severity })}
                >
                  {Object.entries(SEVERITY_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Status">
                <select
                  className="input"
                  value={form.status}
                  onChange={(event) => setForm({ ...form, status: event.target.value as IssueStatus })}
                >
                  {Object.entries(ISSUE_STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Owner">
                <select
                  className="input"
                  value={form.owner_id}
                  onChange={(event) => setForm({ ...form, owner_id: event.target.value })}
                >
                  <option value="">未設定</option>
                  {people.map((person) => (
                    <option key={person.id} value={person.id}>
                      {person.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="関連Task">
                <select
                  className="input"
                  value={form.task_id}
                  onChange={(event) => setForm({ ...form, task_id: event.target.value })}
                >
                  <option value="">なし</option>
                  {tasks.map((task) => (
                    <option key={task.id} value={task.id}>
                      {[...task.path_titles, task.title].join(" / ")}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Field label="発生日">
                <input
                  type="date"
                  className="input"
                  value={form.raised_on}
                  onChange={(event) => setForm({ ...form, raised_on: event.target.value })}
                />
              </Field>
              <Field label="Due Date">
                <input
                  type="date"
                  className="input"
                  value={form.due_date}
                  onChange={(event) => setForm({ ...form, due_date: event.target.value })}
                />
              </Field>
            </div>
            <Field label="対応方針">
              <textarea
                className="input"
                rows={2}
                value={form.action_plan}
                onChange={(event) => setForm({ ...form, action_plan: event.target.value })}
              />
            </Field>
            <Field label="Resolution">
              <textarea
                className="input"
                rows={2}
                value={form.resolution}
                onChange={(event) => setForm({ ...form, resolution: event.target.value })}
              />
            </Field>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setShowForm(false)}>
                キャンセル
              </button>
              <button type="submit" className="btn-primary">
                保存
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
