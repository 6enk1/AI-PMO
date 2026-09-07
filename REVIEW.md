# レビュー用セットアップ手順

このリポジトリは**モックではなく動くアプリケーション**です。フロントエンド（Next.js）と
バックエンド（FastAPI）の2プロセス構成ですが、**バックエンド無しでも画面を触れるモックモード**を
用意しています。

- リポジトリ: https://github.com/6enk1/AI-PMO （public）
- ブランチ: `claude/ai-pmo-v0-1-dev-5e3kyf`
- 除外物: `node_modules` / `.next` / `.venv` / `*.db` / `_uploads` / `.env`（すべて `.gitignore` 済み）

---

## 1. いちばん速い: モックモード（バックエンド不要）

```bash
cd frontend
npm install
NEXT_PUBLIC_MOCK=1 npm run dev     # http://localhost:3000
```

Windows PowerShell の場合:

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_MOCK=1; npm run dev
```

これだけで全7画面が動きます。API通信はメモリ上の擬似データに置き換わり、
Task/Issue/担当者のCRUD、フィルタ、ソート、モーダルもそのまま操作できます。

### 用意してあるデータ

プロジェクト切り替え（左上のプルダウン）で2つ入っています。

| プロジェクト | 中身 |
| --- | --- |
| 基幹システム刷新 PJ (モック) | 20件。期限超過・担当未設定・Blocked・課題つきなど実務に近い状態 |
| ストレス確認 PJ | **200件・40文字ラベル**。長い氏名（「ラミレス・アレクサンドラ」）や長い備考も混在 |

### 件数・ラベル長を変える

```bash
NEXT_PUBLIC_MOCK=1 NEXT_PUBLIC_MOCK_TASKS=1000 NEXT_PUBLIC_MOCK_LABEL_LENGTH=80 npm run dev
```

- `NEXT_PUBLIC_MOCK_TASKS` … ストレス用プロジェクトのTask件数（既定 200）
- `NEXT_PUBLIC_MOCK_LABEL_LENGTH` … タスク名の文字数（既定 40）

データを直接いじる場合は `frontend/src/lib/mock/dataset.ts` を編集してください。

### モックの作り

**MSW は使っていません。** Service Worker を挟まず、APIクライアント
（`frontend/src/lib/api.ts` の `request()`）の先頭で分岐しています。

```
src/lib/api.ts          … fetch のラッパー。MOCK_ENABLED なら handleMock() へ
src/lib/mock/server.ts  … パスごとのハンドラ。状態はメモリ保持（リロードで初期化）
src/lib/mock/dataset.ts … 擬似データの生成（固定シードなので毎回同じ）
```

### モックで再現していないもの

- **Excel取り込みの実処理** … 画面と固定のプレビューは出ますが、ファイルは解析されません
- **AI分析の中身** … Hidden Issue や Risk Score は簡略化した式で埋めた表示用の値です。
  実際の検知ロジック（12種の検出器、CPM、リスク加点）は Python 側にあります

この2つを本物で見る場合は、次の起動方法を使ってください。

---

## 2. 本物のバックエンド込みで動かす

### Docker（推奨）

```bash
cp .env.example .env      # OPENAI_API_KEY は任意。未設定でも全機能が動きます
docker compose up --build
docker compose exec backend python -m app.seed   # デモデータ投入
```

http://localhost:3000 / API docs は http://localhost:8000/docs

### ローカル2プロセス

```bash
# ターミナル1
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload --port 8000

# ターミナル2
cd frontend
npm install && npm run dev
```

`frontend` は `NEXT_PUBLIC_API_BASE`（既定 `http://localhost:8000`）を見ています。

### 取り込み用のサンプルWBS

`samples/wbs_sample_v1.xlsx` を Excel Import 画面から取り込むと、期限超過・担当未設定・
依存関係の矛盾などを含む27行のプロジェクトができます。`samples/README.md` に何が検知されるか
書いてあります。

---

## 3. 現状の作りと既知の状態

正直に書いておきます。**このv0.1はデスクトップ前提で作っており、モバイルは最低限です。**

| 項目 | 状態 |
| --- | --- |
| 390px でのナビゲーション | 対応済み。サイドバーはドロワー化、ハンバーガーは44×44px、横スクロールなし |
| Command Center / AI PMO / 担当者 | カードが縦積みになり、390pxで読めます |
| Task一覧・Issue一覧 | **テーブルは横スクロール**（列数が多く、モバイル用のカード表示は未実装） |
| ガントチャート | **横スクロール前提**。モバイル最適化はしていません |
| タップ領域 | ナビとヘッダーは44px確保。テーブル内のインライン操作（Status/担当のプルダウン）は32px前後で**未達** |
| フォーム・モーダル | 幅は追従しますが、モバイル向けの作り込みはしていません |

つまり「モバイルでも壊れないか」を見ていただくのは有効ですが、
**モバイルUIとして仕上げてはいない**状態です。指摘は前提込みで受け取ります。

### 技術スタック

- Frontend: Next.js 15（App Router）/ React 18 / TypeScript / Tailwind CSS 3
- Backend: FastAPI / SQLAlchemy 2 / SQLite / pandas・openpyxl
- 外部UIライブラリなし（ガントチャートも自前のCSS/divで実装）
- テスト: backend に pytest 139件（`cd backend && .venv/bin/python -m pytest`）

### 画面

`/`（Command Center）`/tasks` `/schedule` `/issues` `/people` `/ai-pmo` `/import`

---

## 5. 触れるデモ（GitHub Pages）

環境構築なしでURLを開くだけで触れるデモを公開しています。

**https://6enk1.github.io/AI-PMO/**

- フロントエンドだけを静的書き出しし、APIはモックデータに置き換えたものです
- Task/Issue/担当者の追加・編集・削除、フィルタ、ソートはその場で動きます（保存はされず、再読み込みで戻ります）
- プロジェクト切替に「ストレス確認 PJ (200件・40文字ラベル)」を同梱
- Excel取り込みの実処理とAI分析の実ロジックは含まれません（画面と固定のプレビューのみ）

公開は `.github/workflows/pages.yml` が担当します。初回のみリポジトリ側で
**Settings → Pages → Build and deployment → Source を「GitHub Actions」** に設定してください。

---

## 4. こちらから見てほしい点

1. 390px での各画面の壊れ方（特にTask一覧のテーブルとガント）
2. 200件・40文字ラベル時の一覧の可読性とスクロール挙動
3. タップ領域が44pxに届いていない箇所の洗い出し
4. カテゴリ（親タスク）と通常タスクの見分けが付くか
5. 情報量の多い画面（Command Center / AI PMO）の優先順位付け

指摘は具体的な箇所・条件つきでいただけると助かります。
