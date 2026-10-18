---
title: CNB → GitHub 回写（评论镜像）
status: v1（2026-10-11，源 CNB issue #2）
owner: 阿白
---

# CNB → GitHub 回写（评论镜像）

> 脚本：`scripts/bridge/cnb_github_backfill.py`　流水线：`.github/workflows/cnb-github-backfill.yml`
> 回归网：`backend/tests/test_cnb_github_backfill.py`　状态：`scripts/bridge/cnb_github_backfill_state.json`

## 1. 这东西解决什么

`github_cnb_issues.py` 把 GitHub 的卡**建到** CNB，但没有回头路：在 CNB 上把一张卡
分析完、结论落在 CNB 评论里，GitHub 上的人看不到。本作业把 CNB 侧的评论**回写**成
GitHub 上的评论，让「在 CNB 讨论」不再等于「GitHub 侧失明」。

## 2. 为什么是「GitHub 拉」而不是「CNB 推」

这是本方案唯一真正被环境逼出来的决定，值得写清楚：

**CNB 构建内没有 GitHub 凭证。** 实测（2026-10-11）：CNB 流水线环境变量里只有 `CNB_*`，
对 `api.github.com` 匿名 POST 返回 **401**。要在 CNB 侧推，就必须在 CNB 仓库存一个
GitHub PAT——把一个能写 issue 的长期凭据放在另一个平台上。

**反方向的凭据是现成的。** GitHub Actions 里 `GITHUB_TOKEN` 自动注入，且本仓库各处
已在用 `issues: write`（`close-linked-issues.yml` / `issue-milestone-guard.yml`）。

所以拓扑定为 **GitHub 定时拉 CNB**：CNB 侧是完全只读的消费方，不存任何 GitHub 凭据。
代价是**延迟**（最长一次 cron 间隔），对 issue 讨论可以接受。

## 3. 三条设计取舍

| 取舍 | 做法 | 为什么 |
|------|------|--------|
| **单向** | 只 CNB → GitHub，绝不在 CNB 建/改任何东西 | 与镜像方向同构；CNB 侧零写权限，出问题影响面最小 |
| **只增不覆盖** | 已回写过的评论永不重发、永不编辑 | CNB 侧改过的评论不会把 GitHub 上的旧副本改掉——**改写历史比留个过时副本更糟** |
| **不自动关卡** | 关闭动作两侧都不自动，只做人可读的对账 | #1177 用「PR 已合并」代替验收、误关整张卡的教训吃过一次 |

## 4. 幂等怎么保证

每条回写评论末尾带一行**隐藏标记**（HTML 注释，渲染不可见）：

```html
<!-- cnb-backfill: issue=2 comment=2109119676427591680 -->
```

回写前，脚本把目标 GitHub issue 的**全部**评论拉下来，用正则收集已有标记；命中的
`(cnb_issue, cnb_comment_id)` 直接跳过。所以**同一天跑十遍只会发一遍**。

三个细节都有回归网钉着（`TestMarker` / `TestBuildComment`）：

- **正则要够窄**：别的 `<!-- ... -->` 注释不能被误认成标记；
- **标记两侧空格容忍**：防「有人手改了一下就全部重发」；
- **长正文截断必须保住标记**：GitHub 单条评论上限 65536 字符，超了会 422。截断时按
  剩余额度裁正文、**把带标记的尾巴留出来**——这条是写测试时才发现的真实缺陷
  （见 §8）。

> ⚠️ 标记的**字面前缀** `<!-- cnb-backfill:` 是冻结契约，有断言钉着（`TestContract`）。
> 改它等于把所有已有回写认成「没写过」，下一轮会把全部 CNB 评论重发到 GitHub，且不可逆。

## 5. 怎么映射 CNB 卡 ↔ GitHub 卡

镜像卡正文顶部有 GitHub→CNB 脚本写入的溯源块，其中一行是原链接：

```
> - 来源：https://github.com/imoyao/fundmate/issues/783
```

脚本用正则从这行抠编号。**抠不到就跳过，绝不猜。**

这是本脚本最贵的一条边界：猜错编号 = 把评论贴到**别人的卡**上，比漏同步严重得多。
故回归网专门钉了四种「不该被认成映射」的情形（`TestResolveGithubNumber`）：

- 正文里没有该链接 → `None`；
- 链接指向**别的仓库** → `None`；
- 链接是 `/pull/123` 而非 `/issues/123` → `None`；
- 正文有多个链接 → 取**第一个**（溯源块在顶部，顺序稳定）。

> 📌 尚未映射的卡：CNB `#2`（本卡自身）。它是「源卡」而非镜像卡，正文里没有溯源块。
> 想让它也回写，**用评论区**补一条指向 `imoyao/fundmate#1568` 的说明（不要 edit 正文，
> 遵循 AGENTS.md「追加请续帖」）——但注意正文才是脚本读的地方，故这条目前要走
> 下面 §7 的「人工中转」。

## 6. 机器人评论：折叠，而不是拦掉（2026-10-18 修订，源 CNB #561）

> ⚠️ **本节已改口径。** 旧版写的是「机器人账号一律不回流」，那条口径的真实代价是
> **高价值结论一个字都到不了 GitHub**：NPC 在 CNB 卡上写下的「这条判据不成立」
> 「原卡数字是错的」，GitHub 侧读者完全看不到。闸门只看作者是谁，不看说了什么。
>
> 用户拍板（CNB #561）：**可以折叠，高价值内容默认展开；存量不补。**

判断谁是机器人不变：`is_bot()` —— `is_npc: true` 优先（最可靠）→ 用户名后缀 `[bot]`
→ 已知机器人名单兜底（历史数据里 `is_npc` 不一定都填了）。反过来的边界也还钉着：
**作者字段缺失时判定为「不是机器人」**（`test_none_author_is_not_bot`）。

变的是**拦不拦**：

| 作者 | 有结论标记 | 回写正文 |
|---|---|---|
| 真人 | — | 超过 `COLLAPSE_THRESHOLD`（2000 字）才折叠 |
| 机器人 | **有** | **默认展开**，摘要置于折叠条之外 |
| 机器人 | 无 | **一律折叠**（执行日志不铺屏），但正文完整保留 |

### 结论标记（NPC 自己声明「这段别折叠」）

```html
<!-- conclusion -->
结论：A 方案的判据不成立。
<!-- /conclusion -->
```

也认单行形态 `<!-- conclusion: 一句话结论 -->`。标记渲染不可见，回写时会被剥掉。

为什么要**显式声明**而不是「自动识别哪段像结论」：识别一定靠猜，猜错就是把本地执行
日志当结论铺给 GitHub 读者。**声明了才展开，没声明就折叠**——宁可漏展开，不可误展开。

### 存量不补

`NPC_INCLUDE_SINCE = 2026-10-18` 写死在脚本里，`run()` 必过 `default_since()`：

- 不传 `--since` → 下界就是它；
- 传了更早的 `--since` → 取**更晚**的那个（`--since` 只能收窄，不能撑大）。

写死而不是靠 `--since` 传，是因为后者**忘了带就把几千条存量全搬过去**，而 GitHub
评论发出去撤不回（不可逆）。真要全量补，得改代码过 review。

对应回归网：`TestNpcCollapse` / `TestStockNotBackfilled`（含接线层用例 —— 把 `run()`
里那行删掉，纯函数测试照样全绿，探针 P4 就是咬这个）。

## 7. 怎么跑

```bash
export GITHUB_TOKEN=<有 issues:write 的 PAT>

# 先看要回写什么（默认 dry-run，不写任何东西）
python scripts/bridge/cnb_github_backfill.py --dry-run

# 真正回写
python scripts/bridge/cnb_github_backfill.py --apply

# 只回写某时间之后的（ISO8601），或限制条数
python scripts/bridge/cnb_github_backfill.py --apply --since 2026-10-01
python scripts/bridge/cnb_github_backfill.py --apply --limit 3
```

依赖：**纯标准库**（`urllib`），不需要 `pip install`——故意保持这样，免得每日作业被某个
三方包的破坏性升级带崩。

读 CNB 侧**必须带 token**：`CNB_READ_TOKEN`（或 `CNB_TOKEN`）配进 GitHub 仓库 secret
（Settings → Secrets and variables → Actions）。**匿名一律 401**——2026-10-14 实测纠正：
`api.cnb.cool` 对匿名请求返回 `{"errcode":16,...}`，与仓库是否公开无关。本文档旧版
「匿名即可（公开仓库）」的说法是错的，正是它让三次定时运行全挂在第一步。

> 两侧措辞是同一事实（「匿名 401，与公开与否无关」）的两种写法，冲突时**保留其一**：
> 取 GitHub 侧版本（多写了 secret 配在哪，对读者更有用）。

## 8. 流水线

`.github/workflows/cnb-github-backfill.yml`：**每日 18:30 UTC**（北京次日 02:30）+
`workflow_dispatch`（带 `dry_run` / `since` / `limit` 入参）。

与镜像 cron（18:00）错开半小时，免得两个作业抢同一个 runner 池。
`concurrency` 用固定 group 且 `cancel-in-progress: false`：定时与手动同时点不会重复发，
排队而非取消，回写不丢。

### 写测试时抓到的真实缺陷

`test_body_is_truncated_to_github_limit` 第一次是**红的**：原实现直接 `text[:MAX_BODY]`，
把末尾的幂等标记一起切掉了。后果不是「少一段正文」，而是**这条评论每跑一轮就重发一次**，
且 GitHub 上已发出的评论无法被脚本静默撤回。

修法是截断时先给标记留出额度。这类「截断把哨兵切掉」的缺陷靠人工 review 很难发现
（截断逻辑看着人畜无害），正是回归网的用武之地。

## 9. 分支纪律：镜像脚本的改动提到哪

> 这一节回答的是 CNB #123 的质问：「提 PR 的时候到底是提到 `dev` 还是 `main`？必须固定下来。」
> 权威判据在 `AGENTS.md` §「Git 分支规范 → PR 与 Review」，此处只讲**镜像链路特有的那部分**。

### 两条长期分支，两种 base，没有第三种

| PR 类型 | base | head |
|---|---|---|
| 功能 / 文档分支 PR（**默认**） | `dev` | `feat/*` / `fix/*` / `docs/*` |
| 发布 PR（发版） | `main` | **`dev` 本身** |

**镜像脚本的改动照走第一行。** 「它要跑 cron，所以得进 `main`」**不是**改 base 的理由——
cron 挂在哪个分支，改变不了「改动应当经过 `dev` 集成」这件事。

### 为什么「要跑 cron」会诱使人改 base

CNB 的 `crontab` 事件**只能挂在具体分支下**（不能放 `$` 兜底），当前挂在 `main`
（`.cnb.yml`）。于是产生一个真实的时间差：

```
功能分支 ──PR(base=dev)──▶ dev ──发布PR──▶ main ──cron 读这里──▶ 作业生效
                          ↑
                 改动停在这里时，跑的还是旧脚本
```

**这个窗口应通过「及时发版」消除，而不是通过「把 base 改成 `main`」消除。**
后者看起来更快，代价是把 `dev` 绕过：`main` 上长出一个 `dev` 没有的提交，
两边从此**互不包含**（`git merge-base --is-ancestor main dev` 变 false），
之后的每一次发版都会撞上「为什么 main 有 dev 没有的东西」。

### 已付的代价（2026-10-11 实测，可复现）

正是这个诱因，让镜像链路连续几个 PR 以 `main` 为 base。截至本卡：

```
                     CNB dev            CNB main
.cnb.yml                无                 有      ← 镜像流水线只挂在 main
github_cnb_issues.py    无                 有      ← 建卡脚本只在 main
mirror_correction.py    无                 有      ← 更正通道只在 main
cnb_github_backfill.py  有                 无      ← PR #116 的回写脚本只在 dev
.github/workflows/cnb-github-backfill.yml 有     无
```

```text
git rev-list --count origin/dev..origin/main   = 6    ← main 独有的 6 个提交
git rev-list --count origin/main..origin/dev   = 10   ← dev 独有的 10 个提交
git merge-base --is-ancestor origin/main origin/dev    ⇒ false（已分叉）
```

后果不是理论风险：**「改镜像链路」的代码在 `dev`，「会被真正执行」的代码在 `main`**，
而两边对「镜像卡是只读副本还是允许修正」的结论是**相反**的。

> ⚠️ **本节这一段的结论已过期（2026-10-14 更正，源 CNB #179）**：原文写「评论回写链路目前
> **一行都没在跑**」——那是 **2026-10-11 当时**的状态（脚本只在 `dev`、workflow 没铺开）。
> 现状是**已在跑**：`scripts/bridge/cnb_github_backfill.py` +
> `.github/workflows/cnb-github-backfill.yml`（每日 18:30 UTC），且脚本在 `dev` / `main`
> **两侧都有**。实测（2026-10-14，本机真 GitHub + 真 CNB）跑 `--dry-run` 得到
> 「可映射 21 张，回写 0 条评论」，说明映射与幂等判定都在正常工作。
> **唯一使用门槛**：CNB 卡面引用 GitHub 卡要写**完整 URL**
> `https://github.com/imoyao/fundmate/issues/N` —— 裸引用 `imoyao/fundmate#N` 会被
> **静默跳过**（写路径「宁可漏，不可错」是对的，只是没信号）。

### 发版前先自查有没有分叉

```bash
git fetch origin dev main
git rev-list --count origin/dev..origin/main   # 正常应为 0
git merge-base --is-ancestor origin/main origin/dev && echo '未分叉' || echo '⚠ 已分叉'
```

**`main` 领先 `dev` 的提交数应为 0**（`main` 始终是 `dev` 的历史前缀）。
不为 0 就是有 PR 用错了 base，先查清再发版——直接发版会把分叉固化。

### 本节的边界

- **不改变**任何脚本的行为，只是把「改动提到哪」写死，消除「看起来随意」的空间；
- **不替代**发版：本节明确「要生效就得发版」，而不是宣称改 `dev` 就自动生效；
- 与 `docs/dev/github-cnb-mirror.md`（只在 `main` 上）的关系：那份文档记录镜像链路的
  **路线决策**，本卡的分支纪律是它的**执行层补充**，两者不冲突。

## 10. 已知边界

- **延迟**：最长一次 cron 间隔（一天）。要即时，走 `workflow_dispatch` 手动触发。
- **只回写评论，不改状态**：CNB 卡关了不会自动关 GitHub 卡，反之亦然。关闭是人的判断。
- **闭卡也会回写**：`list_cnb_issues` 同时拉 open + closed——卡片常是「讨论完 → 关掉」，
  只拉 open 等于把最后一轮讨论丢掉。
- **不回写镜像卡之外的内容**：CNB 侧人工新建、正文里没有 GitHub 链接的卡，一律跳过。
- **只回写顶层评论**，不含行内 review 评论 / 附件 / 表情。
- **CNB 列表接口不返回 `body`**：映射阶段是「列表 + 逐张详情」两步；`comment_count == 0`
  的卡直接跳过，省掉详情调用。

## 11. 与代码双向镜像的关系

**代码不需要这套机制。** 代码的两个方向各有归属：

- **CNB → GitHub**：`.cnb.yml` 的 `push:` 段（`branch: dev`）与
  `"**/!(main|dev)"` 段（`branch: ${CNB_BRANCH}`，功能分支）；
- **GitHub → CNB**：`crontab: 0 * * * *` 的 `sync_mode: pull`。

`main` 两个方向都不走——它是 GitHub 的权威分支，只由发版 PR（`dev → main`）推进。
细节与守卫见 `docs/dev/github-cnb-mirror.md` §13.3。

本作业只管 **issue 与评论**这一层——它没有 git 层面的等价物。

> ⚠️ 那条 `sync/mirror` 定时任务**自 2026-10-11 起处于停摆状态**，且**至今仍在红**
> （2026-10-14 复核）：两侧 `dev` 互不包含，该任务只允许快进，一旦有人直接往 CNB 侧
> 推过分支，后续同向快进就被拒。
>
> **2026-10-14 补充（源 CNB #179）**：这条红有了**已成文的两条口径**——
> ① **权威源单向后分叉不再产生**：CNB 侧的 git-sync 两个方向都收窄到 `dev`
> （`push` 推 `dev`、`pull` 只拉 `dev`，`main` 两侧互不推、互不覆盖，见
> `docs/dev/github-cnb-mirror.md` §13.3）；
> ② **存量分叉靠发版收敛**，不是靠 `--force`（force 会静默抹掉一侧改动）。
> 本作业仍刻意不碰它（不越界修别人的腿），但它**不再是「无人认领」的红**。
>
> **2026-10-14 处置（源 CNB #450 评论「先按 2、3 提个 PR」）**：
> ① `sync/mirror` 那条 cron 已被**移除**——该分支自建起就只为托管这条 cron
> （相对共同祖先只有 1 个提交、+48 行），而职责早被 `dev` 的 git-sync 取代；
> ② `dev` 的 **pull cron 已删除**：插件的 pull = `git pull --rebase` + `git push origin --force`，
> 而 CNB `dev` 比 GitHub `dev` 多 83 笔独有提交、**逐笔 rebase 79 笔冲突**
> （同一对分支用 **merge** 则零冲突）⇒ 它必然红且一字节都拉不动。**「解掉
> `decisions.md` 的冲突债」解不掉它**——那只是 79 分之一。GitHub → CNB 的整段合并
> 改走人工的 `scripts/bridge/dev_converge.py --apply`（用 merge）。
> 仍**待办**：GitHub 侧 `dev` 的分支保护（push 被 `质量门禁汇总` 拦）需要仓库管理员在 Web 上处置。
