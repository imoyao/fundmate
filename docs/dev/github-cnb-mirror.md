---
title: GitHub → CNB Issue 增量镜像
status: v1（2026-10-11，源 CNB issue #2）
owner: 阿白
---

# GitHub → CNB Issue 增量镜像

> 脚本：`scripts/bridge/github_cnb_issues.py`　流水线：`.cnb.yml`（每日 cron + 手动触发）
> 回归网：`backend/tests/test_github_cnb_mirror.py`　状态：`scripts/bridge/github_cnb_state.json`

## 1. 为什么有这个东西

本仓库的正式讨论在 GitHub，但 CNB 侧没有 issue 视图——两边各说各话，人在 CNB 就
看不到 GitHub 新开的卡。2026-10-11 做过一次**全量手工同步**（107 张卡，CNB `#5`~`#112`），
但那是一次性的：GitHub 之后新开的卡不会再出现。

本作业把那轮同步**固化成可重复执行的增量任务**，把「CNB 侧能看到全部 GitHub 卡」
变成常态，而不是靠人手再同步一次。

## 2. 三条设计取舍

| 取舍 | 做法 | 为什么 |
|------|------|--------|
| **单向** | 只 GitHub → CNB，绝不回写 GitHub | 双向会在两侧状态不一致时互相打架（谁会赢没有定义） |
| **只增不覆盖** | 已存在的镜像卡永不改动 | 存量卡可能被 CNB 侧人工调过正文 / 标签，覆盖等于抹掉那些调整 |
| **不同步关闭态**（2026-10-11 起**降级为「标记不关」**） | GitHub 关了，CNB 不**自动**关，只回流一条状态评论 + 挂 `GitHub 已关闭` 标签（§8） | 「CNB 关了」会被误读成「这事不做了」，而关闭与否该由人拍板——但「一个字都不说」同样会误读，故改为**说清楚、不动手** |

镜像卡正文顶部写明「只读镜像，讨论回 GitHub」，就是为了让这三条在卡面上可见。

### 但「只增不覆盖」有一个必须自己扛的代价（#118）

前三条取舍合起来会产生一个副作用：**镜像卡正文一旦写成，就永久停在那一刻**。
GitHub 侧后来的更正传不过来，而卡面顶上那些「状态：`open`」「评论数：5」看着很权威——
**比不写更糟，它给了读者一个看起来权威的过期事实**。

实测（2026-10-11，#106 ← GitHub #2034）就是活例子：正文引用
`WelcomeAssetBoard.vue:119-130`，该行随 #980 拆页删除、#1955 又改了口径，
卡面描述的是**两个版本之前**的代码，而读者没有任何线索。

故溯源块里必须自己声明「这是快照」：

```
> - 镜像生成时间：2026-10-12 00:00 UTC
>
> ⚠️ 本卡是**建卡时快照**（截至 2026-10-12），**不覆盖后续变更**；
> 正文引用的文件 / 行号 / 字段 / 结论均为快照时刻的位置，可能与当前代码不一致——
> 按它动手之前，先用 `git show <ref>:<file>` 确认该行仍在当前分支上。
> ⚠️ 正式讨论、更正与状态变更请回到 GitHub 原卡，CNB 侧改动不会自动回流；
> 本卡正文若与 GitHub 原卡不符，**一律以 GitHub 为准**。
>
> 📝 **更正**：在本卡评论区追加一条更正评论（不改正文）——
> 标题写 `## 更正（{日期}）`，正文逐条写「❌ 原文 → ✅ 实际（依据：PR/commit）」。
> 依据 AGENTS.md「失实信息修正纪律」；命令见 `scripts/bridge/mirror_correction.py`。
```

旧的「本卡为只读镜像」措辞**刻意删掉**了：它和「更正在评论区」自相矛盾（只读 = 不许写，
可我们又要人在这里留更正）。现在的措辞是「快照 + 以 GitHub 为准 + 更正写哪」三件事，
不再自相矛盾。

> 溯源块最终形状由 CNB #118 与 #120 两条线合并而来：**建卡时刻 + 更正台账**取自 #120
> （`mirror_correction.py`），**可执行核对动作**（`git show <ref>:<file>`）取自 #118，
> 二者合成同一份头部，避免镜像卡出现两种长相。格式冻结断言见
> `backend/tests/test_github_cnb_mirror.py::test_header_matches_frozen_shape`。

## 3. 幂等怎么保证

幂等键是 **GitHub 编号**，写在每张镜像卡正文里，形如 `` GitHub 编号：`#783` ``。
脚本每次运行时：

1. 读 `scripts/bridge/github_cnb_state.json`（GitHub 编号 → CNB 编号）；
2. 状态文件里没有的，才去 CNB 逐张拉正文抠编号（列表接口**不返回 body**，必须单张取）；
3. 抠出来的编号回写状态文件，下次不再重复拉。

所以**同一天跑十遍，只会建一次卡**。状态文件随 PR 入库，是首次运行后的快照，
避免每次冷启动都把 100+ 张卡拉一遍。

> ⚠️ 状态文件是**缓存、不是权威**。真权威是镜像卡正文里的编号——两者不一致时以正文为准，
> 删掉状态文件重跑即可自愈。

## 4. 字段映射

映射口径与 2026-10-11 那轮全量同步**完全一致**，免得同一批卡出现两种长相。

| GitHub | CNB | 说明 |
|--------|-----|------|
| 标题 | `title` | 原样，超 200 字截断 |
| 正文 | `body` | 溯源块（来源 / 编号 / 状态 / 里程碑 / 原标签 / 作者 / **镜像生成时间**）+ `---` + 原文 |
| `Q1-RED` | priority `P0` | 象阵转 CNB 原生 priority |
| `Q2-YELLOW` | `P1` | |
| `Q3-GREEN` | `P2` | |
| `Q4-GRAY` | `P3` | |
| 里程碑 | 标签 `里程碑:<名>` | CNB 无里程碑 API，只能以标签承载 |
| 其他标签 | `labels` | 去掉象阵四项；名字做合法化改写 |

**标签名合法化**是硬需求：CNB 只允许中英文 / 数字 / `._:-/\` 与内部空格，且长度 ≤50，
`&`、`（）`、`#` 一律 400 拒收。脚本做等价替换（`&`→`和`、`（#1909）`→` No.1909`），
超长截断。单卡标签上限 10 条，溢出时**先丢原标签、保里程碑**——里程碑是看板归类的硬信息。

## 5. 怎么跑

```bash
export CNB_TOKEN=<你的 CNB token>

# 先看要建哪些（默认 dry-run，不写任何东西）
python scripts/bridge/github_cnb_issues.py --dry-run

# 真正创建
python scripts/bridge/github_cnb_issues.py --apply

# 调试：本次最多建 3 张
python scripts/bridge/github_cnb_issues.py --apply --limit 3
```

依赖：**纯标准库**（`urllib`），无需 `pip install`，所以流水线用 `python:3.12-slim` 即可。

## 6. 流水线

`.cnb.yml` 里两条触发方式，跑同一套命令：

- **每日 18:00 UTC**（北京次日 02:00）：issue 不是时效数据，一天一次足够，也省构建分钟数；
- **手动触发**（web_trigger）：改了脚本、或想立刻同步时用。

注意 **crontab 事件必须挂在具体分支下**（不能放 `$` 兜底），故 cron 挂在 `main` 下；
`web_trigger` 与分支无关，按平台建议放 `$` 下。

> ⚠️ **正因为 cron 挂在 `main` 下，`.cnb.yml` 与本脚本必须活在 `main` 上。**
> 2026-10-11 实测：`.cnb.yml` / `github_cnb_issues.py` 只存在于 CNB `main`，
> 而 CNB `dev` 上有另一套（`cnb_github_backfill.py` + 回写 workflow）——**两边互不包含**。
> 也就是说：**「改镜像链路」的代码在 `dev`，「会被真正执行」的代码在 `main`**。
> 改镜像行为时，先确认改动落在 `main`（或已经发版过去），否则它永远不会被执行。
> 这与 `issue-milestone-guard.yml`「补挂里程碑后不自愈」同族：整改做完了，跑的不是它。

cron 阶段末尾挂了三节**只报告/幂等**的收尾任务：

```yaml
    - name: 状态回流（GitHub 已关闭 → CNB 标记）
      script: |
        python scripts/bridge/mirror_state_sync.py --apply || true
    - name: 引用时效自检（认评论区更正，只报告）
      script: |
        python scripts/bridge/check_mirror_refs.py --report || true
    - name: 分支分叉自检（只报告）
      script: |
        python scripts/bridge/check_branch_divergence.py --report || true
```

三节都带 `|| true`：**建卡才是主任务**，这些收尾作业是信号，不该把建卡一起拖红。
（状态回流自身是幂等的，重复执行只发一次评论。）


## 7. 引用时效自检（#118）

「只增不覆盖」让**卡面过期不可见**。为此加了一件独立的只读工具：

```bash
# 单张卡面：从 GitHub issue / 本地文件核对
python scripts/bridge/check_issue_refs.py --issue 2034 --ref origin/dev
python scripts/bridge/check_issue_refs.py --file card.md --ref origin/dev --strict-ref

# 全部镜像卡：批量扫，输出 markdown 报告
python scripts/bridge/check_mirror_refs.py --report --ref origin/dev
```

`check_mirror_refs.py` 复用 `check_issue_refs.py` 的抽取 / 核对逻辑（**不抄第二份正则**，
两份判据必然漂移），扫 CNB 侧全部镜像卡，报出失效引用。

关键设计取舍：

| 取舍 | 做法 | 为什么 |
|------|------|--------|
| **只报告，不改卡** | 不写任何 CNB / GitHub 状态 | 改镜像卡正文要产品拍板（CNB #120）；`.cnb.yml` 里用 `\|\| true` 明确「这是信号不是门禁」 |
| **路径补全要求唯一** | 裸文件名（`summary_service.py:392`）只有在全仓**恰好一个**文件以它结尾时才认 | 多命中时挑一个是**猜**，会给出**假绿灯**，比报「不存在」更坏 |
| **`scripts/` 不在前缀表里** | — | 它是本脚本自己的目录，放进去会把引用核对成脚本自己 |
| **`--strict-ref` 默认关** | 缺 `@ref` 只提示不拦 | 存量卡全都没写 `@ref`，硬拦等于全红；新卡由 strict 管 |

**首轮实测**（2026-10-11，110 张镜像卡）：报出 **3 张卡 / 4 条失效引用**，逐条核实为真：

- `#56` (#1095)：引用 `portfolios/views.py:214-215` 说 `get_portfolio_holdings`「Python 循环逐行算市值」，
  但该文件现在只有 **166 行**，函数在第 **159** 行——卡面引用的行号在文件之外；
- `#56` (#1095)：`portfolios/views.py:193` 同样越界；
- `#38` (#968)：`explore/index.vue:751`，该文件现在 **698 行**。

> 这一节是「引用须带 ref」这条纪律的**机器化落地**：光在文档里写「引用要写引自哪个 commit」
> 是没用的（存量卡已经躺在那儿了），得有一个作业能问出「这张卡读过时了吗」。

### 但只读正文会产出**假红**（#123 修）

`#120` 拍板的更正通道是「**正文不动、更正写评论区**」。于是只看正文的自检会
**永远报红**——修好了也红，而红却不指向任何还需动手的事。这与 #118 要治的「静默降级」
是同一族：那边是假绿，这边是假红，**红灯的可信度一样会掉没**。

故报告按「评论区有无更正」分两类（靠 `mirror_correction.py` 的幂等键
`更正键：<sha1>` 识别，**不抄第二份正则**）：

| 类别 | 含义 | 要不要动手 |
|------|------|-----------|
| ⚠️ **待更正** | 正文引用失效，评论区**没有任何**更正 | **要**——这才是待办 |
| ✅ **已更正** | 正文引用失效，但评论区已有更正说明 | 不要——账已记 |

实测（2026-10-11）：修复前报告 4 张全为待办；修复后 **0 张待办 / 4 张已记**
（这 4 张的更正评论此前已按 #120 通道逐张发布，`mirror_correction.py list` 可复核）。

## 8. 状态回流（CNB #117 硬要求 ②）

`github_cnb_issues.py` 只做**建卡**，建完即止。于是溯源块里的「状态：`open`」是
**建卡当时的快照**——GitHub 之后把卡关了，CNB 侧一个字都不变。读者在 CNB 看到一张
「还活着」的卡，实际那件事早已结案。这比两侧明显不一致**更难察觉**。

`mirror_state_sync.py` 把「GitHub 已关闭」这个事实**单向回流**到镜像卡上：

```bash
# 只报告漂移（不写任何东西）
python scripts/bridge/mirror_state_sync.py --report

# 真正回流（默认 dry-run；幂等，同一事实只发一次）
python scripts/bridge/mirror_state_sync.py --apply

# 单张卡演练
python scripts/bridge/mirror_state_sync.py --cnb 106 --apply
```

形态是两件一起做：

1. 在该卡评论区追加一条 `## 状态回流（日期）` 评论（带隐藏幂等键 `状态键：<sha1 前 12 位>`）；
2. 给该卡挂 `GitHub 已关闭` 标签，供看板一眼筛出。

### 为什么是「标记」而不是「自动关卡」

原取舍写的「不同步关闭态」有一条正当理由：「CNB 关了会被误读成『这事不做了』，
而关闭与否该由人拍板」（#117 硬要求 ①：人工回路保留）。这条理由**现在仍然成立**
——CNB 侧的追问往往发生在 GitHub 关掉之后，直接把卡关掉会把那些讨论一起埋掉。

所以本作业采取**标记法**：把关闭事实**说清楚**（评论 + 标签），但**不替人做关闭这个决定**。
评论正文里明写「本卡**不会被自动关闭**」并给出人工入口 `cnb issues close --number <n>`。
要真正关卡，人工执行那一条。

### 漂移只认一个方向

| GitHub | CNB | 判定 |
|---|---|---|
| closed | open | **漂移** → 回流标记 |
| closed | closed | 已对齐 |
| open | open | 已对齐 |
| open | closed | **不回流** |

最后一行是刻意的：**CNB 侧关卡是人的决定**（讨论已结束），GitHub 后来重开原卡
不代表 CNB 侧那些讨论又活了。若脚本反向回退，它就变成「GitHub 只要还开着，CNB 就不许关」
——等于取消人工回路，正是 #117 硬要求 ① 要防的。

### 幂等键带上 GitHub 的 `updated_at`

`状态键 = sha1(CNB 编号 | GitHub 编号 | 状态 | GitHub 侧 updated_at)`。带上 `updated_at`
是为了让「关闭 → 重开 → 再关闭」各发一条——否则第二次关闭会被当成重复而静默吞掉。

### 标签 / 优先级 / 里程碑

这三项**建卡时已同步**（见 §4 字段映射）。建卡之后的漂移**本作业不处理**：
「只增不覆盖」的直接推论是存量卡的标签/优先级不会跟着 GitHub 改——那需要先拍板
「镜像卡是只读副本还是允许修正的本地副本」，口径见 CNB #117。

## 9. 已知边界

- **不回写、不覆盖、不关**：见 §2。状态用**标记**（§8），不做自动关卡。
- **只镜像 open issue**：GitHub 侧已关闭的卡不会补建。若某张卡在首次同步前就关了，
  CNB 侧看不到（但若它已被镜像过、之后 GitHub 关了，§8 会回流标记）。
- **匿名 GitHub API 限额 60 次/时/IP**：107 张卡走 2 次分页调用，余量充足；仓库若长到
  数千 open issue，需配 `GITHUB_TOKEN`。§8 的状态回流要拉 `state=all`（含 closed），
  调用量比建卡那次大——限额下会静默少拉（`plan()` 对拉不到的卡**跳过而不是猜**）。

## 10. 分支分叉自检（CNB #123）

`crontab` **只能挂在具体分支下**（平台限制，见 §6），而本仓 `.cnb.yml` 挂在 `main`。
若「整改代码在 `dev`、会被执行的代码在 `main`」，就会出现 #123 记的那个病：

> **写完了，跑的不是它**——且没有任何信号提示这件事。

这与 `issue-milestone-guard.yml`「补挂里程碑后不自愈」同族。故加一件只读工具：

```bash
# 默认比较 origin/main ← origin/dev
python scripts/bridge/check_branch_divergence.py --report

# 只看「哪些作业只在单侧」
python scripts/bridge/check_branch_divergence.py --report --jobs-only
```

### 判据

- **`main` 独有提交数 > 0 ⇒ 分叉**（正常态恒为 0：发版 PR 把 `dev` 推上去，`main` 不领先）；
- 列出两侧互不包含的「决定什么会被执行」的文件（`.cnb.yml` + `.github/workflows/*.yml`）。

退出码：`0` = 未分叉；`1` = 检出分叉；`2` = 取不到分支。`.cnb.yml` 里带 `|| true`
——它是信号，不是门禁。

### 为什么这么写

| 取舍 | 做法 | 为什么 |
|------|------|--------|
| **纯离线** | 只读本地 git，**不 fetch** | 分叉判定不该依赖网络，否则「网络不通 = 报告绿」又是一次静默降级 |
| **只报告，不改动** | 不 fetch / merge / push | 要不要更新远端视图是调用方的决定；脚本有副作用就不可信 |
| **方向敏感** | `git diff --name-status left right` 里 `D` = 只在 `left`、`A` = 只在 `right` | 初版把 `A`/`D` 都算「只在 right」，同一文件同时出现在两侧列表（见回归网 `test_side_only_no_duplicate_across_sides`） |

### 分叉的成因（2026-10-11 实测）

不是「main 落后 dev」，是**双向分叉**：`main` 独有 15 个提交、`dev` 独有 20 个，
`git merge-base --is-ancestor origin/main origin/dev` 为 **false**。根因是两条功能分支
（`feat/github-issue-cnb-mirror`、`feat/2-cnb-github-backfill`）从**同一个 base**
分出后各自只投递到一侧 ⇒ `main` 拿到镜像链路、`dev` 拿到回写链路，互不包含。

**处置是发版**（`dev` → `main` 的 PR，head 必须是 `dev` 本身），
**不是**「把功能分支 base 改成 `main`」——后者正是本分叉的成因（见 AGENTS.md「PR 与 Review」）。
