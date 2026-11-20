#!/usr/bin/env bash
# dependabot 锁重生成 + 分支重建的编排脚本（#2434 的机制，本文件是 #3205 脚本化瘦身产物）。
#
# 为什么把编排逻辑从 .github/workflows/dependabot-lockfile-regen.yml 收进本脚本：
#
#   该 workflow 因依赖 bot 触发，必须保留 `pull_request_target`（见 #2803）⇒ 它的
#   workflow 定义（包括原来 run: 里那一大段内联 bash）**锁死在默认分支 main**，
#   dev 上的改动要等 dev → main 发版才生效。把编排逻辑搬进本脚本后，workflow 定义
#   退化成「取脚本 + 一行调用」，而脚本本体经 `git show origin/dev:scripts/...` 取
#   **dev 上那一版** ⇒「怎么修锁」改一次、下次运行即生效，不必等发版。
#
# 环境变量（由 workflow 注入，表达式先落 env 再引用，防 CodeQL 判 critical 注入）：
#   EVENT_NAME  : github.event_name（push = dev 前进后的重扫；否则 = PR 事件）
#   PR_HEAD_REF : github.event.pull_request.head.ref（仅 PR 事件；push 下为空）
#   REPO        : github.repository
#   GH_TOKEN    : secrets.GITHUB_TOKEN（gh 命令用）
#
# 边界与「每条对应一次真实事故」的完整说明见 workflow 文件头（#2434），本脚本只承载执行编排。
set -euo pipefail

git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git fetch origin dev

# 三个脚本一律取 **dev 上那一版**：任一缺失都是「机制完全没跑」，显式红，
# 不静默降级（空 ≠ 没拿到，见 AGENTS.md）。
for f in regen_pnpm_lockfile.mjs rebuild_dependabot_branch.py pr_autorebase_approve.py; do
  if ! git show "origin/dev:scripts/$f" > "/tmp/$f" 2>/dev/null; then
    echo "::error::origin/dev 上缺 scripts/$f —— 本工作流无法执行"
    exit 1
  fi
done

approve() {
  local sha="$1" rc=0
  set +e
  python3 /tmp/pr_autorebase_approve.py --repo "$REPO" --sha "$sha"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "::warning::推送后的自动批准未完成（rc=$rc）——该 PR 的 CI 可能挂死，请人工批准"
  fi
}

# 只重生成锁（旧路径）：分支已包含 dev，或重建不适用时走这里。
regen_only() {
  local b="$1" rc_total=0 d rc=0
  git fetch origin "$b"
  git checkout -B "$b" "origin/$b"
  # 上一轮已经是本工作流推的锁：跳过，避免「推回 → synchronize → 再跑」空转。
  if [ "$(git log -1 --format=%ae)" = "github-actions[bot]@users.noreply.github.com" ]; then
    echo "最新提交已是锁重生成，跳过"
    return 0
  fi
  DIRS=$(git diff --name-only origin/dev..."$b" -- '*pnpm-lock.yaml' \
    | sed -E 's#/?pnpm-lock.yaml$##' | sed -E 's#^$#.#' | sort -u)
  if [ -z "$DIRS" ]; then
    echo "本 PR 未改 pnpm-lock.yaml，无需重生成"
    return 0
  fi
  echo "待重生成的目录: $DIRS"
  for d in $DIRS; do
    echo "::group::regen $d"
    set +e
    node /tmp/regen_pnpm_lockfile.mjs --dir "$d" --base-ref origin/dev --apply
    rc=$?
    set -e
    echo "::endgroup::"
    if [ "$rc" -ne 0 ]; then
      # 不推送：脚本已在内部回滚锁文件（失败态不留半成品）。
      echo "::error::锁重生成失败（dir=$d rc=$rc）——不推送坏锁"
      rc_total=$rc
    fi
  done
  [ "$rc_total" -eq 0 ] || return "$rc_total"
  if git diff --quiet -- '*pnpm-lock.yaml'; then
    echo "重生成后无差异：PR 的锁本来就可用"
    return 0
  fi
  git add -- '*pnpm-lock.yaml'
  git commit -F /tmp/commit-msg.txt
  git push origin "HEAD:$b"
  approve "$(git rev-parse HEAD)"
}

cat > /tmp/commit-msg.txt <<'MSG'
chore(deps): 重生成 pnpm 锁（dependabot 重写丢 peer 条目，#2434）

dependabot 不跑 pnpm，而是文本级重写 pnpm-lock.yaml，会丢掉 peer-suffixed
条目，导致 `pnpm install --frozen-lockfile` 报 ERR_PNPM_LOCKFILE_MISSING_DEPENDENCY。

本提交由 dependabot 锁重生成通道生成：
以 dev 上那份 pnpm 认可的锁为基线，按本 PR 的 package.json 重生成，
并把改动过的依赖钉回 manifest 声明的版本；收尾已跑 --frozen-lockfile 自证。
MSG

if [ "$EVENT_NAME" = "push" ]; then
  # dev 前进后的重扫：只认 base=dev、作者是 dependabot 的 open PR。
  BRANCHES=$(gh pr list --base dev --state open --author "app/dependabot" \
    --json headRefName --jq '.[].headRefName')
  SWEEP=1
else
  BRANCHES="$PR_HEAD_REF"
  SWEEP=0
fi
if [ -z "${BRANCHES:-}" ]; then
  echo "无待处理的 dependabot 分支"
  exit 0
fi

failures=0
for b in $BRANCHES; do
  echo "---- 处理 $b ----"
  git fetch origin "$b"
  OLD_SHA=$(git rev-parse "origin/$b")

  # ① 重建分支：把「落后 dev」与「锁冲突」一起消掉（撞锁的唯一正解）。
  set +e
  python3 /tmp/rebuild_dependabot_branch.py \
    --branch "$b" --base origin/dev --regen-script /tmp/regen_pnpm_lockfile.mjs --apply
  RB=$?
  set -e
  if [ "$RB" -eq 0 ]; then
    NEW_SHA=$(git rev-parse HEAD)
    if [ "$NEW_SHA" = "$OLD_SHA" ]; then
      echo "$b 无需重建（内容已是最新）"
      continue
    fi
    # `--force-with-lease` 带确切旧值：并发推送时宁可失败，也不覆盖别人的提交。
    git push --force-with-lease="refs/heads/$b:$OLD_SHA" origin "HEAD:refs/heads/$b"
    approve "$NEW_SHA"
    continue
  fi
  if [ "$RB" -eq 3 ]; then
    # ② 重建不适用（改了 manifest/锁之外的文件、或 dev 动过同一份 manifest）：
    # 退回「只重生成锁」。冲突仍需人看，但锁至少是好的，红灯原因不会被锁污染。
    echo "::warning::$b 不适用重建（见上一行 reason）——退回只重生成锁"
    if ! regen_only "$b"; then
      failures=$((failures + 1))
    fi
    continue
  fi
  echo "::error::$b 重建失败（rc=$RB）——未推送任何内容"
  failures=$((failures + 1))
done

if [ "$failures" -ne 0 ]; then
  if [ "$SWEEP" -eq 0 ]; then
    exit 1
  fi
  # 重扫模式不把整条 dev 推送判红（分支已逐个处理），但必须浮到 run 页面上，
  # 别只躺在日志里（只进日志等于没写）。
  echo "::warning::重扫中有 $failures 个分支未能自动处理，见上方 ::error:: 行"
fi
