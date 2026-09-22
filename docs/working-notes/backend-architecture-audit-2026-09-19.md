---
title: 后端架构审查（结构性问题分级 · 2026-09-19）
---

# 后端架构审查报告（结构性问题分级）

**审查日期**：2026-09-19
**审查对象**：`backend/app`（229 个 py 文件 / 约 3.1 万行）
**审查基线**：`docs/spec/conventions.md`（冻结区）、`architecture.md`、`data-strategy.md`、`data-model.md`、`AGENTS.md`、`docs/dev/db-data-domain.md`
**审查性质**：结构与架构层（分层边界、依赖方向、事务边界、契约一致性）。**不含**业务逻辑正确性与数据源可用性。

---

## 0. 审查口径（先声明，避免误读）

1. **只报「文档有硬约束 / 代码内有客观口径可量」的偏差**，不凭风格偏好提意见。
2. 每条结论必须有 `file:line` 或可复跑的计数支撑。
3. **凡涉及"运行时行为"的结论，以最小复现实验为准，不以阅读推断为准**（见 §2.1 的实验记录）。
4. 已登记在 `tech-debt.md` / 既有 issue 的事项不重复开卡，仅在其"实际情况与登记不符"时指出。
5. 本轮**只审查、不修改代码**（`conventions.md` §16.3）。

---

## 1. 结论速览

| # | 问题 | 级别 | 关键证据 | 归属里程碑 | issue |
|---|---|---|---|---|---|
| 1 | 跨域 SQL join 违反双库「零 join」硬约束，真双库下运行时抛错 | **P0** | `orchestrator_parse.py:353,363`；最小复现抛出 `no such table: funds` | 14 双库架构 | [#1605](https://github.com/imoyao/fundmate/issues/1605) |
| 2 | 视图层承担业务逻辑与事务边界（ledgers 1811 行 / 71 次 DB 调用） | P1 | `domains/ledgers/views.py`、`domains/watchlist/views.py` | 9 Backlog | [#1606](https://github.com/imoyao/fundmate/issues/1606) |
| 3 | 依赖方向失序：core 反向依赖 domains；domains 与 services 双向互引 | P1 | `core/auth.py:168,218,235,257`、`core/database.py:401-402`；包级双向依赖 23 对 | 9 Backlog | [#1607](https://github.com/imoyao/fundmate/issues/1607) |
| 4 | 全局单例 + 模块级早绑定，测试隔离靠手工维护的「例外模块清单」 | P1 | `tests/conftest.py:85-124` | 9 Backlog | [#1608](https://github.com/imoyao/fundmate/issues/1608) |
| 5 | 事务范式两极并存，服务方法无法参与同一事务 | P2 | `core/database.py:120-133` vs `ledgers/views.py:1095-1312` | 9 Backlog | [#1609](https://github.com/imoyao/fundmate/issues/1609) |
| 6 | 错误响应绕过统一信封：63 处错误路径缺 `error_code` | P2 | 全仓 AST 扫描（可复跑） | 9 Backlog | [#1610](https://github.com/imoyao/fundmate/issues/1610) |
| 7 | 规范与文档一致性批次（尾斜杠 / api.md 滞后 / 日志规范） | P2 | 18 个无尾斜杠端点；api.md 列 30 条 vs 实际 131 条 | 9 Backlog | [#1611](https://github.com/imoyao/fundmate/issues/1611) |
| 8 | 导入编排器 1076 行无直接测试 | P2 | `importer/orchestrator_holdings.py` | 11 导入统一入口 | [#1612](https://github.com/imoyao/fundmate/issues/1612) |

**范围外的良性事实**（本轮核实后认为无需处理，记录以免后人重复怀疑）：
`advisor_catalog.py` 1386 行硬编码、46 处 `except Exception`、`cross_domain.py` 全表扫描 —— 详见 §3。

---

## 2. P0：跨域 SQL join 违反双库硬约束

### 2.1 问题

`AGENTS.md`「数据域架构（双引擎硬规则）」与 `architecture.md` §1.2 均规定：

> 两域**跨库零外键、零 SQL join**，用户表仅以 `symbol`/`fund_code` 字符串冗余键引用市场表。

代码中 `Position`（user 域）与 `Fund`（market 域）出现在**同一条 SQL**：

```python
# backend/app/services/importer/orchestrator_parse.py:351-366
pos_fund = (
    self.db.query(Fund.fund_code)
    .join(Position, Position.symbol == Fund.fund_code)   # L353  user 域 × market 域
    .filter(Fund.name.ilike(search_pattern))
    .first()
)
...
watch_fund = (
    self.db.query(Fund.fund_code)
    .join(WatchlistItem, WatchlistItem.symbol == Fund.fund_code)  # L363  同上
    ...
)
```

调用链：`orchestrator_parse.py:263`（导入时按基金名匹配代码）→ 仅此一处调用方，属**导入主链路**。

### 2.2 实证（最小复现，非阅读推断）

复刻真实场景（market 库只有 `funds`，user 库只有 `positions`，与 Supabase 不含 `funds` 表的事实一致），并给引擎挂 `before_cursor_execute` 观察 SQL 落库：

```
=== query(Fund.fund_code).join(Position, Position.symbol == Fund.fund_code).first() ===
    -> 发往 [USER] 库: SELECT funds.fund_code AS funds_fund_code
       FROM funds JOIN positions ON positions.symbol = funds.fund_code
  !! 抛出 OperationalError: no such table: funds

=== 对照：文档要求的「两步法」（先取 key，再 in_）===
    -> 发往 [USER] 库: SELECT positions.symbol FROM positions
    -> 发往 [MARKET] 库: SELECT funds.fund_code FROM funds WHERE funds.fund_code IN (?)
  返回: ('000001',)          <-- 正常
```

**结论（A 级证据）**：
- SQLAlchemy 的 `Session(binds={表: engine})` 会把跨 bind 的 join **整体发往 user 引擎**（因为 join 里含 user 域表）；
- user 库没有 `funds` 表 → 抛 `OperationalError`；
- 该错误**只在双库模式下出现**：本地开发默认单库（两个域同一 engine 对象），永不暴露。

### 2.3 为什么定 P0

| 维度 | 判断 |
|---|---|
| 触发条件 | 配置 `SUPABASE_DATABASE_URL`（生产用户域）或 `DEV_USER_DATABASE_URL`（本地双库模拟） |
| 覆盖范围 | 导入链路的基金名匹配，走 `_match_fund_by_name` 的第一、二优先级分支 |
| 隐蔽性 | dev / CI 全绿；测试用单库内存引擎（`conftest.py:33-60`），结构上测不出 |
| 与路线关系 | 导入是 P0 里程碑（#929/#933/#937）的核心功能，一旦双库上线即命中 |

**注意**：这不是"依赖倒置"式的设计洁癖问题，而是**生产双库架构下必然引爆的运行时缺陷**，只是被单库开发环境完全遮蔽。

### 2.4 建议处置

1. 改两步法：先在 user 域取 `Position.symbol` / `WatchlistItem.symbol` 的 key 列表，再到 market 域 `Fund.fund_code.in_(keys)` 匹配（保留"持仓优先 → 自选次之"的优先级语义）。
2. **回归用例必须用两个不同 engine 构造双库**（否则与既有单库测试同样测不出），断言不抛错且能命中。
3. 可选加固：静态守卫禁止跨域模型出现在同一 `query()/join()`（当前无守卫）。

---

## 3. 已核查但排除的项（防后人重复怀疑）

| 候选 | 初判 | 核实结论 |
|---|---|---|
| `domains/funds/advisor_catalog.py` 1386 行硬编码数据 | 硬编码坏味道 | **保留**：模块 docstring 明示为"且慢组合元数据**单一真相源**"，供 seed / job / 迁移共用，且区分了"随行情变化"字段并注明以实时抓取为准。属**有意的数据注册表**，非散落硬编码 |
| 46 处裸 `except Exception` | 异常吞噬 | **大部分为合理降级**：逐处核查后确认普遍带 `# noqa: BLE001` + 理由注释（缓存不可用、外部源不可达降级）；`position_service.py:818,931,1065` 为 `logger.exception(...) + raise` 的正确写法。仅少数 `pass` 无注释（`core/requests_patch.py:80`、`watchlist_service.py:395`），不构成结构问题 |
| `cross_domain.py` 无条件全表加载 | 热路径炸弹 | **已由 #1404 修复**且该模块**当前零生产调用方**，与 `tech-debt.md` §16 第 2 条登记一致，不重复开卡 |
| `services/daily_scheduler.py` 依赖 13 个域、`securities_type_backfill.py` 依赖 14 个域 | 上帝模块 | **属设计使然**：调度器与回填脚本的职责就是触达所有域（与 `tools/sync_metadata.py` 同范式）。耦合度由职责决定，不列为问题 |
| 108 处 `commit()` 散落 | 事务边界混乱 | **降级为 P2**：精确扫描显示"单函数内多次 commit"仅 `positions/views.py:create_position`（2 次）一处，不存在大面积"半提交"；真实问题是**范式并存**（见 §5.5） |

---

## 4. P1：分层与依赖方向

### 4.1 视图层承担业务逻辑与事务（#2）

| 文件 | 行数 | DB 调用 | 最大函数 |
|---|---|---|---|
| `domains/ledgers/views.py` | **1811** | 71 | `commit_migration` 218 行 |
| `domains/watchlist/views.py` | **1445** | 45 | `list_items` 104 行 / `_build_holding_row` 103 行 |

`commit_migration`（L1095-1312，218 行）内含：目标校验、跨销售机构软闸门、冲突决议解析、去重/合并策略、**守恒校验**、单事务提交与整体回滚。这些是**业务规则**，不是 HTTP 编排。

**工程影响**：
1. 无法被其他入口复用（CLI / 定时任务 / 导入器要走同一套迁移语义时只能重写）；
2. 无法独立单测 —— 必须起 HTTP 栈；
3. `tech-debt.md` 曾记「自选模块视图层业务逻辑过重 **✅ 已修复 (v4.6.0)**」，而现值为 1445 行 / 45 次 DB 调用 —— 属**债务回潮**，说明当时只做了抽取动作、没有形成防回潮的边界或守卫。

### 4.2 依赖方向失序（#3）

**（a）core 反向依赖 domains**（基础设施层依赖领域层）：

| 位置 | 内容 |
|---|---|
| `core/auth.py:168, 218, 235, 257` | `from app.domains.users.models import User` —— 鉴权中间件直接持有用户领域模型 |
| `core/database.py:401-402` | `_seed_default_identity` 内 `from app.domains.families.models import Family` / `from app.domains.users.models import ROLE_ADMIN, User`，且**种子业务数据硬编码在 core** |

**（b）domains 与 services 双向互引**（包级双向依赖 23 对）：

- `domains.positions ↔ services.position_service`
- `domains.ledgers ↔ services.ledger_service / position_aggregation / sync`
- `domains.watchlist ↔ services.watchlist_service`（其余见附录 A）

"services 依赖 domains.models"是正常的（服务用模型）；但"domains 反向 import services"同时大面积存在，说明**两侧没有确立单向依赖**，`services` 实际是与 `domains` 平级的另一套聚合层，而非"领域之下的服务层"。

**（c）模型双轨**：`app/models/` 仅有 `sync_log.py` 一个模型，其余全部在 `app/domains/*/models.py`。`core/db_factory.py:222` 自注「少量历史模型在 app/models/ 下」，属**已知遗留**，但它是"模型位置"规则的例外，使 `DATA_DOMAIN_REGISTRY` 的登记面横跨两处。

**影响**：`core` 无法脱离领域层独立使用与测试；每新增一处 `core → domains` 引用都会加深 Python 导入期循环风险（当前靠函数内延迟 import 缓解，属"用延迟 import 掩盖的架构问题"）。

---

## 5. P1/P2：可测试性与运行时耦合

### 5.1 全局单例 + 模块级早绑定（#4）

`core/database.py` 的 `SessionLocal` 是模块级单例，而多个 service 在**导入期**就把它绑成模块属性。后果直接写在 `tests/conftest.py` 的注释里：

```python
# tests/conftest.py:86-89
# service 模块在 import 时早绑定了 app.core.database.SessionLocal，
# 而 app fixture 把 app.core.database.SessionLocal 重定向到内存引擎，
# monkeypatch 改模块属性只对 app.core.database 生效，对 service 模块的早绑定无效，
# 会导致 TemperatureService 连到真实库。此处把 service.SessionLocal 对齐到内存引擎
```

`_disable_async_backfill`（conftest.py:104-124）更进一步 —— 测试里硬编码一份"需要打补丁的模块清单"：

```python
for mod_name in (...):
    monkeypatch.setattr(importlib.import_module(mod_name), 'trigger_backfill', _noop, raising=False)
```

**风险**：测试隔离的正确性依赖"新增模块时记得补一条 patch"。漏了不会报错，只会**静默连到开发库**（conftest 注释已明写这一历史故障）。这是"约定式隔离"，且清单维护在测试侧而非被测代码侧。

**另一处同源脆弱点**：`core/database.py:91-98` 的 `_ROUTING_BINDS` 是**全局缓存**，首次建 session 时构建后永久持有 engine 引用；且 `_build_routing_binds()` 会遍历全部表并 `_engine_for()` 两个域 —— 抵消了 #1513 为"不限域入口不因缺驱动崩溃"所做的惰性构造（首次 `SessionLocal()` 即触发两个域引擎构造）。

> **已修复（2026-09-22，#1608）**：本段结论经探针复核**成立**（缺 user 域驱动时首次 `SessionLocal()` 即 `ModuleNotFoundError: pg8000`，被请求的域恰是 user）。修法＝域路由改**查询期按语句解析**（`_domain_for_statement` + `_RoutingSession.get_bind`），`_ROUTING_BINDS` 全局缓存与 `reset_routing_binds()` 一并删除（无引擎缓存即无需失效路径）；第一次 `SessionLocal()` 不再构造非必需域的引擎。本段原文保留以留痕。

### 5.2 事务范式两极并存（#5）

| 范式 | 位置 | 行为 |
|---|---|---|
| 服务内建提交 | `core/database.py:120-133` `BaseRepository.save()/delete()` | 单条写立即 `commit()`，调用方无法组合 |
| 视图内显式单事务 | `ledgers/views.py:1095-1312` `commit_migration` | 手工控制 commit / rollback + 守恒校验 |

两种范式各自都合理，**并存**导致：需要「多服务步骤原子」时无统一机制 —— 走 `BaseRepository` 的路径必然多次提交，走视图单事务的路径又无法复用服务方法。建议明确唯一事务边界策略（视图/服务层二选一持有 transaction，另一侧只 `flush`）。

### 5.3 错误响应绕过统一信封（#6）

`main.py:131-182` 定义了 `{data, message, error_code}` 统一信封与全局处理器，但视图内**自建**错误响应普遍只有两字段。AST 扫描（仅统计 `return jsonify({...}), <status>=400+`）：

- **63 处**错误路径缺 `error_code`，分布：`ledgers/views.py` **32**、`funds/views.py` 7、`summary/views.py` 7、`importers/views.py` 4、`positions/views.py` 4、`temperature/views.py` 3、`assets/views.py` 2、`watchlist/views.py` 2、`securities/views.py` 1、`strategy/views.py` 1；
- 其中 `temperature/views.py:82, 92, 102` 连 `data` 都缺（仅 `{'message': ...}`），直接违反 `{data, message}` 基本信封；
- 另有 `summary/views.py` 六个视图**逐个 try/except** 自建 500 响应，重复实现全局处理器职责。

当前影响偏"契约卫生"（前端仅 `api/search.ts:32` 一处声明了 `error_code`，尚未消费），但一旦前端要用 `error_code` 做错误分支，这 63 处即返回 `undefined`。

### 5.4 规范与文档一致性批次（#7）

| 项 | 事实 | 依据 |
|---|---|---|
| 端点尾斜杠 | 131 个路由中 **18 个无尾斜杠**（`auth/views.py` 的 `/me`、`/logout`；`importers/views.py` 的 5 个；`ocr/views.py` 2 个；`temperature/views.py` 4 个等） | `conventions.md` §2.6「所有 API 端点强制尾部斜杠，杜绝 308 重定向」（🔒 冻结区） |
| `api.md` 滞后 | 文档列 **30 条**端点，实际路由 **131 个** | `api.md` 自称"核心端点清单""随代码演进的事实标准" |
| 日志规范 | `services/nav_service.py:55` 存在 `import logging` | `AGENTS.md`：新代码必须用 loguru，**禁止**新增 `import logging`（唯一例外 `app/__init__.py`） |

### 5.5 测试覆盖缺口（#8）

`services/importer/orchestrator_holdings.py`（**1076 行**）与 `orchestrator_parse.py`（437 行）无直接测试（仅经 `orchestrator.py` 间接调用）。整个后端 1668 个测试函数、CI 跑 `-m "not slow"` 全量、**无覆盖率门槛**。缺失集中在导入编排（也正是 §2 的 P0 所在链路）。

---

## 6. 建议排期

1. **先修 §2**（P0）：改动面小（一个函数两处查询改两步法）、收益明确（解除生产隐患）、且**必须先补双库形态的回归用例**。
2. §4.2（依赖方向）与 §5.2（事务范式）是**同一件事的两面**：确立"domains 为叶子、services 单向依赖 domains、事务由单一层持有"三条规则，再按规则收敛。建议合并为一次架构决策（先落 `decisions.md`，再动代码）。
3. §5.1（测试隔离）建议随 §4.2 一起做：把"模块级早绑定 SessionLocal"改为"从 `core.database` 动态取"，即可删除 conftest 里的例外清单。
4. §5.3 / §5.4 属低风险批量收敛，可在任意窗口顺手做，但**应配守卫**（信封字段 / 尾斜杠本可静态检测），否则必然再次回潮 —— 参照 §4.1 的教训。

---

## 附录 A：包级双向依赖清单（23 对）

```
app.core.auth                     <-> app.domains.users
app.core.database                 <-> app.domains.families
app.core.database                 <-> app.domains.users
app.core.database                 <-> app.models.sync_log
app.domains.assets                <-> app.domains.ledgers
app.domains.funds                 <-> app.services.fund_service
app.domains.ledgers               <-> app.services.ledger_service
app.domains.ledgers               <-> app.services.position_aggregation
app.domains.ledgers               <-> app.services.sync
app.domains.portfolios            <-> app.domains.positions
app.domains.positions             <-> app.domains.transactions
app.domains.positions             <-> app.services.position_service
app.domains.positions             <-> app.services.position_valuation
app.domains.reconciliation        <-> app.services.reconciliation_service
app.domains.summary               <-> app.services.summary_service
app.domains.temperature           <-> app.services.thermometer
app.domains.transactions          <-> app.services.position_service
app.domains.usage                 <-> app.services.ai_recognizer
app.domains.watchlist             <-> app.services.watchlist_service
app.services.bias                 <-> app.services.thermometer
app.services.fund_service         <-> app.services.sync
app.services.importer             <-> app.services.position_service
app.services.sync                 <-> app.services.thermometer
```

## 附录 B：复跑命令

```bash
# 包级依赖矩阵与双向依赖（§4.2）
# 见本报告所用一次性脚本；等价手工方式：
cd backend && python -c "
import ast,pathlib,collections
..."   # 生产代码 import 图

# 错误信封合规（§5.3）：AST 遍历所有 'return jsonify({...}), <int 状态码>'
# 只统计状态码 >= 400 者，缺 data/message/error_code 即命中

# 无尾斜杠端点（§5.4）
cd backend && python -c "
import re,pathlib
pat=re.compile(r'@(\w+)\.(route|get|post|put|patch|delete)\(\s*[\'\\\"]([^\'\\\"]*)[\'\\\"]')
..."

# 双库跨域 join 最小复现（§2.2）
# 两个独立 engine + Session(binds={表:engine}) + before_cursor_execute 观察落库
```
