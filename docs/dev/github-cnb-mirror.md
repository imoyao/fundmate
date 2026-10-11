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
| **不同步关闭态** | GitHub 关了，CNB 不自动关 | 「CNB 关了」会被误读成「这事不做了」，而关闭与否该由人拍板 |

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
> - 镜像于：2026-10-12（**以下字段均为建卡时快照，之后 GitHub 侧的变更不会回流**）
>
> ⚠️ **本卡是快照，不是实时视图。** 正文引用的文件 / 行号 / 字段 / 结论可能已随代码变化——
> 按它动手之前，先用 `git show <ref>:<file>` 确认该行仍在当前分支上。
> ⚠️ 卡面若与 GitHub 原卡不符，**以 GitHub 为准**；CNB 侧改动不会自动回流，
> 更正请写在 GitHub 原卡（或本卡评论区，见 `AGENTS.md`「失实信息修正纪律」）。
```

旧的「本卡为只读镜像」措辞**刻意删掉**了：它和「更正在评论区」自相矛盾（只读 = 不许写，
可我们又要人在这里留更正）。现在的措辞是「快照 + 以 GitHub 为准 + 更正写哪」三件事，
不再自相矛盾。

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
| 正文 | `body` | 溯源块（来源 / 编号 / 状态 / 里程碑 / 原标签 / 作者 / **镜像于**）+ `---` + 原文 |
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

cron 阶段末尾挂了一节**引用时效自检**（`check_mirror_refs.py`，`|| true` 只报告）：

```yaml
    - name: 引用时效自检（只报告）
      script: |
        python scripts/bridge/check_mirror_refs.py --report || true
```


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

## 8. 已知边界

- **不回写、不覆盖、不关**：见 §2。想改镜像卡内容，去改 GitHub 原卡，等下一轮同步——
  但注意**只增不覆盖**，存量卡不会更新，需要人工删卡后重跑。
- **只镜像 open issue**：GitHub 侧已关闭的卡不会补建。若某张卡在首次同步前就关了，
  CNB 侧看不到。
- **匿名 GitHub API 限额 60 次/时/IP**：107 张卡走 2 次分页调用，余量充足；仓库若长到
  数千 open issue，需配 `GITHUB_TOKEN`。
