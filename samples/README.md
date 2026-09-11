# テスト用WBSサンプル

AI PMO の動作確認用のWBSファイルです。日付は**生成した日を基準にした相対日付**なので、
そのまま取り込めば「期限超過」「期限間近」といった状況が再現されます。

古くなったら再生成してください。

```bash
python samples/generate_wbs_samples.py
python samples/generate_templates.py        # クライアント記入用テンプレート
```

| ファイル | 用途 |
| --- | --- |
| `wbs_sample_v1.xlsx` | 初版。まずこれを新規プロジェクトとして取り込む |
| `wbs_sample_v2_update.xlsx` | 1週間後の更新版。同期インポート（更新4件・追加2件）の確認用 |
| `wbs_sample_en.csv` | 英語ヘッダーのCSV。列名の自動判定を試す用 |
| `wbs_template.xlsx` | **クライアントに配るWBS記入用テンプレート**。「このカテゴリのゴール」列つき |
| `issue_list_template.xlsx` | **クライアントに配る課題記入用テンプレート**。記入例つき。記入して取り込むと課題分析プレビューへ進む |

## wbs_sample_v1.xlsx の中身

システム開発プロジェクトのWBS（27行 / 6フェーズ）。実務でありがちな形にしてあります。

- タイトル行2行と空行1行が上にある（**ヘッダー行の自動検出**を通る）
- 列名は `作業内容` `担当` `着手日` `期限` `進捗` `状態` `重要度` `先行作業` `MS` など**表記揺れあり**
- WBS番号（`1` / `1.1` / `1.2`）から**親子関係**が復元される
- 実績開始日・実績終了日つき（完了タスクは予定から1〜3日ずれている＝**予実差**が出る）

取り込むと、意図的に仕込んだ次の状況が検知されます。

| 仕込み | 検知される内容 |
| --- | --- |
| 基本設計が95%のまま期限超過 | `stalled_near_completion`（完了間際の停滞） |
| API仕様確定が期限超過＋「顧客からのAPI仕様回答待ち」 | `overdue_status_unchanged` ／ 打ち手の推定原因が**顧客回答待ち** |
| 画面設計・受入テスト支援・ベンダー選定が担当未設定 | `owner_missing` |
| 田中 美咲に高優先度タスクが5件集中 | `critical_task_concentration` |
| 前工程が終わっていないのに開始日が来ている | `successor_start_blocked` |
| 先行作業の期限より後続の着手日が早い | `dependency_date_conflict` |
| 期限間近なのに進捗が低い | `due_soon_low_progress` |
| Owner未設定・期限切れの課題 | `issue_governance_gap` |

Health Score は 66（注意）前後、Hidden Issue 20件前後になります。

## 試す順番

1. **Excel Import** で `wbs_sample_v1.xlsx` を新規プロジェクトとして取り込む
2. **Command Center** で Health Score と「今日見るべき項目」を見る
3. **AI PMO** で Hidden Issues / Delay Risks / Recommended Actions を確認する
4. **Task管理** の「✦ カテゴリ自動分類」でカテゴリを自動生成する
5. **Excel Import** で `wbs_sample_v2_update.xlsx` を**既存プロジェクトに追加**で取り込み、
   「差分を確認」で `更新4件 / 追加2件 / 変更なし23件` を見てから実行する
6. **Schedule** でガントを見る（カテゴリの集計バーと本日線、遅延タスクの赤表示）
