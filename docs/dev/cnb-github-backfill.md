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

## 6. 谁的回写、谁的不回写

CNB 侧的机器人账号（`is_npc: true`，以及用户名 `OCI` / `CodeBuddy`）**不回流**。
理由：把 NPC 的输出搬回 GitHub，会被 GitHub 侧的 AI review 再看见，形成回声；
而且那些内容多半是执行日志，不是给人看的讨论。

判断顺序：`is_npc` 优先（最可靠）→ 用户名后缀 `[bot]` → 已知机器人名单兜底
（历史数据里 `is_npc` 不一定都填了）。

> 反过来的边界也钉着：**作者字段缺失时判定为「不是机器人」**——宁可多发一条，
> 也别把真人讨论吞掉（`test_none_author_is_not_bot`）。

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

读 CNB 侧**匿名即可**（公开仓库），不需要 token；`CNB_READ_TOKEN` 留给将来仓库转私有时的口子。

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

## 9. 已知边界

- **延迟**：最长一次 cron 间隔（一天）。要即时，走 `workflow_dispatch` 手动触发。
- **只回写评论，不改状态**：CNB 卡关了不会自动关 GitHub 卡，反之亦然。关闭是人的判断。
- **闭卡也会回写**：`list_cnb_issues` 同时拉 open + closed——卡片常是「讨论完 → 关掉」，
  只拉 open 等于把最后一轮讨论丢掉。
- **不回写镜像卡之外的内容**：CNB 侧人工新建、正文里没有 GitHub 链接的卡，一律跳过。
- **只回写顶层评论**，不含行内 review 评论 / 附件 / 表情。
- **CNB 列表接口不返回 `body`**：映射阶段是「列表 + 逐张详情」两步；`comment_count == 0`
  的卡直接跳过，省掉详情调用。

## 10. 与代码双向镜像的关系

**代码不需要这套机制。** 两侧的 `dev` / `main` 由 CNB 侧 `sync/mirror` 分支的定时任务
`git fetch` + **fast-forward only** 对齐（`.cnb.yml`），这是仓库级的直接搬运，比任何
基于 API 的镜像都快且无冲突；GitHub 侧的 PR 合并会经那条通路自动出现在 CNB。

本作业只管 **issue 与评论**这一层——它没有 git 层面的等价物。

> ⚠️ 那条 `sync/mirror` 定时任务**自 2026-10-11 起实际处于停摆状态**：两侧 `dev`
> 已分叉（CNB 停在 `0de73e21`，GitHub 已到 `16e807c4`，中间是 PR #2049/#2051）。
> 该任务只允许快进，一旦有人直接往 CNB 侧推过分支（镜像分支本身就在 CNB 侧），
> 后续同向的快进会被拒。这是**代码镜像独立于本作业的一个待修项**，见 issue #2 的
> 讨论；本作业刻意不碰它（不越界修别人的腿）。
