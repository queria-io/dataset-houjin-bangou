{{
    config(
        materialized='table'
    )
}}

{# houjin_zip_url は main.py が解決・ダウンロードした全件 zip 内 CSV の
   zip:// パス。dbt build --vars '{houjin_zip_url: ...}' で渡す。 #}
{{ read_houjin_csv(var('houjin_zip_url')) }}
