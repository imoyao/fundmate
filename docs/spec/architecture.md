---
title: 架构与技术设计（architecture）
---

# 架构与技术设计（architecture）

本文件收录项目概述、第三方数据适配层、高级能力设计、暗色模式规划与断点续传协议，属于**中频变更**的架构类事实标准。

## 1. 项目概述（原 SPEC 第 1 章）

### 1.1 项目愿景

为个人投资者提供一个安全、可长期维护的全资产记账与投资分析工具，标准化解决两大核心问题：「我的全部资产分布在哪里」「我的投资收益与行为如何复盘优化」。区别于普通记账工具，本项目主打**数据分级主权、投资分析专业、全资产全覆盖**。

> **存储架构（2026-08-18 定稿）**：本项目**架构必须上云**——核心账本（用户域）生产落 Supabase（云端权威 + 本地缓存），市场数据（市场域）生产落 Turso。「永不上云」的旧承诺已取消（D3，2026-08-07 修订）。详见 `docs/dev/db-data-domain.md`。合规红线仍为：严禁用户券商/平台持仓自动登录/爬取/同步、不荐股不跟单不预测。

### 1.2 核心价值主张

- **数据分级主权（D3 修订“绝对不上云”为按域拆分上云）**：按数据域拆分存储——**市场域（market）**承载公开、读多写少、会无限膨胀的市场数据（净值/行情/温度/基金基础资料/基金管理人/同步日志），生产落 Turso（开发期用本地 SQLite 替身）；**用户域（user）**承载含 `family_id`/`user_id` 的核心账本（账户/持仓/交易/组合/自选/家庭/用户/销售机构/用户操作审计），生产落 Supabase（云端权威 + 本地缓存），须用户显式授权、可一键关闭。两域**跨库零外键、零 SQL join**，用户表仅以 `symbol`/`fund_code` 字符串冗余键引用市场表。**本地开发默认单库**（market 与 user 同落 `invest.db`，零网络依赖）；需验证域边界时显式配 `DEV_USER_DATABASE_URL` 才拆双 SQLite 模拟（`invest.db` + `invest.user.dev.db`）；配 `SUPABASE_DATABASE_URL` 才走真 Supabase。权威设计见 `docs/dev/db-data-domain.md`（2026-08-18）。红线不变：**严禁用户券商/平台持仓自动登录/爬取/同步**。
- **绝对合规性**：仅支持手动逐条录入、标准 CSV/JSON 文件导入，全程无自动登录券商、无爬虫抓包、无接口窃取数据等违规行为，完全合规
- **记账+分析闭环**：不止流水记录，支持基金持仓穿透、组合年化计算、收益复盘、风险集中度分析、配置目标优化，形成投资闭环
- **全资产统一管理**：统一覆盖股票、基金、ETF 交易资产，同时兼容现金、固收、房产、保险、应收、负债等广义资产，真正做到「一张表看全身家」

### 1.3 技术栈规范

- **后端**：Python 3.12+、APIFlask、SQLAlchemy 2.0 原生 ORM、SQLite（本地开发）。统一手动返回 `{data, message}` 结构，不依赖自动范式，为未来平滑迁移 FastAPI 预留架构空间
- **前端**：Vue3 + Vite + TypeScript、pure-admin-thin 骨架、Element Plus 组件库、ECharts 可视化
- **代码质量规范**：后端 ruff 静态校验，前端严格遵循 pure-admin 官方编码与目录规范
- **数据源体系**：xalpha（主力基金净值/分析引擎）+ AKShare（证券行情备用），通过统一 DataSourceAdapter 防腐层封装，隔离第三方接口变更

## 2. 第三方数据适配层（原 SPEC 第 6 章 · 原"第三方集成架构（xalpha 完整边界定义）"）

> 原章节标题偏窄（仅提 xalpha）。当前代码已实现 **`xalpha_adapter.py` 与 `akshare_adapter.py` 双适配器**，统一经 `DataSourceAdapter` 防腐层封装，因此本章更名为「第三方数据适配层」，覆盖全部第三方数据源。**实现位置**：`backend/app/services/adapters/`（xalpha / akshare / 东财直连 / 韭圈儿 / 各投顾平台）——它是跨家族共享的独立层，**不属任何 job 家族**（#1607 批次 3 从 `services/sync/adapters/` 上提；决策见 `decisions.md` D26）。

- **职责边界**：仅负责外部数据获取、净值解析、组合数学计算，不参与业务入库、不参与前端交互、不参与权限逻辑
- **缓存策略**：独立文件夹本地缓存，与业务数据库物理隔离，可手动清理（xalpha 使用 `xa.set_backend("csv", path="data/xalpha_cache")` 启用）
- **调用方式**：全部通过后端 adapter 层统一封装，业务层不直接裸调用第三方库
- **容错策略**：失败重试、超时处理、数据异常兜底，保证系统稳定性

## 3. 高级能力设计细节（原 SPEC 第 7 章）

### 3.1 持仓穿透冷热分层设计

热数据（持仓+流水）实时读写；温数据（穿透明细）定时缓存、过期刷新；冷数据（历史行情）归档存储，平衡速度、性能、时效性。

### 3.2 旧项目架构继承说明

完整继承 fundmate 核心设计：枚举体系、基金经理多对多、自选体系、费率体系思想，重构后架构更干净、可扩展、无历史技术债。

### 3.3 元数据同步系统设计

#### 3.3.1 分层更新策略

同步目标按优先级分为三层：

1. **核心池**（每日更新）：用户持仓 + 自选标的
2. **CSV 导入池**：通过 `--target-file` 参数指定
3. **全量池**：`--full-sync` 时触发全市场同步

#### 3.3.2 基类重构（v2.0）

`SyncJob` 基类统一流程：

- `run(full_sync, targets)` 不再被子类覆盖。
- 分批逻辑内置，子类只需设置 `batch_size`。
- 空数据保护通过 `_allow_empty_data` 控制。
- 目标代码由 `DataSyncOrchestrator.resolve_targets()` 统一解析后注入。

#### 3.3.3 静默历史数据回填

用户新增持仓或自选标的时，后台异步回填该标的的全部历史净值/行情。使用 `threading.Thread` 实现，不阻塞前端请求，失败静默处理。

**T 日不回填边界（#824）**：回填范围止于 **T-1**，不写入当日（上海时区 `today_shanghai()`）未收盘、未定稿的净值/行情。原因：盘中数据未定，回填进去用户会看到不完整/变动中的数据而困惑。

- 实现位置：`backend/app/services/async_backfill.py` 的 `_drop_today()`，在 `_backfill_fund_nav`（按 `date`）与 `_backfill_stock_price`（按 `trade_date`）插入前丢弃 `日期 >= 今日` 的记录。
- 适配器若本身只返回已定稿数据，该过滤为防御性冗余，不改变既有行为。
- 适用范围：**导入历史交易触发的按需回填** 与 **自选/持仓新增触发的回填** 共用同一边界（导入器与回填共用）。

#### 3.3.4 基金详情补充任务

`FundDetailEnrichJob` 负责补充核心池基金的分类、公司、风险等级、成立日期、业绩基准、拼音简拼、费率规则等静态信息。数据源：`ak.fund_info_ths`（详情） + `xalpha.fundinfo`（费率）。

#### 3.3.5 人类可读同步摘要

每次同步完成后，输出自然语言格式的摘要报告，包含：各任务成功/失败状态、新增/跳过记录数、失败原因。

### 3.4 乖离度模块设计细节（新增，v4.5.9）

**模块位置**：`backend/app/services/bias/`

| 文件 | 职责 |
|------|------|
| `constants.py` | 申万一级行业代码映射（31 个）、计算参数（EMA 周期 20 天）、阈值（±5/±15） |
| `schemas.py` | Pydantic 模型（`BiasResult`, `BiasBatchResult`） |
| `calculator.py` | 核心计算逻辑（`logbias` 纯函数、`PriceFetcher`、`BiasCalculator`），含重试+指数退避 |
| `provider.py` | 品种列表提供者（行业列表、宽基指数、用户持仓/自选） |
| `job.py` | 调度适配器（被 `TemperatureJob` 调用） |

**数据流**：

```plain
BiasJob._fetch_data()
  → ProductProvider.get_default_list()  (行业 + 宽基)
  → BiasCalculator.calculate_batch()
  → 转换为 market_multi_items 存储格式
  → TemperatureService.save_multi_items()
  → 写入 market_multi_items 表 (source='bias')
```

**计算频率**：午间（12:00）一次 + 盘后（15:30）一次

**数据保留**：30 天

## 4. 暗色模式规划（原 SPEC 第 11 章）

> 多多贝 暗色模式采用独立的设计规范（详见 [`../../frontend/design.dark.md`](../../frontend/design.dark.md)），核心方向：
>
> - 背景使用深灰层级（非纯黑）
> - 品牌色饱和度降低 20%，避免在暗色背景下“震动”
> - 涨跌颜色通过 `--color-rise`/`--color-fall` 变量自动切换，业务代码零修改
> - 层次感通过“边框提亮 + 内阴影”实现，替代传统投影

### 4.1 编码预埋约束

- 所有业务代码必须通过 `--color-rise` / `--color-fall` 引用涨跌色，禁止直接使用 `--brand-*`
- 暗色模式切换时仅需更新 CSS 变量值，业务代码无需任何改动
- 品牌色的饱和度降低和涨跌色的提亮，建议通过 CSS 自定义属性（HSL 色值）动态计算，而非硬编码独立色值
- 完整暗色模式设计规范参见 [`../../frontend/design.dark.md`](../../frontend/design.dark.md)

## 5. 断点续传协议（原 SPEC 第 13 章）

后续任何会话接续开发，只需携带：

1. 本规范体系（docs/spec/，v4.5.9）
2. 当前进度一句话
3. 核心文件清单
4. 最新的报错截图或要解决的具体问题

> **UI/UX 设计规范索引**：完整视觉设计语言请参阅 [`../../frontend/design.md`](../../frontend/design.md)（亮色模式 v2.3.2）和 [`../../frontend/design.dark.md`](../../frontend/design.dark.md)（暗色模式 v1.4）。本体系仅记录与业务/技术架构有交集的强制决策。

## 6. 后端分层与依赖方向（2026-09-19 定稿，#1607）

> 决策原文见 [`decisions.md`](./decisions.md) 2026-09-19 行（D24）；本节只记**应然状态**，改动须先动决策。

```
core  ←  domains.<域>.models / schemas  ←  services  ←  domains.<域>.views
```

- **core**（DB / money / auth / 异常 / 补丁 / 缓存 / 迁移）：业务无关的基础设施层，**零** `app.domains.*` / `app.models.*` 引用；
  需要领域能力时由组合根（`app/main.py` 的 `create_app()`）**注入**——先例是 `register_user_identity()`
  注入 `domains/users/identity.py::UserIdentity`（鉴权中间件只持实现对象，不持 `User` 模型），
  未注入时显式报错而非静默降级。
- **domains.\*.models / schemas**：叶子层，只依赖 core；不得依赖 services，不得引用其它域的 views。
- **services**：业务服务层，依赖 core 与 `domains.*.models/schemas`；**不得** import `domains.*.views`。
  *services 内部方向（#1607 批次 2 / 3）*：**编排 / 注册类**模块（`sync/orchestrator`、`thermometer/jobs`、
  `importer/orchestrator*`）可依赖其它领域的服务与 job；**领域服务**（`fund_service` / `position_service` /
  `pnl_service` / `watchlist_service` 等）**不得反向依赖编排层**。跨家族**共享件一律放 `services/` 顶层**
  （现为 `job_base.py`（`SyncJob` 基类）、`adapters/`（第三方数据适配层）、`import_records.py`（导入标准化
  记录）），家族包内只留该家族独有实现——共享件若是**叶子**（不得反向依赖家族包），否则又会"寄生"
  （守卫 R5 固定；**#1607 批次 4 后零例外**：且慢取数已上提到 `adapters/qieman_fetcher.py`，见 D31）。
  **R6 已机器化**（#1607 批次 5，D32）：**领域服务**（模块名 `*_service` / `service`，即 `fund_service` /
  `position_service` / `pnl_service` / `watchlist_service` 那一类）→ 编排 / 注册层
  （`sync.orchestrator` / `thermometer.jobs` / `importer.orchestrator*` / `daily_scheduler`）一律红灯；
  **job / scheduler 属编排侧**（由 orchestrator 注册与调用），可依赖编排层与其它领域的服务。
- **domains.\*.views**：HTTP 编排层，依赖 services 与各域 models/schemas；**跨域不得引用对方 views**
  （共用逻辑下沉 services，先例：`services/position_presenter.py::enrich_position_dict`）。
- **模型位置**：业务模型一律 `domains/*/models.py`；**跨域 / 系统级模型**（现仅 `app/models/sync_log.py`，
  同步审计，直属 `DOMAIN_MARKET` 但不属任何业务域）放 `app/models/`，属**被承认的第二类**而非「例外」。
- **建表 / 种子边界**：`core.database.init_db()` 只建「调用方已 import 的模型」的表，不代为导入顶层模型、
  不写业务数据；默认家庭 1 / 默认用户 1 的播种在 `domains/users/seed.py`，由组合根在建表后调用
  （绕过应用工厂的 CLI 入口需要身份行时自行调用）。
- **守卫**：`scripts/guard_layer_direction.py`（pre-commit + CI 的 backend job）——六类非法边 R1 core→domains /
  R2 services→`domains.*.views` / R3 `domains.*.{models,schemas}`→services / R4 跨域 views 互引 /
  R5 `services/` 顶层共享件→家族包（**冻结基线 0 条**，批次 4 清零）/ R6 领域服务→编排注册层（批次 5）；
  配套 `tests/core/test_layer_direction.py`（逐规则灵敏度 + 合法边反向保护 + 冻结基线边界）。
  判据用「**边方向**」而不是「包级双向依赖对数量」——包级双向对多数由 `views→services` 与
  `services→models` 两条**合法边**叠加而成（如 `domains.positions` ↔ `services.position_service`），不构成违规。

### 6.1 视图层判据（#1606 批次 1）

`domains/*/views.py` 的职责边界（决策见 `decisions.md` 2026-09-19 行 D26）：

| 项 | 判据 | 落地 |
|---|---|---|
| **允许** | 解析入参 / 归属校验 / 调用 services / 组织 `{data, message}` / 常量级展示映射 | — |
| **禁止** | 视图内业务规则（校验链、状态机、去重合并策略、守恒校验、跨资源编排）；用 `db.query` 做聚合统计；跨域 import 其它域的 views | 基线冻结，新增即红 |
| **事务** | 同一视图函数内最多一次显式 `commit()`；多步写入整体成功或整体回滚 | 同上 |
| **规模** | 单函数 ≤ 60 行；视图文件行数 / DB 调用数**只减不增** | `scripts/check_view_thickness.py`（pre-commit + CI backend job） |

存量超标**按批次收敛**（不一次性推平：131 个端点批量改写风险大于收益），先立边界、堵新增。
批次 1 已落地：`ledgers` 账户迁移域 → `services/ledger_migration_service.py`；
`watchlist` 展示增强 → `services/watchlist_display.py`（与 `watchlist_service` 的查询/写入/状态机分层）。
后续批次候选：`ledgers` 余下视图内业务规则（活期+ 绑定换绑、改名快照刷新、类型变更校验）、
`positions` / `funds` 等同类文件。
