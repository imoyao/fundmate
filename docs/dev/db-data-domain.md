# 多引擎数据域约束（DB Data Domain）

> **本文是 fundmate 数据库架构的【唯一权威事实标准】（v1，2026-08-18）。** 设计已定稿并落地代码护栏（分支 `feature/db-multi-engine`），不污染 `main-v2` 运行路径。任何新表设计 / 查询编写前以本文为准。
> 配套硬约束摘要见仓库根 `AGENTS.md` 的「多引擎数据域约束」节。
> **单库 / 双库统一可用**：默认单库——本地未显式配置独立 user 库（`DEV_USER_DATABASE_URL` / `SUPABASE_DATABASE_URL`）时，user 域与 market 域共用同一本地 SQLite，既有数据零迁移；显式配置后才拆双库（本地模拟或真库），业务代码零改动。详见第 9 节。
> **历史文档关系**：`docs/backend-restructure-edgeone-dualengine.md` 是 2026-08-01 的**早期计划**（含"双 Base 拆分"设想），与本文实际落地方案有偏差，仅供参考决策背景，不反映当前代码；差异见第 10 节。`docs/dev/db-choice.md` 是 V1 MySQL 选型历史，已标失效。

## 1. 为什么是混合库，而不是单库或主从

演进目标：本地 SQLite → **Turso（市场域）+ Supabase（用户域）+ Neon（灾备，延后）**。

动机（用户拍板的核心）：

- **存储成本**：历史净值 / 行情 / 温度这类数据随「全市场标的数量 × 时间」无限膨胀。仅基金净值一项，1 万只基金 × 250 交易日 ≈ 250 万行/年，5 年约 1–2 GB；加上货币基金、股票/ETF 行情，5 年可达数 GB 甚至上亿行。**Supabase 免费额度（500 MB）装不下**，且这种纯公开读多写少的数据放 Turso 按量计费更便宜。
- **隐私边界**：用户账本（账户/持仓/交易/组合/自选关系）含隐私，应落在 Supabase，可享其 RLS 行级安全与 auth 体系；Turso 没有用户级权限，不适合放隐私数据。
- **不是主从/缓存关系**：市场域与用户域是**按数据域垂直切分、各自独立**，域间不允许 SQL join。Supabase 是用户数据权威（非 Turso 的副本），Neon 仅作灾备替身。

## 2. 两个运行库（engine）的语义

| 域 | 引擎（生产） | 开发期默认（未配云） | 配云后 |
|----|------|-----------|------|
| `market` | Turso（libsql） | 本地 SQLite（`invest.dev.db`） | Turso（设 `TURSO_DATABASE_URL` / `DATABASE_URL`） |
| `user` | Supabase（Postgres） | 本地 SQLite（**默认与 market 同库**；显式设 `DEV_USER_DATABASE_URL` 才独立 `invest.user.dev.db`） | Supabase（设 `SUPABASE_DATABASE_URL`） |

> **单库 / 双库统一可用（核心）**：本地 development 默认「单库」——未显式配置独立 user 库时，user 域与 market 域共用同一本地 SQLite（缺省 `invest.dev.db`，本地常经 `DEV_DATABASE_URL` 指向既有 `invest.db`），本地数据零迁移、开箱即用。只有显式配置 `DEV_USER_DATABASE_URL`（本地双库模拟）或 `SUPABASE_DATABASE_URL`（真库）才拆分。生产期把该变量换成 prod 连接串即可，业务代码零改动（ORM 不关心 Supabase 还是 Neon 的 PG）。
> 因此**不是「必须用双库真实连接」**——本地默认单 SQLite，需要验证域边界 / 跨域工具时用双 SQLite 模拟，仅在最终验证 / 生产才接真云库。

## 3. 表 → 域归属清单（基于真实代码，2026-08-18 盘点）

### `market` 域（Turso）

| 模型 / 表 | 说明 | 体积特征 |
|-----------|------|---------|
| `funds` | 基金基础资料（net_value / 成立日 / 类型等） | 恒定，几千~1 万行 |
| `price_history` | 历史行情（逻辑外键 `fund_code` → funds） | **最大表**，随标的数×时间膨胀 |
| `daily_index` | 指数日线 | 中等，按指数×日期 |
| `securities` | 证券基础资料 | 恒定，几万行 |
| `temperature`（market_single_values / market_composites / market_multi_items） | 全市场温度 | 按 source+日期，可控 |
| `securities_fund_flow` | 资金流 | 中等 |
| `FundManager` / `Manager`（基金管理人，**独立表**） | 被 `funds` 外键引用 | 恒定小表（已确认独立表，放 market 域） |
| `sync_logs`（系统同步审计） | 记录市场/备份同步任务执行情况 | 超小量（每日几次任务），统一放 Turso，随市场同步任务 |
| `advisor_portfolios` / `advisor_holdings` / `advisor_industry_allocs` / `advisor_adjust_histories` | 投顾组合公开参照与持仓/行业/调仓明细（#1167；2026-09-08 补登记，此前文档漂移） | 参照小表，明细随组合数增长 |
| `index_constituents` | 指数成分股（#1358 / #1286；2026-09-08 补登记） | 按指数×成分，覆盖式更新 |
| `index_catalog` | 指数名录（#1286 聚合搜索底座） | 恒定，千级，覆盖式重建 |

> **2026-09-08 注**：完整表清单以 `backend/app/core/db_factory.py` 的 `DATA_DOMAIN_REGISTRY` 为唯一权威（启动校验兜底）；本节为人工盘点快照，新增表时须同步更新（AGENTS.md 双库硬规则 §1）。

### `user` 域（Supabase）

| 模型 / 表 | 说明 | 体积特征 |
|-----------|------|---------|
| `families` | 家庭 | 几十~几千行 |
| `users`（含 `supabase_id`） | 用户 / auth 边界 | 几十~几千行 |
| `ledgers` | 账户（FK → portfolios / sales_institutions） | 增长慢 |
| `portfolios` | 组合 | 增长慢 |
| `positions` | 持仓（存 `symbol`/`fund_code` 字符串冗余键，**非** FK） | 增长慢 |
| `transactions` | 交易（存 `symbol` 快照） | 增长慢 |
| `watchlist`（含 watchlist_groups / item_group / tag_defs / item_tags / alerts / cleared_positions） | **用户自选关系**（非种子清单） | 按用户数×关注数增长，不受美股/港股扩展影响 |
| `strategy`（strategy_tags / position_strategy_tags） | 策略标签 | 轻量 |
| `summary`（asset_snapshots） | 资产快照（family_id 隔离） | 中等 |
| `usage`（user_usage） | 用量统计 | 轻量 |
| `sales_institutions`（销售机构，AMAC 名录） | **被 `ledgers` 外键引用** | 恒定小表（几百~两千行），随 user 域走，避免反向跨域 FK |
| **用户操作审计表**（规划中） | 记录用户在 App 内的写操作（谁/何时/改了哪条/改前改后） | 含 `user_id`，按用户数×操作频率增长；放 user 域，享 RLS，且与原操作同引擎可同事务 |

### 跨域关联键约定（冗余，非外键）

- `positions.fund_code` / `transactions.symbol` / `watchlist.symbol` 只存**字符串冗余键**，指向 market 域的 `funds`/`securities`。market 域为权威来源。
- `sales_institutions` 在 user 域，被 `ledgers` 真实外键引用（同域，合法）。
- `FundManager` 在 market 域，被 `funds` 真实外键引用（同域，合法）。

### 边界画在哪（两个关键例外，已在文档单列）

- **销售机构**：虽是公开小名录，但被 `ledgers`（user 域）外键引用 → 随 user 域走。原因：避免出现「用户表 FK 指向 market 库」的反向跨域引用。
- **基金管理人**：虽是公开小名录，但被 `funds`（market 域）外键引用 → 随 market 域走。原因：与 `funds` 自包含，域内引用合法。
- **自选种子清单 vs 用户自选关系**：全市场可订阅标的（种子）在 `funds`/`securities`（market 域）；用户「我关注了哪只」的关系在 `watchlist`（user 域）。两者不是同一张表。

## 4. 跨域读取最佳实践（应用层两步法）

禁止 SQL join（两域是独立引擎）。需要「我的自选 + 它的净值」这类联合视图时：

```
1. 在 user 域取用户自选的 fund_code 列表（一次轻量查询）
2. 用 in_([...]) 批量去 market 域取净值/行情（一次批量查询）
3. 在应用层按 fund_code 拼装成视图
```

- 此拼接逻辑**必须集中到统一 service 方法**，禁止每个 service 手写（防 N+1、防写错域）。
- 跨域冗余键的取值以 market 域为准；user 域写入自选时如要校验 fund_code 是否存在，放应用层（或异步对账），**不靠 FK**。

## 5. 护栏要求（代码层，消除「容易写错/读错库」）

1. **每个模型加 `__data_domain__` 类属性**（`'market'` / `'user'`）。未声明不允许合并；`init_db` 启动期断言所有表都已声明。
2. **`init_db` 按域分别 `create_all` 到对应 engine**，并启动断言「声明域 == 实际建到的 engine」，不一致直接 fail（防表建错库导致静默错误）。
3. **Session 入口只有 `market_session()` / `user_session()`**，service 层只能从这两个取会话，禁止混用。
4. **开发期迁移点**：本地 SQLite 文件当前已含全部 30 张表（含本该去 Supabase 的用户表）。迁双库后 SQLite 只建 `market` 域表，用户表不再建在本地 SQLite，避免「用户表既在 dev Supabase 又有本地残留」。

## 6. 已识别的坑（设计阶段已规避，记录备查）

- **坑 1 跨域外键**：`positions`/`transactions`/`watchlist` 引用 market 域的 `fund_code`/`symbol`，迁双库后这些数据库层 FK 消失，只能靠「market 域权威 + 应用层冗余存储」。
- **坑 2 反向跨域 FK**：若 `sales_institutions` 放 market、`ledgers` 放 user，会出现「用户表 FK 指向 market 库」。已用「被谁引用决定归属」规则规避（销售机构随 user 域）。
- **坑 3 FamilyScopedMixin 全局混用**：当前 `FamilyScopedMixin` 给多个 user 域表加 `family_id` 隔离列，market 域表未使用（正确）。但代码层无强制约束阻止将来给 market 表加 `family_id`——护栏（规则 1）将补上这道闸。
- **坑 4 init_db 单引擎建全表**：当前 `Base.metadata.create_all(bind=engine)` 会把 30 张表建到一个库，迁双库必须按域拆分（规则 2）。
- **坑 5 跨域联合查询**：已用「应用层两步法 + 统一 service」规避（第 4 节）。

## 7. Neon 灾备（延后，仅说明）

- 底层都是 Postgres，`SUPABASE_DATABASE_URL` 换成 Neon 连接串即可切换，业务零改动。
- 唯一非「换连接串」的点：Supabase auth ≠ Neon 裸 PG。若灾备切换后仍需登录，要么 Neon 侧也跑 Supabase（或兼容 auth），要么用户表 `supabase_id` 改自研 UUID。属延后阶段，不在本次范围。

## 8. 判定决策树（新增任何表先问自己三问）

1. 它含 `user_id` / `family_id` 吗？ → 是 → **user 域**。
2. 它被谁外键引用？ → 被 user 域表引用 → 随 **user**；被 market 域表（`funds`）引用 → 随 **market**。
3. 它会随「全市场标的数量」无限膨胀吗？ → 是 → **market** 域；仅按「用户数」膨胀 → **user** 域（不受美股/港股扩展影响）。

不满足上述「无限膨胀」但属公开只读小表且被 user 域引用 → 随 user 域（销售机构先例）；被 market 域引用 → 随 market 域（基金管理人先例）。

## 9. 单库 / 双库统一可用（本地回退，2026-08-18 落地）

### 9.1 核心结论

**不必强制双库真实连接。** 架构按「数据域」而非「具体云厂商」抽象，本地可用两种模式：

| 模式 | 触发条件 | market 引擎 | user 引擎 | 适用 |
|------|---------|------------|----------|------|
| **单库（默认）** | `init_db()` / `init_db_split()` 且未配置独立 user 库 | `DEV_DATABASE_URL`（缺省 `invest.dev.db`） | **同 market 引擎（同库）** | 本地默认：既有数据零迁移、最快跑通 |
| 双库模拟 | 显式配置 `DEV_USER_DATABASE_URL` | `DEV_DATABASE_URL` | 独立本地文件（如 `invest.user.dev.db`） | 本地验证域边界、跨域工具，零网络 |
| 真双库 | 配 `SUPABASE_DATABASE_URL` | Turso / `DATABASE_URL` | Supabase Postgres | 最终验证 / 生产 |

> 注意：`init_db_split()` 在未显式配置独立 user URL（`DEV_USER_DATABASE_URL` /
> `SUPABASE_DATABASE_URL`）时与单库等价——两域表落在同一引擎，不做物理拆分；
> 本地需要验证域边界 / 跨域工具时，请显式设置 `DEV_USER_DATABASE_URL`。

### 9.2 回退机制（代码事实）

- `DatabaseConfig.for_user(env)`：**永不返回 None**。未设 `SUPABASE_DATABASE_URL` 时，development 环境**默认与 market 同库**（`DEV_DATABASE_URL`，缺省 `invest.dev.db`）；只有显式配置 `DEV_USER_DATABASE_URL` 才回退独立文件（如 `invest.user.dev.db`）；prod/staging 回退 `USER_DATABASE_URL`（默认与 `DATABASE_URL` 同库）。
- 因此 `user_session_factory()` / `user_session()` / `get_user_sessionmaker()` **不再因缺 Supabase 抛 RuntimeError**——本地默认单库零配置即可用 user 会话。
- `DatabaseFactory.create(DOMAIN_USER)` 对任一环境都返回可用引擎；`init_db_split()` 仅在显式配置独立 user URL（`DEV_USER_DATABASE_URL` / `SUPABASE_DATABASE_URL`）时才把两域表分别建到两个物理引擎，域边界成立。

### 9.3 本地工作流（推荐）

```bash
cd backend
# 默认 APP_ENV=development：user 与 market 同库（单库），本地既有数据零迁移。
# 需要本地双库模拟时，先显式配置独立 user 库再 init_db_split：
#   DEV_USER_DATABASE_URL=sqlite:///./invest.user.dev.db
pdm run python -c "from app.core.database import init_db_split; init_db_split()"
# 之后业务代码经 market_session() / user_session() 取会话，与真双库写法完全一致
```

最终验证真双库：

```bash
export SUPABASE_DATABASE_URL='postgresql://...'   # 用户域走 Supabase
export TURSO_DATABASE_URL='libsql://...'          # 市场域走 Turso（可选）
pdm run python -c "from app.core.database import init_db_split; init_db_split()"
```

业务层代码（service / 跨域工具）**两种模式零改动**——只换 env 变量。

### 9.4 跨域工具在两种模式下的行为

`app/services/common/cross_domain.py` 的 `CrossDomainQuery` 接收 `user_sf` / `market_sf` 两个 sessionmaker：
- 双库模拟：两者分别 bind 本地 `invest.user.dev.db` / `invest.dev.db`；
- 真双库：两者分别 bind Supabase / Turso。

应用层两步法（取 user → 批量取 market → 拼装）逻辑不变，仅在真云库时才产生网络往返。本地模拟阶段测试速度最快。

### 9.5 测试覆盖

- `tests/core/test_db_data_domain.py`：注册表完整性、分组、孤儿告警、本地回退落到独立文件（`test_local_fallback_uses_separate_user_database`）、`init_db_split` 双引擎建表互不相交。
- `tests/core/test_cross_domain.py`：两内存 SQLite 验证 `enrich_by_rows` 两步法拼装。

> 注意：CI / 测试默认 `APP_ENV` 若非 `development`，market 域会走 production 回退（`DATABASE_URL` 同库）。验证「双库物理分离」的测试需显式设 `APP_ENV=development` + 两个独立 dev URL。

## 10. 与历史计划文档的关系及差异（防误读）

`docs/backend-restructure-edgeone-dualengine.md`（2026-08-01）是**早期计划文档**，提出过"双 Base（UserBase / MarketBase），模型分别继承"的拆分设想。该设想**未采用**，本文是实际落地方案。后续 agent / 开发者若读到旧文档，请注意以下差异，避免被误导：

| 维度 | `backend-restructure-edgeone-dualengine.md`（旧计划，已偏离） | 本文实际落地（2026-08-18） |
|------|------|------|
| ORM 基类 | 设想拆 `UserBase` / `MarketBase` 两个 Base | **单一 `app.core.Base`**，通过 `__data_domain__` 属性 + `DATA_DOMAIN_REGISTRY` 注册表声明归属，不拆 Base |
| 建表方式 | 未明确，倾向两 Base 各自 `create_all` | `init_db_split()` 在**单一 Base.metadata** 上按域分组 `to_metadata` 后分别 `create_all` 到 market / user 引擎 |
| env 命名 | `SUPABASE_DB_PASSWORD` 拼装、`user.db` / `market.db` | `SUPABASE_DATABASE_URL`（完整连接串）、`invest.dev.db` / `invest.user.dev.db` |
| 本地回退 | 未提 | user 域未配 Supabase 时**自动回退本地 SQLite**（`invest.user.dev.db`），单库/双库统一可用 |
| 跨域查询 | 提及两层查询但未落地 | 已落地 `app/services/common/cross_domain.py`（`enrich_by_rows` 通用两步法 + `enrich_watchlist_with_market`） |
| 状态 | 标 "未来计划 / 部分 P1" | 分支 `feature/db-multi-engine` 已落地护栏 + 跨域工具，待合入 main-v2 |

> **结论**：旧 dualengine 文档保留作"当年为什么这么选"的决策背景（被否决候选、数据量论证、部署约束仍有价值），但它**不是当前事实标准**。一切以本文 + `AGENTS.md` 约束为准。V1 MySQL 选型文档 `docs/dev/db-choice.md` 已自标失效，仅作历史。

## 11. 闭环状态与剩余尾巴（2026-08-18）

**已进入闭环的部分**：
- 数据域归属决策（39 张表 market/user 分类 + 决策树）已定稿并固化为代码护栏。
- `DATA_DOMAIN_REGISTRY` 单一事实来源 + 启动致命校验 `validate_domain_labels` 已落地。
- market / user 双 session 工厂已落地，user 未配 Supabase 自动回退本地 SQLite（单库/双库统一可用）。
- 跨域联合查询可复用基础设施 `CrossDomainQuery` 已落地并测试。
- 配套硬约束已写入 `AGENTS.md`。

**尚未闭环（尾巴 / 下一步）**：
1. `feature/db-multi-engine` 分支**尚未合入 main-v2**，亦未 push 后发起 PR / review（本次改动已 push 至远程分支）。
2. **真双库仅"可配置"未"真接"**：本地验证靠双 SQLite 模拟；Turso / Supabase 真实连接串尚未在部署环境配置并跑通端到端（最终验证阶段）。
3. **生产建表策略未定**：user 域（Supabase）生产建表计划走 Supabase 迁移工具，`init_db_split` 仅作开发/CI 校验，生产路径需补迁移脚本。
4. **Neon 灾备**按原决策延后，未实现（仅预留 `SUPABASE_DATABASE_URL` 可替换为 Neon 连接串的位置）。
5. 审计表 `user_audit_log` 已在 `PENDING_DOMAIN_REGISTRY` 标记待补模型，尚未落地。
