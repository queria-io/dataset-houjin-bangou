#!/usr/bin/env bash
set -euo pipefail
# incremental (日次差分) は公開済み raw の max(_source_date) を基準に未取込分を
# 判定するので、公開中のバージョンが前提。build-fdl.sh は fdl checkout から始まる
# 記述 (*.table.yml) の無いテーブル (stg のビュー) は掲載しない
export FDL_UNDESCRIBED="${FDL_UNDESCRIBED:-unlisted}"
exec "$(dirname "$0")/../shared/scripts/build-fdl.sh" "$@"
