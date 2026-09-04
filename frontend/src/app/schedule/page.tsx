"use client";

import { useCallback, useEffect, useState } from "react";
import { GanttChart } from "@/components/GanttChart";
import { useProjects } from "@/components/ProjectProvider";
import { TaskFormModal } from "@/components/TaskFormModal";
import { Badge, Card, EmptyState, ErrorBanner, Field, Loading, Modal, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { formatFullDate } from "@/lib/format";
import type { Milestone, Person, Task } from "@/lib/types";

export default function SchedulePage() {
  const { projectId } = useProjects();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Task | null>(null);
  const [showMilestoneForm, setShowMilestoneForm] = useState(false);
  const [milestoneForm, setMilestoneForm] = useState({ title: "", due_date: "" });
  const [onlyDelayed, setOnlyDelayed] = useState(false);
  const [dayWidth, setDayWidth] = useState(22);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [taskList, milestoneList, peopleList] = await Promise.all([
        api.listTasks(projectId, { sort: "planned_start", order: "asc" }),
        api.listMilestones(projectId),
        api.listPeople(projectId),
      ]);
      setTasks(taskList);
      setMilestones(milestoneList);
      setPeople(peopleList);
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

  async function addMilestone(event: React.FormEvent) {
    event.preventDefault();
    if (!projectId) return;
    await api.createMilestone(projectId, {
      title: milestoneForm.title,
      due_date: milestoneForm.due_date || null,
    });
    setMilestoneForm({ title: "", due_date: "" });
    setShowMilestoneForm(false);
    await load();
  }

  if (!projectId) return <EmptyState title="プロジェクトを選択してください" />;
  if (loading && tasks.length === 0) return <Loading />;

  const visible = onlyDelayed ? tasks.filter((task) => task.is_overdue || task.progress_gap > 10) : tasks;
  const delayed = tasks.filter((task) => task.is_overdue);
  const criticalPath = tasks.filter((task) => task.is_critical_path && task.status !== "done");
  const variance = tasks
    .filter((task) => task.actual_end && task.planned_end)
    .map((task) => Math.round((new Date(task.actual_end!).getTime() - new Date(task.planned_end!).getTime()) / 86400000));
  const averageVariance = variance.length
    ? (variance.reduce((sum, value) => sum + value, 0) / variance.length).toFixed(1)
    : "0.0";

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Schedule</h1>
          <p className="text-sm text-ink-500">ガントチャート / 依存関係 / マイルストーン</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            className={`badge ${onlyDelayed ? "border-rose-500 bg-rose-500 text-white" : "border-slate-200 bg-white text-ink-600"}`}
            onClick={() => setOnlyDelayed(!onlyDelayed)}
          >
            遅延Taskのみ
          </button>
          <select
            className="input w-28"
            value={dayWidth}
            onChange={(event) => setDayWidth(Number(event.target.value))}
          >
            <option value={12}>縮小</option>
            <option value={22}>標準</option>
            <option value={36}>拡大</option>
          </select>
          <button className="btn-secondary" onClick={() => setShowMilestoneForm(true)}>
            ＋ マイルストーン
          </button>
        </div>
      </header>

      {error && <ErrorBanner message={error} />}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="対象Task" value={tasks.length} hint={`表示 ${visible.length} 件`} />
        <StatCard label="遅延Task" value={delayed.length} tone={delayed.length ? "danger" : "good"} />
        <StatCard label="クリティカルパス上" value={criticalPath.length} hint="Float 0 日" />
        <StatCard label="予実差（完了Task平均）" value={`${averageVariance}日`} tone={Number(averageVariance) > 0 ? "warn" : "good"} />
      </div>

      {visible.length === 0 ? (
        <EmptyState title="表示できるTaskがありません" />
      ) : (
        <>
          <GanttChart tasks={visible} milestones={milestones} dayWidth={dayWidth} onSelect={setEditing} />
          <div className="flex flex-wrap gap-3 text-xs text-ink-500">
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-6 rounded border border-sky-300 bg-sky-100" />予定
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-6 rounded bg-sky-500" />進捗
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-6 rounded border border-rose-400 bg-rose-200" />期限超過
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-6 rounded border border-indigo-400 bg-indigo-100" />クリティカルパス
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-1 w-6 rounded bg-ink-500/60" />実績
            </span>
            <span className="flex items-center gap-1">
              <span className="inline-block h-3 w-0.5 bg-rose-500" />本日
            </span>
          </div>
        </>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="遅延中のTask">
          {delayed.length === 0 ? (
            <p className="text-sm text-emerald-600">期限超過のTaskはありません。</p>
          ) : (
            <ul className="space-y-2">
              {delayed.map((task) => (
                <li key={task.id} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 p-3">
                  <div className="min-w-0">
                    {task.category && (
                      <p className="truncate text-[11px] text-ink-400">{task.category}</p>
                    )}
                    <p className="truncate text-sm font-medium">{task.title}</p>
                    <p className="text-xs text-ink-500">
                      予定 {formatFullDate(task.planned_end)} / 担当 {task.owner_name ?? "未設定"} / 進捗{" "}
                      {task.progress.toFixed(0)}%
                    </p>
                  </div>
                  <Badge className="border-rose-200 bg-rose-50 text-rose-700">{task.days_overdue}日超過</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="マイルストーン">
          {milestones.length === 0 ? (
            <EmptyState title="マイルストーンが未登録です" />
          ) : (
            <ul className="space-y-2">
              {milestones.map((milestone) => (
                <li key={milestone.id} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 p-3">
                  <div>
                    <p className="text-sm font-medium">{milestone.title}</p>
                    <p className="text-xs text-ink-500">
                      {formatFullDate(milestone.due_date)}
                      {milestone.days_remaining != null && ` / 残り ${milestone.days_remaining} 日`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    {milestone.at_risk && (
                      <Badge className="border-rose-200 bg-rose-50 text-rose-700">未達リスク</Badge>
                    )}
                    <button
                      className="text-xs text-rose-500 hover:text-rose-700"
                      onClick={async () => {
                        if (!window.confirm(`「${milestone.title}」を削除しますか？`)) return;
                        await api.deleteMilestone(projectId, milestone.id);
                        await load();
                      }}
                    >
                      削除
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {editing && (
        <TaskFormModal
          projectId={projectId}
          task={editing}
          tasks={tasks}
          people={people}
          onClose={() => setEditing(null)}
          onSaved={() => void load()}
        />
      )}

      {showMilestoneForm && (
        <Modal title="マイルストーン追加" onClose={() => setShowMilestoneForm(false)}>
          <form className="space-y-4" onSubmit={addMilestone}>
            <Field label="名称 *">
              <input
                className="input"
                required
                value={milestoneForm.title}
                onChange={(event) => setMilestoneForm({ ...milestoneForm, title: event.target.value })}
              />
            </Field>
            <Field label="期日">
              <input
                type="date"
                className="input"
                value={milestoneForm.due_date}
                onChange={(event) => setMilestoneForm({ ...milestoneForm, due_date: event.target.value })}
              />
            </Field>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setShowMilestoneForm(false)}>
                キャンセル
              </button>
              <button type="submit" className="btn-primary">
                追加
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
