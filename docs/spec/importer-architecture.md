# 导入系统可扩展架构与社区贡献规范

> 本规范是导入系统相关所有 Issue 的「宪法」。后续任何解析器、持仓导入、去重、OCR 复用、银行产品录入的 Issue 与实现，都必须引用并遵循本文档，不得各自定义口径。

## 0. 背景与目标

当前导入系统已支持多家券商/平台（支付宝、天天基金、腾讯理财通、华泰、广发、方正等），交易级去重机制（`import_hash` + 唯一约束）已成熟落地。但面对以下诉求仍显不足：

1. **券商覆盖有限**：中国有名券商数十家，东方财富等仍缺失，且缺失的原因是「没有真实样本数据就无法写解析器」。前期不应由核心团队逐个攻破，应交给社区。
2. **持仓导入缺失**：当前 `positions` 表不支持导入，且完全没有去重 key，用户先手动录持仓、后又用交割单导入，会导致同一份持仓被写两次。
3. **银行投资产品**：低风险、对用户资产重要，但无统一代码体系、无公开 API，需纳入远期规划。
4. **社区化诉求**：券商模板差异极大、开发量巨大，必须由平台开发者共建，核心团队只做架构与审核。

核心设计原则：**灵活可靠、可扩展热插拔、不降低系统稳定性；先规范后实现、先出文档再拆 Issue。**

---

## 1. 现有架构事实（代码基准，非设想）

以下为已落地代码，任何新设计都必须与之兼容：

### 1.1 解析器基类契约

- 基类：`backend/app/services/importer/base.py` 的 `BaseImportParser`（抽象类）。
- 子类**必须实现**：
  - `parse(file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]`
  - `validate(records) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]`
- 子类**可选覆盖**：`source: str`（数据来源标识，用于注册表和哈希生成，默认 `'unknown'`）。
- 基类已提供通用能力：多编码读取（`_read_csv` / `_read_excel` / `_decode_bytes`）、哈希工具（`compute_import_hash` / `compute_batch_hash`）。

### 1.2 标准输出格式

- `StandardTransactionRecord`（`backend/app/services/importer/records.py`）：所有解析器统一输出。
- 关键字段：`confirm_date, asset_type, symbol, name, business_type, amount, account_name, shares, nav, fee, transaction_id, source, import_hash, batch_id, ...`

### 1.3 交易级去重（已落地）

- `compute_record_hash(source, record)`（`records.py:20`）：
  - 有平台流水号：`md5(f"{source}|{transaction_id}")`
  - 无流水号：`md5(f"{source}|{confirm_date}|{symbol}|{business_type}|{shares:.4f}|{nav:.4f}")`
  - **不含 amount**（不同平台金额四舍五入处理不同）。
- 落库：`transactions.import_hash`（长度 64），表上唯一约束 `uq_txn_import_hash`（`models.py:51`）。撞 key 即数据库层拒绝重复。
- 批次级：`compute_batch_hash()` 用于「同一文件重复上传」的文件级去重。
- **AI 识别导入（`source='ai_txn'`）复用同一函数**，去重口径已统一。

### 1.4 持仓表现状（核心缺口）

- `positions` 表（`backend/app/domains/positions/models.py`）：字段为 `symbol, name, market, type(asset_type), ledger_id, account_name, quantity, avg_price, currency, current_price, confirm_date, notes, allocation`。
- **去重与溯源已落地（#928）**：`import_hash`（内容哈希，`uq_positions_import_hash` 唯一约束）+ `source` / `source_import_id` / `source_broker` 溯源字段，`PositionService.upsert_from_holding` 以 `(ledger_id, symbol)` 为业务键、SET 语义整条替换（快照是某日点位绝对值，不累加）。
- 唯一约束：`uq_positions_ledger_symbol`（按 `ledger_id + symbol`），即同一账户下 symbol 唯一。
- **E账户持仓文件导入已落地（#1012 系列）**：`EAccountHoldingParser`（表头定位容错）+ 编排器持仓分支（`parse_and_preview_holdings` / `commit_holdings`）+ `POST /api/importers/holdings/{parse,confirm}` + `ledger_type='e_account'` 聚合账户 + `position_import_meta` 溯源表（基金管理人/份额类别/基金账户/交易账户/分红方式/销售机构/市值）。
- 结论：交易去重已治本，持仓去重已随 #928 补上；E账户文件导入已闭环，截图/OCR 持仓识别（#1018）与前端导入向导「持仓导入」模式（#1013）为待办。

### 1.5 OCR 域现状

- `backend/app/domains/ocr/` 仅有 `schemas.py` 与 `views.py`，提供底层识别通道（OCR + LLM 调用）。
- 自选导入已复用该通道实现简易识别。
- 持仓导入将**复用同一识别通道**，而非直接复用自选的解析结果结构（持仓快照结构 ≠ 自选产品列表，上层解析逻辑需新写）。

---

## 2. 解析器独立仓库与社区贡献规范（两阶段策略）

### 2.1 仓库形态

- 新建独立仓库 **`fundmate-importers`**（开源），承载社区贡献的解析器与匿名样本。
- 主仓通过**依赖引用 / 子模块**方式使用，而非把解析器直接堆在主仓 `backend/app/services/importer/` 内。
- **前期（阶段一）**：开发者通过 PR 合入 `fundmate-importers`，确保代码质量与测试覆盖，主仓跟随版本升级。
- **后期（阶段二）**：收紧随意 PR，改为「用户上传压缩包/目录 → 平台侧扫描解析 → 审核后合入」。前期即把解析器定义为**可 `pip install` 的独立包接口**，使阶段二平滑迁移，无需重构。

### 2.2 目录结构规范（`fundmate-importers`）

```
fundmate-importers/
├── pyproject.toml            # 可 pip install 的包，定义 entry_points / 版本
├── fundmate_importers/
│   ├── __init__.py           # 暴露 registry 加载入口
│   ├── registry.py           # 解析器注册表协议（见 §2.3）
│   ├── base.py               # 复用主仓 BaseImportParser 契约的镜像基类
│   ├── brokers/
│   │   ├── eastmoney.py      # 东方财富（待样本）
│   │   ├── guotai.py         # 国泰君安 ...
│   │   └── ...
│   └── schemas.py            # 标准输出格式（与主仓 StandardTransactionRecord 对齐）
├── samples/                  # 匿名化样本（见 §2.4）
│   ├── eastmoney/
│   │   ├── sample1.csv
│   │   └── README.md         # 样本来源说明与脱敏方式
│   └── ...
└── tests/                    # 每个解析器配套的断言测试
    ├── test_eastmoney.py
    └── ...
```

### 2.3 注册表协议

- 每个解析器模块声明 `source` 标识与 `can_parse(file_bytes) -> bool`（或基于文件特征/扩展名+关键字嗅探）。
- 主仓加载时遍历已安装包暴露的 entry_points（或 `registry.register(...)`），构建 `source -> parser` 映射。
- **发现机制**：解析器必须自描述「我能解析什么」（扩展名、平台特征行），主仓不硬编码券商清单，从而实现热插拔。

### 2.4 样本数据与脱敏规范

- 样本用于编写解析器的断言测试，确保解析正确。
- **强制脱敏**：金额模糊化、账号/姓名替换、日期偏移。
- 不经用户明确授权，不得使用真实数据。
- 配套最小断言测试（如「解析结果包含 N 条交易记录，首条 symbol == 'xxx'」）。

### 2.5 加载机制（主仓侧，阶段一即预留接口）

- 主仓导入流程先查内置解析器，再查外部包（`fundmate-importers` 提供的 entry_points）。
- 统一走 `BaseImportParser` 契约，内置与外部解析器对上层无感。
- 阶段二仅需把「外部包来源」从 entry_points 扩展到「用户上传目录扫描」，加载协议不变。

---

## 3. 持仓去重方案（治本）

### 3.1 设计原则

与交易去重保持**同一架构模式**：用内容哈希 + 数据库唯一约束，在数据库层拦截重复，不在应用层写复杂去重逻辑。这样用户不会因为「交易和持仓口径不同」而困惑，也为后续多源归集（upsert）打基础。

### 3.2 新增字段（`positions` 表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `import_hash` | String(64), nullable | 持仓内容哈希，用于去重与幂等 |
| `source` | String(30), default `'manual'` | 数据来源：`manual` / `broker_xxx` / `ai_holding` 等 |
| `source_import_id` | String(36), nullable | 本次导入批次 ID（溯源展示、归集用） |
| `source_broker` | String(50), nullable | 来源券商/平台（展示用） |

**角色区分**：`import_hash` 负责「去重」（撞 key 即合并/跳过）；`source` / `source_import_id` / `source_broker` 负责「溯源」（展示这条持仓来自哪次导入、哪个券商）。两者并列，不能互相替代——`source_import_id` 只能防「整批重复导入」，防不了「手动录 + 交割单导入来自不同批次」的重复，唯有内容哈希能治本。

### 3.3 持仓哈希字段选择

```python
hash_fields = [
    source,                              # 数据来源（券商/手动/AI识别）
    account_id,                          # 用户账户标识（ledger_id）
    symbol,                              # 产品代码
    snapshot_date or date(created_at),   # 持仓快照日期；缺失时降级为 created_at 的日期部分
]
position_import_hash = md5("|".join(hash_fields))
```

降级规则保证「同一天、同一产品、同一来源」的持仓不会重复，即便手动录入未提供 `snapshot_date`。

### 3.4 唯一约束

- 新增 `UniqueConstraint('import_hash', name='uq_positions_import_hash')`。
- 与现有 `uq_positions_ledger_symbol` 并存：前者防跨源重复写入，后者保业务唯一性。
- 撞 key 时采用 upsert 语义（更新 quantity/avg_price 等，保留 `source` 溯源），而非简单拒绝。

---

## 4. 持仓导入功能（含截图/OCR 复用）

### 4.1 定位

- 持仓是「结果」，交割单是「过程」。两者都支持，但交割单价值更大（可做情绪/五维/雷达分析）。
- 仅持仓导入的用户（隐私顾虑等）也应被支持，但只能得到静态分布，不做行为分析。

### 4.2 录入路径

1. **手动表单**：结构化录入 symbol / 数量 / 成本价 / 账户 / 来源。
2. **平台文件导入（已落地，E账户）**：`EAccountHoldingParser` 解析券商导出的持仓 Excel（表头定位容错，兼容带/不带个人信息两种上传形态），预览确认后经 `PositionService.upsert_from_holding` 落库，**不产生交易流水**；首次导入自动创建 `ledger_type='e_account'` 聚合账户，溯源元数据写 `position_import_meta`。前端导入向导「持仓导入」模式为待办（#1013）。
3. **截图导入（复用 OCR 通道，待办 #1018）**：复用 `domains/ocr/` 的识别通道（OCR + LLM），上层新写「持仓快照解析」逻辑，将识别出的产品名 + 金额/份额映射为标准持仓结构，再走 §3 去重。**必须走 `upsert_from_holding` 持仓汇点，严禁误建交易流水**（隐患登记 #1018）。
4. **交割单导入自动推导**：现有 `positions` 由交易记录推导的逻辑不变，导入后同样补 `import_hash`，使「先交割单、后手动录」不重复。

### 4.3 去重协同

- 各路径最终都生成 `positions.import_hash`，统一由唯一约束拦截重复。
- 用户先手动录、后交割单导入，或反之，均不会写两份。

---

## 5. 银行投资产品导入（远期规划）

### 5.1 数据源事实

- 官方平台：中国理财网（银行业理财登记托管中心）为全国统一信息披露平台，但**无面向个人/第三方的公开 API**，直联接口仅对金融机构开放。
- 市面查询工具均为爬虫实现，稳定性与合规性无法保证。
- 银行理财**无统一代码体系**（不同于股票/基金 6 位代码），靠「登记编码 + 产品名称」标识，命名规则差异极大，不同平台同名产品可能完全不同。
- 截至 2026-06，全市场存续约 5.12 万只，涉及 153 家银行 + 32 家理财公司，动态变化。

### 5.2 MVP 阶段（P2）

- 采用「手动录入 + 可选元数据」模式：用户录入产品名称与金额，元数据（风险等级、产品类型）为可选填空，**不依赖中心数据源**。
- **决策结论（基于 `data-model.md` §5.12 现状）**：银行理财**留在 `bank` 账户资产记录，不进标准 `positions`**。现有「买入理财」操作已记录三个产品维度字段——`asset_name`（产品名称，如"朝朝宝"）、`asset_type`（6 选 1 标签：活期存款/货币基金/定期理财/债券基金/股票基金/混合资产，可自定义）、`amount`（金额），具备基本产品元数据。因此**不需要扩展 `positions.asset_type` 来承接理财类型**。
- P2 真正的工作量：仅为 `bank` 账户资产记录补**可选的理财专属元数据字段**（期限、业绩比较基准/收益率、风险等级、登记编码），可落在 `bank` 资产记录结构或 `extra` JSON 中，与标准 `positions` 持仓体系解耦。工作量级从「扩展 positions 枚举」降级为「bank 资产补可选字段」。

### 5.3 远期

- 如需产品搜索/匹配，可爬取中国理财网公开数据作为**离线只读参考库**（定期更新），仅用于产品名称自动补全/搜索，不用于实时估值。不属于 MVP。

---

## 6. 关联问题：transactions 明文 source 列

- 现状：`transactions` 表无独立 `source` 列，券商溯源信息仅存在于 `import_hash` 的前缀（`source|...`），无法便捷按平台分组统计盈亏（roadmap P2-14 需求）。
- **决策结论**：**P0 阶段不新增 `source` 列**。按券商分组统计盈亏可通过**反解 `import_hash` 前缀**实现——分组统计查询不频繁，性能足够，无需为低频查询新增列与索引。
- 远期：若分组统计演变为高频查询，再考虑新增 `source_broker` 冗余列并建索引，届时做一次全量回填即可（从 `import_hash` 前缀批量解析写入）。
- 相关 Issue 须与 P2-14 关联，但**不阻塞** P0 去重与持仓导入工作。

---

## 7. Issue 拆分索引（详见 GitHub Project #3）

所有 Issue 描述开头须加：`> 本 Issue 遵循 docs/spec/importer-architecture.md 规范`

| # | 标题 | 象限 | 关联规范章节 |
|---|------|------|--------------|
| 1 | 解析器独立仓库建立 + 注册表协议 | 架构（Q2 重要不紧急） | §2 |
| 2 | 主仓加载外部解析器的机制实现 | 架构 | §2.3 / §2.5 |
| 3 | 持仓表增加 import_hash + 唯一约束 + 溯源字段 | 数据模型（Q1 重要紧急） | §3 |
| 4 | 持仓导入功能（含截图/OCR 复用） | 功能 | §4 |
| 5 | 东方财富等缺失券商的样本征集机制 | 社区 | §2.2 / §2.4 |
| 6 | 银行产品远期录入方案设计 | 远期/调研 | §5 |

各 Issue 通过 `relates to` 互相关联，不与其它大 Issue 堆叠，降低后期维护成本。

---

## 8. 落地节奏

1. 先定稿本规范（当前文档）。
2. 建 §7 的 6 个关联 Issue，挂 Project 象限字段。
3. **不动任何业务代码**，等各 Issue 进入实现阶段再编码。
