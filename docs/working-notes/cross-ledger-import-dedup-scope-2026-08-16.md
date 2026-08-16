# 跨账本重导与去重作用域降级设计（2026-08-16）

## 背景与问题陈述

导入向导第三步预览页当前对「同一份交割单重复导入」在两层同时卡死，即使切换账本（LEDGER）也无法重导：

1. 去重哈希本身不含 `ledger_id`——`compute_record_hash`（`records.py:20`）与平台解析器的 `compute_import_hash` 只按 `source + 流水号` 或 `source + 日期 + 代码 + 类型 + 份额 + 净值` 生成 md5，与账本无关。同一份交割单导进任意 LEDGER，算出的 `import_hash` 完全一致。
2. 去重查询按 `family_id` 作用域，不看 `ledger_id`——预览阶段 `orchestrator.py:178` 查 `import_hash.in_(...) AND family_id == self.family_id`；入库 `commit()` 在 `orchestrator.py:503-507` 也是 `filter_by(import_hash=..., family_id=...)`。family 是净资产边界，LEDGER 只是 family 内子账户，换 LEDGER 完全绕不过去。
3. 数据库层硬闸——`transactions` 表 `UniqueConstraint('import_hash', name='uq_txn_import_hash')`（`models.py:51`）单列全局唯一，插入即约束冲突被拒。

后果：用户无法把旧账户（如「同花顺1号」）的交割单重新导入新账户（「同花顺2号」）做数据清洗/账本重建。一个不能让用户重建自己历史的记账工具是残废的，这是产品死结。

## 业务决策

**同意将去重作用域从 family 级降级到 ledger 级**，以解决跨账户重导死结；但「防净资产翻倍」不能只靠把责任推给用户，必须先补齐真正的安全出口，再配套 UI 软提示。

降级后的语义：同一份交割单导进**同一** LEDGER → 仍判定重复并跳过（幂等防重，正确）；导进**另一** LEDGER → 不再算重复，允许入库（迁移/清洗可行）。哈希内容不必改，仅把去重键变成 `(ledger_id, import_hash)`。

## 落地顺序（不可跳过前置依赖）

### 第 1 步：账本软退役（前置，必须最先做）

当前 `Ledger` 模型（`ledgers/models.py`）无 `is_active` / `retired` / `status` 任何字段；`summary_service.py` 汇总时 `db.query(Ledger).filter(Ledger.family_id == family_id)` 一把全取，无状态过滤；且 `transactions.ledger_id` 外键 `ondelete='RESTRICT'`，有交易的账本删不掉。

若先上线「请去废弃旧账户」警告却不建退役能力，用户会看到一条无法安全执行的动作（要么删交易被外键拦，要么无路可走）。所以软退役是横幅安全出口的前提：

- `Ledger` 模型加 `is_active` 字段（默认 true）。
- `summary_service` 汇总排除 `is_active == false` 的账本（净资产/总资产不再计入）。
- 账户管理页提供「归档此账户」幽灵按钮——字眼温和为「归档 / 退休」，绝不叫「删除」，让用户清楚这不是删数据而是「让它退休」，列表里仍可见（或用折叠区展开查历史）。

### 第 2 步：去重约束降级

- 唯一约束从 `uq_txn_import_hash(import_hash)` 改为复合 `uq_txn_import_hash(ledger_id, import_hash)`（硬前提，否则约束仍拦跨账本导入）。需 DB 迁移脚本，范式参考 `backend/scripts/migrate_positions_import_hash.py`。
- 预览去重 `orchestrator.py:178`、入库去重 `orchestrator.py:505` 的查询补 `ledger_id == ...`。
- 哈希内容不变，去重键变 `(ledger_id, import_hash)`。

### 第 3 步：family 级「幽灵扫描」驱动软提示

降级到 ledger 级后，导进**全新** LEDGER 时这些行在目标账本不重复，预览里打不了标——横幅「与同花顺1号重复」无从弹起。需保留一套**独立的 family 级只读扫描**：硬拦截用 ledger 级（同账本→跳过，保幂等），软提示用 family 级（任何别的账本占了该 hash → 弹横幅并指明来源账本）。两套机制拆开，逻辑才干净。横幅主 CTA 指向「归档旧账户」，次级才是诚实标注的「重新导入本账户」。

### 第 4 步：现金 / 货基跨账本迁移兼容

`orchestrator.py` 把现金类、货基类流水在入库时强制改为 `bank` 账本（`linked_cash_ledger_id` 那套）。同一份含现金/货基的交割单导进两个账本，会撞在 `(bank, import_hash)` 上静默失败迁移不了。处理：跨账户重导涉及现金流水时，前端必须让用户选新的现金关联目标（或提示现金行将失效需手动补录），不要把路堵死。

### 第 5 步：NULL 哈希回填迁移脚本（真正的雷点）

现有 `UniqueConstraint('import_hash')` 已是单列全局唯一，它已保证没有任何两条非空 hash 重复；复合键 `(ledger_id, import_hash)` 是其子集，必然也唯一，SQLite 对 NULL 当不同值处理，所以**加约束不会因历史数据失败**。真正的雷点是老数据里 `import_hash` 为 **NULL** 的行——新方案下同一账本内两条 NULL hash 行会变成「检测不出的重复」。故迁移脚本要做的是**回填**（对历史 NULL 行按内容重算哈希写入），而非去重。不要写「先找冲突再删/改随机 hash 避让」的规避脚本，当前约束下用不上。

## UI 交互设计要点

- 软退役字眼温和，叫「归档此账户 / 让它退休」，不叫删除。
- 警示横幅（非阻断、浅色 `--color-warning` 背景）：family 级幽灵扫描触发，指名来源账本（如「检测到与账户『同花顺1号』重复的交割单记录」），并提示「若想迁移旧数据，请先归档旧账户、确认其不再参与资产统计，否则总资产与盈亏翻倍计算」。下方两出口：`[ 去归档旧账户 ]`（跳账户管理页）+ `[ 重新导入本账户 / 覆盖 ]`（仅同账本场景，诚实命名）。
- 「强制导入」语义澄清：跨账本迁移（目标账本是新的）本就干净入库，**不需要任何强制按钮**；「强制导入 / 重新导入」只对**同账本重复导入**有意义，触发时后端走「事务内先软删旧数据、再插入新数据」（原子包裹），防止同账户「旧 + 新」翻倍。
- 跨账本重导涉现金流水：前端弹选新现金关联目标，不静默失败。

## 验收 / 回归测试要点

- 同账本幂等：重导同一交割单 → 全部跳过，计数不变。
- 跨账本可重导：旧账本已导的交割单导进新账本 → 成功入库，不冲突。
- 翻倍防护：跨账本重导后，若不归档旧账户，净资产确实翻倍（责任在用户 + 横幅已提示）；归档旧账户后汇总排除。
- NULL 回填迁移脚本跑通后，历史 NULL 行均有 hash，且同账本内不出现「检测不出的重复」。
- 同账本「重新导入 / 覆盖」在事务内完成，不残留旧 + 新重复。

## 引用

- 代码证据：`backend/app/services/importer/orchestrator.py`、`backend/app/services/importer/records.py`、`backend/app/domains/transactions/models.py`、`backend/app/domains/ledgers/models.py`、`backend/app/services/summary_service.py`
- 关联评估：`unified-import-entry-evaluation-2026-08-16.md`（统一导入入口，与本次去重降级需协调）
- 统筹 Issue：#1020（跨账本重导——去重作用域降级到 ledger 级，象限 Q1）
