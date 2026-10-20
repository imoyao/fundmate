# CNB ↔ GitHub 正常态说明（2026-10-19）

> **一句话口径**：**GitHub 是唯一权威；CNB 只写代码、只推分支；所有「合并」都发生在 GitHub；CNB `dev` 由一条只 FF（fast-forward）的同步追平，永不自己长提交。**
>
> 本文是**方案草稿**（working-note），用于先对齐「正常情况长什么样」，再动 `.cnb.yml`。
> 落地后应升格为 `docs/dev/github-cnb-mirror.md` 的新一节 + `docs/spec/decisions.md` 一条决策。

---

## 1. 为什么要有这份说明

2026-10-19 实测了一次真实的双向分叉，代价是**一整轮人工收敛**：

| 指标 | 实测值 |
|---|---|
| 合基 | `07b432eb1`（当天 #2380 的搬运 merge） |
| GitHub `dev` 独有提交 | 31 笔 |
| CNB `dev` 独有提交 | 22 笔（含 #591–#602 一串**在 CNB 侧合并的 PR**） |
| 两侧都改过的文件 | 48 个（其中 44 个内容逐字节相同，仅 4 个不同） |
| 直接后果 | `git push` 被拒（`! [rejected] ... (fetch first)`）；`machine_branch` 通道因「有冲突就一个字节都不推」而**静默空转** |

收敛本身不难（本次只解了 2 个文件），**难的是没有人知道它已经在空转**。

而现实约束有两条，正是本方案要同时满足的：

1. **仓库以 GitHub 为主**（`main` 只由 GitHub 的发版 PR 推进）；
2. **日常会在 CNB 上用 NPC 开发** ⇒ 这条路必须**够自动**，否则两边各维护一遍，工作量不可接受。

---

## 2. 稳态：三条「出向」+ 一条「回向」

「出向」= CNB 的代码怎么到 GitHub；「回向」= GitHub 的结果怎么回到 CNB。

| # | 内容 | 通道 | 谁开 PR | 谁合 |
|---|---|---|---|---|
| A | CNB 的**功能分支**（含 NPC 开发） | `"**/!(main\|dev)"` 段 → git-sync 推**同名分支**（`.cnb.yml:478-493`） | ⚠️ **现在没人开** → 【补】CNB 侧脚本调 GitHub API 自动开 | 挂 `automerge` + 门禁绿 ⇒ `pr-auto-merge.yml` 自动合 |
| B | CNB `dev` 上万一存在的提交（**异常兜底**） | `machine_branch.py` 合两侧 → `bridge/github-dev`（`.cnb.yml:349-390`） | ✅ `dev-reconcile.yml:63-99` 自动建 PR + 挂 `automerge` | ✅ 同上 |
| C | **GitHub `dev` → CNB `dev`** | —— | —— | ❌ **这条路不存在**（pull cron 已在 CNB #450 删除）→ 【补】只 FF 的同步作业 <!-- cross-repo-ref-allow --> |

> **A 与 B 的区别不在「推没推」，而在「有没有 PR 与门禁」。**
> 门禁 `质量门禁汇总`（`ci.yml` 的 `gate`）只在 `pull_request` 事件上产生（`ci.yml:22`，各 job 带 `if: github.event_name == 'pull_request'`）。
> ⇒ **凡是没有经过 PR 的合并，都等于绕过了唯一红线。** 这也正是在 CNB 侧合 PR 的真实代价：不是「不合规」，是**那次合并没跑门禁**。

**稳态的判据（一句话）**：`CNB dev` 永远是 `GitHub dev` 的祖先（或相等）。
只要这条成立：A/B 都是「无冲突顺推」，C 永远是一条干净的 FF。

---

## 3. NPC 在 CNB 上的典型一天（目标：零人工点击）

```
 1. NPC 在 CNB 上从最新 dev 切分支 feat/xxx，写代码
 2. NPC push  ↑ 触发 CNB 构建 → `"**/!(main|dev)"` 段把 feat/xxx 推到 GitHub 同名分支
 3.                └─【补】同一构建里的脚本任务：调 GitHub API 开 PR（base=dev）+ 挂 automerge
 4. GitHub PR 打开 → CI 跑起来（质量门禁汇总 + 自动变基 pr-auto-rebase）
 5. 门禁绿 → pr-auto-merge 自动合入 GitHub dev
 6. 【补】FF 同步作业：GitHub dev → CNB dev（merge --ff-only + push）
 7. NPC 下一次开工时 dev 已是最新 —— 回到第 1 步
```

**全程不需要人去 GitHub 点「合并」，也不需要有人在 CNB 上合 PR。**

---

### 3.1 分支生命周期：合并即自动删除（2026-10-19 实测）

- 仓库设置 **`delete_branch_on_merge = true`**（`gh api repos/imoyao/fundmate --jq .delete_branch_on_merge` → `true`），
  `allow_auto_merge = true`；且本仓**没有任何工作流或脚本自己删分支**（全仓 grep `delete-branch|delete_branch|--delete` 无命中）
  ⇒ PR 一旦被 `pr-auto-merge` 自动合入 `dev`，**GitHub 自动删掉 head 分支**，不需要人工清理。
- `bridge/github-dev` 也在自动删除之列，但它是一次性搬运分支（`dev-reconcile.yml` 每轮 `git branch -D` 重建 + `--force-with-lease` 强推），删掉无副作用。
- CNB 侧的源分支属 CNB 自己的命名空间，不受该设置影响；它留着**不影响同步**（同步只搬 `dev` 与被推送的分支），是「洁癖」而非「故障」。
- ⚠️ **但「分支被删」≠「CNB 收敛了」**：自动合并只推进 GitHub `dev`；CNB `dev` 仍要靠 §2 的 **C 通道**（只 FF 同步）。
  **没有 C，合并完 CNB 依然落后**——2026-10-19 那次就是人工 FF 补的。



| 作业 | 触发 | 幂等键 | 失败时必须怎样 |
|---|---|---|---|
| A 自动开 PR【新增】 | `"**/!(main\|dev)"` 的 `push:` | `GET /pulls?state=open&head=OWNER:<branch>&base=dev` 非空则**直接跳过** | 建 PR 失败 ⇒ **退非零**（不得静默："分支推上去了但没人提 PR" 正好是本方案要消灭的形态） |
| 挂 `automerge` 标签 | 同上 | `POST /issues/<n>/labels` 天然幂等 | 标签没挂上 ⇒ 退非零（否则 PR 会静静躺在那里等人点） |
| B bridge 搬运 | CNB `dev` push | 比对两侧 ref | 有冲突 ⇒ 现在**只打日志**（`.cnb.yml:383-386`）→ 【补】**建卡**；`dev-reconcile.yml` 的每日重建是它的兜底 |
| C FF 同步【新增】 | cron（建议 30–60 分钟一次） | `git merge-base --is-ancestor <gh/dev> <cnb/dev>` | 不是祖先 ⇒ **不 merge、不 push**，退非零并打印「CNB dev 有 GitHub 没有的提交，先跑收敛」；拿不到输入 ⇒ 退 2 且声明结论不可信 |
| 分叉自检 | CNB `main` cron（现成） | `git cherry` 双向（`check_cross_repo_dev_divergence.py`） | 两侧都有 `+` ⇒ 退 1；拿不到输入 ⇒ 退 2 |

**所有新增作业都必须满足**：① 幂等（重跑只多几次 API 调用，不产生新副作用）；② **失败态可见**（"拿不到输入" 必须区别于 "结论为空"，参考 #171 的教训）；③ **绝不 force**。

---

## 5. 新增 stage 必须同步挂上的判据与守卫

`.cnb.yml` 每加一段，就要过一遍现有的静态守卫（本地全绿再提 PR）：

| 守卫 | 它管什么 |
|---|---|
| `scripts/guard_cnb_events.py` / `scripts/check_cnb_events.py` | 事件必须写在**分支键之下**（#152） |
| `scripts/guard_cnb_yml_duplicate_keys.py` | 重复 `dev:` 键会让 CNB 严格解析器直接拒（Prepare 就死） |
| `scripts/guard_cnb_script_task_python.py` | 脚本任务必须自带 `docker.image: python:3.12-slim`（#461） |
| `scripts/guard_cnb_script_task_git.py` | `python:3.12-slim` **不含 git**，脚本内要自证（#517） |
| `scripts/guard_git_sync_push_scope.py` | 两个方向都必须显式写 `branch`，且不得碰 `main` |
| `scripts/guard_secret_imports.py` | 密钥文件只能挂在插件任务级 `imports` |
| `scripts/guard_cron_job_reachability.py` / `guard_job_schedule_coverage.py` / `guard_cron_covers_active_branch.py` / `guard_schedule_checkout_ref.py` | cron/调度形态自证（"挂了但没跑" 是历史高发病） |
| `scripts/guard_bridge_machine_branch_single_writer.py` | 机器分支只允许一个写者 |
| `scripts/guard_rule_registry.py` | **新规矩必须登记**（且 runner 与实际执行点一致），纯文字规则预算只减不增 |

---

## 6. 明确不做（边界）

1. **不 force 任何长期分支**（`dev` / `main`）。C 用的 `--ff-only` 就是这条的机器化表达：做不到就红，不"修"。
2. **不自动解治理文件冲突**（`.cnb.yml` / `AGENTS.md` / `ci.yml`）。解错 = 悄悄改治理规则，`dev_converge.py` 有意不提供 `--resolve`。
3. **`main` 不经 CNB 外推**（`branch: dev` 收窄的既有决策不动）。
4. **不把「在 CNB dev 上直接提交」当正常路径**：它是异常，C 会红——这正是「不许绕道」的判据。
5. **不在 CNB 侧新增「跨仓搬运 PR」层**：搬运走 B（`bridge/github-dev`）已有通道；A 开的是**功能分支 → dev** 的**变更** PR，性质不同（见 §9）。

---

## 7. 异常与自愈

| 症状 | 判据 | 处置 |
|---|---|---|
| 两侧各有独有提交 | `git cherry` 双向都有 `+`（`check_cross_repo_dev_divergence.py`） | 等 `dev-reconcile.yml`（每日，`-X ours` 重建）或人工 `dev_converge.py --apply` |
| CNB `dev` 不是 GitHub `dev` 的祖先 | C 作业退非零 | 说明有人在 CNB `dev` 上直接提交或合了 PR → 先查是谁，再决定收敛方向 |
| 分支推上去了但没有 PR | A 的幂等键查不到 open PR，且脚本退非零 | 立刻可见，重跑即补 |
| bridge 通道三天没动静 | 看板上无 `bridge/github-dev` PR | 【补】冲突建卡后当天可见 |
| 拿不到 token / 网络不通 | 退 2，打印「结论不可信」 | **不得**降级成"已对齐"（#171 的形态） |

---

## 8. 回滚

- 每个新增能力都是**一个独立 stage** ⇒ 删 stage 即关，无需回滚数据。
- 关掉后要同步收回守卫白名单（`guard_cron_*` / `guard_rule_registry.py` 的登记），否则会出现"登记了但没跑"的孤儿判据。
- 回滚后的验收口径（不是"构建绿了"）：`git ls-remote` 两侧 `refs/heads/dev` 是否一致 + 分叉自检退 0。

---

## 9. 与既有决策的关系（为什么这条路不与它们冲突）

| 既有决策 | 是否冲突 | 理由 |
|---|---|---|
| #450 删除 pull cron | 不冲突 | 那里反对的是插件的 `pull --rebase` + `push --force`（83 笔提交 79 笔冲突）；C 用的是 `--ff-only`，做不到就红，不会改写历史 |
| §21「治理文件只在 CNB 侧改」 | 不冲突 | A/C 不碰治理文件的**内容**；`.cnb.yml` 自身的改动仍建议只在 CNB 侧做，避免 `-X ours` 把它按 GitHub 侧解掉 |
| §18「CNB 不为跨仓搬运开 PR」 | 不冲突 | 那里说的是**搬运**（同一批已 review 的提交换个分支名再开一层 PR，只增噪声）；A 是**变更**（新代码必须过门禁才能进 dev） |
| D57「认领同步」 | 不冲突 | 那条管的是**卡片维度**「谁在动这张卡」；本文管的是**代码维度**「怎么落到 dev」 |
| 「质量门禁不能关」 | 强化 | A 让每次合并都必然经过 PR ⇒ 门禁**无法被绕过**（现在在 CNB 合 PR 就绕过了它） |

---

## 10. 落地顺序（三步，各自可独立回滚）

**Step 1 — 自动开 PR（收益最大、风险最小）**
在 `"**/!(main|dev)"` 段追加一个脚本任务：推完分支后调 GitHub API 开 PR + 挂 `automerge`。
实现可直接抄 `dev-reconcile.yml:67-99`（约 30 行纯 `urllib`）；凭据走已有的 `claim-sync-env.yml` 里的 `GITHUB_PAT`（`claim_detect.py --apply` 已在生产用它调 GitHub API）。

**Step 2 — bridge 通道冲突建卡**
`machine_branch.py` 退出 1 时建一张卡（幂等键 = 分支名 + 日期）。修的是「作业成功 ≠ 作业做对了」那一类静默：#450 的 224 张重复卡已经教过一次。

**Step 3 — GitHub `dev` → CNB `dev` 的 FF 同步**
CNB 侧 cron：`fetch <github> dev` → `merge --ff-only` → `push origin dev`。
⚠️ **有前置条件**：必须等 bridge 通道把 CNB 那 8 个文件搬进 GitHub `dev` 之后才可能成功（见 §11）。

---

## 11. 未决 / 待确认（动手前必须问清）

1. **CNB `dev` 的保护规则**：上面这些作业能不能直接 push `dev`？（CNB 侧保护规则匿名读不到，返 401 ⇒ 需要你在 CNB 上确认）
2. **`GITHUB_PAT` 的权限范围**：自动开 PR 需要 `pull_requests: write`。现在已知它能 push（git-sync）与挂标签/发评论（claim_detect），但**开 PR 需要实测**。
3. **NPC 的工作形态**：NPC 是「推分支」（走 `push:` 事件，通道 A 可用），还是只在 CNB 侧评论/建卡（那 A 用不上，得换别的挂钩）？
4. **当前时点的分叉余量**：2026-10-19 收敛后合基已前移到 `d9f3c961`，两侧各领先 8 个文件、**零交集**（CNB 侧是 8 个 bridge/治理文件，GitHub 侧是 GitHub #2404 的 8 个后端文件）。Step 3 要等这批搬完。

---

## 附：本次收敛的实测记录（供判据参考）

- 收敛提交 `bb11457ee`（父 = CNB `ef9ada474` + GitHub `d9f3c961`），以 `--ff-only` 语义推回 CNB `dev`（`ef9ada474..bb11457ee`）。
- 冲突 2 处：`DomainEDividendTaxTable.vue` 取 GitHub 版（＝CNB 版 + GitHub #2383 字阶修复，blob 相同）；`scripts/bridge/cleanup_duplicate_mirrors.py` 取 CNB 版（含 `CLOSE_NOTE_MARKER`）。
- 验证：`scripts/tests` **410 tests OK**；`ci.yml` 里 19 个 Python 守卫全部 `rc=0`。
- 过程副产品（**假绿**）：`scripts/bridge/check_cross_repo_dev_divergence.py` 的 `--cnb-url` **默认取 `origin` 的 URL**；在 origin 指向 GitHub 的本地克隆里跑，两侧都从 GitHub 拉 ⇒ 打印「✅ 未分叉」。本地必须显式传 `--cnb-url https://cnb.cool/duoduobei/fundmate.git`。**判据拿错输入源 ⇒ 结论反了**，应单独修。

---

## 12. 2026-10-20 更新：Step 3 已落地（回向只 FF）+ 顺手补了「判据前移」

§10 的 Step 3 **已实现**；同时补了 §10 没写、但对「NPC 改出问题」更直接的一半：把门禁判据搬到 CNB 侧，
让作者在**推的当场**看见红，而不是等搬运到 GitHub 之后。

### 12.1 回向：`scripts/bridge/ffback_cnb_dev.py`

- 判定 `same` / `ff` / `cnb_ahead` / `diverged` / `unknown`，取数与 `check_cross_repo_dev_divergence.py` **同一套**（不重写判据）。
- 退出码 **0 / 1（真分叉）/ 2（拿不到输入）/ 3（推送被拒）**；**永不 force**。1 与 3 分开，因为处置完全不同：分叉要人来合（`dev_converge.py`），推不上去要人开权限。
- 挂三处（同一个 `&ffback-job` 锚点）：`dev: push`（搬完立刻补齐）、`dev:` 每日 cron（兜底）、`$: web_trigger`（手动）。三处共用锚点，`guard_bridge_sync_reachable.py` 的集合等价判据自动成立。
- 前置条件（§10 Step 3 那条）**已满足**：GitHub #2412（head `fix/cnb-dev-merge`）已于 2026-10-20 00:16 合入 GitHub `dev`，bridge 搬运通道本身是通的。

### 12.2 判据前移：`"**/!(main|dev)": push` 上的 `&judge-job`

跑与 `ci.yml` 的 `scripts_test` **同一批**脚本（14 条 python 守卫 + `guard_cross_repo_refs.mjs`），
现场装 git / nodejs / pyyaml；**装不上即 `exit 1`**（不静默跳过，源 CNB #171 的失败态纪律）。
排除 `guard_mojibake.py`：它按提交范围取文件，CNB 检出形态下会恒红，乱码仍由 GitHub 侧 job 守。

为什么是这一批：桥 PR 上那 16 处跨仓裸引用不是「不会写」，是**作者在 CNB 侧收不到反馈**。

### 12.3 §11 四条未决，现在的状态

| # | 状态 |
|---|---|
| 1 CNB `dev` 保护：构建身份能否 push | **仍未实测**（CNB 构建日志本机读不到，需在 CNB 侧看首次回向的退出码；`rc=3` 的处置写在 `.cnb.yml` 注释里） |
| 2 `GITHUB_PAT` 能否自动开 PR | **已由证据回答**：GitHub #2412 就是桥自动开出来的 PR，并已合并 ⇒ 有 `pull_requests: write` |
| 3 NPC 工作形态 | 与本轮无关（未变） |
| 4 分叉余量 | 已收敛并与 GitHub `dev` 同基；本轮回向就是防它再岔开 |

### 12.4 §附 那条「假绿」的处置边界

`ffback_cnb_dev.py` 里**已挡**：两侧输入源归一后相同 ⇒ 直接 `rc 2` 并打印「结论不可信」，不进入 sha 比较。
但 `check_cross_repo_dev_divergence.py` 自己的默认值**没改**（本轮不动它，避免把两件事混在一个提交里）——
单独跑那个脚本时**仍须显式传** `--cnb-url`，建议另开一张卡修它的默认值。

### 12.5 未实测的部分（别读成「已验证」）

本机读不到 CNB 构建结果（`api.cnb.cool` 匿名一律 `errcode 16`，`/-/builds` 也 404），所以
「判据 stage 在 `python:3.12-slim` 里装得上 nodejs / pyyaml」与「回向首次推送的退出码」都**只是设计与本地实证**，
需要在 CNB 侧首跑之后回填结论。机制与本地证据见 `docs/dev/github-cnb-mirror.md` §30。
