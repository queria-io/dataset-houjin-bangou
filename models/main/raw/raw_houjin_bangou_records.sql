{{
    config(
        materialized='incremental',
        incremental_strategy='append',
        full_refresh=false,
    )
}}

{# 読んだ CSV の行を、重複を除いてすべて溜める。法人番号の変更履歴の元になる。
   raw_houjin_bangou は法人番号ごとに最新の 1 行へ上書きされ、月次の全件で作り直されるので、
   過去の商号・所在地は残らない。こちらは full_refresh=false で全件の取り込みでも作り直さず、
   まだ持っていない行だけを足す。
   同じ行は seq と _source_date を除いた全列で判定する (_record_hash)。月次の全件に載る行の
   ほとんどは日次の差分で取り込み済みなので、足されるのは差分で取りこぼした行だけになる。 #}

{%- set record_columns = [
    'corporate_number', 'process', 'correct', 'update_date', 'change_date', 'name',
    'name_image_id', 'kind', 'prefecture_name', 'city_name', 'street_number',
    'address_image_id', 'prefecture_code', 'city_code', 'post_code', 'address_outside',
    'address_outside_image_id', 'close_date', 'close_cause', 'successor_corporate_number',
    'change_cause', 'assignment_date', 'latest', 'name_en', 'prefecture_en',
    'city_street_en', 'address_outside_en', 'furigana', 'hihyoji'
] %}

with src as (
    {{ read_houjin_csv(var('houjin_csv_paths', [])) }}
),

hashed as (
    select
        *,
        md5(concat_ws(chr(31)
            {%- for c in record_columns %}, coalesce({{ c }}, ''){% endfor %}
        )) as _record_hash
    from src
)

select * from hashed
qualify row_number() over (partition by _record_hash order by _source_date) = 1
{% if is_incremental() %}
    and _record_hash not in (select _record_hash from {{ this }})
{% endif %}
