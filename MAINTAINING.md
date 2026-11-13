# 運用メモ

全件データは Web-API では取得できないため、公表サイトのダウンロードページから全国版 zip（`00_zenkoku_all_YYYYMMDD.csv` の Unicode 版・約250MB）を取得して取り込んでいます。

## 更新方式

raw は法人番号をキーにした incremental モデルで、2系統で更新します。

- フル（月次・初回・コード push）: 全件 zip を取得して raw を作り直す（`--full-refresh`）。前月末日時点のスナップショット。
- 差分（日次）: 公表サイトの日次差分 `diff_YYYYMMDD.zip`（同一30列スキーマ、約40日分保持）のうち未取込分のみ取得し、法人番号ごとに最新履歴=1 を1件へ集約して delete+insert で upsert する。

差分の「法人番号ごとの最新履歴=1」は次回全件版に載る行と一致するため、差分適用後の raw は全件スナップショットと等価になる。登記閉鎖・検索対象除外への遷移もその法人の最新レコードに反映されるので、mart の現存フィルタが全件と同じ結果を返す（特別な削除処理は不要）。

## 変更履歴

`raw_houjin_bangou_records` は、全件・差分とも読んだ行を重複を除いてすべて溜める（`full_refresh=false` なので月次フルでも作り直さない）。同じ行の判定は seq と `_source_date` を除いた全列のハッシュ（`_record_hash`）。`mart_houjin_bangou_history` はこれを毎回作り直す。

- 差分には、訂正などのとき最新でない行（latest=0）も含めてその法人の履歴がまとめて載る。その日の履歴を正とし、それより前に取り込んだ行は使わない
- 同じ変更（法人番号・処理区分・変更年月日）が何度か載ったときは、最後に取り込んだ行を使う
- 最初の行は取り込みを始めたときの全件。それより前の変更は、公表サイトの差分（約40日分）にも全件にも残っていないので持てない。持つには Web-API（アプリケーション ID が必要）の期間指定（2015-12-01 以降）か、法人番号指定の履歴取得で埋める
- `raw_houjin_bangou_records` を作り直すと履歴が消える。消してしまったときは全件から始め直すことになる

モードは環境変数 `SYNC_MODE`（`full` / `incremental`、既定 `full`）で切り替える。`incremental` でも raw が無ければ `full` にフォールバックする。差分は約40日しか保持されないため、ベースの再同期として月次フルが必須。

## 開発

`scripts/build.sh` は公開中のバージョンを `fdl checkout` してから取り込み・ビルドし、`fdl commit` と `fdl push` で公開する（`shared/scripts/build-fdl.sh`）。手元で実行するときは、queria.io で発行したトークンを `FDL_TOKEN` に渡す。GitHub Actions では OIDC で取得する。

```bash
git submodule update --init
uv sync
SYNC_MODE=full        FDL_TOKEN=... scripts/build.sh   # 全件フル
SYNC_MODE=incremental FDL_TOKEN=... scripts/build.sh   # 日次差分の未取込分
```
