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

注意 **crontab 事件必须挂在具体分支下**（不能放 `$` 兜底）——**但「必须是个具体分支」
不等于「必须是 `main`」**。2026-10-18 起本仓整组定时作业挂在 **`dev:`** 下（源 CNB #564）：
`dev` 是活跃分支，改脚本合入即生效；挂 `main` 会让每次修复都等一次发版，
历史上还因此逼出以 `main` 为 base 的提交（CNB #114 / #122 / #124 / #126），把两侧 `main` 岔开。
**只挂一份，不复制两份**（两份 = 每轮跑两遍、标签与评论重复）。
`web_trigger` 与分支无关，按平台建议放 `$` 下。
判据：`python scripts/guard_cron_covers_active_branch.py`（并入 `ci.yml` 的 `scripts_test`）。

**`$` 段还挂了第二段 `push:`**（CNB #172）：任何分支的 push 都跑一轮**幂等**建卡 +
状态回流。补的是「有人在功能分支上开了张 CNB 本地卡、却永远扫不到」这个缺口
（原作业只挂 `main` 的 cron，一天一次）。见 §14.3。

> ⚠️ **cron 挂在 `dev` 之后，上面那句「改动落在 `main` 才会被执行」已作废（2026-10-18，源 CNB #564）。**
> 那条判断当年是对的、也是那场事故的**症状**：`.cnb.yml` / `github_cnb_issues.py` 只存在于 CNB `main`，
> 而 `dev` 上有另一套 —— 两边互不包含，于是「整改代码在 `dev`、会被执行的代码在 `main`」。
> **处置根因而不是顺着症状走**：把 cron 搬到 `dev`，改镜像链路照常提 `dev`，合入即生效。
> 这与 `issue-milestone-guard.yml`「补挂里程碑后不自愈」同族：整改做完了就该跑它。

cron 阶段末尾挂了三节收尾任务（前两节只报告/幂等，第三节断链即建卡）：

```yaml
    - name: 状态回流（GitHub 已关闭 → CNB 标记）
      script: |
        python scripts/bridge/mirror_state_sync.py --apply || true
    - name: 引用时效自检（认评论区更正，只报告）
      script: |
        python scripts/bridge/check_mirror_refs.py --report || true
    - name: 分支分叉自检（断链即建卡）
      script: |
        git fetch origin dev main --quiet || true
        python scripts/bridge/check_branch_divergence.py --report --explain --out report-divergence.md
        if [ $? -ne 0 ]; then
          python scripts/bridge/notify_mirror_divergence.py --report report-divergence.md || true
        fi
```

前两节带 `|| true`：**建卡才是主任务**，这两节是信号，不该把建卡一起拖红。
（状态回流自身是幂等的，重复执行只发一次评论。）

第三节**刻意不在检查本身上吞退出码**：分叉是「镜像链路已经坏了」的事实，
只进日志等于静默停摆（crontab 红了没人盯，2026-10-11 白丢大半天）。
它的「大声失败」载体不是红灯而是**建卡**——退出码非零即建一张断链提醒卡
（幂等：已有未关闭同题卡只追加评论，见 §11.1）。stage 整体仍不拦构建：
建卡 job 才是主任务，分叉自检是挂在它尾部的信号。


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

`crontab` **只能挂在具体分支下**（平台限制，见 §6），本仓挂 `dev`（2026-10-18 起）。
**这正是本节要消灭的那类病**——在它搬过来之前，「整改代码在 `dev`、会被执行的代码在 `main`」
就是 #123 记的那个形态：

> **写完了，跑的不是它**——且没有任何信号提示这件事。

这与 `issue-milestone-guard.yml`「补挂里程碑后不自愈」同族。故加一件只读工具：

```bash
# 默认比较 origin/main ← origin/dev
python scripts/bridge/check_branch_divergence.py --report

# 只看「哪些作业只在单侧」
python scripts/bridge/check_branch_divergence.py --report --jobs-only

# 报告落盘（供 notify_mirror_divergence.py 拼断链卡面，见 §11.1）
python scripts/bridge/check_branch_divergence.py --report --explain --out report-divergence.md
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

`.cnb.yml` 里**不在检查本身上吞退出码**（`|| true` 只加在建卡调用上）——退出码是
建卡分支的唯一输入，吞了就又静默了（见 §11.1）；stage 整体仍不拦构建，**它是信号，不是门禁**。

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

### 11.1 断链提醒卡：`notify_mirror_divergence.py`（2026-10-14 补）

分叉自检挂在 **crontab** 上，而 crontab 的红灯没人盯。只把结论写进构建日志，
等于「报告了一切，没人会看」——2026-10-11 那次分叉白丢大半天，根因就在这。
故 `.cnb.yml` 里退出码非零时建一张 **CNB 侧的断链提醒卡**（幂等：已有未关闭
同题卡只追加评论，不重复建）：

```bash
python scripts/bridge/notify_mirror_divergence.py --report report-divergence.md
```

卡面四要素缺一不可（**现场 / 修法 / 禁令 / 溯源**）——缺任何一个，读到的人就无从照做：

- **现场**：落盘报告原文（两侧独有提交清单，照抄即可 cherry-pick）；
- **修法**：把 CNB 独有提交 cherry-pick 成 `rescue/` 分支，走 GitHub PR 合回；
- **禁令**：**不要 force push、不要删 CNB 侧独有提交**（会静默丢改动）；
- **溯源**：CNB #118 / #123。

设计取舍：

- **建卡失败不改退出码**（`|| true`）——「提醒失败」不该把真实原因盖掉；
- **标题就是幂等键**（`[镜像断链] …`）——改标题等于每次运行都建新卡，
  很快把卡列表刷成噪音，而噪音比没有提醒更糟；
- **重复断链只追加评论**，不复述「怎么修」——那是卡面的事，评论只给新现场；
- **零网络单测**：`scripts/tests/test_notify_mirror_divergence.py` 钉模板四要素、
  幂等键与截断行为。

#### 顺手修掉的静默失效：`--explain` 曾经不存在

`--explain` 的用法 2026-10-11 就写进了本文档，`.cnb.yml` 也早就传了这个参数——
但脚本当时**根本没有声明它**：argparse 报错、退出码 2，被 stage 的 shell 忽略，
分叉自检从未真正生效（「看着配了，实际空转」，与 #118 的假绿同族）。
本次把 `--explain` 落到实现（提交清单 + 离线合并试算），并加了一条**反向断言**钉住
「`.cnb.yml` 传了 ⇒ 脚本必须真的声明」：`test_cnb_yml_passes_explain_for_both_sides_lists`。

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

### 层 3：pull_request 反向守卫（2026-10-14 补，CNB #118 / #123）

§11 的自检是**事后**发现分叉；断链的**成因**是「在 CNB 侧合了 PR」。
故 `main:` 与 `dev:` 之下各挂一份 `pull_request` 守卫：PR 打向哪条长期分支，
就在哪条的配置里读到它——**本仓 CNB 侧只读，PR 请到 GitHub 开**，
直接 `exit 1`。

两个写法要点：

- **必须挂分支之下**。挂在顶层会被读成「一个名为 `pull_request` 的不存在分支」
  （#152 的平台语义），守卫空转还不报错；
- **只挂 `main` / `dev`**。feature 分支本就不该在 CNB 侧被合入；`$` 兜底只对
  `web_trigger` 有意义（`pull_request` 需要分支上下文）。

回归网：`scripts/tests/test_notify_mirror_divergence.py::test_cnb_yml_has_reverse_guard_on_pull_request`
（钉「两条长期分支都挂了」+「`exit 1` 在」——少 `exit 1` 就是喊了口号但放行）。

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
GitHub `main` 独有 27、**交集 0**；当年 `crontab` 挂在 `main` ⇒ **真正执行的是 `main` 上那份
配置**，而「整改代码」可能躺在 `dev` 上（病在 #118 / #123 已记过两次）。
**根因已于 2026-10-18 处置（源 CNB #564）：cron 搬到 `dev`**，改脚本合入即生效，
不再是「写完等发版」的窗口（判据 `scripts/guard_cron_covers_active_branch.py`）。

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

### 16.9 第三轮：**「配到流水线环境变量」是错的 —— CNB 没有这个页面**（2026-10-14）

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

### 16.10 第四轮：**「报错里说找不到」是过去时，不是现在时**（2026-10-14）

§16.9 之后，我拉了合并后的真实构建（`cnb-b7f-1k4su8ud9`，`10:10:37`，`push`），
看到 stage `认领同步` 报 `GetFileContent: not found`，于是写下：

> 报错 = 规则已经过了，只是**那个文件还没建**。你要做的一步：新建 `claim-sync-env.yml`。

用户回：**「我刚检查了一下，我们的文档里面已经有这个文件了呀。你居然说没有这个文件，为什么？」**
——截图里 `duoduobei/fundmate-secret` 的 `claim-sync-env.yml` **赫然在目**（用户 7 分钟前刚建）。

#### 我错在哪：把一条**历史**构建的报错，读成了**此刻**的事实

| 时刻 | 发生了什么 |
|---|---|
| `10:10:37` | 合并后的 push 构建跑 `认领同步` → `GetFileContent: not found`（**当时文件确实还没建**） |
| `~10:14` | 用户建好 `claim-sync-env.yml`（构建号 `329b8545`） |
| `10:18` | 我**引用那条 10:10 的报错**，写成「文件还没建」——而它已经建好 4 分钟了 |

**报错本身没骗人**。它是对**那一刻**的准确描述。骗人的是我的时态：
`GetFileContent: not found` 是一个**时间点的事实**，我把它当成了**持续状态**。

这与 §15 / CNB #171 是同一家族，但方向**相反**：

| | 症状 | 典型写法 |
|---|---|---|
| §15（#171） | 「拿不到」被降级成「没问题」（**假绿**） | `except: return []` 后打印「已对齐」 |
| **§16.10（本轮）** | 「那一刻拿不到」被升格成「现在还没有」（**假红**） | 拿 4 分钟前的 `not found` 断言「文件还没建」 |

两者的根都是**没区分「没拿到」和「不存在」**，只是这次错在把边界推向了「不存在」。

#### 一个更基本的错：我**本可以不说这句**

`fundmate-secret` 我**读不到**——本轮实测三种口径全是「读不到」：

```text
web    : https://cnb.cool/duoduobei/fundmate-secret/-/blob/main/claim-sync-env.yml → 404
api    : https://api.cnb.cool/duoduobei/fundmate-secret/-/git/files/...            → Resource not found
git    : git ls-remote https://cnb.cool/duoduobei/fundmate-secret.git              → Repository Not Found
```

**读不到 ⇒ 我没有资格断言「它此刻在不在」。** 正确的一句话是：

> 「报错说规则过了、卡在读那个文件；但**密钥仓库我读不到**，
> 所以**它此刻在不在是你那边的事实**，我不能替你判断 —— 请确认，或我拉最新构建看。」

而我把「读不到」偷换成了「不存在」。**这是 §15 那条诫命的镜像**：
那一条说「拿不全就别下结论」，这一条说「读不到就别下『还没有』的结论」。

#### 还需补的一条：**没有构建能证明它现在是绿的**

用户建好文件后，至今（`10:21`）**没有任何 `push` 构建跑过 `认领同步`**——
`10:15:49` 那两条是 `issue.comment@npc`（NPC 回复触发的镜像作业），不跑 `$` 段的推送管线。
所以「文件在了 ⇒ 认领同步绿了」**仍未验证**。

⇒ 结论的正确写法是「**差一次 push 构建**」，而不是「我看报错，文件还没建」。

#### 规则（补进「判据失败态」一族）

1. **引用构建报错时，必须带上构建号与时刻**（`cnb-b7f-1k4su8ud9` @ `10:10:37`），
   并问一句：**这条报错的观测时间，和我下结论的时间，差了多少？**
   期间有没有人改过那个被引用的东西？
2. **读不到的仓库，不得断言其内容**（在 / 不在 / 是什么）。改成「我读不到，待你确认」。
3. **「文件不在 ⇒ 报错」这类链式推断，要停在「报错说它读不到」这一步**——
   「读不到」的成因可能是「不在」「名字不对」「权限不对」「分支不对」，
   把它们**收敛成「不在」是猜**，而猜错的代价这次是去让用户做一件他已经做完的事。

命令备查：

```bash
cnb build get-build-logs --repo duoduobei/fundmate          # 找 sn 与 event（push / issue.comment@npc / crontab）
cnb build get-build-status --repo duoduobei/fundmate --sn <sn>   # 看 stage 名单，确认这条构建跑没跑目标作业
```

> **`event` 字段是关键**：`issue.comment@npc` 的构建**不跑** `$` 段的 push 作业，
> 拿它当「认领同步 还没绿」的证据是**张冠李戴**。

### 16.11 关联

- 源：CNB #269（#167 排查顺带产出的构建 bug 卡）；
- 邻居：§13.1（凭据挂载位置的三形态）、§13.4（命名 stage 防假绿）；
- 同族：CNB #171 / §15（「拿不到输入」不得降级成正常结论）。

## 17. 跨仓 `dev` 分叉：判据修的是形状，修不了「已经分叉」这个事实（源 CNB #269，2026-10-14）  <!-- cross-repo-ref-allow -->

> 用户 2026-10-14 在 CNB #269 的原话（第 N 次问同一件事）：
>
> > 1. 我们在 CNB 里面改的代码，要能够同步到 GitHub 上面；
> > 2. GitHub 上面更新的代码，也要能在 CNB 上面拉过来。
> > ……这个问题我们已经做了两天了，但一直在这转来转去。我不知道到底是不是没办法实现……
> > 现在导致的问题是，CNB 和 GitHub 里面的代码一直是独立的，那我们开发的意义是什么？

这一节回答的正是「为什么做了两天还在转圈」——**因为两天都在修形状，而堵点在别处。**

### 17.1 先把事实拉出来：两侧 `dev` 早已双向分叉

`git ls-remote` + `fetch` 两侧真实 ref（**不是看文档里写的配置**）：

```
CNB    dev = af8750e0     GitHub dev = eb9c9bba
最后成功同步点 = ccca7bbc，2026-10-11 13:34

git cherry <gh/dev>  <cnb/dev>  → 30 笔 `+`   （CNB 有、GitHub 拿不到）
git cherry <cnb/dev> <gh/dev>   → 89 笔 `+`   （GitHub 有、CNB 拿不到）
git merge-tree                  → 23 个文件冲突
```

**即：从 10-11 下午起三天里，两边各自往前跑，再没对上过。** 用户感觉到的
「CNB 里修好的 issue 同步不到 GitHub」，具体就是那 30 笔（认领同步 #179、  <!-- cross-repo-ref-allow -->
本地卡出口 #172、pull 收窄 #167、镜像自动关 #171、#268/#269 一批修复）。

### 17.2 真根因：两条各自正确的规则，合起来成死锁

`.cnb.yml` 的 push 任务**意图是对的**：

```yaml
branch: dev          # 只推 dev，不碰 main        ✅ 对（§13.3）
# push 模式不开 force：绝不肯把 GitHub 独有提交冲掉  ✅ 对（反向护栏）
```

但在「已经分叉」的既成事实下，这两条正确规则合起来的效果是：

1. 插件推「CNB 的 dev」；
2. GitHub 的 dev 上有 89 笔 CNB 没有的提交；
3. 非快进 ⇒ GitHub **拒收**（`non-fast-forward` / `Failed to push all branches`）；
4. 因为刻意不开 `force` ⇒ **永远不会成功，只会一直红**；
5. `crontab: 0` 的 pull 又只拉 GitHub 的 dev，**哪边都拉不动对方**。

⇒ **死锁**：两边都在前进 ⇒ 谁都合不上谁 ⇒ 谁都不动。

> ⚠️ **「配置对了」不等于「同步成功了」**。§13.1 ~ §13.5 修掉的那些坑
> （凭据挂载层级、命名 stage 假绿、事件挂分支下、`main` 收窄）**都是真坑、都修对了**，
> 但它们修的是**形状**。形状对了，**分叉这个事实还在**，于是照样推不上去。
> 两天一直绕圈，就是因为**一直在修水管，没人去清管里堵的那个东西**。

### 17.3 用户「保护 CNB dev」的思路对，但保护方式要换

用户的担心（原话）：

> 我们把 CNB 的 dev 保护起来，是为了防止从 GitHub 拉代码的时候，
> 把我们其他分支合到 dev 的代码直接冲掉。

**这个担心是对的**——§13.3 已实测 pull 分支会 `git push origin <b> --force` 写回。
但「拒绝同步」保护不了代码，只会让差异滚成 30 vs 89：

| 策略 | 效果 |
|---|---|
| ❌ 谁都别动（现状的隐含策略） | 各自膨胀，三天 30 vs 89，且**没有信号** |
| ✅ 先合一次，之后同步走「拉 + 合 + 推」，差异清零 | 每次同步后两侧一致 |

「保护」的正确形态是**合并**（把对方的改动合进来并解冲突），不是**隔绝**。

### 17.4 缺口在哪：仓内自检**问不出**跨仓分叉

`check_branch_divergence.py`（§11）比的是**同一个仓库内部**的 `main ← dev`。
它做得很好，但它回答不了「CNB dev 与 GitHub dev 是否分叉」——**因为另一半在另一个仓库**。
这就是三天零信号的原因：**判据的作用域，正好避开了出事的那一维。**

补上 `scripts/bridge/check_cross_repo_dev_divergence.py`：

- 判据与 §13.5 / §11 同源：**只用 `git cherry`（补丁等价）**，双向各跑一次；
  - 两侧都空 ⇒ 未分叉（放行正常落后）；
  - 只有一侧有 `+` ⇒ 单侧领先，**正常，不红**；
  - **两侧都有 `+`** ⇒ 真双向分叉 ⇒ **红**；
- **不用 `git diff`**（交叉合并下「一边落后」也非空 ⇒ 假红，§11 已实测）、
  **不用「独有提交数 > 0」**（落后一侧必然 > 0 ⇒ 假红，§11 已回滚过一版）；
- 「拿不到输入」（fetch 失败 / ref 缺失）⇒ 打印「结论不可信」并**退 2**，不得降级成 0
  （同 §15 / CNB #171 的假绿形态）。

**挂载位置（有意如此）**：

| 位置 | 挂不挂 | 为什么 |
|---|---|---|
| `.cnb.yml` 收尾自检 | ✅ 挂（只报告，退出码回显） | 那里有网络与 `GITHUB_PAT` 凭据 |
| `ci.yml` 的 per-PR 门禁 | ❌ **不挂** | 它是**联网**判据，PR 门禁不该依赖外网与 GitHub 凭据 |

回归网：`backend/tests/test_cross_repo_dev_divergence.py`（9 例，含 **2 个变异探针**
——`and`→`or`、删掉 `available` 检查，两者**实测都被咬住**）。
随 `backend` job 跑（`scripts/bridge/**` 已在 `paths-filter` 里，见 `ci.yml`）。

### 17.5 与 `main` 的关系：`main` 保持现状**不是 bug**

同一次实测：CNB `main` 领先 CNB `dev` 的只有 3 个发版 merge；GitHub `main` 领先
GitHub `dev` 只有 1 个合并。**都符合 §13.5 的口径**：

> `dev` 必须两侧一致；**`main` 允许不一致**（CNB `main` 由 CNB 发版 PR 推进，
> GitHub `main` 由 GitHub 发版 PR 推进，两者没有任何关系）。

⇒ 修的是 `dev` 的分叉，**不要**顺手去「同步 main」——那正是 §13.3 要防的事。

### 17.6 收敛路径（需人工定方向后执行）

> **2026-10-14 更新**：这一步已机械化为 `scripts/bridge/dev_converge.py`
> （`--dry-run` 演练 / `--apply` 执行，见 §18.6）。它建分支 + 合并 + 数冲突，
> **不**动 `dev`、**不**自动解冲突。下面保留手工版步骤作为对照。

1. 从当前 CNB `dev` 切 `rescue/dev-converge-<date>`；
2. 把 GitHub `dev` 合进来，**逐处解冲突**（`.cnb.yml` / `AGENTS.md` / `ci.yml` /
   本文件 / `docs/spec/*` 等，全是可解范围）；
   ⚠️ **冲突文件数以真实 merge 为准**：§17.1 的 `git merge-tree` 估算给出 23 个，
   而 `dev_converge.py --apply` 实跑 merge 得到 **25 个**（`git merge-tree` 不覆盖
   全部冲突形态）。**不要拿 23 去对账**——以脚本输出的清单为准。
3. 走 PR 合回 CNB `dev`（**不直接动 dev**）；
4. 合入后手动触发一次 push，把收敛后的 `dev` 推给 GitHub ⇒ **死锁解开**；
5. 此后由本节的跨仓自检盯着，再分叉当天就能看见。

> **必须先定方向再合**（以哪一侧为基线）。**继续放着不动不是中立选项**——
> 每天都会多欠 30 vs 89 那笔债。

## 18. 「CNB 新分支能不能自动向 GitHub 提 PR」——能力边界与三种方案的裁决（源 CNB #269，2026-10-14）  <!-- cross-repo-ref-allow -->

这一节回答用户 2026-10-14 在 CNB #269 提的一组具体问题。它们看起来是三个，
其实是**同一个误解**派生出来的三次试探：

> 1. 「CNB 这边是直接合到了 CNB 的 DEV，并没有向 GitHub 的 DEV 提 PR……
>    我感觉好像也**没办法实现**。」
> 2. 「CNB 收敛到 `dev`，`dev` 直接向 GitHub 同步到它的 `dev` —— 这样不就不会发生冲突吗？」
> 3. 「在 GitHub 建一个 `CNBDEV` 分支专门中转，同步过去之后，再去 GitHub 上让
>    CNB Dev 向 GitHub Dev 做同步。」

**先把事实钉住，再逐条判。**

### 18.1 事实一：CNB **能**调 GitHub API 写东西（「没办法实现」是错的）

用户的「好像没办法实现」来自一个**已经过时的判断**。`scripts/bridge/claim_detect.py`
的文件头曾经写着「CNB 构建 → 写 GitHub ❌」，那是**当时**（没接凭据通道时）的结论。
2026-10-14 已纠正（AGENTS.md「双端协作」节记了这次纠正）：

| 通道 | 通不通 | 依据 |
|---|---|---|
| 手工 `git push https://github.com/...` | ❌ | 构建 `env` 里只有 `CNB_*`，报 `could not read Username` |
| `api.github.com` 匿名写（POST） | ❌ | 返 401 |
| **插件任务 + Secret 仓库 `imports` 取 `GITHUB_PAT`** | ✅ | `claim_detect.py --apply` 正在用：挂标签、发评论 |
| **脚本任务 + Secret 仓库 `imports`（专用密钥文件）** | ✅ | `认领同步` 现走这条路（`a92cde0d`） |

**建一个 PR 只是 `POST /repos/{repo}/pulls`**，与上面「挂标签 / 发评论」是同一个
凭据通道、同一个 `github_api()` 封装。⇒ **技术上完全可行，本环境可复现。**
`claim_detect.py` 已经证明这条路在生产里跑着。

> ⚠️ 但**「能做」不等于「该做」** —— 见 18.3。用户搭这个前提是想论证
> 「不如直接推 `dev`」，而那个结论**恰好是对的**，只是理由不是「提不了 PR」。

### 18.2 事实二：真正的堵点不是「没建 PR」，是**已经分叉了**

用户方案 ② 的推理是：

> 「新分支合到 CNB `dev` → 触发 → CNB `dev` 推到 GitHub `dev`。」**这样就不会冲突了。**

**这句话在「两侧 `dev` 一致」的前提下成立，但前提当前不成立。** 实测
（2026-10-14，本仓 `git cherry` 补丁等价，双向各一次）：

```
CNB    dev = e879b975    GitHub dev = eb9c9bba
最后成功同步点 = ccca7bbc（2026-10-11 13:34）
CNB 独有（GitHub 拿不到）    → 31 笔（16,045 insertions，74 个文件）
GitHub 独有（CNB 拿不到）    → 89 笔
```

那 31 笔不是零碎修改，是**整套 bridge 工具**（`claim_detect.py`、`mirror_state_sync.py`、
`local_card_promote.py`）加 600 行 `test_claim_detect.py` —— GitHub 上**完全没有**。

⇒ **只要两侧 `dev` 还是 31 vs 89，`dev → dev` 的推送永远是非快进、永远被拒**
（push 刻意不开 `force`，那是对的反向护栏）。**「提不提 PR」改变不了这件事**：
PR 也是一种「把一个分支合进另一个分支」，而合的前提是能算出共同祖先 ——
两侧各有对方没有的改动时，合 **必然**要解冲突。

**用户想省掉的「冲突」，恰恰是省不掉的那部分。** 先合一次，是**唯一**的收敛路径。

### 18.3 三种方案的裁决

| 方案 | 做法 | 裁决 | 理由 |
|---|---|---|---|
| **① 直推 `dev`**（用户方案 ②） | 新分支 → CNB `dev` → 触发 → GitHub `dev` | ✅ **采纳**（就是现状，无需改） | `.cnb.yml` 的 `push:` 已收窄到 `branch: dev`（§13.3）；**缺的不是道路，是先合一次** |
| **② `CNBDEV` 中转分支**（用户方案 ③） | CNB → GitHub `CNBDEV` → GitHub PR → `dev` | ❌ **不做** | 多一跳、多一条长期分支（AGENTS.md 禁止新建长期分支），**且不解决 31 vs 89** —— 只是把同一场冲突挪到 `CNBDEV` 上出现 |
| **③ 自动提 PR**（用户的隐含期望） | 每个 CNB 新分支 → 自动开 PR 到 GitHub `dev` | ❌ **不做** | ①技术上能做（18.1），②但**本仓不需要**：CNB 的分支流程是「功能分支 → `dev`」，跨仓那一步由 `push: dev` 承担即可；自动开 PR 会让 GitHub 侧多出**没有对应 issue、没有 review 意图**的 PR 噪声 |

**一句话裁决**：**用户的方案 ① 正确，且已经是现状；方案 ②③ 是在给一个
「已经正确的道路」加多余的绕行，而真正的堵点（分叉）一个都没碰。**

### 18.4 那么「不建 PR、不中转」为什么反而是对的

因为**跨仓与仓内是两件事**，不该用同一套机制：

| 维度 | 仓内（CNB 内部 / GitHub 内部） | 跨仓（CNB ↔ GitHub） |
|---|---|---|
| 单位 | **功能分支 → `dev`** | **`dev` → `dev`**（整条线，不是单个改动） |
| 要 review 吗 | 要（PR 是评审场所） | **不要** —— 内容是同一批已 review 过的提交 |
| 谁审 | 人 + AI review | 无人（是**搬运**，不是**变更**） |
| 失败形态 | 冲突需人解 | 非快进 ⇒ 一直红（死锁） |

⇒ 跨仓同步的本质是**搬运**，不该再造一层 PR 流程去「审」一次已经审过的东西。
用户的方案 ②（`CNBDEV` + PR）恰恰是把搬运当成了变更，平白多一层人工 review —— 
而那一层**不会发现任何新问题**（内容逐字相同）。

### 18.5 正确路径（三步，与 §17.6 一致）

1. **先收敛**（唯一解冲突的那一次）：`python scripts/bridge/dev_converge.py --apply`
   建 `rescue/dev-converge-<date>`，把 GitHub `dev` 合进来 —— 实测**25 个文件冲突**
   （`.cnb.yml` / `AGENTS.md` / `ci.yml` / `docs/spec/*` / bridge 脚本等），**人工逐处解**；
   解完走 PR 合回 CNB `dev`（**不直接动 `dev`**）。
2. **推平**：合入后手动触发一次 git-sync push ⇒ 两侧 `dev` 内容一致，**死锁解开**。
3. **此后常态**：功能分支照旧合 CNB `dev`，`push: dev` 自动搬运；
   `check_cross_repo_dev_divergence.py` 每天盯着，**再分叉当天就能看见**。

> **方向必须先定**（以 CNB 还是 GitHub 为基线）——两步之间差在「谁的 merge 在上、
> 冲突以谁为准」，必须先与人确认。**放着不动不是中立选项**，每天多欠一笔。

### 18.6 新增工具：`scripts/bridge/dev_converge.py`

§17.6 的收敛路径原先只有**文字步骤**（「切分支 → 合 → 解冲突」），
于是「收敛」被读成一个需要手动敲七八条 git 命令的活，谁都不愿意开第一枪。
本脚本把**机械的那半**做掉：

```bash
# 演练（默认）：只报方向与分支名，不建分支、不改工作区
python scripts/bridge/dev_converge.py --dry-run

# 执行：建 rescue 分支 + 合入另一侧（冲突则停下并列出文件）
python scripts/bridge/dev_converge.py --apply
python scripts/bridge/dev_converge.py --apply --base github   # 反向
```

**它刻意不做三件事**（都是有意的边界）：

- ❌ **不直接动 `dev`** —— 建 rescue 分支，走 PR 合回（AGENTS.md 硬规则）；
- ❌ **不自动解冲突** —— 冲突面覆盖规范与流水线文件，一键解会**悄悄改掉治理规则**；
- ❌ **不 push、不开 PR** —— 收敛结果怎么用是人的决定。

退出码：0 = 分支就绪无冲突；1 = 有冲突（列出文件）；2 = 拿不到输入（**结论不可信**，
不得当作「没问题」——同 §15 / §17.4 的假绿口径）。

---

## 19. 收敛之后**又**分叉了：一次成功，不等于稳态（源 CNB #269，2026-10-14）  <!-- cross-repo-ref-allow -->

上一节（§18.5）说「合入后手动触发一次 push ⇒ 死锁解开」。**它确实解开了 ——
然后 30 分钟内又岔开一次。** 这一节记这次复发，以及它暴露出的两个真问题。

### 19.1 复现路径（每一步都已实测）

| 时刻 | 动作 | 两侧 `dev` |
|---|---|---|
| T0 | CNB PR #425 收敛完成，CNB `dev` 含全部 GitHub 独有提交 | 一致 |  <!-- cross-repo-ref-allow -->
| T1 | 发现 push 作业挂在 `main:` 键下 ⇒ 从未生效（§18 之外的另一个病） | — |
| T2 | CNB PR #448 把三条 git-sync 作业挪到 `dev:` 键下，并**再合一次** GitHub `dev` 的 `029afe05` | CNB `866e2043` / GH `ff73c5ad+` |  <!-- cross-repo-ref-allow -->
| T3 | **合并后第一次 push 构建仍红**：`! [rejected] dev -> dev (fetch first)` | CNB `866e2043` / GH **`d1b5780b`** |

**T3 的红不是 T1/T2 修的那个病。** T2 修的是「作业没跑」——已验：runner 日志里
出现了 `Checking if branch dev exists locally... Pushing specified branch: dev`，
**不再是** `Warning: branch dev does not exist locally, skipping push`。

T3 红的是**另一个病**：GitHub `dev` 在 T2 的快照之后又前进了 1 笔。

### 19.2 那 1 笔是什么

`git cherry` 双向量实测：

```
CNB    dev = 866e2043    GitHub dev = d1b5780b
GitHub 独有 → 1 笔：90d233b8「feat(ledger): 持仓行价格时点标注（#2140）」
CNB 独有   → 33 笔
```

它是 PR #2170 在 20:56 合入的**真实新提交**，两条独立佐证：

- ✅ `git grep priceDate origin/dev` 为空 ⇒ CNB 侧连该功能的痕迹都没有；
- ✅ `git patch-id` 扫 CNB `dev` 近 60 个提交，**无一等价补丁**（排除 hook 改写
  commit message 造成的 `cherry` 假阳性 —— 这是 AGENTS.md 提过的 `git cherry` 陷阱，
  这里已排除）。

⇒ push 刻意不开 `force`（反向护栏，**对**），非快进就必被拒。**这就是那次报错。**

### 19.3 教训一：**每次「收敛」都带一个有效期，而不是一个终态**

#425 / #448 都被叙述成「死锁解开了」。**准确的说法是**：

> 截至合并那一刻，CNB `dev` 包含 GitHub `dev`；**从 GitHub 下一次推进 `dev` 起，
> 这个包含关系就作废了**，直到 push 真正跑成功一次为止。

这中间是一个**敞口窗口**：`dev` 已前进、push 还没成功。窗口内 GitHub 只要再动一次
`dev`，收敛就作废。这不是运气差 —— GitHub 那个仓库**是活的**（人在上面合 PR），
窗口越宽，撞上的概率越高。

**故「收敛完成」的验收标准不是「merge 进去了」，而是「push 构建 success
且 GitHub 侧 ref 对上 SHA」。** 只有后者会让窗口关闭。

### 19.4 教训二：自检**咬住了**这次分叉 —— 它不是假绿

值得单独记一句：`check_cross_repo_dev_divergence.py`（§17.3）**上线后第一次真报红**，
而这次是真分叉（不是它自己的假阳性）：

```
$ python3 scripts/bridge/check_cross_repo_dev_divergence.py --report
- CNB   dev → 866e2043
- GitHub dev → d1b5780b
❌ 双向分叉：CNB 独有 33 笔 / GitHub 独有 1 笔
EXIT=1
```

它验证了两件事：

- **判据的方向是对的** —— 上一节担心的「`git cherry` 单向领先也报红」的假红**没有发生**；
- **它挂在收尾自检里是对的** —— 若它挂在 per-PR 门禁，这次分会话里就不会有人看见它。

⚠️ 但要注意它的**报告时机**：它跑在**构建收尾**，而构建是**被 push 触发**的。
⇒ 「分叉 → 下一次有人 push → 才报红」，**不是即时**。要更快只能靠 cron，
但 cron 也就是 hourly 量级 —— **这条链路本来就做不到「秒级感知对方仓库的推进」**，
别把一个「小时级信号」叙述成实时。

### 19.5 处置：再合一次（这一次实测零冲突）

本轮同款处置 —— 合 `gh/dev` 进功能分支，让它重新成为祖先：

```
$ git merge --no-ff refs/remotes/gh/dev
Merge made by the 'ort' strategy.   7 files changed, 127 insertions(+), 7 deletions(-)
$ git merge-base --is-ancestor gh/dev HEAD   ✅
GitHub 独有补丁（merge 后）  0 笔
```

**注意这次是零冲突**（#425 那次 25 个文件冲突）—— 因为 #425 已经解过一次，
这次的 1 笔（#2140）是纯新增文件区域，没有撞上治理文件。⇒ **冲突的成本主要在第一次**，
之后的复发只要及时处理，代价是小得多的。这正是「当天看见就便宜、拖三天就贵」的量化版本。

### 19.6 这段该记进 `AGENTS.md` 的一句话

> **跨仓同步的「收敛」是一次动作，不是一个状态。**
> 只要「GitHub 会推 `dev`」+「CNB push 不开 force」两条同时成立，
> 分叉就会**反复发生**，且每次都可能只差一笔。
> ⇒ ① 收敛的验收标准是「push 成功且 GitHub ref 对上」而非「merge 完成」；
> ② 自检要能长期跑（它已挂收尾），且**别把小时级信号说成实时**。

---

## 20. 镜像建卡重复了 224 张：「缓存被当成全集」，而三天零信号（源 CNB #450，2026-10-14）  <!-- cross-repo-ref-allow -->

用户报的很短：「issues 重复同步，把 github 上面的又同步了一遍」。

**他看到的比报的多得多**：不是「又同步了一遍」，是**同步了十遍**。实测（2026-10-14，
`check_duplicate_mirrors.py` 逐张读 365 张镜像卡正文）：

| 指标 | 实测值 |
|---|---|
| 受影响 GitHub 卡 | **140 张** |
| 重复卡总数 | 364 张 |
| **多出来的卡** | **224 张** |
| 单卡最多重复 | **11 张**（`GitHub #2096` → CNB 164/183/211/240/275/301/328/355/379/402/426） |
| 状态文件里的条目 | 107 条，**冻结在 2026-10-11**（首轮全量同步那批，CNB #5~#112） |

重复卡的建卡时间**相隔约一小时**（CNB #400 是 10:59、#423 是 11:22、#447 是 12:19），
即**每跑一轮建卡作业就再建一遍**。

### 20.1 根因：幂等键判重的依据，停在一份不全的缓存上

建卡作业的判重走 `harvest_existing()`。修复前它是这样写的：

```python
known = {int(k) for k in mirrored if str(k).isdigit()}
if known:          # ← 缓存非空就直接返回，CNB 侧一个字都不查
    return known
# 下面这段「扫 CNB、逐张抠幂等键」的代码，从第二次运行起就再也没执行过
```

这段读起来像**完全合理的缓存优化**（「状态文件里有映射就直接信它」），
所以它在 review 里毫不起眼 —— **它就是从那版漏过去的那一版**。

但状态文件是**一份缓存，而且是不全的缓存**：

- 它只在**建卡成功的那条路径**里被写入。历史上任何一次「卡建出来了、`save_state` 没落盘」
  （构建被中断 / 抛错 / Web 端手工建卡）都不会补记；
- CNB 侧人工创建或调整的卡同样不在里面；
- 于是「缓存里有 1 条 ⇒ 整个 CNB 侧已镜像完毕」这个推论**是错的**。

实测的失效边界：缓存停在 107 条（CNB #5~#112），而 CNB 侧已有 365 张镜像卡
⇒ **#112 之后的每一张，在判定时都"不存在"** ⇒ 每轮重建。

**一句话：建卡是「幂等键判重」的，判重依据却停在一份不会自更新的缓存上 —— 幂等就失效了。**

### 20.2 为什么三天里没有任何信号

这是本条最值得记的部分。已有三条自检作业，**没有一条在问这件事**：

| 作业 | 它问的问题 | 为什么问不出重复 |
|---|---|---|
| `mirror_state_sync.py` | GitHub 关了，CNB 还开着吗？ | 只管**状态**，不管**有没有两张卡** |
| `check_mirror_refs.py` | 正文引用的行号还在吗？ | 只管**正文内容时效** |
| `check_branch_divergence.py` | 分支分叉了吗？ | 只管**代码**，与 issue 无关 |

而每轮作业的日志是**全绿且漂亮的**：

```
✅ CNB #447 ← GitHub #2157 ...  <!-- cross-repo-ref-allow -->
🎉 完成：新建 10 张，跳过已存在 340 张
```

「新建 10 张」本身**看不出对错** —— 它只是把「这 10 张被判为没建过」复述了一遍。
判据错了，日志只会忠实地把错误的结论说得更响。

⇒ 与 #171（拿不到就报「已对齐」）、#179（限额耗尽就报「无新增」）**同一族**：
**不是缺功能，是缺一个能问出这件事的作业。**

### 20.3 修法

**① 根因**（`scripts/bridge/github_cnb_issues.py`）：缓存降级成**索引**，CNB 实况才是**判据**。

```python
cached = {int(k) for k in mirrored if str(k).isdigit()}
# …真扫 CNB 侧，逐张抠幂等键…
return cached | seen        # 并集；扫描结果回写缓存
```

刻意**取并集而不是取 CNB 实况**：读某张卡失败的条目会被保留 ——
「**宁可漏建，不可重复建**」（漏建下一轮补得上，重复建**不可逆**且污染看板）。

**② 守卫**（`scripts/bridge/harvest_scan_guard.py`，并入 `ci.yml` 的 `scripts_test` job，**阻断**）：
`harvest_existing()` 必须在函数体里真的调用 `list_cnb_issues()`，且**扫描之前不得有 `return`**。
不拟合具体写法（`if known:` / `if len(known) > 10:` 一视同仁），判据是「**有没有短路**」。

**③ 观测**（`scripts/bridge/check_duplicate_mirrors.py`，挂 `.cnb.yml` 收尾自检，**只报告**）：
同一幂等键 >1 张卡 ⇒ 退 1；**有卡读不到 ⇒ 退 2 且声明「结论不可信」**
（#171 纪律：拿不到输入不得退化成「无重复」）。存量重复卡的清理是**人的决定**，
脚本不猜（留哪张要看评论与标签）—— 它是「能问出这件事」的手段，不是清理工具。

### 20.4 回归网（含 3 个变异探针）

`scripts/tests/test_dup_mirror_guard.py`，16 条：

- **变异探针 1**：把 `git show origin/dev:` 上**修复前的真实代码**喂给守卫 ⇒ 必须报红。
  这是三条里最重要的一条 —— 不加它，「守卫绿」只能证明「代码里没有它不认识的东西」，
  **证明不了「它能认出那个 bug」**（AGENTS.md 里判据自己崩过两次的教训）。
- **变异探针 2**：`if len(known) > 10: return known` ⇒ 必须报红（不拟合写法）。
- **变异探针 3**：完全不扫描 ⇒ 必须报红。
- 行为契约：缓存不全时仍看得见 CNB 侧已有的卡；读不到时保留缓存条目；扫描结果回写缓存。
- 分类语义：无键卡单独记账；有重复 + 有读取失败时**优先报「不可信」**。

### 20.5 通用教训（该记进 `AGENTS.md` 的那些）

> **① 「缓存」与「判据」不是一回事。** 幂等/去重这类判重逻辑里，
> 缓存只能做**索引**（加速），不能做**边界**（决定「有没有」）。
> 写成 `if cache: return cache` 的那一行，就是把加速器当成了真相来源。
>
> **② 看到 `if <有缓存> : return` 先问一句：「缓存不全时会怎样？」**
> 它的失败形态是**静默**的 —— 判重失效 → 重复建卡 → 每轮都成功 → 全绿。
> 与 `if not data: return []`（#171）是同一族气味。
>
> **③ 「作业成功」证明不了「作业做对了」。** 「新建 10 张」在判据错时照样打印，
> 而且打印得更响亮。**要另有一条作业问「结果对不对」**，不能只问「跑没跑成」。
>
> **④ 修复根因只解决未来，存量必须被发现。** 改完 `harvest_existing`，
> 那 224 张重复卡**还在那儿**。口径变更/根因修复时都要单独答一句：
> 「按旧规则已经产生的数据，会被新规则重新处理一遍吗？」（AGENTS.md 已有同款，源 CNB #171）

---

## 21. `python:3.12-slim` 里没有 git：CNB 的 #461 只答了一半（源 CNB #517，2026-10-16）  <!-- cross-repo-ref-allow -->

### 21.1 现象：同一类错，深了一层

`cnb-bb7-1k522fu78` 的 `dev` push 构建红，`pipeline-002`「跨仓同步（机器分支 + PR 通道）」
的 stage「合并两侧 dev 并推成机器分支」原文：

```text
Traceback (most recent call last):
  File "/workspace/scripts/bridge/machine_branch.py", line 252, in <module>
    sys.exit(main())
  ...
  File "/workspace/scripts/bridge/machine_branch.py", line 246, in main
    code, url = _git(['remote', 'get-url', 'origin'], args.cwd)
  ...
FileNotFoundError: [Errno 2] No such file or directory: 'git'
```

**报错指向脚本第 246 行，但不指向「容器里没有 git」。** 这与 #461
（`sh: line 10: python: command not found`）是**同一类「执行环境缺失」**：
#461 补了 `docker.image: python:3.12-slim`，回答了「有没有 python」，
却**没人问「这个镜像里有没有 git」**——官方 `python:*-slim` 一律不带 git。

### 21.2 更坏的是：同一根因还有一处**假绿**

不只机器分支通道。镜像 job（`main` 的 `crontab: 0 18 * * *`）里的
「分支分叉自检」跑的是 `check_branch_divergence.py`，同样 `subprocess.run(['git', …])`。
实测构建 `cnb-3qr-1k522f3ls` 的 `stage-3`：

```text
python scripts/bridge/check_branch_divergence.py --report --explain || true
FileNotFoundError: [Errno 2] No such file or directory: 'git'
Finished, code: 0, duration: 0.4s        ← 0.4 秒，且报 success
```

**它自上线起每一轮都崩在缺 git，却因为 `|| true` + 末尾 `exit 0` 而报绿**
—— 分叉自检**从未真正跑过**。与 #171 / #450 同族：不是缺功能，
是缺一条能问出「这段代码跑得起来吗」的判据。

> ⚠️ 一处红、一处绿，根因同一个。**只修红的那个，绿的会永远绿着不干活。**

### 21.3 影响面（从源码推导，不手写名单）

`subprocess.run(['git', …])` / `_git(` 驱动的脚本：
`machine_branch.py` / `check_branch_divergence.py` /
`check_cross_repo_dev_divergence.py` / `dev_converge.py` / `check_issue_refs.py`。

在 `.cnb.yml` 里被调用的有 **3 处 stage**（全在 `python:3.12-slim` 上）：

| 分支 / 事件 | stage | 脚本 |
|---|---|---|
| `dev` / `push` | 合并两侧 dev 并推成机器分支 | `machine_branch.py`（+ 提示里的 `dev_converge.py`） |
| `main` / `crontab: 0 18 * * *` | 分支分叉自检 | `check_branch_divergence.py` |
| `$` / `web_trigger` | 分支分叉自检 | 同上 |

### 21.4 修法：脚本里自证 git 存在（不换镜像）

```sh
command -v git >/dev/null 2>&1 || {
  echo "· 容器无 git，安装中（python:3.12-slim 不含 git）"
  apt-get update -qq && apt-get install -y -qq --no-install-recommends git
}
git --version >/dev/null   # 自证：装失败即报错，不吞（#171）
```

为什么**不换镜像**：`python:3.12-slim` 与本仓其它脚本任务一致；换镜像会把
「python 在哪」这个刚被 #461 解决的不确定项重新打开。为什么**在脚本里装**而不是
新起一个 setup stage：CNB 各 stage 的执行环境不保证共享，跨 stage 推断一旦猜错，
就是另一个假绿。

「分支分叉自检」那处额外把装失败**显式报红**（`echo ❌ … 本轮没跑，结论不可信`），
否则它末尾的 `exit 0` 会把安装失败也一起吞掉。

### 21.5 判据机器化

- `scripts/guard_cnb_script_task_git.py`（并入 `ci.yml` 的 `scripts_test` job，阻断）：
  先扫 `scripts/**/*.py` **从源码推导**「哪些脚本真调 git」（不手写名单，手写的会随新脚本失效），
  再扫 `.cnb.yml`，凡调用这些脚本的 stage 必须在同一段 script 里供给 git。
- 回归网 `scripts/tests/test_cnb_script_task_git.py`（8 例），含唯一一条**推导假设**的钉桩
  （`git_driven_scripts()` 必须认出 `machine_branch.py`——它失效则整张网恒绿）、
  重复键遮蔽探针（源 #463），以及拿**修复前的真实 `.cnb.yml`**（不可变 SHA `7b833c4c`）喂守卫
  必须转红。
- 变异探针实测：删掉 `.cnb.yml` 里的 git 供给 ⇒ 探针转红；还原 ⇒ 退 0。

### 21.6 通用教训

> **「环境齐不齐」要一层一层问，问到脚本真正用过的东西为止。**
> #461 问「有没有 python」，本卡问「有没有 git」——**同一个 job、同一次事故、
> 报错形态不同，而两次都以为修完了**。判断某个环境缺件时，
> 先 `grep subprocess` 把脚本**实际调用的外部命令**列出来，逐条问一句「镜像里有吗」。
>
> **一处红的、一处绿的，往往同一个根因。** 绿的更贵：它不会催人去查，
> 只会让人以为「这条自检一直在跑」。（与 §20 的「作业成功证明不了作业做对了」同族。）

---

## 22. 机器分支通道的两处「同一事实问两次」（源 CNB #573，2026-10-18）

构建 `cnb-um5-1k57nplko`（`dev` push）两条 pipeline 都红。表面上是两件事，
实际是**同一类错**：把一次 git 询问问了两遍，然后拿第二遍的结果当结论。

### 22.1 pipeline-001：git-sync 直推 `dev` 被拒（预期内，且已知）

```text
! [rejected]  dev -> dev (fetch first)
Error: Failed to push branch dev
```

这就是 §17.2 的死锁：两侧 `dev` 互有对方没有的提交，push 刻意不开 `force`（反向护栏，**对的**）。
实测（2026-10-18 22:59）：

```
CNB    dev = 2251a39f    GitHub dev = 3504cb8f
共同祖先     = 244a7992
GitHub 独有  → 4 笔（`#2323` / `#2343` / `#2348` 两条 + 一次 ruff format）
CNB 独有     → 4 笔（#561 / #564 / #566 / #567）
```

⇒ 收敛动作仍是 §17.6 / §18.6 那条（`dev_converge.py` + 人工解冲突），**不是配置问题**。

### 22.2 pipeline-002：机器分支通道「合好了，但一个字节都没推出去」

```text
❌ 推机器分支失败：                                ← #567 修过之后才有内容
 ! [rejected]  HEAD -> bridge/github-dev (fetch first)
...
✅ 无冲突，两侧内容可合。
（演练模式：未推、未开 PR。加 --apply 执行。）      ← 这三行是矛盾的
```

三处自相矛盾，各自都是一个真 bug：

| 现象 | 根因 |
|---|---|
| `--apply --push` 跑完却打印「**演练模式**」 | `build_report(pushed=False)` 只有两个状态（推了 / 没推），而「推失败」挤进了「没推」的兜底句 |
| 冲突清单**永远是空的** | 演练路径把 `merge-tree` **问了两遍**：`code, _, _ = …` 取码、`if code == 1:` 再跑一遍取输出 |
| 机器分支推不上去、每小时红一次 | `bridge/github-dev` 是**固定名一次性 ref**，上一轮没被合掉 → 本轮合并结果不含它 → 非快进 |

**「永远空」这件事当时没有信号**：报告打印的是「✅ 无冲突」，读起来是个**结论**，
而且比任何警告都更像结论。这正是「判据错的时候，报告会更响亮地复述错结论」。

### 22.3 处置

1. **一次调用同时拿码与输出**（`merge_tree_conflicts()`）：`git merge-tree` 的退出码与
   冲突清单来自**同一个进程**；「取不出路径」按**不可信**（退 2）处理，
   **不得**退化成「无冲突」。判据：`scripts/guard_ask_git_once.py`（并入 `ci.yml`，
   按**参数形状**比对 —— 只认字面量的第一版在真实代码上恒绿，实测自咬）。
2. **报告把「没推」拆成三种原因**：真演练 / **合好了但推失败** / 试算或合并没跑成。
   三种下一步完全不同，合并叙述等于把诊断方向掉包（#171 同族）。
3. **机器分支按「覆盖自己那条一次性 ref」推**：`--force-with-lease=<ref>:<sha>`。
   - 为什么不冲突于「push 绝不开 force」：`dev` / `main` 是**共享事实**，冲掉别人的提交不可接受；
     机器分支是**本次合并结果的快照**，名字固定即为了幂等地覆盖。判据双向钉在
     `scripts/tests/test_machine_branch.py`（`test_script_never_force_pushes` +
     `test_force_only_allowed_on_machine_branch`）。
   - 为什么 lease 要**显式带期望值**：裸 `--force-with-lease` 依赖「本地有该 ref 的
     remote-tracking 信息」，而我们从不 fetch 这条分支（只抓 `refs/cross-bridge/*`），
     于是它退化成 `(stale info)` —— 实测复现（临时裸仓 + 已存在的目标分支）：
     裸 lease = `stale info` 被拒；`=<ref>:<sha>` = 正常覆盖。

### 22.4 验证（真实仓库，离线）

```
# 冲突判据：造一对真冲突的 ref，修复前报「无冲突」、修复后报 1 个文件
conflicts → (['f.txt'], '')
exit → 1  ⚠️ 有 1 个文件冲突 —— 什么都没推

# 守卫：拿 origin/dev 上修复前的真实代码喂它
$ python scripts/guard_ask_git_once.py --file /tmp/old_mb.py
❌ machine_branch.py:199: 函数 `run` 里同一个 git 询问出现了两次，且第二遍丢掉了退出码（第一遍在 196 行）
rc=1
```

`test_machine_branch.py` 现有 22 条（原 16 条 + 新增 6 条），**6 个变异探针全部咬住**
且各自咬在**对应用例**上：冲突清单恒空 / 普通 push（去掉 lease）/ push_failed 复用「演练模式」/
试算问两次 / 推失败不打 remote 原话 / 「不可信」退化成「无冲突」。

## 23. `bridge/github-dev` 有两个写者，而它们互相砸（源 CNB #574，2026-10-19）  <!-- cross-repo-ref-allow -->

用户拿来的是一张构建日志：`cnb-um5-1k57nplko` 两条 pipeline 都红。

| pipeline | stage | 原文 |
|---|---|---|
| `-001` 同步到 GitHub（仅 dev + 标签） | git-sync | `! [rejected] dev -> dev (fetch first)` |
| `-002` 跨仓同步（机器分支 + PR 通道） | 合并两侧 dev 并推成机器分支 | `❌ 推机器分支失败：… ! [rejected] HEAD -> bridge/github-dev (fetch first)` |

两条都是**非快进被拒**，而两条的成因是同一件事：**同一份内容有两个写者，且它们互相不认识。**

### 23.1 实测（不是推断）

```
CNB   dev 2251a39f    GitHub dev 3504cb8f
bridge/github-dev 在 CNB 上 40230822 / 在 GitHub 上 5d24035f  ← 同一条分支、两份内容
GitHub bridge ref 的父提交：0239301f（CNB #569，机制说明）→ 5d24035f 就是「CNB 为基线合 GitHub」的产物  <!-- cross-repo-ref-allow -->
```

`bridge/github-dev` 的两个写者：

| 写者 | 触发 | 写法 | 开 PR 吗 |
|---|---|---|---|
| GitHub `.github/workflows/dev-reconcile.yml` | 每日 `cron: 37 18 * * *` | `push --force-with-lease`，`git merge -X ours cnb/dev` | **开**（并挂 `automerge`） |
| CNB `.cnb.yml` 的「跨仓同步」stage | 每次推 `dev` | 每轮**换一个 base** 重新合，普通 `push`（非 force） | 不开 |

所以每一轮 CNB `dev` push 都在做两件必然徒劳的事：① 归一化 base 变了 ⇒ 结果不是那条 ref 的
快进 ⇒ 被拒（**构建天天红**）；② 即便侥幸快进成功，也会**改写 reconcile 刚铺好的合并结果**
（口味从 `-X ours` 变成默认策略），而**它开的那张 PR 还开着** ⇒ PR 内容与分支内容不符 ——
这一种**外观一切正常**，比红灯危险。

### 23.2 为什么不是「两个写者协商」，而是「收归一个」

`--force-with-lease` 是**原子检验**，不是可协商的锁。任何「先比远端 SHA、再决定推不推」都是
检查-使用之间的竞态（对方在你比对与推送之间推进即可作废）。故写者身份必须是**配置**，
不是**时序**——`machine_branch.py` 里也写了这句注释，防下一个人再想「能快进就推」。

**写权归 GitHub reconcile**（它是完整的一条通道：冲突取 GitHub、门禁照跑、合完即亡），
CNB 侧保留**读**的价值：「两侧 dev 能不能无冲突合并」这个结论必须每轮都算，但它**不需要写任何东西**。

于是一个自然的错答案被排除了：CNB 侧光「不推」还不够 —— 而**改推 `dev`** 更错
（`dev` 有分支保护，`质量门禁汇总` 只在 PR 上产生，直推需要一个根本不存在的检查 ——
见 `scripts/bridge/machine_branch.py` 文件头那张「两道闸」表）。

### 23.3 修法

- `machine_branch.py`：新增 `writer()`（环境变量 `MACHINE_BRANCH_WRITER`，默认 `github`）。
  非写者身份下**合并照跑、结论照报，但一次 `git push` 都不发**，报告里明写
  「只读探针 / 未推送」，退出码 0 的语义收窄成「无冲突（观测）」。
- `.cnb.yml`：`--push` 保留（写者身份下仍要能推），但**不再要求 `GITHUB_PAT`** ——
  原来的 `exit 1` 把「我们本来就不该写」误报成「凭据缺失」，**红灯指向了错的方向**。
  现改为：有 PAT 用鉴权 URL，没有就匿名读 GitHub 的公开 `dev`。
- 顺带修掉一处：`run()` 的「无冲突」路径此前把报告**打了两遍**（日志里像跑了两轮）。

### 23.4 判据机器化：`scripts/guard_bridge_machine_branch_single_writer.py`

三条静态判据（不拉网络），并入 `ci.yml` 的 `layout_guard` job（**不新增 job**，不动 `gate.needs`）：

1. `.cnb.yml` 里不得设 `MACHINE_BRANCH_WRITER=cnb`（那是「第二个写者」）；
2. `DEFAULT_WRITER` 必须是 `github` —— **默认值翻转不改任何 `.cnb.yml`**，配置看起来完全正常，
   只在运行时把写权搬走，是本判据唯一防不住的场景，故必须单独钉；
3. `dev-reconcile.yml` 必须**仍在推** `bridge/github-dev` —— 被降级的一侧若无对侧接手，
   就变成「没人写、两边都绿」，与 §20 同族的假绿。

回归网 `scripts/tests/test_bridge_single_writer.py`（8 条），3 个变异探针均已实测转红
（删只读闸门 / 默认写者翻转 / `.cnb.yml` 设写者）。登记在 `guard_rule_registry.py`。

### 23.5 这次该记进 AGENTS.md 的两句话

> **「不该做的事」也要有判据，不能只写「我们不做」。** 本例里 CNB **不该**写那条分支，
> 但代码里它一直在写 —— 因为没人问过「这条分支归谁」，写的动作就一直留着。
>
> **一条分支两个写者，症状永远长在「被拒」上，成因永远藏在「另一边也在写」。**
> 看到 `! [rejected] … (fetch first)` 先问：**另一侧是不是也在往这里推？**

---

## 24. §22 / §23 是同一件事的两半：**先问「谁在写」，再问「写成功了吗」**

两节的入手点不同，今天合流了：#22 从「同一事实问两次」进来（pipeline-002 的
`bridge/github-dev` 被拒），#23 从「两个写者」进来，**同一个构建、同一条分支**。合起来的顺序是：

1. **先问归属**（§23）：这条 ref 归谁写？只有一个写者吗？——归属错了，后面每轮都会红，
   而且红得很有规律，容易被当成「环境抖动」。
2. **再问事实**（§22）：写的时候有没有把一次询问问两遍？「没跑成」有没有被读成「没问题」？

顺序反了会怎样：先修「怎么推」（#573 的 `--force-with-lease`）而不先定「谁该推」，
就是给一个**不该写的写者**配了一把更好的钥匙——它会把另一侧铺好的合并结果覆盖掉，
而那一侧开的 PR 还开着（§23.1 的第 ② 条，**外观完全正常**，比红灯危险）。

### 24.1 合流后的实际状态（2026-10-19）

| 层 | 现在的行为 | 判据 |
|---|---|---|
| 写者身份 | CNB 默认**只读探针**；`MACHINE_BRANCH_WRITER=cnb` 才接手（须同时停掉 reconcile 推送） | `guard_bridge_machine_branch_single_writer.py` |
| 试算 | `merge_tree_conflicts()` 一次调用同时拿码与输出；取不出路径 ⇒ 不可信（退 2） | `guard_ask_git_once.py` |
| 推送（写者身份下） | 只对机器分支用 `--force-with-lease=<ref>:<sha>`；`dev` / `main` 永不开 force | `test_machine_branch.py::test_force_only_allowed_on_machine_branch` |
| 报告 | 「没推」拆成 演练 / 只读探针 / 推失败 / 不可信 四种，**不许共用一句** | `test_report_distinguishes_three_reasons_of_not_pushed` |

### 24.2 通用教训

> **同一份内容有两个写者时，症状永远长在「被拒」上，而成因藏在「另一边也在写」。**
> 先定归属，再谈手法。给不该写的写者配更强的推送手段，是把一个红问题变成两个绿着的坏问题。

> **报告的状态数 = 事实的状态数。** 少一个状态，就有一类情况会滚进相邻的句子里，
> 而它滚进的那一边决定了人往哪查方向。（与 §22.5 / §20 同族。）

---

### 22.5 通用教训

> **「先探测、再执行、再读第二次结果」的结构，都要问一句「两次之间变了会怎样」。**
> 能一次调用同时拿码与输出，就别分两次问 —— 所谓「同一个答案的两半」，
> 在进程边界上从来不是同一个答案。

> **「没做」和「做了但失败」不许共用一个句子。** 报告只有两个状态时，第三种情况
> 就会随机落进其中一边；而它落进的那一边，决定了人往哪个方向查。

---

## 25. 每小时红、红在同一行：定时作业挂在 `main` 下却推 `dev`（源 CNB #578，2026-10-18）  <!-- cross-repo-ref-allow -->

用户拿来的是构建 `cnb-ri6-1k57q4k9b`（`crontab: 30 * * * *`）的一条 error。

### 25.1 日志里到底发生了什么

```
[00:00:02] $ git fetch -v --force … origin "refs/heads/dev"
[00:00:02] $ git checkout -f -B "dev" "a9d050b2…"
[00:00:12] To https://github.com/imoyao/fundmate.git
[00:00:12]  ! [rejected]        dev -> dev (fetch first)
[00:00:12] Error: Failed to push branch dev
```

⚠️ **注意第一行拉的是 `refs/heads/dev`，不是 `main`** —— 这条构建的检出里**有** `dev`，
所以本卡**不是** #269 那个「挂错分支 ⇒ 静默跳过」的形态。它是一次**真的尝试**，只是注定失败：

| 事实 | 实测值（2026-10-18） |
|---|---|
| 两侧 `dev` 是否一致 | **不一致**，双向分叉 |
| CNB 独有 | 19 笔 |
| GitHub 独有 | 7 笔 |
| 两侧能不能无冲突合并 | **能**（`git merge-tree` rc=0） |

`git-sync` 的 push 刻意不开 `force`（这是**反向护栏**，对的）。于是只要 GitHub `dev` 多一笔，
这条 cron 就永远推不上去 —— 它每小时红一次、每次都红在同一行，而它**一个字节都没送出去过**。

### 25.2 三个各自成立、合起来却成了死循环的设定

| # | 设定 | 单独看 | 合起来 |
|---|---|---|---|
| ① | CNB `dev` 有 GitHub 没有的提交 | 正常（CNB 侧在干活） | 需要一次合并才能推 |
| ② | git-sync push 不开 force | 正确（不覆盖别人的提交） | 非快进 ⇒ 被拒 |
| ③ | 合并由 GitHub reconcile 做，再由 `push` 带过来 | 合理（单一写者，§23） | 合并 PR 要等 CI；CI 要在 GitHub 上跑 |

⇒ **桥的两端各自都对，唯独没有人负责「先把 CNB 的提交送到 GitHub 去触发那个合并」。**
#578 的这条红就是这个缺口的**唯一可见信号**，而它长得像「配置又坏了」。

### 25.3 处置：判据范围内的已经修，范围外的不假装修

| 面 | 动作 | 判据 |
|---|---|---|
| **挂载位置** | cron 块移入 `dev:` 段 —— 与 #269 同一条纪律，**这次轮到它自己** | `scripts/guard_cron_job_reachability.py`（阻断） |
| **内容分叉** | **不在本卡修**：CNB 侧不开 force，等 GitHub reconcile 合完带过来 | `check_cross_repo_dev_divergence.py --report`（观测，退 1 = 真分叉） |
| **颜色语义** | 这条 cron 的**红只说明「这一轮没推上去」**；它**绿也不**说明两侧已对齐 | 同上 —— 别拿 CI 颜色代替分叉判据 |

> ⚠️ 移入 `dev:` 之后它**仍可能红**（只要两侧还分叉）。那不是回归，是**同一个真问题的
> 正确呈现**：位置对了，剩下的就是内容。**不要**为了让构建变绿而去加 `force`——
> 那是把护栏拆了换绿灯，与 §23 里「给不该写的写者配更好的钥匙」同族。

### 25.4 通用教训

> **「挂在哪」和「推哪条」是一件事的两面。** runner 的检出只包含分支键那一条
> （`git fetch refs/heads/<键>` + `git checkout -B <键>`），所以两者不一致时，
> 作业要么静默跳过（假绿），要么拿一条注定推不上去的 ref 去推（恒红）。
> 两个方向都栽过：假绿那次在 #269，恒红这次在本卡。

> **同一个作业，修好一个毛病之后，症状会换成它真正的毛病。**
> #269 看到的是 `success` + `skipping push`；#578 看到的是 `error` + `rejected`。
> 前者是「位置写错」，后者是「位置对了、内容没合」——
> **别把「症状换了」读成「修回退了」**，先看它换到了哪一件事上。

> **判据要回答的是「这段配置有没有可能是对的」，不是「这次跑成没跑成」。**
> 位置类判据（静态、离线、可阻断）与收敛类判据（联网、只报告、退 1）必须分开：
> 前者不拉网络所以能当闸，后者拉网络所以只能当信号。混在一起的结果通常是
> 「闸不好用、信号没人看」。

### 25.x 后续：这条 cron 已删，位置类判据却留下两条（2026-10-18）

#577 把「直推 `dev`」这种**通行方式**整条删掉了（它结构上必红），#564 则把整组定时作业
从 `main:` **搬进** `dev:`。两件事不互相替代，故两条位置判据都在：

| 判据 | 问的是 | 挂在哪 |
|---|---|---|
| `guard_cron_job_reachability.py` | 挂对分支了，作业的目标分支在不在**它自己的检出**里 | `ci.yml` / `scripts_test` |
| `guard_cron_covers_active_branch.py` | 挂对分支了吗（cron 只许在 `dev`，不许复制到 `main`） | `ci.yml` / `scripts_test` |

第二条带**回退探针**：拿修复前 `dev` 上真实的 `.cnb.yml`（cron 还在 `main:` 下）喂给判据，
确认它真的转红 —— 「守门绿」只能证明「代码里没有它不认识的东西」，证明不了它能认出那个 bug。
