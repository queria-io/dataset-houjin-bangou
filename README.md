## データ出典

[国税庁法人番号公表サイト](https://www.houjin-bangou.nta.go.jp/)が公表している全国の法人番号（全件データ）です。約500万の現存法人について、商号・所在地・法人種別・法人番号指定年月日などを収録しています。

全件データは Web-API では取得できないため、公表サイトのダウンロードページから全国版 zip（`00_zenkoku_all_YYYYMMDD.csv` の Unicode 版・約250MB）を取得して取り込んでいます。

## テーブル: mart_houjin_bangou

現存法人の最新情報のみ（最新履歴・検索対象除外でない・登記閉鎖でない）に絞った法人マスタです。

- corporate_number: 法人番号（13桁）
- seq: 一連番号（ファイル内の連番）
- process / correct: 処理区分 / 訂正区分
- update_date / change_date / assignment_date: 更新 / 変更 / 法人番号指定年月日（DATE）
- name / name_en: 商号又は名称（漢字 / 英語）
- kind: 法人種別（301=株式会社、302=有限会社、305=合同会社 ほか）
- prefecture_name / city_name / street_number: 都道府県名 / 市区町村名 / 丁目番地等
- prefecture_code / city_code: 都道府県コード（2桁）/ 市区町村コード（3桁）
- lg_code: 全国地方公共団体コード（6桁、チェックディジット付き）。dataset-lg-code / dataset-zipcode と結合可能
- post_code: 郵便番号（7桁）
- address_outside / address_outside_en: 国外所在地（漢字 / 英語）
- prefecture_en / city_street_en: 国内所在地の英語表記
- furigana: フリガナ
- change_cause: 変更事由の詳細

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
uv run python main.py local   # dev R2 / Neon へビルド
```

## ライセンス

[公共データ利用規約（第1.0版）](https://www.houjin-bangou.nta.go.jp/riyokiyaku/)に準拠（CC BY 4.0 互換、出典明記が必要）。

出典：国税庁法人番号公表サイト（国税庁）
