---
title: 前后端分离项目中使用 github-action
---
## 如何在子目录运行 action

- [github - Running actions in another directory - Stack Overflow](https://stackoverflow.com/questions/58139175/running-actions-in-another-directory)

```yml
name: CI

on: [push]

jobs:
  phpunit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v1
      - name: Setup and run tests
        working-directory: ./app
        run: |
          cp .env.dev .env
          composer install --prefer-dist
          php bin/phpunit
```

## ⚠️ `pull_request_target` 的 **workflow 定义**取自默认分支（`main`），不是 PR 的 base 分支

**实测（2026-10-20，源 #2419）**：`pr-auto-rebase.yml` 的「变基后自动批准 approval-required runs」
（#2289，2026-10-17 合入 `dev`）**从未真正执行过**。

判据是把两侧 YAML 的 `run:` 脚本逐行拿去和真实构建日志比对（日志 `39290214996`，job `rebase`）：

| 定义来源 | 脚本非注释行数 | 日志里命中 | 未出现 |
|---|---|---|---|
| `origin/main` | 33 | **33** | 0 |
| `origin/dev` | 50 | 40 | **10**（`NEW_SHA=` / `for round in 1 2 3` / `gh api … action_required` …） |

`main` 的每一行都在日志里、`dev` 的批准循环一行都没有 ⇒ 执行的是 **`main` 的那份定义**。
抽查 10-19 当天 8 次 run（`39291973114` / `39290214996` / `39285642831` …）**全部**没有 `gh api`。

**推论（按影响排序）**

1. **CI 修复合入 `dev` 不会立即生效**：本仓 `main` 只由发版 PR（`dev` → `main`）推进，
   workflow 定义就冻在 `main` 上 —— 想让 `pull_request_target` / `schedule` 的改动生效，
   必须先发版。在那之前，`dev` 上的新逻辑一行也不会跑。
2. **`actions/checkout` 的 `ref:` 只解决「检出哪一版代码」，解决不了「跑哪一版 workflow」**：
   两者是两层。签名式写法是
   「定义出自 `main` + 检出与脚本显式取 `dev`（`ref: dev`、`git show origin/dev:<path>`）」——
   这样可以做到「定义虽旧，但**执行的内容**是新的」，改脚本类逻辑时不必等发版。
3. **与 `schedule` 是同一族问题，但那一处已有判据**：`scripts/guard_schedule_checkout_ref.py`
   （源 CNB #586）拦的是「定时作业检出了 `main` 的代码」；本节记的是**更靠前的一层** ——
   连 workflow 定义本身都来自 `main`，`ref:` 拦不到它。此处目前**没有判据**，只能靠读本文。
4. 观察到的现象（bot 推送后分支的 runs 卡在 `action_required`、checks 永远凑不齐、
   `automerge` 永不触发）**就是第 1 条的后果**，不是「窗口太短」：那段批准循环压根没跑。
   循环本身的脆弱点（30s 窗口 + 空结果被当成「没有待批」）仍在，
   已抽成 `scripts/pr_autorebase_approve.py`（#2419）以便单测与自证。

**验证一次发版后是否真的生效**（不要用「PR 已合并」代替）：

```bash
gh run list --workflow pr-auto-rebase.yml --limit 5 --json databaseId,createdAt
gh run view <id> --log | grep -c 'AUTOREBASE_APPROVE'   # >0 才说明新逻辑跑到了
```
