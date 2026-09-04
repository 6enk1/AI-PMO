import type { Severity, TaskPriority, TaskStatus } from "./types";

export const STATUS_LABELS: Record<TaskStatus, string> = {
  not_started: "未着手",
  in_progress: "進行中",
  blocked: "保留",
  done: "完了",
  cancelled: "中止",
};

export const PRIORITY_LABELS: Record<TaskPriority, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "最優先",
};

export const ISSUE_STATUS_LABELS: Record<string, string> = {
  open: "未対応",
  in_progress: "対応中",
  resolved: "解決済",
  closed: "クローズ",
};

export const SEVERITY_LABELS: Record<Severity, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "重大",
};

export function severityClass(severity: string): string {
  switch (severity) {
    case "critical":
      return "bg-rose-100 text-rose-800 border-rose-200";
    case "high":
      return "bg-orange-100 text-orange-800 border-orange-200";
    case "medium":
      return "bg-amber-100 text-amber-800 border-amber-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

export function statusClass(status: string): string {
  switch (status) {
    case "done":
      return "bg-emerald-100 text-emerald-800 border-emerald-200";
    case "in_progress":
      return "bg-sky-100 text-sky-800 border-sky-200";
    case "blocked":
      return "bg-rose-100 text-rose-800 border-rose-200";
    case "cancelled":
      return "bg-slate-100 text-slate-500 border-slate-200";
    default:
      return "bg-slate-100 text-slate-700 border-slate-200";
  }
}

export function riskClass(score: number): string {
  if (score >= 80) return "bg-rose-600";
  if (score >= 60) return "bg-orange-500";
  if (score >= 35) return "bg-amber-400";
  return "bg-emerald-500";
}

export function healthClass(score: number): string {
  if (score >= 80) return "text-emerald-600";
  if (score >= 60) return "text-amber-500";
  if (score >= 40) return "text-orange-500";
  return "text-rose-600";
}

export function loadClass(level: string): string {
  switch (level) {
    case "overloaded":
      return "bg-rose-100 text-rose-800 border-rose-200";
    case "high":
      return "bg-amber-100 text-amber-800 border-amber-200";
    case "light":
      return "bg-slate-100 text-slate-600 border-slate-200";
    default:
      return "bg-emerald-100 text-emerald-800 border-emerald-200";
  }
}

export const LOAD_LABELS: Record<string, string> = {
  overloaded: "過負荷",
  high: "高負荷",
  normal: "適正",
  light: "余裕",
};

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

export function formatFullDate(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(0, 10);
}

export function daysBetween(from: string, to: string): number {
  return Math.round((new Date(to).getTime() - new Date(from).getTime()) / 86400000);
}

export function todayISO(): string {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}
