{{ config(materialized='view') }}

WITH base AS (
    SELECT
        *,
        -- 都道府県コード(2桁) + 市区町村コード(3桁) = JIS X0402 の5桁コード。
        -- 国外所在地のみの法人は都道府県コードが NULL のため lg_code も NULL になる。
        prefecture_code || city_code AS lg_code5
    FROM {{ ref('raw_houjin_bangou') }}
)

SELECT
    corporate_number,
    seq,
    process,
    correct,
    CAST(update_date AS DATE)      AS update_date,
    CAST(change_date AS DATE)      AS change_date,
    name,
    kind,
    prefecture_name,
    city_name,
    street_number,
    prefecture_code,
    city_code,
    -- dataset-lg-code / dataset-zipcode と結合できる6桁(チェックディジット付き)コード
    CASE
        WHEN lg_code5 IS NOT NULL AND length(lg_code5) = 5
        THEN {{ lg_code_with_check_digit('lg_code5') }}
    END                            AS lg_code,
    post_code,
    address_outside,
    CAST(close_date AS DATE)       AS close_date,
    close_cause,
    successor_corporate_number,
    change_cause,
    CAST(assignment_date AS DATE)  AS assignment_date,
    name_en,
    prefecture_en,
    city_street_en,
    address_outside_en,
    furigana,
    -- 公開 mart の絞り込みに使うフラグ（mart で EXCLUDE する）
    (latest = '1')                 AS is_latest,
    (hihyoji = '1')                AS is_excluded,
    (close_date IS NOT NULL)       AS is_closed
FROM base
