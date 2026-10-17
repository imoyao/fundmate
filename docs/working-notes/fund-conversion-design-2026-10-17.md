# 基金转换功能设计（2026-10-17）

> 范围：手动记账页（`/investment/manual`）的「转换」入口，及其后端落库、费用试算、退款/补差与展示。
> 目标：先定方案再写代码。本文所有结论以**本仓现有代码**为准（附证据位置），不照搬基金销售平台的展业规范。
> 相关能力：`#948`（净值回填）、`#1137`（类现金产品绑定）、`#1891`（未保存守卫）、`#2305`（重记预填）。

---

## 0. 结论先行

| 问题 | 结论 | 一句话理由 |
|---|---|---|
| 要不要新建表 | **v1 不建表** | `transactions.link_group_id` 已经能承载「多腿成组」，红利再投已用它配对两条流水 |
| 要不要新增 `txn_type` | **v1 不新增**，复用 `sell` / `buy` | 新增类型要同步 XIRR、盈亏、导入映射、列表筛选、CSV 导出五处；`extra.conversion` 足够表达语义 |
| 费用在哪算 | **服务端单一实现**，试算与落库同源 | 赎回费依赖 FIFO 持有期、补差费依赖两只基金的费率阶梯，前端算必然漂移 |
| 份额精度 4 位是否 bug | **不是 bug，是三处口径不一致**：存 4 / 录 4（赎回）或 2（申购）/ 展示 2 | 建议统一「录入与展示 2 位、存储保持 4 位」，**不做数据迁移** |
| 交互形态 | **四步步骤条**，沿用导入页 `el-steps` 的视觉与节流方式 | 转换是不可逆的资金操作，一步填完提交没有复核环节 |

---

## 1. 现状盘点（代码事实）

### 1.1 「转换」目前只有一个入口按钮，没有任何实现

- 前端：`frontend/src/views/asset/investment/manual/index.vue` 有 `fundOpType === 'convert'` 的分支，但动态表单区落到 `else` 占位「转换 功能开发中」。
- 后端：`backend/app/domains/positions/views.py` 的 `_KNOWN_OP_TYPES` 不含 `convert`；`backend/app/services/position_service.py` 的 `dispatch_position_op()` 对未知 op 直接 `raise ValueError`。
- 全仓 `convert*` 命中都是**可转债**（`convertible_bond_terms` / `bond_convert_price`），与基金转换无关。

### 1.2 手动记账的写入链路（转换必须复用的那条）

| 环节 | 位置 |
|---|---|
| 前端提交 | `usePositionSubmit.ts` → `POST /api/positions/` |
| 视图 | `backend/app/domains/positions/views.py` `create_position()` |
| 分派 | `services/position_service.py` `dispatch_position_op()` |
| 落库 | `process_buy_or_deposit()`（买入合并、移动加权均价）/ `process_sell_or_withdraw()`（份额扣减、已实现盈亏） |

流水与持仓的单位（`domains/transactions/models.py`、`domains/positions/models.py`）：

| 字段 | 存储单位 | 说明 |
|---|---|---|
| `transactions.quantity` / `positions.quantity` | 整数，**0.0001 份** | 换算唯一入口 `Money.shares_to_min_unit()`（×10000，ROUND_HALF_UP） |
| `transactions.price` / `positions.avg_price` | 整数，**0.0001 元** | `Money.yuan_to_price_units()` |
| `transactions.fee` / `transactions.amount` | 整数，**分** | `Money.yuan_to_cents()` |

### 1.3 `link_group_id` 已经是「交易组」的现成载体

`transactions` 有 `link_group_id String(36)`，红利再投已经用它把「分红现金 + 申购」两条流水配成一组：

- `_create_dividend_cash_txn()` / `_reinvest_dual_flow()`（`services/position_service.py`）
- 导入器侧也给「债券兑息 + 兑息兑付」打同一组号（`domains/importers/parser.py`）

**转换 = 同一 `link_group_id` 下的 2~3 条流水**，这套机制不需要新发明。

### 1.4 类现金产品不是「持仓」

`auto_purchase_money_fund()`（`services/position_service.py`）生成的是 **`entry_status='orphan'` 的 `buy` 流水**，`asset_type='money_fund'`，**不建 position**，市值按流水净额计入总资产。

这条事实决定了「退款自动申购货基」在数据层就是一条孤儿流水，不需要货基持仓表。

它还有两个坑：

1. 当前唯一调用点是**普通卖出**路径，转换若直接复用 `process_sell_or_withdraw()`，会**顺带触发一次自动申购**（钱被重复计一次），必须在转换链路里显式关掉。
2. 货基 / 逆回购自身的卖出不触发，避免「赎回 → 自动申购」死循环（同上注释）。

### 1.5 费用数据齐备

| 数据 | 位置 | 用途 |
|---|---|---|
| 申购费率阶梯 | `funds.purchase_rules`（金额区间）+ `fee_ratios`（`fee_type='purchase'`） | 补差费 |
| 赎回费率阶梯 | `funds.redeem_rules`（持有天数区间）+ `fee_ratios`（`fee_type='redeem'`） | 转出赎回费 |
| 赎回费试算 | `FundService.estimate_redeem_fee()`（FIFO）+ `POST /api/funds/redeem-fee/estimate/` | 可直接复用 |
| 费率结构查询 | `FundService.get_fund_fee_rates()` + `GET /api/funds/<code>/fee-rates/` | 试算页展示阶梯 |
| 申购费折扣 | `ledgers.fee_config.subscription_discount`（默认 0.1） | 两只基金的申购费都要乘这个折扣 |

### 1.6 表结构变更机制

无 Alembic。建表走 `init_db()` = `Base.metadata.create_all()` + `backend/app/core/migrations.py` 的启动期幂等迁移（`migrate_<表>_<变更>(engine) -> str`）。

若将来确需新增表：带 `family_id` 的表归 **user 域**，必须在 `backend/app/core/db_factory.py` 的 `DATA_DOMAIN_REGISTRY` 与 `docs/dev/db-data-domain.md` 两处登记，否则启动校验直接拒绝。

### 1.7 份额精度：三处口径不一致

| 环节 | 现状 | 证据 |
|---|---|---|
| 存储 | 4 位（0.0001 份） | `Money.shares_to_min_unit()` |
| 申购录入 | **2 位** | `BuyForm.vue` 份额输入 `:precision="fund ? 2 : 0"` |
| 赎回录入 | **4 位** | `SellForm.vue` `:step="0.0001" :precision="4"` |
| 列表 / 表格展示 | **2 位** | `utils/format.ts` `formatQuantity()`（`maximumFractionDigits: 2`） |
| 后端校验 | **无精度校验** | `PositionCreate.quantity: Optional[float]` |

即：同一笔 2293.9812 份，申购入口只能录到 2293.98，赎回入口能录 4 位，列表只显示 2 位。

---

## 2. 对草案的评审（哪些采纳、哪些改）

| 草案要点 | 处理 | 理由 |
|---|---|---|
| 三层表：申请主表 / 方向明细 / 资金流水 | **改为两层**：流水（自带方向与金额）+ 组号 | 本仓 `transactions` 一行就是「一个方向的一笔钱」，`link_group_id` 就是组。再加三层表等于把已有字段重写一遍，且要同步 XIRR/盈亏两套代码 |
| 申请单号 `app_sheet_no` | **v1 用 `link_group_id` + `extra.conversion.group_no`** | 用户可见编号由前端/后端从组号派生，不落独立列 |
| 状态机 `PENDING → CONFIRMED` | **复用 `entry_status`**（`pending` / `confirmed` / `orphan`）+ `confirm_date` | 已有语义完全一致（基金 T+1 待确认） |
| 未知价法：申请时不写死份额 | **采纳** | 试算只出「预估份额」，确认日再改 `quantity` |
| 货币基金未付收益单独结转 | **v1 不做**（列边界） | 本仓货基按流水净额计市值（§1.4），没有「未付收益」独立字段；强行加会与 `money_fund_income` 的收益行口径冲突。等货基收益入账口径统一后再议 |
| 退款去向 `refund_preference` | **采纳，但不落订单表**：落 `extra.conversion.refund_mode` | 与组号同处，够用 |
| 幂等键 | **采纳**：`import_hash` 已存在唯一索引，转换提交用「组号 + leg 角色」派生 hash | 避免重复点击/重试产生两对流水 |
| 试算与确认两次算费 | **采纳**，且要求同一函数 | 前端只展示服务端返回值 |

**明确不做（v1）**：

- 不做「申请 → 撤销」的状态回退（手工记账场景，撤销 = 删流水）。
- 不做跨账户转换（转换必须同账户，跨账户是「赎回 + 申购」两件事）。
- 不做「超级转换/垫资」类平台的资金占用建模（我们记的是结果，不是渠道的资金流）。

---

## 3. 数据模型（v1：零新表）

### 3.1 一条转换 = 2~3 条流水

设：转出基金 A、转入基金 B、账户绑定的类现金产品 M（可空）。

```
link_group_id = <uuid hex>
├─ leg-1  OUT : txn_type='sell'   symbol=A  quantity=转出份额  price=转出净值
│           fee = 赎回费 + 补差费   amount = 转出份额 × 净值
│           extra.conversion = { role:'out', group_no, fee_breakdown:{redeem, compensate} }
├─ leg-2  IN  : txn_type='buy'    symbol=B  quantity=确认份额  price=转入净值
│           fee = 0                amount = 净转入金额
│           extra.conversion = { role:'in', counter_symbol:'A' }
└─ leg-3  REFUND（可选）:
     · 退类现金 → txn_type='buy', asset_type='money_fund', symbol=M, quantity=0, price=0,
                  entry_status='orphan', amount=退款金额（与 §1.4 自动申购同构）
     · 退账户现金 → txn_type='deposit', asset_type='cash', symbol='__CASH__',
                  entry_status='orphan', amount=退款金额（与导入器现金行同构）
```

**费用只记在 OUT 腿**：赎回费与补差费都是「从转出金额里扣掉的」，记在 OUT 腿的 `fee` 上，`realized_pnl` 自然减掉总费用；IN 腿 `amount` 记的是净额、`fee=0`，否则成本会被重复加一遍。

拆分放在 `extra.conversion.fee_breakdown`，前端「费用明细」两行（赎回费 / 补差费）从 `extra` 读，不做二次计算。

### 3.2 `extra.conversion` 字段约定（版本化）

```json
{
  "conversion": {
    "v": 1,
    "group_no": "C20261017001",
    "role": "out",
    "status": "pending",
    "nav_date": "2026-10-17",
    "counter_symbol": "012708",
    "fee_breakdown": { "redeem": 19.33, "compensate": 0.0 },
    "refund_mode": "money_fund",
    "refund_symbol": "000198",
    "supplement_amount": 0.0,
    "estimated": true
  }
}
```

- `extra` 已是 `Text` 列，存 JSON 字符串，读写走一处 helper（禁止各调用点自行 `json.loads`）。
- `status` 与 `entry_status` 不重复表达：`entry_status` 是系统级处理阶段，`status` 是转换业务态（`pending` / `confirmed` / `partial`）。

### 3.3 什么时候才需要真正建表

只有出现下列需求之一，才值得引入 `fund_conversion_order`：

1. 转换申请需要在**设备间同步/跨会话编辑**（流水组承载不了草稿）。
2. 需要**撤销/修改**已提交的申请（需要订单行做状态机，流水只增不减）。
3. 一条转换的腿数 **> 3**（多基金一进多出），或需要按 leg 记不同确认日与部分确认。

当前手工记账场景（一次操作当场落库、腿数 ≤ 3）都不满足。

---

## 4. 服务端设计

### 4.1 两个端点

**试算（只读，不落库）**

```
POST /api/positions/conversion/estimate
{
  "ledger_id": 12,
  "out_symbol": "012708",
  "out_position_id": 345,
  "out_quantity": 5540,          // 份额；null = 全部转出
  "in_symbol": "012709",
  "in_amount": 4700.00,          // 可选：用户指定转入金额；缺省 = 净额全部转入
  "trade_date": "2026-10-17",
  "is_after_15": false
}
```

返回（字段全部是「预估」，前端加「预估」标识）：

```json
{
  "out": { "quantity": 5540, "nav": 1.3956, "amount": 7731.62, "fee": 19.33,
           "fee_breakdown": { "redeem": 19.33, "compensate": 0 },
           "realized_pnl_estimate": -12.40 },
  "in":  { "nav": 5.055, "amount": 7636.41, "quantity": 1510.66 },
  "net_amount": 7636.41,
  "refund": { "amount": 0, "options": [{ "type": "money_fund", "symbol": "000198" },
                                      { "type": "account_cash" }] },
  "supplement": { "amount": 0, "required": false },
  "warnings": []
}
```

**提交（落库）**

```
POST /api/positions/conversion/
{ ...同上, "refund_mode": "money_fund", "idempotency_key": "<uuid>" }
```

提交内部：**一个 DB 事务**内依次 `process_sell_or_withdraw(auto_purchase=False)` → `process_buy_or_deposit(force_create_position=True)` → 退款腿。任一步失败整体回滚。

### 4.2 费用算法（唯一实现）

```
赎回费 = Σ(按 FIFO 分摊到各买入批次的份额 × 该批次持有天数对应费率) × 当日净值
补差费 = MAX(0, 转入申购费(净额) − 转出申购费(净额)) × 折扣
      其中 申购费(x) = 按 purchase_rules 金额阶梯取率 × x  （含 fee_ratios 的固定金额档）
```

三个必须钉住的点：

1. **赎回费走 FIFO**，直接复用 `FundService.estimate_redeem_fee()`，不要另写一份。
2. 补差费的「转出基金申购费」是**按本次转入金额重新计算的**，不是用户当初实付的费用（草案这一点正确）。
3. 折扣 `subscription_discount` 对**两只基金同时生效**（同一销售平台同一折扣），不能只打折转入侧。
4. 舍入：费用到分（`ROUND_HALF_UP`），份额到 2 位；**所有中间值用 `Decimal`**，禁止 `float` 裸算（现有 `Money` 类已提供入口）。

### 4.3 退款 / 补差

| 场景 | 记账 |
|---|---|
| 净额全部转入 | 2 条流水，`refund.amount = 0` |
| 用户指定转入金额 < 净额 | 2 条流水 + 退款腿（类现金 `buy` 或账户现金 `deposit`） |
| 用户指定转入金额 > 净额（垫资/补款） | v1 **不允许**：前端直接拦下并提示差额，补款请单独记一笔充值。理由：垫资是渠道行为，记账系统没有"应付"科目，硬记会让资产恒等式失真 |

退款腿必须显式选择去向（默认取账户绑定的类现金产品），不选则不允许提交——**不允许"差额凭空消失"**。

### 4.4 必须做的校验（否则会记出错账）

1. 转出份额 ≤ 该持仓可用份额（含 `pending_nav` 占位持仓的边界）。
2. 转出基金 ≠ 转入基金（同基金转换无意义，多数平台也不允许）。
3. 两只基金都必须是 `fund` 类；转入基金**必须支持申购**（费率表缺失时给出警告而不是静默 0 费）。
4. 同一账户；账户类型为 `fund` / `bank`（与现有基金操作组一致）。
5. 转换后转出持仓若份额为 0 → 走清仓逻辑（`process_sell_or_withdraw` 已处理持仓行删除与 `realized_pnl` 落流水）。
6. 幂等：`idempotency_key` + 组号派生 `import_hash`，重复提交返回同一次结果而不是新增流水。
7. `auto_purchase_money_fund` **必须关闭**（§1.4 的坑），由转换服务传参显式禁用。

---

## 5. 份额精度：结论与修法

### 5.1 结论

不是「后端存 4 位错了」，而是**入口与出口的位数不统一**：

- 用户看到的（列表）是 2 位；
- 赎回入口允许 4 位，申购入口只允许 2 位；
- 存储 4 位是为了成本均价的精度（`avg_price` 也是 4 位，份额精度低于它会让成本出现系统偏差）。

基金行业确认份额普遍是 2 位，4 位属于「多出来的精度」，会带来三个实际坏处：

1. **对不上账**：平台显示 2293.98，我们录 2293.9812，市值差 0.02~0.03 元，用户会以为我们算错。
2. **"全部卖出"残留**：全部卖出时若输入框把 4 位截成 2 位，会留下 0.0012 份的幽灵持仓。
3. **入口不一致**：买入 2 位、卖出 4 位，用户无法理解规则。

### 5.2 修法（不迁移数据）

| 改动 | 内容 |
|---|---|
| 录入 | 申购 / 赎回 / 转换统一 **2 位**（`precision=2`、`step=0.01`） |
| 「全部」 | 不受输入框精度影响，直接传持仓精确值（4 位内部精度），提交后由后端按清仓处理 |
| 展示 | 保持 2 位（现状已如此）；详情/对账处提供精确值 tooltip |
| 后端 | 存储保持 0.0001 不变；新增**入参校验**：非「全部」提交时超过 2 位小数直接 400，而不是静默四舍五入 |
| 不做的 | 不改 `Money`、不改表结构、不做数据回填 |

这样「存得比看得多」只是内部精度，不会出现在用户面；同时避免"看起来对不上"。

---

## 6. 交互设计：四步步骤条

### 6.1 为什么用步骤条

导入页（`views/asset/investment/import/index.vue`）已经用 `el-steps` ①选账户 ②上传 ③预览 ④结果，用户对这套节奏有认知。转换同样是「不可逆的资金操作 + 需要复核」，一步填完提交风险太高。

**复用边界**：只统一视觉与步骤语义，**不复用**导入的 composable（那边是文件解析 + 草稿 + 去重，状态模型完全不同）。

### 6.2 四步定义

| 步 | 标题 | 内容 | 可否离开 |
|---|---|---|---|
| 1 | 选择转出 | 转出基金（只能选当前账户持有的，下拉带可用份额/持有天数）+ 转出份额（含 25/50/75/100% 快捷） | 可返回 |
| 2 | 选择转入 | 转入基金（全市场搜索，**当前账户已持有的置顶**）+ 转入金额/份额（默认 = 净额全部转入） | 可返回 |
| 3 | 费用与确认 | 服务端试算结果：转出、费用明细（赎回费/补差费分行）、净转入、预估份额、退款去向、风险提示 | 提交前 |
| 4 | 结果 | 申请单号、状态（待确认 T+1）、已提交摘要、后续操作 | 完成 |

### 6.3 关键交互规则（专业度都在这些细节里）

1. **转出只查本账户持仓**：不能用全市场搜索。数据源就是现有 `getPositionsGroupedByAccount()`，与 `SellForm` 同源。
2. **转入全市场搜索，但持仓置顶**：与 `BuyForm` 的搜索同一套 `searchSecurities`；结果列表分两段「当前持有 / 全部基金」，不做两套搜索框。
3. **步骤条不可点回跳**：只能通过「上一步」返回，且**返回时保留已填内容**（不重新请求净值）。
4. **每步都有校验门**：第 1 步份额 > 0 且 ≤ 可用；第 2 步转入基金 ≠ 转出基金；第 3 步必须有试算结果。
5. **试算 debounce 400ms**：金额/份额变化不逐字请求；请求带 `requestId`，过期响应丢弃（避免倒序覆盖）。
6. **所有基于当日净值的数字带「预估」标识**，页面底部固定一行说明：「实际以 T 日净值确认结果为准，T+1 确认、T+2 可赎回」。
7. **费率缺失不静默**：`fee_rates` 为空时第 3 步显示黄色提示「该基金费率数据缺失，费用按 0 计，请以确认单为准」，不阻断提交但留痕。
8. **退款去向**：默认取账户绑定的类现金产品（`ledger.linked_money_fund`）；未绑定则只能选「退回账户现金」，并提示「可在账户设置里绑定活期+，以后自动申购」。
9. **提交按钮防重**：提交中禁用 + 幂等键；成功后清空表单并跳到第 4 步，不重复弹「再做一笔」。
10. **离开守卫**：第 1~3 步有已填内容时，切换操作类型 / 路由离开 / 切换账户都要确认（复用 `useUnsavedChangesGuard`）。第 4 步不拦。

### 6.4 视觉规范（对齐 `frontend/design.md`）

| 元素 | 规范 |
|---|---|
| 步骤条 | `el-steps :active="step" finish-status="success" align-center`，与导入页一致；移动端 `simple` 或隐藏标题只留圆点 |
| 页面容器 | 与导入页一致：`max-width` 居中卡片，`PageHeaderBar` 统一步骤标题 |
| 操作类型切换 | **D13 果冻胶囊**（每项独立胶囊 + `role="radiogroup"`），不是 iOS 分段轨道，见 §7 |
| 试算面板 | 两列键值对齐（左标签 `--text-secondary`、右数值 `tabular-nums`），费用明细分行，净额用 `--text-primary` + 字重 600 |
| 主按钮 | 仅第 3 步「确认转换」是实底主按钮（`--brand-solid`），其余为次要按钮 |
| 空态 | 账户无持仓时：鹦鹉螺单线插画 + 「该账户暂无持仓，无法转换」+ 「去记一笔申购」按钮 |
| 危险提示 | 退款/补差金额用 `--color-warning`，不使用涨红/跌绿（非行情语义） |

### 6.5 与现有「卖出 / 申购」表单的关系

转换**不复用** `BuyForm` / `SellForm` 组件：两者都带账户选择、费用模式切换、净值联动等大量与转换无关的状态，硬塞会造出第二个"半成品"。转换用独立 `ConversionForm`，但**复用**：

- `useSecurityPriceRange` / `useFundTradeDate` / `calcConfirmAndNav`（净值与确认日）
- `estimateRedeemFee`（赎回费）
- `AssetTypeBadge` / 产品搜索组件

---

## 7. 本轮顺带修掉的三处 UI 缺陷（已实现）

1. **「新建账户」按钮白字隐身**：`type="primary" text` 在本仓 `theme.scss` 下拿到白字 + 透明底。改为描边次按钮（`--bg-card` 底 / `--text-primary` 字 / hover 变 `--brand-ink`）。
2. **操作类型切换不符合 D13 果冻胶囊**：原实现是「软底轨道 + 白色滑块 + 6px 圆角」的 iOS 分段控件，且 6 项等分会把「红利再投 / 送股拆分」压成两行。改为**每项独立胶囊**（`--radius-pill`、1px `--border-default` 描边、选中 `--brand-100` 底 + `--brand-400` 描边 + `--brand-700` 字 + `style-pop` 回弹），`flex-wrap` 平铺。
3. **未保存守卫误报**：`BuyForm` 的「重记一笔」预填（`#2305`）发生在 `markFormClean()` 之后，导致页面一挂载 `isDirty` 即为 true——用户什么都没填、只切操作类型就被弹「记账表单已填写，确定放弃吗？」。修法：预填与净值回填完成后重设脏基线（用户已录入金额/份额时**不**重置，避免洗掉真实编辑）。

---

## 8. 分期落地

| 期 | 内容 | 验收 |
|---|---|---|
| P0 | `estimate` 服务 + 单测（费用、FIFO、补差、份额取整） | 纯函数级用例：2 基金 / 带退款 / 费率缺失 / 全部转出 / 跨类型拒绝 |
| P1 | `POST /conversion` 落库（2 基金场景）+ 前端步骤条 1~3 步 + 结果页 | 转换后：转出持仓减、转入持仓增、两条流水同 `link_group_id`、资产总额守恒（±费用）、XIRR 不异常 |
| P2 | 退款（类现金 / 账户现金）+ 补差拦截 + 类现金默认项 | 三条流水场景；退款后总资产与转换前一致（扣费） |
| P3 | 列表折叠展示「转换」+ 详情页（按组展开各腿、费用明细、状态） | 交易列表不出现两条孤立买卖；组内合计费用 = 各腿费用之和 |

每期都要有的回归：

- 转换后 `recompute_position_from_transactions()` 删除任一流水不出负份额；
- `auto_purchase_money_fund` 不被误触发（断言无额外孤儿流水）；
- 幂等键重复提交只产生一组流水。

---

## 9. 待拍板（需要你决定）

| # | 问题 | 建议 |
|---|---|---|
| Q1 | 转入金额允许**大于**净额（垫资）吗？ | 不允许，v1 直接拦；补款单独记 |
| Q2 | 退款默认去向：账户绑定的类现金 / 账户现金？ | 绑定优先，未绑定则账户现金 + 引导绑定 |
| Q3 | 转出「全部」时，是否允许残留 0.01 份（历史 4 位数据的尾差）？ | 允许尾差保留，但清仓判定用精确值，不做强行抹零 |
| Q4 | 转换是否出现在「交易类型」筛选里（新增 `convert` 虚拟类型）？ | 列表按 `link_group_id` 折叠即可，筛选沿用「买入/卖出」两条真实类型，避免全链路加枚举 |
| Q5 | 费率缺失时是否允许提交？ | 允许，但必须在确认页显式提示并落 `extra.warnings` |
| Q6 | 是否需要「转换后自动更新自选状态」？ | 与卖出同口径，复用 `_silent_reconcile_watchlist` |

---

## 附录 A：与草案字段的对应关系

| 草案字段 | 本仓落点 |
|---|---|
| `conversion_id` / `app_sheet_no` | `transactions.link_group_id` + `extra.conversion.group_no` |
| `status` | `transactions.entry_status`（+ `extra.conversion.status`） |
| `apply_date` / `confirm_date` | `transactions.trade_date` / `confirm_date` |
| `total_out_amount` / `total_fee` / `total_net_in_amount` | OUT 腿 `amount` / `fee`，IN 腿 `amount`；合计由组内求和派生，不另存 |
| `leg.transfer_direction` | `txn_type`（`sell` = OUT，`buy` = IN） |
| `leg.application_vol` / `confirmed_vol` | 申请阶段 `quantity`（预估）→ 确认日改写为确认份额 |
| `leg.nav` / `nav_date` | `price` + `extra.conversion.nav_date` |
| `leg.redeem_fee` / `recuperate_fee` | OUT 腿 `fee` + `extra.conversion.fee_breakdown` |
| `leg.undistribute_income` | v1 不做（§2） |
| `refund_preference` | `extra.conversion.refund_mode` |
| `settle_status` | 退款腿是否存在 + `entry_status` |
| `fund_cash_ledger.idempotency_key` | `transactions.import_hash`（已有唯一索引） |
