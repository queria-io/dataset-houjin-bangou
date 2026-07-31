{{
    config(
        materialized='incremental',
        unique_key='corporate_number',
        incremental_strategy='delete+insert',
        post_hook="drop table if exists {{ make_backup_relation(this, 'table') }}",
    )
}}

{# post_hook は置き換えの後始末。--full-refresh のとき dbt は既存テーブルを
   __dbt_backup に改名して退避し、新しいものと入れ替えるが、退避したコピーを
   落とすのは「次にこのモデルを回したときの冒頭」になる。公開されるのはビルドが
   終わった時点のカタログなので、それでは raw と同じ大きさのコピーが次のビルド
   まで公開され続ける。落とす名前は自分で組み立てず make_backup_relation で dbt に聞く。
   差分実行のときは退避が起きないので、drop は対象なしで何もしない。 #}

{# houjin_csv_paths は main.py が解決した CSV(zip://) パスのリスト。
   全件(--full-refresh): 全件 zip 1要素。全行 latest=1・法人番号ごと1行なのでそのまま。
   差分(incremental):    対象日数分の diff zip。法人番号ごとに最新の latest=1 を1行へ集約し、
   delete+insert で既存行を置き換える。閉鎖・除外への遷移も latest=1 レコードに反映されるため、
   現存判定(mart)が全件スナップショットと同じ結果になる。 #}
with src as (
    {{ read_houjin_csv(var('houjin_csv_paths', [])) }}
)

{% if is_incremental() %}
select * exclude(_rn)
from (
    select
        *,
        row_number() over (
            partition by corporate_number order by _source_date desc
        ) as _rn
    from src
    where latest = '1'
)
where _rn = 1
{% else %}
select * from src
{% endif %}
