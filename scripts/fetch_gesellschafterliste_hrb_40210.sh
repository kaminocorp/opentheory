#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -d /tmp/node_modules/playwright-core ]]; then
  (cd /tmp && npm install playwright-core@1.63.0 --silent)
fi
export NODE_PATH=/tmp/node_modules${NODE_PATH:+:$NODE_PATH}
exec node "$ROOT/scripts/fetch_gesellschafterliste_hrb_40210.js" "$@"
