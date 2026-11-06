# 法人番号

[国税庁法人番号公表サイト](https://www.houjin-bangou.nta.go.jp/)が公表している全国の法人番号を、SQL で検索・集計できるテーブルにしたデータセットです。現存する約 500 万法人の商号・所在地・法人種別・法人番号指定年月日を収録しています。法人番号で gbizinfo・edinet・p_portal などと、`lg_code` で市区町村の統計と結合できます。

## 出典と利用条件

- 国税庁法人番号公表サイトの全件データ（全国版）を加工して作成しています。日次の差分データも取り込んでいます
- [公共データ利用規約（第1.0版）](https://www.houjin-bangou.nta.go.jp/riyokiyaku/)に従います（CC BY 4.0 互換）。出典の明記が必要です
- 国税庁が公表したデータを Queria が加工したもので、最新性・正確性・完全性等が保証されたものではありません

## テーブル

`main.mart_houjin_bangou` は 1 行が 1 法人です。最新の履歴で、検索対象除外でも登記閉鎖でもない法人だけに絞っています。

- corporate_number: 法人番号（13桁）
- seq: 一連番号（ファイル内の連番）
- process / correct: 処理区分 / 訂正区分
- update_date / change_date / assignment_date: 更新 / 変更 / 法人番号指定年月日（DATE）
- name / name_en: 商号又は名称（漢字 / 英語）
- kind: 法人種別（301=株式会社、302=有限会社、305=合同会社 ほか）
- prefecture_name / city_name / street_number: 都道府県名 / 市区町村名 / 丁目番地等
- prefecture_code / city_code: 都道府県コード（2桁）/ 市区町村コード（3桁）
- lg_code: 全国地方公共団体コード（6桁、チェックディジット付き）。lg_code・zipcode と結合できます
- post_code: 郵便番号（7桁）
- address_outside / address_outside_en: 国外所在地（漢字 / 英語）
- prefecture_en / city_street_en: 国内所在地の英語表記
- furigana: フリガナ
- change_cause: 変更事由の詳細

## 使い方

日野市に本店がある法人を、法人種別ごとに数える:

```sql
SELECT kind, count(*) AS corporations
FROM houjin_bangou.main.mart_houjin_bangou
WHERE lg_code = '132128'
GROUP BY ALL
ORDER BY corporations DESC;
```

## 注意

- 所在地は登記上の本店または主たる事務所の所在地です。支店や事業所は含みません
- 法人種別（`kind`）は 301=株式会社、302=有限会社、305=合同会社、101=国の機関、201=地方公共団体などのコードです
- 国外に所在地がある法人は `address_outside` に所在地が入ります
