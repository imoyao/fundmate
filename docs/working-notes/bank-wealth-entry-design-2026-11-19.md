---
title: 银行理财录入落地设计（#931）
---

# 银行理财录入落地设计（#931）

> **决策口径（2026-11-19 用户拍板）**：`symbol` = 理财产品**登记编码**；**产品名称**用于检索与展示；记账方式 `balance`。
> 关联：#931（本设计）、#2850（`bank_wealth` 进 `asset_type`，已闭环）、D70（`balance` 强制口径）。
> 本文取代 `importer-architecture.md` §5.2 的旧结论「留在 `bank` 账户资产记录，不进标准 `positions`」。

## 0. 一句话

银行理财**进 `positions`**（`asset_type='bank_wealth'`、强制 `valuation_mode='balance'`），`symbol` 用银登中心产品登记编码，产品名称只作检索键与展示名；前端在 `bank` 账户的记账通路补出这个品类。

## 1. 现状核查（2026-11-19，基于 `origin/dev`）

| 能力 | 状态 | 证据 |
|---|---|---|
| `asset_type` 有 `bank_wealth`（与 `bank`=银行存款 分离） | ✅ 已有 | `backend/app/core/asset_types.py` |
| 只允许 `balance` 记账，`nav` 直接拒 | ✅ 已有 | `services/position_buy_command.py` `_BALANCE_ONLY_ASSET_TYPES` |
| 无市场 / 无交易场所 | ✅ 已有 | `core/venues.py` `_NO_VENUE_ASSET_TYPES` |
| 投资分层判据（稳健档） | ✅ 已有 | `core/investment_tiers.py`（#2850） |
| 显式 `asset_type` 优先于代码推断 | ✅ 已有 | `services/position_write_support.py` `_SPECIFIC_ASSET_TYPES` |
| **前端能录出 `bank_wealth`** | ❌ 缺失 | `useSecuritySearch.ts` 手填标的恒推 `fund`/`money_fund`；`buyFormPayload.ts` 只对 `portfolio` 发 `valuation_mode='balance'` |
| **产品名检索命中** | ❌ 缺失 | `services/asset_search.py` 无 `bank_wealth` Provider |
| **期限 / 基准 / 风险等级 / 登记编码 字段** | ❌ 缺失 | `positions` 无对应列；`maturity_date` 注释写死「仅 reverse_repo 使用」 |
| 前端「手动建仓」入口 | ❌ 不存在 | 全仓无「新增持仓」入口，持仓只由买入 / 导入产生 |

结论：**后端地基已就位，缺的是「录入通路 + 检索通路 + 期限字段」**。这是实现卡而非设计卡。

## 2. 身份与唯一性（`symbol` = 登记编码）

- 落库约束是 `uq_positions_ledger_symbol (ledger_id, symbol)`（`domains/positions/models.py`）。
  登记编码由银行业理财登记托管中心按产品发放、全市场唯一 ⇒ 同账户内「同产品一条持仓」天然成立。
- **同名不同期 / 不同渠道的产品，编码不同 ⇒ 两条持仓**，这是正确行为，不做名称合并。
- 归一化：登记编码含字母，写入前统一大写去空白（`symbol_norm` 与 `normalize_asset_type` 同口径），
  避免 `z7001…` / `Z7001…` 分裂成两条。
- **一期口径：登记编码必填。**
  - 备选方案 B「编码缺失时用 `BW_` + 产品名归一化临时码」**不做**：临时码会让同一产品因写法不同分裂，
    后续要写「补编码 + 合并持仓」迁移，成本高于一期收益。若实测用户普遍拿不到编码，再开二期。
  - 编码位置：银行 App 产品详情 / 产品说明书首页「产品登记编码：Z7xxxxxxxxxxxx」。

## 3. 检索通路（「产品名可以正常搜索」怎么实现）

新增 Provider `_search_bank_wealth(db, q)`，写入 `services/asset_search.py`：

- **数据源**：`positions` 中 `asset_type='bank_wealth'` 的行，按 `(symbol, name)` 去重（一个产品多次申购只有一行持仓）。
- **匹配**：`symbol ILIKE %q%` OR `name ILIKE %q%` —— 用户输产品名或粘贴登记编码都能命中。
- **返回**：`{code: symbol(登记编码), name: 产品名, asset_type: 'bank_wealth', market: '', venue: '', extra: {}}`。
- **注册**：同时进 `SEARCH_PROVIDERS` 与 `_OTHER_LOCAL_PROVIDERS`（本地源命中即不再触发基金外部兜底）。
- **路由**：必须用 ORM 查询 `Position`，由 `_RoutingSession` 逐句路由到 user 库；**禁止裸 SQL**（#3091 教训）。
- **family 过滤**：与读侧一致，按 `get_family_id()` 过滤。

**必须让用户知道的局限**：中国理财网无公开 API（`importer-architecture.md` §5.1 已确认），
所以这里的搜索是「**本地已知产品库**」= 用户自己录过的产品。**首次录入搜不到，必须手填编码 + 名称**；
第二次起（含跨账户加仓）可搜。全市场目录不做（见 §7）。

## 4. 录入通路（前端）

1. `components/QuickEntry/composables/useSecuritySearch.ts`
   `buildManualOption` 当前把 `bank` 账户的手填标的硬推成 `fund`/`money_fund`。
   改为：`bank` 账户下手填时同时给出「银行理财」候选（`type: 'bank_wealth'`, `type_label: '银行理财'`），
   由用户选，不猜。
2. `components/QuickEntry/buyFormPayload.ts`
   `isPortfolio` 单值判断 → 「balance-only 集合」`{portfolio, bank_wealth}`（与后端 `_BALANCE_ONLY_ASSET_TYPES` 同集合），
   两者都发 `valuation_mode: 'balance'`、`quantity: 0`、金额即市值。
3. `BuyForm.vue`
   balance 品类隐藏「份额 / 净值」行（现在只对 `portfolio` 隐藏）；价格行同样不渲染。
4. 表单校验
   登记编码：非空、`^[A-Za-z0-9]{8,32}$`、写入前大写；产品名：非空、≤100 字。

## 5. 元数据（一期最小集）

| 字段 | 一期 | 理由 |
|---|---|---|
| 登记编码 | 作 `symbol` | 身份键，复用既唯一约束 |
| 产品名称 | 作 `name` | 展示 + 检索 |
| 金额 / 市值 | `market_value_override` | balance 模式唯一市值出口（D80） |
| 到期日 | **放开 `maturity_date`**：注释与校验从「仅 reverse_repo」扩到 `reverse_repo` + `bank_wealth` | 已存在的列，零迁移 |
| 业绩比较基准 / 风险等级 | 一期**不做字段**，写 `notes` | 无估值用途，不为一期扩表 |
| 登记编码副本列 | **不做** | 与 `symbol` 冗余 |

## 6. 与「资产盘点」的边界（防重复计资产）

`assets` 表（大类 `investment` / 子类 `bank_wealth`）**也计入总资产**
（`services/portfolio_service.py` 汇总含 `Asset`，仅排除 `liability`），但**不进收益口径**。

⇒ 同一笔银行理财若两处都记，总资产会翻倍。一期口径：

- **记账入口只有一个**：`bank` 账户 → 记账 → 银行理财（进 `positions`，进收益）。
- 资产盘点里的「投资理财 · 银行理财」子类保留给**静态估值**用途（不想记流水/收益的场景）。
- 一期文案写明这条；「两处同时存在时提示」列为二期巡检，不在本次范围。

## 7. 明确不做

- ❌ 爬取中国理财网作全市场产品库：合规与稳定性双风险，且只用于名称补全的收益不抵维护成本。
- ❌ 银行理财净值估值：不在公开基金名录，`balance` 是唯一正确模式（D70 同口径）。
- ❌ 产品名称合并（不同编码 = 不同产品，同名也不合并）。

## 8. 验收标准

- `GET /api/search/assets/?q=<产品名>` 能命中已录入的银行理财，返回 `asset_type='bank_wealth'`、`code` 为登记编码。
- 输登记编码片段同样命中（`symbol ILIKE`）。
- `bank` 账户记账表单可选「银行理财」，提交后落 `positions`：`asset_type='bank_wealth'`、`valuation_mode='balance'`、`quantity=0`、`market_value_override=金额`。
- 提交 `valuation_mode='nav'` 的银行理财被后端拒（沿用现有 `_BALANCE_ONLY_ASSET_TYPES` 判据）。
- 同一账户同一登记编码重复录入不产生第二行持仓（`uq_positions_ledger_symbol` 兜底）。
- 小写登记编码入库后归一为大写，不分裂。
- `maturity_date` 可写入 `bank_wealth` 持仓，且原 `reverse_repo` 校验不回归。

## 9. 拆分建议（按 PR）

| PR | 范围 | 依赖 |
|---|---|---|
| 1（本文） | 设计文档 + 修正 `importer-architecture.md` §5.2 旧结论 + `decisions.md` 记一条 | 无 |
| 2 | 后端 `_search_bank_wealth` Provider + 单测 | PR1 |
| 3 | 前端录入通路（手填品类 / balance 集合 / 隐藏份额行）+ 提交单测 | PR2 |
| 4 | `maturity_date` 扩义 + 校验与注释 | PR3 |
