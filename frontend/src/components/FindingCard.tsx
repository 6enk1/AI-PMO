"use client";

import { useState } from "react";
import { SEVERITY_LABELS, severityClass } from "@/lib/format";
import type { Finding } from "@/lib/types";
import { Badge } from "./ui";

/**
 * Renders one AI PMO finding. Evidence and the reason behind the recommended
 * action are always shown - a recommendation without grounds is not allowed.
 */
export function FindingCard({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false);

  return (
    <article className="card p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className={severityClass(finding.severity)}>
              Severity {SEVERITY_LABELS[finding.severity]}
            </Badge>
            {finding.risk_score != null && (
              <Badge className="border-slate-200 bg-slate-100 text-ink-700">
                Risk {finding.risk_score.toFixed(0)}
              </Badge>
            )}
            <Badge className="border-slate-200 bg-white text-ink-500">
              確信度 {(finding.confidence * 100).toFixed(0)}%
            </Badge>
            <Badge className="border-slate-200 bg-white text-ink-400">
              {finding.source === "llm" ? "LLM推論" : "ルールベース"}
            </Badge>
            {finding.cause_category && (
              <Badge className="border-indigo-200 bg-indigo-50 text-indigo-700">
                推定原因: {finding.cause_category}
              </Badge>
            )}
          </div>
          <h3 className="mt-2 text-sm font-semibold text-ink-900">{finding.title}</h3>
          <p className="mt-1 text-sm leading-relaxed text-ink-600">{finding.explanation}</p>
        </div>
        <div className="text-right text-xs text-ink-400">
          {finding.task_title && <p>対象Task: {finding.task_title}</p>}
          {finding.person_name && <p>対象Owner: {finding.person_name}</p>}
        </div>
      </div>

      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs font-semibold text-ink-500">Evidence（根拠）</p>
          <ul className="mt-1 space-y-1">
            {finding.evidence.map((item, index) => (
              <li key={index} className="text-xs leading-relaxed text-ink-700">
                <span className="font-medium text-ink-900">{item.label}:</span> {item.detail}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs font-semibold text-ink-500">想定Impact</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-700">{finding.impact}</p>
          <p className="mt-2 text-xs font-semibold text-ink-500">Reasoning Summary</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-700">{finding.reasoning_summary}</p>
        </div>
      </div>

      {finding.recommended_action && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3">
          <p className="text-xs font-semibold text-emerald-800">AI推奨アクション</p>
          <p className="mt-1 text-sm font-medium text-emerald-900">{finding.recommended_action}</p>
          <p className="mt-1 text-xs text-emerald-800">理由: {finding.recommended_action_why}</p>
        </div>
      )}

      {finding.recommended_actions.length > 0 && (
        <div className="mt-2">
          <button className="text-xs font-medium text-ink-500 hover:text-ink-900" onClick={() => setOpen(!open)}>
            {open ? "▾" : "▸"} 打ち手候補 {finding.recommended_actions.length} 件
          </button>
          {open && (
            <ol className="mt-2 space-y-2">
              {finding.recommended_actions.map((action, index) => (
                <li key={index} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-ink-900">
                      {index + 1}. {action.action}
                    </p>
                    <Badge className="border-slate-200 bg-slate-50 text-ink-500">
                      工数 {action.effort === "low" ? "小" : action.effort === "high" ? "大" : "中"}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-ink-600">Why: {action.why}</p>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </article>
  );
}
