# 组合批次级（Lot）归因立项设计 —— #1095 远期方案（2026-08-25）

> 关联：GitHub Issue [#1095](https://github.com/imoyao/fundmate/issues/1095)（本设计对象）
> 决策依据：D20（`docs/spec/decisions.md` 2026-08-24 条目）、实施计划 `portfolio-strategy-unification-2026-08-24.md`
> 状态：立项设计（待实施）；排序 = 先做 D20 一期，本方案留作「二期之后」
> 本次拍板结论：① b 方案永久否决；② 唯一可行路径 = c（批次级 lot）；③ 现金归属 = **按 lot 归属**；④ 排序 = 先做 D20 一期，#1095 留作二期之后。

---

## 0. 结论速览

- 同标的分批分属不同组合的场景，现有 `positions` 聚合行（同账户同标的 = 一行，总量 + 摊薄成本）**在 D20 一期（持仓 1:1 归属组合）下也无法表达**，必须下沉到批次层。
- 路径 b（持仓级多对多）已在 #1095 与 D20 中**永久否决**：经代码核对，`get_portfolio_holdings`（`portfolios/views.py:213-215`）是逐行循环算市值/盈亏、无 DISTINCT/去重/窗口逻辑，同一持仓挂两个组合会被算两遍导致前端翻倍，且无法回答「100 股里多少属 A、多少属 B」。
- 唯一可行路径 = 路径 c（批次级 lot）：在 `positions` 物理行之上新增独立的批次层 `lots`，每笔买入 = 一个 lot，lot 携带 `portfolio_id`；组合归因精确到买入批次。
- 本设计把 #1095 的 4 项前置依赖展开为可执行实施设计，并落实「现金按 lot 归属」的产品决策。

---

## 1. 目标与场景

**场景**：用户同一标的（如腾讯）分多批买入，前一批属组合 A（目的 X），后一批属组合 B（目的 Y）。操作层面应被允许；但 `positions` 是聚合行，无法表达「一条持仓行内部分属不同组合」。

**目标**：
- 不破坏现有「一条持仓行 = 聚合数量 + 摊薄成本」的存储与交易链路（买入/卖出/成本计算逻辑零改动）。
- 用独立的批次层 `lots` 承载「组合归属」语义，使组合维度归因精确到每个买入批次。
- 现金（卖出所得 / 分红）按 lot 归属到对应组合，支持定量收益归因。

**非目标（本期）**：b 方案的多对多绑定、持仓行的物理拆分。

---

## 2. 与 D20 一期 / 二期的关系（排序锚点）

D20 已定稿「组合 = 持仓级」，`positions.portfolio_id` 可空（空 = 继承账户「默认组合」）。但该字段**当前尚未落地**（代码核对：`positions/models.py` 仅有 `ledger_id`，无 `portfolio_id`）。

| 阶段 | 内容 | 与 #1095 前置依赖的对应 |
|---|---|---|
| **D20 一期（先做，未实施）** | `positions.portfolio_id` 列 + 存量回填 + `get_portfolio_holdings` 改写 + `account_name`→`ledger_id` 修复（views.py:193） | 覆盖 #1095 前置 ② 的「持仓视图侧」修复 |
| **#1095 c 方案（二期之后）** | `lots` / `lot_consumptions` 表 + 写入路径 + 现金按 lot 归属 + XIRR 引擎重写（含清理 xirr_engine.py:349 死代码）+ 历史回填 | 覆盖前置 ①（现金定义）③（引擎重写）④（回填）；前置 ② 的 XIRR 侧（xirr_engine.py:303）随引擎重写一并消除 |

**边界**：一期解决「持仓 → 组合」的 1:1 归属；c 方案解决「持仓内部按批次拆分到多组合」。一期是 c 的硬前置——c 的 `lots.portfolio_id` 直接复用一期建立的 portfolio 概念与回填机制。

---

## 3. 数据模型设计（user 域）

`lots` 与 `lot_consumptions` 均由 `positions` / `transactions` 派生，含 `family_id`，归属 **user 域**；模型不声明域属性，须在 `app/core/db_factory.DATA_DOMAIN_REGISTRY` 中央注册表登记（2026-08-24 规则修正，见 AGENTS.md「数据域架构」）。

### 3.1 `lots` 表（批次）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | 自增 |
| family_id | Integer (FK, user 域) | 家庭隔离 |
| position_id | Integer, FK→positions.id, ondelete=CASCADE | 所属聚合持仓行 |
| portfolio_id | Integer, FK→portfolios.id, ondelete=SET NULL, nullable | 该批次所属组合；NULL = 继承账户默认组合（ledger.portfolio_id） |
| txn_id | Integer, FK→transactions.id, ondelete=RESTRICT, nullable | 创建该 lot 的买入交易（溯源 + 回填） |
| lot_date | Date | 买入 confirm_date（FIFO 排序键） |
| quantity | Integer | **原始**批次数量（0.0001 份/min_unit，同 positions.quantity 单位） |
| remaining_quantity | Integer | 卖出消耗后剩余（min_unit） |
| cost_basis | Integer | 原始批次总成本（分），= 买入金额（+费用） |
| avg_cost | Integer | cost_basis / quantity（分/份），便利字段 |
| confidence | String | `high` / `low`；历史回填 lot = `low` |
| source | String | `realtime`（实时写入）/ `backfill`（回填） |

**不变量**（迁移与写入路径必须维护）：`Σ lot.remaining_quantity == position.quantity`；`positions.avg_price` 可由 lots 重建（加权平均 cost_basis/quantity）。

**索引**：`(family_id, portfolio_id)`、`(position_id)`、`(txn_id)`（唯一，upsert 用）。

### 3.2 `lot_consumptions` 表（卖出消耗记录）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | 自增 |
| family_id | Integer (user 域) | 家庭隔离 |
| sell_txn_id | Integer, FK→transactions.id | 触发消耗的卖出交易 |
| lot_id | Integer, FK→lots.id, ondelete=CASCADE | 被消耗的批次 |
| quantity | Integer | 本笔卖出消耗该 lot 的数量（min_unit） |
| proceeds | Integer | 分摊到该消耗的卖出所得（分） |
| cost_basis_consumed | Integer | 该消耗对应的成本（分） |
| realized_pnl | Integer | proceeds - cost_basis_consumed（分，已实现盈亏归因） |

**用途**：组合现金流与已实现盈亏归因时，直接按 `lot_id` 反查；避免每次请求重算 FIFO。

### 3.3 单位约定

沿用现有 Money 约定：`quantity` = 0.0001 份（min_unit），价格/金额/成本 = 分（cents）。所有 lot 字段换算必须走 `app/core/money.py` 的 `Money`（禁止直接 float 运算）。

---

## 4. 四个前置依赖的展开实现

### 4.1 现金归属业务定义（按 lot 归属）—— #1095 前置 ①

本次拍板：**每个批次的卖出/分红现金记到该批次所属组合**。细则：

- **BUY / DIVIDEND_REINVEST**：流出（成本）归属该 lot 所属组合；reinvest 新建 lot 落在源 lot 同一组合。
- **SELL**：按 FIFO 消耗 lots；卖出所得（proceeds）按被消耗数量比例分摊到各被消耗 lot 所属组合；已实现盈亏同理（proceeds - 消耗 cost_basis）。例：卖 100 股 = 消耗 lotA(组合 X)60 + lotB(组合 Y)40 → X 得 60%、Y 得 40%。
- **DIVIDEND_CASH**：按该持仓当前 `lots` 的 `remaining_quantity` 权重分摊到各 lot 组合。**v1 近似**用「当前剩余权重」；历史精确分摊（需持仓历史剩余状态）列为后续增强（见 §8）。
- **DEPOSIT / WITHDRAW（账户级出入金）**：**不进入组合现金流**——组合 XIRR 仅由 lot 驱动。这同时消解 `xirr_engine.py:349` 的死代码（账户级出入金本就被 `_exclude_internal_transfers` 丢弃、从未进现金流），lot 化后直接不再采集账户级出入金。
- **内部划转（跨账户）**：组合口径下不计入。

### 4.2 数据层修复 `account_name` → `ledger_id` —— #1095 前置 ②

两处必须同源修复，避免「持仓视图修了、XIRR 仍断」：

- **`portfolios/views.py:193`** `Position.account_name.in_(ledger_names)` → 一期改为按 `positions.portfolio_id` 直接归属（D20 一期职责），彻底摆脱账户名字符串匹配，根治「账户改名断链 / 串仓」。
- **`xirr_engine.py:303`** `Transaction.account_name.in_(ledger_names)` → 在引擎重写（4.3）中整体替换为「按 `lots` / `lot_consumptions` 取现金流」，字符串匹配自然消失。

### 4.3 XIRR 现金流引擎重写 —— #1095 前置 ③

重写 `generate_portfolio_cashflows`（`xirr_engine.py:263-356`）：

1. 取目标组合 P 的 lots：`portfolio_id == P` **或**（`portfolio_id IS NULL` 且该 lot 所属 position 的账户 `ledger.portfolio_id == P`，继承解析）。
2. 每 lot 在 `lot_date` 记流出 `-cost_basis`。
3. 每 lot 经 `lot_consumptions` 在卖出日记流入 `+proceeds`（按 4.1 分摊后的值）。
4. 每笔 DIVIDEND_CASH 按 lots 权重记流入（4.1）。
5. 期末虚拟卖出 = `Σ remaining_quantity × current_price`，记为 `end_date` 流入。
6. 排序输出 `(date, amount)` 序列喂给现有 XIRR 计算器。

**清理**：删除 `xirr_engine.py:349` 的 `_ = _exclude_internal_transfers(...)` 死代码；`_exclude_internal_transfers` 函数随账户级出入金不再采集而移除（或保留为空操作，建议删除）。

**三层口径衔接**：组合层 = lots 聚合；持仓层 = 现有 `calculate_position_xirr`；账户层 = 现有 Ledger XIRR。三者并列，过渡期隐藏的组合 XIRR 区块在二期新口径下恢复。

### 4.4 历史批次回填 —— #1095 前置 ④

幂等脚本（可重复跑，先清 lots 再重建 or upsert by `txn_id`）：

1. 按 `family` 遍历 `positions`。
2. 按 `transactions`（BUY / DIVIDEND_REINVEST，按 `confirm_date` 升序）机械重建 lots：每笔买入 = 一个 lot 候选，`quantity = txn.quantity`、`cost_basis = txn.amount(+fee)`、`lot_date = txn.confirm_date`、`txn_id = txn.id`。
3. 归属：默认继承该持仓现属组合（一期回填后的 `positions.portfolio_id`；若 NULL 则继承账户 `ledger.portfolio_id`），标记 `confidence='low'`。
4. 对 SELL 交易按 FIFO 在 lots 扣减 `remaining_quantity` 并写 `lot_consumptions`。
5. **不变量校验**：`Σ lot.remaining_quantity == position.quantity`；差异记录为 `low-confidence` 待人工，不阻断。

---

## 5. 实施分期

- **P0 前置（先做）**：D20 一期 —— `positions.portfolio_id` 列 + 存量回填 + `get_portfolio_holdings` 改写 + views.py:193 `ledger_id` 化（同时覆盖 #1095 前置 ② 持仓侧）。
- **P1**：`lots` / `lot_consumptions` 模型 + 写入路径（buy/reinvest 建 lot、sell 消耗 lot 并写 `lot_consumptions`）+ 历史回填脚本 + 不变量校验 + 单测。写入路径须事务内同步 `position.quantity` 与 lot 数量。
- **P2**：XIRR 引擎重写（4.3）+ 清理 :349 死代码 + 组合 XIRR 恢复展示（新口径）。
- **P3 前端**：组合详情按 lot 展示归属（同标的多 lot 分组合）、组合 XIRR 区块恢复、分红/卖出归属可视化。

---

## 6. 测试与验收

- 单测（pytest 单进程，防 OOM）：
  - 同标的两批次分属 A/B → `get_portfolio_holdings(A)` 只含 lotA 数量、组合 B 只含 lotB；组合 XIRR 各自独立。
  - 卖出跨 lot 时现金按消耗比例归因（4.1 例：60/40 分摊）。
  - DIVIDEND_CASH 按 lots 权重分摊到组合。
  - 回填不变量 `Σ lot.remaining_quantity == position.quantity`。
  - `account_name` 改名不再断链（前置 ② 回归）。
- 前端 `vue-tsc` 零错误。

---

## 7. 迁移与回滚

- `lots` / `lot_consumptions` 为**新增表**（ADD，不删任何现有列）；回填 UPDATE 可重跑。
- 回滚：drop 两表 + 删写入路径代码即可；`positions` / `transactions` 不动，旧口径不受影响。
- 死代码删除属纯清理，可独立 revert。

---

## 8. 风险与开放子决策

- **卖出消耗算法**：v1 仅 FIFO。是否支持用户指定批次（指定成本基础法）列为后续增强。
- **分红历史精确分摊**：需持仓历史剩余状态，成本高；v1 用当前剩余权重近似。
- **双写一致性**：`position.quantity` 与 lot 数量必须由 service 层事务同步（buy 同时 +position.quantity 与 +lot.quantity；sell 同时扣），避免漂移。
- **性能**：lots 随交易增长；组合现金流请求时现算，须对 `(family_id, portfolio_id)` / `(position_id)` 建索引；大组合可考虑结果缓存。

---

## 9. 引用

- GitHub Issue [#1095](https://github.com/imoyao/fundmate/issues/1095)（本设计对象，状态 OPEN / Q2-YELLOW，留作二期之后）
- `docs/spec/decisions.md` 2026-08-24 条目（D20 组合体系殊途同归）
- `docs/working-notes/portfolio-strategy-unification-2026-08-24.md`（D20 实施计划）
- 代码锚点：`portfolios/views.py:193`（account_name 匹配）、`:213-215`（无去重循环）；`xirr_engine.py:263-356`（generate_portfolio_cashflows）、`:303`（account_name 匹配）、`:349`（死代码 `_ = _exclude_internal_transfers`）；`positions/models.py`（字段与单位：quantity=0.0001 份、avg_price/current_price=分）
