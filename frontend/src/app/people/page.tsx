"use client";

import { useCallback, useEffect, useState } from "react";
import { useProjects } from "@/components/ProjectProvider";
import { Badge, Card, EmptyState, ErrorBanner, Field, Loading, Modal, ProgressBar } from "@/components/ui";
import { api } from "@/lib/api";
import { LOAD_LABELS, formatFullDate, loadClass, riskClass } from "@/lib/format";
import type { Person, Task } from "@/lib/types";

export default function PeoplePage() {
  const { projectId } = useProjects();
  const [people, setPeople] = useState<Person[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Person | null>(null);
  const [form, setForm] = useState({ name: "", role: "", email: "", capacity_tasks: "8" });
  const [expanded, setExpanded] = useState<number | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [peopleList, taskList] = await Promise.all([
        api.listPeople(projectId),
        api.listTasks(projectId, { sort: "risk_score", order: "desc" }),
      ]);
      setPeople(peopleList);
      setTasks(taskList);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  function openForm(person: Person | null) {
    setEditing(person);
    setForm({
      name: person?.name ?? "",
      role: person?.role ?? "",
      email: person?.email ?? "",
      capacity_tasks: String(person?.capacity_tasks ?? 8),
    });
    setShowForm(true);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId) return;
    const payload = {
      name: form.name,
      role: form.role || null,
      email: form.email || null,
      capacity_tasks: Number(form.capacity_tasks || 8),
    };
    try {
      if (editing) await api.updatePerson(editing.id, payload);
      else await api.createPerson(projectId, payload);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    }
  }

  if (!projectId) return <EmptyState title="プロジェクトを選択してください" />;
  if (loading && people.length === 0) return <Loading />;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">担当者管理</h1>
          <p className="text-sm text-ink-500">担当件数・期限超過・高リスクTaskから負荷状況を可視化</p>
        </div>
        <button className="btn-primary" onClick={() => openForm(null)}>
          ＋ 担当者を追加
        </button>
      </header>

      {error && <ErrorBanner message={error} />}

      {people.length === 0 ? (
        <EmptyState title="担当者が登録されていません" hint="Excel Importでも担当者は自動登録されます。" />
      ) : (
        <div className="space-y-3">
          {people.map((person) => {
            const owned = tasks.filter((task) => task.owner_id === person.id);
            const openTasks = owned.filter((task) => task.status !== "done" && task.status !== "cancelled");
            return (
              <Card key={person.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-base font-semibold">{person.name}</h2>
                      {person.role && <span className="text-xs text-ink-500">{person.role}</span>}
                      <Badge className={loadClass(person.load_level)}>
                        {LOAD_LABELS[person.load_level]}（負荷率 {person.load_ratio.toFixed(2)}）
                      </Badge>
                    </div>
                    <p className="mt-1 text-xs text-ink-500">
                      capacity {person.capacity_tasks} 件 / 平均進捗 {person.average_progress.toFixed(0)}%
                      {person.email && ` / ${person.email}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <button className="text-xs text-ink-500 hover:text-ink-900" onClick={() => openForm(person)}>
                      編集
                    </button>
                    <button
                      className="text-xs text-rose-500 hover:text-rose-700"
                      onClick={async () => {
                        if (!window.confirm(`${person.name} を削除しますか？（担当Taskは未設定になります）`)) return;
                        await api.deletePerson(person.id);
                        await load();
                      }}
                    >
                      削除
                    </button>
                  </div>
                </div>

                <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                  <Metric label="担当Task" value={person.assigned_task_count} />
                  <Metric label="未完了" value={person.open_task_count} />
                  <Metric label="期限超過" value={person.overdue_task_count} tone={person.overdue_task_count ? "danger" : "default"} />
                  <Metric label="高リスク" value={person.high_risk_task_count} tone={person.high_risk_task_count ? "warn" : "default"} />
                  <Metric label="高優先度" value={person.critical_task_count} />
                  <Metric label="今週期限" value={person.due_this_week_count} />
                </div>

                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs text-ink-500">
                    <span>負荷（未完了Task / capacity）</span>
                    <span className="tabular-nums">
                      {person.open_task_count} / {person.capacity_tasks}
                    </span>
                  </div>
                  <div className="mt-1">
                    <ProgressBar value={Math.min(100, person.load_ratio * 100)} expected={100} />
                  </div>
                </div>

                <button
                  className="mt-3 text-xs font-medium text-ink-500 hover:text-ink-900"
                  onClick={() => setExpanded(expanded === person.id ? null : person.id)}
                >
                  {expanded === person.id ? "▾" : "▸"} 担当Task {openTasks.length} 件を表示
                </button>
                {expanded === person.id && (
                  <ul className="mt-2 space-y-1">
                    {openTasks.length === 0 && <li className="text-xs text-ink-400">未完了Taskはありません。</li>}
                    {openTasks.map((task) => (
                      <li key={task.id} className="flex items-center gap-2 rounded border border-slate-100 px-3 py-2 text-xs">
                        <span className={`inline-block h-2 w-2 shrink-0 rounded-full ${riskClass(task.risk_score)}`} />
                        <span className="flex-1 truncate">{task.title}</span>
                        <span className="tabular-nums text-ink-400">{formatFullDate(task.planned_end)}</span>
                        <span className="w-10 text-right tabular-nums text-ink-400">{task.progress.toFixed(0)}%</span>
                        {task.is_overdue && (
                          <Badge className="border-rose-200 bg-rose-50 text-rose-700">{task.days_overdue}日超過</Badge>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {showForm && (
        <Modal title={editing ? `担当者編集: ${editing.name}` : "担当者を追加"} onClose={() => setShowForm(false)}>
          <form className="space-y-4" onSubmit={submit}>
            <Field label="氏名 *">
              <input
                className="input"
                required
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </Field>
            <div className="grid gap-3 md:grid-cols-3">
              <Field label="Role">
                <input
                  className="input"
                  value={form.role}
                  onChange={(event) => setForm({ ...form, role: event.target.value })}
                />
              </Field>
              <Field label="メール">
                <input
                  className="input"
                  value={form.email}
                  onChange={(event) => setForm({ ...form, email: event.target.value })}
                />
              </Field>
              <Field label="同時担当可能Task数">
                <input
                  type="number"
                  min={1}
                  className="input"
                  value={form.capacity_tasks}
                  onChange={(event) => setForm({ ...form, capacity_tasks: event.target.value })}
                />
              </Field>
            </div>
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

function Metric({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "warn" | "danger";
}) {
  const toneClass = tone === "danger" ? "text-rose-600" : tone === "warn" ? "text-amber-600" : "text-ink-900";
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <p className="text-[11px] text-ink-500">{label}</p>
      <p className={`text-lg font-semibold tabular-nums ${toneClass}`}>{value}</p>
    </div>
  );
}
