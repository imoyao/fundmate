---
title: GitHub → CNB Issue 增量镜像
status: v1.4（2026-10-14，源 CNB issue #2；§9 本地卡对照源自 CNB #117；§13 双向同步三故障/四种失败形态；§13.5 「CNB main 与 GitHub main 无关」口径）
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
# 单张卡面：从 GitHub issue / 本地文件核对（留空 --ref = 远端默认分支）
python scripts/bridge/check_issue_refs.py --issue 2034
python scripts/bridge/check_issue_refs.py --file card.md --strict-ref
# 需要指定版本时才显式传（例如核对一条明确指向 dev 的引用）
python scripts/bridge/check_issue_refs.py --file card.md --ref origin/dev

# 全部镜像卡：批量扫，输出 markdown 报告
python scripts/bridge/check_mirror_refs.py --report
```

> **默认核对版本 = 远端默认分支**（`default_ref()` 解析 `git ls-remote --symref origin HEAD`，
> 本仓即 `origin/main`），**不是**写死的 `dev`。#144 §四 记的正是这处错位：卡面
> （GitHub 原卡 / CNB 镜像卡）描述的是**默认分支**的代码，拿 `dev` 核对会把
> 「`dev` 上已删、`main` 上还在」的引用报成失效——实测假阳性就是 `#104`（GitHub #2032）
> 的 `AssetInsightPanel.vue`（`main` 上仍在，`dev` 上已删）。逐条输出现在会打出
> `[核对版本 <ref>]`，卡面自带 `@ref` 时一眼可见它与默认版本不同。

`check_mirror_refs.py` 复用 `check_issue_refs.py` 的抽取 / 核对逻辑（**不抄第二份正则**，
两份判据必然漂移），扫 CNB 侧全部镜像卡，报出失效引用。

关键设计取舍：

| 取舍 | 做法 | 为什么 |
|------|------|--------|
| **只报告，不改卡** | 不写任何 CNB / GitHub 状态 | 改镜像卡正文要产品拍板（CNB #120）；`.cnb.yml` 里用 `\|\| true` 明确「这是信号不是门禁」 |
| **路径补全要求唯一** | 裸文件名（`summary_service.py:392`）只有在全仓**恰好一个**文件以它结尾时才认 | 多命中时挑一个是**猜**，会给出**假绿灯**，比报「不存在」更坏 |
| **`scripts/` 不在前缀表里** | — | 它是本脚本自己的目录，放进去会把引用核对成脚本自己 |
| **`--strict-ref` 默认关** | 缺 `@ref` 只提示不拦 | 存量卡全都没写 `@ref`，硬拦等于全红；新卡由 strict 管 |

**首轮实测**（2026-10-11，110 张镜像卡）：按 `origin/dev` 核对报出 **4 张卡 / 5 条**，
其中 **`#104`（GitHub #2032）的 `AssetInsightPanel.vue:38-41` 是假阳性**——该文件在
`main` 上仍然存在、只在 `dev` 上被删，属「判据读错了版本」（#144 §四）。默认版本改为
**远端默认分支 `origin/main`** 后，报告为 **3 张卡 / 4 条**，且这 4 条逐条核实为真：

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

# 只想标记、不想自动关（逃生阀）
python scripts/bridge/mirror_state_sync.py --apply --no-close

# 单张卡演练
python scripts/bridge/mirror_state_sync.py --cnb 106 --apply
```

形态是**三件一起做**（2026-10-13 起，B 口径）：

1. 在该卡评论区追加一条 `## 状态回流（日期）` 评论（带隐藏幂等键 `状态键：<sha1 前 12 位>`）；
2. 给该卡挂 `GitHub 已关闭` 标签，供看板一眼筛出；
3. **把 CNB 镜像卡关掉**（`PATCH /{repo}/-/issues/{n}`，`state=closed` + `state_reason=completed`）。

### 口径变更：从「标记不关」到「真的关」（D48 → D55）

D48（CNB #117 硬要求 ②）原口径是**标记不关**，理由是「CNB 侧的追问常发生在
GitHub 关掉之后，关掉会把那些讨论一起埋掉」，并保留人工回路（硬要求 ①）。

**用户 2026-10-13 在 CNB `#171` 选了 B：GitHub 关了，CNB 也自动关。** 理由不是
「原理由错了」，而是**权衡变了**：「标记不关」让「卡片状态」与「事实状态」永久劈成
两半——看板上是一张「还活着」的卡，GitHub 上早已结案；读者要打开卡、翻到评论区
才可能看到那条回流评论。**看板越用越不可信，这个代价比埋掉讨论更高。**

讨论并不会丢：**评论不删**，卡片只是变灰；需要继续时 `cnb issues open --number <n>`
一条命令即可重开。**人工回路也没丢**：

- **反向仍不回流**（见下），CNB 侧关卡依旧是人的决定；
- `--no-close` 逃生阀：只标记不关，用于想先人工 triage 的那一轮。

### ⚠️ 「评论已发过」不阻断「关卡」（切口径必须补关存量卡）

D48 时代已有 **13 张卡**发过回流评论、却仍是 `open`（旧口径的本意）。切换到 B 后，
它们**必须被补关**——否则就是「口径改了、那些卡继续漂着」，等于换个说法继续不一致。

故 `run()` 里两条判据**分开**：

| 动作 | 判据 | 说明 |
|---|---|---|
| 发评论 | 幂等键 `状态键：<sha1>` 是否已存在 | 同一事实只发一次 |
| 挂标签 | 总是尝试 | CNB 侧幂等 |
| **关闭卡片** | **与评论无关** | 漂移卡就应该关 |

2026-10-13 真实复跑验证：14 张漂移卡里 13 张只执行「关闭卡片」（评论已存在）、
1 张（#91）发评论 + 关闭；单卡 `--cnb 35 --apply` 实测 CNB #35 由 `open` 转 `closed`、
`state_reason=completed`，二次执行 0 漂移（幂等）。

### 漂移只认一个方向

| GitHub | CNB | 判定 |
|---|---|---|
| closed | open | **漂移** → 回流标记 **并关闭** |
| closed | closed | 已对齐 |
| open | open | 已对齐 |
| open | closed | **不回流** |

最后一行是刻意的：**CNB 侧关卡是人的决定**（讨论已结束），GitHub 后来重开原卡
不代表 CNB 侧那些讨论又活了。若脚本反向回退，它就变成「GitHub 只要还开着，CNB 就不许关」
——等于取消人工回路，正是 #117 硬要求 ① 要防的。

### ⚠️ 「拿不到数据」≠「没有漂移」（#171，2026-10-13 修）

这是本作业上线后**真实发生**的失效，且形态最坏：**它一直是绿的，也一直没干活。**

症状：`--report` 打印

```text
⚠️ GitHub 限额用尽（403），只拿到前 0 页共 0 张；本轮的卡可能漏标。
📥 GitHub issue 0 张；CNB 镜像卡 107 张
✅ 无状态漂移，两侧已对齐          ← 一张 issue 都没拉到，却报「已对齐」
```

根因是两层叠加：

1. **额度不够**：`fetch_github_issues_by_number()` 用 `state=all`（含已关闭卡）翻页，
   而 cron 里 `GITHUB_TOKEN` 是「可选、不设则走匿名」——匿名只有 **60 次/时/IP**，
   且建卡 job 先跑、先把额度吃掉，`state=all` 到第 3 页就 403；
2. **错误的等价**：403 时函数 `break` 返回空映射，而 `run()` 里 `if not todo: print('✅ 两侧已对齐')`
   —— **「拉不到」被当成了「没漂移」**。文件头当时写的「少拉只是少标记、不会误标」
   只考虑了**误标**（确实成立），没意识到**少拉到 0 张时报告会给出完全错误的结论**。

修法（`scripts/bridge/mirror_state_sync.py`）：

- `fetch_github_issues_by_number()` 改为返回 `(映射, 是否完整)` 二元组，把「完整性」
  交出去当一等值；
- `run()` 在 `complete=False` 时**一律不得宣称对齐**，打印「数据不完整，本次结论不可信」，
  并**以退出码 1 结束**（让 cron 侧看得出这次没跑成）；
- 部分数据下**照做但不背书**：`plan()` 对拿不到的卡本就是跳过，故能安全回流已判定的漂移。

回归网：`scripts/tests/test_mirror_state_sync.py` 的 `TestIncompleteDataNotGreen`（3 条）
—— 「0 张 + 不完整不得报已对齐」「不完整但有漂移照做但不背书」「完整且无漂移才报已对齐」。
**2 轮反向探针 CAUGHT**（S1 去掉 `not complete` 分支；S2 永不置 `complete=False`）。

> 这条修正的教训不止于本脚本：**任何「拿不到输入就当没有」的判据都是假绿生产线**。
> 假绿比假红更贵——假红有人去修，假绿没人去看。

**修复后复跑立刻露出第二个独立的坑**：GitHub 已对**大结果集禁用 page 参数**——
page 9/10 正常（各 100 条）、**page 11 直接 422**（阈值 1000 条），
报 `Pagination with the page parameter is not supported for large datasets, please use cursor based pagination`。
而镜像卡是 `#783`~`#2050` 的**老卡**，`sort=updated` 会把它们排到 1000 名之外 ⇒
**靠后的镜像卡永远落在可达窗口之外**。故「按编号直查（`GET /issues/{n}`）替代翻全量列表」
不是优化项，而是**前置必修**；在此之前，`complete=False` 会如实报出这个不完整。

### 幂等键带上 GitHub 的 `updated_at`

`状态键 = sha1(CNB 编号 | GitHub 编号 | 状态 | GitHub 侧 updated_at)`。带上 `updated_at`
是为了让「关闭 → 重开 → 再关闭」各发一条——否则第二次关闭会被当成重复而静默吞掉。

### 标签 / 优先级 / 里程碑

这三项**建卡时已同步**（见 §4 字段映射）。建卡之后的漂移**本作业不处理**：
「只增不覆盖」的直接推论是存量卡的标签/优先级不会跟着 GitHub 改——那需要先拍板
「镜像卡是只读副本还是允许修正的本地副本」，口径见 CNB #117。

## 9. CNB 本地卡：只对 CNB 有效的卡，不进 GitHub（#117）

镜像的初衷是「把 GitHub 的讨论带到 CNB」。但**反方向同样成立且更容易被忽略**：
CNB 侧会长出一些**只对 CNB 有效**的卡——`CNB_TOKEN` 是构建内注入的凭据、
`cnb issues` CLI、CNB 的 cron 语义、CNB 自身的镜像链路取舍……这些讨论放到
GitHub 上读起来会莫名其妙，因为它们描述的是一个 GitHub 上不存在的环境。

本节回答的就是用户当时问的那句：「有的 issue 只是对我们 CNB 来说有效，
完全同步到 GitHub 上面的话似乎也很奇怪，应该怎么处理？」

### 结论：**本地卡不进 GitHub，但必须是「被声明的」，且必须能被数出来**

三条一起才成立，缺一条就会退化成静默：

1. **不进 GitHub**：本地卡不参与镜像（现状已如此，因为镜像方向是 GitHub → CNB 单向）；
2. **被声明的**：卡面必须能表明「我是本地卡」，否则下一个人（或下一个作业）
   会把它当成「漏同步的镜像卡」，去补一张莫名其妙的 GitHub 卡；
3. **能被数出来**：必须有一条命令能回答「CNB 侧有多少本地卡、它们上面有多少讨论、
   其中多少条讨论**本该到 GitHub 却到不了**」。

### 声明方式（两种，都认）

```text
> 📍 **CNB 本地卡**     ← 正文顶部声明（人工卡最常用；锚在行首引用块，正文里提到这个概念不算）
```

或挂 `CNB 本地` 标签（显式、可筛选）。

两种都是**声明**。既没声明、又无 `GitHub 同步` 标签、也抠不到 `GitHub 编号：#N` 的，
判据会**兜底**认成本地卡 —— 但兜底是**猜**，报告里单独计数（`fallback`），
因为一张格式写歪的镜像卡也会命中兜底。

> **把「是不是」和「怎么判出来的」分开**，是这条判据最容易被做错的地方。
> 合在一起时，报告看不出某一行是**声明**还是**猜测**，而一份「少算了 87%
> 却依然自洽」的报告比没有报告更坏 —— 实测踩过：早期版本用状态文件的映射
> 跳过「已知镜像卡」，报告说「本地卡 12 张」，而真实总数是 123 张卡。

### 怎么数：`--report-local`

```bash
# 只读：不建卡、不写状态文件
python scripts/bridge/github_cnb_issues.py --report-local
python scripts/bridge/github_cnb_issues.py --report-local --out local-report.md
```

输出的关键几行（**实测读数，2026-10-11**）：

```text
- CNB 卡总数：123
- 镜像卡：111
- 本地卡：12（标签声明 0 / 正文声明 0 / 兜底猜测 12）
- 判据冲突（既像本地又像镜像）：0
- 本地卡上的评论总数：72 —— 这些讨论不会出现在 GitHub
- 其中引用了 GitHub 侧卡的本地卡：3
```

### 它顺手查出的一个**真缺口**：裸引用

回写作业（`cnb_github_backfill.py` 的 `resolve_github_number`）只认**完整 URL**
`https://github.com/<repo>/issues/N`，抠不到就跳过（「宁可漏，不可错」——写路径认错了
会把评论贴到别人卡上，这条取舍**是对的**）。

但实测发现：#117 / #120 等本地卡正文里写的是**裸引用** `imoyao/fundmate#2034`，
不是完整 URL ⇒ **认不出、静默跳过**。也就是说这些卡「指向 GitHub、讨论却到不了 GitHub」，
而**没有任何信号**提示这件事。

本报告把它标出来（`🔗imoyao/fundmate#2034` + 汇总计数），但**不改回写脚本**：

| | 回写脚本（写路径） | 本报告（只读路径） |
|---|---|---|
| 认什么 | **只认完整 URL** | 完整 URL + 裸引用都收 |
| 认错了的代价 | 评论贴到别人的卡上 | 报告里多一行提示 |
| 该取哪一边 | **宁可漏** | **宁可全** |

两边判据**刻意不同**，不是不一致。要根治「裸引用到不了 GitHub」，需要的是
**规范卡面写法**（引用跨仓卡时写完整 URL）或**在回写侧加白名单**，
那是另一件事，不在本报告范围内。

## 10. 已知边界

- **不回写、不覆盖、不关**：见 §2。状态用**标记**（§8），不做自动关卡。
- **本地卡不进 GitHub**：见 §9。它们不是「漏同步」，是**本就不该同步**；
  判据、声明方式与 `--report-local` 都在那一节。兜底判定（`fallback`）是**猜**，
  报告里单独计数，别把它的数字当成事实。
- **只镜像 open issue**：GitHub 侧已关闭的卡不会补建。若某张卡在首次同步前就关了，
  CNB 侧看不到（但若它已被镜像过、之后 GitHub 关了，§8 会回流标记）。
- **匿名 GitHub API 限额 60 次/时/IP**：107 张卡走 2 次分页调用，余量充足；仓库若长到
  数千 open issue，需配 `GITHUB_TOKEN`。§8 的状态回流要拉 `state=all`（含 closed），
  调用量比建卡那次大——限额下会静默少拉（`plan()` 对拉不到的卡**跳过而不是猜**）。

## 11. 分支分叉自检（CNB #123）

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

### 判据（2026-10-14 改为**内容级**，源 CNB #167 规则 1）

**`main` 有没有 `dev` 拿不到的代码**才算分叉 —— 判据从「提交数」升级为「内容」：

| 形态 | 内容级判据 | 退出码 |
|---|---|---|
| `git diff <left> <right>` 为空 | ✅ 一致：`left` 独有的只是**发版等结构节点** | 0 |
| diff 非空，但 `left` 是 `right` 的**祖先** | ℹ️ 只是 `right` 领先（正常态） | 0 |
| diff 非空，且 `left` 有 `right` 拿不到的路径 | ⚠️ **真分叉**，报告点名文件 | 1 |
| 拿不到 `git diff` | ❓ **判据不可用**，明说不降级（#171 教训） | 2 |

> **为什么改**：旧口径「`main` 独有提交数 > 0 ⇒ 分叉」把**每次发版**都报成红——
> 发版 PR 必然给 `main` 留一个 merge commit，而它**不引入内容**。红却不指向任何
> 还需动手的事，是**假红**（与 #118 的假绿同族）。用户口径原话是「CNB 的 `main`
> 不能有 `dev` 没有的**代码**」——判据就该按**内容**答，而不是按提交数。

辅助信号（仍会打印，供人看结构）：

- 两侧**互不包含**时明说「这才是 #123 记的双向分叉形态」；
- 列出两侧互不包含的「决定什么会被执行」的文件（`.cnb.yml` + `.github/workflows/*.yml`）。

`.cnb.yml` 里带 `|| true`——它是信号，不是门禁。

### 根因诊断：`--explain`（答「为什么分叉」，2026-10-11 补）

首版只报「分叉了几个提交、哪些作业只在单侧」，**答不出「为什么」**。而卡面 §一 建议 3
的原话是：

> 为什么 `dev` 会完全不含 `main` 的这一个 commit？……**需要先答这个，
> 否则发版完还会再分叉一次。**

```bash
python scripts/bridge/check_branch_divergence.py --report --explain
```

它额外给两件**可证**的事：

1. **稳定分支独有的提交清单**（短号 + 主题）——来路由人判断；
2. **发版试算**：`git merge-tree --write-tree --name-only <right> <left>`（**离线**，不碰工作区），
   答「把 `dev` 合进 `main` 会不会冲突、冲突哪几个文件」。

#### 为什么不自动判断「这条提交来自 GitHub 还是 CNB」

实测三条路**都答不了**这个问题（2026-10-11），逐条留证：

| 路 | 为什么不成立 |
|---|---|
| 提交信息启发式 | `feat(detail): …（#2029 卡 B）` 与 `docs(api): …（#2029 卡 B）` 同批同源，没有任何标记能区分平台 |
| `refs/fetched/*` | 它标的是「该提交**被合进** CNB 时 fetch 过」：跨仓同步 merge `6c97c259` 在内，而它上游那批 GitHub 提交**全不在**——反着来 |
| `sync/mirror` 分支 | 是另一条 lineage，不含这批提交 |

猜错的代价是**报告指向错误的处置**（该发版的被判成纪律违规，或反之），比不给结论坏得多。
故 `--explain` 只报事实、由人判断来路。

> 这个「不猜」的取舍本身有一条回归网钉着：`test_explain_never_guesses_platform`
> 断言报告里**不得**出现 `github-pr` / `cnb-local` 一类的平台归类标签。

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


## 12. `.cnb.yml` 的事件必须挂在分支之下（CNB #152）

> 事故：2026-10-11 双向同步上线后，**连续 7 条流水线全红**，报错三种形态、每一条
> 单独看都会把人指向错误的方向。根因不在密钥仓库、不在分支纪律，而在 `.cnb.yml`
> 的**写法**——GitHub PR #150 把 `push:` 与两条 `"crontab: ..."` 写在了**文件顶层**。

### 平台语义

CNB 的 `.cnb.yml` 顶层**只认分支名**（与 `$`）；事件（`push:` / `"crontab: ..."` /
`web_trigger:` …）必须写在**分支之下**：

```yaml
# ✅ 对：事件挂在分支下
main:
  push:
    - stages: [...]
  "crontab: 0 * * * *":
    - stages: [...]

# ❌ 错：顶层只认分支名 ⇒ 平台读成三个「名为 push / crontab: … 的分支」
push:
  - stages: [...]
"crontab: 0 * * * *":
  - stages: [...]
```

写错的后果不是「事件没生效」这么直白，而是**报错指向与真实原因相反的方向**：

| 现象 | 看起来在说 | 实际在说 |
|---|---|---|
| `GetFileContent: not found` | 密钥仓库里没这个文件 | **事件无定义** ⇒ CNB 拿 `main` 的定义兜底，而 `main` 上当时没有 `imports` |
| `parse yaml failed … (3:12)` | `vars.yml` 内容写错 | 定义**后来**长出来了（GitHub #150 合入 `main`），于是才轮到文件内容被读到——两种报错是**两件事**，不是同一件事的两个阶段 |
| `sync from github` 的 `无法快进` | 分支纪律出问题 | 与本次**无关**：那是 `sync/mirror` 分支上的镜像任务（CNB 为权威源的正常态），只是链路起来后才成为可见的红灯 |

> 这三条里前两条把注意力引向 `fundmate-secret`（一个**读不到也改不了**的 Secret 仓库，
> 对 API / token 一律 403），第三条引向根本不存在的问题——一次事故里三次误判，
> 全部由「顶层写了非分支键」这一个原因产生。

### 静态守卫

`scripts/check_cnb_events.py`（**零第三方依赖之外的 `pyyaml`**，仓库已有）：
顶层键必须是分支名或 `$`；`imports` 必须指向**文件**而不是仓库（指向仓库是 `installs` 的语法）。
并入 `ci.yml` 的 **`scripts_test` job**（不新增 job ⇒ 不必动 `gate.needs`），回归网
`scripts/tests/branch_structure.test.js`。

**刻意不做的事**：**不拉网络、不校验 URL 可达性**。`GetFileContent: not found` 那一类
构造不出静态判据（要查的是 Secret 仓库的权限与存在性），守卫拦的是它的**根因**——
事件有没有挂在真实分支上。

### 守卫自己也可能失效（本仓老规矩）

判据写好后跑了 **6 组反向探针**（含「事件挂顶层」「imports 指向仓库」「白名单混入分支名」
「顶层键判据被摘掉」「自检探针被摘掉」「imports 判据被摘掉」），全部 CAUGHT、还原后复绿。

其中两条**必须踩过才知道**：

- **白名单只能是单值键**。第一版把 `main` / `dev` 也写进白名单（想着「分支键当然合法」），
  于是**任何**分支名都合法、「顶层键必须是分支名」等于没有——探针 S3 当场抓住。
  现在守卫自带一个自检：用真实存在的唯一值键 `sync/mirror:` 反证白名单没被架空。
- **探针要断言「变异真的生效」**。第一轮探针里，往函数体开头插 `return []` 看着像回退，
  实际那是一段**不可达代码**（循环照跑），于是 `--file` 指对文件时守卫仍能报错、
  探针却误判成 `MISSED`。**没有「变异生效」断言的探针，本身就是一个假信号。**

## 13. 双向同步的三个故障与「失败形态对照表」（源 CNB #148，2026-10-12）

2026-10-11~10-12 的构建列表里，**大量 job 长相一模一样**（都叫 `Crontab job`、都是
`error`），但底下是三种**互不相关**的故障。分不清形态就会像 #152 那次一样，
把注意力全花在一个读不到也改不了的 Secret 仓库上。

**排查第一步：不要看 job 标题，看 stage 名。**

| stage 长这样 | 报错原文关键词 | 真实原因 | 处理 |
|---|---|---|---|
| `Prepare` 失败（**连 stage 都没进**） | `declares allow_images and can only be referenced by plugin tasks` | 密钥文件被挂在**流水线级 `imports`** 上（§13.1） | 移到**插件任务内部**（与 `image` 同级），见 §13.1 |
| `stage-0` 失败，日志有 `could not read Username` | `fatal: could not read Username for 'https://github.com'` | 凭据挂在**插件 `settingsFrom`** 上，但 `settings` 用了 `${VAR}`（§13.1 ②） | 改用**插件任务级 `imports`**（注入环境变量），见 §13.1 |
| `Prepare` 失败 | `parse yaml failed … (3:12)` | 密钥文件写成了 `.env` 风格（`KEY=VALUE`） | 改成 `KEY: value` |
| `Prepare` 失败 | `GetFileContent: not found` | **事件无定义**（事件写在 `.cnb.yml` 顶层，见 §12），平台拿默认分支的定义兜底 | 把事件挂到分支之下 |
| `stage-0` 失败，日志有 `无法快进` | `无法快进：CNB 侧存在独有提交（dst=… src=…），已跳过，需人工处理` | 分支**分叉**（§11）：CNB 侧长出了 GitHub 没有的提交 | 走 PR 把 CNB 独有提交同步过去，分叉消失后自愈 |

前三条都发生在 `Prepare`、都指向密钥仓库，但**根因完全不同**（位置错 / 格式错 / 事件没定义），
只有报错原文能区分；第四条根本不在 Prepare 阶段，是**内容**问题。

> **「有的成功有的失败」的真相**（#148 实测）：绿的那条是 `crontab: 0 18 * * *` 的
> **issue 镜像 job**——它用 `python:3.12-slim` 跑纯标准库脚本，**不 import 密钥、不用插件**；
> 红的那些全是 git-sync 作业。两者唯一的区别就是「有没有碰密钥文件」。

### 13.1 凭据引用必须挂在**插件任务级**，且用 `imports`（不是流水线级、不是 `settingsFrom`）

三条 git-sync 作业（`push` + 两条 `crontab`）曾在 2026-10-12 连续踩了**两个**形态——
报错完全不同，且**都把人带向了错方向**。

#### ① 流水线级 `imports` ⇒ 死在 `Prepare`

先看第一个形态：

```
The file: .../fundmate-secret/-/blob/main/vars.yml declares allow_images
and can only be referenced by plugin tasks.
```

根因是**引用挂在了流水线级**（`push:` 下一层、`stages:` 之上一行）：

1. `fundmate-secret` 是私有且非同源仓库，被引用时**必须**声明
   `allow_images: [tencentcom/git-sync]`（见 CNB 文档
   [文件引用 › 权限检查](https://docs.cnb.cool/zh/build/file-reference.md#权限检查)），
   否则 git-sync 插件读不到密钥；
2. 但 `imports` 若挂在**流水线级**，平台**不认为它是「插件任务」**⇒ 判定
   「声明了 `allow_images` 却没在插件任务里用它」⇒ `Prepare` 直接拒绝，连 stage 都进不去。

#### ② 插件任务级 `settingsFrom` ⇒ `Prepare` 过了，但推不上去

按 ① 的结论把凭据改挂插件 `settingsFrom` 后，`Prepare` 转绿、stage 也进了，
却在推送时换了一个**看着很不相干**的报错：

```
Configuring Git...
Setting up authentication type: https
HTTPS setup completed
...
Local tags count: 2
Pushing all branches
fatal: could not read Username for 'https://github.com': No such device or address
Error: Failed to push all branches
```

注意日志里 `HTTPS setup completed` **只说明走到这一步了**，不代表凭据写成功了——
插件的 `setup_https()` 是这样的：

```sh
setup_https() {
  if [ ! -z "$PLUGIN_USERNAME" ] && [ ! -z "$PLUGIN_PASSWORD" ]; then
    echo "https://$PLUGIN_USERNAME:$PLUGIN_PASSWORD@$DOMAIN" > $HOME/.git-credentials
  fi            # ← 没有 else：凭据为空时静默跳过，什么都不打印
}
```

所以「`HTTPS setup completed` 之后 git 还要用户名」= **`PLUGIN_USERNAME` / `PLUGIN_PASSWORD`
是空的**，凭据文件根本没写。

为什么空？`settingsFrom` 的语义是「从文件**加载插件参数**」（文件里的 `KEY` 直接当插件参数名），
**它不注入环境变量**；而 `settings` 里写的 `username: ${GIT_USERNAME}` 是**环境变量替换**。
两者对不上 ⇒ 插件最终拿到空的 username/password。

> CNB 文档《文件引用 › image 检查说明》原文：
> 镜像任务参数「可通过 `settingsFrom` 设置，也可通过 `imports` 引入后以**环境变量**方式设置，
> **两种方式均视为插件任务引用文件**」。
> 前半句就是 ① ② 两个形态的来源，后半句是解药——见 ③。

#### ③ 正确形态：**插件任务级 `imports`**（与 `image` 平级）

把凭据引用**从流水线级下移到插件任务内部**（与 `image` 同级），并且**用 `imports`**：

```yaml
main:
  push:
    - stages:
        - name: 同步到 GitHub（全分支 + 标签）
          image: tencentcom/git-sync
          imports:                                       # ← 与 image 平级，不是流水线级
            - https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/vars.yml
          settings:
            target_url: https://github.com/imoyao/fundmate.git
            auth_type: https
            username: ${GIT_USERNAME}                    # 环境变量替换：imports 注入后才解析得出
            password: ${GITHUB_PAT}
            push_tags: true
```

为什么这样就对：

- **位置**：插件任务级 `imports` 同样是**合规的插件引用**（官方文档「两种方式均视为插件任务
  引用文件」），故 `allow_images` 检查通过 ⇒ 解 ①；
- **语义**：`imports` **注入环境变量** ⇒ `settings` 里的 `${GIT_USERNAME}` 解析得出
  ⇒ 插件拿到真实凭据 ⇒ 解 ②。

这也是 git-sync 插件作者给的**官方示例形状**——其仓库 `example.yml` 正是
`imports: <密钥文件>` + `username: "${GIT_USERNAME}"`（见
[插件仓库](https://cnb.cool/cnb/plugins/tencentcom/git-sync)）。

判断口诀：

```
「引用挂在哪」决定合规      → 必须在**插件任务内**（与 image 同级）；挂流水线级必死 Prepare
「用 imports 还是 settingsFrom」决定 `${VAR}` 能不能解析
                            → 要在 settings 里用 ${VAR} 就必须 imports；settingsFrom 不注入环境变量
```

⚠️ 迁移时**必须删掉原来那一种写法**：同一份文件两种语义并存（`imports` + `settingsFrom`）
会让「到底哪条生效」变得不可预测，也是过渡期最容易留下的半吊子状态。

#### 静态守卫与它的边界

`scripts/guard_secret_imports.py`（并入 `ci.yml` 的 **`layout_guard`** job；不新增 job，
就不必动 `gate.needs`）拦三条，全部**只读仓库内 `.cnb.yml`**、不拉网络：

1. **密钥类 URL 挂在流水线级（非插件任务级）** —— #148 ① 的回潮；
2. **插件任务用 `settingsFrom` 引密钥、却在 `settings` 里写 `${VAR}` 凭据** —— #148 ② 的回潮
   （这一条是本轮新增，用来钉住「改了位置、但改错了方式」这个半成品）；
3. **同一份 URL 同时出现在 `imports` 与 `settingsFrom`** —— 半吊子迁移。

**判据 1 的边界**：它只认 `push:` / `crontab:` **事件对象直接持有**的
`imports` / `settingsFrom`（即流水线级）；插件任务级的引用在 `stages[*]` 内部，不会被误伤。

**已知假阴性（刻意不拦）**：引用**不声明 `allow_*`** 的普通 YAML 是合法用法（那种文件
既可挂流水线级 `imports`，也不受 `allow_images` 约束），守卫不报错；
只有 URL 里含 `secret` 或结尾是 `vars.yml` 的才进入判据 1 的视野。

#### 守门自己也得先被验过（本仓老规矩）

`guard_secret_imports.py` 带 `self_check()` 探针，用**最小真实形态**的配置验证三件事：

- 合法的「插件任务级 `imports`」形态**不误报**；
- 三个错误形态（流水线级 `imports` / `settingsFrom` + `${VAR}` / 两种语义并存）**各自会报错**。

回归网 `scripts/tests/guard_secret_imports.test.js` 更进一步：它把真实 `.cnb.yml` 里的一处
`imports` **回退成 `settingsFrom`** 写进临时文件，断言守卫确实以退出码 1 报错——探针本身
失效时，那才是真正的假绿（#152 的教训：没有「变异生效」断言的探针就是个假信号）。

### 13.2 Secret 仓库的人工操作清单（本仓改不进 PR）

`.cnb.yml`、模板、文档都能走 PR；**唯独密钥仓库那份 `vars.yml` 只能人工在 Web 改**。
以下步骤需在 CNB Web 界面执行（AI / CLI 读不到也写不了，`Secret repos do not support
token access`）：

1. 打开 `https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/vars.yml`（需登录且有权限）；
2. 对照本仓模板 `docs/ops/git-sync-secret-vars.example.yml` 逐项核对：
   - 文件是**YAML**（`KEY: value`），不是 `.env` 的 `KEY=VALUE`；
   - 有 `GIT_USERNAME` 与 `GITHUB_PAT`（PAT 需 `repo` 权限）；
   - 四个 `allow_*` 齐全：`allow_slugs`（本仓 slug）、`allow_events`（`push` + `crontab:*`）、
     `allow_branches`（`main` / `dev`）、`allow_images`（`tencentcom/git-sync` 及其 `:*` glob）；
   - 没有多写 `allow_tags` / `allow_users`（字段不存在，写了静默不生效）；
3. **保存后手动触发一次任一条 git-sync 作业**（`main` 分支 → 运行流水线 → 选 `push` 或
   `crontab: 0 * * * *`），确认 `Prepare` 转绿、stage **能进且能推成功**（`Pushing all branches`
   之后不出现 `could not read Username`）；
4. 两种红灯的归属不同，别混：
   - `Prepare` 报 `declares allow_images` ⇒ 是 **`.cnb.yml` 的引用位置**错（还挂在流水线级，
     或改动没发版到 `main`），**不是**密钥仓库的问题；
   - `stage-0` 报 `could not read Username` ⇒ 是 **`.cnb.yml` 的引用方式**错（用了
     `settingsFrom` 却写 `${VAR}`）；先跑 `python scripts/guard_secret_imports.py` 自证。

> ⚠️ 改密钥仓库时同步更新本仓模板——两者是**内容同步的副本**，模板漂了，
> 后续排查就会对着过期事实判断。注意：`settingsFrom` 路线**不需要**改密钥仓库
> （保持 `GIT_USERNAME` / `GITHUB_PAT` 的键名即可），这正是选它的原因之一。

### 13.3 分支范围收窄：`main` **不外推、也不被覆盖**（源 CNB #167 / #172）

**这条的口径（用户 2026-10-14 在 CNB #167 明确）**：

> **CNB 的 `main` 与 GitHub 的 `main` 没有任何关系。** CNB `main` 只由 CNB 自己的
> 发版 PR（`dev` → `main`）推进，既**不外推**给 GitHub，也**不被覆盖**。
> CNB 的 `dev` 推给 GitHub `dev` 是可以的；CNB 从 GitHub 拉代码也是可以的。
> 判据一句话：**「CNB `main` 不能有 `dev` 没有的代码」**（发版 merge commit 除外）。

**两个方向各有一个「默认行为会碰 `main`」的陷阱**，且第二个反直觉：

| 方向 | 不写 `branch` 时插件干什么 | 后果 |
|---|---|---|
| **push** | `git push <target> --all`（源码 else 分支） | 把 CNB 的 `main` 一并推给 GitHub |
| **pull** | 取 target 的**全部**分支，逐个 `git pull --rebase` 后 **`git push origin <b> --force`** | **把 GitHub 的 `main` force 覆盖到 CNB 的 `main`**（不看是否 fast-forward） |

> ⚠️ **「pull 只拉不推、不会分叉」是直觉错误**（#167 收尾实测，读插件 `entrypoint.sh` 得到）：
> pull 分支**总会** `git push origin --force` 写回本地 origin。不写 `branch` 时走
> else 分支 ⇒ 遍历 target 全分支 ⇒ GitHub `main` 直接盖掉 CNB `main`。
> 故 **pull 也必须显式写 `branch: dev`**。

**push 方向的分叉症状（#172 回顾）**：2026-10-13 实测 CNB `main` 独有 31 /
GitHub `main` 独有 27、**交集 0**；`crontab` 只能挂在具体分支下、`.cnb.yml` 挂在 `main`
⇒ **真正执行的是 `main` 上那份配置**，而「整改代码」可能躺在 `dev` 上（病在 #118 / #123
已记过两次）。

**修法（四处，缺一不可）**：

| 作业 | 事件 | 目标分支 | 说明 |
|---|---|---|---|
| 推 `dev` | `push:` on `main` | `branch: dev` | 发版前的集成分支；不再带 `main` |
| 每小时兜底推 | `crontab: 30` | `branch: dev` | cron 下没有「当前功能分支」上下文，故只管 `dev` |
| 功能分支 | `"**/!(main|dev)"` 的 `push:` | `branch: ${CNB_BRANCH}` | 精确推触发本次构建的那条分支 |
| **从 GitHub 拉** | `crontab: 0`（`sync_mode: pull`） | **`branch: dev`** | **只拉 `dev`**；不加就会被 GitHub `main` force 覆盖（#167） |

**守卫**：`scripts/guard_git_sync_push_scope.py`（并入 `ci.yml` 的 `layout_guard` job，
阻断），覆盖**两个方向**的四条判据：① 两个方向的 git-sync 都必须显式写 `branch`
（push 不写 = `--all`；pull 不写 = 全分支 force 覆盖）；② `branch` 不得是
`main` / `*` / `--all`；③ `main` 顶层键下不得用 `${CNB_BRANCH}` 推分支；
④ 每个 job 必须带 `name`（见 §13.4）。
回归网 `scripts/tests/git_sync_push_scope.test.js`，含 **5 个**变异回退探针
（push 三种 + **pull 两种**）。

**连带放宽**：`check_cnb_events.py` 的 `BRANCH_NAME` 字符集补上 glob 通配
（`"**/!(main|dev)"` 是 CNB 官方支持的形态，旧字符集把它误判成非法顶层键）。
放宽**不架空**核心判据——`EVENT_LIKE` 仍在 `check_top_keys` 里**先判**，
顶层 `push:` 照样报错，且自检探针用真实 glob 反证（两向）。

**未验证项**（不当作已完成）：`branch: ${CNB_BRANCH}` 在插件 `settings` 里的插值、
以及 Secret 仓库 `allow_branches` 是否放行 `"**/!(main|dev)"` 段，均需在 CNB Web 上
人工确认——本环境跑不了真实流水线。

### 13.4 `crontab` / `push` 下必须写成「job 列表 + 命名 stage」

**症状**：`"crontab: 30 * * * *"` 的 stage 在构建详情的 `get-build-stage` 里**查不到**
（`stage-0` / `stages` / 各类 id 全报「没有查询到该stage信息」）。于是**它内部踢没踢成功
看不出来**——从 `sha` 看它长期挂在旧提交上、实际没推上去，却报**绿**。比红灯更危险。

**根因是结构写法**：把 `stages:` **直接**挂在 `"crontab: ..."` 下（没有 `- name:` 包一层的
job 对象）时，CNB 不把它当标准 job 列表处理，stage 不进可查索引。`push:` 段当时写的是
`- stages: [...]`（正确形态），两者不一致。

```yaml
# ❌ 错：stages 直接挂在事件下，没有 job 对象包一层
"crontab: 30 * * * *":
    stages:
      - name: 同步到 GitHub（每小时兜底）
        image: tencentcom/git-sync

# ✅ 对：job 列表 + 命名 job + 命名 stage（stage 名是 get-build-stage 的查询锚点）
"crontab: 30 * * * *":
  - name: 同步到 GitHub（每小时兜底，仅 dev）
    stages:
      - name: 同步到 GitHub（每小时兜底，仅 dev）
        image: tencentcom/git-sync
```

**判据机械化**：`scripts/tests/git_sync_push_scope.test.js` 里按 `- name:` 切块，
逐条 git-sync 任务断言 `branch` 存在且非禁区——结构回潮会一起暴露
（`stages` 直接挂在事件下时，`- name:` 切块拿不到该任务，测试会报「任务数少了」）。

### 13.5 口径：**CNB 的 `main` 与 GitHub 的 `main` 没有任何关系**（源 CNB #167，2026-10-14）

在 §13.3 的「怎么改」之上，先钉住「为什么这么改」——否则下一个人看到「CNB 落后 GitHub
27 个提交」，第一反应还是「那就同步过去呗」，于是把两侧 `main` 又接到一起。

**用户原话（CNB #167，2026-10-14）**：

> 我们不应该在 CNB 端去更新……CNB 的 `main` 应该和 `dev` 不能超出 `dev`，有超出 `dev` 的代码。
> 我们 CNB 的 `dev` 直接往 GitHub 上面去推送是可以接受的。但是 CNB 上面的 `main` 分支和
> GitHub 上面的 `main` 分支，它们两个应该没有什么关系，不能够把它们两个做一个推送，
> 不然的话肯定会出现问题的呀。我们 CNB 和 GitHub 上面的分支同步的时候，应该是
> **CNB 向 GitHub 同步**，然后 **CNB 拉 GitHub 的代码**。

**翻译成四条可判定的规则**：

| # | 规则 | 判据（可机器验） |
|---|---|---|
| 1 | **CNB `main` 不得有 `dev` 没有的代码** | `git log origin/dev..origin/main` 只允许出现发版 merge commit（内容 diff 为空） |
| 2 | **CNB `dev` → GitHub `dev` 是允许的** | `.cnb.yml` 的 push 任务 `branch: dev`（✅，已落地） |
| 3 | **CNB `main` 与 GitHub `main` 互不推送** | ① CNB 侧没有任何 push 任务的目标是 `main`；② **pull 任务必须写 `branch: dev`**，否则 GitHub `main` 会 force 覆盖 CNB `main` |
| 4 | **方向固定：CNB → GitHub（推 dev）；GitHub → CNB（拉 dev）** | 两个方向都收窄到 `dev`，功能分支走 `"**/!(main|dev)"`（CI 守卫钉住） |

**为什么「CNB `main` 与 GitHub `main` 无关」是对的**：两者的**推进者**不同——
CNB `main` 是 CNB 上发版 PR 的产物（甚至可以是空 diff 的合并节点），
GitHub `main` 是 GitHub 上发版 PR 的产物。它们**恰好内容相近**只是巧合，
一旦「同步」就会把两套发版历史焊在一起（谁赢没定义），这正是 2026-10-13 那场
「交集 0 的双向分叉」的成因。

**存量核对（2026-10-14 实测，CNB 侧）**：

```
CNB main: 8fa55fe6    CNB dev: c76b7621
git log origin/dev..origin/main  → 8fa55fe6（发版 #177）、fc49e500（发版 #162）
git log origin/main..origin/dev  → （空）
git diff origin/dev origin/main  → （空）
```

即：CNB `main` 领先 `dev` 的**只有两个发版 merge commit，内容差异为 0** ⇒
**符合规则 1**（「不能有 `dev` 没有的代码」——这两条没有引入任何代码）。

**回归网**：规则 3 的 ①② 由 `scripts/guard_git_sync_push_scope.py` 阻断；
规则 1 由 `.cnb.yml` 的「分支分叉自检」节点（`check_branch_divergence.py --report --explain`）
持续报告。
