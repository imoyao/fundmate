# 销售机构「常用分组」与账户类型感知设计（2026-08-24）

> 关联：#1081（常用分组 + 常用名）、#1082（账户类型区分与机构筛选）
> 分支：`feat/sales-institution-common-group`（自 dev 切出，PR 合回 dev）
> 状态：设计已与用户对齐，本文档为实施依据

## 1. 背景与目标

- 创建账户时销售机构下拉为 394 项平铺列表（AMAC 名录同步），按 `org_name` 字典序排序，用户找不到熟悉的平台（#1081）。
- 账户类型不区分销售机构类别：证券账户混入基金销售机构、基金账户混入券商（#1082）。
- 目标：常用机构置顶分组 + 常用名 + 类型标识 + 按账户类型过滤机构。

## 2. 决策记录（2026-08-24 与用户对齐）

| # | 决策 | 理由 |
|---|---|---|
| D1 | 蚂蚁常用名 = **支付宝**（非蚂蚁基金） | 普通用户心智入口是支付宝 App；维持既有 BUILTIN_ALIASES |
| D2 | fund 账户机构列表**包含券商** | 券商确实代销场外基金（中信证券规模排名 #8）；靠常用置顶 + 类型标识解决「看不清楚」 |
| D3 | stock 账户机构列表**仅券商** | 股票交易只发生在券商 |
| D4 | 常用名单 = 中基协保有规模 Top10 + 5 大互联网平台 = **15 家**；`common_sort` 直接用排名数字 | 客观可辩护，免拍脑袋；名单成员极稳定 |
| D5 | 排序定位为**实现细节**（稳定顺序），非产品功能；用户无排名感 | 用户常用仅 2~3 家，排序无感知价值，但需防字典序反直觉 |
| D6 | 策展数据**代码声明、job 幂等应用**，禁止手工改库 | 迁移零负担：任何环境跑 AMAC job 即收敛（名录本体本就由 job 重建） |
| D7 | 类型标识复用 `org_type`（11 类 → 4 组展示映射），零新增字段 | 数据已在库；同时服务 #1081 徽标与 #1082 筛选 |
| D8 | 银行渠道记账提示：fund 账户选中银行类机构时展示轻提示 | 缓解 #1082 心智问题，一行文案成本 |

## 3. 数据模型变更（`backend/app/domains/positions/models.py` SalesInstitution）

```python
is_common = Column(Boolean, nullable=False, default=False, server_default='0', comment='常用机构标志（代码策展，勿手工维护）')
common_sort = Column(Integer, nullable=True, comment='常用组内排序（小者在前），取中基协保有规模排名；非常用为 NULL')
```

- **域归属核实**：`sales_institutions` 已在 `db_factory.DATA_DOMAIN_REGISTRY` 登记为 user 域（:85，含边界先例注释）。注意：AGENTS.md 规则 1 所述「模型声明 `__data_domain__` 类属性」与实际实现不符——真实机制是中央注册表（表名 → 域），全仓库无任何模型使用该属性；文档漂移已登记，不在本 feature 内改 AGENTS.md。
- Schema 演进：项目无迁移框架（先例：`display_name` 随建表落地；`_validate_schema` 会在启动时拦截模型与库结构漂移）。新增列按 `scripts/migrate_family_id.py` 先例提供幂等 ALTER 脚本 `scripts/migrate_sales_institution_common.py`，存量库执行一次即可通过启动校验。

## 4. CURATED_INSTITUTIONS（15 家，代码声明 SSOT）

落点：`amac_institution_job.py`，替代/扩展现有 `BUILTIN_ALIASES`。结构：精确 `org_name` → `(display_name|None, common_sort)`。**sort 值 = 中基协保有规模排名（保真来源，允许跳号）**。

| org_name（与库内精确一致） | display_name | common_sort |
|---|---|---|
| 蚂蚁（杭州）基金销售有限公司 | 支付宝 | 1 |
| 招商银行 | — | 2 |
| 上海天天基金销售有限公司 | 天天基金 | 3 |
| 中国工商银行 | — | 4 |
| 中国建设银行 | — | 5 |
| 中国银行 | — | 6 |
| 交通银行 | — | 7 |
| 中信证券 | — | 8 |
| 中国人寿保险股份有限公司 | 中国人寿 | 9 |
| 中国农业银行 | — | 10 |
| 腾安基金销售（深圳）有限公司 | 理财通 | 13 |
| 珠海盈米基金销售有限公司 | 且慢 | 26 |
| 京东肯特瑞基金销售有限公司 | 京东金融 | 32 |
| 浙江同花顺基金销售有限公司 | 同花顺 | 33 |
| 北京雪球基金销售有限公司 | 雪球基金 | 36 |

应用语义：job upsert 时对命中行**覆写** `is_common/common_sort/display_name`（代码即 source of truth，保证各环境收敛）；未命中行维持原值。注意现有 `BUILTIN_ALIASES` 的支付宝/天天基金两条并入本表，避免双源。

## 5. API 契约（`GET /api/ledgers/sales-institutions/`）

- 新增查询参数：`org_types`（可选，逗号分隔原始 `org_type` 值，如 `证券公司,独立基金销售机构`）；提供时仅返回命中类型。
- 返回项字段扩充：`{id, org_name, display_name, org_type, is_common, common_sort}`。
- 默认排序：`is_common DESC → common_sort ASC（NULL 最后）→ org_name ASC`。
- 前端按 `is_common` 拆「常用机构 / 全部机构」两个 option-group。

## 6. 前端设计（`AccountFormFields.vue` 及入口）

### 6.1 类型组映射（前端常量，11 → 4）

| 原始 org_type | 展示标签 |
|---|---|
| 独立基金销售机构 | 独立 |
| 全国性商业银行 / 城市商业银行 / 农村商业银行 / 在华外资法人银行 | 银行 |
| 证券公司 / 证券投资咨询机构 | 券商 |
| 保险公司 / 保险代理公司和保险经纪公司 | 保险 |
| 期货公司 / 公募基金管理公司销售子公司 | 其他 |

### 6.2 账户类型 → 可见机构类型（#1082 D2/D3）

| ledger_type | org_types 范围 |
|---|---|
| stock（证券账户） | `证券公司` |
| fund（基金账户） | 除 `期货公司` 外全部（独立/银行×4/券商/投咨/保险×2/基金公司销售子公司） |
| 其他类型 | 维持现状（实现时核实选择器显隐逻辑，不回归） |

入口预填：按「新增基金平台 / 新增证券账户」入口预置 `ledger_type`（#1082 第 1 问）。

### 6.3 交互

- 下拉分两组：`常用机构`（is_common，按 common_sort）置顶 + `全部机构`（其余，字典序）；filterable 过滤作用于两组。
- 选项渲染：主文本 = `display_name || org_name`；别名存在时全称作次级文本；右侧小标签 = 类型组（独立/银行/券商/保险/其他）。
- 银行提示（D8）：fund 账户选中银行类机构时，表单内展示轻提示：「银行渠道购买的基金记录在此；银行卡本身资产请使用银行账户管理」。

## 7. 迁移考量（D6 展开）

- 名录本体：AMAC job 全量重建，生产首部署跑一次即得 394 条。
- 策展数据：随代码走，job 幂等应用，任何环境（本地 SQLite / Supabase / Neon 重建）收敛一致。
- 远期（不在本期）：「本家庭已使用机构自动置顶」（信号优于静态排名，数据基础 ledgers.sales_institution_id 现成）；用户个人标星（带 user_id，属用户数据需迁移策略）。

## 8. 验证标准

- 后端：pytest 单进程全量通过；新增用例覆盖策展应用（upsert 幂等/覆写语义）、API 新字段/排序/org_types 过滤、`__data_domain__` 断言。
- 前端：`pnpm typecheck` 零错误、`pnpm lint` 通过。
- 手工冒烟：创建账户弹窗常用组置顶且 15 家齐全、类型标签正确、stock/fund 过滤生效。
