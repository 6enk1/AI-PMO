"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useProjects } from "./ProjectProvider";
import { Field, Modal } from "./ui";

const NAV = [
  { href: "/", label: "Command Center", icon: "◎" },
  { href: "/tasks", label: "Task管理", icon: "☰" },
  { href: "/schedule", label: "Schedule", icon: "▤" },
  { href: "/issues", label: "Issue管理", icon: "!" },
  { href: "/people", label: "担当者", icon: "☺" },
  { href: "/ai-pmo", label: "AI PMO", icon: "✦" },
  { href: "/import", label: "Excel Import", icon: "↥" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { projects, project, projectId, selectProject, reloadProjects } = useProjects();
  const [creating, setCreating] = useState(false);
  const [navOpen, setNavOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", start_date: "", end_date: "" });
  const [error, setError] = useState<string | null>(null);

  // 画面遷移したらモバイルのドロワーは閉じる
  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    try {
      const created = await api.createProject({
        name: form.name,
        description: form.description || null,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
      });
      await reloadProjects();
      selectProject(created.id);
      setCreating(false);
      setForm({ name: "", description: "", start_date: "", end_date: "" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "作成に失敗しました");
    }
  }

  const current = NAV.find((item) => item.href === pathname);

  return (
    <div className="flex min-h-screen">
      {/* モバイル用のヘッダー（lg未満で表示） */}
      <header className="fixed inset-x-0 top-0 z-40 flex h-14 items-center gap-2 border-b border-slate-200 bg-white px-3 lg:hidden">
        <button
          className="flex h-11 w-11 items-center justify-center rounded-lg text-xl text-ink-700 hover:bg-slate-100"
          onClick={() => setNavOpen(true)}
          aria-label="メニューを開く"
        >
          ☰
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold leading-tight">{current?.label ?? "AI PMO"}</p>
          <p className="truncate text-[11px] leading-tight text-ink-400">{project?.name ?? "プロジェクト未選択"}</p>
        </div>
      </header>

      {navOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink-900/40 lg:hidden"
          onClick={() => setNavOpen(false)}
          aria-hidden
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white transition-transform lg:static lg:translate-x-0 ${
          navOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-start justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <p className="text-lg font-semibold tracking-tight">AI PMO</p>
            <p className="text-xs text-ink-400">Project Management OS v0.1</p>
          </div>
          <button
            className="-mr-2 flex h-11 w-11 items-center justify-center text-ink-400 lg:hidden"
            onClick={() => setNavOpen(false)}
            aria-label="メニューを閉じる"
          >
            ✕
          </button>
        </div>

        <div className="border-b border-slate-100 px-4 py-3">
          <span className="label">プロジェクト</span>
          <select
            className="input"
            value={projectId ?? ""}
            onChange={(event) => selectProject(Number(event.target.value))}
          >
            {projects.length === 0 && <option value="">（未作成）</option>}
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          <button className="btn-secondary mt-2 min-h-[44px] w-full" onClick={() => setCreating(true)}>
            ＋ 新規プロジェクト
          </button>
        </div>

        <nav className="flex-1 space-y-1 p-3">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex min-h-[44px] items-center gap-2 rounded-lg px-3 py-2 text-sm transition ${
                  active ? "bg-ink-900 text-white" : "text-ink-700 hover:bg-slate-100"
                }`}
              >
                <span className="w-4 text-center text-xs opacity-70">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <p className="px-5 py-4 text-[11px] leading-relaxed text-ink-400">
          Observe → Detect → Diagnose → Predict → Recommend
        </p>
      </aside>

      <main className="min-w-0 flex-1 overflow-x-auto pt-14 lg:pt-0">
        <div className="mx-auto max-w-[1400px] p-4 sm:p-6">{children}</div>
      </main>

      {creating && (
        <Modal title="新規プロジェクト" onClose={() => setCreating(false)}>
          <form className="space-y-4" onSubmit={createProject}>
            {error && <p className="text-sm text-rose-600">{error}</p>}
            <Field label="プロジェクト名 *">
              <input
                className="input"
                required
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </Field>
            <Field label="説明">
              <textarea
                className="input"
                rows={3}
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="開始日">
                <input
                  type="date"
                  className="input"
                  value={form.start_date}
                  onChange={(event) => setForm({ ...form, start_date: event.target.value })}
                />
              </Field>
              <Field label="終了日">
                <input
                  type="date"
                  className="input"
                  value={form.end_date}
                  onChange={(event) => setForm({ ...form, end_date: event.target.value })}
                />
              </Field>
            </div>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={() => setCreating(false)}>
                キャンセル
              </button>
              <button type="submit" className="btn-primary">
                作成
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
