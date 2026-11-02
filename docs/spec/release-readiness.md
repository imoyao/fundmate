# 发版 readiness 判据（dev → main）

> 状态：2026-10-08 首版落地；2026-11-02 修正 DDL 判据与待发 PR 计数口径（见 §1.2 / §6）。
> 配套脚本 `scripts/release_readiness.py`，回归用例 `scripts/tests/release_readiness.test.js`（33 条）。
> 本文件是**语义闸**的唯一判据来源。脚本是机械闸，两者都要过。

---

## 0. 判定对象：dev 的 HEAD 快照

发版 PR 是 `dev → main` 的**整体快照**，不是「清一堆 PR」。因此：

- **不判定「一个个 PR 是否中间态」**——要判定的是「dev 此刻这个整体能否落到生产」。
- **不存在「剔除某个中间态 feature」**——快照不能挑着合。发现中间态只能二选一：补完再发，或本次不发。
- **不存在「按依赖拓扑排序」**——排序只在你手动逐个把功能 PR 合进 dev 时才有意义。

---

## 1. 机械闸（脚本自动判，无需人）

跑 `python scripts/release_readiness.py`，退出码 1 = BLOCK。

| 检查项 | 级别 | 判据 |
|--------|------|------|
| main/dev 分叉 | **BLOCK** | `origin/main` 领先 `origin/dev` 任一提交即拦。必须是「dev 领先、main 无独有」 |
| dev 门禁状态 | warn | 最近已合 PR 的 `质量门禁汇总` 结论。非 SUCCESS 需说明 |
| 批次规模 | warn | >120 提交或 >10 天。diff 无法在正文穷举，review 覆盖度下降 |
| DDL / 迁移 | warn | 改动命中迁移实现 / 表结构定义 / SQL 脚本（见 §1.2）。DDL 不可逆 |
| 待合并发版 PR | warn | 已存在未合并的 dev → main PR ⇒ 本次不重复开 |
| 中间态信号 | warn | PR 标题含 `WIP` / `中间态` / `分步` / `未完成` / `半成品`；**只扫最近一页**（见 §6） |
| 单 PR 规模 | warn | >40 文件或 >+1500 行 |
| DDL 覆盖范围 | warn | compare API 文件数被截断（≥300）时声明覆盖范围 |
| 待发 PR 覆盖范围 | warn | 一页未取全时，待发 PR 数只能给下限（见 §6） |

### 1.2 DDL 判据认哪些路径（2026-11-02 修正）

首版只认 `alembic` / `migrations/` / `schema.sql` / `init_db` / `*.sql`，而**本仓没有 alembic**：
迁移函数写在 `backend/app/core/migrations.py`，`init_db()` 在 `backend/app/core/database.py` 里——
`init_db` 是**函数名**，路径里根本不会出现。结果是这条闸在本仓**结构上不可能亮红**：
v0.3.0 发版实测有 1320 行迁移改动 + 5 张新表，脚本却判「未命中迁移或建表脚本」。

现在按真实布局认三类：

| 类别 | 路径形态 |
|---|---|
| 迁移实现 | `alembic/`、`migrations/`、`backend/app/core/migrations.py`、`backend/app/core/database.py`、`init_db` |
| 表结构定义 | `*/models.py`、`*/models/*.py`（一文件一张表） |
| SQL / Supabase DDL | `*.sql`、`schema.sql`、`supabase/` |

**截断时不得判「通过」**：compare API 只回前 300 个文件，拿不到完整列表就等于「不知道有没有 DDL」，
此时 `DDL / 迁移` 一律 warn，并指向本地复核命令。把「未知」渲染成「通过」是本仓反复踩过的假绿灯形态。

### 1.1 分叉的成因与修法

**成因**：历史发版 PR（#1524 / #1645 / #1765）用 merge commit 合入 main，发版后**没把 main 回合并到 dev**，导致 main 长期留有 dev 不存在的 merge commit 节点。

**修法**：merge，不是 force push。

```bash
BASE=$(git rev-parse origin/dev)
MT=$(git rev-parse origin/main)
TREE=$(git merge-tree --write-tree $BASE $MT)   # 输出纯 tree hash 即零冲突
MC=$(git commit-tree $TREE -p $BASE -p $MT -m "merge: 补齐发版 merge commit 历史节点")
```

**必做的两项断言**（缺一不可）：

```bash
git diff origin/dev $MC                                    # 必须为空 —— 证明零内容变化
git merge-base --is-ancestor origin/main $MC               # 必须为真 —— 证明分叉消除
```

`commit-tree` 不触碰工作区，是本仓最安全的 git 操作形态（避免 `checkout` / `worktree add` 在此环境写大量文件超时）。

**不要用** `git push --force origin dev:main`——不可逆，且丢 commit。

---

## 2. 语义闸（必须回 `origin/dev` 实证，脚本判不了）

### 2.1 铁律

**不采信 issue 评论和 PR 正文里的自述进度。** 一律回 `origin/dev` grep / 读源码验证。

反面教材（本仓已发生）：

- #1926 正文写「验收口径（先占位，动手前再细化）」——占位的验收口径等于没有口径。
- #1978 正文写「物化一旦分叉就是 #1812 那种隐蔽复刻」——作者自己都标了这是高风险改造。
- `issue_health_scan` 的 B 类（「关联 PR 全部合入、无开放 PR」）**不是**「可关」：反例 #1460（P2 待拍板 / P3 未动 / 定时链 15 连红）、#1121、#980。

### 2.2 中间态识别判据

任一条成立 ⇒ 该 feature 视为中间态，**本次不发**：

| # | 判据 | 怎么查 |
|---|------|--------|
| 1 | **新增表/字段无读路径消费** | grep 新表名，命中只在 models.py / schema 定义，读路径零命中 |
| 2 | **flag 无默认值或默认关闭** | grep flag 定义与 `default=`；默认关闭的功能等于没做 |
| 3 | **正文写「占位」「后续」「先…再说」且代码无对应实现** | 交叉读正文与 diff |
| 4 | **改动有新增测试但无反向验证** | revert 旧代码，测试须转红；不复红 = 测试没在测东西 |
| 5 | **依赖后续 PR 才能跑通** | 检查是否 import / 调用了尚未合入 dev 的符号 |
| 6 | **DDL 已改但数据回填未做** | 建表有、回填脚本无 ⇒ 生产上是空表 |
| 7 | **该卡对应的 issue 仍 open 且里程碑未完成** | 复用 `issue-health-scan` 的 milestone 规则 |

### 2.3 反向清单：以下**不是**中间态

误伤比漏放更贵——机械闸一旦被噪声淹没，可信度归零，此后所有告警都无人当真。

| 形态 | 判定 | 实证 |
|------|------|------|
| 「删重复实现，两页降为占位」 | ✅ 完成态 | #1855：刻意把废弃功能收敛成占位页就是交付结果 |
| 「占位页去假数据」 | ✅ 完成态 | #1854：占位页本身是要修的对象，不是未完成 |
| 单 commit 改 9 文件 | ✅ 正常 | #1978 的规模在常规区间 |
| 标题无 feat/fix 前缀 | ✅ 正常 | 标题前缀不是判据 |

---

## 3. Release note 判据（Closes 怎么写）

### 3.1 GitHub 原生行为的硬事实

- 功能 PR `base=dev` ⇒ **closing keyword 被完全忽略**（连 link 都不建）。本仓靠 `close-linked-issues.yml` 补这一层。
- 发版 PR `base=main` ⇒ main 是默认分支 ⇒ **closing keyword 原生生效，合并即关卡**。

⇒ **发版 PR 正文的 `Closes #N` 是真会关卡的。写错就是「中间态被当成完成」。**

### 3.2 写法规则

- **只对通过 §2 语义闸的卡写 `Closes`。** 没过的卡留 open，在「本次不发」清单里点名。
- **限定词必须去掉**：`Closes #1286（数据底座部分）` 这种括号限定会让 GitHub **照关不误**——GitHub 不理解「部分」。要关就关全卡，不关就别写。（`issue_health_scan` 已把带括号的降级为 B 类待复核，两边口径必须一致。）
- **支持逗号列表**：`Closes #1926, #1927`。解析口径与 `close_linked_issues.js`（D37）严格一致——九个关键字变体、逗号/顿号/中文逗号列表。
- **跨仓 `Closes owner/repo#N` 不对本仓生效**，只作登记，报告里单独标出。
- **代码块与行内代码内的关键字不生效**，所以不要在正文里贴「示例：`Closes #123`」——会被解析器看到（虽然 GitHub 自己也会看到，但我们报告要能区分）。

### 3.3 标题格式（沿用 #1765 / #1645 / #1524 的既有惯例）

```
chore(release): dev → main 发布（N 提交 / M PR，含 #XXXX 轨道名、#YYYY 轨道名）
```

`含…` 部分由语义复核产出，**脚本生成不了**，必须人写或 agent 写。

---

## 4. 流程

| 步 | 动作 | 执行者 |
|----|------|--------|
| 1 | 跑 `release_readiness.py` 修完所有 BLOCK | 脚本 + 人 |
| 2 | 按 §2 逐 feature 回 `origin/dev` grep 实证 | agent / 人 |
| 3 | 定 release note：哪些 `Closes`，哪些留 open 并点名 | agent / 人 |
| 4 | 开 `dev → main` 发版 PR | agent |
| 5 | **等 `质量门禁汇总` 绿**（main 的 required check） | CI |
| 6 | **合并发版 PR** | **人，不自动化** |

### 4.1 为什么合并不自动化

- 合并 = 立即上生产（Vercel / Cloudflare 都听 main 的 push）。不可逆动作。
- base=main 时 Closes 原生生效 ⇒ 正文写错 = 误关卡，且**无法通过回滚 PR 撤销**。
- 本仓既有立场一致：`issue-health-scan.yml` 明确「只报告不自动关」，理由是 #1349 误标证伪了纯规则自动关。

### 4.2 与 issue 体检的关系

两者都是周一上午的独立 workflow，**刻意错开 15 分钟**：

- `issue-health-scan.yml`：周一 08:30 北京时间。**纯机械规则**，不引入 AI（其设计决策第 1 条）。
- `release-readiness.yml`：周一 08:45 北京时间，产出发版机械闸报告。**机械闸 + agent 语义闸**。
  错开是因为两者都要密集调用 GitHub API，同一分钟起跑会互相抢速率配额。

不要把语义判定塞进体检脚本——那会让它偏离自己写下的设计原则。体检结果作为发版复核的输入（哪些卡 open、哪些停滞），而非被改写。

---

## 5. 性能实测（本机到 GitHub 链路，2026-10-08）

| 调用 | 单次耗时 |
|------|---------|
| `pulls?state=closed&base=dev&per_page=100` | **94s** |
| `pulls?...&per_page=30` | 显著更快 |
| `compare/main...dev` | **45s** |

首版全流程 3m21s，稳定 SIGTERM。优化到 **1m47s**（-47%），靠三件事：

1. `PR_PAGE = 30` 而非 100（body 字段是响应体大头）
2. gate 判定复用同一份已合 PR 列表，不再二次拉取
3. 双向 compare 合并为一次 `main...dev`，`behind` 由祖先关系反推

**不要把 `PR_PAGE` 调回 100。** 回归用例里有静态断言钉住这个值和实测数据。

---

## 6. 已知边界

- compare API 只返回前 300 个文件。**截断时 DDL 判据不给「通过」**（见 §1.2），但仍可能漏掉真实 DDL ⇒ 大批次必须本地复核。
- **待发 PR 数是下限，不是全量。** `PR_PAGE = 30` 是性能取舍（见 §5），一页只装 30 条：
  v0.3.0 发版实测真实 220 个待发 PR，报告只数到 27（覆盖 12%）。脚本会把未取全的计数渲染成 `≥N`
  并单列「待发 PR 覆盖范围」，但**要精确值必须人工逐页复核**。中间态标题扫描同样只覆盖这一页。
- 语义闸**完全**依赖人 / agent 执行。脚本绿灯 ≠ 可发版。这句话印在报告顶部。
- `gh_json` 无速率限制处理。本仓周均 PR 量在百级，暂不构成压力。
