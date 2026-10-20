# 工作备忘索引（working-notes）

> 共 **151 张**，2026-10-19 按主题归类。**一张未删**——本表只解决「找不到」，不解决「该不该留」。
> 归位与归档的判断依据见 [docs-audit-2026-10-19.md](./docs-audit-2026-10-19.md)。
> 「摘要」列是卡片开头若干字符的**机械截取**，不是结论——结论以卡片本体为准。

## 图例

| 标记 | 含义 | 机械判据 |
|---|---|---|
| 📌 | 被其他文档引用 | 文件名在其他 md 中出现 |
| ✅ | **已完全落地** | 卡内 ≥3 个代码标识符全部仍存在于代码 → 卡已无增量信息 |
| ◐ | **部分落地** | 标识符缺失 <50% |
| · | 疑似过时/孤儿 | 全仓无任何文件引用 |
| — | 判据未跑 | 索引生成后才入库的卡，机械判据未覆盖；补录时不硬套上面四档 |


## 账本与记账（23 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [portfolio-strategy-unification-2026-08-24](./portfolio-strategy-unification-2026-08-24.md) | 80 | ✅ 📌 | - 「投资组合」（账户级绑定，XIRR 口径）与「策略视图」（持仓级标签，展示口径）回答同一问题——「我的钱按目的分 |
| [ledger-cash-like-product-binding-2026-08-29](./ledger-cash-like-product-binding-2026-08-29.md) | 178 | ✅ 📌 | 用户在证券 / 基金账户卖出后，资金应留在投资账户内（账户现金，或账户绑定的类现金产品）， |
| [dividend-tax-reminder-2026-10-19](./dividend-tax-reminder-2026-10-19.md) | 80 | ✅ 📌 | 即：不自动算税，改为提醒 + 让用户自己补记。这一条把「要不要做」定死了， |
| [dividend-tax-timely-2026-10-19](./dividend-tax-timely-2026-10-19.md) | 118 | ✅ | 原判据是「同标的同一年有 dividend_tax ⇒ 视为已结清」。实测后果： |
| [holding-days-semantics-2026-09-02](./holding-days-semantics-2026-09-02.md) | 56 | ✅ | 当前实现已经正确：持仓详情页的「持有时长」按 positions.confirm_date（本轮建仓日）到今天计日； |
| [product-detail-research-2026-10-12](./product-detail-research-2026-10-12.md) | 163 | ✅ | 走势已上首屏（#2107）；数据分层按「持仓本地持久 + 非持仓后端代理 + 冷热分层缓存」做，前端不直连第三方；持 |
| [summary-aggregation-convergence-2026-10-15](./summary-aggregation-convergence-2026-10-15.md) | 112 | ✅ | D59 把「总资产」收敛到 family_totals 一个出口，验收三项达成。但那一轮的正文里留了一句边界： |
| [cash-equivalent-classification-design-2026-09-07](./cash-equivalent-classification-design-2026-09-07.md) | 115 | ◐ 📌 | - 理财 / 投资导向：买货基是为了赚 ~3% 年化，希望看到收益贡献，倾向归「投资」。 |
| [jigu-migration-plan-2026-08-11](./jigu-migration-plan-2026-08-11.md) | 142 | ◐ 📌 | - 用户部署并拥有自己的基估宝实例，核心数据在 Supabase user_configs 表的 data JSON |
| [asset-management-gap-analysis-2026-08-30](./asset-management-gap-analysis-2026-08-30.md) | 160 | ◐ 📌 | 这份报告把一位资深用户提出的六条硬需求，逐条对齐到 fundmate 现有代码，得出的结论是：产品的「壳」已经搭起来 |
| [advisor-ttfund-id-research-2026-09-08](./advisor-ttfund-id-research-2026-09-08.md) | 190 | ◐ 📌 | 一句话：App 搜索确实能呈现投顾，但其接口不可复现；GitHub 帮不上投顾持仓的忙，却意外给了 validmar |
| [asset-management-gap-roadmap-2026-08-30](./asset-management-gap-roadmap-2026-08-30.md) | 108 | ◐ 📌 | 那位用户提的六条需求不是功能清单，而是一个模型主张：资产的记账粒度应该由"能不能拿到净值"决定，而不是由产品形态决定 |
| [frontend-holding-import-plan-2026-08-16](./frontend-holding-import-plan-2026-08-16.md) | 151 | 📌 | E 账户（中国结算基金 E 账户）持仓快照导入。用户上传平台导出的持仓 Excel，系统解析后自动归因到渠道账户（天 |
| [2026-08-24-ledger-merge-spike](./2026-08-24-ledger-merge-spike.md) | 54 | ◐ | 迁移持仓撞 UNIQUE(ledger_id, symbol)： |
| [advisor-ttfund-holdings-api-2026-09-08](./advisor-ttfund-holdings-api-2026-09-08.md) | 245 | ◐ | 按既定优先级继续逆向签名/鉴权系统，并从 tradeh5 的 funda91a99886abf7e 包（App.js |
| [branch-convergence-assessment-2026-08-19](./branch-convergence-assessment-2026-08-19.md) | 42 | · | 现状（frontend/src/views/explore/index.vue 的 handleAdd / addH |
| [cross-ledger-import-dedup-scope-2026-08-16](./cross-ledger-import-dedup-scope-2026-08-16.md) | 68 | ◐ | 导入向导第三步预览页当前对「同一份交割单重复导入」在两层同时卡死，即使切换账本（LEDGER）也无法重导： |
| [fund-conversion-design-2026-10-17](./fund-conversion-design-2026-10-17.md) | 605 | ◐ | - 前端：frontend/src/views/asset/investment/manual/index.vue  |
| [ledger-alignment-review-2026-10-13](./ledger-alignment-review-2026-10-13.md) | 94 | · | 调研大方向全部成立，无系统性走偏。账本主干（成本/流水/分红/估值链路/导入）已完整，多项比同花顺更深（盈亏三段口径 |
| [ledger-capability-backlog-2026-10-10](./ledger-capability-backlog-2026-10-10.md) | 157 | ◐ | 1. 账本主干已齐：持仓/成本/浮动盈亏/已实现盈亏/流水/多账户/收益日历（日·月·年·自定义区间）/XIRR/分 |
| [pnl-calendar-design-2026-10-06](./pnl-calendar-design-2026-10-06.md) | 304 | ◐ | #1812 原方案（读 asset_snapshots 画日历）不可行，因asset_snapshots |
| [portfolio-lot-attribution-design-2026-08-25](./portfolio-lot-attribution-design-2026-08-25.md) | 180 | ◐ | - 同标的分批分属不同组合的场景，现有 positions 聚合行（同账户同标的 = 一行，总量 + 摊薄成本）在  |
| [reconciliation-framework-design-2026-08-31](./reconciliation-framework-design-2026-08-31.md) | 423 | ◐ | 手动导入是投资记账的核心场景，数据源头在用户手里，系统永远无法 100% 自动正确。现有三套流程各自独立、形态不一： |

## 数据源与落库（35 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [external-source-policy-2026-09-30](./external-source-policy-2026-09-30.md) | 192 | ✅ 📌 | 结论：没有任何一项「高价值且只能从 fundfof 取」的数据。 剩下的两件事 |
| [bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md) | 124 | ✅ 📌 | backend/app/services/bias/calculator.py 的 PriceFetcher.fet |
| [eastmoney-antiscrape-2026-08-05](./eastmoney-antiscrape-2026-08-05.md) | 162 | ✅ 📌 | akshare 取东方财富数据在本机失败，有两个叠加的、性质不同的根因： |
| [fundfof-borrowing-analysis-2026-08-03](./fundfof-borrowing-analysis-2026-08-03.md) | 99 | ✅ 📌 | 我之前的版本把 多账户聚合、全交易类型、XIRR+回撤、自选/提醒、手动记账、统一资产模型 列为"待实现/已规划"， |
| [db-download-import-2026-08-09](./db-download-import-2026-08-09.md) | 78 | ✅ 📌 | - 同步入口现状（backend/app/tools/sync_metadata.py + sync_cli.py  |
| [fundfof-round2-db-issue-2026-09-30](./fundfof-round2-db-issue-2026-09-30.md) | 398 | ✅ 📌 | ① 第一轮有一处判断错了，必须撤回：基金经理数据"未落盘"是错的。 |
| [manager-profile-card-phase1-design-2026-10-10](./manager-profile-card-phase1-design-2026-10-10.md) | 326 | ✅ 📌 | #1970 的降级判断是错的，根因不是数据源没有，而是 job 把已拿到的数据丢在了地上。 |
| [eastmoney-datasource-and-account-linkage-design-2026-08-30](./eastmoney-datasource-and-account-linkage-design-2026-08-30.md) | 87 | ✅ 📌 | 用户提到的「头部数据」「MCP 抓取」「天天基金代码」经核查如下，均为已存在事实： |
| [index-daily-tencent-source-2026-10-01](./index-daily-tencent-source-2026-10-01.md) | 76 | ✅ 📌 | index_daily 原本只有万得系（韭圈儿 .WI，10 个目标），而绩效对比最常用的基准 |
| [industry-crowding-baostock-fallback-2026-08-07](./industry-crowding-baostock-fallback-2026-08-07.md) | 75 | ✅ 📌 | 行业拥挤度 crowding_pct 的分母 = 全 A 中位 PB，由 industry_crowding.py: |
| [display-name-portfolio-bare-code-hijack-2026-10-10](./display-name-portfolio-bare-code-hijack-2026-10-10.md) | 79 | ✅ | 详情页副标题仍是「投顾组合 / QIEMAN · 基民柠檬」，标题却是基金名 —— 说明 |
| [fund-position-skip-path-triage-2026-10-01](./fund-position-skip-path-triage-2026-10-01.md) | 158 | ✅ | 12:50:07 | INFO    | orchestrator:run_job:371 - 开始执行 fund_ |
| [index-catalog-sources-research-2026-09-08](./index-catalog-sources-research-2026-09-08.md) | 91 | ✅ | 对高价值指数在三大名录源的覆盖实测： |
| [industry-crowding-multidim-2026-08-08](./industry-crowding-multidim-2026-08-08.md) | 110 | ✅ | 现有行业拥挤度 industry_crowding.py 只输出单维 =「PB 倍数 / 全 A 中位 PB」的历史 |
| [money-fund-income-plan-2026-08-09](./money-fund-income-plan-2026-08-09.md) | 210 | ✅ | 1. 本金口径混乱（两条并行的货币基金记账路径）： |
| [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md) | 155 | ◐ 📌 | ① 新浪行情（经 akshare stock_zh_a_daily） |
| [datasource-priority-plan-2026-08-03](./datasource-priority-plan-2026-08-03.md) | 131 | ◐ 📌 | A 股数据的真实上游只有几家：东财 / 腾讯 / 新浪 / 天天基金 / 集思录。 |
| [scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md) | 169 | 📌 | 不要让"定时器"去跑 Python 重活。 正确姿势： |
| [fundfof-gap-analysis-2026-09-30](./fundfof-gap-analysis-2026-09-30.md) | 331 | ◐ 📌 | 1. 你的 P0/P1 方向是对的，但排序的「轴」选错了。 你按功能排序，而真正的成本瓶颈只有一处数据：基金季报持仓 |
| [worktile-archive-2021-2026-08-09](./legacy/worktile-archive-2021-2026-08-09.md) | 353 | 📌 | 本文件收录不适合建 issue、但有长期参考价值的卡片原文：数据源调研、竞品观察、算法论证。 |
| [fund-holdings-probe-2026-09-30](./fund-holdings-probe-2026-09-30.md) | 298 | ◐ 📌 | 用主仓真实环境（D:/codes/fundmate/backend/.venv，Python 3.12.0，aksh |
| [investment-strategy-engine-requirements-2026-10-15](./investment-strategy-engine-requirements-2026-10-15.md) | 834 | ◐ 📌 | 值得做，但必须先换掉成功标准。 |
| [advisor-platform-landscape-2026-09-08](./advisor-platform-landscape-2026-09-08.md) | 207 | 📌 | 且慢提供官方 MCP 服务（盈米且慢 MCP），共 72 个金融工具，分五大模块。与你的需求直接对应的工具如下： |
| [data-persistence-criteria-2026-09-30](./data-persistence-criteria-2026-09-30.md) | 166 | ◐ 📌 | - 结论能脱离账本成立 —— 别人也能算，且我们做不过有全市场数据的对手； |
| [investment-ledger-gap-analysis-2026-10-10](./investment-ledger-gap-analysis-2026-10-10.md) | 185 | ◐ 📌 | 账本主干已经齐了——持仓/成本/浮动盈亏/已实现盈亏/流水/多账户/收益日历/XIRR 都在跑。 |
| [pr1362-review-closure-2026-09-09](./pr1362-review-closure-2026-09-09.md) | 86 | ◐ 📌 | PR #1362 上的评审意见分两批：owner 自评 6 条（第一轮收束，见 commit b86d4b2）与 A |
| [advisor-holdings-research-2026-09-08](./advisor-holdings-research-2026-09-08.md) | 177 | ◐ | 你要的是前者。下面所有内容都围绕"投顾组合持仓比例"。 |
| [ark-model-availability-2026-09-28](./ark-model-availability-2026-09-28.md) | 61 | · | 纪律：写「可用」必须是第 3 层实测 OK。Retiring 模型的 404 报文是 |
| [fund-detail-second-expansion-2026-10-10](./fund-detail-second-expansion-2026-10-10.md) | 403 | ◐ | 做。但做的不是「照抄报告版式」，是三件事： |
| [fund-metadata-arch-issue-1155-research-2026-08-29](./fund-metadata-arch-issue-1155-research-2026-08-29.md) | 97 | ◐ | 根因已明确：fund_type_id 字段本身就存在于 funds 表（backend/app/domains/fu |
| [fund-penetration-design-2026-10-01](./fund-penetration-design-2026-10-01.md) | 282 | ◐ | 1. 数据底座早已齐备、读侧为零。 fund_industry_allocs（830 行 / 101 基金）与 fu |
| [manager-style-tags-calibration-2026-10-12](./manager-style-tags-calibration-2026-10-12.md) | 101 | ◐ | 阈值取整说明：集中度/行业档位取全库 P50 / P80 并四舍五入到整数——集中度按剔除不完整样本后的 n=100 |
| [release-notes-v0.1.0-body](./release-notes-v0.1.0-body.md) | 23 | · | 把散落在不同平台的钱，合成一你自己看得懂的账。 |
| [sw-industry-source-plan-2026-09-14](./sw-industry-source-plan-2026-09-14.md) | 150 | ◐ | 结论：申万宏源官网通道在本机可用且数据到当日，调研包「不碰东财、纯申万单源」的路线在数据源侧成立。 |
| [watchlist-type-dimensions-design-2026-09-10](./watchlist-type-dimensions-design-2026-09-10.md) | 264 | ◐ | - #1286 就绪：统一编码/唯一键、聚合搜索、指数名录、天天投顾抓取、fund 元数据回填。 |

## 账户与渠道（9 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [ledger-channel-category-redesign-2026-08-28](./ledger-channel-category-redesign-2026-08-28.md) | 179 | ✅ 📌 | - 两层正交：ledger_type（内部资产类键，计算用，用户不可见） ⊥ channel_category（用户 |
| [e-account-reconciliation-design-2026-08-16](./e-account-reconciliation-design-2026-08-16.md) | 428 | ✅ 📌 | PR #1021 已合入 E 账户持仓快照导入：解析 → 预览 → 确认 → 落 e_account 聚合账户（up |
| [securities-aggregation-design-2026-08-29](./securities-aggregation-design-2026-08-29.md) | 68 | ✅ 📌 | 本功能（#1132）是 #1101 场外基金聚合的互补集：把跨多个券商/股票账本持有的 股票 + ETF + 可转债 |
| [e-account-import-data-decentralization-plan-2026-08-16](./e-account-import-data-decentralization-plan-2026-08-16.md) | 205 | ◐ 📌 | 两张参考截图构成了本次评估的起点：图 1 是第三方工具面向普通投资者的「全平台资产分析攻略」，解决"多账户分散看不清 |
| [sales-institution-common-group-2026-08-24](./sales-institution-common-group-2026-08-24.md) | 105 | ◐ 📌 | - 创建账户时销售机构下拉为 394 项平铺列表（AMAC 名录同步），按 org_name 字典序排序，用户找不到 |
| [account-channel-and-fee-design-2026-08-16](./account-channel-and-fee-design-2026-08-16.md) | 13 | 📌 |  |
| [e-account-aggregation-design-2026-08-28](./e-account-aggregation-design-2026-08-28.md) | 89 | ◐ 📌 | 1. E 账户不当普通账户显示 → 账户列表过滤掉它（保留 ledger_type='e_account' 作为内部 |
| [concept-explainer-five-buckets-and-goals-2026-08-13](./concept-explainer-five-buckets-and-goals-2026-08-13.md) | 64 | · | 你打开多多贝，会看到两个主页面：投资概览 和 资产总览。它们说的不是同一件事，用一个比喻就通了： |
| [ledger-detail-info-redesign-plan-2026-08-27](./ledger-detail-info-redesign-plan-2026-08-27.md) | 41 | · | 用户在使用账户详情页时发现三处体验问题，经讨论确定方向： |

## 自选与探市（14 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [data-refresh-scheduling-plan-2026-09-13](./data-refresh-scheduling-plan-2026-09-13.md) | 345 | ✅ 📌 | 状态：待拍板（v2）。v1 只列现状与待决项；v2 按评审意见补了四块——① 事实核证（能查的全查了，会上只确认不争 |
| [explore-watchlist-enhancement-2026-08-12](./explore-watchlist-enhancement-2026-08-12.md) | 211 | ✅ 📌 | - 不是必须：OCR 是便利性功能，解决「从券商/天天基金 App 截屏 → 导入自选」的录入痛点；不引入则用户手动 |
| [explore-watchlist-replan-2026-08-08](./explore-watchlist-replan-2026-08-08.md) | 293 | ◐ 📌 | 架构要点（CLAUDE.md 确认）：localStorage（storageStore）是主数据库，Supabas |
| [watchlist-paid-features-discussion-2026-08-14](./watchlist-paid-features-discussion-2026-08-14.md) | 54 | 📌 | 用户提出自选功能可做付费功能，三大方向： |
| [page-split-welcome-vs-panorama-2026-08-13](./page-split-welcome-vs-panorama-2026-08-13.md) | 159 | ◐ 📌 | welcome/index.vue（投资概览 / 「家庭资产看板」首屏）与 AssetPanorama.vue（资产 |
| [ai-recognizer-architecture-2026-08-13](./ai-recognizer-architecture-2026-08-13.md) | 217 | ◐ 📌 | 现有 AI 识别（backend/app/services/ocr_service.py）是单场景硬编码： |
| [free-cloud-services-2026-08-09](./free-cloud-services-2026-08-09.md) | 26 | 📌 | - 用户域（身份、家庭账本）→ Supabase 云端权威 + 本地 SQLite 缓存；市场域（净值/估值大数据， |
| [watchlist-group-switch-perf-2026-10-11](./watchlist-group-switch-perf-2026-10-11.md) | 67 | ◐ 📌 | 三层叠加，缺一不会「卡好几秒」： |
| [explore-issue808-status-2026-08-19](./explore-issue808-status-2026-08-19.md) | 105 | · | 「探市」体验版——免登录沙盒，看实时收益、零门槛添加（≤2 步）、注册引导（迁移本地持仓）。 |
| [launch-plan-2026-08-09](./launch-plan-2026-08-09.md) | 157 | · | - 后端 API + 前端工具站部署到云上，公网可用； |
| [market-pages-consolidation-2026-09-11](./market-pages-consolidation-2026-09-11.md) | 336 | ◐ | 1. 数据链路断了，「基础数据不够」的直觉是对的，但根因不在算法。 本地库温度数据停更于 2026-08-02（40 |
| [mvp-launch-blockers-2026-08-18](./mvp-launch-blockers-2026-08-18.md) | 94 | ◐ | 用户定义的 MVP 红线：探市页可用、温度计页可用、注册功能可用，并且要能从「本机 localhost」走到「部署上 |
| [qieman-strategy-catalog-2026-09-13](./qieman-strategy-catalog-2026-09-13.md) | 179 | ◐ | 此前系统只建档 2 只且慢组合（scripts/seed_advisors.py 里手写的 SEED 列表）， |
| [watchlist-feature-gap-audit-2026-08-13](./watchlist-feature-gap-audit-2026-08-13.md) | 64 | · | 逐条核对 #661 / #807 / #826 / #860 四个自选相关 issue，对照当前 backend/a |

## 产品详情页（1 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [product-detail-page-design-2026-10-08](./product-detail-page-design-2026-10-08.md) | 434 | ✅ 📌 | 一套详情页体系：按品类分 URL、两个入口、Epic 汇总卡带分项子卡。 |

## 前端与设计（19 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [unified-import-entry-evaluation-2026-08-16](./unified-import-entry-evaluation-2026-08-16.md) | 119 | ✅ 📌 | 数据导入功能目前确实散落在四个入口，且都未进入侧边栏（showLink:false），托盘入口又默认隐藏，可发现性存 |
| [frontend-api-reorg-2026-08-09](./frontend-api-reorg-2026-08-09.md) | 110 | ✅ | - AssetPanorama 瀑布图：initWaterfallChart（L691-780）硬编码（上期末 28 |
| [ghost-duplicate-domain-d-frontend-2026-10-16](./ghost-duplicate-domain-d-frontend-2026-10-16.md) | 64 | ✅ | 关联：CNB duoduobei/fundmate#477 / GitHub https://github.com/ |
| [supabase-jwks-es256-verification-2026-08-08](./supabase-jwks-es256-verification-2026-08-08.md) | 63 | ✅ | app/core/auth.py 的 decode_supabase_token 用 HS256 + SUPABAS |
| [tech-baseline-roadmap-2026-08-04](./tech-baseline-roadmap-2026-08-04.md) | 94 | ✅ | - 每域一个 APIBlueprint，路由在 views.py： |
| [build-oom-fix-2026-08-04](./build-oom-fix-2026-08-04.md) | 214 | 📌 | tech-debt.md 第 56 条： |
| [landing-login-sso-2026-08-04](./landing-login-sso-2026-08-04.md) | 48 | 📌 | - 静态落地页只做跳板：导航栏右上角放「登录」「免费开始」两个按钮，均为跳转链接，指向工具站 /app/login  |
| [frontend-architecture-mobile-eval-2026-08-04](./frontend-architecture-mobile-eval-2026-08-04.md) | 95 | 📌 | - 技术栈：Vue3 ＋ Vite ＋ TypeScript ＋ Pinia ＋ ECharts，UI 用 Elem |
| [fundfof-detail-impl-research-2026-10-10](./fundfof-detail-impl-research-2026-10-10.md) | 305 | ◐ 📌 | ① fundfof 的 13 个 tab 没有一个「重实现」，全是同一个骨架换参数。 |
| [font-plan-review-2026-09-04](./font-plan-review-2026-09-04.md) | 111 | 📌 | title: 字体方案（方案 B：Inter + Mi Sans）决策评审 |
| [asset-insight-panel-2026-08-28](./asset-insight-panel-2026-08-28.md) | 106 | ◐ | 可以做，且无需新增后端接口。 |
| [brand-landing-plan-2026-08-04](./brand-landing-plan-2026-08-04.md) | 93 | · | - 主标题：多多贝；副标题：投资账本；站点全名/SEO：多多贝投资账本。 |
| [brandsub-beta-pending-2026-08-08](./brandsub-beta-pending-2026-08-08.md) | 35 | · | 已解除（RESOLVED，2026-08-10）。按「恢复方案」重建两文件并提交（commit e56e838，对应 |
| [entry-points-consolidation-2026-08-14](./entry-points-consolidation-2026-08-14.md) | 137 | ◐ | - 手动记账壳 manual/index.vue 已抽出 useQuickEntrySubmit（composabl |
| [ocr-import-validation-issue-2026-08-21](./ocr-import-validation-issue-2026-08-21.md) | 48 | ◐ | 标题：feat(ocr): 粘贴文本导入增加产品存在性校验，未识别行返回行级错误 |
| [road-not-taken-revive-2026-08-30](./road-not-taken-revive-2026-08-30.md) | 68 | ◐ | views/asset/favorites/index.vue 原实现处于「呆萌」状态，主要问题： |
| [trading-personality-h5-plan-2026-08-10](./trading-personality-h5-plan-2026-08-10.md) | 182 | ◐ | 「多多贝」投资产品以海洋投资生态为隐喻，核心是投资认知闭环：人格测试（自报）→ 交易复盘（实测）→ 对比打脸（闭环） |
| [username-sensitive-word-2026-08-14](./username-sensitive-word-2026-08-14.md) | 78 | ◐ | - 后端 app/domains/users/schemas.py：ProfileUpdate 已对 usernam |
| [welcome-message-layer-2026-08-13](./welcome-message-layer-2026-08-13.md) | 40 | · | 投资概览（welcome）此前叠了多处死数据（风险热力图、收益趋势、资产变动趋势、财务晴雨表四项），且时间线重复、无 |

## 后端与架构（9 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [backend-architecture-audit-2026-09-19](./backend-architecture-audit-2026-09-19.md) | 278 | ✅ 📌 | title: 后端架构审查（结构性问题分级 · 2026-09-19） |
| [amac-encoding-incident-2026-08-17](./amac-encoding-incident-2026-08-17.md) | 51 | ✅ 📌 | amac_institution 同步 job 首次验证时，库中 AMAC 销售机构（394 条）/ 公募基金管理人 |
| [doc-code-discrepancy-2026-08-03](./doc-code-discrepancy-2026-08-03.md) | 34 | ✅ | - 鉴权方向：用户要求单用户→家庭成员多用户，且拒绝写死变量。建议继续用 Supabase Auth + Flask |
| [deployment-implementation-guide-2026-08-04](./deployment-implementation-guide-2026-08-04.md) | 216 | 📌 | [用户/前端] --HTTPS--> [EdgeOne Pages：Vue SPA，免费全球 CDN] |
| [backend-hosting-fetch-selection-2026-08-03](./backend-hosting-fetch-selection-2026-08-03.md) | 100 | ◐ 📌 | 1. EdgeOne 不只是前端：EdgeOne Pages＝前端静态 + Node Functions（JS 后端 |
| [code-audit-and-remediation-2026-08-01](./code-audit-and-remediation-2026-08-01.md) | 1124 | ◐ 📌 | 1. [代码问题审查（初版 2026-07-31）](#sec1) |
| [db-cost-decision-2026-08-04](./db-cost-decision-2026-08-04.md) | 102 | 📌 | - 腾讯云 PostgreSQL：无免费档，必产生费用（最小实例约 ¥100–300/月，按量更贵）。与你"验证期零 |
| [erniao-fetcher-redesign-2026-08-01](./erniao-fetcher-redesign-2026-08-01.md) | 319 | 📌 | 日期: 2026-08-01 |
| [mock-service-data-isolation-2026-08-30](./mock-service-data-isolation-2026-08-30.md) | 102 | · | 可以为 fundmate 引入 mock 服务来实现你的两个目标，而且绝大多数核心方案都是免费的。你的诉求其实分两层 |

## AI 与Agent（10 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [agent-guardrail-layer-design-2026-08-17](./agent-guardrail-layer-design-2026-08-17.md) | 148 | ✅ 📌 | 账本精灵（对话 Agent）要对用户账本做「查询 / 表现分析 / 行为解读 / 快速记账」。其最大风险不是技术，而 |
| [agent-issues-2026-08-17](./agent-issues-2026-08-17.md) | 182 | ✅ 📌 | 标题：feat(guard): ai_recognizer/safety 包骨架 + L3 输出词法过滤 |
| [win-local-pytest-env-prereqs-2026-09-27](./win-local-pytest-env-prereqs-2026-09-27.md) | 73 | ✅ | 1. .env 不入库（gitignored），CI 上没有 TURSO_DATABASE_URL → for_ap |
| [agent-dev-learning-plan-2026-09-25](./agent-dev-learning-plan-2026-09-25.md) | 463 | ◐ 📌 | 1. 你缺的不是 Agent 名词，是一条能自证的链路。 面试官那篇帖子的核心不是知识点，是「有没有被生产环境验证过 |
| [investment-agent-brainstorm-2026-08-17](./investment-agent-brainstorm-2026-08-17.md) | 386 | ◐ 📌 | 四个功能成熟度差异大，且都不是从零开始： |
| [agent-interview-prep-plan-2026-09-25](./agent-interview-prep-plan-2026-09-25.md) | 158 | 📌 | 缝合话术（承前启后，两段不重复的关键句）： |
| [agent-s6-interview-final-2026-09-28](./agent-s6-interview-final-2026-09-28.md) | 359 | ◐ 📌 | 计划 §S6 给的草稿约 350 字（常速 ≈70 秒），本稿按 30 秒口径压缩，零新增事实、逐句可溯源： |
| [mineru-alipay-ocr-eval-2026-08-14](./mineru-alipay-ocr-eval-2026-08-14.md) | 126 | ◐ 📌 | 用户从支付宝导出交割单往往只截图（手机截图 / 长图），而非规整 PDF。现有截图路径依赖火山方舟 ARK visi |
| [agent-dev-progress-2026-09-26](./agent-dev-progress-2026-09-26.md) | 630 | ◐ 📌 | - #1717 资产总览闪烁 + 按钮组样式（你提的，挂 M0 上线）——独立处理，不排入 Agent 主线。 |
| [ai-code-review-deepseek-dual-line-2026-08-23](./ai-code-review-deepseek-dual-line-2026-08-23.md) | 54 | · | 日期：2026-08-23。分支：feat/ghost-duplicate-scan（提交 9918f05，已推送） |

## 运营与发布（5 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [asset-snapshot-yoy-plan-2026-08-09](./asset-snapshot-yoy-plan-2026-08-09.md) | 123 | ✅ | frontend/src/views/asset/AssetPanorama.vue 顶部总览大卡片存在硬编码假数据 |
| [feedlog-setup-cn-2026-08-09](./feedlog-setup-cn-2026-08-09.md) | 151 | 📌 | 1. Cloudflare 账号（Workers 免费额度足以支撑中小流量） |
| [feedback-changelog-rollout-2026-10-09](./feedback-changelog-rollout-2026-10-09.md) | 103 | · | 要，但只要一个 token 端点；且这个端点不该在主站。 |
| [gitee-ai-reference-audit-2026-09-26](./gitee-ai-reference-audit-2026-09-26.md) | 48 | · | 一句话定级：骨架真、皮肉虚、测试是装饰，文档跑在代码前面。 |
| [release-notes-v0.1.0-draft-2026-10-09](./release-notes-v0.1.0-draft-2026-10-09.md) | 55 | · | 第一版 changelog 不是「变更记录」，是「产品介绍」。 |

## 双库与同步（11 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [cnb-github-sync-steady-state-2026-10-19](./cnb-github-sync-steady-state-2026-10-19.md) | 5 | — | 本文是**方案草稿**（working-note），用于先对齐「正常情况长什么样」，再动 `.cnb.yml`。 |
| [mirror-state-backflow-2026-10-11](./mirror-state-backflow-2026-10-11.md) | 318 | ✅ 📌 | title: 镜像卡状态回流：GitHub 已关闭 → CNB 标记并自动关闭（B 口径） |
| [fund-company-backfill-1199-2026-08-30](./fund-company-backfill-1199-2026-08-30.md) | 71 | ✅ | #1199 承接 #1168（PR #1190）的范围外遗留： |
| [issue-triage-dispatch-2026-10-18](./issue-triage-dispatch-2026-10-18.md) | 110 | ✅ | 源：CNB #564。用户拍板四件事——先回流已关的 → 分诊/打标签/写评论 → 派活每轮 3 张、 |
| [mirror-correction-channel-2026-10-11](./mirror-correction-channel-2026-10-11.md) | 83 | ✅ | github_cnb_issues.py 的取舍是「只增不覆盖」——CNB 侧人工调过的正文不会被覆盖，理由正当。 |
| [mirror-false-red-and-divergence-2026-10-11](./mirror-false-red-and-divergence-2026-10-11.md) | 81 | ✅ | 日期：2026-10-11　关联：CNB #118 / #120 / #123　状态：待合入 dev |
| [worktile-migration-map-2026-08-09](./worktile-migration-map-2026-08-09.md) | 122 | 📌 | 导出文件仅 1 个 sheet、10 个字段（标题/编号/状态/优先级/需求分类/需求来源/需求类型/创建人/创建时 |
| [cnb-github-mirror-route-2026-10-11](./cnb-github-mirror-route-2026-10-11.md) | 250 | 📌 | 要。 理由不是「统一好看」，而是三条已经真实付过代价的： |
| [issue-board-audit-2026-10-11](./issue-board-audit-2026-10-11.md) | 97 | 📌 | 这张表里最刺眼的一行是最后一行：仓库这个阶段只关掉过 3 张卡，且都不是「解决了」； |
| [cnb-dev-ahead-rescue-2026-10-11](./cnb-dev-ahead-rescue-2026-10-11.md) | 88 | · | 路线决策文件（cnb-github-mirror-route-2026-10-11.md）给出的是口径：单源 + 两 |
| [divergence-criterion-bifurcation-2026-10-14](./divergence-criterion-bifurcation-2026-10-14.md) | 106 | ◐ | 日期：2026-10-14　关联：CNB #179 / #167 / #171 / #123 / #148　状态：待 |

## 项目管理（15 张）

| 卡片 | 行 | 标记 | 摘要 |
|:---|---:|:---:|---|
| [2026-09-28](./issue-triage/auto/2026-09-28.md) | 98 | ✅ 📌 | - 日期：2026-09-28 |
| [import-page-ux-and-monetization-review-2026-08-15](./import-page-ux-and-monetization-review-2026-08-15.md) | 113 | ✅ 📌 | 这份优化讨论写得不错，但它是在不了解已上线的 OCR 成本护栏与既有付费分层规范的前提下写的。 |
| [2026-09-11](./issue-triage/auto/2026-09-11.md) | 83 | ✅ 📌 | - 日期：2026-09-11 |
| [2026-10-16](./issue-triage/auto/2026-10-16.md) | 111 | ✅ | - 对比基线：本目录下最近一次落盘报告是 2026-09-28.md。⚠️ 流程异常：记忆中记录的 2026-10- |
| [product-roadmap-audit-2026-08-09](./product-roadmap-audit-2026-08-09.md) | 253 | ✅ | - 已有 issue 覆盖、无需新建：#429 导出、#785 同步、#796 XIRR、#588 温度计、#823 |
| [2026-08-14](./issue-triage/auto/2026-08-14.md) | 89 | ◐ 📌 | - 日期：2026-08-14 |
| [2026-09-19](./issue-triage/auto/2026-09-19.md) | 99 | ◐ 📌 | - 日期：2026-09-19 |
| [monetization-strategy-plan-2026-08-15](./monetization-strategy-plan-2026-08-15.md) | 149 | 📌 | 当前没有商业化计划，但开发阶段就要给功能打"付费/免费"标签。驱动这次规划的只有两件事： |
| [triage-report](./issue-triage/triage-report.md) | 113 | 📌 | 1. 文档 ↔ issue 交叉引用：文档和 issue 处于交叉状态时必须互相链接，否则后期无法关联。 |
| [data-refresh-implementation-plan-2026-09-13](./data-refresh-implementation-plan-2026-09-13.md) | 253 | ◐ | 状态：方案设计 + 实施规划（本轮在 v2「待拍板」底稿之上，把 9 项需求转成可落地的设计与 PR 拆分）。 |
| [issue-783-import-checklist-audit-2026-10-15](./issue-783-import-checklist-audit-2026-10-15.md) | 158 | · | 一句话：这张卡已不具备「待办清单」的功能——它的勾选状态不可信、条目大面积被后续产品演进替代或重置，继续挂着只会重复 |
| [issue-870-activation-comment-2026-09-30](./issue-870-activation-comment-2026-09-30.md) | 167 | ◐ | 可直接粘贴到 GitHub。建议同时执行：摘掉 归档 标签 + 粘贴下方正文。 |
| [jigu-migration-to-duoduobei-plan-2026-08-18](./jigu-migration-to-duoduobei-plan-2026-08-18.md) | 171 | ◐ | 你记忆里"找不到的文档"就是 docs/spec/site-architecture-and-traffic-rou |
| [opencode-github-issue-utf8-rule-2026-08-09](./opencode-github-issue-utf8-rule-2026-08-09.md) | 25 | · | - 标题/正文里的中文在提交到 GitHub 之前就已经损坏（GitHub 服务端不会把中文变 ?）。 |
| [roadmap-realign-2026-10-19](./roadmap-realign-2026-10-19.md) | 281 | — 📌 | 失控的不是执行力，是结构。近 30 天关闭 305 个 issue，吞吐非常健康；但 14 个开放里程碑、96 个 open issue、 |

## 命名规范（强制）

- 文件名一律英文 kebab-case + 日期后缀：`{topic}-{YYYY-MM-DD}.md`（如 `deployment-implementation-guide-2026-08-04.md`）。
- **禁止中文文件名 / 中文路径**。历史中文命名（`多多贝_*.md`）已于 2026-08-09 全部重构并删除（原文备份于本机 Temp）。
- 正文标题用中文（如 `# 部署实施指南（2026-08-04）`），文件名只作定位键。
- 交叉引用一律用相对链接 `./{english-name}.md`，不用书名号 / 全中文名。

## 子目录归档

| 目录 | 内容 |
|---|---|
| `legacy/` | Worktile 2021 年看板归档：`legacy/worktile-archive-2021-2026-08-09.md`（晨星爬虫方案、开源金融数据对比、监控组合竞品，及雪球 IRR/XIRR/Modified Dietz 论证全文存档；原始卡片「不适合建 issue 但有长期参考价值」）。原前端重构系列 27 个文件（batches / codebooks / reference / guides）已因**入库前即乱码、不可逆且已被后续实现取代**于 2026-10-11 整批删除（Issue #2042），处置依据见 `legacy/README.md` |
| `issue-triage/` | Issue 看板分拣依据：`triage-report.md`（24 个活跃 issue 分拣报告）、`triage-matrix.csv`（优先级矩阵）。`_tmp_bodies/` 为分拣中间产物，不入库；`auto/` 为按期归档的《Issue 验收清单代码实证复核》系列，**按期入库**（2026-08-14 / 09-11 / 09-19 / 09-28 / 10-16），单期报告是后续复查的对照基线，不应视作临时产物 |
