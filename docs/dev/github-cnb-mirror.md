---
title: GitHub → CNB Issue 增量镜像
status: v1.5（2026-10-14，源 CNB issue #2；§9 本地卡对照源自 CNB #117；§13 双向同步三故障/四种失败形态；§13.5 「CNB main 与 GitHub main 无关」口径；§14 本地卡出口）  <!-- cross-repo-ref-allow -->
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

**`$` 段还挂了第二段 `push:`**（CNB #172）：任何分支的 push 都跑一轮**幂等**建卡 +
状态回流。补的是「有人在功能分支上开了张 CNB 本地卡、却永远扫不到」这个缺口
（原作业只挂 `main` 的 cron，一天一次）。见 §14.3。

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
| **只报告，不改卡** | 不写任何 CNB / GitHub 状态 | 改镜像卡正文要产品拍板（CNB #120）；  <!-- cross-repo-ref-allow -->`.cnb.yml` 里用 `\|\| true` 明确「这是信号不是门禁」 |
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

两边判据**刻意不同**，不是不一致。

**结论（CNB #172，2026-10-14）**：出口不是「放宽回写判据」（那会把评论贴到别人卡上），
而是两件更硬的事 ——

1. **规范卡面写法**：引用跨仓卡一律写**完整 URL**（这条已成规则，见 AGENTS.md
   「双端协作」；`scripts/guard_cross_repo_refs.mjs` 把新增的裸引用拦在 CI 上）；
2. **给本地卡一条显式的出口**：结论需要 GitHub 侧看见时，用
   §14.2 的 `local_card_promote.py` 推广——它**只建一次卡、只留一条完整 URL 的链**，
   不靠「裸引用恰好被认出来」这种运气。

## 10. 已知边界

- **不回写、不覆盖、不关**：见 §2。状态用**标记**（§8），不做自动关卡。
- **本地卡不进 GitHub**：见 §9。它们不是「漏同步」，是**本就不该同步**；
  判据、声明方式与 `--report-local` 都在那一节。兜底判定（`fallback`）是**猜**，
  报告里单独计数，别把它的数字当成事实。
- **本地卡的结论有一个显式出口**（CNB #172）：结论需要 GitHub 侧看见时，用  <!-- cross-repo-ref-allow -->
  `local_card_promote.py` **推广**成一张 GitHub 卡（§14.2）。它是**人工决定 + 三步固定动作**，
  不是自动镜像——别把「有出口」读成「会自己同步」。
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

### 判据（2026-10-14 定型，源 CNB #167 / #179）

只认一件事：**`main` 有没有 `dev` 拿不到的代码**。判据说到底就是用户口径那句
「CNB 的 `main` 不能有 `dev` 没有的**代码**」。

**两个旧口径都产生过假红**，各修掉一层，值得都记下来 —— 它们看着都「挺对」：

| 旧口径 | 为什么会误报 |
|---|---|
| ①「`main` 独有提交数 > 0 ⇒ 分叉」 | 发版 PR 必然给 `main` 留一个 merge commit，而它**不引入内容** ⇒ **每发一次版红一次** |
| ②「`git diff main dev` 非空 ⇒ 分叉」 | `git diff` 是**双向**的。非空既可能是「`main` 有 `dev` 拿不到的」，也可能是「`dev` 更新、`main` 停在旧版」。本仓 2026-10-14 实测正是后者：7 个文件的 diff 全是 `main` **更旧**（numstat 里删除数远大于新增），一条「`main` 独有内容」都没有 |

#### 三层判据（提交级 + 内容级；任一层成立才红）

**先说结论**：本仓「发版滞后」是**正常态**（`dev` 一直在前进，`main` 停在上一发版点），
**不得报红**。拿它当红灯喊久了，红灯就不再被人当真 —— 这比没有自检更坏。

| 层 | 判据 | 红？ |
|---|---|---|
| **提交级** | `main` 独有提交是 merge，且其**第二父**是 `dev` 的祖先 | ✅ 合规发版，**不红** |
| | `main` 独有提交是**普通提交**（非合并） | ⚠️ **红**（有人绕过 `dev`） |
| | merge 的**第二父不是** `dev` 的祖先（如 `feature` → `main` 直通车） | ⚠️ **红** |
| | 提交类型**读不出**（拿不到父提交 / 祖先关系） | ⚠️ **红**（拿不到 ≠ 正常，#171） |
| **内容级** | `git cherry <right> <left>` **无 `+` 行**（`main` 的改动 `dev` 全有） | ✅ **不红** |
| | 有 `+` 行（`main` 上有 `dev` 拿不到的改动），报告点名路径 | ⚠️ **红** |

退出码：`0` 无新形态；`1` 有新形态；`2` **取不到分支**。
（`2` 与「有新形态」分开：「分支不存在」与「判出问题」是两件事，混在一起就分不出是哪一种。）

#### 内容级判据一定用 `git cherry`（补丁等价），**不得**用这两个

两个看着都很对的替代实现，实测各有盲区，都被淘汰：

- **`git diff main dev` 非空**：`diff` 是**双向**的 ⇒ 「`dev` 领先、`main` 停在旧版」
  也非空。本仓 2026-10-14 实测 7 个文件的 diff 全是 `main` **更旧**，
  一条「`main` 独有内容」都没有 ⇒ **假红**。
- **逐文件 blob 历史**（`git log --find-object=<blob>`）：它遍历 `git diff --name-only`
  的路径，只处理 `left` 侧**存在**的路径 ⇒ `left` 上**纯删除**的文件（`left:{path}`
  解析失败）被跳过 ⇒ **假绿**。实测（`main` 合过 `dev` 后删掉一个 `dev` 里还在的文件、
  `dev` 再前进）：`git cherry` 报 `+`（真违规），逐文件法给「✅ 两侧内容一致」。
  回归网 `test_cross_merge_deletion_on_left_is_red` 与
  `test_content_ahead_uses_cherry_not_diff` 把这条钉死。

`git cherry` 以**补丁**为单位，没有上面两个盲区，且是一个判据直接回答被问的问题
—— 不再拼「diff + 祖先关系」那条两步路。

```bash
git cherry <right> <left>   # 逐行 `+ <sha>`（right 缺这条改动）/ `- <sha>`（right 已有等价补丁）
```

- **没有 `+` 行** ⇒ `left` 的改动 `right` 全有 ⇒ 放行（发版滞后不算分叉）；
- **有 `+` 行** ⇒ `left` 上有 `right` 拿不到的改动 ⇒ 红，并逐个列出 sha 与涉及路径。

#### 两个「拿不到输入」都不得降级成正常（#171 / #179）

`commits_readable` 为假、或 `content.available` 为假 ⇒ **红**，并在报告里明说
「本轮结论不可信」。这条是被实测咬出来的：`check_mirror_refs.py` 的假绿
（拉不到 GitHub issue 就报「已对齐」）同族，都是「拿不到输入 ⇒ 退化成一个看起来正常的结论」。

#### 方向：**第二父**，不是第一父

`git log --format=%P` 的**第一父**是当前分支自己的历史（`main` 上继续的那个），
**第二父**才是被合入的一侧。取第一父判「是不是 `dev` 的祖先」，会把**每一笔合规发版
都判成违规**。回归网 `test_classify_commit_release_uses_second_parent` 造了一个
「第一父不是 `dev` 的祖先、第二父是」的发版合并，专门钉住这个方向。

### 辅助信号（仍会打印，供人看结构）

- 两侧**互不包含**时说明「形态上是双向分叉，**是否报红看上两段判据**」；
- 列出两侧互不包含的「决定什么会被执行」的文件（`.cnb.yml` + `.github/workflows/*.yml`）；
- ⚠️ **提交数不是判据**：交叉合并下两侧会「互不包含」而 `left` 其实零独有内容。

`.cnb.yml` 里带 `|| true`——它是信号，不是门禁。

#### 内容级的返回字段是契约（不准悄悄改）

`content_ahead()` 返回 `{available, has_only_left, only_left_commits, files}`：

- `available=False` ⇒ **判据不可用**（`git cherry` 取不到结果），调用方按红处理；
- `has_only_left` ⇒ 有没有 `+` 行（判据的**唯一**结论）；
- `only_left_commits` / `files` ⇒ 给报告点名用。

旧实现那套「逐文件分别填 `files`（独有）/ `superseded`（停在旧版）」已随判据改为
`git cherry` 一并删除 —— 那两个列表**语义互斥**、同时填会让同一路径出现在报告两处、
**自相矛盾**（本仓 #123 时代 `list_side_only` 就踩过同型 bug）。现在只有一个结论字段，
矛盾在结构上就不可能出现。

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
| **判据选型** | 内容级用 `git cherry`（补丁等价），提交级看 merge 的**第二父** | `git diff` + 祖先关系在交叉合并下假红（#179）；第一父是当前分支自己的历史，取它会误判合规发版 |

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

### 13.5 口径：**CNB 的 `main` 与 GitHub 的 `main` 没有任何关系**（源 CNB #167，2026-10-14）  <!-- cross-repo-ref-allow -->

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
## 14. 本地卡的出口：推广 + 兜底挂载（源 CNB #172，2026-10-14）

> 本节回答用户 2026-10-14 在 CNB #172 的两个质问，两问都指向**真缺口**：
>
> 1. 「只对 CNB 生效的这些改动，它会永远留在 CNB 里面，然后不会同步到 GitHub 上面吗？」
> 2. 「我们有一些其他的分支在实现其他的功能，这个 issues 是不是无法感知到这一块？」

### 14.1 先把「只对 CNB 生效」拆成三类（这是困惑的根源）

「只对 CNB 生效的改动」不是一件事，是三件，处理方式各不相同：

| 类别 | 能不能到 GitHub | 机制 |
|---|---|---|
| **代码改动** | **能** | `push:` 段（`branch: dev`）+ `"**/!(main|dev)"` 段（`branch: ${CNB_BRANCH}`） |
| **issue / 评论** | **能** | `cnb-github-backfill.yml` 每日拉取（只回写**镜像卡**上的评论） |
| **CNB 本地卡的结论** | **原先不能，现在按需能** | 见 §14.2 的推广通道 |

前两类此前已经通了，**第二类里的「本地卡评论」是真正的缺口**：本地卡
（D49 / CNB `#117`）按设计不镜像到 GitHub，于是它上面的讨论**没有任何出口**——
实测规模：123 张 CNB 卡里 12 张是本地卡，它们上面有 **72 条**评论永远到不了 GitHub。

> 一句话：**代码是双向流动的，issue 也是（有边界），只有「本地卡上的结论」原先没有出口。**

### 14.2 出口：`local_card_promote.py`（人工决定、脚本执行）

不自动判定「哪张本地卡该推广」——脚本猜错会往 GitHub 灌一堆讲 CNB cron 的卡。
把「**人工决定**」与「**三步固定动作**」分开：

```bash
# ① 先看有哪些本地卡（只读，与 `--report-local` 同一判据）
python scripts/bridge/local_card_promote.py --list

# ② 演练（默认 dry-run，不写任何东西）
python scripts/bridge/local_card_promote.py --cnb 172 \
    --title '<GitHub 卡标题>' --body-file /tmp/promote-body.md

# ③ 执行：GitHub 建卡 → CNB 原卡留链 → 刷新镜像
python scripts/bridge/local_card_promote.py --cnb 172 \
    --title '<GitHub 卡标题>' --body-file /tmp/promote-body.md --apply
```

三步缺一不可，且**顺序固定**（先 GitHub 后 CNB：GitHub 建卡失败则 CNB 一个字都不改，
不会留下「半个推广」）：

1. **GitHub 建卡**：用推广正文（**去掉 CNB 味的标题**），默认挂 `CNB 本地` 标签；
2. **CNB 原卡留链**：在评论区追加一条「## 已推广到 GitHub」，给**完整 URL**——
   这是本卡唯一不会被任何机制覆盖的位置（正文是只读的）；
3. **刷新映射**：调既有建卡作业，让新卡的评论按常规通道回流。

#### 为什么第 2 步必须是**完整 URL**

`cnb_github_backfill.py` 的 `resolve_github_number` **只认完整 URL**，裸引用
（`imoyao/fundmate#2034`）会被**静默跳过**——CNB `#117` 正文写的就是裸引用，
于是它一直没能参与回写，而没有任何报错。回归网把这条钉死在
`scripts/tests/test_local_card_promote.py::test_链接是完整URL`。

#### 幂等与重跑

推广键 = `sha1(CNB 编号 | GitHub 编号)` 的前 12 位，写在 CNB 原卡那条评论的**隐藏标记**
（`<!-- 推广键：… -->`）里。另有一道兜底：建卡前先按**完全相同**的标题搜一遍 GitHub
（模糊匹配会撞上「标题像但其实是另一件事」的卡，那比重复建一张更贵）。

### 14.3 第二个缺口：功能分支上的新卡没人扫

**症状**：建卡作业原先只挂 `main` 的 `crontab: 0 18 * * *`。有人在 `feat/*` 上开一张
CNB 本地卡 ⇒ **永远扫不到**，因为作业只跑在 `main` 上、且一天一次。

**修法**：`.cnb.yml` 的 `$` 段新增一段 `push:`，任何分支的 push 都跑一轮
**幂等**建卡 + 状态回流：

```yaml
$:
  push:
    - name: issue 镜像兜底（任何分支，幂等）
      stages:
        - name: 增量建卡（幂等，任何分支）
          script: python scripts/bridge/github_cnb_issues.py --apply
```

**为什么敢挂在 push 上**：两个作业都是**幂等**的——`github_cnb_issues.py` 靠
`GitHub 编号：#N` 判重，`mirror_state_sync.py` 靠评论里的 `状态键：`。重复跑的成本是
「多几次 API 调用」，不是「重复建卡 / 重复发评论」。

**为什么只挂这两条**：其余自检（引用时效 `check_mirror_refs.py`、分支分叉
`check_branch_divergence.py`）读的是「仓库整体状态」，push 到功能分支时结论并不会更新，
留在 `main` 的 cron 里跑即可。

**为什么 `$` 段不挂 git-sync**：`$` 事件不属于任何分支，`CNB_BRANCH` 在此不可靠；
一旦有 git-sync push 落在这里就可能把 `main` 推给 GitHub——那正是 §13.3 要消灭的分叉来源。
回归网 `scripts/tests/git_sync_push_scope.test.js` 最后三条断言钉住这一点
（含一条「`$` 段里不得出现 `tencentcom/git-sync`」）。

### 14.4 边界（不要把这套读成「本地卡会全自动回流」）

- 推广**是人工决定**的：脚本不猜哪张卡该推广，`--list` 只负责把候选列出来；
- **不是全自动镜像**：推广之后，原 CNB 卡与其 GitHub 新卡是**两张卡**，靠原卡评论区
  那条链接互相指认；本地卡正文的后续修改**不会**自动同步过去；
- **`$` 段兜底不等于实时**：它跟着 push 走，`feat/*` 上没有新动作时当然不会触发；
  这不是「巡逻」，只是「有动静就顺手扫一遍」。

### 14.5 关联

- 决策与口径：D49（CNB 本地卡）、D52（本地卡识别与对照报告）、本节（出口通道）；
- 上位规范：AGENTS.md「双端协作（CNB ↔ GitHub）」；
- 相关卡：CNB #117（本地卡定义）、#120（更正台账）、#167（push 收窄）、#172（本卡）。

## 15. 认领同步：两边不再同时改同一张卡（源 CNB #179）

> 本节回答用户 2026-10-14 在 CNB #179 的问题  <!-- cross-repo-ref-allow -->：**「我们在 CNB 上修某个 issue，GitHub 那边
> 怎么知道？应该有一套约束——CNB 认领了就相当于认领了这个问题，GitHub 不要再做同一个。」**

### 15.1 先把问题说准：这不是「同步」，是「去重」

前面十四节讲的都是**同一份事实的两份副本怎么对齐**（镜像、回写、状态回流）。
本节是另一件事：**一件工作被两边同时领走**。

实测已经发生过一次，就在这张卡自己身上：

| | CNB PR #180 | CNB PR #181 |
|---|---|---|
| 标题 | `fix(bridge): 分叉判据二分 + 交叉合并假阳性（CNB #179）` | `fix(bridge): 分叉判据改正（main 独有 vs main 停在旧版），消两组假红（CNB #179）` |
| base | `dev` | `dev` |
| 结局 | 都合并了，冲突要人工逐处消解（`724e5add`） | |

两条线**改同一批文件**、**目标同一张卡**，各自都自洽，直到合并时才发现撞了。
这不是谁做错了，是**没有任何机制让第二个人知道第一个人已经动手**。

### 15.2 认领的判据：只看事实，不看声明

不看「谁说了什么」，只看**已经发生的事**：

| 判据 | 说明 |
|---|---|
| **CNB 侧有 open PR，其标题/正文引用这张卡** | 标题里的 `（#167）` 就是「本次在做的卡」 |
| **CNB 镜像卡本身 open** | 关掉的卡上写「正在处理」是自相矛盾 |
| **它是镜像卡，不是本地卡** | 本地卡（§9 / D52）不进 GitHub，没有可挂标签的对象 |

**刻意不做的判定**：

- **不看 assignee**——assignee 是意图，不是事实；而且 GitHub 侧的 assigned 由 GitHub 自己管；
- **不看「评论里有人说在改」**——那句话下次就不算数了。

一句话：**事实优先于声明**。

### 15.3 「实时」的诚实口径（用户最在意的一点）

用户的诉求是「**实时感知，不能靠每小时拉或推**」。这个诉求被**凭据与事件拓扑**挡住，
而且不是「还没做」，是**结构上做不到**：

| 方向 | 有没有凭据 / 通路 | 结论 |
|---|---|---|
| CNB 构建 → 写 GitHub | ✅ 有（Secret 仓库 `GITHUB_PAT`，与 git-sync 同一份） | CNB **有能力**挂标签 |
| GitHub 事件 → **叫醒** CNB 流水线 | ❌ 本仓没装 GitHub App，也没有 webhook 中继 | CNB **收不到**「GitHub 有人动了那张卡」 |
| GitHub Actions → 读 CNB | ✅ `GITHUB_TOKEN` 自动注入（CNB 公开仓匿名也可读） | **这条通** |

> ⚠️ 顺带纠正一条本仓流传过的错话：**「CNB 构建环境没有 GitHub 凭据」是错的**。
> 那条报错（`could not read Username`）指的是**手工 `git push`**；走**插件任务 +
> Secret imports** 这条路是通的——git-sync 三个方向全在跑就是证据（§13.1）。

**既然「叫醒」做不到，就把方向掰过来——自己那一侧的事件由自己订阅：**

| 方向 | 谁驱动 | 延迟 | 落点 |
|---|---|---|---|
| **GitHub 有人动手** → CNB 镜像卡评论区 | `.github/workflows/claim-sync.yml`（订阅 `issues` / `pull_request` 事件） | **秒级** | `claim_detect.py --apply` |
| **CNB 有人动手** → GitHub 原卡挂 `CNB 处理中` | `.cnb.yml` 的 `$` 段 `push` | **分钟级**（跟着 push 走） | 同左 |

两个方向合起来才是「实时」：**没有任何一方在轮询对方**，各自订阅自己能收到的事件。

**CNB 侧为什么用 push 而不是 cron**：认领是「有人正在干活」的影子，而「干活」= push。
挂 `$` 段 ⇒ **任何分支一有 push 就顺手报一次**。挂 cron 反而更差（cron 只能挂具体分支，
会退化成「一小时一次」）。

**CNB 侧为什么能挂插件任务**（§14.3 刚说过 `$` 段不能挂 git-sync）：
那条禁令的理由是 `CNB_BRANCH` 在 `$` 下不可靠 ⇒ 可能误推 `main`。
本任务**不推任何东西**（只读 CNB、写 GitHub 的 issue 标签），没有 `branch` 参数，
也就没有 `main` 可误推。`git_sync_push_scope.test.js` 里那条「`$` 段不得出现
`tencentcom/git-sync`」断言**依然成立**，不要为了本任务放宽它。

### 15.4 标签会自己消失（「狼来了」的反面）

只挂不摘的标签会变成噪音，下一个人学到的教训是「别信那个标签」——比不挂更坏。
故每次事件都重新评估：

| 形态 | 动作 |
|---|---|
| CNB 侧有 open PR 引用这张卡 | 挂 `CNB 处理中` + 留一条认领评论（**只发一次**） |
| 认领的 PR **集合变了**（第 2、3 条线加入） | 补一条说明评论（标签说不出「哪些 PR 在动」） |
| CNB 侧**没有** open PR 引用它了 | **摘掉标签**（评论不删，历史留着） |
| 数据不完整（拉不到 CNB 卡 / PR / 带标签清单） | **什么都不做**，且不得宣称「已对齐」 |

最后两行是**刻意相反**的两条：**摘多了比留多了贵**（误摘一张其实有人动的卡，
下一个人就会去动它）。所以「拿不到输入」时一律**不摘**，并如实报出来。

### 15.5 幂等：三条独立的键

敢挂在每次 push / 每个事件上的前提是幂等：

| 对象 | 幂等键 | 重复跑会怎样 |
|---|---|---|
| 标签 | GitHub `POST /labels` **原生幂等** | 不重复挂、不报错 |
| 认领评论 | 正文末尾 `<!-- cnb-claim: github=N prs=… -->` | 同一事实只发一次 |
| 「PR 集合变了」评论 | 标记里的 `prs=` 列表 | 只在集合真的变大时才发 |

### 15.6 从 PR 里认「它在做哪张卡」：为什么**只信标题**

这是本节唯一一处**被实测推翻**的设计，值得单独记。

初版收正文里的裸 `#N`。在 5 个真实 CNB PR（#180 / #181 / #182 / #210 / #238）上
逐行核对后，**抽出的 7 个裸号里 4 个是别的东西**：

| 真实原文 | 抽出的 | 那其实是 |
|---|---|---|
| ``上一张 PR #210 已合入 dev`` | 210 | **CNB PR** 编号，不是卡 |
| ``（#1403 的形态）`` | 1403 | **GitHub** 侧卡号 |
| ``撞 #1403 同族限流`` | 1403 | GitHub 侧卡号 |  <!-- cross-repo-ref-allow -->
| ``#2034 口径 tooltip`` | 2034 | GitHub 侧卡号 |  <!-- cross-repo-ref-allow -->

而 CNB 编号连续、镜像卡从 #5 起 ⇒ **这些号在 CNB 侧确实存在同号卡** ⇒ 标签挂到
一张完全不相干的卡上。这正是本脚本最贵的一种错。

**试过四条行级启发式，全部不够**：行内 `PR #N`、GitHub 字样、行内代码、加粗。
真实行文里 `**（#1403 的形态）`（加粗没闭合）、`撞 #1403 同族限流`（纯散文）都躲得过去。
继续加启发式，就是在拟合今天这 5 个样本——正是本仓「判据要能被证伪、不要拟合」反对的。

**故改用结构性判据：标题 = 这件事是什么，正文 = 怎么做的。**

| 形态 | 收不收 | 理由 |
|---|---|---|
| 完整 URL `https://cnb.cool/<slug>/-/issues/N` | ✅（标题 + 正文） | 人主动挂的源，无歧义 |
| 限定写法 `CNB #N` / `CNB 的 #N` / `CNB 侧 #N` | ✅（标题 + 正文） | 明确挂了源 |
| **标题里的裸 `#N`** | ✅ | 标题里的编号必然是本次在做的卡 |
| **正文里的裸 `#N`** | ❌ | 多数是在引用别的东西（见上表） |

**已知假阴性**：正文写裸 `#106`、且标题没写卡号的 PR 会被漏掉 ⇒ 少挂一个标签，
下一个人仍能从 PR 里看到这件事。**宁可漏，不可错。**

### 15.7 这个脚本做什么、不做什么

| | 内容 |
|---|---|
| **做** | 认领识别（CNB open PR 引用 → 镜像卡 → GitHub 卡）、挂/摘 GitHub 标签、写认领评论 |
| **不做** | 不写 CNB（CNB 侧只读）、不关任何卡、不自动合并、不猜「哪张卡该被认领」 |
| **凭据** | `GITHUB_PAT`（来自 Secret 仓库，与 git-sync 同一份，**不要**另存一份） |
| **缺凭据时** | 脚本自己以退出码 1 失败（不是静默跳过）——认领的假绿最坏：标签没挂上，所有人却以为挂上了 |

跑法：

```bash
# 只报告（默认，不写任何东西）
python scripts/bridge/claim_detect.py --report
python scripts/bridge/claim_detect.py --report --cnb 179   # 只看一张卡

# 真正执行（需要 GITHUB_TOKEN / GH_PAT）
python scripts/bridge/claim_detect.py --apply
```

回归网：`scripts/tests/test_claim_detect.py`（**51 条**），含 **14 个变异探针**
（拿不到输入报已对齐 / 本地卡闸门摘掉 / 评论不再幂等 / unknown 静默丢弃 / 缺 token 不失败 /
已关闭卡算处理中 / 已合并 PR 算正在干 / 外部仓库链接当自己的编号 / 标签只挂不摘 /
数据不完整也摘 / 无认领时提前返回 / 新增 PR 不补评论 / 正文裸号也收 / 标题裸号不收）。

> ⚠️ 两条探针是**写完之后才发现测试没咬住**的，处置都是**补用例**而不是改断言迎合：
> ① 「本地卡闸门」的初版 fixture 用的是「本地卡不引用任何 GitHub 卡」，摘掉闸门仍然绿
> ——真实危险形态是**本地卡正文里引用了 GitHub 卡**（AGENTS.md 要求跨仓引用写完整 URL，
> 所以这很常见）；
> ② 「数据不完整不摘标签」只在**无认领**那条路上断言过，而摘除代码在**有认领**那条路上
> ——`if complete or dry_run` 换成 `if True` 仍然绿。

### 15.8 边界（不要把这套读成「两边再也不会撞了」）

- **只在 CNB 侧**：本机制识别的是「**CNB** 有人在动」。GitHub 侧两个人同时动手，
  由 GitHub 自己的 assignee / PR 关联管，本机制不介入；
- **标签是信号不是锁**：它不阻止任何人动手，只是让人**看得见**。要「锁」得靠
  assignment + 分支保护，那是另一件事（本仓没做，也不打算做——会拖慢单人开发）；
- **CNB 侧的延迟 = 距离上一次 push**：功能分支上长时间没 push，GitHub 侧就看不到认领；
- **摘标签依赖 GitHub 事件或 2 小时一次的兜底 cron**：CNB 侧「撤回了 PR」不会被 CNB 推上去
  （撤回是删分支，不一定触发 push），故靠 GitHub 侧的兜底 cron 收敛。

### 15.9 关联

- 源：CNB #179（用户提的「两边不打架」+「不要每小时拉推」）；
- 决策：D57；
- 邻居：§13.3（`main` 独立）、§14（本地卡出口）；D52（本地卡定义）；
- 邻居卡：CNB #167（push 收窄）、#172（`$` 段兜底）、#171（拿不到输入不得报正常）。

## 16. 守卫自己的两个洞：判据 1 曾经「跳过真 bug 所在的那一段」（源 CNB #269，2026-10-14）

> 这一节记的是**守卫的失败**，不是同步链路的失败。写它的理由与 §0 的老规矩一致：
> **判据的假绿比假红贵得多** —— 假红会有人来查，假绿会让刚修好的东西被当成「本来就合规」。

### 16.1 起因：`$` 段里有一个每跑必红的作业

CNB `$` 段 push 下的 `认领同步`（`tencentcom/http-request` 插件）把 `imports`
挂在了 **job 对象**上 —— 那就是**流水线级**。平台判定「声明了 `allow_images` 却没在插件任务里用」，
该作业**每跑必红**，死在 Prepare：

```text
vars.yml declares allow_images and can only be referenced by plugin tasks.
```

同一个坑 §13.1 在 git-sync 上已经踩过一轮（CNB #148），这一段是新作业**重犯**。

### 16.2 但真正值得注意的是：守卫当时报绿

`scripts/guard_secret_imports.py` 的两处遍历都写着：

```python
if branch.startswith('.') or branch == '$':
    continue
```

——把 `$` 段和锚点键（`.mirror-job`）**一起跳过了**。于是：

| 谁 | 结论 |
|---|---|
| 线上 | `认领同步` 每跑必红 |
| 守卫 | ✅ 合规（因为那一段它压根没看） |

**判据 1 的盲区恰好覆盖真 bug 所在的段。** 回退探针实测 MISSED —— 这正是本仓
「守门通过 ≠ 守门有效」那条规矩存在的理由：光看守卫绿，会把「刚修好」读成「本来就对」。

`$` 不是锚点，它只是「**所有分支**」的写法，语义上仍是一个分支段，插件任务规则完全适用。

### 16.3 第二个洞更隐蔽：URL 级白名单把判据 1 架空了

判据 1 原来有一条豁免：

```python
if url in plugin_level:      # 该 URL 在**任意**插件任务级出现过
    continue                 # ⇒ 放过
```

它的初衷是给判据 3（「同一引用对象两种语义并存」）去重，但它**顺手把判据 1 也豁免了**。
而本仓**所有 job 引的是同一份 `vars.yml`** ⇒ 只要 git-sync 的某条 stage 挂对了，
**任何一条挂错的 job 都会被放过**。

合规是**每个挂载点各自**的属性，不能由别处的正确豁免。现在的判据按
`(键, URL, 挂载路径)` 三元组去重，白名单只服务于判据 3。

> 复现方式：把 `$` 段某个 job 的 imports 挪到 job 对象上，同时 git-sync 那几处**保持正确**
> —— 旧判断会报绿。这条已固化成回归网用例。

### 16.4 现在的判据（三条，逐挂载点）

| # | 判据 | 形态 |
|---|---|---|
| 1 | 密钥 URL 不得出现在 **job 对象**（`stages:` 之外）上 | 不论别处挂得多对 |
| 2 | 插件任务用 `settingsFrom` 引密钥、却在 `settings` 里用 `${VAR}` | §13.1 ② 形态 |
| 3 | 同一份 URL 同时被 `imports` 与 `settingsFrom` 引用 | 半吊子迁移 |

遍历范围：**除锚点键（`.` 开头）外的全部段**，含 `$`。

### 16.5 回归网

- `scripts/tests/guard_secret_imports.test.js` 新增 3 条：
  - `$` 段的流水线级 imports 必须报错（#269 ①）；
  - `$` 段的插件任务级 imports 不得误报（反向，防止「一刀切跳过」改法）；
  - 「别处挂对、这一处挂错」必须报错（#269 ②）；
- 守卫自带 `self_check()` 探针同步补了两条。
- 四条回退探针实测：跳过 `$` / 恢复 URL 白名单 / settingsFrom / 流水线级 —— **全部 CAUGHT**。

### 16.6 第二轮（同一天）：真根因是「**job 的类型**」，前三条判据结构上抓不到

第一轮修完、合并进 `dev`（`0a78f8fd`）之后，我拉了**真实构建结果** —— **它还是红的**，
同一条报错：

```text
[认领同步] The file: .../fundmate-secret/-/blob/main/vars.yml declares allow_images
          and can only be referenced by plugin tasks.
```

**为什么「挪到插件任务级」没用**：CNB 的 `stages:` 元素**本身就是那个 Job**（《语法手册》：
「当 Stage 只有一个 Job 时，可省略 Stage 层级」）。所以我从 job 对象挪到 stage 里，
**只是把同样的东西写在了同一个地方的另一侧** —— 判据 1 的「第几层」这个轴，
在这件事上根本不存在。

真根因在《文件引用 › 权限检查 › image 检查说明》里，两条连起来读：

> - 非插件任务的 image 为空字符串，无法匹配任何 glob 表达式；配置文件声明了 `allow_images`
>   **将不能被非插件任务引用**
> - **Job 同时设置 `image` 和 `script` 属于以 image 作为执行环境的脚本任务**

`认领同步` 同时写了 `image: tencentcom/http-request` 和 `script:` ⇒ 它是**脚本任务**
（image 只是跑 script 的容器），`allow_images` **永远匹配不上**。
git-sync 那三条能过，正是因为它只有 `image` + `settings`、**没写 `script`**。

**修法**（⚠️ **这一格后来又被改过一次，见 §16.10 —— 当时写的「配到流水线环境变量」是错的**）；
真根因确认在 `allow_images`，修法见 §16.10。

**新增判据 4**：脚本任务（带 `script`/`commands`）上引用**带 `allow_images` 的**密钥文件、
或用 `settingsFrom` 引密钥 —— 前三条判的是「挂在第几层」（语法层），
这一条判的是「job 是不是插件任务 + 被引文件是给谁用的」（**语义层**）。

| 判据 | 判什么 | 层 |
|---|---|---|
| 1 | 引用不在 job 对象上 | 语法 |
| 2 | `settingsFrom` 不配 `${VAR}` | 语法 |
| 3 | 两种语义不并存 | 语法 |
| **4** | **脚本任务不得引带 `allow_images` 的密钥文件 / 不得用 `settingsFrom`** | **语义** |

### 16.6.1 这一轮真正学到的东西

**「位置对不对」有两层 —— 配置语法层（守卫能查）和平台语义层（守卫查不了）。**

第一轮我把「守卫绿」当成了「线上一定绿」，于是报了个「已完成」。**它当时还红着。**
守卫只验配置的形状；「一个 `image` + `script` 的 job 到底算不算插件任务」是**平台语义**，
静态文本里看不出来 —— 只有真实构建能验。

所以这一轮的流程改了：**改完必须用真实构建验证，不再只看守卫**。
（构建号见 §16.8；这一条比任何判据都贵。）

### 16.7 借这条说一句通用的话

**判据的遍历范围本身就是判据的一部分。** 「跳过哪些段」看起来是遍历的实现细节，
实际是**判据的边界**——而边界写错时的表现是**静默通过**，不是报错。
故凡是「跳过 X」的写法，都要能回答：**如果 bug 就在 X 里呢？**

### 16.8 用真实构建验证（本节的规矩：改完必须跑一次真流水线）

```bash
# 看最近构建
cnb build get-build-logs --repo duoduobei/fundmate
# 看某个 stage 的真实报错（stageId 从构建详情里取）
cnb build get-build-stage --repo duoduobei/fundmate --sn <sn> \
    --pipelineId <pipelineId> --stageId stage-0
```

**为什么写进文档**：`get-build-stage` 的 `error` 字段是**唯一**能证明「这一条真的修好了」
的证据 —— 静态守卫只能证明「形状合规」。第一轮的教训就是只看了守卫。

### 16.10 第三轮：**「配到流水线环境变量」是错的 —— CNB 没有这个页面**（2026-10-14）

§16.6 那句修法（「`GITHUB_PAT` 因此改配在 CNB 仓库的**流水线环境变量**里」）**是错的**。
它是**文档驱动的臆测** —— 见 §16.6.1 的自我批评（「守卫绿 ≠ 线上绿」），这次错得更深一层：
**连文档都没读，直接编了一个平台不存在的功能**。

#### 事实：CNB 没有「仓库级流水线环境变量」这个设置页

翻遍 CNB《云原生构建》文档，环境变量只有四条路（《环境变量》一文的功能概览表即全部）：

| 功能 | 说明 |
|---|---|
| 声明环境变量 | `env` —— **写在 `.cnb.yml` 里**（Pipeline / Job 级） |
| 导入环境变量 | `imports` —— 从**密钥仓库文件**注入 |
| 导出环境变量 | `exports` —— 任务结果转环境变量 |
| 使用环境变量 | 脚本 / 配置里引用 |

Web 上唯一叫「环境变量」的页面是 **`个人设置 → 云原生开发 → 个人环境变量`**
（`docs.cnb.cool/zh/workspaces/personal-envs.md`），而它**明写**：

> 个人环境变量仅在`云原生开发`环境中生效，**不影响普通构建（`Build`）**。

⇒ 它救不了 `认领同步`。而「仓库设置」下**没有**环境变量页。
**所以 §16.6 让用户去点的那一步，用户根本点不到 —— 这正是用户回问「在哪里加？」的原因。**

#### 那正确的修法是什么

回到 §16.6 的核心事实（这条是**对的**）：

> - 非插件任务的 image 为空字符串，无法匹配任何 glob 表达式；
>   配置文件**声明了 `allow_images`** 将不能被非插件任务引用

**关键是这句话的宾语**：被拒的是「**文件里有 `allow_images`**」，**不是**「脚本任务引用密钥」。
§16.6 把它读成了后者，于是推出「脚本任务不能碰密钥仓库」这个**过宽的结论**。

CNB 官方文档《文件引用 › 权限检查 › 示例 › **流水线密钥文件引用**》给的正是反例：

```yaml
# 密钥仓库中的 secret.yml —— 只声明 allow_slugs / allow_events / allow_branches
allow_slugs: "p1/**"
allow_events: push
allow_branches: main
DOCKER_USER: docker-user
DOCKER_PWD: docker-pwd
```
```yaml
# .cnb.yml —— 普通**脚本任务**用 imports 引它，完全合法
main:
  push:
    - imports: .../secret.yml
      stages:
        - name: docker login
          script: |
            docker login -u ${DOCKER_USER} -p "${DOCKER_PWD}"
```

所以修法是：**另起一份不声明 `allow_images` 的密钥文件**，脚本任务 `imports` 引那一份。
`vars.yml` 保持不动（git-sync 是插件任务，它需要 `allow_images`）。

| | `vars.yml` | `claim-sync-env.yml`（新） |
|---|---|---|
| 读者 | git-sync **插件**任务 | `认领同步` **脚本**任务 |
| `allow_images` | **必须有**（否则插件读不到密钥） | **必须没有**（有则脚本任务必然死在 Prepare） |
| `allow_events` | 需要（`crontab:*` 等） | 不需要（`push` 是可信事件 + 非镜像任务） |
| `allow_branches` | 需要（`main`/`dev`/`feat/**`…） | **刻意不写**（`$` 段 = 所有分支） |
| `allow_slugs` | `duoduobei/fundmate` | 同左 |

「allow 必要性检查」流程图对**可信事件 + 非镜像任务**的判定是「**通过**」
（既不需要 `allow_events`，也不需要 `allow_images`），故这份文件只需 `allow_slugs`。
模板见 `docs/ops/claim-sync-secret-env.example.yml`。

#### 判据 4 也跟着收窄：**过宽与过窄一样是 bug**

初版判据 4 写成「脚本任务上不得挂密钥文件引用」，会把上面那条**官方示例的合法形态**
一并判红。**判据过宽的表现不是误报，而是让人放弃正确做法** —— 一样有害。

| 形态 | 判 |
|---|---|
| 脚本任务 + `imports` 引**带 `allow_images`** 的文件（`vars.yml`） | ❌ 死在 Prepare |
| 脚本任务 + `settingsFrom` 引密钥 | ❌ 「加载插件参数」语义，脚本任务没有插件参数 |
| 脚本任务 + `imports` 引**不带 `allow_images`** 的文件 | ✅ 合法（官方示例形态） |
| 插件任务（`image` + `settings`，无 `script`） | ✅ 由判据 1/2/3 管 |

守卫读不到密钥仓库（403），故按**文件名约定**判「是不是带 `allow_images` 的那份」：
形如 `vars.yml` / `*.vars.yml` 即认定（与 `docs/ops/git-sync-secret-vars.example.yml`
里确实写着 `allow_images` 互为印证）。

#### 顺带修掉判据 4 的第二个盲区：**遍历范围漏掉了真实形态**

收窄完判据 4，回退探针**第一次又 MISSED**：把脚本任务的 `imports` 改回 `vars.yml`，
守卫竟然报绿。查下去是 `_iter_plugin_stages()` 的老毛病 ——

```python
if isinstance(stage, dict) and 'image' in stage:   # ← 只收「stage 自带 image」的
```

而 `认领同步` 的 `image` 来自 **job 级 `docker.image`**（经 YAML 锚点 `&claim-job` 注入），
stage 自身**没有** `image` 键 ⇒ 它压根不在遍历结果里 ⇒ 判据 4 看不见它。

**这与 §16.7 那句是同一件事**：「判据的遍历范围本身就是判据的一部分」。
第一次栽在「跳过 `$` 段」，第二次栽在「只收自带 image 的 stage」——
**同一个错误换了张脸**。改法是判据只认「有没有 `script`/`commands`」
（「有没有 shell 命令」才是「是不是脚本任务」的判据，「image 从哪儿来」不是），
遍历则凡带 `script`/`commands`/`imports`/`settingsFrom`/`settings` 的 stage 全收。
**宁多扫，不要漏。**

#### 这一轮的四条回退探针（每条都先确认变异生效）

| 探针 | 期望 | 结果 |
|---|---|---|
| 脚本任务 `imports` 改回 `vars.yml` | 报错 | ✅ CAUGHT |
| 现状（`imports` 引 `claim-sync-env.yml`） | 不报错 | ✅ 绿（不误报） |
| 脚本任务改用 `settingsFrom` 引密钥 | 报错 | ✅ CAUGHT |
| git-sync 插件任务 `imports` 引 `vars.yml` | 不报错 | ✅ 绿 |

#### 一句更长的话

**「这个功能在哪个页面」这种问题，答错的方式只有一个：没查就说。**
§16.6 的错不是判据写错（那还能被探针咬住），是**说了一个平台没有的东西**——
它连「判据」都不是，探针咬不到，只能靠人去点一下才发现。
所以规则补一条：**凡涉及「在 UI 哪里操作」，必须能在官方文档里指到原文，
否则一律回答「我没查到，待确认」。**

### 16.9 关联

- 源：CNB #269（#167 排查顺带产出的构建 bug 卡）；
- 邻居：§13.1（凭据挂载位置的三形态）、§13.4（命名 stage 防假绿）；
- 同族：CNB #171 / §15（「拿不到输入」不得降级成正常结论）。
