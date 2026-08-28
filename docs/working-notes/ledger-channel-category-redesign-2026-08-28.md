# 账本渠道分类（channel_category）重设计方案

> 权威记录：本文件是账本"渠道分类"重设计的唯一权威说明。代码注释须反向引用本文件（见 §7）。
> 关联：#1101 基金E账户聚合；后续 issue：聚合视图视觉优化、场内证券（ETF/可转债）聚合卡片。

## 1. 背景与根因
- 现象：微众银行（商业银行）被显示为"基金平台"分组，与用户感知（"钱放在银行卡里"）冲突。
- 根因：前端分组硬绑 `ledger_type`（`ledgers/index.vue` 按 `ledger_type` 分组；`constants/index.ts` 映射 `fund→基金平台`）；导入器给所有命中销售机构的账本无脑设 `ledger_type='fund'`（`services/importer/orchestrator.py`）。
- 正确判别字段 `sales_institutions.org_type`（证券公司 / 独立基金销售机构 / 商业银行 / 全国性商业银行 / 保险 / 期货 …）一直存在，却未被用于分组。

## 2. 双字段模型（核心）
账本现在有两个正交字段，维护者必须分清：

### 2.1 `ledger_type`（账户类型 / 内部资产类键）
- 语义：账户持有的**资产品种本质**，驱动计算、费率结构、视图分支（如货币基金收益仅 fund 账本展示）。
- 取值：`stock` / `fund` / `bank` / `property` / `e_account` / `family`。
- **用户不可见**，不作为分组或"账户类型"标签展示。
- 何时写：仅在"账户持有的资产品种本质变化"时由系统改（极少）。手动建账时由用户选的"分组"经映射推导，维护者不应把它当展示标签用。

### 2.2 `channel_category`（渠道分类 / 用户可见分组）
- 语义：用户感知的**机构渠道类别**（钱放在哪类机构）。
- 取值：`bank`（银行）/ `securities`（证券·券商）/ `fund_platform`（基金平台·第三方独立销售）/ `insurance`（保险）/ `futures`（期货）/ `other`（其他）。
- **用户可见**：同时作为"账户列表分组"和"账户类型标签"。
- 何时写：建账/导入时由系统从 `sales_institution_id → org_type` 映射自动写入；手动建账由用户选的"分组"推导写入。**用户从不直接编辑此字段。**

### 2.3 维护者铁律
- 分组、类型标签、排序、筛选：**只读 `channel_category`**，绝不读 `ledger_type` 当展示。
- `ledger_type` 只进计算/费率/视图分支逻辑，不出现在用户面。
- 两者来源不同、用途不同，禁止互相赋值或合并。

## 3. channel_category 分类法与 org_type 映射
| org_type（AMAC） | channel_category |
|---|---|
| 商业银行 / 全国性商业银行 / 农村商业银行 / 外资银行 | bank |
| 证券公司 / 证券投资咨询机构 | securities |
| 独立基金销售机构 / 基金销售支付结算机构 | fund_platform |
| 保险公司 | insurance |
| 期货公司 | futures |
| 基金公司 / 基金管理公司子公司 / 其他 | other |

映射表集中在代码单一函数（如 `map_org_type_to_channel_category`），便于维护。

## 4. 派生规则（系统维护，用户不碰）
- 有 `sales_institution_id`：查机构 `org_type` → 映射得 `channel_category`。
- 无机构（手动账本）：由创建时用户选的"分组"直接写入 `channel_category`；系统据分组映射 `ledger_type`（bank→bank, securities→stock, fund_platform→fund, insurance→property, futures→stock, other→bank）。
- 导入器：命中销售机构建账时，`ledger_type` 按资产类（基金销售机构→fund），`channel_category` 按 `org_type`（商业银行→bank）。微众银行即 `ledger_type=fund + channel_category=bank`，UI 一致显示"银行"。

## 5. 动态分组（前端）
- 账户列表只渲染**有数据的分组**；无账户的分组（如用户无保险/期货）不显示空分组，避免困惑。
- 分组顺序、组内排序沿用现有 localStorage / `display_order` 机制，键改为 `channel_category` 值。

## 6. 存量数据回归
- 有 `sales_institution_id`：按 §3 映射回填 `channel_category`。
- 无机构：按 `ledger_type` 回退（bank→bank, stock→securities, fund→fund_platform, property→other）。
- 冲突（`ledger_type` 与 `org_type` 不一致，如 fund 账本指向商业银行机构）：**以 `org_type` 为准** → bank。
- `e_account` 聚合账本：不进普通分组（已被 `is_aggregation` 隐藏），单独处理。

## 7. 代码注释规约
- `models.py` 的 `ledger_type` 与 `channel_category` 字段注释必须互相引用本文件，并写明"展示用读 channel_category，计算用读 ledger_type"。
- 导入器、建账视图、列表视图、分组逻辑的关键处加注释指向本文件 §2.3 铁律。

## 8. 后续（另开 issue）
- 聚合视图视觉优化（页面观感 + 聚合卡片与分类卡片区分度）。
- 场内证券（ETF/可转债）聚合卡片，与场外基金并列。

## 9. 与其他 issue 的边界（#1100）
- #1100 讨论的是**销售机构绑定的"每人/每家"基数**问题：一个销售机构下能否挂多个家庭成员的独立账户（如夫妻各自在支付宝开户）、以及重复账户创建时的拦截 UX。它属于"一个机构能建几个账本"的层。
- 本设计只解决**展示分组**：每个账本自身的 `channel_category` 从 `sales_institution_id → org_type` 推导，不触碰机构绑定基数规则。
- 两者正交：无论一个机构下挂 1 个还是 N 个账本，每个账本各自算出对应的 `channel_category`（如夫妻各自的支付宝账本都得到 `fund_platform`），本设计逻辑均成立。
- 若 #1100 后续落地"按人独立账户"，是导入器/建账策略的独立改动，不影响本设计的 `channel_category` 推导；届时本文件与导入器注释应同步更新，但映射与分组层不变。
