#!/usr/bin/env bash
set -euo pipefail
# incremental (日次差分) は公開済み raw の max(_source_date) を基準に未取込分を
# 判定するので、公開中のバージョンが前提。build-fdl.sh は apply ブランチの fdl clone から始まる
# 記述 (*.tabledoc.yml) の無いテーブル (stg のビュー) は掲載しない
export FDL_UNDESCRIBED="${FDL_UNDESCRIBED:-hidden}"
exec "$(dirname "$0")/../shared/scripts/build-fdl.sh" "$@"
