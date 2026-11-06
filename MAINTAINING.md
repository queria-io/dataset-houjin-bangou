# 運用メモ

全件データは Web-API では取得できないため、公表サイトのダウンロードページから全国版 zip（`00_zenkoku_all_YYYYMMDD.csv` の Unicode 版・約250MB）を取得して取り込んでいます。

## 更新方式

raw は法人番号をキーにした incremental モデルで、2系統で更新します。

- フル（月次・初回・コード push）: 全件 zip を取得して raw を作り直す（`--full-refresh`）。前月末日時点のスナップショット。
- 差分（日次）: 公表サイトの日次差分 `diff_YYYYMMDD.zip`（同一30列スキーマ、約40日分保持）のうち未取込分のみ取得し、法人番号ごとに最新履歴=1 を1件へ集約して delete+insert で upsert する。

差分の「法人番号ごとの最新履歴=1」は次回全件版に載る行と一致するため、差分適用後の raw は全件スナップショットと等価になる。登記閉鎖・検索対象除外への遷移もその法人の最新レコードに反映されるので、mart の現存フィルタが全件と同じ結果を返す（特別な削除処理は不要）。

モードは環境変数 `HOUJIN_MODE`（`full` / `incremental`、既定 `full`）で切り替える。`incremental` でも raw が無ければ `full` にフォールバックする。差分は約40日しか保持されないため、ベースの再同期として月次フルが必須。

## 開発

`.env`（direnv が `.envrc` の `dotenv` で読み込む）に Neon / R2 の認証情報を設定する。必要な環境変数:

- NEON_DATABASE_URL
- QUERIA_S3_ENDPOINT
- QUERIA_S3_ACCESS_KEY_ID
- QUERIA_S3_SECRET_ACCESS_KEY
- CF_ACCOUNT_ID
- QUERIA_S3_BUCKET（default ターゲット時）/ QUERIA_DEV_S3_BUCKET（local、既定 queria-dev）

```bash
uv sync
HOUJIN_MODE=full        uv run python main.py local   # 全件フルで dev へビルド
HOUJIN_MODE=incremental uv run python main.py local   # 日次差分の未取込分を dev へ適用
```

