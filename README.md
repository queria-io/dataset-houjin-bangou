# 法人番号

[国税庁法人番号公表サイト](https://www.houjin-bangou.nta.go.jp/)が公表している全国の法人番号を、SQL で検索・集計できるテーブルにしたデータセットです。現存する約 500 万法人の商号・所在地・法人種別・法人番号指定年月日と、閉鎖した法人を含む商号・所在地の変更履歴を収録しています。法人番号で gbizinfo・edinet・p_portal などと、`lg_code` で市区町村の統計と結合できます。

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

`main.mart_houjin_bangou_history` は 1 行が 1 回の変更（新規・商号変更・所在地変更・登記記録の閉鎖など）の後の状態です。閉鎖した法人も含みます。

- corporate_number: 法人番号（13桁）
- history_seq / is_latest: 法人番号ごとに変更年月日の古い順に振った番号 / その法人の最後の行か
- process / correct: 処理区分 / 訂正区分
- change_date / next_change_date / update_date: 変更年月日 / 同じ法人の次の行の変更年月日 / 更新年月日
- name / previous_name: 商号又は名称 / 変更前の商号又は名称（商号が変わった行だけ）
- kind・prefecture_name・city_name・street_number・prefecture_code・city_code・lg_code・post_code・address_outside: `mart_houjin_bangou` と同じ
- close_date / close_cause / successor_corporate_number: 登記記録の閉鎖等年月日 / 閉鎖等の事由 / 承継先法人番号
- change_cause / assignment_date / name_en / furigana: 変更事由の詳細 / 法人番号指定年月日 / 英語表記 / フリガナ

## 使い方

日野市に本店がある法人を、法人種別ごとに数える:

```sql
SELECT kind, count(*) AS corporations
FROM houjin_bangou.main.mart_houjin_bangou
WHERE lg_code = '132128'
GROUP BY ALL
ORDER BY corporations DESC;
```

旧商号から今の法人番号と商号を引く:

```sql
SELECT h.corporate_number, h.name AS old_name, m.name AS current_name, h.close_date
FROM houjin_bangou.main.mart_houjin_bangou_history h
LEFT JOIN houjin_bangou.main.mart_houjin_bangou m USING (corporate_number)
WHERE h.name = '株式会社〇〇';
```

## 注意

- 所在地は登記上の本店または主たる事務所の所在地です。支店や事業所は含みません
- 法人種別（`kind`）は 301=株式会社、302=有限会社、305=合同会社、101=国の機関、201=地方公共団体などのコードです
- 国外に所在地がある法人は `address_outside` に所在地が入ります
- 変更履歴は取り込みを始めた時点の全件データの状態を各法人の最初の行とし、それ以降の変更を日次の差分データから追加しています。それより前の商号・所在地は、差分データに過去の履歴が含まれていた法人だけが持ちます
- 閉鎖した法人の最後の行には `close_date` が入ります。合併で解散した法人は `successor_corporate_number` で承継先を引けます
