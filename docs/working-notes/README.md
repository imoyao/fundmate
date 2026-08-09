# 工作记录索引（2026-07-31 ~ 2026-08-09）

本目录归集了各轮会话中产生的工作文档，避免散落于仓库根目录 `docs/`。
本目录经 `docs/.vitepress/config.mjs` 的 `srcExclude: ['working-notes/**']` 屏蔽出文档站构建，**不对外公开**。

## 命名规范（强制）

- 文件名一律英文 kebab-case + 日期后缀：`{topic}-{YYYY-MM-DD}.md`（如 `deployment-implementation-guide-2026-08-04.md`）。
- **禁止中文文件名 / 中文路径**。历史中文命名（`多倍贝_*.md`）已于 2026-08-09 全部重构并删除（原文备份于本机 Temp）。
- 正文标题用中文（如 `# 部署实施指南（2026-08-04）`），文件名只作定位键。
- 交叉引用一律用相对链接 `./{english-name}.md`，不用书名号 / 全中文名。

## 数据源 / 抓取系列（2026-08-03）

| 文件 | 内容 |
|---|---|
| `external-datasource-reference-2026-08-03.md` | **端点清单 SSOT**：全部外部数据源 host/端点/参数/Token/实时状态（东财 push2/push2his、腾讯 gtimg、xalpha、集思录、且慢、有知有行、韭圈儿、akshare 宏观、Supabase Auth、Playwright） |
| `datasource-priority-plan-2026-08-03.md` | 通用数据源优先级方案（防依赖腐烂）：诊断树、Tier0-3 优先级分层、能力→Provider 矩阵、wrapper→上游映射、熔断/缓存机制；配套代码沙箱 `DataSourceRouter` 已实跑验证 |
| `bias-datasource-replacement-2026-08-03.md` | 乖离度数据源替换方案（借鉴 daily_stock_analysis）：绕过 akshare 直连腾讯/东财，含实测结果与可粘贴代码 |
| `eastmoney-antiscrape-2026-08-05.md` | 东财反爬：akshare 腐烂 / 大智慧 中转，行情数据链路修复 |

## 后端架构 / 部署系列（2026-08-03 ~ 2026-08-04）

| 文件 | 内容 |
|---|---|
| `backend-hosting-fetch-selection-2026-08-03.md` | 后端托管与 fetch 落点选型：腾讯云 SCF / EdgeOne / Oracle 免费 VM 对比，推荐栈 = SCF Web 函数 + EdgeOne Pages |
| `scheduling-options-research-2026-08-04.md` | 定时调度方案调研：调度与计算解耦原则、APScheduler / GitHub Actions / Supabase Edge cron 对比、EdgeOne 无原生 cron 的触发框架 |
| `deployment-implementation-guide-2026-08-04.md` | 部署实施指南（确定性方案）：前端 EdgeOne Pages + 后端 SCF Web 函数 + SCF 原生定时触发器，含 scf_bootstrap / serverless.yml / 官方定价复核 |
| `tech-baseline-roadmap-2026-08-04.md` | 技术基线与路线图：技术栈、领域分层、已实现/进行中/远期路线、技术债清单（按严重性排序） |
| `db-cost-decision-2026-08-04.md` | 其余项目评估与数据库成本决策（市场验证中）：腾讯云 PG vs Supabase 免费档 |
| `doc-code-discrepancy-2026-08-03.md` | 文档与代码误差追踪（会议纪要）：9 条误差表 + 决策 + 待办 |

## 前端 / 产品系列（2026-08-03 ~ 2026-08-04）

| 文件 | 内容 |
|---|---|
| `frontend-architecture-mobile-eval-2026-08-04.md` | 前端架构与移动端评估（未来可选方案）：Vant / uni-app / RN 对比与迁移成本 |
| `fundfof-borrowing-analysis-2026-08-03.md` | fundfof 功能借鉴分析（v3 源码复核版）：源码已实现能力清单、真实问题（mock 分析页 / 无回撤计算 / 多用户隔离）、值得借鉴功能 |
| `brand-landing-plan-2026-08-04.md` | 品牌与落地页规划：命名、slogan、品牌色（珊瑚红 #E34F38）、logo 执行、落地页结构、公开路线图 |
| `landing-login-sso-2026-08-04.md` | 落地页登录与 SSO 设计决策（MVP）：只做跳板、不做 SSO、落地页与工具站不共享登录态 |

## 其它记录

| 文件 | 内容 |
|---|---|
| `code-audit-and-remediation-2026-08-01.md` | 合并的 6 份代码审计与架构整改记录：① 代码问题审查（初版 2026-07-31）② 代码问题审查（深化版 2026-08-01）③ V1（`backend/fundmate/`）退役清除分析 ④ `data/` 接口可用性评估 ⑤ `libs/cal` 与测试目录瘦身 ⑥ FastAPI 解耦规划 |
| `erniao-fetcher-redesign-2026-08-01.md` | 二鸟说手抄报 自动维护（v2.0）：fetcher 重构设计 |
| `build-oom-fix-2026-08-04.md` | 前端 Build OOM 修复：构建内存参数 |
| `industry-crowding-baostock-fallback-2026-08-07.md` | 行业拥挤度 baostock 兜底实现方案 |
| `industry-crowding-multidim-2026-08-08.md` | 行业拥挤度多维方案设计 |
| `supabase-jwks-es256-verification-2026-08-08.md` | Supabase JWT 验签改造为 JWKS+ES256（HS256 已失效）；含 3 条踩坑教训 |
| `brandsub-beta-pending-2026-08-08.md` | **悬挂问题**：SidebarLogo/NavHorizontal 的 brand-sub/beta 改动被误删，待重建（有完整 diff 可恢复） |
| `explore-watchlist-replan-2026-08-08.md` | 探市 / 自选 页重新规划 |
| `db-download-import-2026-08-09.md` | DB 下载与导入规划 |
| `free-cloud-services-2026-08-09.md` | 免费产品清单 |
| `launch-plan-2026-08-09.md` | 上线计划（含动态 静态 / Turso 双数据源 / 日志追踪选型） |
| `feedlog-setup-cn-2026-08-09.md` | FeedLog (dbb-feedback) 中文环境初始化指南：Cloudflare Workers + R2 + Hyperdrive 部署全流程，含环境变量/品牌定制/AI配置 |
| `opencode-github-issue-utf8-rule-2026-08-09.md` | OpenCode/GitHub Issue 创建 UTF-8 环境规则（复盘 #859-#862 乱码事故） |
| `money-fund-income-plan-2026-08-09.md` | 货基收益入账方案设计 |
