# AI PMO — Project Management OS v0.1

「Projectを記録するツール」ではなく、**Projectの異常を発見し、失敗する前にPMへ打ち手を提示するツール**。

通常のプロジェクト管理（Task / 担当者 / スケジュール / 課題）を実用水準で備えたうえで、
`Observe → Detect → Diagnose → Predict → Recommend` をAI PMOとして実装しています。

```
Structured Analysis (Python)  →  LLM Reasoning  →  Recommendation
 ・スケジュール計算 / CPM          ・原因仮説の言語化      ・推奨アクション
 ・期限超過・進捗乖離              ・Hidden Issueの説明    ・選定理由(Why)
 ・担当者負荷 / 依存関係           ・打ち手候補の並び替え
 ・Risk Score(0-100)
```

数値・根拠はすべてPython側で確定させ、LLMには**説明文と推奨の並び替えだけ**を任せます。
そのため `OPENAI_API_KEY` が無くても全機能が動作し（ルールベース推論にフォールバック）、
AIの出力には必ずEvidenceが付きます。

---

## 0. 触れるデモ / レビュー用（バックエンド無しで動かす）

**デモ: https://6enk1.github.io/AI-PMO/** — 環境構築なしでURLを開くだけで全画面を操作できます
（サンプルデータ。保存はされません）。


```bash
cd frontend && npm install
NEXT_PUBLIC_MOCK=1 npm run dev      # http://localhost:3000
```

APIをメモリ上の擬似データに差し替えて全画面が動きます（MSW不使用）。
200件・40文字ラベルのストレス確認用プロジェクトも同梱。件数は
`NEXT_PUBLIC_MOCK_TASKS` / `NEXT_PUBLIC_MOCK_LABEL_LENGTH` で変更できます。
詳細と既知の制限は [REVIEW.md](REVIEW.md) を参照してください。

---

## 1. クイックスタート

### Docker（推奨）

```bash
cp .env.example .env          # OPENAI_API_KEY は任意
docker compose up --build
# デモデータを入れる場合
docker compose exec backend python -m app.seed
```

- フロントエンド: http://localhost:3000
- API / OpenAPI docs: http://localhost:8000/docs

### ローカル実行

```bash
# --- backend ---
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed                     # 任意: デモプロジェクト作成
uvicorn app.main:app --reload --port 8000

# --- frontend（別ターミナル） ---
cd frontend
npm install
cp .env.local.example .env.local        # APIのURLを変える場合のみ
npm run dev
```

### テスト

```bash
cd backend && .venv/bin/python -m pytest      # 96 tests
cd frontend && npm run typecheck && npm run build
```

---

## 2. 画面

| 画面 | 内容 |
| --- | --- |
| **Project Command Center** (`/`) | Health Score とその減点内訳、未完了 / 期限超過 / High Risk / Hidden Issue / Open Issue 件数、次回マイルストーン、**今日見るべき項目**（最大10件） |
| **Task管理** (`/tasks`) | 一覧・新規・編集・削除、Status/Owner のインライン変更、**カテゴリ（親タスク）列**（その場で付け替え・新規作成・AI提案の適用）と**カテゴリ自動分類**、既定は階層順（WBS）表示でカテゴリ行を色分け、カテゴリ絞り込み、検索・Status/Priority/担当者/期限超過/Risk下限フィルタ、各列ソート |
| **Schedule** (`/schedule`) | ガントチャート（WBS階層順・カテゴリの集計バー・予定/進捗/実績バー・本日線・マイルストーン・クリティカルパス表示）、遅延Task一覧、予実差 |
| **Issue管理** (`/issues`) | Taskとは独立したIssueのCRUD、Severity / Status / Owner / Due Date / 関連Task |
| **担当者** (`/people`) | 氏名・Role・capacity、担当件数 / 未完了 / 期限超過 / 高リスク / 今週期限、負荷率と負荷レベル |
| **AI PMO** (`/ai-pmo`) | Hidden Issues / Delay Risks / Recommended Actions の3セクション |
| **Excel Import** (`/import`) | アップロード → シート選択 → ヘッダー行検出 → 列マッピング → プレビュー → Import確定 |

---

## 3. AI PMO の中身

### 3-1. Hidden Issue 検出（Issue未登録の問題を発見）

| 検出タイプ | 内容 |
| --- | --- |
| `stalled_near_completion` | 進捗90%以上で期限超過のまま停滞 |
| `due_soon_low_progress` | 期限が近いのに進捗が低い |
| `owner_missing` | Owner未設定 |
| `owner_overload` | 特定担当者へのTask集中（capacity超過・シェア50%以上） |
| `critical_task_concentration` | 同一担当者への高優先度Task集中 |
| `successor_start_blocked` | 後続Taskの開始日到来なのに前工程が未完了 |
| `dependency_cycle` / `dependency_date_conflict` | 依存関係の循環・日程の逆転 |
| `green_but_issue_heavy` | 予定上はGreenだが未解決Issueが積み上がっている |
| `progress_inconsistency` | 進捗率とStatus・実績日・子Taskの不整合 |
| `overdue_status_unchanged` | 予定終了日を過ぎてもStatusが「進行中」のまま |
| `milestone_buffer_insufficient` | マイルストーン直前の余裕日数不足 |
| `issue_governance_gap` | Owner未設定 / 期限切れの未解決Issue |

各Findingは **Severity / 対象Task・Owner / 発見内容 / Evidence / 想定Impact / 打ち手 / 推奨Actionと理由 / Confidence** を必ず保持します。
根拠が作れないFindingは出力前に破棄されるため、「危険です」だけの出力は構造上発生しません。

### 3-2. Delay Risk（遅延リスク分析・0〜100）

まだ遅延していないTaskも対象。ルールベースで加点し、**加点の内訳（factor）ごとに根拠テキスト**を保持します。

| Factor | 加点 |
| --- | --- |
| 期限超過（超過日数に比例） | 最大40 |
| 想定進捗との乖離 | 最大25 |
| 期限逼迫（残日数×進捗） | 最大18 |
| 前工程未完了 | 最大20 |
| Owner未設定 / 担当者過負荷 | 8〜10 |
| 未解決Issue（Severity考慮） | 最大15 |
| Float僅少・クリティカルパス | 6〜10 |
| 後続Task数 | 最大9 |
| Blocked / 更新停滞 / 未着手 | 6〜12 |
| 高Priority補正 | 3〜6 |

`>=80 critical / >=60 high / >=35 medium`。

### 3-3. 打ち手提案（Delay Action）

期限超過またはRisk Score 50以上のTaskについて、測定可能なシグナルから原因仮説を選定します。

対応する原因カテゴリ: 依存Task遅延 / 顧客回答待ち / 意思決定待ち / レビュー待ち / 仕様変更 / Scope増加 /
技術課題 / Owner不明確 / 人員不足 / 着手遅れ / 工数見積誤り / 未解決課題 / 完了処理待ち / 要因未特定。

出力例:

```
Task: T-002 API仕様確定
推定原因: 顧客回答待ち
Evidence:
  ・Due Date超過: 4 日（予定終了日 2026-08-31）
  ・進捗: 60%（想定 100%）
  ・関連Issue: 顧客からのAPI仕様回答待ち[open/high]
  ・後続Task: 2 件が待機中
打ち手:
  1. 回答期限を明示した督促を出し、未回答時の暫定方針を通知する
  2. 暫定仕様でFreezeし、後続Taskを再開する
  3. 回答不要な範囲を切り出して先行着手する
AI推奨: 2
理由: 後続Taskを再開でき、全体の停止コストを止められるため
```

### 3-4. カテゴリ自動分類

タスク名・説明・備考から工程カテゴリを推定し、WBSの大分類を自動で組み立てます。

1. **キーワード辞書（ルールベース）** — 企画・構想 / 要件定義 / 設計 / 開発・実装 / テスト /
   移行・リリース / インフラ・環境 / セキュリティ / データ / 運用・保守 / 教育・展開 /
   調達・契約 / プロジェクト管理 の13工程。一致した語を根拠として必ず残します
2. **既存カテゴリの再利用** — プロジェクトに既に「フェーズ2: 開発」があれば、新しく
   「開発・実装」を作らずそちらへ寄せます
3. **LLMによる精緻化（任意）** — キーがあれば、候補カテゴリを渡したうえでLLMが割り当てを
   見直します。未設定ならルールベースの結果をそのまま使います

Task管理の「✦ カテゴリ自動分類」から、提案をカテゴリ単位で確認し、名前を編集し、
チェックを外した行を除いて一括適用できます。行のカテゴリ欄には「✦ 提案: 設計」が並び、
1件ずつ適用することもできます。

カテゴリ（子を持つTask）は、日付と進捗を子から集計します。ガントでは階層順に並び、
カテゴリ行は子全体の期間と加重平均進捗を表す集計バーになります。

---

## 4. Excel / WBS Import

- 対応形式: `.xlsx` / `.xlsm` / `.xls` / `.csv`（CSVは UTF-8 / CP932 等を自動判定）
- タイトル行や空行が上にあっても**ヘッダー行を自動検出**（列名らしさ＋データらしさでスコアリング）
- 列名は固定しません。表記揺れを同義語辞書＋あいまい一致で解決します。
  - 担当 / 担当者 / Owner / Assignee / PIC …
  - 進捗 / 進捗率 / 完了率 / Progress / Progress % …
  - 終了日 / 完了予定日 / 期限 / 納期 / Due Date …（「実績終了日」は実績側へ正しく振り分け）
- 自動判定できない場合はImport画面で**ユーザーが列マッピングを修正**できます。
- 値の正規化: 日付（`2025/4/1`・`2025年4月1日`・`20250401`・Excelシリアル値）、
  進捗（`80%`・`0.8`・`80`・`完了`）、Status（完了/進行中/未着手/保留 ↔ done/in_progress/…）、Priority（高/最優先/High/…）
- 取り込み時に **Task / 担当者 / Issue（課題列）/ 依存関係（先行タスク列）/ 親子関係** を自動生成。
  親子は「親タスク列」またはWBS番号（`1.2.1` → `1.2`）から復元します。

### 課題リストの自動判定（課題分析プレビュー）

先方が作る課題リストは1行1課題になっておらず、進捗報告や感想が混ざる。そのまま登録すると
Issue管理がノイズで埋まるため、取り込み後に**課題分析プレビュー**を挟む。

Import画面の「課題列の扱い」で **AIで判定してから登録（推奨）** を選ぶと、取り込み完了後に
自動でプレビュー画面へ移動する。各行は3つのラベルに分類される。

| ラベル | 意味 | 既定の扱い |
| --- | --- | --- |
| 課題 (`issue`) | 対応・意思決定を要する記述 | チェック済み（登録対象） |
| 要確認 (`uncertain`) | 課題らしいが対象や影響が不明瞭 | **チェックなし**（目視確認が必須） |
| 課題ではない (`not_issue`) | 進捗報告・感想・挨拶 | 非表示（「表示する」で展開） |

判定と同時に、課題名（20〜30文字に要約）・詳細・関連タスク候補・重要度の推定を生成する。

- **元の文章にない情報は足さない。** 課題名は元の語だけで作り、詳細は整形のみ
- **1セルに複数課題があれば分割する。** 改行・箇条書き・番号を優先し、無理な分割はしない
- **関連タスク候補は既存タスク名との一致がある場合のみ。** 無関係な提案はしない
- **重要度は根拠が弱ければ「不明」。** 決め打ちしない
- プレビュー画面で全項目を編集でき、チェックした行だけが登録される
- `OPENAI_API_KEY` 未設定時はキーワード辞書によるルールベース判定にフォールバックする

判定は `POST /api/issues/analyze` が担当し、入力はテキスト配列なので Excel 以外
（Word / PDF / 貼り付けテキスト）を足すときもそのまま使える。

### 同期インポート（2回目以降）

既存プロジェクトへ取り込むときは、**Task ID → タスク名**の順で既存Taskと突き合わせます。

- 一致した行 → 進捗・日付・担当・Status などを**更新**（重複を作りません）
- 無い行 → **追加**
- **空欄のセルは既存の値を上書きしません**（進捗だけ書いたExcelを投げても担当や日付は残ります）
- 依存関係は既存Taskも解決対象。課題・マイルストーンは同名なら再作成しません
- 手動で設定したカテゴリ（親タスク）は保持されます
- ファイルから消えた既存Taskは**削除せず**、確認画面で一覧表示するだけです

Import実行前に「差分を確認」を押すと、`更新 2件 / 追加 1件 / 変更なし 4件` と
`進捗率: 70.0 → 90.0` のような変更内容を確認できます。突き合わせ方法は
自動 / Task IDのみ / タスク名のみ / 突き合わせない（すべて追加）から選べます。

---

## 5. データモデル

```
Project ──┬── Task ──┬── TaskDependency (predecessor / successor, FS|SS|FF|SF, lag)
          │          ├── parent_task_id（親子）
          │          └── Issue (task_id は任意 = TaskとIssueは独立)
          ├── Person (name / role / capacity_tasks)
          ├── Milestone
          └── AIRiskFinding（分析結果の永続化）
```

`Task` は Task ID / 親 / 子 / 担当者 / 開始・終了予定日 / 実績日 / 進捗率 / Status / Priority / 依存 / 備考 / 関連Issue を保持。
親子は何階層でもネストでき（`ソフトウェア開発 > フェーズ1 > 要件定義`）、最上位の親を「カテゴリ」として
Task一覧・ガント・Issue一覧・AI PMOの各Findingに表示します。APIは `category` / `parent_task_title` /
`path_titles` / `depth` を返し、`category_task_id` で配下Taskを階層まるごと絞り込めます。
`Issue` は Issue ID / 課題名 / 詳細 / Severity / Owner / 発生日 / Due Date / Status / 関連Task / 対応方針 / Resolution を保持します。

---

## 6. 技術スタック

| レイヤ | 採用技術 |
| --- | --- |
| Frontend | Next.js 15 (App Router) / TypeScript / Tailwind CSS |
| Backend | FastAPI / SQLAlchemy 2.x / Pydantic v2 |
| DB | SQLite（`DATABASE_URL` を変えればPostgreSQL等へ移行可能） |
| Excel | pandas / openpyxl / xlrd |
| AI | OpenAI Structured Output（任意・未設定時はルールベース） |
| Chart | 依存ライブラリなしの自前ガント（SVG/CSS） |
| 実行 | Docker Compose |

### ディレクトリ

```
backend/
  app/
    analysis/     # 構造化分析: snapshot(CPM/負荷) / risk / hidden_issues / delay_actions / health
    ai/           # LLM推論レイヤ（説明文と推奨の並び替えのみ）
    importer/     # Excel/CSV取込: 列マッピング・値パース・コミット
    routers/      # FastAPI エンドポイント
    models.py schemas.py services.py seed.py
  tests/          # pytest（CRUD / Risk / Hidden Issue / Import / API）
frontend/
  src/app/        # 各画面（App Router）
  src/components/ # AppShell / Gantt / FindingCard / フォーム / UI
  src/lib/        # APIクライアント・型・表示フォーマット
```

---

## 7. 主なAPI

| メソッド | パス | 用途 |
| --- | --- | --- |
| GET/POST | `/api/projects` | プロジェクト一覧・作成 |
| GET | `/api/projects/{id}/dashboard` | Command Center 用の集計 |
| GET/POST | `/api/projects/{id}/tasks` | Task一覧（フィルタ・ソート）・作成 |
| PATCH/DELETE | `/api/tasks/{id}` | Task更新・削除 |
| GET/POST | `/api/projects/{id}/issues` | Issue一覧・作成 |
| GET/POST | `/api/projects/{id}/people` | 担当者一覧（負荷付き）・作成 |
| GET | `/api/projects/{id}/ai-pmo` | Hidden Issue / Delay Risk / 打ち手 |
| GET | `/api/projects/{id}/risks` | Risk Score 一覧（factor内訳付き） |
| POST | `/api/imports/analyze` | ファイル解析・列マッピング推定 |
| GET | `/api/imports/{token}/preview` | シート・ヘッダー行を変えて再解析 |
| POST | `/api/imports/plan` | 取り込み前の差分確認（更新/追加/変更なし） |
| POST | `/api/imports/issue-rows` | 課題列の自由記述を全行抽出 |
| POST | `/api/issues/analyze` | 自由記述の課題判定・整形（書き込みなし） |
| POST | `/api/issues/bulk_create` | 確認済み課題の一括登録 |
| POST | `/api/imports/commit` | 取り込み確定（既存Taskとの同期を含む） |

全エンドポイントは `/docs`（Swagger UI）で確認できます。

---

## 8. v0.1 の範囲と制限

- スケジュール計算は**暦日ベース**（営業日カレンダー・休日考慮は未実装）
- 認証・権限管理なし（ローカル / 社内利用を想定）
- Teams / Slack / Gmail 連携、議事録解析、Monte Carlo シミュレーションは対象外
- LLM連携はOpenAI互換のみ。未設定時はルールベース推論で全機能が動作します
