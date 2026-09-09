"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useProjects } from "@/components/ProjectProvider";
import { Badge, Card, ErrorBanner, Field, Loading } from "@/components/ui";
import { api } from "@/lib/api";
import { STATUS_LABELS } from "@/lib/format";
import { TRIAGE_CONTEXT_KEY } from "@/lib/triage";
import type { ImportAnalyze, ImportPlan, ImportResult, MatchBy, TaskStatus } from "@/lib/types";

const REQUIRED_FIELD = "title";

type IssueMode = "triage" | "raw" | "skip";

export default function ImportPage() {
  const router = useRouter();
  const { projects, selectProject, reloadProjects } = useProjects();
  const [analysis, setAnalysis] = useState<ImportAnalyze | null>(null);
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [target, setTarget] = useState<"new" | "existing">("new");
  const [projectName, setProjectName] = useState("");
  const [existingProjectId, setExistingProjectId] = useState("");
  const [issueMode, setIssueMode] = useState<IssueMode>("triage");
  const [matchBy, setMatchBy] = useState<MatchBy>("auto");
  const [plan, setPlan] = useState<ImportPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const analyzed = await api.analyzeImport(file);
      setAnalysis(analyzed);
      setPlan(null);
      setMapping(analyzed.mapping);
      setProjectName(file.name.replace(/\.[^.]+$/, ""));
    } catch (err) {
      setError(err instanceof Error ? err.message : "解析に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function reanalyze(sheet: string, headerRow: number) {
    if (!analysis) return;
    setBusy(true);
    try {
      const analyzed = await api.previewImport(analysis.token, sheet, headerRow);
      setAnalysis(analyzed);
      setMapping(analyzed.mapping);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "再解析に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  function importPayload() {
    if (!analysis) return null;
    return {
      token: analysis.token,
      sheet: analysis.selected_sheet,
      header_row: analysis.header_row,
      mapping,
      project_id: target === "existing" && existingProjectId ? Number(existingProjectId) : null,
      new_project_name: target === "new" ? projectName || analysis.filename : null,
      create_issues: issueMode === "raw",
      match_by: target === "existing" ? matchBy : "none",
    };
  }

  async function checkDiff() {
    const payload = importPayload();
    if (!payload) return;
    if (!mapping[REQUIRED_FIELD]) {
      setError("タスク名の列を指定してください。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setPlan(await api.planImport(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : "差分を取得できませんでした");
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!analysis) return;
    if (!mapping[REQUIRED_FIELD]) {
      setError("タスク名の列を指定してください。");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const committed = await api.commitImport(importPayload()!);
      setResult(committed);
      setPlan(null);

      // 自由記述の課題列は、そのまま登録せず判定プレビューへ送る
      if (issueMode === "triage" && analysis && mapping.issue) {
        window.sessionStorage.setItem(
          TRIAGE_CONTEXT_KEY,
          JSON.stringify({
            token: analysis.token,
            sheet: analysis.selected_sheet,
            header_row: analysis.header_row,
            mapping,
            project_id: committed.project_id,
            project_name: committed.project_name,
          }),
        );
        router.push("/import/issues");
      }
      await reloadProjects();
      selectProject(committed.project_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取り込みに失敗しました");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Excel / WBS Import</h1>
        <p className="text-sm text-ink-500">
          .xlsx / .xls / .csv のWBSを取り込みます。列名は自動判定し、必要に応じて手動で修正できます。
        </p>
      </header>

      {error && <ErrorBanner message={error} />}

      <Card title="1. ファイルをアップロード">
        <label className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center transition hover:border-ink-400">
          <span className="text-sm font-medium text-ink-700">クリックしてWBSファイルを選択</span>
          <span className="mt-1 text-xs text-ink-400">対応形式: .xlsx / .xlsm / .xls / .csv（最大20MB）</span>
          <input
            type="file"
            className="hidden"
            accept=".xlsx,.xlsm,.xls,.csv"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />
        </label>
        {analysis && (
          <p className="mt-3 text-sm text-ink-600">
            読み込み済み: <span className="font-medium">{analysis.filename}</span>
          </p>
        )}
      </Card>

      {busy && <Loading label="処理中…" />}

      {analysis && (
        <>
          <Card title="2. シートとヘッダー行">
            <div className="flex flex-wrap items-end gap-4">
              <Field label="シート">
                <select
                  className="input"
                  value={analysis.selected_sheet}
                  onChange={(event) => void reanalyze(event.target.value, 0)}
                >
                  {analysis.sheets.map((sheet) => (
                    <option key={sheet.name} value={sheet.name}>
                      {sheet.name}（{sheet.row_count}行）
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="ヘッダー行（0始まり・自動検出済み）">
                <input
                  type="number"
                  min={0}
                  className="input w-32"
                  value={analysis.header_row}
                  onChange={(event) => void reanalyze(analysis.selected_sheet, Number(event.target.value))}
                />
              </Field>
              <div className="text-xs text-ink-500">
                検出列: {analysis.columns.length} 列 ／ プレビュー {analysis.preview.length} 行
              </div>
            </div>
            {analysis.warnings.length > 0 && (
              <ul className="mt-3 space-y-1">
                {analysis.warnings.map((warning, index) => (
                  <li key={index} className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
                    ⚠ {warning}
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="3. 列マッピング">
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {analysis.known_fields.map((field) => {
                const candidate = analysis.mapping_candidates.find((item) => item.field === field.field);
                return (
                  <div key={field.field} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-ink-700">
                        {field.label}
                        {field.field === REQUIRED_FIELD && <span className="ml-1 text-rose-500">*</span>}
                      </span>
                      {candidate && mapping[field.field] === candidate.column && (
                        <Badge className="border-slate-200 bg-slate-50 text-ink-400">
                          自動判定 {(candidate.confidence * 100).toFixed(0)}%
                        </Badge>
                      )}
                    </div>
                    <select
                      className="input mt-1"
                      value={mapping[field.field] ?? ""}
                      onChange={(event) =>
                        setMapping({ ...mapping, [field.field]: event.target.value || null })
                      }
                    >
                      <option value="">（使用しない）</option>
                      {analysis.columns.map((column) => (
                        <option key={column} value={column}>
                          {column}
                        </option>
                      ))}
                    </select>
                    {candidate?.reason && mapping[field.field] === candidate.column && (
                      <p className="mt-1 text-[11px] text-ink-400">{candidate.reason}</p>
                    )}
                  </div>
                );
              })}
            </div>
            {analysis.unmapped_columns.length > 0 && (
              <p className="mt-3 text-xs text-ink-400">
                未使用の列: {analysis.unmapped_columns.join(" / ")}
              </p>
            )}
          </Card>

          <Card title="4. プレビュー（変換後）">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px]">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="th">Task ID</th>
                    <th className="th">タスク名</th>
                    <th className="th">担当</th>
                    <th className="th">開始</th>
                    <th className="th">終了</th>
                    <th className="th">進捗</th>
                    <th className="th">Status</th>
                    <th className="th">優先度</th>
                    <th className="th">依存</th>
                    <th className="th">課題</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.preview.map((row, index) => (
                    <tr key={index} className="border-t border-slate-100">
                      <td className="td text-xs text-ink-500">{String(row.code ?? "")}</td>
                      <td className="td font-medium">{String(row.title ?? "")}</td>
                      <td className="td text-xs">{String(row.owner ?? "")}</td>
                      <td className="td text-xs tabular-nums">{String(row.planned_start ?? "")}</td>
                      <td className="td text-xs tabular-nums">{String(row.planned_end ?? "")}</td>
                      <td className="td text-xs tabular-nums">{String(row.progress ?? 0)}%</td>
                      <td className="td text-xs">
                        {STATUS_LABELS[(row.status as TaskStatus) ?? "not_started"] ?? String(row.status ?? "")}
                      </td>
                      <td className="td text-xs">{String(row.priority ?? "")}</td>
                      <td className="td text-xs text-ink-500">
                        {Array.isArray(row.dependency) ? row.dependency.join(", ") : ""}
                      </td>
                      <td className="td max-w-[200px] truncate text-xs text-ink-500">{String(row.issue ?? "")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card title="5. 取り込み先とImport実行">
            <div className="flex flex-wrap items-end gap-4">
              <Field label="取り込み先">
                <select
                  className="input"
                  value={target}
                  onChange={(event) => setTarget(event.target.value as "new" | "existing")}
                >
                  <option value="new">新規プロジェクトを作成</option>
                  <option value="existing">既存プロジェクトに追加</option>
                </select>
              </Field>
              {target === "new" ? (
                <Field label="プロジェクト名">
                  <input
                    className="input"
                    value={projectName}
                    onChange={(event) => setProjectName(event.target.value)}
                  />
                </Field>
              ) : (
                <Field label="既存プロジェクト">
                  <select
                    className="input"
                    value={existingProjectId}
                    onChange={(event) => setExistingProjectId(event.target.value)}
                  >
                    <option value="">選択してください</option>
                    {projects.map((project) => (
                      <option key={project.id} value={project.id}>
                        {project.name}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {target === "existing" && (
                <Field label="既存Taskとの突き合わせ">
                  <select
                    className="input"
                    value={matchBy}
                    onChange={(event) => {
                      setMatchBy(event.target.value as MatchBy);
                      setPlan(null);
                    }}
                  >
                    <option value="auto">自動（Task ID → タスク名）</option>
                    <option value="code">Task ID のみ</option>
                    <option value="title">タスク名のみ</option>
                    <option value="none">突き合わせない（すべて追加）</option>
                  </select>
                </Field>
              )}
              <Field label="課題列の扱い">
                <select
                  className="input"
                  value={issueMode}
                  onChange={(event) => setIssueMode(event.target.value as IssueMode)}
                >
                  <option value="triage">AIで判定してから登録（推奨）</option>
                  <option value="raw">そのまま全行をIssueにする</option>
                  <option value="skip">取り込まない</option>
                </select>
              </Field>
              {target === "existing" && (
                <button className="btn-secondary mb-0.5" onClick={() => void checkDiff()} disabled={busy}>
                  差分を確認
                </button>
              )}
              <button className="btn-primary mb-0.5" onClick={() => void commit()} disabled={busy}>
                Importを実行
              </button>
            </div>

            {issueMode === "triage" && (
              <p className="mt-3 text-xs text-ink-500">
                課題列は自由記述を想定し、取り込み後に<strong>課題分析プレビュー</strong>へ移動します。
                そこで「課題 / 要確認 / 課題ではない」の判定を確認・修正してから登録できます。
              </p>
            )}
            {target === "existing" && (
              <p className="mt-3 text-xs text-ink-500">
                既存Taskと同じ Task ID / タスク名の行は<strong>更新</strong>され、無い行だけが追加されます。
                空欄のセルは既存の値を上書きしません。
              </p>
            )}

            {plan && (
              <div className="mt-4 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge className="border-sky-200 bg-sky-50 text-sky-800">更新 {plan.update_count} 件</Badge>
                  <Badge className="border-emerald-200 bg-emerald-50 text-emerald-800">
                    追加 {plan.create_count} 件
                  </Badge>
                  <Badge className="border-slate-200 bg-slate-50 text-ink-600">
                    変更なし {plan.unchanged_count} 件
                  </Badge>
                  {plan.skipped_rows > 0 && (
                    <Badge className="border-amber-200 bg-amber-50 text-amber-800">
                      スキップ {plan.skipped_rows} 行
                    </Badge>
                  )}
                </div>

                <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-200">
                  <table className="w-full">
                    <thead className="sticky top-0 bg-slate-50">
                      <tr>
                        <th className="th">操作</th>
                        <th className="th">タスク</th>
                        <th className="th">変更内容</th>
                      </tr>
                    </thead>
                    <tbody>
                      {plan.rows
                        .filter((row) => row.action !== "unchanged")
                        .map((row) => (
                          <tr key={row.row_index} className="border-t border-slate-100">
                            <td className="td">
                              <Badge
                                className={
                                  row.action === "create"
                                    ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                                    : "border-sky-200 bg-sky-50 text-sky-800"
                                }
                              >
                                {row.action === "create" ? "追加" : "更新"}
                              </Badge>
                            </td>
                            <td className="td text-sm">
                              {row.code && <span className="mr-2 text-xs text-ink-400">{row.code}</span>}
                              {row.title}
                              {row.matched_by && (
                                <span className="ml-2 text-[11px] text-ink-400">
                                  （{row.matched_by === "code" ? "Task ID" : "タスク名"}で一致）
                                </span>
                              )}
                            </td>
                            <td className="td text-xs text-ink-600">
                              {row.changes.length === 0
                                ? "新規登録"
                                : row.changes.map((change) => (
                                    <span key={change.field} className="mr-3 whitespace-nowrap">
                                      {change.label}: <span className="text-ink-400">{change.before ?? "—"}</span>
                                      {" → "}
                                      <span className="font-medium">{change.after ?? "—"}</span>
                                    </span>
                                  ))}
                            </td>
                          </tr>
                        ))}
                      {plan.update_count + plan.create_count === 0 && (
                        <tr>
                          <td className="td text-sm text-ink-500" colSpan={3}>
                            差分はありません。
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {plan.missing_in_file.length > 0 && (
                  <p className="text-xs text-ink-500">
                    ファイルに無い既存Task（削除はされません）: {" "}
                    {plan.missing_in_file.map((task) => task.title).join("、")}
                  </p>
                )}
              </div>
            )}
          </Card>
        </>
      )}

      {result && (
        <Card title="Import完了">
          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Summary label="追加Task" value={result.created_tasks} />
            <Summary label="更新Task" value={result.updated_tasks} />
            <Summary label="担当者" value={result.created_people} />
            <Summary label="Issue" value={result.created_issues} />
            <Summary label="依存関係" value={result.created_dependencies} />
            <Summary label="マイルストーン" value={result.created_milestones} />
            <Summary label="スキップ行" value={result.skipped_rows} />
          </div>
          <p className="mt-3 text-sm">
            プロジェクト「{result.project_name}」に取り込みました。{" "}
            <Link href="/" className="font-medium underline">
              Command Centerで確認する →
            </Link>
          </p>
          {result.warnings.length > 0 && (
            <ul className="mt-3 space-y-1">
              {result.warnings.map((warning, index) => (
                <li key={index} className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  ⚠ {warning}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </div>
  );
}

function Summary({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <p className="text-[11px] text-ink-500">{label}</p>
      <p className="text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
