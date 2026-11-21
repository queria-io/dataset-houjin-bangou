{{ config(materialized='view') }}

-- 同じ変更（法人番号・処理区分・変更年月日）が何度か載ったときは、最後に取り込んだ行を使う。
-- 訂正の行（correct=1）も、後の変更で最新でなくなった行（latest=0）も、後から取り込んだ方が残る
select *
from {{ ref('raw_houjin_bangou_records') }}
qualify row_number() over (
    partition by corporate_number, process, change_date
    order by _source_date desc, update_date desc
) = 1
