"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { CategorySuggestion } from "@/lib/types";
import { Badge, ErrorBanner, Loading, Modal } from "./ui";

interface Props {
  projectId: number;
  onClose: () => void;
  onApplied: () => void;
}

/**
 * タスク名・説明から推定したカテゴリを、グループ単位で確認して一括適用する。
 * カテゴリ名はその場で編集でき、チェックを外した行は適用されない。
 */
export function CategorySuggestModal({ projectId, onClose, onApplied }: Props) {
  const [suggestions, setSuggestions] = useState<CategorySuggestion[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [renames, setRenames] = useState<Record<string, string>>({});
  const [includeCategorized, setIncludeCategorized] = useState(false);
  const [useLlm, setUseLlm] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const [llmUsed, setLlmUsed] = useState(false);
  const [unmatched, setUnmatched] = useState(0);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const body = await api.suggestCategories(projectId, {
        include_categorized: includeCategorized,
        use_llm: useLlm,
      });
      setSuggestions(body.suggestions);
      setSelected(new Set(body.suggestions.map((s) => s.task_id)));
      setRenames({});
      setNote(body.llm_note);
      setLlmUsed(body.llm_used);
      setUnmatched(body.unmatched_task_ids.length);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "分類に失敗しました");
    } finally {
      setLoading(false);
    }
  }, [projectId, includeCategorized, useLlm]);

  useEffect(() => {
    void load();
  }, [load]);

  const groups = useMemo(() => {
    const map = new Map<string, CategorySuggestion[]>();
    suggestions.forEach((suggestion) => {
      const list = map.get(suggestion.suggested_category) ?? [];
      list.push(suggestion);
      map.set(suggestion.suggested_category, list);
    });
    return [...map.entries()].sort((a, b) => b[1].length - a[1].length);
  }, [suggestions]);

  function toggle(taskId: number) {
    const next = new Set(selected);
    if (next.has(taskId)) next.delete(taskId);
    else next.add(taskId);
    setSelected(next);
  }

  function toggleGroup(rows: CategorySuggestion[]) {
    const allOn = rows.every((row) => selected.has(row.task_id));
    const next = new Set(selected);
    rows.forEach((row) => (allOn ? next.delete(row.task_id) : next.add(row.task_id)));
    setSelected(next);
  }

  async function apply() {
    const assignments = suggestions
      .filter((s) => selected.has(s.task_id))
      .map((s) => ({
        task_id: s.task_id,
        category_name: (renames[s.suggested_category] ?? s.suggested_category).trim(),
      }))
      .filter((a) => a.category_name);
    if (assignments.length === 0) {
      setError("適用する項目が選択されていません。");
      return;
    }
    setApplying(true);
    try {
      const result = await api.applyCategories(projectId, assignments);
      if (result.skipped.length > 0) setError(result.skipped.join(" / "));
      onApplied();
      if (result.skipped.length === 0) onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "適用に失敗しました");
    } finally {
      setApplying(false);
    }
  }

  return (
    <Modal title="カテゴリ自動分類" onClose={onClose} wide>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 text-xs">
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={includeCategorized}
                onChange={(event) => setIncludeCategorized(event.target.checked)}
              />
              カテゴリ設定済みのTaskも対象にする
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
              LLMで精緻化する
            </label>
          </div>
          <Badge
            className={
              llmUsed
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : "border-slate-200 bg-white text-ink-500"
            }
          >
            {llmUsed ? "LLM分類" : "ルールベース分類"}
          </Badge>
        </div>

        {note && <p className="text-xs text-ink-500">{note}</p>}
        {error && <ErrorBanner message={error} />}

        {loading ? (
          <Loading label="タスク内容を分析中…" />
        ) : groups.length === 0 ? (
          <p className="py-8 text-center text-sm text-ink-500">
            提案できるカテゴリはありませんでした。
            {unmatched > 0 && `（判定できなかったTask: ${unmatched} 件）`}
          </p>
        ) : (
          <>
            <p className="text-xs text-ink-500">
              {suggestions.length} 件のTaskに {groups.length} カテゴリを提案しました。
              {unmatched > 0 && ` 判定できなかったTaskが ${unmatched} 件あります。`}
              カテゴリ名は変更できます。
            </p>
            <div className="max-h-[52vh] space-y-3 overflow-y-auto pr-1">
              {groups.map(([category, rows]) => (
                <section key={category} className="rounded-lg border border-slate-200">
                  <header className="flex flex-wrap items-center gap-2 border-b border-slate-100 bg-slate-50 px-3 py-2">
                    <input
                      type="checkbox"
                      checked={rows.every((row) => selected.has(row.task_id))}
                      onChange={() => toggleGroup(rows)}
                    />
                    <input
                      className="input h-8 max-w-[280px] py-1 text-sm font-medium"
                      value={renames[category] ?? category}
                      onChange={(event) =>
                        setRenames({ ...renames, [category]: event.target.value })
                      }
                    />
                    <span className="text-xs text-ink-500">{rows.length} 件</span>
                    {rows[0].existing_category_id && (
                      <Badge className="border-indigo-200 bg-indigo-50 text-indigo-700">既存カテゴリ</Badge>
                    )}
                  </header>
                  <ul>
                    {rows.map((row) => (
                      <li
                        key={row.task_id}
                        className="flex items-start gap-2 border-b border-slate-50 px-3 py-2 last:border-b-0"
                      >
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={selected.has(row.task_id)}
                          onChange={() => toggle(row.task_id)}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm">
                            {row.task_code && <span className="mr-2 text-xs text-ink-400">{row.task_code}</span>}
                            {row.task_title}
                          </p>
                          <p className="text-[11px] text-ink-400">
                            {row.reason}
                            {row.current_category && ` ／ 現在: ${row.current_category}`}
                          </p>
                        </div>
                        <Badge className="shrink-0 border-slate-200 bg-white text-ink-500">
                          確信度 {(row.confidence * 100).toFixed(0)}%
                        </Badge>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </>
        )}

        <div className="flex justify-end gap-2">
          <button className="btn-secondary" onClick={onClose}>
            キャンセル
          </button>
          <button className="btn-secondary" onClick={() => void load()} disabled={loading}>
            再分析
          </button>
          <button
            className="btn-primary"
            onClick={() => void apply()}
            disabled={applying || loading || selected.size === 0}
          >
            {applying ? "適用中…" : `${selected.size} 件に適用`}
          </button>
        </div>
      </div>
    </Modal>
  );
}
