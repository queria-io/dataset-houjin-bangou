{# 国税庁 法人番号 CSV (全件 00_zenkoku_all_YYYYMMDD.csv / 差分 diff_YYYYMMDD.csv)
   https://www.houjin-bangou.nta.go.jp/download/
   Unicode(UTF-8), ヘッダーなし, 30カラム, BOM なし。全件・差分とも同一スキーマ。
   英語名フィールドに二重引用符のエスケープ ("K" → ""K"") が含まれるため、
   quote / escape を明示しないとパースに失敗する。
   paths は main.py が解決した zip:// パスのリスト
   (全件は1要素、差分は対象日数分)。filename からファイル名の日付(YYYYMMDD)を
   取り出し _source_date とする (差分の取り込み済み日付の判定に使う)。 #}
{% macro read_houjin_csv(paths) %}
select
    * exclude(filename),
    strptime(regexp_extract(filename, '(\d{8})'), '%Y%m%d')::DATE as _source_date
from read_csv(
    [{% for p in paths %}'{{ p }}'{{ "," if not loop.last }}{% endfor %}],
    header=false,
    quote='"',
    escape='"',
    filename=true,
    columns={
        'seq':                        'VARCHAR',
        'corporate_number':           'VARCHAR',
        'process':                    'VARCHAR',
        'correct':                    'VARCHAR',
        'update_date':                'VARCHAR',
        'change_date':                'VARCHAR',
        'name':                       'VARCHAR',
        'name_image_id':              'VARCHAR',
        'kind':                       'VARCHAR',
        'prefecture_name':            'VARCHAR',
        'city_name':                  'VARCHAR',
        'street_number':              'VARCHAR',
        'address_image_id':           'VARCHAR',
        'prefecture_code':            'VARCHAR',
        'city_code':                  'VARCHAR',
        'post_code':                  'VARCHAR',
        'address_outside':            'VARCHAR',
        'address_outside_image_id':   'VARCHAR',
        'close_date':                 'VARCHAR',
        'close_cause':                'VARCHAR',
        'successor_corporate_number': 'VARCHAR',
        'change_cause':               'VARCHAR',
        'assignment_date':            'VARCHAR',
        'latest':                     'VARCHAR',
        'name_en':                    'VARCHAR',
        'prefecture_en':              'VARCHAR',
        'city_street_en':             'VARCHAR',
        'address_outside_en':         'VARCHAR',
        'furigana':                   'VARCHAR',
        'hihyoji':                    'VARCHAR'
    }
)
{% endmacro %}
