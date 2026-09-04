"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { PRIORITY_LABELS, STATUS_LABELS } from "@/lib/format";
import type { Person, Task, TaskPriority, TaskStatus } from "@/lib/types";
import { Field, Modal } from "./ui";

interface Props {
  projectId: number;
  task: Task | null;
  tasks: Task[];
  people: Person[];
  onClose: () => void;
  onSaved: () => void;
}

export function TaskFormModal({ projectId, task, tasks, people, onClose, onSaved }: Props) {
  const [form, setForm] = useState({
    title: task?.title ?? "",
    code: task?.code ?? "",
    description: task?.description ?? "",
    parent_task_id: task?.parent_task_id ? String(task.parent_task_id) : "",
    owner_id: task?.owner_id ? String(task.owner_id) : "",
    planned_start: task?.planned_start ?? "",
    planned_end: task?.planned_end ?? "",
    actual_start: task?.actual_start ?? "",
    actual_end: task?.actual_end ?? "",
    progress: String(task?.progress ?? 0),
    status: (task?.status ?? "not_started") as TaskStatus,
    priority: (task?.priority ?? "medium") as TaskPriority,
    estimated_hours: task?.estimated_hours != null ? String(task.estimated_hours) : "",
    notes: task?.notes ?? "",
  });
  const [predecessors, setPredecessors] = useState<number[]>(task?.predecessor_task_ids ?? []);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const payload = {
      title: form.title,
      code: form.code || null,
      description: form.description || null,
      parent_task_id: form.parent_task_id ? Number(form.parent_task_id) : null,
      owner_id: form.owner_id ? Number(form.owner_id) : null,
      planned_start: form.planned_start || null,
      planned_end: form.planned_end || null,
      actual_start: form.actual_start || null,
      actual_end: form.actual_end || null,
      progress: Number(form.progress || 0),
      status: form.status,
      priority: form.priority,
      estimated_hours: form.estimated_hours ? Number(form.estimated_hours) : null,
      notes: form.notes || null,
      predecessor_task_ids: predecessors,
    };
    try {
      if (task) {
        await api.updateTask(task.id, payload);
      } else {
        await api.createTask(projectId, payload);
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存に失敗しました");
    } finally {
      setSaving(false);
    }
  }

  const selectable = tasks.filter((candidate) => candidate.id !== task?.id);

  return (
    <Modal title={task ? `Task編集: ${task.title}` : "Task新規作成"} onClose={onClose} wide>
      <form className="space-y-4" onSubmit={submit}>
        {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}

        <div className="grid gap-3 md:grid-cols-4">
          <Field label="Task ID" className="md:col-span-1">
            <input
              className="input"
              placeholder="自動採番"
              value={form.code}
              onChange={(event) => setForm({ ...form, code: event.target.value })}
            />
          </Field>
          <Field label="タスク名 *" className="md:col-span-3">
            <input
              className="input"
              required
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
            />
          </Field>
        </div>

        <Field label="説明">
          <textarea
            className="input"
            rows={2}
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
        </Field>

        <div className="grid gap-3 md:grid-cols-3">
          <Field label="親タスク">
            <select
              className="input"
              value={form.parent_task_id}
              onChange={(event) => setForm({ ...form, parent_task_id: event.target.value })}
            >
              <option value="">（なし）</option>
              {selectable.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {[...candidate.path_titles, candidate.title].join(" / ")}
                </option>
              ))}
            </select>
          </Field>
          <Field label="担当者">
            <select
              className="input"
              value={form.owner_id}
              onChange={(event) => setForm({ ...form, owner_id: event.target.value })}
            >
              <option value="">（未設定）</option>
              {people.map((person) => (
                <option key={person.id} value={person.id}>
                  {person.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="工数（人日/時間）">
            <input
              className="input"
              type="number"
              step="0.5"
              value={form.estimated_hours}
              onChange={(event) => setForm({ ...form, estimated_hours: event.target.value })}
            />
          </Field>
        </div>

        <div className="grid gap-3 md:grid-cols-4">
          <Field label="開始予定日">
            <input
              type="date"
              className="input"
              value={form.planned_start}
              onChange={(event) => setForm({ ...form, planned_start: event.target.value })}
            />
          </Field>
          <Field label="終了予定日">
            <input
              type="date"
              className="input"
              value={form.planned_end}
              onChange={(event) => setForm({ ...form, planned_end: event.target.value })}
            />
          </Field>
          <Field label="実績開始日">
            <input
              type="date"
              className="input"
              value={form.actual_start}
              onChange={(event) => setForm({ ...form, actual_start: event.target.value })}
            />
          </Field>
          <Field label="実績終了日">
            <input
              type="date"
              className="input"
              value={form.actual_end}
              onChange={(event) => setForm({ ...form, actual_end: event.target.value })}
            />
          </Field>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <Field label="進捗率 (%)">
            <input
              type="number"
              min={0}
              max={100}
              className="input"
              value={form.progress}
              onChange={(event) => setForm({ ...form, progress: event.target.value })}
            />
          </Field>
          <Field label="Status">
            <select
              className="input"
              value={form.status}
              onChange={(event) => setForm({ ...form, status: event.target.value as TaskStatus })}
            >
              {Object.entries(STATUS_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Priority">
            <select
              className="input"
              value={form.priority}
              onChange={(event) => setForm({ ...form, priority: event.target.value as TaskPriority })}
            >
              {Object.entries(PRIORITY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="依存タスク（先行タスク・Ctrlキーで複数選択）">
          <select
            multiple
            className="input h-28"
            value={predecessors.map(String)}
            onChange={(event) =>
              setPredecessors(Array.from(event.target.selectedOptions).map((option) => Number(option.value)))
            }
          >
            {selectable.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.code ? `${candidate.code} ` : ""}
                {candidate.title}
              </option>
            ))}
          </select>
        </Field>

        <Field label="備考">
          <textarea
            className="input"
            rows={2}
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </Field>

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            キャンセル
          </button>
          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
