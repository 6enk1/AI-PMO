"use client";

import { useCallback, useEffect, useState } from "react";
import { FindingCard } from "@/components/FindingCard";
import { useProjects } from "@/components/ProjectProvider";
import { Badge, Card, EmptyState, ErrorBanner, Loading, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { formatFullDate, riskClass } from "@/lib/format";
import type { AIPMOResponse, TaskRisk } from "@/lib/types";

const TABS = [
  { key: "hidden", label: "Hidden Issues" },
  { key: "risks", label: "Delay Risks" },
  { key: "actions", label: "Recommended Actions" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function AiPmoPage() {
  const { projectId } = useProjects();
  const [data, setData] = useState<AIPMOResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("hidden");
  const [useLlm, setUseLlm] = useState(true);

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      setData(await api.aiPmo(projectId, useLlm));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析に失敗しました");
    } finally {
      setLoading(false);
    }
  }, [projectId, useLlm]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!projectId) return <EmptyState title="プロジェクトを選択してください" />;
  if (loading && !data) return <Loading label="構造化分析とAI推論を実行中…" />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">AI PMO</h1>
          <p className="text-sm text-ink-500">
            Structured Analysis → LLM Reasoning → Recommendation ／ 基準日 {data.as_of}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-ink-600">
            <input type="checkbox" checked={useLlm} onChange={(event) => setUseLlm(event.target.checked)} />
            LLM推論を使う
          </label>
          <button className="btn-secondary" onClick={() => void load()} disabled={loading}>
            {loading ? "分析中…" : "再分析"}
          </button>
        </div>
      </header>

      <div className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-xs text-ink-500">
        {data.llm_used ? (
          <span>
            <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">LLM推論あり</Badge>{" "}
            {data.llm_note} — 数値・根拠はPython側の構造化分析で確定しており、LLMは説明と推奨の並び替えのみを担当します。
          </span>
        ) : (
          <span>
            <Badge className="border-slate-200 bg-slate-100 text-ink-600">ルールベース</Badge> {data.llm_note}
          </span>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="Hidden Issue" value={data.hidden_issues.length} tone={data.hidden_issues.length ? "warn" : "good"} />
        <StatCard label="遅延リスクTask" value={data.delay_risks.length} tone={data.delay_risks.length ? "warn" : "good"} />
        <StatCard label="打ち手提案" value={data.delay_actions.length} />
      </div>

      <nav className="flex gap-2 border-b border-slate-200">
        {TABS.map((item) => (
          <button
            key={item.key}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition ${
              tab === item.key
                ? "border-ink-900 text-ink-900"
                : "border-transparent text-ink-400 hover:text-ink-700"
            }`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "hidden" && (
        <section className="space-y-3">
          <p className="text-sm text-ink-500">
            Issueとして登録されていないが、プロジェクトデータ上で異常・懸念が検出された項目です。
          </p>
          {data.hidden_issues.length === 0 ? (
            <EmptyState title="Hidden Issueは検出されませんでした" />
          ) : (
            data.hidden_issues.map((finding) => <FindingCard key={finding.id} finding={finding} />)
          )}
        </section>
      )}

      {tab === "risks" && (
        <section className="space-y-3">
          <p className="text-sm text-ink-500">
            まだ遅延していないTaskも含め、将来遅延する可能性をRisk Score（0〜100）で評価しています。
          </p>
          {data.delay_risks.length === 0 ? (
            <EmptyState title="高リスクTaskはありません" />
          ) : (
            data.delay_risks.map((risk) => <RiskCard key={risk.task_id} risk={risk} />)
          )}
        </section>
      )}

      {tab === "actions" && (
        <section className="space-y-3">
          <p className="text-sm text-ink-500">
            遅延中・高リスクのTaskについて、推定原因と打ち手候補、AI推奨アクションとその理由を提示します。
          </p>
          {data.delay_actions.length === 0 ? (
            <EmptyState title="打ち手が必要なTaskはありません" />
          ) : (
            data.delay_actions.map((finding) => <FindingCard key={finding.id} finding={finding} />)
          )}
        </section>
      )}
    </div>
  );
}

function RiskCard({ risk }: { risk: TaskRisk }) {
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          {risk.task_category && <p className="text-xs text-ink-400">{risk.task_category}</p>}
          <h3 className="text-sm font-semibold">
            {risk.task_code && <span className="mr-2 text-ink-400">{risk.task_code}</span>}
            {risk.task_title}
          </h3>
          <p className="mt-1 text-xs text-ink-500">
            担当 {risk.owner_name ?? "未設定"} ／ 期限 {formatFullDate(risk.planned_end)} ／ 進捗{" "}
            {risk.progress.toFixed(0)}%
            {risk.days_overdue > 0
              ? ` ／ ${risk.days_overdue}日超過`
              : risk.days_to_due != null
                ? ` ／ 残り${risk.days_to_due}日`
                : ""}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-ink-500">Risk Score</p>
          <p className="text-3xl font-bold tabular-nums">{risk.risk_score.toFixed(0)}</p>
          <div className="mt-1 h-1.5 w-28 overflow-hidden rounded-full bg-slate-200">
            <div className={`h-full ${riskClass(risk.risk_score)}`} style={{ width: `${risk.risk_score}%` }} />
          </div>
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs font-semibold text-ink-500">リスク理由 / Evidence</p>
          <ul className="mt-1 space-y-1">
            {risk.factors.map((factor) => (
              <li key={factor.key} className="flex gap-2 text-xs text-ink-700">
                <span className="w-10 shrink-0 text-right font-semibold tabular-nums text-rose-600">
                  +{factor.points.toFixed(0)}
                </span>
                <span>
                  <span className="font-medium">{factor.label}</span>: {factor.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs font-semibold text-ink-500">想定影響</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-700">{risk.impact}</p>
          {risk.recommended_action && (
            <>
              <p className="mt-2 text-xs font-semibold text-ink-500">推奨Action</p>
              <p className="mt-1 text-xs font-medium text-emerald-800">{risk.recommended_action}</p>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}
