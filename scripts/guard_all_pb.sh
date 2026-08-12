#!/usr/bin/env bash
# 守卫：防止 all_pb.csv（全A中位PB历史基线）被清空/误删后提交。
#
# 该文件是行业拥挤度分母兜底数据，误删会导致温度计整组标灰。
# 曾因误判为"cache"被清空到 2 行（见 #821），故加此硬守卫：
# pre-commit 在提交前检查行数，低于阈值即拒绝。
#
# 重新生成：cd backend && pdm run python scripts/prefetch_all_pb.py
set -euo pipefail

TARGET="backend/app/services/thermometer/data/all_pb.csv"
# 完整历史约 5000+ 行，低于此值视为被清空/截断
MIN_ROWS=1000

if [ ! -f "$TARGET" ]; then
  echo "❌ 缺失必要基线数据：$TARGET" >&2
  echo "   禁止删除；请用 scripts/prefetch_all_pb.py 重新抓取后提交" >&2
  exit 1
fi

ROWS=$(wc -l < "$TARGET" | tr -d ' ')
if [ "${ROWS:-0}" -lt "$MIN_ROWS" ]; then
  echo "❌ $TARGET 行数异常(${ROWS} < ${MIN_ROWS})，疑似被清空/截断，提交被拒绝。" >&2
  echo "   重新生成：cd backend && pdm run python scripts/prefetch_all_pb.py" >&2
  exit 1
fi

echo "✅ all_pb.csv 基线数据完整(${ROWS} 行)"
