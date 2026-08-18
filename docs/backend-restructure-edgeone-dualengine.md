# ~~fundmate 后端重构：双 Engine（Supabase + Turso）+ EdgeOne Pages 部署~~ 【已废弃 / DEPRECATED】

> 🚫 **【废弃文档 · 请勿参考】**。本文档是 2026-08-01 的历史规划，**与当前代码已严重不符**，
> 据此写代码会导致错误实现。请**立即移步权威文档**：
> **👉 `docs/dev/db-data-domain.md`（2026-08-18，当前数据库架构唯一事实标准）**。
>
> 废弃原因（一句话）：本文设想的"双 Base（UserBase / MarketBase）拆分 + `SUPABASE_URL` 拼串"
> **实际未采用**。当前落地方案是单一 `app.core.Base` + `DATA_DOMAIN_REGISTRY` 注册表 +
> `init_db_split()` 按域建表，user 域直读 `SUPABASE_DATABASE_URL`（不拼串）。详见 `db-data-domain.md` 第 10 节差异对照。
>
> 保留本文档**仅**作"当年为什么这么选"的决策背景存档，不代表当前代码状态。

> 设计文档 · 2026-08-01
> 目的：让**其他 AI / 协作者**在独立项目下也能完整理解 fundmate 后端这次重构的来龙去脉与落地步骤。
> 关联讨论：本文件是 2026-08-01 多轮架构讨论的落地产物（前端已部署 EdgeOne、后端拟部署 EdgeOne Pages Python 函数、二鸟数据来自独立项目 WeChatRSS）。

---

## 0. 决策摘要（为什么是这套）

经过一轮深度调研与取舍，最终锁定：

| 维度 | 决策 |
|---|---|
| 前端 | **EdgeOne Pages**（已部署，独立前端项目） |
| 后端宿主 | **EdgeOne Pages Python 函数**，APIFlask 原样跑（WSGI 模式，**零重写**） |
| 数据库 | **双库**：Supabase(Postgres) 装用户自产生数据；Turso(libSQL/SQLite 兼容) 装市场/金融大数据 + 二鸟说 |
| 二鸟数据落点 | WeChatRSS(GitHub Action) → POST `/api/internal/erniao/sync`(EdgeOne 函数) → upsert 进 **Turso** 的 market 库 |
| 二鸟采集策略 | **雪球镜像默认（已跑通，全自动）**；微信自动抓取(MP_COOKIE/MP_TOKEN)因登录票据过期**判为不可行**；下一步优化 = 前端提交微信 URL + Edge function 解析（绕开 token） |
| DB 映射 | 用户库读 **`SUPABASE_URL`**（Supabase Postgres）；市场库读 **`TURSO_URL`**（Turso libSQL）。内部引擎名 `user_engine`/`market_engine`（见 §4.1）。凭据已在 `backend/.env` 就位，仅缺 Supabase 数据库密码（见 §9） |
| 域名/备案 | 后端函数**独立部署在 EdgeOne（独立后端项目，选中国香港/境外加速区 → 无需 ICP 备案）** |
| 成本 | EdgeOne 免费层 + Supabase 免费层(500MB) + Turso 免费层(9GB) ≈ **全免费** |

**被否决的候选**（记录理由，免得下次返工）：

- Cloudflare Workers：走 Pyodide/WASM，仅支持纯 Python/PyEmscripten 包，APIFlask 未在其官方支持列表，需重写 → 排除。
- 腾讯云轻量香港 VPS：可行但要自己管服务器，且多了单独一台机器 → 不如同生态 EdgeOne 省心。
- 国内轻量云 + 备案：最便宜但用户域名未备案（需 ~10–20 天）→ 暂不选。
- 单一 Supabase：免费 500MB 装不下本地金融大数据 → 改为"大数去 Turso"。
- 单一本地 SQLite + VPS：用户明确不想重写且要托管 DB，且 VPS 仍需备案/HK 成本 → 不如 EdgeOne 全托管。
- 微信公众号自动抓取（MP_COOKIE/MP_TOKEN）：登录票据几小时~数日过期，需周期手动刷新 → 无法真正自动化，与"全自动"目标冲突 → **弃用**；降级为雪球镜像默认，微信解析留作"前端提交 URL + Edge function"优化项（见 §10）。

---

## 1. 目标与约束

**目标**

1. 让 fundmate 的 API 在公网可用（当前只在本地开发态）。
2. 把"完全自动化采集二鸟说"（WeChatRSS 的 GitHub Action）的数据，回写到 fundmate 并出 API。
3. 不重写任何业务逻辑（保住 APIFlask + SQLAlchemy 现有代码）。
4. 数据库不被免费额度卡死（金融大数据 > 500MB）。
5. 能绑域名、国内访问快、尽量免费。

**硬约束（来自用户）**

- 不重写逻辑（APIFlask 必须原样跑）。
- 域名当前未备案 → 不能走"大陆加速区 + 自定义域名"路径。
- 不想买云数据库（成本敏感）→ 用免费层（Supabase/Turso）。
- 并发不是问题（个人读多写少）→ 不需要为并发上 Postgres（见 §3 论证）。

---

## 2. 目标架构

```plain
   两个 EdgeOne 项目：前端项目(已部署, 静态) + 后端项目(独立, 选 HK/境外区免备案)
   ┌────────────────────────────────────────────────────────────────┐
   │  后端：EdgeOne 独立项目（APIFlask 原样跑 WSGI 零重写）              │
   │  cloud-functions / WSGI 入口  ← APIFlask app 原样跑 (零重写)       │
   │     ├─ /api/temperature/...        读市场温度（market 库/Turso）    │
   │     ├─ /api/positions|transactions  读用户数据（user 库/Supabase）  │
   │     └─ /api/internal/erniao/sync    token 保护的二鸟回写端点        │
   └───────────────┬───────────────────────────┬──────────────────────┘
                   │ user_engine                │ market_engine
                   ▼                            ▼
            Supabase (Postgres)          Turso (libSQL / SQLite 兼容)
            用户数据：持仓/交易/观察池      市场数据：market_* 表
            认证/账户                       金融大数据 + 二鸟说(186行周更)
                                            9GB 免费

   WeChatRSS GitHub Action (海外, 定时 07:00/19:00 北京)
        └─ analyze.py 产出 data/er-niao/index.json
              └─ POST /api/internal/erniao/sync (token) → 全球可达无墙
```

---

## 3. 数据库切分方案（哪些表去哪）

**原则**：按"数据归属 + 体量 + 读写特征"切分，而不是盲目 CQRS。

| 数据（表） | 目标库 | 理由 |
|---|---|---|
| **用户域（Supabase / Postgres）** | | |
| `ledgers` 资金账户（股票/基金/银行/实物/家庭） | Supabase | 用户自建账户容器，量极小 |
| `portfolios` 投资组合 | Supabase | 用户自建组合 |
| `assets` 通用资产/负债（含 `user_id`） | Supabase | 个人资产快照 |
| `positions` 持仓（`ledger_id`→ledgers） | Supabase | 用户持仓 |
| `transactions` 交易记录（`ledger_id`→ledgers） | Supabase | 用户交易流水 |
| `watchlist` / `watchlist_groups` / `watchlist_item_group` / `watchlist_tag_defs` / `watchlist_item_tags` / `watchlist_alerts` / `cleared_positions` 自选/关注/分组/标签/提醒/清仓快照 | Supabase | 用户自选与笔记 |
| `strategy_tags` / `position_strategy_tags` 策略标签（挂在 positions 上） | Supabase | 用户自定义标签 |
| **市场域（Turso / libSQL）** | | |
| `securities` 证券主数据（股票/ETF/可转债/期货/加密） | Turso | 外部同步的参考主数据 |
| `price_history` 证券历史行情（`security_id`→securities） | Turso | 行情时间序列，体量大、只读 |
| `funds` / `fund_companies` / `fund_varieties` / `fund_types` / `fund_sales_orgs` / `managers` / `fund_managers` / `daily_worth` / `money_fund_daily_worth` / `purchase_rules` / `redeem_rules` / `fee_ratios` 基金元数据 + 净值/万份收益序列 | Turso | 基金参考主数据 + NAV 时间序列 |
| `market_single_values` / `market_composites` / `market_multi_items` 市场温度 | Turso | 市场指标，体量大、只读 |
| `sync_logs` 元数据同步审计日志 | Turso | 市场同步任务产出，与市场流水线同生 |
| `erniao_issues`（新增）二鸟说 | Turso | 参考数据，周更、累计 186 行，co-locate 进 market 库 |

> **跨库外键天然为零（本方案可行性的关键）**：用户域所有外键（`positions.ledger_id`→`ledgers`、`transactions.ledger_id`→`ledgers`、`portfolios.portfolio_id`↔`ledgers`、`watchlist_*`→`watchlist`、`position_strategy_tags`→`positions`/`strategy_tags`）都落在用户域内；市场域外键（`price_history.security_id`→`securities`、`daily_worth.fund_code`→`funds`、`fund_managers`/`fee_ratios`→`funds`/`managers` 等）都落在市场域内。用户表只通过 `symbol` 字符串引用市场表（**无 FK 约束**），因此双库拆分无需拆解任何外键关系。

**关于"并发必须用 Postgres"的澄清**：SQLite（含 Turso/libSQL）在 WAL 模式下单服务器可扛 ~10 万读/秒、数千写/秒，唯一硬限是"同时一个写者"。fundmate 是读多写少（98%+ 读）的个人应用，二鸟每周仅 1 次写。因此**并发不是上 Postgres 的理由**；Postgres 只在"serverless 无盘宿主"或"高并发写/多节点分布式"时才必需——本项目两者都不沾。双库是为了**按归属与体量分别用最合适的免费层**，而非为并发。

**关于"数据量 vs 免费额度"的实测（2026-08-01，决定性）**：当前本地 `backend/invest.db` **实测 1.8 GB**（另有 1.6 GB WAL 临时文件），是用户数据 + 市场数据混装的单一库。据此：

- **Supabase 免费额度 500MB 装不下 1.8GB** → 市场数据**不能**放进 Supabase，必须另寻 9GB 免费的 Turso。用户"Supabase 装不下"的判断正确。
- **Turso 免费 9GB 装 1.8GB 绰绰有余** → 市场域（基金净值/基金基本信息/股票基本信息/行情/温度等）归 Turso。
- 拆分后用户域（个人账本/持仓/交易/自选）体量仅 MB 级，落 Supabase 500MB 内毫无压力。
→ **双库不是"可选项"，是被数据量逼出来的必选项**；且市场域只能走 Turso（不能为省事全塞 Supabase）。

---

## 4. 双 Engine 改造（`backend/app/core/database.py`）

当前 `database.py` 是**单 engine 绑定 `DATABASE_URL`**（默认 `sqlite:///./invest.db`），`Base` / `SessionLocal` / `get_db()` 全绑死这一个引擎。改造为**两个引擎 + 两个 Base + 两个会话依赖**。

### 4.1 改造后 `database.py`（草图）

```python
# backend/app/core/database.py
import os
from contextlib import contextmanager
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# ── 两个连接串：生产读 Supabase / Turso，本地未配则回退本地 SQLite ──
# 用户库：Supabase Postgres（需数据库密码；.env 已有 SUPABASE_URL + service key，但缺 DB 密码，见 §9）
SUPABASE_URL = os.getenv('SUPABASE_URL', '')
SUPABASE_DB_PASSWORD = os.getenv('SUPABASE_DB_PASSWORD', '')
SUPABASE_DATABASE_URL = os.getenv('SUPABASE_DATABASE_URL', '')  # 可选：直接给完整 postgres 串
if not SUPABASE_DATABASE_URL and SUPABASE_URL and SUPABASE_DB_PASSWORD:
    _project = SUPABASE_URL.replace('https://', '').rstrip('/')
    SUPABASE_DATABASE_URL = f'postgresql://postgres:{SUPABASE_DB_PASSWORD}@db.{_project}:5432/postgres'
USER_DATABASE_URL = SUPABASE_DATABASE_URL or 'sqlite:///./user.db'

# 市场库：Turso libSQL（.env 已有 TURSO_URL + TURSO_TOKEN）
TURSO_URL = os.getenv('TURSO_URL', '')
TURSO_TOKEN = os.getenv('TURSO_TOKEN', '')
if TURSO_URL and TURSO_TOKEN:
    MARKET_DATABASE_URL = f'{TURSO_URL}?authToken={TURSO_TOKEN}'
else:
    MARKET_DATABASE_URL = 'sqlite:///./market.db'

def _make_engine(url: str) -> Engine:
    connect_args = {}
    # check_same_thread 仅 SQLite 系需要；Postgres/libSQL 不需要
    if url.startswith(('sqlite', 'libsql', 'turso')):
        connect_args = {'check_same_thread': False, 'timeout': 30}
    return create_engine(url, connect_args=connect_args)

user_engine = _make_engine(USER_DATABASE_URL)
market_engine = _make_engine(MARKET_DATABASE_URL)

# ── 两个独立的 Base（元数据隔离，分别 create_all 到各自引擎）──
UserBase = declarative_base()     # 用户域模型继承
MarketBase = declarative_base()   # 市场域模型继承（含二鸟）

UserSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=user_engine)
MarketSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=market_engine)

@event.listens_for(Engine, 'connect')
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """WAL 仅对 SQLite 系引擎开启（Postgres 不需要也认不了 PRAGMA）"""
    name = connection_record.engine.dialect.name
    if name in ('sqlite', 'libsql', 'turso'):
        cur = dbapi_connection.cursor()
        cur.execute('PRAGMA journal_mode=WAL;')
        cur.close()

@contextmanager
def get_user_db() -> Session:
    db = UserSessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_market_db() -> Session:
    db = MarketSessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    UserBase.metadata.create_all(bind=user_engine)
    MarketBase.metadata.create_all(bind=market_engine)
```

### 4.2 模型拆分（逐文件映射，已据实读全代码）

| 模型文件 | 模型 | 改继承 |
|---|---|---|
| `domains/ledgers/models.py` | `Ledger` | `UserBase` |
| `domains/portfolios/models.py` | `Portfolio` | `UserBase` |
| `domains/assets/models.py` | `Asset` | `UserBase` |
| `domains/positions/models.py` | `Position` | `UserBase` |
| `domains/transactions/models.py` | `Transaction` | `UserBase` |
| `domains/watchlist/models.py` | `WatchlistItem` / `WatchlistGroup` / `WatchlistItemGroup` / `WatchlistTagDef` / `WatchlistItemTag` / `WatchlistAlert` / `ClearedPosition` | `UserBase` |
| `domains/strategy/models.py` | `StrategyTag` / `PositionStrategyTag` | `UserBase` |
| `domains/securities/models.py` | `Security` | `MarketBase` |
| `domains/price_history/models.py` | `PriceHistory` | `MarketBase` |
| `domains/funds/models.py` | `Fund` / `FundCompany` / `FundVariety` / `FundType` / `FundSaleOrg` / `Manager` / `FundManager` / `DailyWorth` / `MoneyFundDailyWorth` / `PurchaseRule` / `RedeemRule` / `FeeRatio` | `MarketBase` |
| `domains/temperature/models.py` | `MarketSingleValue` / `MarketComposite` / `MarketMultiItem` | `MarketBase` |
| `models/sync_log.py` | `SyncLog` | `MarketBase` |
| 新增 `domains/erniao/models.py` | `ErNiaoIssue`（见 §6） | `MarketBase` |

> 操作：把每个文件里的 `from app.core.database import Base, PrimaryKeyMixin, TimestampMixin` 改为 `from app.core.database import UserBase, PrimaryKeyMixin, TimestampMixin`（市场域改 `MarketBase`）；类定义 `class X(Base, ...)` 改为 `class X(UserBase, ...)`（`MarketBase`）。`PrimaryKeyMixin` / `TimestampMixin` 不动（不依赖具体 Base）。**每个模型模块都必须在应用启动时 import 一次**，确保 `UserBase`/`MarketBase` 的 `metadata` 收集齐全部表（见 §4.4）。

### 4.3 调用点改造 + 跨库 join 处理

- 现有视图里 `from app.core.database import get_db` 的地方，按它访问的表所属域，换成 `get_user_db()` 或 `get_market_db()`。
- `init_db()` 调用处（应是 `create_app` 启动时）无需改逻辑，已同时建两张元数据。

**跨库 SQL join 唯一风险点（已全代码扫描确认）**：

- `app/services/importer/orchestrator.py` 的 `_match_fund_by_name`（约 374、384 行）用**单一 `self.db`** 做 `Fund`（市场域）JOIN `Position` / `WatchlistItem`（用户域）。双库后单一会话无法跨引擎 join，**必须拆成两个会话分别查询再用 symbol 在 Python 层合并**：
  - 市场查询：`market_db.query(Fund.fund_code).filter(Fund.name.ilike(...))`
  - 用户查询：`user_db.query(Position.symbol)` / `user_db.query(WatchlistItem.symbol)`
  - 命中判断在 Python 里做。
- 其余扫描到的 join 均**域内**或**分库单独查后在 Python 合并**，拆分安全：
  - `watchlist_service.py:243` 的 `market_value_subq` 来自 `Position`（用户域）→ 用户域内 join，不跨库；
  - `performance/calculators.py:75/96` 的 join 对象（`latest` 子查询）由 `DailyWorth`/`PriceHistory` 自身派生（市场域）→ 市场域内；
  - `fund_service.py` 的 `FeeRatio↔PurchaseRule↔RedeemRule`、`importer/orchestrator.py:301` 的 `Fund↔FundVariety` 均为市场域内；
  - `strategy/views.py`、`watchlist_service.py:302/335` 的 join 均为用户域内。
- `importer/orchestrator.py` 还读 `Fund`/`FundVariety`/`Security`（市场域，见 `_batch_query_asset_info`/`_fill_missing_nav_and_shares` 调 `FundService.get_fund_nav_map`），写入 `Position`/`Transaction`/`Asset`（用户域）——**该服务需要同时持有两个会话**，是双引擎的典型"读写分库"场景。

---

## 4.4 测试 / 生产数据库工厂模式（沿用 conftest monkeypatch）

fundmate **已有**测试/生产 DB 分离机制，位于 `backend/tests/conftest.py`（不是 git 历史里的独立工厂类，而是 pytest fixture + monkeypatch）：

```python
# 现有 conftest.py（单引擎版）
@pytest.fixture
def app(monkeypatch):
    test_engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr('app.core.database.engine', test_engine)
    monkeypatch.setattr('app.core.database.SessionLocal', TestSessionLocal)
    Base.metadata.create_all(bind=test_engine)
    app = create_app(); app.config['TESTING'] = True
    yield app
```

**双引擎后 conftest 必须同步改造**（否则测试只覆盖单库、且 `UserBase`/`MarketBase` 元数据未建）：

1. 建两个内存引擎 + 两个 TestSession：`user_test_engine` / `market_test_engine`，分别 `UserBase.metadata.create_all` / `MarketBase.metadata.create_all`。
2. monkeypatch 覆盖 **4 个符号**（不是 2 个）：
   - `app.core.database.user_engine` → `user_test_engine`
   - `app.core.database.user_session`（或 `UserSessionLocal`）→ 对应 TestSession
   - `app.core.database.market_engine` → `market_test_engine`
   - `app.core.database.market_session`（或 `MarketSessionLocal`）→ 对应 TestSession
3. monkeypatch 禁用异步回填（`trigger_backfill` → no-op），沿用现有做法。

**⚠️ 现有 conftest 的模型 import 缺口（双引擎必须补）**：当前 conftest 只 import 了 7 个模型模块（assets / funds / positions / price_history / securities / transactions / watchlist），**缺 `ledgers` / `portfolios` / `strategy` / `temperature` / `sync_log`**。单引擎时 `Base` 可能因其他 import 路径被间接加载而"碰巧"建全；双引擎后 `UserBase`/`MarketBase` 必须**显式 import 全部模型模块**才能 `create_all` 出完整表，否则测试会漏表/漏迁移。改造时把 12+ 个模型模块全部 import 进 conftest。

> 这套 fixture 即"测试库用内存 SQLite、生产库用 Supabase/Turso"的工厂切换——与你记忆中"之前的 fundmate 用工厂模式区分测试/生产 DB"一致，只是实现是 monkeypatch 而非独立工厂类。

---

## 5. `db_utils` 方言兼容（必须核对的坑）

`backend/app/core/db_utils.py` 已有方言分支基础，但仍有两个点需为 Turso/libSQL 补齐：

### 5.1 `bulk_insert_if_not_exists`

当前：

```python
dialect_name = db.bind.dialect.name
if dialect_name == 'postgresql':
    stmt = pg_insert(model).values(batch).on_conflict_do_nothing(...)
else:
    stmt = model.__table__.insert().prefix_with('OR IGNORE').values(batch)  # 走 SQLite 分支
```

- libSQL 是 SQLite 兼容分支，**若其 dialect.name 是 `'sqlite'` 则已覆盖**；
- 若 `sqlalchemy-turso` 注册的 dialect.name 是 `'libsql'` / `'turso'`，需把该分支条件改为 `if dialect_name in ('postgresql',): ... else: ...`（即非 Postgres 全走 `INSERT OR IGNORE`，libSQL 支持）。
- **验证点**：装好 `sqlalchemy-turso` 后打印 `engine.dialect.name` 确认。

### 5.2 `SafeNumeric.process_bind_param`

当前：

```python
if dialect.name == 'sqlite':
    return float(value)
return value  # Postgres 等用 Decimal
```

- libSQL/Turso 接收数值型；为稳妥，将条件改为 `if dialect.name in ('sqlite', 'libsql', 'turso'): return float(value)`，避免严格模式下类型不匹配。
- **验证点**：同上，确认 dialect.name 后对齐。

---

## 6. 二鸟回写端点 `/api/internal/erniao/sync`

### 6.1 新增模型 `ErNiaoIssue`（market 库 / Turso）

```python
# backend/app/domains/temperature/models.py （或新建 erniao.py）
from sqlalchemy import JSON, Column, Date, Integer, String, UniqueConstraint
from app.core.database import MarketBase, PrimaryKeyMixin, TimestampMixin

class ErNiaoIssue(MarketBase, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = 'erniao_issues'
    issue_no = Column(Integer, nullable=False, index=True, comment='期号')
    title = Column(String(200), nullable=False, comment='标题')
    publish_date = Column(Date, nullable=True, comment='发布日期')
    coefficient = Column(SafeNumeric(6, 2), nullable=True, comment='温度系数 0-12')
    sentiment = Column(String(20), nullable=True, comment='情绪枚举')
    portfolios = Column(JSON, nullable=True, comment='涉及组合')
    market_view = Column(JSON, nullable=True, comment='市场观点')
    empirical_actions = Column(JSON, nullable=True, comment='实证操作')
    source_url = Column(String(500), nullable=True, comment='原文链接')
    collected_at = Column(String(30), nullable=True, comment='采集时间')

    __table_args__ = (
        UniqueConstraint('issue_no', name='uq_erniao_issue_no'),
    )
```

> 字段对齐 WeChatRSS 已归档的 `data/er-niao/index.json` 结构（issue_no / title / publish_date / coefficient / sentiment / portfolios / market_view / empirical_actions / source_url / collected_at）。

### 6.2 端点实现

```python
# backend/app/domains/internal/views.py
import os
from apiflask import APIBlueprint, abort
from flask import jsonify, request
from app.core.database import get_market_db
from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.temperature.models import ErNiaoIssue

internal_bp = APIBlueprint('internal', __name__, url_prefix='/api/internal')

@internal_bp.post('/erniao/sync')
def erniao_sync():
    """WeChatRSS Action 调用的二鸟数据回写入口（token 保护）"""
    if request.headers.get('X-Sync-Token') != os.getenv('ERNIAO_SYNC_TOKEN'):
        abort(401)
    payload = request.get_json(force=True) or {}
    issues = payload.get('issues', [])
    if not issues:
        return jsonify({'inserted': 0, 'message': 'empty'}), 200
    with get_market_db() as db:
        inserted = bulk_insert_if_not_exists(
            db, ErNiaoIssue, issues, unique_columns=['issue_no']
        )
    return jsonify({'inserted': inserted, 'message': 'ok'}), 200
```

### 6.3 注册蓝图

在 `backend/app/main.py` 的 `create_app()` 里（现有 `register_blueprint(thermometer_bp)` 附近）增加：

```python
from app.domains.internal.views import internal_bp
app.register_blueprint(internal_bp)
```

---

## 7. EdgeOne Pages 部署

### 7.1 为什么能原样跑 APIFlask

EdgeOne Pages **Python 运行时原生支持 WSGI（Flask/Django）与 ASGI（FastAPI/Sanic）**，框架自动检测、无需额外配置（官方文档 `edgeone.ai/document/205713904659333120`）。因此 `create_app()` 产出的 APIFlask `app` 对象可直接作为 WSGI 入口部署，**业务逻辑零改动**。

### 7.2 项目结构（两种可选，推荐 A）

- **方案 A（最小改动，✅ 已选）**：把 fundmate 后端作为**一个独立后端项目**部署到 EdgeOne Pages，用 WSGI 模式暴露 `app`。目录：

  ```plain
  fundmate-backend/                # 部署到 EdgeOne Pages 的项目根
  ├── app.py                       # WSGI 入口：from app.main import create_app; app = create_app()
  ├── requirements.txt             # 依赖（见 §7.4）
  ├── cloud-functions/             # （可选）若用文件路由；WSGI 模式可不需要
  └── app/                         # 现有后端代码整体搬入
        ├── main.py
        ├── core/database.py
        ├── domains/...
        └── ...
  ```

  EdgeOne 检测到 WSGI `app` 后自动挂载，路由沿用 APIFlask 的 `/api/...`。
- **方案 B（全栈同仓，❌ 已否）**：把后端 `cloud-functions/api/` 并入现有前端 EdgeOne 项目——**用户已明确"后端独立部署，不与前端同项目"**，故 B 排除。

> **已确认（2026-08-01）**：后端代码独立部署，**不与前端同项目**（选方案 A，独立 EdgeOne 后端项目）。代码落盘 = 新建独立 EdgeOne 项目根，搬入 `backend/` + `app.py` WSGI 入口；前端仍留在现有 EdgeOne 前端项目。

### 7.3 本地调试与部署

- 本地：`edgeone makers dev`（EdgeOne CLI）启动本地服务调试函数。
- 部署：推送到 Git 仓库 → EdgeOne Makers 自动构建 + 发布（Git 集成）。
- 环境变量 / Secrets：在 EdgeOne 项目设置里配置 `SUPABASE_URL` / `SUPABASE_DB_PASSWORD` / `TURSO_URL` / `TURSO_TOKEN` / `ERNIAO_SYNC_TOKEN`（见 §9）。

### 7.4 依赖（部署用 requirements.txt）

在部署项目的 `requirements.txt` / `pyproject.toml` 中确保包含：

```plain
apiflask
sqlalchemy
psycopg2-binary         # SQLAlchemy 连 Supabase Postgres 的驱动（postgresql:// 默认用 psycopg2）；若用 psycopg3 则改为 psycopg
loguru
python-dotenv
sqlalchemy-libsql       # 纯 Python 方言适配器（py3-none-any），注册 libsql:// 方言，连 Turso
# 其依赖 libsql-experimental（libSQL 官方驱动）：
#   - PyPI 提供 cp310~cp313 的 manylinux_2_17_x86_64 轮子 → EdgeOne(Linux x86_64) 可装
#   - 但【无 Windows 轮子】→ 本机 Windows 开发装不上（源码编译 Rust 失败）
#   → 解法：dev 用本地 SQLite 文件（用户已定），本机不碰该轮子；prod(EdgeOne Linux) 才用它
```

> **✅ 实测定论（2026-08-01，更正此前误判）——市场域走 Turso 且【不改写任何 SQL】：**
>
> 1. `sqlalchemy-turso` 在 PyPI 不存在（已证实）；真实方言包是 **`sqlalchemy-libsql`**（纯 Python 适配器，注册 `libsql://` 方言），其依赖 `libsql-experimental`（libSQL 官方驱动）。
> 2. **关键：该驱动有 Linux manylinux 轮子（cp310~cp313），但【无 Windows 轮子】。** 结论与之前相反：
>    - **prod（EdgeOne Pages = Linux x86_64）能正常安装运行** → ORM 经 `libsql://` 方言直连 Turso 成立 → **"APIFlask 用 SQLAlchemy ORM 不改写、直接连 Turso" 在部署目标上可行**。
>    - **本机 Windows 开发装不上**（无 Windows 轮子，源码编译 Rust 失败）——但 **dev 已定为本地 SQLite 文件**，本机开发根本不需要 libsql 轮子，完全规避。
> 3. **因此市场域保持现有 SQLAlchemy ORM 不变**（模型/`db_utils`/`SafeNumeric`/`bulk_insert_if_not_exists` 的 sqlite 分支在 libSQL 上自动生效）；仅在 prod 把 `market_engine` 指向 `libsql://` 方言连 Turso。**无需改用裸 libsql 客户端、无需重写 SQL**（此前提出的"方案 2 裸客户端重写"已否决）。
> 4. Turso 官方 `libsql` 客户端（0.1.11）也已实测可连（`SELECT 1 → (1,)`），保留作 migrate/运维备选通路，但日常 ORM 读写不走它。
> 5. **本沙箱无法真验 ORM-on-Turso**（Windows 无轮子 + 无 WSL）；prod 验证待部署 EdgeOne 后用 `init_db()` / `SELECT 1` 复测。dev/test 用本地 SQLite/内存不受影响，可先行验证双引擎与模型拆分逻辑。

---

## 8. 数据迁移（本地 SQLite → Supabase / Turso）

一次性脚本，用 ORM 双引擎把现有 `invest.db` 的表分别迁过去：

```python
# scripts/migrate_to_cloud.py （一次性）
from app.core.database import user_engine, market_engine, UserBase, MarketBase
from app.domains.temperature.models import MarketSingleValue, MarketComposite, MarketMultiItem
# 导入所有用户域模型以确保 UserBase 元数据完整
# ... 读取 invest.db（旧单库）各表 → 写入对应云引擎
```

要点：

- fundmate 当前用 `init_db()`（`create_all`）建表，**没有 Alembic 历史** → 首次对 Supabase/Turso 跑 `init_db()` 即可自动建表，无需迁移工具。
- 迁移脚本用旧 SQLite 引擎读取、用新云引擎 `bulk_insert_if_not_exists` 写入（复用 §5 的方言兼容逻辑）。
- 二鸟数据在 WeChatRSS 侧（`data/er-niao/index.json`），可在迁移后由首次 sync 端点灌入，不必从 fundmate 旧库迁。

---

## 9. 环境变量 / Secrets 清单

| 变量 | 用途 | 配置位置 | 现状 |
|---|---|---|---|
| `SUPABASE_URL` | Supabase 项目地址（`https://xxx.supabase.co`） | EdgeOne 环境变量 / `backend/.env` | ✅ 已填（`.env`） |
| `SUPABASE_DB_PASSWORD` | Supabase Postgres 数据库密码（拼出 `postgresql://` 串） | EdgeOne Secrets / `backend/.env` | ⚠️ **缺失，需补**（见下方说明） |
| `SUPABASE_DATABASE_URL` | 可选：直接给完整 Postgres 连接串（优先于上面两项拼装） | EdgeOne 环境变量 | 可选 |
| `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` | Supabase Auth/RLS（`SUPABASE_ANON_KEY` 亦作 JWKS 端点 `apikey` 头） | `backend/.env` | ✅ 已填 |
| `SUPABASE_JWT_SECRET` | **已废弃**（原 HS256 共享密钥已随 Supabase 迁移 ECC 轮换，`SUPABASE_JWT_SECRET` 实际是 Key ID 而非密钥） | — | ❌ 移除，勿再用（验签改 JWKS+ES256，见 decisions D2 修订） |
| `TURSO_URL` | Turso libSQL 地址（`libsql://xxx.turso.io`） | EdgeOne 环境变量 / `backend/.env` | ✅ 已填 |
| `TURSO_TOKEN` | Turso 访问令牌（拼进 libSQL URL 的 `authToken`） | EdgeOne Secrets / `backend/.env` | ✅ 已填 |
| `ERNIAO_SYNC_TOKEN` | 二鸟回写端点共享密钥 | EdgeOne Secrets / WeChatRSS Secrets | 需设 |
| `ARK_API_KEY` / `ARK_MODEL` | Ark 结构化解析 | WeChatRSS GitHub Secrets | 已填（`.env`） |
| `MP_COOKIE` / `MP_TOKEN` | ~~微信自动抓取登录态~~ **已弃用** | — | 不再需要 |

> **DB 映射（用户确认）**：用户库读 **`SUPABASE_URL`**（+ 密码拼 `postgresql://`）、市场库读 **`TURSO_URL`**（+ `TURSO_TOKEN` 拼 `authToken`）。内部引擎名仍叫 `user_engine` / `market_engine`（见 §4.1）。
>
> **关于 Supabase 连接方式的硬约束**：fundmate 全代码用 **SQLAlchemy ORM**（不能改写为 supabase-py SDK，否则违反"零重写"）。SQLAlchemy 连 Supabase Postgres 需要 `postgresql://postgres:<密码>@db.<项目>.supabase.co:5432/postgres`，**密码不在当前 `.env` 中**（现有 `SUPABASE_SERVICE_ROLE_KEY` 是 JWT，不是 DB 密码）。→ **需你去 Supabase 控制台「Project Settings → Database → Connection string」取数据库密码，补到 `.env` 的 `SUPABASE_DB_PASSWORD`**。本地未配时 `user_engine` 回退 `sqlite:///./user.db`（§4.1 默认值），故 P1 改造可先用本地 SQLite 验证，无需该密码。
>
> **凭据就位情况**：`backend/.env` 已含 `SUPABASE_URL` + 三个 key、`TURSO_URL` + `TURSO_TOKEN`。因此 P0 的"注册账号 + 取连接串"大部分已完成，唯一待补 = Supabase 数据库密码（及设置 `ERNIAO_SYNC_TOKEN`）。

### 9.1 多环境配置文件策略（dev / test / prod）—— 已确定

**现状问题**：`backend/app/main.py` 仅 `load_dotenv()` 认单一 `.env`，`database.py` 仅读单一 `DATABASE_URL`，无法区分环境；且真实密钥与生产混在 `.env` 一处。需拆成 3 个环境文件。

**文件结构（恰好 3 个真实文件 + 1 个提交模板）**
| 文件 | 是否提交 | 内容 |
|---|---|---|
| `backend/.env.development` | ❌ gitignore | 开发环境：用户域=Docker Postgres（本地）、市场域=本地 SQLite（`dev_market.db`） |
| `backend/.env.test` | ❌ gitignore | 仅非 DB 设置（如 `CORS_ORIGINS=*`、`FLASK_DEBUG=0`）；DB 由内存化逻辑接管，不写真实库 URL |
| `backend/.env.production` | ❌ gitignore | 把当前 `.env` 里的 Supabase/Turso 真值搬过来（用户域 Postgres + 市场域 Turso） |
| `backend/.env.example` | ✅ 提交、无密钥 | 重写现有模板，列出三套变量占位 |

> 旧的单文件 `backend/.env` 在改造后**退役**：其生产真值并入 `.env.production`，开发值并入 `.env.development`。

**环境选择机制（恰好 3 文件）**

- 引入 `APP_ENV` 变量，**默认 `development`**。
- `main.py` 把 `load_dotenv()` 改为：

  ```python
  import os
  from dotenv import load_dotenv
  ENV = os.getenv('APP_ENV', 'development')
  load_dotenv(f'.env.{ENV}', override=True)   # CI / EdgeOne 用真实环境变量 APP_ENV=production 盖过文件默认
  ```

- `database.py` 顶部读 `APP_ENV` 决定引擎（见 §4.1 草图扩展）：
  - `test` → 两个引擎均 `sqlite:///:memory:` + `StaticPool`（无需 `.env.test` 写 DB URL）
  - `development` → `user_engine` = `postgresql://postgres:postgres@localhost:5432/fundmate_dev`（Docker PG）；`market_engine` = `sqlite:///./dev_market.db`（WAL）
  - `production` → `user_engine` 读 `SUPABASE_DATABASE_URL`（或 `SUPABASE_URL`+`SUPABASE_DB_PASSWORD` 拼装）；`market_engine` 读 `TURSO_URL`+`TURSO_TOKEN`
- 各环境变量仍可被真实进程环境变量覆盖（EdgeOne / CI 设 `APP_ENV=production` + 直接注入 Secrets，不必依赖文件）。

**配套修正**

1. `main.py` 第 48 行硬编码 `app.config['DEBUG'] = True` → 改为 `app.config['DEBUG'] = (ENV != 'production')`。
2. `conftest.py` 顶部加 `os.environ.setdefault('APP_ENV', 'test')`（在 import `app` 之前），内存引擎由 `database.py` 的 test 分支自建；`create_all` 跑在内存引擎上，`db()`/`clean_db()` fixture 改用 `user_session`/`market_session`。双引擎后 monkeypatch 覆盖 4 个符号（见 §4.4）。
3. `.gitignore` 增加 `backend/.env.*`（注意保留 `.env.example` 不被忽略）；root `.gitignore` 已有 `frontend/.env.development` 等先例可参照。
4. **与前端约定对齐**：前端用 `dev/staging/prod`（staging=部署的预发云端）；后端 `test`=内存=pytest、**不部署**，两者独立。若以后要"部署到云端的测试环境"，再加 `backend/.env.staging`（第 4 个文件）即可。

> **dev 用 Docker Postgres 的好处**：开发期就跑真实 Postgres 方言（与 prod Supabase 同源），提前暴露 `SafeNumeric`/pg_insert 等方言分支问题；市场域 dev 用本地 SQLite，把"Turso/libsql 客户端能否在本地跑"的风险隔离在生产，本地开发最省心。

---

## 10. 二鸟采集策略（降级机制 + 下一步优化）

### 10.1 现状：雪球镜像已全自动跑通（默认路径）

WeChatRSS 的 `analyze.py` + `erniao.py` 插件**当前已实测跑通**：云端 WebFetch 抓雪球全文 → 火山 Ark 结构化 → 写 `data/er-niao/index.json`（source_url 用雪球镜像链接）。GitHub Action 定时（07:00/19:00 北京）运行，**无需任何微信登录态**，零凭证维护成本。这条就是生产默认链路。

### 10.2 微信自动抓取（MP_COOKIE/MP_TOKEN）：判为不可行，弃用

`gen_rss.py` 走 `mp.weixin.qq.com` 的 `getmsg` 搜索接口需要登录态（`data_ticket`/`slave_sid`），而**登录票据几小时~数日即过期**，塞进 GitHub Secrets 后必然周期性失效、Action 跑空。这与"完全自动化"目标冲突 → **不作为正式链路**，仅保留为可选实验。

### 10.3 降级机制（实现要点）

`gen_rss.py` / `analyze.py` 必须支持：**未配置或配置不合法的微信凭证时，直接走雪球镜像方案**，不报错、不中断。当前 `gen_rss.py` 在缺 `MP_COOKIE` 时已优雅跳过（生成空订阅源），需保持此行为并把雪球链路作为唯一稳定产出源。

### 10.4 下一步优化（绕开 token）：前端提交微信 URL + Edge function

既然每过一段时间就要登录的 token 路不现实，**改用"人肉提交 + 服务端解析"**：

- 前端做一个表单：用户把某期二鸟说的**微信原文分享链接**（`mp.weixin.qq.com/s?__biz=...`）贴进来提交。
- EdgeOne Pages Function（如 `/api/erniao/submit`）接收 URL → 服务端 `fetch` 该**单篇**文章页（单篇微信文章 URL 公开可读，**不需要登录态**；只有"搜索/列表"接口才要 cookie）→ 抽取标题/正文 → 调 Ark 结构化 → 经 `X-Sync-Token` 写入 `/api/internal/erniao/sync`（复用 §6 端点）。
- 这样完全绕开 token 维护，且拿到的是真·微信原文链接（取代雪球镜像链接）。

> 风险：mp.weixin.qq.com 单篇抓取偶发反爬/验证页；若解析失败，仍可只存提交的微信 URL、内容回退雪球镜像。列为 P6 优化项，不阻塞 P0–P5。

### 10.5 WeChatRSS Action 接回写（默认链路落地）

在 `rss.yml` 于 `analyze.py` 产出 `data/er-niao/index.json` 之后，增加一步 POST 到 fundmate：

```yaml
      - name: Sync erniao to fundmate
        run: |
          curl -X POST "$ERNIAO_SYNC_ENDPOINT/api/internal/erniao/sync" \
            -H "Content-Type: application/json" \
            -H "X-Sync-Token: $ERNIAO_SYNC_TOKEN" \
            -d @data/er-niao/index.json
```

> 这替代了之前讨论的"本地 WorkBuddy 兜底自动化"——fundmate 公网常驻后，Action 直接 POST 即可，无需本机 replay。

---

## 11. 实施阶段与用户前置

| 阶段 | 内容 | 执行方 |
|---|---|---|
| **P0 前置（用户）** | ① Supabase 项目 + 连接串：**`.env` 已有 `SUPABASE_URL`+key，仅缺 `SUPABASE_DB_PASSWORD`**；② Turso：**`.env` 已有 `TURSO_URL`+`TURSO_TOKEN`**；③ EdgeOne 后端项目布局 **已确认 = 独立后端项目** | **用户**（补密码 + 设 `ERNIAO_SYNC_TOKEN`） |
| **P1 双 Engine** | 改造 `database.py`（§4）、拆分模型 Base、`db_utils` 方言补齐（§5） | AI |
| **P2 回写端点** | 新增 `ErNiaoIssue` 模型 + `/api/internal/erniao/sync`（§6），注册蓝图 | AI |
| **P3 EdgeOne 部署** | 部署项目结构 + `requirements.txt` + 环境变量 + CLI 调试（§7） | AI（需用户给项目路径） |
| **P4 数据迁移** | 一次性脚本迁本地 SQLite → Supabase/Turso（§8） | AI |
| **P5 接回写** | WeChatRSS Action 改为 POST sync 端点（§10.5） | AI |
| **P6 优化（前端提交）** | 前端表单 + Edge function 提交微信 URL、服务端解析写入（§10.4）；绕开 token | AI（需前端配合） |

**P0 进度**：③ EdgeOne 后端项目布局已确认（独立项目）；①/② Supabase/Turso 账号与连接串**凭据已在 `backend/.env` 就位**（AI 不能代注册，但你也已配好）。**唯一待补 = `SUPABASE_DB_PASSWORD`**（Supabase Postgres 数据库密码，§9 说明）与 `ERNIAO_SYNC_TOKEN`。**P1 代码改造已可开工**：`database.py` 读 `SUPABASE_URL`/`TURSO_URL` + 本地 SQLite 兜底，本地用 SQLite 即可验证双 Engine 逻辑与模型拆分，无需真实云连接串；真正联调/部署待 `SUPABASE_DB_PASSWORD` 就位。

---

## 12. 风险与验证清单

| 风险 | 缓解 / 验证 |
|---|---|
| **libsql 驱动无 Windows 轮子（已澄清，非阻断）** | `libsql-experimental` 仅有 Linux manylinux 轮子（cp310~cp313），**无 Windows 轮子** → 本机 Windows 装不上；但 **prod(EdgeOne Linux) 可装**，且 **dev 已定为本地 SQLite 文件**故本机无需它。**市场域保持 SQLAlchemy ORM 不变、prod 切 `libsql://` 方言连 Turso，零重写**。待办：prod 部署后真验 `init_db()`/`SELECT 1`；`database.py` 的 `set_sqlite_pragma`(WAL) 与 sqlite-only `connect_args` 需对 libSQL 远程连接跳过（针对性小修，非重写）。详见 §7.4。 |
| Turso 直连客户端 `libsql` 已验证可用（备选通路） | `libsql.connect(libsql://<host>, auth_token=...)` → `SELECT 1 → (1,)` 成功（2026-08-01 实测）。保留作 migrate/运维备选，日常 ORM 读写不走它。 |
| Supabase 直连域名 `db.<ref>.supabase.co` 在 serverless 不稳 | 部署到 EdgeOne 时用 **Transaction Pooler** 串（`aws-0-<region>.pooler.supabase.com:6543`，用户名 `postgres.<ref>`，端口 6543），避免连接耗尽 + 直连域名解析问题。本地开发用直连串即可。`.env` 中的 `SUPABASE_DATABASE_URL` 已是标准直连串（格式正确）。 |
| Supabase 凭据在本沙箱无法完整验证 | 沙箱 DNS 解析不了 `db.<ref>.supabase.co`（但 API 域名/pooler 域名可解析）；实测已能抵达 Supabase 服务器（返回 FATAL，证明密码已送达），从用户本机/EdgeOne 直连串可用。需在用户本机或部署后复测 `SELECT 1`。 |
| `create_all` 的 DDL 兼容性（已定路径） | 用户域走 Supabase/Postgres（DDL 成熟）；**市场域走 libSQL（已定）** → 首次 `init_db()` 需实测建表，关注 `server_default=func.now()` 等在 libSQL 的差异；`db_utils` 的 sqlite 分支（`OR IGNORE` / `SafeNumeric→float`）在 libSQL 上自动生效，无需改。 |
| EdgeOne Python 冷启 ~百毫秒、有执行超时 | 个人低频 API 可接受；超时可在 EdgeOne 函数配置调大 |
| serverless 临时文件系统 | DB 全在外部（Supabase/Turso），应用无状态，无影响 |
| DB 查询腿跨境（Supabase/Turso 美西/东京）延迟 | 应用层 EdgeOne 亚洲节点快；Turso 可用 embedded replica 放边缘只读副本优化 |
| 依赖清单位置 | 已确认 = `pyproject.toml`（pdm 管理），无顶层 requirements.txt；Turso 接入用 `sqlalchemy-libsql`（纯 Python 方言适配器）+ 其依赖 `libsql-experimental`（仅 Linux wheel，prod 用）。 |

---

## 13. 一句话给后来者

> fundmate 后端从"本地单 SQLite"重构为"EdgeOne Pages 托管 APIFlask（零重写）+ 双 Engine（Supabase 装用户数据 / Turso 装市场与二鸟数据）"。二鸟说数据由独立项目 WeChatRSS 的 GitHub Action 定时采集，POST 到 `/api/internal/erniao/sync` 回写 Turso。所有密钥走环境变量/Secrets，不落库。改造核心在 `app/core/database.py`（双 Base/双会话）与 `app/core/db_utils.py`（方言分支补齐），新增端点在 `app/domains/internal/views.py`。 二鸟采集以雪球镜像为默认全自动链路（微信自动抓取因 token 过期弃用），下一步优化为前端提交微信 URL + Edge function 解析（§10）。

---

## 14. 东方财富抓取的国内 IP 部署约束（乖离度 / 温度计）

**结论先行**：所有向东财（`push2.eastmoney.com` / `80.push2.eastmoney.com` 等公开行情接口）发起的抓取，**必须在国内 IP 环境运行**；EdgeOne 香港/境外节点**只承载读取**，不得由它直接抓东财。

### 14.1 为什么

- 乖离度（BiasJob）与部分温度计数据依赖东方财富公开行情接口。东财按**出口 IP** 动态限流/临时封，境外 IP（如 EdgeOne 香港函数出口）或对裸请求/被封 IP 直接 `RST` / `RemoteDisconnected` / `schannel: server closed abruptly`。
- 2026-08-01 本机实测：裸 `requests` 直连东财可 200，但挂 DevSidecar 边车代理或不挂代理均出现两 host 的 schannel 失败；根因倾向**代理 TLS 干扰或出口 IP 被封**，非代码缺陷（退出代理后 `diag_em.py` 验收确认中）。

### 14.2 部署形态（推荐）

| 环境 | 抓取任务怎么跑 | 数据落点 | 读取 |
|---|---|---|---|
| 本机开发/自托管 | `pdm run sync --job temperature`（已注册别名，触发 BiasJob）定时跑 | 本地 SQLite / 或推云库 | 本机/本地 API |
| 云上（推荐） | 腾讯云 **SCF 国内区**（上海/广州等）定时触发器跑同一同步脚本 | 写 **Supabase（用户库）/ Turso（市场库）** | EdgeOne 香港函数只读库返回 API |
| 禁止 | ❌ 由 EdgeOne 香港函数直接 `akshare`/请求东财 | — | — |

> EdgeOne 香港函数职责 = **只读 + 聚合 + 返回**；任何 `akshare` / 东财请求都应解耦到国内 IP 抓取端，结果入库后由 EdgeOne 读。

### 14.3 代码层已做的缓解（与部署约束互补，非替代）

- `app/core/requests_patch.py`：全局 `requests` 补丁（浏览器头 + 连接复用 + 3 次指数退避重试 + `N.push2`→`push2` host 重写保险）。进程启动一次安装，覆盖所有 akshare 调用（已源码核实：乖离度用到的 akshare 函数均走 `requests.get`/`Session.get`，被补丁覆盖）。
- `app/services/bias/calculator.py` 的 `PriceFetcher`：持久化文件缓存（`backend/data/bias_price_cache/*.json`）。实时抓取失败且本地有旧缓存时，**回退旧数据并标 `stale=True`**（BiasResult.stale 透传落库），断网/东财挂时仍有数据可算，前端可感知滞后。
- `scripts/diag_em.py`：连通性诊断（A 裸 requests / B 候选 host / C 真实 akshare）；退出本机代理后跑 `pdm run python scripts/diag_em.py` 确认 [C] 通过即证明代码路径可用、根因在代理/出口 IP。

### 14.4 验收与待办

- [ ] 退出 DevSidecar 后本机跑 `diag_em.py`，[C] 真实 akshare 返回成功 → 坐实根因为代理/出口 IP，非代码。
- [ ] 选定为 SCF 国内区定时触发器（或保留本机定时），将抓取与 EdgeOne 读取彻底解耦。
- [ ] 前端温度计页展示 `stale` 标记（数据滞后提示）——见 bias 任务可观测项。
