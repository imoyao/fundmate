# 基金转换功能设计（2026-10-17）

> 范围：手动记账页（`/investment/manual`）的「转换」入口，及其后端落库、费用试算、退款/补差与展示。
> 目标：先定方案再写代码。本文所有结论以**本仓现有代码**为准（附证据位置），不照搬基金销售平台的展业规范。
> 相关能力：`#948`（净值回填）、`#1137`（类现金产品绑定）、`#1891`（未保存守卫）、`#2305`（重记预填）。

---

## 0. 结论先行

| 问题 | 结论 | 一句话理由 |
|---|---|---|
| 要不要新建表 | **v1 不建表** | `transactions.link_group_id` 已经能承载「多腿成组」，红利再投已用它配对两条流水 |
| 要不要新增 `txn_type` | **存储层不新增，展示层新增独立类型 `convert`**（后端下发 `display_type`） | 用户看到/筛选/复盘的确实是「转换」一等类型；但落库不必新增枚举——新增枚举要同步 8 处白名单，其中 5 处是静默失败（详见 §3.4） |
| 退款记在哪 | **必须落真实流水**（第 3 条腿），`extra` 只存元数据 | 只在 `extra` 里记金额＝没有账，与「记一笔」的初衷冲突；金额/份额一律以流水为准 |
| 退款申购货基后能否在持仓页看到 | **能**，但用「类现金分组」读流水聚合展示，**不给货基建 position** | 总资产已含孤儿货基（`summary_service`），再建 position 会双计；详见 §4.5 |
| 撤销 / 修改已提交的转换要不要新表 | **不要**，按 `link_group_id` 组内重放 | 现有删除流水已支持「从流水重算持仓」，组级删除 + 重放可复用同一套；约束见 §3.5 |
| 草稿存哪 | **只存前端**（IndexedDB / localForage），后端不做草稿 | 已有通用 `useReconDraft`（TTL 7 天、版本化、sanitize），导入页在用 |
| 交割单把转换拆成两条怎么办 | 解析器只落**原始 buy/sell**，转换组是**派生可重算**关系；L1 关键词才自动成组，L2 同日一卖一买只出「疑似」候选，不自动合并 | 同日卖 A 买 B 与正常调仓同构，误合并代价大于漏合并 |
| 持仓页要不要也显示类现金 | **要**，与账户页同一口径、不重复加总 | 账户页答「这个账户有多少」，持仓页答「我的钱都在哪」 |
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

### 1.4 类现金产品不是「持仓」，但**是真实流水**（当前有个可见性缺口）

`auto_purchase_money_fund()`（`services/position_service.py`）生成的是 **`entry_status='orphan'` 的 `buy` 流水**，`asset_type='money_fund'`、`position_id IS NULL`，**不建 position**。

净额聚合的唯一口径是 `summary_service.orphan_money_fund_totals_by_ledger()`（判定用 `position_id IS NULL`，不是 `entry_status`），它已经：① 计入总资产；② 在账户详情「类现金」卡片里展示（`LedgerCashLikeCard.vue`，文案明确「不建持仓，故不在环形图内」）；③ 在交易记录列表里可见（列表只按 `family_id` 过滤，不过滤孤儿）。

**缺口只有一个**：持仓页（`views/asset/inventory/index.vue`）只渲染 `positions` 表，所以货基不出现。这正是 §4.5 要补的展示，不是「没记账」。

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
| 退款去向 `refund_preference` | **采纳**：去向落 `extra.conversion.refund_mode`，**金额落真实流水** | 与组号同处，够用；金额不能只活在 JSON 里 |
| 幂等键 | **采纳**：`import_hash` 已存在唯一索引，转换提交用「组号 + leg 角色」派生 hash | 避免重复点击/重试产生两对流水 |
| 试算与确认两次算费 | **采纳**，且要求同一函数 | 前端只展示服务端返回值 |

**本轮新增的四条拍板（2026-10-17 二次确认）**：

| 议题 | 结论 | 见 |
|---|---|---|
| 退款资金怎么记 | **真实流水**（第 3 条腿），`extra` 只存去向/拆分等元数据 | §3.1、§4.5 |
| 转换的交易类型 | **对用户与前端是独立类型 `convert`**（后端下发 `display_type`），存储仍用 `sell`/`buy` | §3.4 |
| 撤销 / 修改已提交的转换 | **不新增表**，按 `link_group_id` 组内删除 + 重放 | §3.5 |
| 草稿 | **只存前端**（IndexedDB），后端不做草稿接口 | §3.6 |

**明确不做（v1）**：

- 不做跨账户转换（转换必须同账户，跨账户是「赎回 + 申购」两件事）。
- 不做「超级转换/垫资」类平台的资金占用建模（我们记的是结果，不是渠道的资金流）。
- 不做「已确认（T+1）之后改金额」的冲正（走 §3.5 的组级更正，前端会提示重新录入）。

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

**退款不是「只记在 extra 里」**：`leg-3` 是一条**真实流水**，`amount` 就是退款金额，会被交易列表、账户现金流、类现金聚合各自读到。`extra.conversion.refund_mode` / `refund_symbol` 只说明「这笔钱去了哪」，不承载金额——金额的唯一真相是流水。

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

`撤销/修改` 不再是建表理由（见 §3.5，组内重放即可）。只剩两条：

1. 转换需要在**设备间同步**草稿（前端草稿只在本机，换设备看不到——这是有意的取舍）。
2. 一条转换的腿数 **> 3**，或需要按 leg 记**不同确认日/部分确认**（流水组没有独立的组级字段）。

当前手工记账场景（一次操作当场落库、腿数 ≤ 3）都不满足。

### 3.4 交易类型：对用户是独立类型，对存储不是

**用户要的是「转换」这个一等类型**：列表里能一眼看到、能筛选、点进去能复盘「这笔转换划不划算」。这一点完全成立，本设计采纳。

但「独立类型」不一定等于「新增 `txn_type` 枚举」。先看新增枚举的真实成本（全仓白名单消费点）：

| # | 位置 | 新增类型后的后果 |
|---|---|---|
| 1 | `services/importer/mappings.py` `BusinessType` + `VALID_OP_TYPES` | **硬报错**：导入器遇到未知类型直接判非法 |
| 2 | `services/performance/xirr_engine.py` 现金流方向 | **静默丢**：`convert_*` 不在 in/out 集合 → 现金流消失、XIRR 虚高 |
| 3 | `services/pnl_service.py` `_INVEST_TXN_TYPES` / `_DIVEST_TXN_TYPES` | **静默漏**：净投入与成本基数不算 |
| 4 | `position_service.recompute_position_from_transactions()` | **静默漏**：删/改流水后份额原地不动 |
| 5 | `domains/transactions/views.py` 删除后的重算白名单 | **静默不重算**：删了转换流水，持仓还是错的 |
| 6 | `services/reconciliation_service.py` 买卖集合 | **误报**：净份额漏算 → 天天报「孤儿/差异」 |
| 7 | `services/summary_service.py` 孤儿现金流集合 | **静默 continue**：类现金/现金流漏算 |
| 8 | `domains/positions/views.py` `_KNOWN_OP_TYPES` | **硬 400**：手工录入直接拒绝 |
| 9 | 前端 `TXN_TYPE_LABELS` / `TransactionTable.typeClass` | 显示原始英文 code + 中性色 |

注意第 2~7 项的共同点：**不报错、不崩溃、只是少算**。这类缺陷最难发现，也最容易变成"账不对但查不出原因"。

而且新增枚举**并不能省掉显示成本**：转换天然是两条腿，列表仍要按组折叠成一行，否则用户看到「卖出 + 买入」两条。折叠逻辑无论如何都得写。

**裁决（方案 A）**：

- 存储：`sell` + `buy`（+ 退款腿），`extra.conversion` 标记组内角色。
- 接口：后端为每条流水计算并下发 `display_type`，转换组内两条腿的 `display_type = 'convert'`，其余等于 `txn_type`。
- 前端：类型标签、颜色、图标、筛选、详情页**只认 `display_type`**；筛选「转换」时后端按 `link_group_id IS NOT NULL AND extra.conversion IS NOT NULL` 过滤。
- 效果：用户侧「转换」是独立类型、独立筛选、独立详情；工程侧不动任何 txn_type 白名单。

这不是临时 hack，而是本仓既有范式：红利再投就是「存 `dividend` + `buy`，展示折叠成一条『红利再投资』」，`dividend_service` 还靠「同组是否存在 buy」判定它的 kind。

### 3.5 撤销 / 修改：组内重放，不新增表

现有能力已经够用：

- 删除单条流水后，`transactions/views.py` 会调 `PositionService.recompute_position_from_transactions()` **从剩余流水重算持仓**（净份额 ≤ 0 删行；持仓行已被清掉时可依剩余买入流水重建）。
- 编辑走 `PATCH /api/ledgers/<lid>/transactions/<tid>/`，改数量后同样触发重算。

因此新增两个组级端点即可：

```
DELETE /api/positions/conversion/<link_group_id>/      # 撤销：删组 → 重算持仓 → 清自选状态
PUT    /api/positions/conversion/<link_group_id>/      # 修改：删组 → 用新参数重放 → 重算
```

实现要点：

1. **一个事务**：删组 + 重算 + 重放 + 再重算，任一步失败整体回滚（不能出现"删了没重放"的中间态）。
2. **重算对象是「涉及到的 position_id 集合」**，不是固定两个：退款腿无持仓，跳过。
3. **可编辑窗口（必须做）**：该组之后，两只基金若已有后续流水（再买入/赎回/分红），组内重放会让后续流水的成本与份额交错。判定：两标的在该组 `trade_date/created_at` 之后存在任何流水 → **禁止删改**，前端提示「该笔转换之后已有新交易，无法撤销；请用一笔反向转换更正」。
4. **已确认（`confirmed`）的转换**：允许撤销（物理删除），但要二次确认并提示「确认份额已入账，撤销后持仓将按流水重算」。
5. **审计**：本仓交易删除本来就是物理删除、无审计表（`TransactionEditDialog` 的删除也是）。转换沿用同一口径，**不为此单独建表**；如将来需要留痕，应该是给 `transactions` 加统一的历史表，而不是转换专用表。
6. **幂等/防重**：组级接口按 `link_group_id` 操作，天然幂等（第二次调用时组已不存在 → 返回 404 或 `already_revoked`）。

### 3.6 草稿：只在前端

- 复用 `frontend/src/composables/useReconDraft.ts`（localForage/IndexedDB，TTL 7 天，`sanitizeRows` 剥离函数与循环引用，Set↔数组序列化）。
- 转换需要**独立草稿槽**（现有导入草稿是全局单槽 `recon-draft`）：新增 `conversion:{ledgerId}` 键，避免一次导入把转换草稿冲掉。
- 存的内容：`step`、`ledger_id`、`out_symbol`/`out_quantity`、`in_symbol`/`in_amount`、`refund_mode`、`trade_date`、`updated_at`；**不存试算结果**（净值会变，恢复后重新试算）。
- 恢复时校验账户是否仍存在、是否仍有该持仓；不满足则丢弃草稿并提示。
- 提交成功 / 明确放弃后 `discardDraft()`；离开页面只弹确认，不自动保存到后端。

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

### 4.5 退款买到货基之后，持仓页怎么显示

**前提**：这笔申购一定有一条真实流水（§3.1 的 leg-3），交易记录里能看到；要解决的是「持仓页看不到」。

两条路径：

| | 路径 A：持仓页新增「类现金」分组（**推荐**） | 路径 B：给货基建 position 行 |
|---|---|---|
| 数据源 | 复用 `summary_service.orphan_money_fund_totals_by_ledger()` | `positions` 新增 `asset_type='money_fund'` 行，`quantity` 按 1.0000 净值折算 |
| 总资产 | **不加总**（已含，见 `summary_service` 的 orphan 合并），只展示 | 必须同步改聚合，否则**双计** |
| 货基收益 | 用既有 `money_fund_income.py`（净额基线 + 万份收益） | 收益基线会与净额叠加，需要重写 `_collect_position_market_value` |
| 对账 | 无影响 | `reconciliation_service` 会把「有持仓无流水差额」当差异报出 |
| 其他副作用 | 无 | 进 XIRR 分母（默认排除 money_fund）、被 `orphan_backfill_job` 反向回填、聚合视图多一类 |
| 成本 | 1 个只读接口 + 1 个展示组件 | 5 处口径同步，风险面最大 |

**裁决：路径 A**。理由：本仓已经把「类现金产品按流水净额计市值」定为口径（`#1137`），总资产、账户详情卡片、现金流三处都按这个口径对齐；为了一个展示位改建 position，会把三处已经对齐的口径重新拆开。

具体落地：

- 后端：`GET /api/positions/cash-like/?ledger_id=` 返回 `{ symbol, name, amount, income_amount, nav_date, income_7d }`，内部直接调 `orphan_money_fund_totals_by_ledger`，**不做任何加总**。
- 前端：持仓页在持仓表下方新增「类现金」分组（可折叠），行内展示「产品名 / 持有金额 / 昨日收益 / 七日年化」，点击进入产品详情；空态不渲染。
- 文案必须写明这是**账面口径**（按流水净额计，不是份额×净值），避免与基金持仓的「份额 × 净值」混淆。
- 该行**不参与**持仓盈亏、不参与持仓占比环图（与账户详情卡片现有口径一致）。

---

### 4.6 持仓页也要有「类现金」（已做）

账户详情的 `LedgerCashLikeCard` 已经回答了「这个账户里的活期+有多少」；持仓页回答的是「我总共有什么」，两者不是重复：

- 账户页：单账户视角，跟着账户走；
- 持仓页：家庭视角，跨账户，用户在这里找「我的钱都在哪」。

因此本页新增「类现金」分组（位于持仓明细之后、「其他投资」之前），数据源为 `GET /api/summary/cash-like/`（按「账户 + 产品」归组），展示本金 / 累计收益 / 合计，空列表不渲染。

**口径红线**：分组里的合计只是明细求和，**不得**并入页面任何总额（`summary_service` 已经把孤儿净额算进 `total_assets`，再加一次就是双计）。组件底部固定一行说明文案。

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
10. **离开守卫 + 草稿**：第 1~3 步有已填内容时，切换操作类型 / 路由离开 / 切换账户都要确认（复用 `useUnsavedChangesGuard`）；同时按 §3.6 保存前端草稿，下次进入弹「发现未完成的转换草稿，继续？」（Banner，不弹窗打断）。
11. **撤销入口**：第 4 步与转换详情页提供「撤销这笔转换」，走 §3.5 的组级删除；若该组之后已有新交易则置灰并给出原因。

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

### 6.6 交易列表与复盘：转换是独立类型

用户要的不只是「能筛选」，而是能复盘这笔决策。因此除列表标签外，还要有一个**转换详情视图**：

| 位置 | 展示 |
|---|---|
| 交易列表 | 一行「转换」：`转出 A 5,540 份 → 转入 B（预估 1,510.66 份）`，右侧显示净转入金额；颜色用**中性蓝/品牌中性色**，不套涨红跌绿（转换没有涨跌语义） |
| 类型筛选 | 一级类型新增「转换」；后端按 `link_group_id` 组过滤（不是按 `txn_type`） |
| 转换详情 | 四条关键数字：转出金额、费用合计（展开＝赎回费/补差费）、转入金额、退款；下方列出各腿明细（可点进单条流水） |
| 复盘卡（P3） | 「转换时点对比」：转出基金在本组 T 日净值 vs 转入基金在 T+N 的净值走势，给出「转入后跑赢/跑输转出 X%」的中性描述。**不做买卖建议**，只做事实陈述 |
| 状态 | 待确认（T+1）/ 已确认 / 已撤销；待确认时金额标「预估」 |

「高卖低买」类判断**不落库**，由复盘卡实时计算（净值都在 `daily_worth`），避免再加一套派生字段。

---

## 7. 本轮顺带修掉的三处 UI 缺陷（已实现）

1. **「新建账户」按钮白字隐身**：`type="primary" text` 在本仓 `theme.scss` 下拿到白字 + 透明底。改为描边次按钮（`--bg-card` 底 / `--text-primary` 字 / hover 变 `--brand-ink`）。
2. **操作类型切换不符合 D13 果冻胶囊**：原实现是「软底轨道 + 白色滑块 + 6px 圆角」的 iOS 分段控件，且 6 项等分会把「红利再投 / 送股拆分」压成两行。改为**每项独立胶囊**（`--radius-pill`、1px `--border-default` 描边、选中 `--brand-100` 底 + `--brand-400` 描边 + `--brand-700` 字 + `style-pop` 回弹），`flex-wrap` 平铺。
3. **未保存守卫误报**：`BuyForm` 的「重记一笔」预填（`#2305`）发生在 `markFormClean()` 之后，导致页面一挂载 `isDirty` 即为 true——用户什么都没填、只切操作类型就被弹「记账表单已填写，确定放弃吗？」。修法：预填与净值回填完成后重设脏基线（用户已录入金额/份额时**不**重置，避免洗掉真实编辑）。

---

## 8. 分期落地

> **进度（2026-10-18）**：P0 / P1 已实现并合入分支 `feat/manual-conversion-p0p1`
> （试算 `f1d5fd661`、落库 `3d35afa32`、前端步骤条 `2ea79303f`）。
> P1 相对设计的收窄：「确认日改份额」的 T+1 改价流程未做——v1 按预估份额落库，
> 用户可走既有交易编辑（PATCH）修正；`display_type` / 列表折叠 / 转换详情 /
> 撤销（组级删除）属 P3，复盘卡与草稿属 P4。

| 期 | 内容 | 验收 |
|---|---|---|
| P0 | `estimate` 服务 + 单测（费用、FIFO、补差、份额取整） | 纯函数级用例：2 基金 / 带退款 / 费率缺失 / 全部转出 / 跨类型拒绝 |
| P1 | `POST /conversion` 落库（2 基金场景）+ 前端步骤条 1~3 步 + 结果页 | 转出持仓减、转入持仓增、两条流水同 `link_group_id`、资产总额守恒（±费用）、XIRR 不异常 |
| P2 | 退款腿（类现金 / 账户现金）+ 补差拦截 + 持仓页「类现金」分组 | 三条流水；退款后总资产仍守恒；货基分组**不加总**（与总资产对账相等） |
| P3 | `display_type` + 列表折叠/筛选 + 转换详情 + 撤销（组级删除） | 列表中不出现两条孤立买卖；筛选「转换」命中整组；撤销后两名持仓均按流水重算正确 |
| P4 | 复盘卡 + 前端草稿 | 复盘数字可复算（净值直接取 `daily_worth`）；草稿跨刷新恢复、账户删除后自动丢弃 |

每期都要有的回归：

- `recompute_position_from_transactions()` 对组内任一流水删除/重放后份额、均价正确（含清仓行重建）；
- `auto_purchase_money_fund` 不被误触发（断言无额外孤儿流水）；
- 幂等键重复提交只产生一组流水；
- 转换前后总资产差 = 费用合计（分，精确相等）。

---

## 9. 决策记录

**已拍板（2026-10-17 用户确认）**：

| # | 问题 | 结论 |
|---|---|---|
| D1 | 退款资金怎么记 | 落**真实流水**；`extra` 只存去向与费用拆分，不承载金额 |
| D2 | 退款买货基后是否要在持仓页看到 | 要；用「类现金分组」读流水聚合展示，不建 position（§4.5） |
| D3 | 草稿 | 只在前端（IndexedDB），后端不做草稿 |
| D4 | 撤销/修改已提交的转换 | 不新增表，按 `link_group_id` 组内删除 + 重放（§3.5） |
| D5 | 转换的交易类型 | 对用户与前端是**独立类型 `convert`**（后端下发 `display_type`），存储仍用 `sell`/`buy`（§3.4） |
| D6 | 转入金额 > 净额（垫资） | 不允许，v1 直接拦；补款单独记一笔 |
| D7 | 退款默认去向 | 优先账户绑定的类现金；未绑定则账户现金 + 引导绑定 |
| D8 | 「全部」的尾差 | 允许保留（历史 4 位数据），清仓判定用精确值，不抹零 |
| D9 | 费率缺失能否提交 | 允许，确认页显式提示并落 `extra.warnings` |
| D10 | 转换后是否同步自选状态 | 与卖出同口径，复用 `_silent_reconcile_watchlist` |

**仍待定（不阻塞 P0/P1）**：

| # | 问题 | 说明 |
|---|---|---|
| O1 | 已确认（T+1）后撤销是否需要留痕 | 本仓交易删除本就是物理删除、无审计表；若要做，应是全表级别的历史表，不做转换专用表 |
| O2 | 货基「类现金分组」是否也要覆盖逆回购 | 建议一起覆盖（同属 `asset_type in ('money_fund','reverse_repo')`），待 UI 确认 |
| O3 | 转换详情里的「复盘卡」是否需要基准对比（如沪深 300） | 一期先做「转出 vs 转入」两条净值对比即可 |

---

## 10. 交割单导入：平台可能把转换拆成两条，也可能给一行

这是本方案里**唯一必须靠真实样本才能定的事**。已知三种形态：

| 形态 | 平台导出长什么样 | 难点 |
|---|---|---|
| ① 拆成两条 | 同日（或相差 ≤1 天）「赎回 A」+「申购 B」，备注可能写「转换」也可能什么都不写 | 与「卖 A 买 B 的正常调仓」在数据上**完全同构**，误判会把两笔独立交易并成转换 |
| ② 一行转换 | 业务类型＝「基金转换」，字段可能是「转出 A / 转入 B / 费用」合在一行，也可能只有转出侧 | 字段不齐时**无法**合成另一条腿，硬造就是脏数据 |
| ③ 单边在途 | 今天只有转出行（T 日），转入行 T+1 才出现 | 导入时点不同会得到不同结果，需要可重算 |

### 10.1 工程原则：先落原始流水，再算组关系

**解析器永远只产出 `buy` / `sell` 原始流水**（保留 `raw_payload`），转换组是**派生的、可重算的**关系（`link_group_id` + `extra.conversion`）。理由：

1. 判定错了改判定即可，不用重解析、不用回滚持仓；
2. 平台换导出格式不影响账；
3. 重复导入靠 `import_hash` 幂等——**组号不能进 hash**，否则同一份文件重导会生成新组号、重复入库；
4. 组号由导入批次内**确定性生成**（`hash(account + out_row_id + in_row_id)`），不是随机 UUID，重导结果一致。

### 10.2 三层识别，默认保守

| 层 | 触发条件 | 行为 |
|---|---|---|
| L1 确定性 | 业务类型 / 摘要命中关键词：`转换`、`基金转换`、`转换转入`、`转换转出`、`超级转换`、`同公司转换` | 直接成组，导入预览里显示「已识别为转换」 |
| L2 启发式 | 同账户 + 同交易/确认日（相差 ≤1 天）+ 一卖一买 + 两端均为场外基金 + 金额匹配（见下）+ 一对一最优匹配 | **只标「疑似转换」候选，不自动合并**，预览页给「合并 / 保持两笔」二选一 |
| L3 人工 | 用户在交易列表选中两条 → 合并；对已识别的组 → 拆分 | 任何自动判定都必须可逆 |

L2 不自动合并的理由：**同一天卖 A 买 B 是最常见的调仓方式**，与转换在字段上不可区分。误合并的代价是费用归属错误、复盘失真、以后想拆还得手工修；漏合并的代价只是列表多两行。两害相权，宁漏勿错。

金额匹配公式（允许容差 `max(1 元, 0.5%)`）：

```
卖出金额 − 赎回费 − 补差费 ≈ 买入金额
（费用列存在时直接用；缺失时用 份额 × 净值 估算，并标 confidence=low）
```

若同时出现多个候选（例如卖出 A 后买入 B、C 两笔），**只有一个能一对一匹配时才出候选**；一对多直接不出，交给人。

### 10.3 形态 ②③：v1 不自动补腿

- 只有转出侧：按普通 `sell` 入账 + `extra.import.pending_leg='in'`，导入结果页提示「转换转入待确认」；等 T+1 的转入行进来再由用户或后续规则合并。
- 只有一行且缺转入份额/净值：**不合成**第二条腿。合成需要净值与费用，猜出来的数会进入持仓成本和盈亏，属于不可接受的数据污染。

### 10.4 需要你提供的样本

在写识别规则前，至少需要 3 份真实交割单（脱敏即可）：天天基金、支付宝/蚂蚁、一家券商（或你最常用的两个平台）。要确认的字段：

1. 「业务类型 / 摘要」的原始枚举值有哪些（是否区分转换转入/转出）；
2. 是否有「转换」关键字，还是只能靠同日一卖一买推断；
3. 费用是否单列（赎回费 / 补差费是否分列）；
4. 转入确认是否单独一行、日期是否 T+1；
5. 同一笔转换是否有可复用的平台单号（有的话 L1 直接按单号成组，最稳）。

**在这些样本到位前，转换导入保持「L1 才合并、其余原样导入」**，不做更激进的推断。

---

## 附录 A：与草案字段的对应关系

| 草案字段 | 本仓落点 |
|---|---|
| `conversion_id` / `app_sheet_no` | `transactions.link_group_id` + `extra.conversion.group_no` |
| `status` | `transactions.entry_status`（+ `extra.conversion.status`） |
| `apply_date` / `confirm_date` | `transactions.trade_date` / `confirm_date` |
| `total_out_amount` / `total_fee` / `total_net_in_amount` | OUT 腿 `amount` / `fee`，IN 腿 `amount`；合计由组内求和派生，不另存 |
| `leg.transfer_direction` | `txn_type`（`sell` = OUT，`buy` = IN）；对外统一由 `display_type='convert'` 呈现 |
| `leg.application_vol` / `confirmed_vol` | 申请阶段 `quantity`（预估）→ 确认日改写为确认份额 |
| `leg.nav` / `nav_date` | `price` + `extra.conversion.nav_date` |
| `leg.redeem_fee` / `recuperate_fee` | OUT 腿 `fee` + `extra.conversion.fee_breakdown` |
| `leg.undistribute_income` | v1 不做（§2） |
| `refund_preference` | `extra.conversion.refund_mode` |
| `settle_status` | 退款腿是否存在 + `entry_status` |
| `fund_cash_ledger.idempotency_key` | `transactions.import_hash`（已有唯一索引） |
