# ビルドと更新

データセットの概要は [README.md](README.md) にあります。ここにはこのリポジトリでデータセットをビルド・更新する手順を書きます。

全件データは Web-API では取得できないため、公表サイトのダウンロードページから全国版 zip（`00_zenkoku_all_YYYYMMDD.csv` の Unicode 版・約250MB）を取得して取り込んでいます。

## 更新方式

raw は法人番号をキーにした incremental モデルで、2系統で更新します。

- フル（月次・初回・コード push）: 全件 zip を取得して raw を作り直す（`--full-refresh`）。前月末日時点のスナップショット。
- 差分（日次）: Web-API（`webapi.py`）の期間指定で、未取込の日を 1 日ずつ前日まで取得し（全件・差分のダウンロードと同じ 30 列）、法人番号ごとに最新履歴=1 を1件へ集約して delete+insert で upsert する。

差分の「法人番号ごとの最新履歴=1」は次回全件版に載る行と一致するため、差分適用後の raw は全件スナップショットと等価になる。登記閉鎖・検索対象除外への遷移もその法人の最新レコードに反映されるので、mart の現存フィルタが全件と同じ結果を返す（特別な削除処理は不要）。

## 変更履歴

`raw_houjin_bangou_records` は、全件・差分とも読んだ行を重複を除いてすべて溜める（`full_refresh=false` なので月次フルでも作り直さない）。同じ行の判定は seq と `_source_date` を除いた全列のハッシュ（`_record_hash`）。`mart_houjin_bangou_history` はこれを毎回作り直す。

- 同じ変更（法人番号・処理区分・変更年月日）が何度か載ったときは、最後に取り込んだ行を使う（`stg_houjin_bangou_records`）。訂正の行や、後の変更で latest=0 になった行も同じ扱い
- 過去分は日次の incremental が続きから少しずつ取り、`houjin_history_csv_paths` で `raw_houjin_bangou_records` にだけ足す（`raw_houjin_bangou` には入れない）
  - 期間指定: 2015-12-01 から `BACKFILL_END`（全件で始めた 2026-10-30）まで、1 回 `HOUJIN_BACKFILL_DAYS`（既定 600）日。1 日あたり 1〜2 リクエストで、600 日は 30 分ほど。進み具合は `_source_date < BACKFILL_END` の最大値
  - 法人番号指定（history=1）: 商号変更か吸収合併の行があるのに処理区分 01 の行を持たない法人を、1 回 `HOUJIN_HISTORY_REQUESTS`（既定 1500）リクエスト（10 法人ずつ）。2015-12-01 より前に指定された法人の最初の商号はこれでしか取れない
- Web-API は 1 リクエストごとに 1 秒空ける。アプリケーション ID は `HOUJIN_BANGOU_APP_ID`（GitHub の organization のシークレット）
- `raw_houjin_bangou_records` を作り直すと履歴が消える。消してしまったときは全件から始め直すことになる

モードは環境変数 `SYNC_MODE`（`full` / `incremental`、既定 `full`）で切り替える。`incremental` でも raw が無ければ `full` にフォールバックする。月次フルはベースの再同期。incremental はアプリケーション ID が要る。

## 開発

`scripts/build.sh` は公開中の apply ブランチを `fdl clone` してから取り込み・ビルドし、`fdl commit` と `fdl push` で公開する（`shared/scripts/build-fdl.sh`）。説明は `tabledoc.yml` と、モデルの隣の `<model>.tabledoc.yml` に書く。手元で実行するときは、queria.io で発行したトークンを `FDL_TOKEN` に渡す。GitHub Actions では OIDC で取得する。

```bash
git clone --depth=1 https://github.com/queria-io/dataset-shared.git shared
uv sync
SYNC_MODE=full        FDL_TOKEN=... scripts/build.sh   # 全件フル
SYNC_MODE=incremental HOUJIN_BANGOU_APP_ID=... FDL_TOKEN=... scripts/build.sh   # 日次差分の未取込分と過去分の続き
```
