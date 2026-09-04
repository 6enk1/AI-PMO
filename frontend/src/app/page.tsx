"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useProjects } from "@/components/ProjectProvider";
import { Card, EmptyState, ErrorBanner, Loading, ProgressBar, StatCard, Badge } from "@/components/ui";
import { api } from "@/lib/api";
import { formatFullDate, healthClass, severityClass } from "@/lib/format";
import type { Dashboard } from "@/lib/types";

export default function CommandCenterPage() {
  const { projectId, project, loading: projectsLoading } = useProjects();
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      setData(await api.dashboard(projectId));
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

  if (projectsLoading) return <Loading />;
  if (!projectId) {
    return (
      <EmptyState
        title="プロジェクトがありません"
        hint="左のメニューから新規プロジェクトを作成するか、Excel ImportでWBSを取り込んでください。"
      />
    );
  }
  if (error) return <ErrorBanner message={error} />;
  if (loading && !data) return <Loading />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Project Command Center</h1>
          <p className="text-sm text-ink-500">
            {project?.name} ／ 基準日 {data.as_of}
            {project?.start_date && ` ／ 期間 ${formatFullDate(project.start_date)} 〜 ${formatFullDate(project.end_date)}`}
          </p>
        </div>
        <button className="btn-secondary" onClick={() => void load()}>
          再計算
        </button>
      </header>

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="card p-5 lg:col-span-1">
          <p className="text-xs font-medium text-ink-500">Project Health Score</p>
          <p className={`mt-1 text-5xl font-bold tabular-nums ${healthClass(data.health_score)}`}>
            {data.health_score.toFixed(0)}
          </p>
          <p className="text-sm font-medium text-ink-600">{data.health_label}</p>
          <div className="mt-4 space-y-1.5">
            {data.health_breakdown.length === 0 && (
              <p className="text-xs text-emerald-600">減点要因はありません。</p>
            )}
            {data.health_breakdown.map((item) => (
              <div key={item.key} className="text-xs">
                <div className="flex justify-between">
                  <span className="font-medium text-ink-700">{item.label}</span>
                  <span className="tabular-nums text-rose-600">-{item.penalty}</span>
                </div>
                <p className="text-ink-400">{item.detail}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:col-span-3 lg:grid-cols-3">
          <StatCard label="未完了Task" value={data.open_tasks} hint={`全 ${data.total_tasks} 件 / 完了 ${data.done_tasks} 件`} />
          <StatCard
            label="期限超過Task"
            value={data.overdue_tasks}
            tone={data.overdue_tasks > 0 ? "danger" : "good"}
            hint="予定終了日を過ぎた未完了Task"
          />
          <StatCard
            label="High Risk Task"
            value={data.high_risk_tasks}
            tone={data.high_risk_tasks > 0 ? "warn" : "good"}
            hint="Risk Score 60以上"
          />
          <StatCard
            label="Hidden Issue"
            value={data.hidden_issue_count}
            tone={data.hidden_issue_count > 0 ? "warn" : "good"}
            hint="未登録だが検出された問題"
          />
          <StatCard
            label="Open Issue"
            value={data.open_issue_count}
            tone={data.critical_issue_count > 0 ? "danger" : "default"}
            hint={`うち高Severity ${data.critical_issue_count} 件`}
          />
          <StatCard
            label="次回マイルストーン"
            value={
              data.next_milestone
                ? `${data.next_milestone.days_remaining ?? "—"}日`
                : "—"
            }
            tone={data.next_milestone?.at_risk ? "danger" : "default"}
            hint={data.next_milestone ? `${data.next_milestone.title}（${formatFullDate(data.next_milestone.due_date)}）` : "未設定"}
          />
          <div className="card px-4 py-3 sm:col-span-2 lg:col-span-3">
            <div className="flex items-center justify-between text-xs text-ink-500">
              <span>平均進捗率</span>
              <span className="tabular-nums">
                {data.average_progress.toFixed(0)}% ／ Owner未設定 {data.unassigned_tasks} 件 ／ 平均遅延{" "}
                {data.schedule_variance_days.toFixed(1)} 日
              </span>
            </div>
            <div className="mt-2">
              <ProgressBar value={data.average_progress} />
            </div>
          </div>
        </div>
      </div>

      <Card
        title="今日見るべき項目"
        action={
          <Link href="/ai-pmo" className="text-xs font-medium text-ink-500 hover:text-ink-900">
            AI PMOで詳細を見る →
          </Link>
        }
      >
        {data.focus_items.length === 0 ? (
          <EmptyState title="対応が必要な項目はありません" hint="期限超過・高リスク・重要Issueはいずれも検出されていません。" />
        ) : (
          <ol className="space-y-2">
            {data.focus_items.map((item, index) => (
              <li key={`${item.kind}-${item.ref_id}-${index}`} className="flex items-start gap-3 rounded-lg border border-slate-200 p-3">
                <span className="mt-0.5 w-5 text-center text-xs font-semibold text-ink-400">{index + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={severityClass(item.severity)}>{item.severity.toUpperCase()}</Badge>
                    <p className="text-sm font-medium text-ink-900">{item.title}</p>
                  </div>
                  <p className="mt-0.5 text-xs text-ink-500">{item.detail}</p>
                </div>
                {item.link && (
                  <Link href={item.link} className="shrink-0 text-xs font-medium text-ink-500 hover:text-ink-900">
                    開く →
                  </Link>
                )}
              </li>
            ))}
          </ol>
        )}
      </Card>

      <Card title="マイルストーン">
        {data.milestones.length === 0 ? (
          <EmptyState title="マイルストーンが未登録です" hint="Schedule画面から追加できます。" />
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="th">マイルストーン</th>
                <th className="th">期日</th>
                <th className="th">残日数</th>
                <th className="th">状態</th>
              </tr>
            </thead>
            <tbody>
              {data.milestones.map((milestone) => (
                <tr key={milestone.id} className="border-b border-slate-50">
                  <td className="td font-medium">{milestone.title}</td>
                  <td className="td tabular-nums">{formatFullDate(milestone.due_date)}</td>
                  <td className="td tabular-nums">{milestone.days_remaining ?? "—"}</td>
                  <td className="td">
                    {milestone.status === "achieved" ? (
                      <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">達成</Badge>
                    ) : milestone.at_risk ? (
                      <Badge className="border-rose-200 bg-rose-50 text-rose-700">未達リスク</Badge>
                    ) : (
                      <Badge className="border-slate-200 bg-slate-50 text-ink-600">予定通り</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
