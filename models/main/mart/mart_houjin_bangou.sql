{{ config(materialized='table') }}

-- 現存法人の最新情報のみ:
--   is_latest    最新履歴（全件データでは常に真だが将来の差分取込に備えて明示）
--   not is_excluded  検索対象除外でない
--   not is_closed    登記記録が閉鎖されていない
-- 閉鎖・承継関連の列は現存法人では常に NULL のため EXCLUDE する。
SELECT * EXCLUDE (
    is_latest, is_excluded, is_closed,
    close_date, close_cause, successor_corporate_number
)
FROM {{ ref('stg_houjin_bangou') }}
WHERE is_latest
  AND NOT is_excluded
  AND NOT is_closed
