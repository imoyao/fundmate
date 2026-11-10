# 资产值变动记录（余额 / 估值）设计

> 状态：**设计定稿**；规范决策（D99 / D100）与本文档先独立合入 `dev`，事件表与时间线实现另从 `dev` 切功能分支。
> 关联决策：`docs/spec/decisions.md` **D99**（双时间戳 / 补录边界）、**D100**（锚点业务日期）。
> 上位规范：`conventions.md` §2.10、`data-strategy.md`（准入四问 + 域登记）、`net-worth-caliber.md`、D41 / D62 / D79 / D98。
> 范围：`assets` 表单条通用资产（房贷、借款、房产、应收应付等）的**值变动历史**。
> 不含：证券持仓、家庭级净资产历史重算、收益日历、计息。

---

## 1. 结论先行

| 事项 | 判定 | 落点 |
|---|---|---|
| 房产（估值）与房贷（余额）是不是两笔账 | **是，且数据层本就是两行 `Asset` 记录** | 共用一张事件表，`kind` 只是展示标签，不分表 |
| 两笔账是否互不影响 | **数据层成立，汇总层不成立** | `net_worth = Σ资产 − Σ负债`，须显式声明历史口径分叉 |
| 「编辑留痕」属于哪一侧 | **都不属于，是横切关注点（纠错）** | 不擦除、只冲销；两类账共用 |
| 锚点要不要落一行存储 | **不要，它是派生量** | 复用 D98 倒推公式，`start_date` 只定可信下界 |
| 事件表存什么 | **只存 `delta`（业务变动量），不存 `after_amount`** | 补录乱序时无需重算任何存量行 |
| 名称可编辑 | **本期先做，且不进事件表** | 纯前端补字段；改名历史另立卡，本期无读者 |

---

## 2. 现状证据（只读核查，2026-11-10）

| 事实 | 证据 |
|---|---|
| 只有一张 `assets` 表承载全部手动资产 | `backend/app/domains/assets/models.py:27-85`；房贷 = `liability/mortgage`、借款 = `receivable`、房产 = `real_estate` 或 `fixed/house`，均无独立模型 |
| `amount` 是**当前值**（分）、恒正 | `models.py:55`「当前价值/余额」；`views.py:33-34` 的 `signed_amount` 才对负债取负；`summary_service.py:188-197` 负债保持正数、在出口相减 |
| 编辑是直接覆盖，无历史 | `views.py:115-149` `setattr` + `flush`；唯一痕迹 `updated_at`（`models.py:75-79`，墙钟 `func.now()`），不存旧值 |
| 现有两条历史链都不服务单资产 | `asset_snapshots` 是家庭聚合的落库时点快照（D62 禁止回填）；`pnl_daily_snapshots` 仅持仓口径，`pnl_snapshot_store.py:109` 的 `_WATCHED = (Position, Transaction, Ledger)` 明确排除 `Asset` |
| `name` 三层都存在，只缺 UI | `models.py:54`、`schemas.py:55`、`frontend/src/api/assets.ts:78`；`AssetEditDialog.vue:102-113 / 165-173` 的 form 与 `save()` 不含 name |
| `start_date` 存在但从未被录入或消费 | `models.py:62`、`schemas.py:42/62/86`；前端 `views/asset/assetEntry/` 全目录 `start_date`／`end_date` 零命中；`_load_user_assets` 无日期过滤 |
| 名称被当隐式业务键（非引用完整性） | `ledger_migration_service.py:73-85` 按 `(name, major, minor)` 找同类资产；`sankey_service.py:95-110` 同名负债聚合；`summary_service.py:724` `liability_map`；前端 `:key` |

**规范文字与实现的偏差（必须写进实现约束）**：`conventions.md:105` 写「后端存储层……负债存负」，但 `assets` 表实测恒正。事件表跟随 `assets.amount` 的**实际口径**，负债方向只在 `signed_amount` 与分桶处出现一次，**不在事件表重复变号**。本设计不触发 `conventions.md` 的修改。

---

## 3. 概念模型：两笔账 + 一个横切关注点

### 3.1 两类事实，一个存储结构

| 账 | 语义 | `kind` 示例 | 典型 `delta` |
|---|---|---|---|
| 房产 / 贵金属 | **资产估值**（observation，主观估计） | `valuation` | 重估 +20 万 |
| 房贷 / 借款 / 应收应付 | **余额**（flow，业务事实驱动） | `repayment` / `borrow` / `receivable_change` | 月供 −3,000 / 新增借款 +5 万 |

它们本就是 `assets` 表里**两行不同记录**，各有独立 `id`、`amount`、`start_date`。因此「记录一次值变化」的存储结构对两者完全相同，差异只在展示文案与 `delta` 符号 ⇒ **共用一张事件表**，`kind` 是标签而非分表依据。分两张表会多一套读写路径，属于无意义扩展。

### 3.2 汇总层会交汇

`summary_service.py:204-205`：`net_worth = total_assets − total_liabilities`。房产估值 ↑ 与房贷余额 ↓ 同时推高净资产。补录历史日期后，单资产明细可回溯、家庭净资产曲线（`asset_snapshots`）**按 D62 不重算**，两者会出现可见的口径分叉。这不是技术冲突，是认知冲突；不预先说明会被当成 BUG 报回。见 §9.3。

### 3.3 三种语义必须分开

| 语义 | 含义 | 是否进事件表 |
|---|---|---|
| 业务事实 | 「10 月 8 日还款 3,000」「9 月 30 日重估为 230 万」 | **是**，L1 真相源 |
| 时点值 | 「截至 10 月 31 日房贷余额」 | **否**，由 §6 公式派生 |
| 纠错 | 把 140 万输成 14 万，次日改回 | **是**，但作为冲销事件 |

**纠错是横切关注点，不是房产专属**：两类账都会输错。原则是会计的第一性原理——**不擦除，只冲销**：append-only 事件表里，纠错 = 追加一条反向记录（`kind='correction'`），而不是修改或删除历史那条。`decisions.md:163`（D5）已有同源思想：「记在流水上还能在删除/回滚流水时自动冲销」。这样 append-only 与不变量同时成立，也避免再建一张 audit 表踩 D41「同一事实存两遍必然漂移」。

### 3.4 设计级决策：纠错记录是否展示

**拍板：时间线显示，但标注「更正」并默认折叠为一行（可展开）。**

理由：产品目标是「能看到值的变化」，把操作痕迹完全隐藏与之矛盾；但纠错噪音不该与真实业务事件平级铺开。替代方案「完全隐藏」否决（历史不可审计），「与普通事件平级展示」否决（一次输错会永久污染走势图的视觉密度）。该取舍属设计级，不进 `decisions.md`。

---

## 4. 数据模型

### 4.1 新增表 `asset_value_events`（user 域，append-only）

**必须在 `core/db_factory.DATA_DOMAIN_REGISTRY` 登记 `DOMAIN_USER`**（含 `family_id`，按 AGENTS.md 数据域归属决策树；AGENTS.md:963 / :966）。

| 字段 | 类型 / 约束 | 读者（AGENTS.md:957 要求当场指定） |
|---|---|---|
| `id` | Integer PK, autoincrement | 同日多笔定序 |
| `family_id` | Integer NOT NULL, index | 家庭隔离 + 域判定 |
| `asset_id` | Integer NOT NULL, FK → `assets.id` ON DELETE **RESTRICT**, index | 时间线归属；禁止删资产行连带毁序列 |
| `effective_date` | Date NOT NULL | 时点查询、时间线排序（D99） |
| `recorded_at` | DateTime(tz) NOT NULL, `server_default=func.now()` | 审计「何时录入」（D99），不参与 as-of |
| `delta` | Integer NOT NULL（**分，带符号**） | §6 倒推公式、时间线「变动」列、不变量 |
| `kind` | String(20) NOT NULL | 时间线文案 / 图标 / 筛选 |
| `notes` | String(500) nullable | 时间线「说明」列（本次变动原因） |
| `client_token` | String(64) NOT NULL, **UNIQUE** | 幂等写入（D71 同源：防网络重试产生重复事件） |

**复合索引** `(family_id, asset_id, effective_date, id)`，覆盖单资产时间线与 as-of 求和，不做全表扫描（AGENTS.md:962）。

### 4.2 刻意不落的字段

| 不落 | 理由 |
|---|---|
| `after_amount` / `before_amount` | 是 `delta` 的折叠结果；补录更早事件会让所有后续值失效 ⇒ 必须重算，属可漂移的冗余。只存 `delta` 时补录乱序**零重算**（§5.3） |
| `name_snapshot` | 时间线展示的是「值的变化」，名称取资产当前行即可；当前无读者，违反 AGENTS.md:957「禁止先存着」 |
| 名称变更事件 | 改名不是值变化，混进来会污染 `Σdelta` 不变量；本期无读者，见 §11 |
| `opening` 锚点行 | 锚点是派生量，见 §6.2 |

### 4.3 值口径

- `delta` 是**恒正余额**的变动量（单位：分）。还款 −300000，重估 +20000000。
- 负债方向**不**在事件表变号；`signed_amount`（`views.py:34`）与 `summary_service.py:194-197` 各出现一次即可。
- `assets.amount` 继续恒正，是**唯一当前值**。

### 4.4 不变量（实现 PR 必须配测试 + 回退探针）

| # | 不变量 | 判据 |
|---|---|---|
| I1 | `assets.amount − Σ(delta) = 初始余额 ≥ 0` | 任一资产任意时刻恒等；序列为空时初始值 = `amount` |
| I2 | `value_asof(d)` 恒 ≥ 0 | 出现负值说明 `delta` 写反或漏写，报红而非夹紧 |
| I3 | 事件行只增不改不删 | 无 UPDATE / DELETE 路径；纠错只能追加冲销 |
| I4 | `client_token` 唯一 | 同 token 重放不产生第二行 |
| I5 | `Σ账户桶 ≡ 家庭桶` | 现有 `summary_service` 结构恒等式不得破坏 |

---

## 5. 写入收口

### 5.1 单一写者

新增 `services/asset_value_event_service.py` 作为**唯一写者**：一个事务内完成「插入事件行 + 更新 `assets.amount`」。`PATCH /api/assets/<id>/` 中涉及金额的部分改委托该服务；**其余字段（name / notes / minor_category）仍走原 `setattr` 路径**，不混入事件写入（AGENTS.md:963：同一字段只有一个写者）。

事务边界沿用 `core/database.py` 的 teardown；并发写按 D71 的教训用**数据库原生约束**（`client_token` UNIQUE + `ON CONFLICT DO NOTHING`），不做「先 SELECT 再 INSERT」的先查后写。

### 5.2 何时不写事件

`after_amount == before_amount`（只改名称 / 只改备注 / 只改子类）⇒ **不写事件**。否则时间线会被纯改名刷屏，且 `Σdelta` 不变却多出无意义行。

### 5.3 补录乱序

`effective_date` 允许早于今天（D99）。因为只存 `delta`、不存 `after_amount`，插入一条更早事件**不需要重算任何存量行**：`Σdelta` 自动包含它，`value_asof` 的倒推公式天然正确。同日多笔按 `(effective_date, id)` 定序。这是选「只存 delta」而非「存绝对值序列」的决定性理由。

### 5.4 幂等

前端提交时生成 `client_token`（UUID），保存按钮 loading 期间禁止重复提交；后端以唯一约束兜底网络重试。重放返回首次写入的结果，不报错、不重复。

---

## 6. 时点语义

### 6.1 双时间戳（D99）

| 时间 | 来源 | 用途 |
|---|---|---|
| `effective_date` | 用户显式填写，允许过去 | 业务发生日；as-of 查询、时间线横轴 |
| `recorded_at` | 系统 `func.now()`，墙钟 | 只回答「何时录入」；**绝不**参与时点取数 |

D62 / D98 禁止的是「系统把今天的状态贴到历史日期」，本设计不产生任何派生回填 —— 每个历史数字都来自用户逐条录入的 `delta`。

### 6.2 锚点是派生量，不是一行

复用 D98 / `net-worth-caliber.md:110` 的回放公式（方向改为由当前值倒推）：

```
value_asof(asset, d) = assets.amount − Σ(delta_i where effective_date_i > d)
初始余额          = value_asof(asset, start_date) = assets.amount − Σ(全部 delta)
```

**对上一轮「锚点 = 显式初始行」提法的收敛**：显式锚点行在补录更早事件时会立刻失真（要重算锚点或拒绝补录），而派生锚点无需任何维护，且省掉一张表、一个真相源。用户所说「锚点相当于初始状态」的语义完整保留，只是不落库。

### 6.3 可信下界（D100）

- `start_date` = 可信下界。`d < start_date` ⇒ 返回 `None`，前端显示「—」。
- `start_date` 为空 ⇒ **整条序列不提供 as-of 查询**，时间线显示「起账日未填写，历史不可回溯」。不回落 `created_at`、不用最早事件反推、不向前外推成水平线。
- `start_date` 到首条事件之间是合法区间：余额未变，值 = 初始余额。
- 存量数据**不回填** `start_date`（D100 第 ⑤ 条）：迁移只加列／加表，用户补齐前保持「历史不可回溯」。

### 6.4 软删

`status='closed'` / `end_date` 不删除 `assets` 行与事件行（D100 第 ④ 条，与 `decisions.md:239` 清仓不删行同源）。FK 用 `ON DELETE RESTRICT` 在数据库层兜底。时间线保留，只标「已结清」。

---

## 7. 数据准入四问（PR 描述必须留痕）

| 问 | 答案 |
|---|---|
| **谁在用？** | 读者 A：`GET /api/assets/<id>/value-events/` → 盘点页行内「明细」抽屉的时间线表 + 折线；读者 B：`GET /api/assets/<id>/value-at/?date=` → 时间线时点值；读者 C：不变量测试 I1–I5；读者 D：`client_token` 的幂等写入路径 |
| **什么场景用？** | 用户复盘房贷逐月下降、欠款增减、房产重估；在编辑弹窗填「变动日期 + 本次变动量 + 说明」保存后，抽屉里按时间看到每一步与折线 |
| **缺了会怎样？** | 只能看到当前值，用户诉求（历史追溯）**完全无法满足**，降级不可接受 ⇒ 必须存 |
| **成本多大？** | 每行约 100 字节、单资产年均数十行；**零外部请求**、零抓取、零调度 job；一次单资产查询走复合索引 |

**新表登记**：`DATA_DOMAIN_REGISTRY` 加 `asset_value_events: DOMAIN_USER`（AGENTS.md:966），与四问留痕并行、互不替代。

---

## 8. API 契约

| 方法 | 路径 | 说明 |
|---|---|---|
| `PATCH` | `/api/assets/<id>/` | 现有端点。新增可选 `delta` / `effective_date` / `change_note` / `client_token` / `change_kind`；`delta` 是**独立业务事实**（元，带符号），由 §5.1 服务写事件 + 更新 `amount`。`delta` 与 `amount` 不可同时传；**都不传时行为与第 2 期之前逐字相同**（向后兼容） |
| `GET` | `/api/assets/<id>/value-events/` | 单资产事件列表，按 `(effective_date, id)` 升序；带 `family_id` 隔离；分页 |
| `GET` | `/api/assets/<id>/value-at/?date=YYYY-MM-DD` | 返回 `{ value, valid }`；`valid=false` 时 `value=null`（`start_date` 未知或日期早于下界） |

`GET /api/summary/snapshots/` **一行不改**；补录前后返回必须完全相同（D99 判据）。

> **实现期修订（2026-11-10，用户拍板）**：初稿 §9.2 让弹窗填「变动后余额 / 估值」，
> 与 §4.2「只存 delta、乱序补录零重算」**数学上不兼容**。实证：初始 100 万，
> 先录 11 月 90 万、再补 10 月 95 万，按 `delta = 新值 − 当前值` 反推会得到
> 10 月 105 万 / 11 月 95 万 / 当前 95 万——两个填写值都没对上，因为当前值
> 已含后续变动，补录更早事件会平移后面整条曲线。改为提交 `delta` 后同一组数据
> 得到 10 月 95 万 / 11 月 90 万 / 当前 90 万，求和可交换 ⇒ 乱序零重算成立。
> 旧客户端的 `amount` 绝对值语义保留，由视图换算成 `after − before` 后仍走同一写者。

---

## 9. UI 骨架

### 9.1 第 1 期：名称可编辑（本次已落地）

`AssetEditDialog.vue` 补「资产名称」输入框、`form.name`、`EMPTY_FORM.name`、打开回填、`save()` 提交 `name`、脏检查文案，并在保存前 `trim()` + 非空校验（空名会让按 name 聚合的口径静默失真）。后端 / 类型层零改动。资产名**不要求唯一**（与「组合名必须唯一」是两回事）。

防回潮判据：`frontend/src/views/asset/inventory/components/__tests__/assetEditDialogName.spec.ts`，剥注释后钉住「渲染 / 回填 / 脏基线 / 提交 / 非空校验」五处——本需求最易回潮的形态是「输入框还在、`save()` 漏提交 `name`」，界面正常但改名静默失效。**后端汇总归因断言（改名后各汇总仍按 `id` 归一、无重复漏算）归第 2 期实现 PR**，本期无后端改动；`ledger_migration_service.py:79`、`sankey_service.py:103`、`summary_service.py:724` 把 name 当隐式业务键，改名会改变匹配与分组结果（软依赖，不是引用完整性）。

### 9.2 第 2 期：值变动录入 + 时间线

- 编辑弹窗把「金额」改为**「本次变动量」**（`el-input-number`，默认 0、允许负数：负债还款填 −3000、房产重估填 +200000），下方实时预览「当前余额 → 变动后余额」；另增「变动日期」（`el-date-picker`，默认今天）与「变动说明」（写事件 `notes`，与资产级「备注」分开）。文案按 `major_category` 切换（负债叫「余额」、房产叫「估值」）。
- **录入语义必须填 delta，不是变动后绝对值**：理由与实证数据见 §8 的实现期修订。`delta == 0` 时不提交金额字段，保证「只改名 / 只改备注」不写事件（A10）。
- 盘点页表格行加「明细」→ `el-drawer`：上半部 `TimeSeriesChart`（通用折线，`frontend/src/components/Charts/TimeSeriesChart.vue`），下半部时间线列表（可借鉴 `TransactionTimelineView.vue` 的按月分组与 `transactionListModel.ts` 的 `groupByMonth` 纯函数；本项目 `el-timeline` 只注册未使用，不强行引入）。
- 时间线每行显示：业务日期、变动量、变动后值、说明、`kind` 标签、`recorded_at`（「录入于 …」）；`correction` 行默认折叠。
- 数据有缺口时显示「—」+ 成因文案，不画 0、不插值。

### 9.3 汇总层口径分叉文案（必须）

抽屉顶部一行小字：**「此处为单资产历史明细；家庭净资产走势按每日落库快照生成，不会随补录改写。」** 不重算 `asset_snapshots`（D62），不偷偷抹平差异。

---

## 10. 明确不做（范围边界）

| 不做 | 理由 |
|---|---|
| 房产与房贷的「一次动作同时改两行」关联事件 | 会引入当前无读者的 `group_id`，撞 AGENTS.md:957；用户分别记两条即可，属范围扩展 |
| 名称变更历史 / 改名审计表 | 本期无读者，撞 AGENTS.md:957-958「只写不读禁止建立」；另立卡 |
| 家庭净资产历史曲线重算、`asset_snapshots` 回填 | D62 明文禁止；D98「不得为凑出历史数字编造余额」 |
| 静态资产进收益日历 | `net-worth-caliber.md:131-137` 明令不做；`_WATCHED` 继续排除 `Asset` |
| 全仓 as-of 回放、自动计息、估值提醒 | 远期；本期只做单资产维度 |
| 为存量资产猜 `start_date` | D100；迁移不回填 |
| 改 `conventions.md` §2.10 | 本设计不改任何现有口径，只固定实现侧「恒正」事实 |

---

## 11. 验收标准（逐条可核验）

| # | 标准 | 判据形态 |
|---|---|---|
| A1 | 名称可编辑且不影响汇总 | 编辑弹窗改名后 PATCH body 含 `name`；列表显示新名；`family_totals` 前后数值不变 |
| A2 | 双时间戳 | 补录 30 天前一条事件 ⇒ `effective_date` = 该日、`recorded_at` = 今天 |
| A3 | 系统回填仍被拒 | 任何以当前 `amount` 为输入、目标日期早于今天的批量写入 ⇒ 拒绝 |
| A4 | 补录乱序零重算 | 先录 11 月、再补 10 月 ⇒ 两条 `delta` 原样不动，`value_asof` 与两条都对得上 |
| A5 | 不变量 I1 / I2 | 构造 6 组序列（含负债、纠错、软删）逐组断言恒等与非负 |
| A6 | 缺数据不外推 | `start_date` 为空 ⇒ `valid=false` / `value=null`；查询早于下界 ⇒ 同；前端显示「—」 |
| A7 | 软删不丢锚点 | `status='closed'` 后事件条数不变、I1 仍成立 |
| A8 | 家庭历史不受影响 | 补录前后 `GET /api/summary/snapshots/` 返回逐字节相同 |
| A9 | 幂等 | 同 `client_token` 重放两次 ⇒ 一行事件、`amount` 只变一次 |
| A10 | 只改名不写事件 | 金额未变 ⇒ 事件表零新增 |
| A11 | 域登记与准入留痕 | `DATA_DOMAIN_REGISTRY` 含新表；PR 描述含 §7 四问答案 |
| A12 | 质量门禁 | `质量门禁汇总` 绿；`pnpm typecheck` / 后端相关测试 / ruff 全绿 |

每条判据配**一个回退探针**（变异后必须精确转红、还原后复绿），沿用 D85–D90 的验证纪律。

---

## 12. 分期

| 期 | 内容 | 状态 |
|---|---|---|
| 0 | D99 / D100 决策记录 + 本设计文档 | **本次已完成** |
| 1 | 名称可编辑（纯前端，独立小 PR） | **本次已完成代码，待走 PR** |
| 2 | `asset_value_events` 表 + 域登记 + 写入收口 + 两个 GET 端点 + 明细抽屉 / 时间线 + A2–A11 判据 | 待从 `dev` 切 `feat/asset-value-events` |
| 3 | 家庭级历史联动、全仓 as-of、计息、改名审计 | 明确延后，另开卡 |

**第 0 / 1 期本轮验证记录（2026-11-10，实测）**：

| 检查 | 结果 |
|---|---|
| `pnpm typecheck`（tsc + vue-tsc） | EXIT 0 |
| 新判据 `assetEditDialogName.spec.ts` | 6/6 passed |
| 变异探针：临时摘掉 `save()` 的 `name,` | **精确转红** 1 failed / 5 passed；还原后 6/6 复绿、`git diff` 无残留 |
| `prettier --check`（两个改动文件） | 通过 |
| `eslint --max-warnings 0`（两个改动文件） | EXIT 0 |
| `pnpm test:unit` 全量 | 177 files / **2401 tests** 全绿 |
| `check_vue_size.mjs` | 534 个 .vue 无超阈 |
| `decisions.md` 表格结构 | 新增两行各 4 个竖线，表格未破 |

**未执行 / 未创建**：未跑 Playwright e2e（本环境无浏览器；且本需求最易回潮点是「漏提交 `name`」，源码判据比 DOM 断言更直接，故按项目既有惯例改用结构判据，见 §9.1）；未创建 GitHub issue、未提交代码、未切功能分支——按 `AGENTS.md` 分支规范，从 `dev` 切 `fix/asset-name-editable` 走 PR 由用户执行。

---

## 13. issue 卡面草案（供提卡，**本次未创建 GitHub issue**）

> 标题：`feat(assets): 单资产值变动记录与历史追溯（D99 / D100）`
> 里程碑：按 `AGENTS.md` 归属规则挂 `#17 账本能力对齐` 或 `#2 基础数据`（提卡时确认）
> 正文：粘贴 §7 四问答案 + §11 验收标准 A2–A11 + 本设计文档相对路径；标注「先有设计文档、再动代码」。
> 依赖：第 1 期名称可编辑 PR 先行；无外部数据源依赖。

---

## 14. 风险与未验证项

| 项 | 说明 |
|---|---|
| `name` 作为隐式业务键 | 改名会改变 `sankey_service` 同名负债聚合与 `ledger_migration_service` 去重匹配结果；A1 必须实测，不是理论推断 |
| 规范文字偏差 | `conventions.md:105`「负债存负」与 `assets` 表恒正不一致；实现按实际口径，若将来真要改存储符号，须单独决策并同步本设计 |
| GitHub 侧是否已有同题 issue | 文档侧（`docs/todo.md` / `roadmap.md` / issue 模板）只有账户／总资产层面的曲线诉求，**未联网核对 GitHub issue**；提卡前先搜重 |
| 事件完整性由用户负责 | `value_asof` 的前提是 `delta` 序列完整；用户漏记时系统无法察觉，故 §6.3 的下界与「—」降级不可省 |
