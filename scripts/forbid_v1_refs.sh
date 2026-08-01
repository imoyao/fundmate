#!/usr/bin/env bash
# Guard: V1 (fundmate) 已于 2026-08-01 退役清除。
# 任何对 backend.fundmate / from fundmate / import fundmate 的新引用都视为回归，
# 应在 CI / pre-commit 中运行本脚本以永久禁止 V1 引用死灰复燃。
set -euo pipefail

cd "$(dirname "$0")/.."

if grep -rn --include='*.py' -E 'backend\.fundmate|from fundmate|import fundmate' backend/app backend/tests 2>/dev/null; then
  echo "ERROR: 发现 V1 (fundmate) 引用，V1 已退役，禁止回引。" >&2
  exit 1
fi

echo "OK: backend/app 与 backend/tests 无 V1 (fundmate) 引用。"
