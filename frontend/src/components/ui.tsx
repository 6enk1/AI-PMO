"use client";

import { useEffect } from "react";

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="card-header">
          <h2 className="card-title">{title}</h2>
          {action}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  tone?: "default" | "warn" | "danger" | "good";
}) {
  const toneClass =
    tone === "danger"
      ? "text-rose-600"
      : tone === "warn"
        ? "text-amber-600"
        : tone === "good"
          ? "text-emerald-600"
          : "text-ink-900";
  return (
    <div className="card px-4 py-3">
      <p className="text-xs font-medium text-ink-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${toneClass}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-ink-400">{hint}</p>}
    </div>
  );
}

export function Badge({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <span className={`badge ${className}`}>{children}</span>;
}

export function ProgressBar({ value, expected }: { value: number; expected?: number }) {
  return (
    <div className="relative h-2 w-full overflow-hidden rounded-full bg-slate-200">
      <div
        className="h-full rounded-full bg-sky-500"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
      {expected !== undefined && (
        <div
          className="absolute top-0 h-full w-0.5 bg-ink-900/60"
          style={{ left: `${Math.min(100, Math.max(0, expected))}%` }}
          title={`想定進捗 ${expected.toFixed(0)}%`}
        />
      )}
    </div>
  );
}

export function Loading({ label = "読み込み中…" }: { label?: string }) {
  return <p className="py-10 text-center text-sm text-ink-400">{label}</p>;
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {message}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 py-10 text-center">
      <p className="text-sm font-medium text-ink-600">{title}</p>
      {hint && <p className="mt-1 text-xs text-ink-400">{hint}</p>}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-900/40 p-4">
      <div className={`mt-10 w-full ${wide ? "max-w-4xl" : "max-w-2xl"} rounded-xl bg-white shadow-xl`}>
        <header className="flex items-center justify-between border-b border-slate-100 px-5 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          <button className="text-ink-400 hover:text-ink-700" onClick={onClose} aria-label="閉じる">
            ✕
          </button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
