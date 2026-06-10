#!/usr/bin/env bash
set -euo pipefail
target="${1:-local}"
# incremental (日次差分) は公開済み raw の max(_source_date) を基準に未取込分を
# 判定するため、公開済みカタログを取り込んでからビルドする (初回は未公開なので無視)。
uv run fdl pull "$target" || true
exec "$(dirname "$0")/../shared/scripts/build-dataset.sh" "$target"
