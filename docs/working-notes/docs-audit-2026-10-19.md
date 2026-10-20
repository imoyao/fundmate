# docs/ 目录审计报告（2026-10-19）

> 全部结论由机械判据得出，**不含主观取舍**。需要 owner 判断的部分集中列在 §5。
> 配套索引：[working-notes/README.md](./working-notes/README.md)

---

## 0. 全库现状

| 指标 | 数值 |
|---|---|
| docs/ 下 md 总数 | 279 |
| 其中 working-notes | 149 |
| working-notes 被其他文档引用 | 79（53%） |
| **已完全落地** | **50**（28 张仍被引用 → 不建议动；22 张零引用 → 可归档） |
| 部分落地 | 58 |
| 无引用 + 非落地（疑似孤儿） | 20 |

---

## 1. 三个误判澄清

审计过程中有三个「看起来像问题但其实不是」的点，先纠正，避免按错误前提动手：

### 1.1 「V1 时期文档堆积」——不成立

按 git 最后提交时间筛「8 月前未再动」的文档，在**当前工作树**里只剩**1 张**：

| 文档 | 最后提交 |
|---|---|
| `docs/api/api-from-third-party.md` | 2026-05-08 |

> ⚠️ 曾用 `git log --name-only` 的历史文件名当现状清单，得到「47 张 V1 遗留」——**这是错的**，那些是 V1 项目 `showbuy` 的路径（`docs/showbuy/`、`docs/fallback/`、`docs/thoughts/`），当前仓库里**根本不存在**。用历史文件名冒充现状清单是典型的 git 误用，已修正为「历史文件名 ∩ 当前 glob」。

### 1.2 「git 历史完备所以可以删」——不成立

`git log` **不能全文搜正文**，只能搜 commit message 的一行标题；`git log -S` 能搜内容差异但要求你记得当时的用词，且慢。AI 读文件比解析 git diff 快一个量级。**「完备」不等于「可达」**——删掉就等于真的找不回来。

### 1.3 「working-notes 对用户不友好」——不成立

`docs/.vitepress/config.mjs` 的 `contentDirs` 只列了 9 个目录（guide/dev/api/pytest/features/spec/design/ops/blog），**working-notes 不在其中** ⇒ 这149 张从未出现在文档站，对外部用户不可见。

---

## 2. 已完全落地 → 建议归档（50 张）

**判据**：卡内 ≥3 个代码标识符（形如 `` `snake_case` ``），且**全部仍存在于代码中** ⇒ 卡的全部主张都已实现，卡相对代码**零增量信息**。

> 这些不是「过时」而是「已完成」。归档后代码仍是唯一真相，损失为零。

### 2.1 其中仍被其他文档引用（28 张）——**不建议动**

被引用说明它们承载了「为什么这样做」的解释，直接归档会造成悬空引用。

| 卡片 | 主题 |
|:---|:---|
| [agent-guardrail-layer-design-2026-08-17](./working-notes/agent-guardrail-layer-design-2026-08-17.md) | AI 与Agent |
| [external-source-policy-2026-09-30](./working-notes/external-source-policy-2026-09-30.md) | 数据源与落库 |
| [2026-09-28](./working-notes/2026-09-28.md) | 项目管理 |
| [bias-datasource-replacement-2026-08-03](./working-notes/bias-datasource-replacement-2026-08-03.md) | 数据源与落库 |
| [eastmoney-antiscrape-2026-08-05](./working-notes/eastmoney-antiscrape-2026-08-05.md) | 数据源与落库 |
| [fundfof-borrowing-analysis-2026-08-03](./working-notes/fundfof-borrowing-analysis-2026-08-03.md) | 数据源与落库 |
| [ledger-channel-category-redesign-2026-08-28](./working-notes/ledger-channel-category-redesign-2026-08-28.md) | 账户与渠道 |
| [agent-issues-2026-08-17](./working-notes/agent-issues-2026-08-17.md) | AI 与Agent |
| [backend-architecture-audit-2026-09-19](./working-notes/backend-architecture-audit-2026-09-19.md) | 后端与架构 |
| [import-page-ux-and-monetization-review-2026-08-15](./working-notes/import-page-ux-and-monetization-review-2026-08-15.md) | 项目管理 |
| [product-detail-page-design-2026-10-08](./working-notes/product-detail-page-design-2026-10-08.md) | 产品详情页 |
| [db-download-import-2026-08-09](./working-notes/db-download-import-2026-08-09.md) | 数据源与落库 |
| [e-account-reconciliation-design-2026-08-16](./working-notes/e-account-reconciliation-design-2026-08-16.md) | 账户与渠道 |
| [fundfof-round2-db-issue-2026-09-30](./working-notes/fundfof-round2-db-issue-2026-09-30.md) | 数据源与落库 |
| [mirror-state-backflow-2026-10-11](./working-notes/mirror-state-backflow-2026-10-11.md) | 双库与同步 |
| [portfolio-strategy-unification-2026-08-24](./working-notes/portfolio-strategy-unification-2026-08-24.md) | 账本与记账 |
| [data-refresh-scheduling-plan-2026-09-13](./working-notes/data-refresh-scheduling-plan-2026-09-13.md) | 自选与探市 |
| [ledger-cash-like-product-binding-2026-08-29](./working-notes/ledger-cash-like-product-binding-2026-08-29.md) | 账本与记账 |
| [manager-profile-card-phase1-design-2026-10-10](./working-notes/manager-profile-card-phase1-design-2026-10-10.md) | 数据源与落库 |
| [amac-encoding-incident-2026-08-17](./working-notes/amac-encoding-incident-2026-08-17.md) | 后端与架构 |
| [dividend-tax-reminder-2026-10-19](./working-notes/dividend-tax-reminder-2026-10-19.md) | 账本与记账 |
| [eastmoney-datasource-and-account-linkage-design-2026-08-30](./working-notes/eastmoney-datasource-and-account-linkage-design-2026-08-30.md) | 数据源与落库 |
| [explore-watchlist-enhancement-2026-08-12](./working-notes/explore-watchlist-enhancement-2026-08-12.md) | 自选与探市 |
| [index-daily-tencent-source-2026-10-01](./working-notes/index-daily-tencent-source-2026-10-01.md) | 数据源与落库 |
| [industry-crowding-baostock-fallback-2026-08-07](./working-notes/industry-crowding-baostock-fallback-2026-08-07.md) | 数据源与落库 |
| [2026-09-11](./working-notes/2026-09-11.md) | 项目管理 |
| [securities-aggregation-design-2026-08-29](./working-notes/securities-aggregation-design-2026-08-29.md) | 账户与渠道 |
| [unified-import-entry-evaluation-2026-08-16](./working-notes/unified-import-entry-evaluation-2026-08-16.md) | 前端与设计 |

### 2.2 无任何引用（22 张）——**建议移入 legacy/**

零引用 + 已完全落地 = 纯冗余。归档动作 = `git mv` 到 `docs/working-notes/legacy/`，**不删内容**。

| 卡片 | 行数 | 主题 | 摘要 |
|:---|---:|:---|:---|
| `product-roadmap-audit-2026-08-09.md` | 253 | 项目管理 | - 已有 issue 覆盖、无需新建：#429 导出、#785 同步、#796 XIRR |
| `money-fund-income-plan-2026-08-09.md` | 210 | 数据源与落库 | 1. 本金口径混乱（两条并行的货币基金记账路径）： |
| `product-detail-research-2026-10-12.md` | 163 | 账本与记账 | 走势已上首屏（#2107）；数据分层按「持仓本地持久 + 非持仓后端代理 + 冷热分层缓 |
| `fund-position-skip-path-triage-2026-10-01.md` | 158 | 数据源与落库 | 12:50:07 | INFO    | orchestrator:run_job:37 |
| `asset-snapshot-yoy-plan-2026-08-09.md` | 123 | 运营与发布 | frontend/src/views/asset/AssetPanorama.vue 顶 |
| `dividend-tax-timely-2026-10-19.md` | 118 | 账本与记账 | 原判据是「同标的同一年有 dividend_tax ⇒ 视为已结清」。实测后果： |
| `summary-aggregation-convergence-2026-10-15.md` | 112 | 账本与记账 | D59 把「总资产」收敛到 family_totals 一个出口，验收三项达成。但那一轮 |
| `2026-10-16.md` | 111 | 项目管理 | - 对比基线：本目录下最近一次落盘报告是 2026-09-28.md。⚠️ 流程异常：记 |
| `frontend-api-reorg-2026-08-09.md` | 110 | 前端与设计 | - AssetPanorama 瀑布图：initWaterfallChart（L691- |
| `industry-crowding-multidim-2026-08-08.md` | 110 | 数据源与落库 | 现有行业拥挤度 industry_crowding.py 只输出单维 =「PB 倍数 / |
| `issue-triage-dispatch-2026-10-18.md` | 110 | 双库与同步 | 源：CNB #564。用户拍板四件事——先回流已关的 → 分诊/打标签/写评论 → 派活 |
| `tech-baseline-roadmap-2026-08-04.md` | 94 | 前端与设计 | - 每域一个 APIBlueprint，路由在 views.py： |
| `index-catalog-sources-research-2026-09-08.md` | 91 | 数据源与落库 | 对高价值指数在三大名录源的覆盖实测： |
| `mirror-correction-channel-2026-10-11.md` | 83 | 双库与同步 | github_cnb_issues.py 的取舍是「只增不覆盖」——CNB 侧人工调过的 |
| `mirror-false-red-and-divergence-2026-10-11.md` | 81 | 双库与同步 | 日期：2026-10-11　关联：CNB #118 / #120 / #123　状态：待 |
| `display-name-portfolio-bare-code-hijack-2026-10-10.md` | 79 | 数据源与落库 | 详情页副标题仍是「投顾组合 / QIEMAN · 基民柠檬」，标题却是基金名 —— 说明 |
| `win-local-pytest-env-prereqs-2026-09-27.md` | 73 | AI 与Agent | 1. .env 不入库（gitignored），CI 上没有 TURSO_DATABAS |
| `fund-company-backfill-1199-2026-08-30.md` | 71 | 双库与同步 | #1199 承接 #1168（PR #1190）的范围外遗留： |
| `ghost-duplicate-domain-d-frontend-2026-10-16.md` | 64 | 前端与设计 | 关联：CNB duoduobei/fundmate#477 / GitHub https |
| `supabase-jwks-es256-verification-2026-08-08.md` | 63 | 前端与设计 | app/core/auth.py 的 decode_supabase_token 用 H |
| `holding-days-semantics-2026-09-02.md` | 56 | 账本与记账 | 当前实现已经正确：持仓详情页的「持有时长」按 positions.confirm_dat |
| `doc-code-discrepancy-2026-08-03.md` | 34 | 后端与架构 | - 鉴权方向：用户要求单用户→家庭成员多用户，且拒绝写死变量。建议继续用 Supabas |

---

## 3. 公开可见的通用教程（21 张）——需 owner 定性

**这批与上面不同：它们进了文档站导航，普通用户能看见。**

| 目录 | 张数 | 性质 |
|---|---:|---|
| `docs/pytest/` | 8 | 通用 pytest 教程（fixture / parametrize / cov / keywords / questions）—— 读者是「学 pytest 的人」，不是「用 fundmate 的人」 |
| `docs/dev/` | 13 | 部分是通用技术笔记（apiflask-tutorial / oauth2 / python-typing / errors-vs-exceptions），部分是本仓开发约定 |

**核心问题：文档站服务谁？** 若定位为「用 fundmate 的人」，则pytest/apiflask 这类通用教程不该在这里；若接受它同时是学习站，则保留但需要与项目文档区分。

> 注：`docs/dev/` 有 3 张带 `permalink` frontmatter，**已对外发布**（如 `choices-for-sqlalchemy` → `/dev/choices-for-sqlalchemy`），删除会破外链。

---

## 4. 无引用 + 未落地（20 张）——**需 owner 判断，不建议 AI 动**

这批里可能混着两类完全不同的东西：

- **你的想法存档**：无实现、无引用，但记录了当时的判断与取舍 → **有长期价值，不能删**；
- **真正过时**：结论已被后续推翻、任务从未开始 → 可清。

**AI 无法区分这两类**（这是你上一轮指出的关键点，已接受）。列出供参考：

| 卡片 | 行数 | 摘要 |
|:---|---:|---|
| `issue-783-import-checklist-audit-2026-10-15.md` | 158 | 一句话：这张卡已不具备「待办清单」的功能——它的勾选状态不可信、条目大面积被后续产品演进替代或重置， |
| `launch-plan-2026-08-09.md` | 157 | - 后端 API + 前端工具站部署到云上，公网可用； |
| `explore-issue808-status-2026-08-19.md` | 105 | 「探市」体验版——免登录沙盒，看实时收益、零门槛添加（≤2 步）、注册引导（迁移本地持仓）。 |
| `feedback-changelog-rollout-2026-10-09.md` | 103 | 要，但只要一个 token 端点；且这个端点不该在主站。 |
| `mock-service-data-isolation-2026-08-30.md` | 102 | 可以为 fundmate 引入 mock 服务来实现你的两个目标，而且绝大多数核心方案都是免费的。你 |
| `ledger-alignment-review-2026-10-13.md` | 94 | 调研大方向全部成立，无系统性走偏。账本主干（成本/流水/分红/估值链路/导入）已完整，多项比同花顺更 |
| `brand-landing-plan-2026-08-04.md` | 93 | - 主标题：多多贝；副标题：投资账本；站点全名/SEO：多多贝投资账本。 |
| `cnb-dev-ahead-rescue-2026-10-11.md` | 88 | 路线决策文件（cnb-github-mirror-route-2026-10-11.md）给出的是口 |
| `concept-explainer-five-buckets-and-goals-2026-08-13.md` | 64 | 你打开多多贝，会看到两个主页面：投资概览 和 资产总览。它们说的不是同一件事，用一个比喻就通了： |
| `watchlist-feature-gap-audit-2026-08-13.md` | 64 | 逐条核对 #661 / #807 / #826 / #860 四个自选相关 issue，对照当前 b |
| `ark-model-availability-2026-09-28.md` | 61 | 纪律：写「可用」必须是第 3 层实测 OK。Retiring 模型的 404 报文是 |
| `release-notes-v0.1.0-draft-2026-10-09.md` | 55 | 第一版 changelog 不是「变更记录」，是「产品介绍」。 |
| `ai-code-review-deepseek-dual-line-2026-08-23.md` | 54 | 日期：2026-08-23。分支：feat/ghost-duplicate-scan（提交 9918 |
| `gitee-ai-reference-audit-2026-09-26.md` | 48 | 一句话定级：骨架真、皮肉虚、测试是装饰，文档跑在代码前面。 |
| `branch-convergence-assessment-2026-08-19.md` | 42 | 现状（frontend/src/views/explore/index.vue 的 handleAd |
| `ledger-detail-info-redesign-plan-2026-08-27.md` | 41 | 用户在使用账户详情页时发现三处体验问题，经讨论确定方向： |
| `welcome-message-layer-2026-08-13.md` | 40 | 投资概览（welcome）此前叠了多处死数据（风险热力图、收益趋势、资产变动趋势、财务晴雨表四项）， |
| `brandsub-beta-pending-2026-08-08.md` | 35 | 已解除（RESOLVED，2026-08-10）。按「恢复方案」重建两文件并提交（commit e5 |
| `opencode-github-issue-utf8-rule-2026-08-09.md` | 25 | - 标题/正文里的中文在提交到 GitHub 之前就已经损坏（GitHub 服务端不会把中文变 ?） |
| `release-notes-v0.1.0-body.md` | 23 | 把散落在不同平台的钱，合成一你自己看得懂的账。 |

> 共 20 张，全部列出。完整清单见索引表里标记为 `·` 的行。

---

## 5. 需要 owner 判断的三件事

### 5.1 想法存档的识别标准

你提到「有时会把一些自己的想法记录在备忘卡里」。要不要在文件名或 frontmatter 上加一个显式标记（如 `type: idea` / 文件名前缀 `idea-`）？有了标记，这批卡就能被机器识别、**永久免于被清理**，而其他卡可以被自动归位。

这是唯一能让我在**不冒判断错误风险**的前提下做归位的办法 —— **建议采纳**。

### 5.2 文档站定位

`pytest/` `dev/` 里的通用教程是留还是清？清了会破外链（3 张有 permalink）。

### 5.3 归档范围

§2.2 那批零引用已落地的卡，是否全部移入 `legacy/`？还是先只移一半（行数 >200 的）？

---

## 6. 后续防堆积：把成本前置

整理是一次性的，**不解决继续堆积**。建议加两条低成本机制：

| 机制 | 判据 | 何时触发 |
|:---|:---|:---|
| 备忘卡必带 frontmatter | 新卡缺 `date` / `theme` / `type` | 建卡时（人或 AI 都一样） |
| 备忘卡进文档站前需归类 | 主题为「其他」的卡 | 索引表生成时提示 |

> 这两条只约束**新卡**，不追溯存量，因此零风险。存量治理靠 §5 的一次性判断。

