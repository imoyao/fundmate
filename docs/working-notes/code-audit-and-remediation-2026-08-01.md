# 代码审计与架构整改记录（2026-07-31 ~ 2026-08-01）

> 本文档归集了本轮代码审查、V1 退役清除、接口可用性评估、测试瘦身与 FastAPI 解耦规划的全部工作记录，避免散落于仓库根目录 `docs/`。
> 原始 6 份文档已按章节合并，内容忠实保留。
> 二鸟说 fetcher 重构为独立功能设计文档，见同目录 `erniao-fetcher-redesign-2026-08-01.md`。

## 目录

1. [代码问题审查（初版 2026-07-31）](#sec1)
2. [代码问题审查（深化版 2026-08-01）](#sec2)
3. [V1（`backend/fundmate/`）退役清除分析](#sec3)
4. [`data/` 接口可用性评估](#sec4)
5. [`libs/cal` 与测试目录瘦身](#sec5)
6. [FastAPI 解耦规划（`@bp.input` 自动范式冲突）](#sec6)

---

<a id="sec1"></a>
## 1. 代码问题审查（初版 2026-07-31）


- **日期**：2026-07-31
- **审查范围**：`backend/app/`（后端 124 个 `.py`）与 `frontend/src/`（前端 205 个 `.vue`/`.ts`）
- **规范基准**：`SPEC.md` v4.5.2（项目唯一事实标准）
- **方法**：以 SPEC 硬性红线（§2/§3/§4/§15）为标尺，结合代码静态扫描与关键文件精读，所有结论附 `文件:行号` 证据。

---

## 零、总体结论（TL;DR）

| 等级 | 数量 | 代表性问题 |
|------|------|-----------|
| 🔴 严重（合规/正确性） | 2 | ① 引入 Supabase 云端后端，与 SPEC「本地优先、不上云」硬性规范冲突；② 项目源码零自动化测试，违反 SPEC §2.5 |
| 🟠 高 | 3 | 视图层过重、统一响应契约被 `abort()` 绕过、同一端点返回异构结构 |
| 🟡 中 | 4 | 前端硬编码色值（含涨绿跌红语义反向）、金额组件未全覆盖、ProductDisplay 未全覆盖、usePageRefresh 覆盖不全 |
| 🟢 低 | 5 | 组件内直连 http、残留 SQL 聚合、DEBUG/CORS、会话混用、新功能 SPEC 漂移 |

> **值得肯定的基础**：金融精度核心 `Money` 工具类设计正确，`multiply_price_quantity` 单位换算无误（**SPEC 历史「市值放大 100 倍」致命 Bug 已在服务层修复**）；前端 `api/` 层封装规范；`MoneyDisplay`/`RiseFallText` 组件本身正确实现了「涨红跌绿」。问题主要集中在**规范落地的一致性**而非核心算法。

---

## 一、🔴 严重问题（必须立即决策/处理）

### 1.1 云端后端（Supabase）与「本地优先、不上云」硬性规范冲突  【合规风险】
**违反**：SPEC §1.1、§2.1（核心原则：数据绝对私有、全量本地 SQLite、不上云、不采集）。

**证据**：
- `frontend/src/utils/supabase.ts:1-7` —— 用 `createClient(VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY)` 建立**云端**数据库连接。
- `frontend/src/composables/useSupabaseAuth.ts` 全文件 —— 基于 Supabase 实现 `signUp/signIn/signOut/getSession`，并包含 `migrateExploreData()` 将本地「探市」持仓**写入 Supabase 云端表**（`watchlist_items`/`watchlist_groups`）。
- `frontend/src/App.vue:13,22,25` —— `useSupabaseAuth().initAuthListener()` 在应用启动即激活云端认证监听。
- `frontend/src/utils/auth.ts:4,124-126` —— `removeToken()` 在本地登出时强制调用 `supabase.auth.signOut()`，把本地会话与云端耦合。
- `frontend/src/views/login/index.vue` —— 登录页新增「邮箱注册」模式，直接走 Supabase 账号体系。
- `frontend/src/components/Watchlist/SettingsDrawer.vue:222-224` —— 使用 Supabase 做「探市数据迁移」。

**影响**：
1. 与项目对外承诺的「绝对数据主权、不上云」构成**直接矛盾**，存在合规与用户信任风险。
2. 引入外部云依赖后，本地离线可用性、隐私边界、第三方数据泄露面都发生变化，而 SPEC 未授权该架构。
3. 登录/登出链路被云端账号耦合，若未配置 Supabase 环境变量，核心体验可能异常。

**建议**：作为**最高优先级决策项**——要么（A）在 SPEC 中明确授权「探市」等社交功能使用云端、并界定本地记账数据永不触云；要么（B）将 Supabase 限制为可选/可关闭的扩展功能（环境变量开关 + 未配置时完全不初始化），核心记账保持纯本地。无论哪种，都需补一条 SPEC 决策记录。

### 1.2 项目源码零自动化测试，违反 SPEC §2.5 强制测试规范  【正确性风险】
**违反**：SPEC §2.5（新增/重构接口必须覆盖增删改查、边界、空值、异常、权限分支；提交前 pytest 全量通过方可合并）。

**证据**：全盘扫描 `backend/`，所有 `test_*.py`/`conftest.py` 均位于 `backend/.venv/Lib/site-packages/`（第三方包），**项目自身 `backend/app/` 下无任何测试目录或用例**。SPEC 正文（如 §10）反复引用 `test_ths_otc_cash_format`、`watchlist_service` 测试等，但当前仓库均无对应实现。

**影响**：金融记账工具数据正确性优先级最高（SPEC §14「数据准确性优先级最高」）。没有测试意味着：精度换算、持仓合并、XIRR、赎回费率估算等核心金融逻辑在每次改动后**无法被验证**，回归风险极高，与 SPEC 自述的「全量测试通过方可合并」完全脱节。

**建议**：作为第一象限任务补齐关键路径测试（至少覆盖 `Money` 换算、持仓买卖合并、费率估算、XIRR、自选标准化），建立 `conftest` + 内存 SQLite fixture（SPEC §4.2 要求共用 db fixture）。

---

## 二、🟠 高优先级问题

### 2.1 视图层过重，违反「薄视图、厚服务」架构边界  【架构】
**违反**：SPEC §2.2（薄视图、厚服务）、§4.4（重构彻底性）、§15.3（精准修改）。

**证据**（views 中直接 `db.query` 次数）：`watchlist/views.py:26`、`ledgers/views.py:25`、`strategy/views.py:11`、`positions/views.py:10`、`portfolios/views.py:8`、`assets/views.py:6`、`transactions/views.py:2`。

典型病症 —— `backend/app/domains/positions/views.py`：
- `list_positions()`（:47-104）内联 ORM 查询、原生 SQL 聚合（首次买入确认日）、并**手动拼装响应 dict**，与 `enrich_position_dict()`（:25-36）逻辑大量重复（DRY 违反）。
- `get_position_transactions()`（:107-145）同样在视图里写 SQL + 手工 dict。
- `:110` 混用 `Position.query.get(id)`（Flask-SQLAlchemy 查询接口）与 `with get_db() as db:` 会话，存在会话边界隐患（见 4.4）。

虽 SPEC §10 称自选已「视图层极薄化、抽取至 watchlist_service」，但 `watchlist/views.py` 仍有 26 处 `db.query`，说明重构**并未彻底**。

**影响**：业务逻辑与路由耦合，重构/单测困难，易 reintroduce Bug；与 SPEC 宣称的架构不一致。

### 2.2 统一响应契约 `{data, message}` 被 `abort()` 绕过  【契约/UX】
**违反**：SPEC §1.3（统一手动返回 `{data, message}`）、决策记录 2026-06-14「将所有 abort 替换为 jsonify」。

**证据**：
- 全代码约 **70 处 `abort(...)`**（如 `positions/views.py:112,176,201,224`；`watchlist/views.py` 大量；`ledgers/views.py` 大量）。
- `backend/app/main.py:87-134` 注册的错误处理器仅覆盖 `SBException`/`ValueError`/404/500，**未覆盖 `abort()` 抛出的 `HTTPException`**。因此 `abort(400, msg)` 走 APIFlask 默认错误体（含 `message` 但**无 `data` 字段**），而前端 `api/*` 与组件普遍假设 `{data, message}` 结构（见 `frontend/src/api/watchlist.ts`、`http/index.ts` 直接返回 `response.data`）。

**影响**：错误时前端取到 `res.data` 为 `undefined`，错误提示丢失或页面解析异常；与「统一响应契约」自相矛盾。

**建议**：统一封装 `error_response(message, code)` 替代所有 `abort()`；或在 `main.py` 增加 `@app.errorhandler(HTTPException)` 全局兜底，将其重写成 `{data:null, message:...}`。

### 2.3 同一端点返回异构响应结构  【契约】
**证据**：`backend/app/domains/positions/views.py`：
- `group_by=account` 分支返回 `{'data': {账户: [...]}}`（:99，dict）；
- 分页分支返回 `{'data': [...], 'total','page','per_page'}`（:104，list）。

**影响**：前端需对同一个 `/api/positions/` 做两种结构分支判断，易引发 `undefined`/白屏，且违背 SPEC §2.4「对外 API 完全兼容、结构定型不可变动」精神。

---

## 三、🟡 中优先级问题

### 3.1 前端硬编码十六进制色值 + 涨绿跌红语义反向  【规范/正确性】
**违反**：SPEC §3.1（禁止 `#xxxxxx` 硬编码，全部用语义变量）、§3.12（禁止直接调 `--brand-*`）、金融语义「涨红跌绿」。

**证据与重点**：
- **语义反向（正确性 Bug）**：`frontend/src/views/account/InvestmentAnalysis.vue:113`
  `color: (params) => (params.value >= 0 ? "#22c55e" : "#ef4444")` —— 盈利用**绿色(#22c55e)**、亏损用**红色(#ef4444)**，与 SPEC「红=涨/盈利、绿=跌/亏损」**正好相反**。同文件 :138-142 图表配色亦为硬编码 hex。
- 大量硬编码 hex：`AccountOverview.vue:2,224`、`SystemSettings.vue:226`、`AssetManagement.vue:322,465`、`layout/index.vue:33,62,245`、`lay-setting/index.vue` 多行、`explore/index.vue` 多行、`RealtimeStatusIndicator/index.vue:80`（注释里直接写 `#7BC49A`）。
- 直接使用 `--brand-*`（违反 §3.12「涨跌必须用 `--color-rise`/`--color-fall`」）：`welcome/index.vue:129,130,189,577,829,945`、`explore/index.vue:1212,1530,1688,1689`、`watchlist/index.vue:139,140,190,312,709,1803-1927`。
- 正面：`MoneyDisplay/index.vue`、`RiseFallText/index.vue` 已正确使用 `var(--color-rise, #e34f38)` / `var(--color-fall, #7bc49a)`，组件本身是对的——问题在**没被全站采用**（见 3.2）。

### 3.2 金额/涨跌幅未统一使用 `MoneyDisplay` / `RiseFallText`  【规范红线】
**违反**：SPEC §3.11.1/§3.11.2 红线「所有金额/收益率展示必须使用组件，禁止手写格式化」。

**证据**（手写 `toLocaleString()`/`toFixed()`/`±`）：
- `TransactionList.vue:134,139,208,239,245`
- `strategies/index.vue:38,44,59,62,94,100,108`
- `ledgers/index.vue:69,73,76,119,139,156,202,237,256,275`
- `portfolio/detail.vue:67,73,77,82,119,124,131`
- `ledgers/detail.vue:90,117,150,172,273,294,317,430,444`
- `watchlist/index.vue:264,269,282,294`（部分已用组件，部分仍手写）

**影响**：手写格式化无法保证与 `MoneyDisplay` 完全一致的千分位/符号/涨跌色，且 `strategies`/`portfolio/detail` 自行判断正负并上色，存在与「涨红跌绿」再次不一致的风险；违反 SPEC 编码红线。

### 3.3 `ProductDisplay` 复合列未全站覆盖  【规范】
**违反**：SPEC §3.8 / §3.11.4（资产/持仓表格「名称+代码+类型」复合列必须用 `ProductDisplay`）。

**证据**：`ProductDisplay` 仅被 `inventory`、`ledgers/detail`、`watchlist`、`AssetPanorama` 使用；而 `strategies/index.vue`、`portfolio/detail.vue`、`TransactionList.vue` 的持仓/资产表格**疑似手写**产品单元格（无 `ProductDisplay` 导入）。需进一步确认，但按现有证据属于覆盖缺口。

### 3.4 `usePageRefresh` 未覆盖全部数据页  【规范】
**违反**：SPEC §3.11.5 / §10（新增页面必须接入，目前仅账户详情页与全面盘点页）。

**证据**：仅 `ledgers/index.vue:539`、`ledgers/detail.vue:1198` 使用；自选、交易流水、仪表盘等数据页未接入。记账后这些页面可能出现「数据不刷新」的老问题复现。

---

## 四、🟢 低优先级 / 技术债

### 4.1 `portfolio/detail.vue` 组件内直连 http  【规范】
**违反**：SPEC §4.5（所有请求封装在 `src/api`）。
**证据**：`frontend/src/views/asset/portfolio/detail.vue:351` `const res = await http.request("get", "/api/performance/xirr/", {...})`。应下沉到 `api/performance.ts`（该文件已存在对应封装，却未复用）。

### 4.2 残留 SQL 市值聚合  【技术债】
**证据**：`backend/app/services/ledger_service.py:237` `order_by(desc(Position.current_price * Position.quantity / 10000.0))`。
**说明**：当前单位下 `/10000` → 分，与 `Money.multiply_price_quantity`（同除 10000）**数值一致**，**并非**历史「100 倍放大」Bug（该 Bug 已在服务层修复）。但 SPEC §10/决策 2026-06-18 明确要求「移除所有 SQL 市值聚合、统一 Python 聚合」，此处属于**未清理干净**的残留，存在单位口径漂移时的隐性风险。

### 4.3 `DEBUG=True` 与 `CORS='*'`  【运维/安全】
**证据**：`backend/app/main.py:47` `app.config['DEBUG'] = True`；`:57-61` 默认 `CORS origins='*'`。本地个人工具风险可控，但属不应提交到非本地环境的状态，建议用环境变量约束。

### 4.4 会话混用 `Position.query.get()` 与 `get_db()`  【健壮性】
**证据**：`positions/views.py:110` 在 `with get_db() as db:` 内调用 `Position.query.get(id)`。两套查询接口可能绑定不同 Session，存在「对象附加到另一会话」的潜在异常。建议统一用 `db.get(Position, id)`。

### 4.5 新功能（探市/涨跌温度）SPEC 漂移  【治理】
`explore/`、`temperature/` 域及「探市」社交能力在 SPEC 中无对应章节，且探市依赖云端 Supabase（与 1.1 关联）。建议要么补入 SPEC 决策记录，要么收缩范围，避免规范与实现持续脱节。

---

## 五、做得好的地方（正面）

- **金融精度核心正确**：`core/money.py` 设计严谨（Decimal、ROUND_HALF_UP、因子常量），服务层 `multiply_price_quantity` 单位换算无误，历史致命市值 Bug 已修复。
- **API 封装规范**：前端 `src/api/*` 全部经 `http` 封装（仅 1 处组件内直连，见 4.1），符合 SPEC §4.5。
- **通用组件实现正确**：`MoneyDisplay`/`RiseFallText` 正确实现「涨红跌绿」与语义变量引用，是后续全站推广的可靠基础。
- **`usePageRefresh` 机制设计合理**：基于 `mitt` + 生命周期自清理，已落地于两个核心页面。
- **领域分层骨架清晰**：`domains / services / core / models` 分层方向正确，服务层已沉淀 `ledger_service`/`position_service`/`watchlist_service`/`fund_service` 等。

---

## 六、下一步工作优先级与计划（按 SPEC §9.1 四象限）

### 🔴 第一象限｜重要且紧急（建议 48h 内闭环）
1. **决策 Supabase 云端定位（1.1）**：与用户确认「探市」云端功能是否授权；输出 SPEC 决策记录；未配置环境变量时禁止初始化云端客户端，确保核心记账零云依赖。
2. **建立测试地基（1.2）**：补齐 `Money` 换算、持仓买卖合并、费率估算、XIRR 的最小测试集 + `conftest` 内存 SQLite fixture；CI 强制 pytest。

### 🟠 第二象限｜重要不紧急（固定排期）
3. **统一错误响应（2.2）**：封装 `error_response()` 替换全部 `abort()`，或在 `main.py` 增加 `HTTPException` 兜底，保证 `{data, message}` 契约一致。
4. **视图层瘦身（2.1）**：将 `positions/views.py`、`watchlist/views.py`、`ledgers/views.py` 中的内联 ORM/SQL/手工 dict 抽取到对应 Service；消除 `enrich_position_dict` 与内联逻辑的重复。
5. **规范端点响应结构（2.3）**：`list_positions` 的 `group_by` 与分页统一为同一信封结构（或拆为独立端点）。
6. **前端规范落地专项**：
   - 全站金额/涨跌幅改用 `MoneyDisplay`/`RiseFallText`（3.2）；
   - 所有资产/持仓表格产品列改用 `ProductDisplay`（3.3）；
   - 清除硬编码 hex 与 `--brand-*`，统一语义变量；**重点修正 `InvestmentAnalysis.vue` 涨绿跌红反向**（3.1）；
   - 新数据页接入 `usePageRefresh`（3.4）。

### 🟡 第三象限｜不重要但紧急（极简快速修）
7. `portfolio/detail.vue:351` 改用 `api/performance.ts` 封装（4.1）。
8. `positions/views.py:110` 改用 `db.get(Position, id)`（4.4）。
9. `DEBUG`/`CORS` 改用环境变量约束（4.3）。

### 🟢 第四象限｜不重要不紧急（延后归档）
10. 清理 `ledger_service.py:237` 残留 SQL 聚合（4.2）。
11. 将 `explore`/`temperature` 纳入 SPEC 或收缩范围（4.5）。
12. 端到端验证 UI 暗色模式与「涨红跌绿」一致性（SPEC §11）。

---

## 附录：证据索引（file:line）

| 问题 | 关键证据 |
|------|---------|
| 1.1 云端后端 | `utils/supabase.ts:1-7`；`composables/useSupabaseAuth.ts`（全）；`App.vue:13,22,25`；`utils/auth.ts:4,124-126`；`login/index.vue`；`Watchlist/SettingsDrawer.vue:222-224` |
| 1.2 无测试 | `backend/app/` 无 `tests/`；全盘 `test_*.py` 仅在 `.venv` |
| 2.1 视图过重 | `watchlist/views.py:26`、`ledgers/views.py:25`、`positions/views.py:47-104,110` |
| 2.2 abort 绕契约 | `main.py:87-134`（无 HTTPException 处理）；约 70 处 `abort()` |
| 2.3 异构响应 | `positions/views.py:99` vs `:104` |
| 3.1 色值/语义 | `InvestmentAnalysis.vue:113`（绿涨红跌反向）、`:138-142`；`welcome/index.vue:129,130`；`watchlist/index.vue:139,190` |
| 3.2 金额组件 | `TransactionList.vue:134,139`；`strategies/index.vue:38,44`；`ledgers/index.vue:69,73`；`portfolio/detail.vue:67,73` |
| 3.3 ProductDisplay | 使用面：`inventory`/`ledgers/detail`/`watchlist`/`AssetPanorama`；缺口：`strategies`/`portfolio/detail`/`TransactionList` |
| 3.4 usePageRefresh | `ledgers/index.vue:539`、`ledgers/detail.vue:1198`（仅两处） |
| 4.1 直连 http | `portfolio/detail.vue:351` |
| 4.2 残留 SQL 聚合 | `ledger_service.py:237` |
| 4.3 DEBUG/CORS | `main.py:47,57-61` |
| 4.4 会话混用 | `positions/views.py:110` |

---

<a id="sec2"></a>
## 2. 代码问题审查（深化版 2026-08-01）


> 本文是对 `2026-07-31` 初稿的**修订与深化**。初稿有两处事实性误判，已在此更正（见 §0）。
> 审查对象：后端 `backend/app/`（V2 目标架构）、前端 `frontend/src/`、以及与代码现状的偏差。
> 规范基准：`SPEC.md`（v4.5.2）。

---

## §0 对初稿的重要更正（先纠错）

1. **“零测试”是错误结论，郑重更正**。
   `backend/tests/` 存在完整且高质量的 V2 测试体系，且直接锁定了金融核心逻辑：
   - `tests/core/test_money.py` —— 覆盖 `yuan_to_cents / cents_to_yuan / shares_to_min_unit / min_unit_to_shares / parse_nav / multiply_price_quantity`（含 `1050×1001234→105130`、负数、四舍五入边界）。
   - `tests/domains/test_portfolios.py` —— 断言 `market_value == 1200.0`。
   - `tests/domains/test_ledgers.py` —— 断言 `total_market_value` 多场景聚合。
   - `tests/domains/test_summary.py / test_watchlist.py / test_positions.py / test_funds.py` —— 覆盖汇总、自选、持仓、基金。
   初稿误把“测试文件在 `.venv` 之外未找到”当成“没有测试”，这是我的检索失误，特此致歉。

2. **“ledger_service 有原始 SQL / SQL 注入风险”是误读，更正**。
   实际 `app/services/ledger_service.py` 全篇使用 **SQLAlchemy ORM + `func.sum` + `Money` 整数运算**，没有任何字符串拼接 SQL，不存在注入风险。初稿所谓“残留 `/10000` SQL 聚合”是读错文件位置所致，实际代码精度正确。

---

## §1 测试的真实状态（基于 `pytest --co` 实测）

- **收集结果**：`524` 个测试被收集成功，但 **19 个遗留 V1 模块收集失败**，整套件当前无法正常跑绿（`Interrupted: 19 errors during collection`）。
- **19 个错误的根因（全部在遗留 V1 `fundmate.*` 测试）**：
  - `backend/fundmate/errors.py:201` `class NotHundredPercentSumPortionError(HTTPUserInputError)` —— **`HTTPUserInputError` 未定义，导入即 `NameError`**，连带拖垮所有 import `backend.fundmate.errors` 的测试（含 `test_errors.py`、所有 `data/*` 测试）。
  - 缺失测试依赖：`pyjson5` / `faker` / `plummet`（未装进 `.venv`）。
  - 缺失环境变量：`dkhs / zo / utils` 等测试触发 `environs.exceptions.EnvError`。
- **🔴 最关键风险：测试没有覆盖真正部署的代码**。
  - 生产入口 `backend/autoapp.py:4` → `from backend.fundmate.app import create_app`（**V1 遗留应用**，标题“多倍贝 API v1.0.0”，含 flask-praetorian / sentry / mail）。
  - 测试 `backend/tests/conftest.py:25` → `from app.main import create_app`（**V2 应用**）。
  - 结论：**线上跑的是 V1，测试跑的是 V2**。V2 的测试全绿，也不代表线上 V1 正确——而 V1 此刻还带着 `errors.py` 的 `NameError` 真实缺陷。

---

## §2 问题清单（按严重性排序 + 优化建议）

### 🔴 严重（必须立即决策/处理）

**S1. 双代码库：部署(V1) 与 测试目标(V2) 错位 —— 头号架构风险**
- 证据：`autoapp.py:4`（V1）、`app/main.py:39`（V2）、`app/` 与 `fundmate/` 并存；两套 conftest（`conftest.py`→V2，`conftest_fm.py`→V1）。
- 影响：SPEC 描述的是 V2 架构，但线上仍是 V1；V1 含真实 `NameError`，且无人用测试护航。规范与现状严重脱节。
- **优化建议**：
  1. 明确迁移裁决：V2 `app/` 是否就是下一代 runtime？若是，将 `autoapp.py` 改为 `from app.main import create_app`，并在部署前让 V2 测试全绿。
  2. 若 V2 尚未就绪，则**至少先修 V1 `errors.py` 的 `NameError`**（把 4 个类改为继承 `HTTPUserInputError` 的真实基类或本地定义），让 V1 测试可跑，避免“带缺陷上线且无测试”。
  3. 设定清除 `fundmate/` 的时间盒（SPEC §4.7），迁移完成即删除，杜绝双代码库长期共存。

**S2. 遗留 V1 `fundmate/errors.py:201` NameError（真实缺陷）**
- 证据：`:201/:206/:211/:216` 四个类均继承未定义的 `HTTPUserInputError`。
- **优化建议**：定义 `class HTTPUserInputError(ThirdPartError)` 或在 `fundmate/errors.py` 顶部补齐基类；加一个 `import` 冒烟测试防止回归。

### 🟠 高（影响契约一致性 / 正确性保障）

**H1. 错误响应契约不统一（~65 处 `abort()` 绕过 `{data,message}` 信封）**
- 证据：`app/` 内 `abort()` 计数：watchlist 21、ledgers 14、importers 7、positions 5、portfolios 5、strategy 4、assets 3、utils 3、performance 3（共 65）。
- 根因 1：`app/main.py:87` 的 `register_error_handlers` **只在模块级 `app` 上调用（`:138`），并未放进 `create_app()` 内部**。因此测试客户端 `create_app()` 得到的实例**完全没有自定义错误处理器**，错误退回 APIFlask 默认体（缺 `data`/`error_code`）。
- 根因 2：`abort()` 抛出 `HTTPException`，而 `main.py` 未注册 `HTTPException` 处理器，返回体无 `data` 字段，前端按 `{data,message}` 解析会丢提示。
- SPEC 早已在 `2026-06-14` 决策“禁止 `abort()`、改用统一 `jsonify({data,message})`”，但代码仍大量违反。
- **优化建议**：
  1. 把 `register_error_handlers(app)` 移入 `create_app()` 内（优先，低成本高收益）。
  2. 增加 `@app.errorhandler(HTTPException)` 归一化器，将任何 `abort()` 响应包成 `{data:null, message, error_code}`。
  3. 逐步将 `abort()` 替换为抛 `SBException`（已有 `ErrorCode` 枚举），彻底统一。

**H2. 视图层偏重 + 持仓表示双路径**
- 证据：`positions/views.py:25` `enrich_position_dict` 定义在视图层；`list_positions` 的 `group_by=account` 分支（`:49-99`）**手写另一套 dict 拼装**，与 `enrich_position_dict` 逻辑重复、字段可能漂移。
- 影响：同一资源两种序列化路径，极易出现“分组视图与分页视图字段不一致”。
- **优化建议**：`group_by=account` 复用 `enrich_position_dict`；展示型转换统一下沉到 schema（`PositionOut`）或 service，视图只做编排。与 SPEC §2.2“薄视图厚服务”对齐。

### 🟡 中

**M1. 前端涨绿跌红反向（演示页违规范）**
- 证据：`views/account/InvestmentAnalysis.vue:58-69` 用 `text-green-600` 表示正收益、`text-red-600` 表示回撤；`:113` `params.value>=0 ? "#22c55e" : "#ef4444"`——**绿色=涨、红色=跌，与 SPEC §3.1“涨红跌绿”正好相反**；且硬编码 hex 违反 §3.1/§2.12（禁用 `#hex`、须用 `--color-rise/--color-fall`）。
- 注：该页为硬编码数据的演示/占位页（日期写死 2023、数值写死），但作为仓库内样例会误导后续开发，且违反硬红线。
- **优化建议**：改用 `MoneyDisplay`/`RiseFallText`（自带涨红跌绿）或 `--color-rise/--color-fall`；删除硬编码 hex 与 `#f5f5f5` 背景（`:224`）。

**M2. 金额/涨跌组件未全量覆盖**
- 证据：`TransactionList`、`strategies`、`ledgers`、`portfolio/detail` 等多页仍手写 `toLocaleString()`/`toFixed()`。
- **优化建议**：按 SPEC §3.11 红线，全站替换 `MoneyDisplay`/`RiseFallText`；可由 ESLint 规则（`no-restricted-syntax` 禁 `toLocaleString` 出现在模板）兜底。

**M3. 持仓身份解析脆弱（dual lookup）**
- 证据：`position_service.py:164-177` 先按 `(symbol, ledger_id)` 找 `same`，再按 `(symbol, account_name)` 找 `existing_position`，两条路径可能指向不同记录，存在“同一标的建出重复持仓”的隐患。
- **优化建议**：统一身份键（推荐 `ledger_id + normalized_symbol`），去掉冗余二次查询；缺失时显式报错而非静默新建。

**M4. `get_positions_paginated` 全量加载两次（性能）**
- 证据：`ledger_service.py:236-245` 先 `offset/limit` 取本页，又 `db.query(...).all()` 全量加载算 `total_mv`，O(n) 额外开销。
- **优化建议**：用 `func.sum(Money.multiply_price_quantity(...))` 单条聚合 SQL 求总市值；`get_overview_stats`（`:26-41`）同样可在 SQL 层聚合，避免 Python 全表遍历。

### 🟢 低（可纳入技术债，按时间盒处理）

- **L1** `traceback.print_exc()` 出现在视图层（`positions/views.py:173/178/183`、`portfolios/views.py:69`）——改 `logger.exception(...)`，避免生产 stderr 噪声且丢失结构化日志。
- **L2** 旧式 `db.query(Position).get(id)`（`positions/views.py:110`、`fund_service.py:190`）—— SQLAlchemy 2.0 应为 `db.get(Position, id)`。
- **L3** `app/main.py:47` `DEBUG=True`、`57-59` `CORS_ORIGINS` 缺省 `*`——生产配置硬编码风险；改为读环境变量且默认收紧。
- **L4** 前端 `portfolio/detail.vue:351` 组件内直连 `http`——违反 SPEC §4.5，应收到 `src/api`。
- **L5** `backend/invest.db`、`invest.db-shm/wal`、`htmlcov`、`*.sqbpro` 落在仓库根——应加入 `.gitignore`，避免提交真实数据库与覆盖率产物。

---

## §3 SPEC 与代码现状的关键偏差（需更新 SPEC，见 §4）

| 位置 | SPEC 现状 | 代码现实 | 建议 |
|---|---|---|---|
| §1.2 / §2.1 不上云 | 绝对“不上云、不采集、不泄露” | 已接入 Supabase：**仅同步自选（watchlist_items/groups）** + Supabase Auth；核心记账（positions/transactions/assets/ledgers）仍本地 | 改为“数据分级”：核心账本永不上云；自选/社交类非敏感数据可云端同步，且须用户显式开启 |
| §10 / §12 市值 100× | “分母应为 1,000,000 而非 10,000” | **笔误**。当前 `Money.multiply_price_quantity = price_cents×quantity_units/SHARE_FACTOR(10000)` 正确，且被 `test_money.py` 锁定 | 更正笔误，明确“禁止把代码改成 ÷1e6，否则将引入真实 100× 错误” |
| §2.5 测试 | “提交前 pytest 全量通过” | 套件当前 19 模块收集失败、且测试跑的是 V2 而非线上 V1 | 增补：套件须跑绿；测试须覆盖**部署版本**；双代码库未合并前须明确哪套是权威 |
| §2.2 架构 | 仅描述 V2 `app/` | 实际 `fundmate/`(V1) 才是 runtime | 增补“双代码库 + 迁移状态”说明 |

---

## §4 下一步优先级与计划（对齐 SPEC §9.1 四象限）

**第一象限｜重要且紧急（建议 48h 内闭环）**
1. 修 `fundmate/errors.py:201` NameError（S2）—— 让 V1 测试至少能跑、消除线上隐患。
2. 决策双代码库走向（S1）：明确 V2 是否接管 runtime；若接管，切换 `autoapp.py` 并跑绿 V2 测试。
3. 把 `register_error_handlers` 移入 `create_app()`（H1 根因1）—— 低成本修复错误契约。

**第二象限｜重要不紧急（固定排期）**
4. 让测试套件整体跑绿：补 `pyjson5/faker/plummet` 依赖、补 env 样例、隔离/移除损坏的 V1 测试。
5. 统一错误契约：加 `HTTPException` 归一化器 + 逐步废 `abort()`（H1）。
6. 视图瘦身：`group_by=account` 复用 `enrich_position_dict`，展示转换下沉（H2）。
7. 前端规范落地专项：修 `InvestmentAnalysis.vue` 反向色 + 清 hex（M1）；`MoneyDisplay/RiseFallText` 全量覆盖（M2）；`usePageRefresh` 覆盖自选/交易流水页。
8. 性能：聚合 SQL 化（M4）、持仓身份统一键（M3）。

**第三象限｜不重要但紧急**
9. L1/L2/L3/L5 零碎修复（logger、SQLAlchemy 2.0、`DEBUG`/`CORS`、`.gitignore`）。

**第四象限｜不重要不紧急**
10. L4 组件内直连 http 收口；演示页整体重做或删除。

---

## §5 附录：证据索引（file:line）

- 双代码库：`backend/autoapp.py:4`(V1) · `backend/app/main.py:39`(V2) · `backend/tests/conftest.py:25`(V2) · `backend/tests/conftest_fm.py:21`(V1)
- V1 真实缺陷：`backend/fundmate/errors.py:201,206,211,216`
- 错误契约：`backend/app/main.py:87-138`（处理器在 `create_app` 外）· `app/` 内 `abort()` 共 65 处（watchlist21/ledgers14/importers7/positions5/portfolios5/strategy4/assets3/utils3/performance3）
- 视图偏重：`backend/app/domains/positions/views.py:25,49-99`
- 性能：`backend/app/services/ledger_service.py:236-245,26-41`
- 持仓身份：`backend/app/services/position_service.py:164-177`
- 前端反向色：`frontend/src/views/account/InvestmentAnalysis.vue:58-69,113,224`
- 云端范围：`frontend/src/composables/useSupabaseAuth.ts:126-179`（仅 watchlist 表）
- 测试覆盖：`backend/tests/core/test_money.py` · `tests/domains/test_portfolios.py` · `test_ledgers.py` · `test_summary.py` · `test_watchlist.py`

---

<a id="sec3"></a>
## 3. V1（`backend/fundmate/`）退役清除分析


> 评估对象:`backend/fundmate/`(V1 旧架构) 是否仍有存在必要
> 对比基准:`backend/app/`(V2 重构版,见 SPEC)
> 日期:2026-08-01

---

## 0. 对上一轮结论的更正(重要)

上一轮我说"**生产运行时跑的是 V1**",这是**错误结论**,特此更正。

我当时只看了 `backend/autoapp.py`(它 `from backend.fundmate.app import create_app`),就推断生产 = V1。但遗漏了 README 的启动命令。实际真相:

- **README.md:37 写明启动方式**:`pdm run flask --app app.main:app run --debug --host 0.0.0.0 --port 8000` —— 这是 **V2 (`backend.app.main`)**。
- `backend/app/main.py:137` 在模块级暴露了 `app = create_app()`,因此 `app.main:app` 是标准的 `flask`/`gunicorn` 入口目标。
- `backend/autoapp.py`(→ V1)是**陈旧残留入口**,并非项目实际运行方式,且 `backend/` 下**没有** `wsgi.py`/`manage.py`/`gunicorn.conf.py` 等其它入口,README 也未引用它。

**更正后的判断:V1 是已被 V2 全面取代的遗留代码,而不是生产系统。** 用户"V1 是残留、考虑清除"的直觉是正确的。

---

## 1. 结论摘要

**V1 (`backend/fundmate/`) 没有必要继续存在,应按"受控退役"流程清除,而非盲目 `rm -rf`。**

理由(证据见第 2 节):
1. 整个开发生态——**前端 API 契约、README 启动命令、测试 conftest、数据库模型**——全部指向 V2。`autoapp.py` 指向 V1 只是过时入口。
2. 前端 `src/api/` 的模块(positions/ledgers/portfolios/securities/temperature/strategy/summary/performance/importer/watchlist/assets)与 **V2 的 domains 一一对应**,而 V1 的蓝图是 `/accounts` `/collections` `/funds` `/users`——**前端根本不消费 V1 的接口**。
3. V2 拥有**完全独立、不 import `fundmate` 的数据库模型与表结构**(assets/ledgers/positions/portfolios/transactions/securities/...),与 V1 的表(Account/Collection/Fund/InvestProduct/...)是两套管。

**唯一需要前置处理再删的部分**(第 3 节):
- V1 `data/` 子系统有 **11 个数据源 V2 尚未移植**(danjuan / chinawealth / dkhs / fundb / sipf / yzyx / jq / jsl / amac / tencentwm / ten_jqka),需做数据源覆盖审计后决定移植或正式废弃。
- V2 的测试 `tests/libs/cal/test_rate_of_return.py` **import 了 `backend.fundmate.libs.cal`**,删除 V1 前必须把 `libs/cal` 迁入 V2 core。

---

## 2. 证据链

### 2.1 真实入口是 V2,`autoapp.py` 是陈旧残留
| 证据 | 位置 |
|---|---|
| README 启动命令指向 V2 | `README.md:37` → `flask --app app.main:app` |
| V2 模块级暴露 app 入口 | `backend/app/main.py:137` → `app = create_app()` |
| V1 陈旧入口(不被 README 引用) | `backend/autoapp.py:4` → `from backend.fundmate.app import create_app` |
| 无其它入口 | `backend/` 下无 `wsgi.py`/`manage.py`/`gunicorn.conf.py` |

### 2.2 前端契约 = V2,不消费 V1 接口
- V1 蓝图前缀(`backend/fundmate/*/views.py`):`/accounts`、`/collections`、`/funds`、`/users`
- 前端 `frontend/src/api/` 模块:`assets.ts`、`funds.ts`、`importer.ts`、`ledger.ts`、`performance.ts`、`portfolio.ts`、`positions.ts`、`securities.ts`、`strategy.ts`、`summary.ts`、`temperature.ts`、`transactions.ts`、`user.ts`、`watchlist.ts`
- 结论:前端全部按 V2 的 domain 命名组织,**V1 的四个蓝图无人调用**。

### 2.3 V2 数据库模型完全独立
- V2 表名(节选,`backend/app/**/models.py`):`assets` / `ledgers` / `positions` / `portfolios` / `transactions` / `securities` / `price_history` / `watchlist*` / `strategy_tags` / `market_composites` / `fund_companies` / `fund_managers` ...
- V1 表名(节选):`Account` / `AccountTransactionRecord` / `Collection` / `CategoriesOfCollection` / `Fund` / `Manager` / `InvestProduct` / `FeeRatio` ...
- V2 的 `app/models/` **没有任何文件 import `fundmate`**(已 grep 确认)→ 两套独立 schema。

### 2.4 测试指向 V2,但存在一处耦合
- 激活的 `backend/tests/conftest.py` → `backend.app.main.create_app`(V2)。`conftest_fm.py`(V1)不被 pytest 自动发现。
- **耦合点**:`backend/tests/libs/cal/test_rate_of_return.py:14` → `from backend.fundmate.libs.cal import rate_of_return`。V2 测试依赖 V1 的 `libs/cal`,删除前需迁移。

### 2.5 V1 体量(量化)
- `backend/fundmate/` 共 **157** 个 `.py` 文件。
- `data/` 子系统 **66** 个 `.py`,覆盖 **20+** 外部数据源(见第 3.1 节列表)。
- `migrations/` 仅 **1** 个版本文件,且 `env.py:98` 引用 `backend.fundmate.custom_sql_types` 与 `backend.migrations.choices`(V1 schema 绑定)。V1 实际用 `commands.py:39,47` 的 `db.drop_all()+create_all()` 管 schema(破坏性,见第 4 节)。

---

## 3. 删除前必须处理的部分(Load-bearing)

### 3.1 V1 `data/` 数据源覆盖缺口
对 V1 的 20+ 数据源逐一在 `backend/app/` 检索引用(grep 计数):

| 数据源 | V1 提供 | V2 是否覆盖 | 备注 |
|---|---|---|---|
| eastmoney(东方财富) | ✅ | ✅ 6 files | akshare/xalpha 覆盖 |
| xalpha | ✅ | ✅ 9 files | V2 核心回测/净值 |
| akshare | ✅ | ✅ 13 files | V2 主抓取引擎 |
| qieman(且慢) | ✅ | ✅ 4 files | 组合/策略 |
| zo(且缓?) | ✅ | ✅ 4 files | 组合/策略 |
| howbuy(好买) | ✅ | ✅ 2 files | 组合 |
| baostock | ✅ | ✅ 2 files | 行情 |
| alipay(支付宝) | ✅ | ✅ 4 files | 账单导入 |
| **danjuan(蛋卷)** | ✅ | ❌ 0 files | **组合/估值,需审计** |
| **chinawealth(中国财富/银行理财)** | ✅ | ❌ 0 files | **净值/理财,需审计** |
| **dkhs(东方财富基金费率)** | ✅ | ❌ 0 files | **费率,需审计** |
| **fundb(集思录)** | ✅ | ❌ 0 files | **需审计** |
| **sipf** | ✅ | ❌ 0 files | **需审计** |
| **yzyx** | ✅ | ❌ 0 files | **需审计** |
| **jq(聚宽)** | ✅ | ❌ 0 files | **需审计** |
| **jsl(集思录论坛)** | ✅ | ❌ 0 files | **需审计** |
| **amac(基金业协会)** | ✅ | ❌ 0 files | **需审计** |
| **tencentwm(腾讯理财通)** | ✅ | ❌ 0 files | **需审计** |
| **ten_jqka(同花顺)** | ✅ | ❌ 0 files | **需审计** |

> 注:上表"V2 覆盖"为代码引用计数代理,非功能等价证明。由于**前端契约已是 V2 且 V2 自有 `market_composites`/`strategy` 表**,蛋卷/且慢等"组合"能力大概率为 V2 已内置;但 dkhs 费率、chinawealth 理财净值等**可能仍有独立用途**,需做一次性数据源用途审计后再决定移植或废弃。

### 3.2 `libs/cal`(收益率计算)被 V2 测试引用
- `backend/tests/libs/cal/test_rate_of_return.py` 直接 import `backend.fundmate.libs.cal`。
- 处置:把 `fundmate/libs/cal/` 整体迁入 `backend/app/core/cal/`(或 `backend/app/libs/cal/`),更新该测试 import,再删 V1。

### 3.3 `migrations/` 与 V1 schema 绑定(可随 V1 一同删除)
- V1 `migrations/` 仅 1 个版本文件,且 `env.py` 硬编码引用 `backend.fundmate.custom_sql_types`。
- V2 当前**无任何 migrations 目录**(已确认 `app/` 下无 `alembic.ini`/`env.py`)。V1 迁移对 V2 无意义,可删;但 V2 亟需建立自己的 alembic 迁移(见第 5 节 Phase 4)。

---

## 4. 历史债务清单(清除对象)

| 债务项 | 位置 | 风险/说明 |
|---|---|---|
| 陈旧入口 `autoapp.py` 指向 V1 | `backend/autoapp.py:4` | 误导性,易让人误以为 V1 在生产 |
| V1 整套 `fundmate/` 包 | `backend/fundmate/`(157 .py) | 遗留系统,与 V2 双轨 |
| V1 测试树 + `conftest_fm.py` | `backend/tests/**`(V1 部分) | 19 个收集错误,`errors.py:201` 未定义 `HTTPUserInputError` 的 NameError 真实缺陷 |
| 双 conftest 共存 | `tests/conftest.py`(V2) + `tests/conftest_fm.py`(V1) | 测试归属混乱 |
| `init_db` 破坏性 `db.drop_all()` | `fundmate/commands.py:39,47` | 误跑 `flask init-db --drop` 会清空库(删除 V1 后自然消失) |
| V1 `migrations/` 绑定 V1 schema | `backend/migrations/` | 随 V1 删除 |
| 两套包导致依赖臃肿 | `pyproject.toml` 同时服务 V1/V2 | 清理后可瘦身 |

> 上一轮提到的 `ledger_service.py` 原始 SQL 注入、**经核实不存在**——V2 该文件是干净的 ORM + `Money` 整数运算,初稿"残留 SQL 聚合"系读错位置,在此一并更正。

---

## 5. 去残留分阶段计划(受控退役)

### Phase 0 — 冻结与标记(0.5 天)
- 在 `backend/fundmate/` 根加 `DEPRECTED.md`,声明 V1 进入退役期、不再接受功能改动。
- 锁定 `autoapp.py` 仅作历史参考,README 明确唯一入口为 `app.main:app`。

### Phase 1 — 数据源覆盖审计(1~2 天)
- 对第 3.1 节标 ❌ 的 11 个源,逐个确认:(a) 是否被当前前端/功能实际使用;(b) V2 的 akshare/xalpha 是否已等价覆盖。
- 输出"移植清单"或"废弃清单"。对确需保留的(如 dkhs 费率),在 V2 `services/sync/adapters/` 下补适配器。

### Phase 2 — 迁移 `libs/cal`(0.5 天)
- 将 `fundmate/libs/cal/` 迁入 `backend/app/core/cal/`,更新 `tests/libs/cal/test_rate_of_return.py` 的 import,确保 V2 测试仍绿。

### Phase 3 — 删除 V1 残留(0.5 天)
- 删除:`backend/fundmate/`、`backend/autoapp.py`、`backend/migrations/`(V1 绑定)、`backend/tests/` 下所有 V1 测试与 `conftest_fm.py`、`tests/factories.py` 中 V1 模型引用。
- 清理 `pyproject.toml` 中仅 V1 使用的依赖(如 `flask-praetorian`、`sentry-sdk`、`flask-loguru` 视情况)。

### Phase 4 — V2 建立迁移机制(1 天)
- V2 当前无 alembic 迁移。新增 `backend/app/migrations/`(alembic),以 V2 现有模型 `create_all()` 产出的 schema 为基线,生成首个迁移版本,后续变更走版本化迁移(避免再出现"双轨 schema 无迁移"的坑)。

### Phase 5 — 文档与 SPEC 对齐(0.5 天)
- SPEC 增加"单一代码库"声明:V2(`backend/app`)为唯一真相源,V1 已退役(见 SPEC 本轮更新)。
- README 删除任何 V1 残留描述;确认部署/本地运行命令统一为 `app.main:app`。

---

## 6. 立即可做的零风险项(不等分阶段)
- 把 `autoapp.py` 顶部加注释或删除,消除"V1 在生产"的误导(不动逻辑)。
- 修正 `app/main.py:47` 硬编码 `DEBUG = True`(生产应读环境变量),与 CORS `*`(SPEC §2.1 已要求收紧)一并处理——属 V2 自身债务,与 V1 清除无关但建议同步修。

---

## 7. 风险与回滚
- **最大风险**:Phase 1 审计遗漏,删 V1 后某功能因依赖未移植的 V1 数据源而失效。缓解:Phase 1 必须产出可追溯的"移植/废弃"决策表,并在删除前用 V2 全量测试 + 前端冒烟覆盖。
- **回滚**:Phase 3 删除前用 git 提交快照;若出问题,`git revert` 该提交即可恢复 V1(无需保留长期分支)。
- **不删 V1 的长期代价**:双轨维护、依赖膨胀、`autoapp.py` 误导、新人理解成本——高于一次性退役成本。

---

## 8. 决策建议(需你拍板)
1. 是否认可"**V1 是残留、按 Phase 0→5 退役**"这一结论?(我基于证据强烈建议"是")
2. Phase 1 的 11 个数据源审计,由我做还是你先确认功能清单?
3. 是否现在就执行 Phase 0(加 `DEPRECTED.md` + 注释 `autoapp.py`),还是先等审计完成?

---

<a id="sec4"></a>
## 4. `data/` 接口可用性评估


> 日期：2026-08-01
> 关联文档：`docs/v1-decommission-analysis-2026-08-01.md`、`SPEC.md`(v4.5.4)
> 结论摘要：**V1 `data/` 全部 20 个数据源对 V2 零引用、整体冗余，且其中券商/平台自动导入类源违反 SPEC §2.1，建议随 V1 一并退役，不移植。**

---

## 0. 已执行的动作（Phase 0）

- ✅ 在 `backend/fundmate/` 新增 `DEPRECATED.md`，说明 V1 受控退役、V2 为唯一权威代码库、本目录被 gitignore。
- ✅ 在 `backend/autoapp.py` 顶部加「DEPRECATED ENTRY POINT」注释，指明生产启动应为 `flask --app app.main:app`。
- 上述改动**零逻辑风险**，不影响任何运行行为。

---

## 1. 版本控制现状（关键证据）

`.gitignore` 第 345 行 `fundmate/` 使**整个 V1 目录被版本库忽略**：

```
$ git check-ignore backend/fundmate/data/danjuan
backend/fundmate/data/danjuan          # => 被忽略

$ git log -1 -- backend/fundmate/data/danjuan
（空）                                  # => 从未被提交
```

含义：

- V1 不在版本控制中，**干净克隆后不存在**；
- 当前仅是本机残留，删除无 git 历史损失（可从此磁盘即时恢复）；
- Phase 3（删除 `fundmate/`）风险被降至极低。

> 这与上一轮「双代码库」判断形成闭环：V1 既非生产运行时（README 跑 V2），也非版本库资产，**确属遗留孤儿**。

---

## 2. 接口可用性探测结果

对每个数据源的代表性真实接口做 HTTP 探测（浏览器 UA、`-L` 跟随重定向、12s 超时）。
状态码说明：`200`=可达；`405`/`411`=端点存活但需 POST/带 Content-Length；`404`=路径失效/迁移。
多数接口裸 GET 返回 `size=0` 属正常（需参数/登录态），不代表失效。

| # | 数据源 | 代表性接口 | 探测结果 | 可用性判定 |
|---|--------|-----------|---------|-----------|
| 1 | danjuan（蛋卷） | `danjuanapp.com/djapi/fund/` | **200 但 301→`danjuanfunds.com`** | ⚠️ 域名已迁移，旧 host 依赖重定向；脆弱 |
| 2 | chinawealth（银行理财） | `chinawealth.com.cn/LcSolrSearch.go` | GET/POST 均 **404** | ❌ 端点疑似失效/迁移 |
| 3 | dkhs（德盛/费率） | `dkhs.com/api/v1` | 200 json(空) | ✅ 存活，需参数 |
| 4 | fundb（韭学/九菜说） | `api.jiucaishuo.com/v2/fundrate` | 405→POST **200**；`funddb.cn/tool/fear` **404** | ⚠️ 部分存活（jiucaishuo），恐惧贪婪路径失效 |
| 5 | jsl（集思录） | `jisilu.cn/data/indicator/get_last_indicator/` | **200 json** | ✅ 存活（V2 已自建 fetcher） |
| 6 | sipf（证券投资者保护） | `sipf.com.cn/survey/sipf-api/v2/investor/index` | **200 json** | ✅ 存活 |
| 7 | tencentwm（腾讯理财通） | `tencentwm.com/app/v2.0/wxh5_fund_trans_list.cgi` | 200 html | ✅ 存活（需登录态） |
| 8 | yzyx（有知有行） | `youzhiyouxing.cn/thermometer` | **200 html** | ✅ 存活（V2 已自建 fetcher） |
| 9 | zo（且慢 FOF/且慢） | `mobile.qiangungun.com/v2/product/detail` | **200 text/plain** | ✅ 存活（券商/平台导入类） |
| 10 | qieman（且慢组合） | `qieman.com/pmdj/v1/pomodels/` | **200** | ✅ 存活（券商/平台导入类） |
| 11 | amac（基金业协会） | `amac.org.cn/.../findFsAgencyAnnos` | **200 json** | ✅ 存活（行业权威，稳定） |
| 12 | 10jqka（同花顺） | `fund.10jqka.com.cn/data/client/myfund/` | 200 html(gbk) | ✅ 存活（需登录） |
| 13 | efunds（易方达） | `e.efunds.com.cn/funds` | 200 html | ✅ 存活 |
| 14 | howbuy（好买） | `howbuy.com/fund/company/ajax.htm` | GET 404 / POST 411 | ⚠️ 端点脆弱（需 Content-Length） |
| 15 | eastmoney（东财） | `fund.eastmoney.com/js/fundcode_search.js` | 已知稳定 | ✅ 存活（V2 经 akshare 间接使用） |
| 16 | baostock | Python 包（无 HTTP） | — | ✅ 库可用 |
| 17 | alipay / xa(xalpha) / inject / cmp | 见各模块 | — | 非独立抓取源 |

**探测结论**：绝大多数源主机仍存活（200/405/411 均表示端点可达），仅 `chinawealth` 与 `funddb.cn/tool/fear` 出现真实 404；`danjuan` 域名迁移、`howbuy` 端点脆弱属需维护项。但——**存活 ≠ 需要保留**（见 §3/§4）。

---

## 3. V2 对 V1 数据源的独立性验证（决定性的"无需移植"证据）

V2 的数据来源有两条独立通道：

- `app/services/sync/adapters/`：**仅 `akshare_adapter.py` + `xalpha_adapter.py`**（委托第三方库抓公开基金净值/元数据）；
- `app/services/thermometer/fetchers.py`：自建 fetcher，覆盖
  `eastmoney_volume / jisilu_cb / qieman / youzhiyouxing / jiucaishuo / jisilu_indicator / self_calc / er_niao`。

对 V1 独有源在 `backend/app` 中做引用扫描，结果**全部为 0 文件**：

```
chinawealth:0  dkhs:0  amac:0  tencentwm:0  ten_jqka:0  efunds:0
fundb:0  sipf:0  qiangungun(zo):0  joinquant(jq):0  10jqka:0
```

**即：V2 已完全自给，V1 `data/` 对 V2 是 100% 冗余。删除 V1 不会丢失任何 V2 所需能力（含「探市」温度——V2 自带 youzhiyouxing/jisilu/jiucaishuo fetcher，与 V1 的 yzyx/fundb/jsl 同源但独立实现）。**

---

## 4. 按 SPEC §2.1 的合规性判定

SPEC §2.1（第 73–74 行）明文：

> 合法录入渠道仅两种：用户手动 Web 表单录入、用户自行上传标准结构化文件导入。
> 系统全程无任何自动爬取、自动登录、自动抓包、自动同步券商数据逻辑，永久禁用。

据此对 V1 `data/` 各类源分类：

| 类别 | 代表源 | SPEC 判定 | 退役处置 |
|------|--------|----------|---------|
| **券商/平台持仓自动导入** | danjuan 组合、qieman 组合、howbuy 组合、zo(且慢FOF)、jq(聚宽) | ❌ 违反「禁止自动同步券商/平台数据」 | **删除，不移植** |
| **银行理财/费率等边缘聚合** | chinawealth、dkhs、amac、tencentwm、ten_jqka、efunds、fundb、sipf | 无 V2 消费者，且多为非核心聚合 | **删除（冗余孤儿）** |
| **公开基金净值/元数据** | eastmoney、baostock、akshare、xalpha | ✅ 属「元数据同步/净值回填」（SPEC 第 745 行已认可） | **已由 V2 sync 覆盖，不依赖 V1** |
| **市场情绪指数（探市）** | jsl、yzyx、fundb(恐惧贪婪)、sipf(信心) | ✅ 展示型、用户主动触发，非账本数据 | **V2 thermometer 已自建 fetcher 覆盖** |

> ⚠️ **SPEC 自身张力**：V2 的 `services/sync`(akshare/xalpha) 与 `thermometer` fetchers 本质上也在「自动抓取公开数据」，与 §2.1「永久禁用自动爬取」字面冲突。需在 SPEC 中**细化边界**（见 §6）。

---

## 5. 前瞻性评估（结合 SPEC 与后期开发方向）

近期 git 提交聚焦于 `探市温度计增强`、`乖离率计算`、`探市页面`——表明**「探市」(market temperature/exploration) 是当下及后续的主力开发方向**。基于此：

1. **数据能力已被 V2 锁定**：探市所需全部源（东财成交额、集思录温度计/可转债温度、且慢行情、有知有行、韭圈儿、自算、二鸟）均在 V2 `thermometer/fetchers.py` 内，且已写入测试。V1 `data/` 不参与该方向。
2. **不应"复活"任何 V1 抓取器**：新功能一律走 V2 的 `sync`(akshare/xalpha) 或 `thermometer`(自建 fetcher) 通道，保持单一数据接入面，避免再次分裂。
3. **探市 fetcher 的脆弱性需正视**：`fetchers.py` 使用 scrape cookie（`JISILU_COOKIE`/`kbzw__Session`）取「真值」，这类接口随时可能因对方改版/反爬失效。建议：(a) 将 fetcher 失败降级为 `self_calc` 或缓存值；(b) 为 fetcher 加健康检查与告警；(c) 在 SPEC 中把"探市类公开数据抓取"列为**显式允许**项，与"账本数据自动导入"明确区分。
4. **账本数据自动导入红线**：蛋卷/且慢/好买等"组合自动同步"属 SPEC 禁区，即便用户想要，也应改为「用户导出文件 → 手动上传」流程，而非后台爬虫。
5. **`libs/cal` 仍是唯一需迁移项**：V2 测试 `tests/libs/cal/test_rate_of_return.py` 仍 import `backend.fundmate.libs.cal`。删除 V1 前须先将该计算库迁入 `app/core` 或 `app/libs`（Phase 2），否则 V2 测试会断。

---

## 6. SPEC 修订建议（已落实到 v4.5.5）

- **§2.1 细化「自动抓取」边界**：
  - ✅ 允许：用户触发/展示用的**公开**市场数据抓取（基金公开净值/元数据经 akshare/xalpha；市场情绪指数经探市 fetcher）。
  - ❌ 禁止：任何**用户券商/平台持仓**的自动登录、爬取、同步；强制「手动录入 or 上传文件」。
- **技术债务表**：将「V1 `data/` 数据源」由"待审计"更新为"**已审计：V2 零引用、整体冗余、随 V1 退役删除，不移植**"；保留「`libs/cal` 迁移」为 Phase 2 阻塞项。
- **新增「数据接入单一通道」原则**：所有数据获取必须经 V2 `services/sync` 或 `services/thermometer`，禁止新增独立爬虫模块。

---

## 7. 结论与下一步

**结论**：V1 `data/` 20 个数据源——

- 对 V2 **零引用、整体冗余**；
- 其中券商/平台导入类**违反 SPEC §2.1**；
- 公开数据/情绪类**已被 V2 独立覆盖**；
- 目录本身**被 gitignore、非版本资产**。

→ **建议：不移植任何 V1 数据源，随 V1 一并退役。** 接口"是否还可用"在此语境下已非决策因素——即便可用，也应由 V2 自建通道接管，而非保留 V1 爬虫。

**下一步（承接 Phase 0，进入 Phase 1→2）**：

1. **Phase 1（已就绪）**：本报告的"零引用"结论即数据源审计结论，可直接归档。
2. **Phase 2（阻塞删除）**：迁移 `fundmate/libs/cal` → V2 `app/core` 或 `app/libs`，确保 V2 测试 `tests/libs/cal/*` 改指向新位置后全绿。
3. **Phase 3**：删除 `fundmate/`、`autoapp.py`、V1 测试树、`migrations/`；保留 git 快照前先用 `git stash -u` 或打 tag 备份本机残留。
4. **Phase 4**：为 V2 建立 Alembic 迁移（当前 V2 无迁移目录，schema 仅靠 `create_all`，存在生产迁移风险）。
5. **Phase 5**：文档对齐（README 删除一切 V1 引用；SPEC 落地 §6 修订）。

---

## 附录 A：探测命令与原始输出（节选）

```bash
curl -m 12 -sL -A "Mozilla/5.0 ... Chrome/120" -w "%{http_code}|%{content_type}|%{size_download}" <URL>
# danjuanapp.com/djapi/fund/000001  → 200 | json | 0  (301→danjuanfunds.com)
# chinawealth.com.cn/LcSolrSearch.go → 404 | text/html | 0
# dkhs.com/api/v1                   → 200 | application/json | 0
# api.jiucaishuo.com/v2/fund-lists/fundrate → 405 → POST 200
# funddb.cn/tool/fear               → 404
# jisilu.cn/.../get_last_indicator/ → 200 | application/json | 0
# sipf.com.cn/.../investor/index    → 200 | application/json | 0
# youzhiyouxing.cn/thermometer      → 200 | text/html | 0
# mobile.qiangungun.com/v2/product/detail → 200 | text/plain | 0
# qieman.com/pmdj/v1/pomodels/      → 200
# amac.org.cn/.../findFsAgencyAnnos → 200 | application/json | 0
# fund.10jqka.com.cn/.../myfund/    → 200 | text/html;gbk | 0
# e.efunds.com.cn/funds            → 200 | text/html | 0
# howbuy.com/.../ajax.htm          → 404(GET) / 411(POST)
```

## 附录 B：V2 探市 fetcher 已覆盖源（`app/services/thermometer/fetchers.py`）

`eastmoney_volume`、`jisilu_cb`、`qieman`、`youzhiyouxing`、`jiucaishuo`、`jisilu_indicator`、`self_calc`、`er_niao`。

---

<a id="sec5"></a>
## 5. `libs/cal` 与测试目录瘦身


> 日期：2026-08-01
> 背景：项目已进入 V2（`backend/app/`）单一代码库阶段，V1（`backend/fundmate/`）为遗留残留（已标记 `DEPRECATED.md`）。
> 目标：评估 `fundmate/libs/cal` 是否还有存在必要，并对“从 V1 移植来的测试用例目录”做重新评估，为项目大瘦身提供精确删除清单与执行计划。

---

## 0. 核心结论（先说结论）

1. **`fundmate/libs/cal` 没有存在必要，应删除。**
   - 它**仅被 V1 自身代码**与 **1 个从 V1 移植的测试**（`tests/libs/cal/test_rate_of_return.py`）引用。
   - V2 部署代码（`backend/app/`）对 `fundmate.libs` 的引用数 = **0**（已全仓扫描确认）。
   - V2 已自带功能等价且更现代的 XIRR 引擎 `app/services/performance/xirr_engine.py`（基于 `pyxirr`，Excel 精度一致，纯 Python 兜底）。

2. **测试目录里 29 个文件指向 V1（`backend.fundmate`），属于移植残留，应分期移除。**
   - 真正生效的测试套件由 `tests/conftest.py`（指向 V2 `app.main`）驱动，共 **36 个文件** 引用 V2 `app`。
   - 其余 29 个 V1 引用文件分三类：纯 V1 死测试（直接删）、可迁移测试（迁 XIRR 金值后删）、V1 辅助（随 V1 测试一起删）。

3. **`fundmate/` 整目录已被 `.gitignore` 忽略**（第 345 行 `fundmate/`），本机删除零版本风险；但为可回滚，删除前建议 `git stash -u` 或打本地 tag。

---

## 1. `fundmate/libs/cal` 去留评估

### 1.1 该目录是什么

`fundmate/libs/cal/rate_of_return.py`（约 850 行）是一套 **V1 时代的通用金融数学库**，包含：

| 类/函数 | 说明 |
|---------|------|
| `XIRR` / `XNPV` | 不定期现金流 IRR/NPV（scipy 牛顿迭代 + `numpy_financial` 兜底） |
| `IRR` / `NPV` | 定期现金流 IRR/NPV |
| `RATE` / `FV` / `PMV` / `PPMT` / `IPMT` / `PV` / `NPER` | 年金类计算（直接包装 `numpy_financial`） |
| `MIRR` | 修正内部收益率 |
| `XIRRDeprecated` | 已被 `@deprecated` 标记的旧实现 |

文件头明确标注 “Copyright (c) 2012 Sutoiku… ported from Apache OpenOffice”，且 `XIRRDeprecated` 已打 `@deprecated` —— **本身就是该下线的老代码**。

同级的 `fundmate/libs/` 还有 `convert.py`(被 `rate_of_return` 引用)、`dataklasses/`、`dk_enums.py`、`drf/`、`fund_morning_star_crawler/`、`ivix/`、`pysnowflake/`、`redeem_fee/` —— **全部仅被 V1 引用**，V2 零依赖。

### 1.2 谁在用它（事实核查）

全仓（`backend/`，排除 `.venv`）扫描 `from backend.fundmate.libs` / `import fundmate.libs` / `libs.cal`：

- **V2 部署代码 `app/`：0 处引用。**
- **仅有的外部引用 = `tests/libs/cal/test_rate_of_return.py`**（第 14 行 `from backend.fundmate.libs import rate_of_return as rr`）。

即：删掉这个测试 + V1 后，`fundmate/libs/cal` 成为完全无人引用的孤儿。

### 1.3 V2 的等价实现（已就位，无需重写）

`app/services/performance/xirr_engine.py`（部署版 XIRR）：

- `calculate_xirr(cashflows)`：优先用 **`pyxirr`**（与 Excel 结果一致），失败降级为纯 Python 牛顿迭代（`_pure_python_xirr`）。
- `_safe_return()`：把结果夹在 `[-1.0, 10.0]`，`|result| < 1e-8` 归零 —— **故意对病态现金流返回 `0.0`**（而非 V1 的 `+inf`/`-inf`/`None`）。
- `generate_cashflows()` / `generate_portfolio_cashflows()`：理解 V2 的 `Transaction` / `BusinessType` / `Money` 模型，自动过滤零值、内部划转、货币基金/逆回购等非投资资产。

**结论**：V2 的 XIRR 能力不仅覆盖、且在精度（pyxirr）与业务贴合度（直接吃 V2 模型）上优于 V1 的 `rate_of_return.py`。`cal` 无保留价值。

### 1.4 唯一的“价值残留”——XIRR 金值测试用例

`tests/libs/cal/test_rate_of_return.py` 里有**高质量数值金值用例**，值得抢救：

- `[-18990, -23320, 49490] → 0.12801613991037272`（精确到 1e-11）
- `{-80005.8, 65209.6} → -0.6454` 等多组已知 XIRR
- 边界用例：`{}→None`、单笔 → `±inf`、`1e-5 → 0.0`、极大值 `1.22e16`

⚠️ **但语义不一致**：V2 引擎对病态用例**故意返回 `0.0`**（`_safe_return` 夹逼 + `clean_xirr` 逻辑），与 V1 返回 `inf`/`None` 冲突。因此：
- **可迁移**：正常数值金值（`0.1280…`、`-0.6454` 等）——作为 V2 `test_xirr_engine.py` 的 Excel 对照回归，强化 `pyxirr` 正确性保证。
- **不可迁移**：`inf`/`-inf`/`None` 类病态断言 —— 与 V2 设计语义相悖，迁移会失败。

---

## 2. 测试目录重新评估

### 2.1 V1 vs V2 的分层（事实）

测试目录 `backend/tests/` 实际存在**两套并行体系**：

| 维度 | V2 激活套件 | V1 残留套件 |
|------|------------|------------|
| 驱动 conftest | `tests/conftest.py`（`import app.domains.*; create_app` 来自 V2） | `tests/conftest_fm.py`（`from backend.fundmate.app import create_app`） |
| 是否自动发现 | ✅ pytest 只认 `conftest.py` | ❌ 文件名非 `conftest`，**不会被自动加载** |
| 引用目标 | `backend.app` / `from app` / `import app`（36 文件） | `backend.fundmate`（29 文件） |
| 测试内容 | `core/`、`domains/`、`services/sync`、`services/importer`、`services/performance` | `collection/`、`fund/`、`user/`、`data/`、`exts/flask_loguru`、`libs/cal`、根级 `test_*` |

> 注：之前 `pytest --co` 报的 **19 个收集错误全部来自 V1 残留树**（`conftest_fm` 不被加载 + V1 `errors.py:201` NameError + 缺 `pyjson5/faker/plummet`）。这些错误**不影响 V2 套件绿色**。

### 2.2 29 个 V1 引用文件（删除候选）分类

**Tier 1 — 纯 V1 死测试，直接删（21 文件）**

```
tests/collection/collection_teardown.py
tests/collection/test_collection_models.py
tests/collection/test_collection_views.py
tests/fund/test_fund_models.py
tests/fund/test_fund_views.py
tests/user/test_user_models.py
tests/user/test_user_views.py
tests/exts/flask_loguru/test_configuration_logger.py
tests/data/chinawealth/test_china_wealth.py
tests/data/danjuan/test_dj_base.py
tests/data/danjuan/test_dj_combination.py
tests/data/dkhs/test_dkhs_base.py
tests/data/eastmoney/test_em_base.py
tests/data/eastmoney/test_trade_day.py
tests/data/fundb/test_fundb_base.py
tests/data/howbuy/test_hb_combination.py
tests/data/qieman/test_qm_combination.py
tests/data/sipf/test_confidence.py
tests/data/ten_jqka/test_jq_base.py
tests/data/yzyx/test_yzyx_base.py
tests/data/zo/test_qgg_base.py
```

- `collection/`：V1 的“组合/Fund 收藏”概念，V2 由 `domains/ledgers`、`domains/positions` 取代。
- `fund/`：V1 Fund 模型（用 `backend.tests.factories.FundFactory`）；V2 已有 `domains/test_funds.py`（引用 `app.domains.funds.models`），**保留 V2 版、删 V1 版**。
- `user/`：V1 基于 `flask_praetorian` 的认证；V2 后端无用户视图（认证走 Supabase），**整树无价值**。
- `data/` 整树：V1 各数据源抓取单测；V2 已由 `services/sync/test_*` 覆盖等价数据源，**重复**。
- `exts/flask_loguru/`：V1 日志扩展测试，V2 未沿用该扩展。

**Tier 2 — 先迁移、后删除（2 文件）**

```
tests/libs/cal/test_rate_of_return.py   → 迁移可移植 XIRR 金值到 V2 test_xirr_engine.py
tests/libs/cal/__init__.py
```

**Tier 3 — V1 辅助/夹具，随 Tier1/2 一起删（4 文件）**

```
tests/conftest_fm.py          # V1 conftest，不被自动加载
tests/factories.py            # V1 工厂，仅被 collection/fund/user 引用（已核实无 V2 测试 import）
tests/test_commands.py        # V1 CLI 命令（V2 用 flask --app app.main）
tests/test_config.py          # V1 create_app 配置
tests/test_db.py              # V1 数据库初始化
tests/test_errors.py          # V1 错误枚举测试
tests/test_utils.py           # V1 工具函数
```

> 核查：`tests/factories.py` 仅被 `collection/`、`fund/`、`user/` 三个 V1 树 import，**没有任何 V2 测试引用它** → 可安全删除。
> 提示：`tests/data/test_data.py` 与 `tests/data/__init__.py` **未在 V1 引用清单内**，疑似通用数据工具测试，删除 `tests/data/` 前请单独确认。

### 2.3 应保留的 V2 测试（36 文件，不赘述）

`tests/conftest.py` + `tests/core/`、`tests/domains/`(15) + `tests/services/sync/`(10) + `tests/services/importer/`(8) + `tests/services/performance/`(2) + `tests/schemas.py`、`tests/settings.py`、`tests/test_xalpha.py`、`tests/test_apps/`。这些是项目真实回归安全网，**大瘦身必须保留并持续跑绿**。

### 2.4 一个值得补的缺口

V2 的 `app/core/exceptions.py`（`SBException`）**目前没有任何测试**。删掉 V1 `test_errors.py` 后，错误码唯一性/结构无回归保障。建议补一个轻量 `tests/test_exceptions.py`（验证 `SBException` 错误码唯一、`{data,message}` 结构）。

---

## 3. 大瘦身执行计划（分 4 阶段，均带回滚）

### Phase A — 抢救 XIRR 金值（低风险，先补后删）
1. 在 `tests/services/performance/test_xirr_engine.py` 追加 `TestXirrGoldValues`：
   - 移植可移植数值用例：`[-18990,-23320,49490]→≈0.1280`、`{-80005.8,65209.6}→≈-0.6454` 等（断言用 `approx(..., rel=1e-3)`，因 V2 走 pyxirr）。
   - **跳过** `inf`/`-inf`/`None` 类病态断言（与 V2 语义冲突）。
2. 跑 `pytest tests/services/performance/` 确认新用例绿。

### Phase B — 删除 V1 测试残留（中风险）
1. 删除 Tier 1（21 文件）+ Tier 3（6 文件）+ `tests/libs/cal/`（2 文件）。
2. 删除前：`git stash -u` 或本地打 tag 备份本机未跟踪的 `fundmate/` 与这些测试。
3. 跑 `pytest` 全量（仅 V2 conftest）→ 必须 100% 绿；确认 19 个历史收集错误消失。

### Phase C — 删除 `fundmate/libs/` 冗余（低风险，因 gitignore）
- `fundmate/libs/` 整目录（含 `cal`、`convert`、`dataklasses`、`dk_enums`、`drf`、`fund_morning_star_crawler`、`ivix`、`pysnowflake`、`redeem_fee`）V2 零引用 → 删除。
- 若担心误伤，可先 `git stash -u` 再删。

### Phase D — 收尾与规范对齐
1. 补 `tests/test_exceptions.py`（V2 错误契约回归）。
2. 更新 SPEC：标记测试目录已单轨化（仅 V2），删除“双代码库/测试须覆盖部署版本”相关旧表述，新增“测试只允许引用 `app`”的硬约束（CI 加 `grep backend.fundmate tests/ && exit 1` 守卫）。
3. 运行 `pytest --cov` 确认覆盖率不因删除下降（V1 测试对 V2 代码覆盖本就为 0）。

---

## 4. 风险与注意事项

1. **`tests/data/test_data.py` 需单独确认**：它未被 V1 引用清单捕获，可能是通用工具测试，删 `tests/data/` 前请人工过一眼。
2. **语义差异**：V1 `xirr` 病态返回 `inf`/`None`，V2 返回 `0.0`。迁移测试时**只能搬正常金值**，否则 CI 必红。
3. **`fundmate/` 未入库**：删除本机残留不影响他人克隆；但若团队有人依赖本机 `fundmate/` 跑脚本，需提前知会。
4. **不要顺手删 `tests/services/sync/`**：那是 V2 真实数据层测试，对应 V2 `app/services/sync`，与 V1 `data/` 不是一回事。

---

## 5. 证据索引（file:line）

- `fundmate/libs/cal/rate_of_return.py:14` `from backend.fundmate.libs import convert`（V1 内部引用）
- `fundmate/libs/cal/rate_of_return.py:480` `@deprecated XIRRDeprecated`（自身已标记废弃）
- `tests/libs/cal/test_rate_of_return.py:14` `from backend.fundmate.libs import rate_of_return as rr`（唯一外部引用）
- `app/services/performance/xirr_engine.py:23` `from pyxirr import xirr`（V2 等价实现，Excel 精度）
- `app/services/performance/xirr_engine.py:38-42` `_safe_return` 夹逼 `[-1.0, 10.0]`（与 V1 语义差异点）
- `tests/conftest.py:12-16` `import app.domains.*`（V2 激活 conftest）
- `tests/conftest_fm.py:21` `from backend.fundmate.app import create_app`（V1 残留 conftest，不自动加载）
- `app/` 全仓扫描：`fundmate.libs` 引用数 = 0（V2 不依赖 V1）
- `.gitignore:345` `fundmate/`（V1 整目录被忽略，删除无版本风险）

---

<a id="sec6"></a>
## 6. FastAPI 解耦规划（`@bp.input` 自动范式冲突）


**日期**：2026-08-01
**依据**：SPEC §1.3「统一手动返回 `{data, message}` 结构，**不依赖自动范式**，为未来平滑迁移 FastAPI 预留架构空间」
**状态**：`assets` 域已完成实证改造（88 用例全绿）；其余 11 处待按同模式收敛。

---

## 1. 结论：冲突存在，但范围比预期小

经全量核查（`backend/app`），冲突**确实违反 SPEC §1.3 字面条款**，但实测发现一个关键事实，显著降低了迁移成本：

- **违反点**：`app/` 内 13 处 `@bp.input(Schema)` 自动校验装饰器 —— 这正是 SPEC 禁止的「自动范式」，且视图函数签名依赖其注入的已校验对象。
- **关键更正（循证反查）**：这 13 处所用的输入模型**本身已是 `pydantic.BaseModel`**（如 `assets/schemas.py:14 class AssetCreate(BaseModel)`），并非 `apiflask.Schema`（marshmallow）。APIFlask 2.x 支持直接用 Pydantic 模型作 `@bp.input` 实参。
  → **模型层已是 FastAPI 就绪**，未来迁移时这些模型可直接复用，**模型迁移成本≈0**。
- **真正耦合**：仅 `@bp.input()` 装饰器这一「框架调用」本身。移除它即可消除对 APIFlask 自动范式的依赖。
- 唯一真 marshmallow 耦合在 `importers/views.py`（`from apiflask import Schema, fields`，定义 2 个 Schema 但注释「暂不启用校验」——属未启用死代码，可后续清理或转 Pydantic）。

**输出侧合规**：全项目 `@bp.output()` 使用 **0 处**，响应全部手动 `return jsonify({'data':..., 'message':'ok'})`，已 FastAPI 友好。

---

## 2. 迁移模式（已落地，`app/core/validation.py`）

```python
# app/core/validation.py
from flask import abort, request
from pydantic import BaseModel, ValidationError

def parse_body(model: type[BaseModel]) -> BaseModel:
    """替代 @bp.input(model)；等价于 FastAPI Body() + Pydantic 校验。"""
    payload = request.get_json()          # 非法 JSON → 抛 400（与原 @bp.input 行为一致）
    if not isinstance(payload, dict):
        abort(422, "请求体必须是 JSON 对象")
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        abort(422, f"请求参数校验失败: {_format_errors(e)}")

def parse_query(model: type[BaseModel]) -> BaseModel:
    """替代 @bp.input(model, location='query')；等价于 FastAPI Query()。"""
    try:
        return model.model_validate(dict(request.args))
    except ValidationError as e:
        abort(422, f"查询参数校验失败: {_format_errors(e)}")
```

要点：
- 失败 `abort(422)` → 走 `app/main.py` 的 `HTTPException` 处理器 → 统一 `{data, message, error_code}` 信封。
- 返回状态码 **422 与 `@bp.input` 完全一致**，既有断言 `status_code == 422` 的测试**不受影响**（已用 `test_assets` 验证）。
- 迁移 FastAPI 时：`parse_body(X)` → `X = Body()`，`parse_query(X)` → `X = Query()`，模型不变。

---

## 3. 改造示例（已实证：`assets/views.py`）

**Before**
```python
@bp.post('/')
@bp.input(AssetCreate)
def create_asset(json_data):
    data = json_data.model_dump()
    ...
```
```python
@bp.patch('/<int:id>/')
@bp.input(AssetUpdate)
def update_asset(id, json_data):
    with get_db() as db:
        ...
        update_data = json_data.model_dump(exclude_unset=True)
```

**After**
```python
@bp.post('/')
def create_asset():
    json_data = parse_body(AssetCreate)
    data = json_data.model_dump()
    ...
```
```python
@bp.patch('/<int:id>/')
def update_asset(id):
    json_data = parse_body(AssetUpdate)
    with get_db() as db:
        ...
        update_data = json_data.model_dump(exclude_unset=True)
```
仅移除 `@bp.input` 装饰器、把注入参数改为函数内 `parse_body(Model)` 调用；业务校验（ledger_id 防御、金额分转换）**原样保留**。`parse_body` 从 `app.core.validation` 导入。

---

## 4. 13 处逐项收敛表

| # | 文件:行 | 路由 | 模型（已 Pydantic） | 输入位置 | 改造动作 |
|---|---|---|---|---|---|
| 1 | `assets/views.py:60` | `POST /api/assets/` | `AssetCreate` | body | `parse_body(AssetCreate)` ✅ 已完成 |
| 2 | `assets/views.py:91` | `PATCH /api/assets/<id>/` | `AssetUpdate` | body | `parse_body(AssetUpdate)` ✅ 已完成 |
| 3 | `positions/views.py:149` | `POST /api/positions/` | `PositionCreate` | body | `parse_body(PositionCreate)` |
| 4 | `positions/views.py:196` | `PATCH /api/positions/<id>/` | `PositionUpdate` | body | `parse_body(PositionUpdate)` |
| 5 | `watchlist/views.py:144` | `POST /api/watchlist/items/` | `WatchlistItemCreate` | body | `parse_body(...)` |
| 6 | `watchlist/views.py:165` | `PATCH /api/watchlist/items/<id>/` | `WatchlistItemUpdate` | body | `parse_body(...)` |
| 7 | `watchlist/views.py:201` | `POST /api/watchlist/groups/` | `WatchlistGroupCreate` | body | `parse_body(...)` |
| 8 | `watchlist/views.py:213` | `PATCH /api/watchlist/groups/<id>/` | `WatchlistGroupUpdate` | body | `parse_body(...)` |
| 9 | `watchlist/views.py:306` | `POST /api/watchlist/tags/` | `WatchlistTagDefCreate` | body | `parse_body(...)` |
| 10 | `watchlist/views.py:449` | `PATCH /api/watchlist/tags/<id>/` | `WatchlistTagDefUpdate` | body | `parse_body(...)` |
| 11 | `strategy/views.py:136` | `POST /api/strategy/` | `StrategyTagCreate` | body | `parse_body(...)` |
| 12 | `funds/views.py:37` | `POST /api/funds/nav/` | `FundNavRequest` | body | `parse_body(...)` |
| 13 | `performance/views.py:20` | `GET /api/performance/xirr/` | `XirrRequest` | **query** | `parse_query(XirrRequest)` |

> 注：watchlist 的 `WatchlistItemUpdate` 等名称以实际 schema 文件为准；模式完全一致。

---

## 5. 执行顺序与防回潮

1. 按上表逐域改造，每域改完跑对应 `tests/domains/test_*.py`（全部已有覆盖）。
2. 改造后跑全量 `pytest` 确认仅 eastmoney 实时联网测试失败（既有非回归）。
3. **CI 守卫**：在 `scripts/` 新增 `forbid_apiflask_input.sh`，grep `backend/app` 内 `@.*\.input\(` 并加以禁止（类比既有的 `forbid_v1_refs.sh`），并入 CI，防止回潮。
4. `importers/views.py` 的 2 个未启用 `apiflask.Schema` 单独清理（转 Pydantic 或删除），不在本批范围。

---

## 6. 反向压力测试结论（若今日硬迁 FastAPI）

- ✅ 13 个输入模型：直接复用（已是 Pydantic）。
- ✅ 输出信封 `{data,message}`：FastAPI `response_model`/直接返回 dict，零改写。
- 🔧 13 处 `@bp.input`：本方案消除后，仅需把 `parse_body/parse_query` 换成 `Body()`/`Query()`。
- 🔧 71 处 `abort()` → FastAPI `HTTPException`；145 处 `request`/`jsonify`/`send_file` → `Request`/`JSONResponse`/`FileResponse`；15 处 `APIBlueprint` → `APIRouter`（这些属 SPEC 允许的「使用 APIFlask」范畴，是剩余迁移成本，但已与「自动范式」解耦）。
