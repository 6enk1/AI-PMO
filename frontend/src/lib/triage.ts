/** Import画面から課題分析プレビューへ引き継ぐ取り込み条件（同一セッション内のみ） */
export const TRIAGE_CONTEXT_KEY = "ai-pmo:issue-triage-context";

export interface TriageContext {
  token: string;
  sheet: string | null;
  header_row: number | null;
  mapping: Record<string, string | null>;
  project_id: number;
  project_name: string;
}
