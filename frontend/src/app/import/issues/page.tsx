"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Card, EmptyState, ErrorBanner, Loading, StatCard } from "@/components/ui";
import { api } from "@/lib/api";
import { SEVERITY_LABELS, severityClass } from "@/lib/format";
import { TRIAGE_CONTEXT_KEY, type TriageContext } from "@/lib/triage";
import type { Severity, TriageItem, TriageLabel } from "@/lib/types";

const LABEL_META: Record<TriageLabel, { text: string; className: string; hint: string }> = {
  issue: {
    text: "課題",
    className: "border-rose-200 bg-rose-50 text-rose-700",
    hint: "対応が必要な課題として登録します",
  },
  uncertain: {
    text: "要確認",
    className: "border-amber-200 bg-amber-50 text-amber-800",
    hint: "課題らしいが情報が足りません。内容を見て判断してください",
  },
  not_issue: {
    text: "課題ではない",
    className: "border-slate-200 bg-slate-100 text-ink-500",
    hint: "進捗報告・感想などとして除外しました",
  },
};

const SEVERITY_OPTIONS: Severity[] = ["low", "medium", "high", "critical"];

export default function IssueTriagePage() {
  const router = useRouter();
  const [context, setContext] = useState<TriageContext | null>(null);
  const [items, setItems] = useState<TriageItem[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [showNotIssue, setShowNotIssue] = useState(false);
  const [labelFilter, setLabelFilter] = useState<TriageLabel | "all">("all");
  const [sort, setSort] = useState<"row" | "label" | "confidence">("row");
  const [llmUsed, setLlmUsed] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ created: number; skipped: string[] } | null>(null);
  const [tasks, setTasks] = useState<{ id: number; title: string }[]>([]);

  useEffect(() => {
    const raw = window.sessionStorage.getItem(TRIAGE_CONTEXT_KEY);
    if (!raw) {
      setLoading(false);
      return;
    }
    try {
      setContext(JSON.parse(raw) as TriageContext);
    } catch {
      setLoading(false);
    }
  }, []);

  const analyze = useCallback(async (ctx: TriageContext) => {
    setLoading(true);
    try {
      const extracted = await api.importIssueRows({
        token: ctx.token,
        sheet: ctx.sheet,
        header_row: ctx.header_row,
        mapping: ctx.mapping,
      });
      if (extracted.rows.length === 0) {
        setItems([]);
        setNote("課題列に文章が見つかりませんでした。");
        return;
      }
      const analyzed = await api.analyzeIssues({ project_id: ctx.project_id, rows: extracted.rows });
      setItems(analyzed.items);
      setLlmUsed(analyzed.llm_used);
      setNote(analyzed.llm_note);
      // 課題は既定でチェック済み、要確認は目視確認が要るので外しておく
      setChecked(new Set(analyzed.items.filter((item) => item.label === "issue").map((item) => item.id)));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "分析に失敗しました");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!context) return;
    void analyze(context);
    void api
      .listTasks(context.project_id, { sort: "code", order: "asc" })
      .then((list) => setTasks(list.map((task) => ({ id: task.id, title: task.title }))))
      .catch(() => setTasks([]));
  }, [context, analyze]);

  const visible = useMemo(() => {
    let rows = items;
    if (labelFilter !== "all") rows = rows.filter((item) => item.label === labelFilter);
    else if (!showNotIssue) rows = rows.filter((item) => item.label !== "not_issue");
    const order: Record<TriageLabel, number> = { issue: 0, uncertain: 1, not_issue: 2 };
    return [...rows].sort((a, b) => {
      if (sort === "label") return order[a.label] - order[b.label];
      if (sort === "confidence") return b.confidence - a.confidence;
      return (a.row_index ?? 0) - (b.row_index ?? 0) || a.part_index - b.part_index;
    });
  }, [items, labelFilter, showNotIssue, sort]);

  function update(id: string, patch: Partial<TriageItem>) {
    setItems((current) => current.map((item) => (item.id === id ? { ...item, ...patch } : item)));
  }

  function toggle(id: string) {
    setChecked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectLabel(label: TriageLabel) {
    setChecked((current) => {
      const next = new Set(current);
      items.filter((item) => item.label === label).forEach((item) => next.add(item.id));
      return next;
    });
  }

  async function apply() {
    if (!context) return;
    const selected = items.filter((item) => checked.has(item.id));
    if (selected.length === 0) {
      setError("登録する行が選択されていません。");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const created = await api.bulkCreateIssues(
        context.project_id,
        selected.map((item) => ({
          title: item.title || item.statement.slice(0, 60),
          description: item.description || item.statement,
          severity: item.severity,
          task_id: item.related_task_candidates[0]?.task_id ?? null,
          status: "open",
        })),
      );
      setResult({ created: created.created, skipped: created.skipped });
      setItems((current) => current.filter((item) => !checked.has(item.id)));
      setChecked(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : "登録に失敗しました");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Loading label="課題を判定しています…" />;

  if (!context) {
    return (
      <EmptyState
        title="取り込み結果が見つかりません"
        hint="Excel Import からやり直してください（このページはImport直後にだけ使えます）。"
      />
    );
  }

  const uncheckedUncertain = items.filter(
    (item) => item.label === "uncertain" && !checked.has(item.id),
  ).length;

  const counts = {
    issue: items.filter((item) => item.label === "issue").length,
    uncertain: items.filter((item) => item.label === "uncertain").length,
    not_issue: items.filter((item) => item.label === "not_issue").length,
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">課題分析プレビュー</h1>
          <p className="text-sm text-ink-500">
            取り込み先: {context.project_name} ／ 登録前に内容を確認・修正できます
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge
            className={
              llmUsed
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-slate-200 bg-white text-ink-500"
            }
          >
            {llmUsed ? "LLM判定" : "ルールベース判定"}
          </Badge>
          <button className="btn-secondary" onClick={() => void analyze(context)}>
            再判定
          </button>
        </div>
      </header>

      <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
        <p className="font-medium">
          チェックを入れた行だけが、Issue管理に登録されます。
        </p>
        <p className="mt-1 text-xs">
          課題名・詳細・関連タスク・重要度はこの画面で修正できます。修正した内容で登録されます。
          登録するまで、Issue管理には何も追加されません。
        </p>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs">
          <span className="flex items-center gap-1.5">
            <span aria-hidden>✅</span>
            <Badge className={LABEL_META.issue.className}>課題</Badge>
            {LABEL_META.issue.hint}
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden>⚠️</span>
            <Badge className={LABEL_META.uncertain.className}>要確認</Badge>
            {LABEL_META.uncertain.hint}
          </span>
          <span className="flex items-center gap-1.5">
            <span aria-hidden>❌</span>
            <Badge className={LABEL_META.not_issue.className}>課題ではない</Badge>
            {LABEL_META.not_issue.hint}
          </span>
        </div>
      </div>

      {note && <p className="text-xs text-ink-500">{note}</p>}
      {error && <ErrorBanner message={error} />}

      {result && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <p className="font-medium">{result.created} 件をIssueとして登録しました。</p>
          {result.skipped.length > 0 && (
            <ul className="mt-1 list-disc pl-5 text-xs">
              {result.skipped.map((message, index) => (
                <li key={index}>{message}</li>
              ))}
            </ul>
          )}
          <div className="mt-2 flex gap-3 text-xs">
            <Link href="/issues" className="font-medium underline">
              Issue管理で確認する →
            </Link>
            <button className="underline" onClick={() => router.push("/import")}>
              Import画面へ戻る
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard label="課題" value={counts.issue} tone={counts.issue ? "danger" : "default"} hint="チェック済み・このまま登録されます" />
        <StatCard label="要確認" value={counts.uncertain} tone={counts.uncertain ? "warn" : "default"} hint="未チェック・見て判断してください" />
        <StatCard label="課題ではない" value={counts.not_issue} hint="非表示・登録されません" />
      </div>

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          {(["all", "issue", "uncertain", "not_issue"] as const).map((value) => (
            <button
              key={value}
              className={`badge ${
                labelFilter === value
                  ? "border-ink-900 bg-ink-900 text-white"
                  : "border-slate-200 bg-white text-ink-600"
              }`}
              onClick={() => setLabelFilter(value)}
            >
              {value === "all" ? "すべて" : LABEL_META[value].text}
            </button>
          ))}
          <span className="mx-1 text-slate-300">|</span>
          <button className="badge border-slate-200 bg-white text-ink-600" onClick={() => selectLabel("issue")}>
            課題を全選択
          </button>
          <button
            className="badge border-slate-200 bg-white text-ink-600"
            onClick={() => setChecked(new Set())}
          >
            選択をすべて解除
          </button>
          <button
            className={`badge ${
              showNotIssue ? "border-ink-900 bg-ink-900 text-white" : "border-slate-200 bg-white text-ink-600"
            }`}
            onClick={() => setShowNotIssue(!showNotIssue)}
          >
            課題ではない行を{showNotIssue ? "隠す" : "表示する"}
          </button>
          <span className="mx-1 text-slate-300">|</span>
          <select
            className="input w-40"
            value={sort}
            onChange={(event) => setSort(event.target.value as typeof sort)}
          >
            <option value="row">元の行順</option>
            <option value="label">判定順</option>
            <option value="confidence">確信度順</option>
          </select>
          <span className="ml-auto text-xs text-ink-500">{checked.size} 件を選択中</span>
        </div>
      </Card>

      {visible.length === 0 ? (
        <EmptyState title="表示できる行がありません" hint="フィルタを変更するか、Import画面からやり直してください。" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full min-w-[1100px]">
            <thead className="bg-slate-50">
              <tr>
                <th className="th w-10"></th>
                <th className="th">判定</th>
                <th className="th">課題名</th>
                <th className="th">詳細</th>
                <th className="th">関連タスク</th>
                <th className="th">重要度</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr
                  key={item.id}
                  className={`border-t border-slate-100 align-top ${
                    item.label === "not_issue" ? "bg-slate-50/60 text-ink-400" : ""
                  }`}
                >
                  <td className="td">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={checked.has(item.id)}
                      onChange={() => toggle(item.id)}
                    />
                  </td>
                  <td className="td whitespace-nowrap">
                    <select
                      className={`badge ${LABEL_META[item.label].className}`}
                      value={item.label}
                      onChange={(event) => update(item.id, { label: event.target.value as TriageLabel })}
                    >
                      {(Object.keys(LABEL_META) as TriageLabel[]).map((label) => (
                        <option key={label} value={label}>
                          {LABEL_META[label].text}
                        </option>
                      ))}
                    </select>
                    <p className="mt-1 text-[11px] text-ink-400">確信度 {(item.confidence * 100).toFixed(0)}%</p>
                    {item.split && (
                      <Badge className="mt-1 border-indigo-200 bg-indigo-50 text-indigo-700">分割</Badge>
                    )}
                  </td>
                  <td className="td w-64">
                    <input
                      className="input py-1 text-sm"
                      value={item.title}
                      placeholder={item.label === "not_issue" ? "（登録しません）" : "課題名"}
                      onChange={(event) => update(item.id, { title: event.target.value })}
                    />
                    <button
                      className="mt-1 text-[11px] text-ink-400 hover:text-ink-700"
                      onClick={() =>
                        setExpanded((current) => {
                          const next = new Set(current);
                          if (next.has(item.id)) next.delete(item.id);
                          else next.add(item.id);
                          return next;
                        })
                      }
                    >
                      {expanded.has(item.id) ? "▾" : "▸"} 元テキスト
                    </button>
                    {expanded.has(item.id) && (
                      <div className="mt-1 rounded bg-slate-50 p-2 text-[11px] leading-relaxed text-ink-600">
                        {item.source_text}
                        {item.reasons.length > 0 && (
                          <p className="mt-1 text-ink-400">判定根拠: {item.reasons.join(" / ")}</p>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="td">
                    <textarea
                      className="input py-1 text-sm"
                      rows={2}
                      value={item.description}
                      onChange={(event) => update(item.id, { description: event.target.value })}
                    />
                  </td>
                  <td className="td w-48">
                    <select
                      className="input py-1 text-sm"
                      value={item.related_task_candidates[0]?.task_id ?? ""}
                      onChange={(event) => {
                        const taskId = event.target.value ? Number(event.target.value) : null;
                        const task = tasks.find((t) => t.id === taskId);
                        update(item.id, {
                          related_task_candidates: task
                            ? [{ task_id: task.id, title: task.title, score: 1 }]
                            : [],
                        });
                      }}
                    >
                      <option value="">（関連なし）</option>
                      {item.related_task_candidates
                        .filter((c) => c.task_id !== null && !tasks.some((t) => t.id === c.task_id))
                        .map((c) => (
                          <option key={c.task_id} value={c.task_id ?? ""}>
                            {c.title}
                          </option>
                        ))}
                      {tasks.map((task) => (
                        <option key={task.id} value={task.id}>
                          {task.title}
                        </option>
                      ))}
                    </select>
                    {item.related_task_candidates.length > 1 && (
                      <p className="mt-1 text-[11px] text-ink-400">
                        他の候補: {item.related_task_candidates.slice(1).map((c) => c.title).join("、")}
                      </p>
                    )}
                  </td>
                  <td className="td w-32">
                    <select
                      className={`badge ${severityClass(item.severity)}`}
                      value={item.severity}
                      onChange={(event) => update(item.id, { severity: event.target.value as Severity })}
                    >
                      {SEVERITY_OPTIONS.map((severity) => (
                        <option key={severity} value={severity}>
                          {SEVERITY_LABELS[severity]}
                        </option>
                      ))}
                    </select>
                    <p className="mt-1 text-[11px] text-ink-400">推定 {item.severity_estimate}</p>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-end gap-3">
        <p className="mr-auto text-xs text-ink-500">
          {checked.size === 0 ? (
            "登録する行にチェックを入れてください。"
          ) : (
            <>
              チェックした <strong className="text-ink-900">{checked.size} 件</strong>を
              「{context.project_name}」の Issue管理に登録します
              {uncheckedUncertain > 0 && `（要確認 ${uncheckedUncertain} 件は未チェックのまま登録されません）`}。
            </>
          )}
        </p>
        <Link href="/import" className="btn-secondary">
          Import画面へ戻る
        </Link>
        <button className="btn-primary" onClick={() => void apply()} disabled={saving || checked.size === 0}>
          {saving ? "登録中…" : `チェックした ${checked.size} 件を登録`}
        </button>
      </div>
    </div>
  );
}
