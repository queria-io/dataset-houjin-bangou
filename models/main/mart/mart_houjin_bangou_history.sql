{{ config(materialized='table') }}

{# 法人番号ごとの変更履歴。1 行が 1 回の変更（新規・商号変更・所在地変更・閉鎖など）の後の状態。
   元は全件データ・日次の差分・Web-API の期間指定（2015-12-01 以降）と法人番号指定の変更履歴。 #}

with deduped as (
    select * from {{ ref('stg_houjin_bangou_records') }}
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
