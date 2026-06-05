{# 国税庁 法人番号 全件データ (00_zenkoku_all_YYYYMMDD.csv)
   https://www.houjin-bangou.nta.go.jp/download/zenken/
   Unicode(UTF-8), ヘッダーなし, 30カラム, BOM なし。
   英語名フィールドに二重引用符のエスケープ ("K" → ""K"") が含まれるため、
   quote / escape を明示しないとパースに失敗する。
   url には main.py が解決した zip:// パスを渡す
   (例: zip:///abs/path/00_zenkoku_all_20260529.zip/00_zenkoku_all_20260529.csv)。#}
{% macro read_houjin_csv(url) %}
select *
from read_csv(
    '{{ url }}',
    header=false,
    quote='"',
    escape='"',
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
