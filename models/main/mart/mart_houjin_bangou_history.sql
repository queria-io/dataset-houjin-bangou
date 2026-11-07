{{ config(materialized='table') }}

{# 法人番号ごとの変更履歴。1 行が 1 回の変更（新規・商号変更・所在地変更・閉鎖など）の後の状態。
   取り込みを始めた時点の全件データが各法人の最初の行になり、それ以降の変更が日次の差分から足される。 #}

with records as (
    select * from {{ ref('raw_houjin_bangou_records') }}
),

-- 訂正などのとき、差分には最新でない行（latest=0）も含めてその法人の履歴がまとめて載る。
-- その日の履歴を正とし、それより前に取り込んだ行は使わない
resent as (
    select corporate_number, max(_source_date) as resent_date
    from records
    where latest = '0'
    group by all
),

kept as (
    select r.*
    from records r
    left join resent s using (corporate_number)
    where s.resent_date is null or r._source_date >= s.resent_date
),

-- 同じ変更（法人番号・処理区分・変更年月日）が何度か載ったときは、最後に取り込んだ行を使う
deduped as (
    select *
    from kept
    qualify row_number() over (
        partition by corporate_number, process, change_date
        order by _source_date desc, update_date desc
    ) = 1
),

ordered as (
    select
        *,
        row_number() over w as history_seq,
        count(*) over (partition by corporate_number) as history_count,
        lag(name) over w as previous_name,
        lead(change_date) over w as next_change_date,
        prefecture_code || city_code as lg_code5
    from deduped
    window w as (
        partition by corporate_number
        order by change_date, latest, update_date, _source_date, seq::bigint
    )
),

-- 最新の行が検索対象除外の法人は、過去の行も含めて載せない
excluded as (
    select corporate_number
    from ordered
    where history_seq = history_count and hihyoji = '1'
)

select
    corporate_number,
    history_seq,
    (history_seq = history_count)                   as is_latest,
    process,
    correct,
    cast(change_date as date)                       as change_date,
    cast(next_change_date as date)                  as next_change_date,
    cast(update_date as date)                       as update_date,
    name,
    -- 商号が変わった行でだけ入れる
    case when previous_name <> name then previous_name end as previous_name,
    kind,
    prefecture_name,
    city_name,
    street_number,
    prefecture_code,
    city_code,
    case
        when lg_code5 is not null and length(lg_code5) = 5
        then {{ lg_code_with_check_digit('lg_code5') }}
    end                                             as lg_code,
    post_code,
    address_outside,
    cast(close_date as date)                        as close_date,
    close_cause,
    successor_corporate_number,
    change_cause,
    cast(assignment_date as date)                   as assignment_date,
    name_en,
    furigana
from ordered
where corporate_number not in (select corporate_number from excluded)
order by corporate_number, history_seq
