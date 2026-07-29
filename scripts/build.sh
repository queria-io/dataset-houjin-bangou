#!/usr/bin/env bash
set -euo pipefail
# incremental (日次差分) は公開済み raw の max(_source_date) を基準に未取込分を
# 判定するので、公開済みカタログの取り込みが前提。queria sync が pull から始める
exec "$(dirname "$0")/../shared/scripts/build-dataset.sh"
