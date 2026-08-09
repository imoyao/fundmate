# 技术基线与路线图（2026-08-04）

> 性质：内部备忘（`docs/working-notes/` 屏蔽出构建，不对外）。
> 合并自：技术基线与路线图 v0.4（含 v0.1/v0.2 的历史决策点）、技术债清单 v0.1（本地盘点）。
> 日期：2026-08-04
> 关联：部署方案见 [deployment-implementation-guide-2026-08-04](./deployment-implementation-guide-2026-08-04.md)；后端托管与 fetch 落点见 [backend-hosting-fetch-selection-2026-08-03](./backend-hosting-fetch-selection-2026-08-03.md)；外部数据源见 [external-datasource-reference-2026-08-03](./external-datasource-reference-2026-08-03.md)。

---

## 0. 技术栈基线（已锁定）

| 层 | 选型 | 说明 |
|---|---|---|
| 前端 | Vue 3 + Vite + TS + Element Plus | pure-admin 模板；Vue 3 + Pinia + vue-router |
| 后端 | Python 3.12 + APIFlask（Flask 子类） | 分层 core / domains / services / tools；OpenAPI 自动 |
| 数据库 | SQLite 本地 + Supabase（Postgres）同步 | 身份认证 / 家庭核心账本走 Supabase 云端权威 + 本地 SQLite 缓存（D3 修订，RLS 兜底，可一键关闭） |
| 认证 | Supabase Auth（JWT） | 后端验签 + 白名单鉴权；user_preferences 按 user_id 私有 |
| 部署 | 前端 EdgeOne Pages（静态）；后端 腾讯云 SCF Web 函数（Python） | 免费 + 不备案 + 对华友好出口；详见 [deployment-implementation-guide-2026-08-04](./deployment-implementation-guide-2026-08-04.md) |
| 依赖管理 | 后端 PDM；前端 pnpm | 仓库根与 frontend 各独立 package.json + lock |

---

## 1. 后端领域分层（V2，backend/app）

- 每域一个 APIBlueprint，路由在 views.py：
  - `assets` / `transactions` / `positions` / `watchlist` / `funds` / `securities` / `summary` / `performance`（XIRR）/ `strategy` / `importer`（CSV/PDF 解析）/ `thermometer`（探市，免登录）
- core：`database.py`（SQLite+WAL）、`money.py`（金额/份额单位换算唯一入口）、`auth.py`（Supabase JWT 验签+白名单）、`exceptions.py`（SBException+统一错误信封）
- services：`sync/`（jobs+adapters，xalpha/akshare 双适配器）、`bias/`（乖离度）、`importer/`、`performance/`
- 同步入口两套、同一 `DataSyncOrchestrator`：`pdm run invoke grab.*` 走 `app/tools/sync_cli.py`；`pdm run sync --job <name>` 走 `app/tools/sync_metadata.py`

## 2. 前端技术基线（Vue 3 + pure-admin）

- 设计语言：`frontend/design.md`（亮色）与 `design.dark.md`（暗色）；`style/colors.css` 品牌色规范 v2.1（低饱和莫兰迪+暖调，主色珊瑚 #E34F38，涨红跌绿）
- 接口按域集中在 `src/api/*.ts`；公共类型在 `src/api/types.d.ts`
- 动态路由：`import.meta.glob("/src/views/**/*")` 自动生成；组件 `defineOptions.name` 须与路由 name 一致
- 请求统一走 `src/api`，组件内禁裸 axios；列表增删改成功后须清空列表缓存

---

## 3. 路线图

### 3.1 已实现（V2 基线）

- 统一资产模型（Transaction/Position/Security/Fund/Asset/Ledger/Portfolio）；多账户聚合（Ledger+summary）
- 全交易类型（buy/sell/dividend/deposit/withdraw）；XIRR 年化收益（performance 域，真实计算）
- 自选+异动提醒+清仓复盘（watchlist）；基金元数据+净值+费率（funds+xalpha）；证券行情（price_history）
- 市场温度（thermometer：且慢/有知有行/韭圈儿/集思录，模型层已建、待数据管线填充）
- 手动记账+CSV/PDF 导入（importers）；探市/health 免登录

### 3.2 进行中 / 已排期

- 市场温度采集 jobs（fetchers 已写好，缺落库 job 与调度）→ 见 [scheduling-options-research-2026-08-04](./scheduling-options-research-2026-08-04.md)
- 券商交割单导入（品牌规划 §9 公开路线图"在做"）
- 乖离度 akshare 绕过直连上游（修复完成，见 [bias-datasource-replacement-2026-08-03](./bias-datasource-replacement-2026-08-03.md)）
- 后端部署到 SCF（见 [deployment-implementation-guide-2026-08-04](./deployment-implementation-guide-2026-08-04.md)）

### 3.3 待排期 / 远期（不公开路线图）

- AI 辅助：复盘/归因/异动提醒/目标进度（不做"替你买卖决策"）
- 美股/港股/加密/房产扩展；移动端打磨（见 [frontend-architecture-mobile-eval-2026-08-04](./frontend-architecture-mobile-eval-2026-08-04.md)）
- 市场温度每日推送（微信）；真实指标接入 mock 分析页（见 [fundfof-borrowing-analysis-2026-08-03](./fundfof-borrowing-analysis-2026-08-03.md)）

---

## 4. 技术债清单（v0.1 本地盘点，按严重性排序）

| 级别 | 债 | 说明 / 修复路径 |
|---|---|---|
| 高 | 两个分析页为硬编码 mock（InvestmentAnalysis / IntelligentAnalysis） | 数字全写死（回撤-8.2%、夏普1.2、收益¥2,580,000），未接 API；易误导演示与进度判断。路径：先接真实数据（见 fundfof-borrowing-analysis P0）或先标注"示例数据" |
| 高 | 回撤/波动/Sharpe/相关性未实现 | performance 服务只有 XIRR；全仓 grep 仅测试 fixture/README 命中。路径：新增 analytics 服务（基于 price_history.adj_close + transactions） |
| 高 | 多用户隔离未落实 | `Asset.user_id = Column(Integer, default=1)`，无 users 表外键、未见 row 级隔离；若接真实多用户存在跨用户泄露风险。路径：确认 Supabase RLS / 应用层隔离兜底 |
| 中 | 市场温度是空模型 | temperature 三表已建但缺定时采集+入库；前端无数据可展示。路径：补 jobs+调度（scheduling-options-research §三） |
| 中 | 持仓成本复权口径待验 | Position.avg_price/quantity 混用；配股/拆细会改 quantity 与成本，需验证 PositionService 复权正确性 |
| 中 | 后端 V1（backend/fundmate）退役后遗留引用 | 2026-08-01 已退役，禁止新增 backend.fundmate 引用；守卫脚本 scripts/forbid_v1_refs.sh |
| 低 | 全局依赖 akshare 的脆弱点 | 行情日线/基金元数据/宏观估值多函数经 akshare 包装，单函数断更即拖垮。路径：逐个直连上游+重试+熔断（external-datasource-reference §三.3） |
| 低 | 命名/文档规范遗留 | 本批 docs/working-notes 中文文件名历史债已清除（本任务），此后统一英文 kebab-case+日期后缀 |
| 低 | --color-primary #7A7FA8 遗留 | 仅向后兼容的冷紫蓝主色，建议迁到珊瑚（brand-landing-plan §4） |

---

## 5. 架构决策记录

- 前端 SPA + 后端 REST（API-First 契约冻结）；探市与 health 免登录、其余需登录（白名单+requiresAuth 双轨一致）
- 精度：金额整数分、份额×10000、净值 DECIMAL(18,6)，换算唯一入口 core/money.py 的 Money
- 资产正负：用户录正数，后端按大类自动转换，接口输出 signed_amount 唯一计算字段
- 同步：DataSyncOrchestrator 统一编排，jobs+adapters 分离，xalpha/akshare 双适配器

---

## 6. 边界

- **事实**：以上均来自本仓库代码与已冻结决策；技术栈基线、领域分层、已实现项均有源码可查。
- **推断**：SCF 部署、温度调度、mock 接入等"进行中"项的可行性已由配套调研文档论证（部署/调度/数据源系列）。
- **未知**：SCF 免费额度与区域可用性实况；温度采集各外部源长期稳定性；多用户上线时间点。
