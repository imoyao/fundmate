#!/usr/bin/env bash
#
# dev.sh —— 本地一键启动前后端开发服务
#
# 用法：
#   ./scripts/dev.sh            # 依赖已就绪时，直接启动
#   ./scripts/dev.sh --install  # 启动前重新安装前后端依赖
#
# 启动后：
#   前端  http://localhost:8848
#   后端  http://localhost:8000  （API 文档 Swagger UI: http://localhost:8000/docs）
#
# 按 Ctrl + C 退出，脚本会一并清理前后端进程树。
#
set -uo pipefail

# 仓库根目录（本文件位于 <root>/scripts/）
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# ---------- 解析参数 ----------
INSTALL=0
for arg in "$@"; do
  case "$arg" in
    --install) INSTALL=1 ;;
    *) echo "未知参数: $arg" >&2 ;;
  esac
done

# ---------- 依赖准备 ----------
if [[ "$INSTALL" -eq 1 || ! -d "$BACKEND/.venv" ]]; then
  echo "📦 安装后端依赖 (pdm) ..."
  (cd "$BACKEND" && pdm install) || { echo "❌ 后端依赖安装失败" >&2; exit 1; }
fi

if [[ "$INSTALL" -eq 1 || ! -d "$FRONTEND/node_modules" ]]; then
  echo "📦 安装前端依赖 (pnpm) ..."
  (cd "$FRONTEND" && pnpm install) || { echo "❌ 前端依赖安装失败" >&2; exit 1; }
fi

# ---------- 进程清理 ----------
# Windows(Git Bash) 下用 taskkill 杀掉整个进程树；其他平台回退到 kill。
kill_tree() {
  local pid="$1"
  [[ -z "$pid" ]] && return
  if command -v taskkill >/dev/null 2>&1; then
    # 优先用 Git Bash/MSYS 惯用的 //T（避免被当成路径转换）；
    # 个别环境（如部分 taskkill 实现）只认单斜杠，故失败回退 /T。
    if taskkill //T //F //PID "$pid" >/dev/null 2>&1; then
      return
    fi
    taskkill /T /F /PID "$pid" >/dev/null 2>&1 || true
  else
    kill -TERM -"$pid" >/dev/null 2>&1 || kill -TERM "$pid" >/dev/null 2>&1 || true
  fi
}

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo ""
  echo "🛑 正在停止前后端服务 ..."
  if [[ -n "$FRONTEND_PID" ]]; then
    kill_tree "$FRONTEND_PID"
    FRONTEND_PID=""
  fi
  if [[ -n "$BACKEND_PID" ]]; then
    kill_tree "$BACKEND_PID"
    BACKEND_PID=""
  fi
  echo "✅ 已退出。"
}
trap cleanup EXIT INT TERM

# ---------- 启动后端 (Flask :8000) ----------
echo "🚀 启动后端  -> http://localhost:8000"
(
  cd "$BACKEND"
  exec pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

# ---------- 启动前端 (Vite :8848) ----------
echo "🚀 启动前端  -> http://localhost:8848"
(
  cd "$FRONTEND"
  exec pnpm dev
) &
FRONTEND_PID=$!

echo ""
echo "✅ 前后端已启动（Ctrl + C 退出）："
echo "   前端  http://localhost:8848"
echo "   后端  http://localhost:8000   API 文档: http://localhost:8000/docs"
echo ""

# 阻塞，直到任一进程退出或收到信号；随后清理另一个。
wait
cleanup
