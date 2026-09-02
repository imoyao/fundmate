# 账本（Ledger）数据模型权威说明

> **唯一权威文档**：本文件是账本（Ledger）数据模型的唯一权威说明，涵盖账户结构、渠道分类、外部资金账户、品类正交与虚拟聚合视图。代码注释、其它设计文档、issue 描述均须反向引用本文件，不得另立"账本模型"口径。
> 演进：本文件由 `ledger-channel-category-redesign-2026-08-28.md`（原仅覆盖渠道分类重设计）扩展为完整账本数据模型。文件名保留以不破坏既有引用。
> 关联 issue：#1100（销售机构唯一账户制）、#1101（账户×品类正交 / 基金汇总虚拟视图）、#1089（存量重复账本合并）。

---

## 0. 一句话模型

- **两层正交**：`ledger_type`（内部资产类键，计算用，用户不可见） ⊥ `channel_category`（用户可见分组，展示用）。两者禁止互相赋值。
- **三层结构**：`SalesInstitution`（机构法人） → `ExternalAccount`/`external_account_code`（外部资金账户/凭证） → `ChannelLedger`（账本，物理容器）。账本归属机构，资金账户决定物理隔离。
- **品类在持仓层**：一个账本可同时持有多种 `asset_type`（股票/基金/货基…），`asset_type` 是持仓属性，不是账本属性。基金汇总 = 按 `asset_type` 跨账本的**只读虚拟聚合视图**。

---

## 1. 三层概念模型

| 层 | 实体 | 含义 | 代码落点 |
|---|---|---|---|
| 机构法人 | `SalesInstitution`（AMAC 名录） | 微众银行、银河证券这类**法律实体** | `sales_institutions` 表；`Ledger.sales_institution_id` FK |
| 外部资金账户 / 凭证 | `ExternalAccount` | 你在机构下的**资金账户/登录凭证**：招行 I 类/II 类卡号、银河普通资金账号/两融资金账号、同花顺登录的银河账户 | `Ledger.external_account_code`（String 标识，非独立表） |
| 渠道账本 | `ChannelLedger` | 记录该资金账户下金融资产的**物理容器**（份额/持仓） | `ledgers` 表的一行 |

### 券商"子账户"的真相（关键，避免误建模）
券商支持的多账户分两类，处理完全不同：
- **物理隔离型（必须拆成不同账本）**：普通账户 vs 融资融券（信用）账户。资金与持仓法律隔离、负债不同，混在一起会导致 P&L/风险/强平口径全错。→ 用不同的 `external_account_code` 表达。
- **逻辑分仓型（不建物理账本）**：同一普通账户内按策略分仓（50% 价值股 / 50% 成长股）。→ 走持仓层标签（`Portfolio` / `StrategyTag`，见 `docs/spec/data-model.md` §5.11），不是账本层概念。

---

## 2. Ledger 字段权威规范

> 规则：每个字段必须同时说明「目的 / 行为 / 参考值」。下列为**当前模型真实字段**（以 `app/domains/ledgers/models.py` 为准）。本文件不引入任何冗余字段。

### 2.1 `name` —— 账户展示名
- 目的：用户在账户列表看到的名字（如"华泰证券""微众银行"）。
- 行为：自由文本；权威机构名不进此字段（机构展示名取自 `SalesInstitution.display_name`）。
- 参考值：`"华泰证券"` / `"微众银行"` / `"银河证券"`。

### 2.2 `ledger_type` —— 内部资产类键（用户不可见，计算/费率用）
- 目的：标识该账本持有的**资产品种本质**，驱动计算、费率结构、视图分支逻辑。
- 行为：**只进计算/费率/视图分支，绝不出现在用户面、绝不当展示标签**；编辑带数据账户时不可变（改类型返回 409）；由系统据 `channel_category` 或机构 `org_type` 派生。
- 参考值（枚举，不再增减）：`stock`(股票账户) / `fund`(基金账户) / `bank`(现金账户) / `property`(实物资产) / `e_account`(基金E账户汇总，导入自动建) / `family`(家庭账户)。
- ⚠️ 易错点：某类收益的展示门控是持仓/流水的 `asset_type`（如 `money_fund`），**不是本字段**。谁的账户持有货基就显示货基收益，与账本被标成 `fund`/`bank` 无关。

### 2.3 `channel_category` —— 用户可见渠道分组（展示用，系统维护）
- 目的：用户感知的"钱放在哪类机构"，同时作为账户列表分组与账户类型标签。
- 行为：分组/标签/排序/筛选**只读本字段，绝不读 `ledger_type`**；由系统从 `sales_institution_id → org_type` 映射写入；手动账本由用户所选"分组"推导写入；用户从不直接编辑。
- 参考值（枚举）：`bank`(银行) / `securities`(证券·券商) / `fund_platform`(基金平台·第三方独立销售) / `insurance`(保险) / `futures`(期货) / `other`(其他)。
- 映射表见 §4。

### 2.4 `sales_institution_id` —— 关联销售机构（AMAC 权威名录）
- 目的：把账本锚定到真实机构法人，解决"支付宝 vs 蚂蚁（杭州）基金销售有限公司"同名多账本问题。
- 行为：FK → `sales_institutions.id`，`ON DELETE SET NULL`；可选（历史兼容）；命中后驱动 `channel_category` 派生。`NULL` 表示无机构手动账本（如家庭房产）。
- 参考值：AMAC 机构 id（如微众银行、银河证券）；`NULL` 表示未绑定。

### 2.5 `external_account_code` —— 外部资金账户/凭证标识（物理隔离维度）
- 目的：表达"同一机构下的不同资金账户"（普通 vs 两融、I 类 vs II 类），实现**物理隔离**而不破坏"一机构一账本"默认。
- 行为：
  - `String(50)`，**NOT NULL，默认哨兵 `'MAIN'`**（无显式账号时的主账户）。
  - 建账/导入时：若导入数据含资金账号（`PositionImportMeta.fund_account` / `trade_account`，E 账户数据已抽取），传导到本字段；否则取默认 `'MAIN'`。
  - **唯一键组成维度**（见 §6）：`(family_id, sales_institution_id, external_account_code)`。
  - 与 `frontend_app` 正交：本字段是"哪个资金账户"，`frontend_app` 是"用哪个软件登录"，互不影响。
- 参考值：券商交易账号（如 `"A123456"`）、基金账号、银行卡尾号（若用户提供）；默认 `"MAIN"`。普通/两融用不同 code 区分（如 `"NORMAL"` / `"MARGIN"` 或真实账号）。
- ⚠️ **不引入 `account_subtype`（normal/margin/options）独立列**：物理隔离已由 `external_account_code` 的不同取值天然表达，再加枚举列属于冗余。若前端需"类型筛选"，从 `external_account_code`（或后续小映射表）派生，不在 Ledger 加冗余字段。

### 2.6 `frontend_app` —— 交易前端标签（展示用，纯标签）
- 目的：记录用户通过哪个前端软件查看/操作该账户（同花顺 / 东方财富 / 券商 APP）。
- 行为：**仅展示，不参与任何资产计算或业务逻辑**；不影响分组、隔离、聚合。
- 参考值：`tonghuashun` / `eastmoney` / `self`(券商自有 APP) / `other`；`NULL` 等同 `self`。

### 2.7 `is_aggregation` —— 聚合/系统账本标记
- 目的：标识系统级聚合账本（如基金E账户），从用户账户列表默认隐藏。
- 行为：`Boolean`，默认 `False`；`True` 时列表查询过滤（前向兼容未来聚合账本）。
- 参考值：`True` 仅基金E账户等系统聚合账本。

### 2.8 `is_active` —— 归档状态
- 目的：活跃/归档。归档保留全部数据仅从日常视图默认隐藏。
- 行为：`Boolean`，默认 `True`；有交易/持仓/资产的账户禁止删除，只能归档。
- 参考值：`True`(活跃) / `False`(已归档)。

### 2.9 其余保留字段（均有明确用途，非冗余）
- `default_allocation`：默认五笔钱配置目标（`liquid/stable/longterm/speculative/security`）。
- `fee_config`：费率 JSON（`stock` 记佣金/印花税等；`fund` 记申购费折扣）。
- `display_order`：组内手动排序序号（NULL 回退按持仓金额降序，#1083）。
- `portfolio_id`：默认组合（D20：新建持仓未显式指派时继承；非组合成员判定依据）。
- `linked_cash_ledger_id`：关联现金账户（仅 stock/fund）。
- `linked_money_fund_id` + `auto_purchase_money_fund`：类现金产品绑定（余额宝）与回款自动申购（#1137）。
- `notes`：备注。

---

## 3. 双字段正交铁律（维护者必读）
- 分组、类型标签、排序、筛选：**只读 `channel_category`**，绝不读 `ledger_type` 当展示。
- `ledger_type` 只进计算/费率/视图分支逻辑，不出现在用户面。
- 两者来源不同、用途不同，禁止互相赋值或合并。

---

## 4. `org_type` → `channel_category` 映射表（权威，集中维护）
| org_type（AMAC） | channel_category |
|---|---|
| 商业银行 / 全国性商业银行 / 农村商业银行 / 外资银行 | bank |
| 证券公司 / 证券投资咨询机构 | securities |
| 独立基金销售机构 / 基金销售支付结算机构 | fund_platform |
| 保险公司 | insurance |
| 期货公司 | futures |
| 基金公司 / 基金管理公司子公司 / 其他 | other |

集中函数：`app/domains/ledgers/constants.py :: map_org_type_to_channel_category`。**禁止在别处硬编码映射。**

---

## 5. 派生规则（系统维护，用户不碰）
- 有 `sales_institution_id`：查机构 `org_type` → `channel_category`（§4）；`external_account_code` 默认 `'MAIN'`（导入有账号则取真实值）。
- 无机构（手动账本）：建账时用户所选"分组" → `channel_category`；据分组映射 `ledger_type`（bank→bank, securities→stock, fund_platform→fund, insurance→property, futures→stock, other→bank）；`external_account_code` 默认 `'MAIN'`。
- 导入器：命中销售机构建账时，`ledger_type` 按资产类（基金销售机构→fund），`channel_category` 按 `org_type`（商业银行→bank）。**例：微众银行 = `ledger_type=fund + channel_category=bank`，UI 归"银行"。**

---

## 6. 唯一键与约束
- **应用层查/建键**（`_get_or_create_channel_ledger` 等）：`(family_id, sales_institution_id, external_account_code)`。
  - 简单用户（无账号数据）→ `external_account_code='MAIN'` → 每机构仍只有**一个**账本（满足 #1100 默认值）。
  - 有两融/多账号 → 不同 `external_account_code` → 自动多账本（物理隔离）。
- **DB 部分唯一索引**（#1100 计划，演进）：`UNIQUE(family_id, sales_institution_id, external_account_code) WHERE sales_institution_id IS NOT NULL`。无机构手动账本不受约束。
- 注意：键中**不含 `ledger_type`**——单账本可持有混合 `asset_type`，`ledger_type` 仅是主资产类派生属性。

---

## 7. 虚拟聚合视图（基金汇总）
- 基金全景 = 按 `asset_type`（如 `fund`/`money_fund`）**跨账本只读聚合**，不产生物理账本（不产生多余账号、不分叉数据）。
- `external_account_code` 已在列：默认跨机构汇总"总额"；若未来需"某资金账户买的基金 vs 另一资金账户"，可下钻本列，**两种口径都支持，无需现在决定**。
- 与 D20 组合体系（持仓级组合归属）层级不同、不冲突；聚合层避免重复建设。

---

## 8. 关键决策记录（与用户对齐，2026-09-02）
1. **沪A/深A/京A 不建模为子账本**：属交易席位（market 差异），由持仓 `market`(CN_A/CN_B/CN_N) 处理，建子账本仅增复杂度无收益。
2. **银行 I 类/II 类不在模型拆分**：我们抓取的是 `fund_account`/`trade_account`（基金/交易账号），非银行卡号；拆分无数据支撑且非必要。
3. **普通 vs 两融必须物理拆分**：允许同券商绑两个账户（普通+信用是常态），用不同 `external_account_code` 隔离（E 账户 `trade_account` 已能区分）。
4. **基金全景默认跨机构汇总**，支持按 `external_account_code` 下钻（§7）。
5. **不引入 `account_subtype` 冗余列**；物理隔离由 `external_account_code` 表达（§2.5）。
6. **`frontend_app`（同花顺）保持正交**，独立于 `external_account_code`（§2.6）。

---

## 9. 数据库设计原则（必要字段，无冗余/歧义）
- 保留 §2 全部字段，均具单一明确职责，无冗余。
- **明确不新增**：`account_subtype`（被 `external_account_code` 覆盖）。
- 任何新增字段须满足：单一职责、可被参考值枚举或明确来源、不与其他字段语义重叠；否则应并入既有字段或落到持仓/元数据结构，而非 Ledger。

---

## 10. 与存量/迁移的关系
- #1100：销售机构唯一账户制——部分唯一索引按 §6；手动账本绑定机构引导/拦截"同机构已存在账本"。
- #1089：存量重复账本合并工具（见 `docs/design/ledger-merge-design.md`），合并且归一后防回归。
- 迁移脚本：存量 `ledger` 回填 `external_account_code='MAIN'`（无机构或原无账号者）；`channel_category` 按 §5 从 `org_type` 或 `ledger_type` 回退（冲突以 `org_type` 为准）。

---

## 11. 代码注释规约
- `models.py` 的 `ledger_type` 与 `channel_category` 字段注释必须互相引用本文件，写明"展示用读 channel_category，计算用读 ledger_type"。
- 导入器、建账视图、列表视图、分组逻辑关键处加注释指向本文件 §3 铁律。
- `external_account_code` 注释须指向 §2.5 与 §6（唯一键维度）。

---

## 12. 文档演进 / 替代关系
- **取代**（机构维度部分）：`account-channel-and-fee-design-2026-08-16.md` 设想的"`institution_id` 指向用户自建小表"已被实际落地的 `sales_institutions`(AMAC) + `Ledger.sales_institution_id` 取代；该文件已改为指针。
- **关联（特性文档，非数据模型，保留并指向本文件）**：
  - `docs/design/ledger-merge-design.md`（#1089 合并机制）
  - `e-account-aggregation-design-2026-08-28.md`（E 账户聚合 / `is_aggregation`）
  - `securities-aggregation-design-2026-08-29.md`（场内证券聚合卡片）
  - `eastmoney-datasource-and-account-linkage-design-2026-08-30.md`（`fund_account` vs `source_broker` 正交，佐证 §2.5 来源）
  - `sales-institution-common-group-2026-08-24.md`（常用机构策展）
  - `ledger-cash-like-product-binding-2026-08-29.md`（类现金绑定）
  - `docs/spec/data-model.md` §5.12 账户类型已对齐本文件（详见该文件引用）
- 任何文档/issue 与本文冲突，以本文为准。
