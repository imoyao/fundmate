# 基金E账户导入与数据去中心化评估（2026-08-16）

## 0. 背景与目标

两张参考截图构成了本次评估的起点：图1 是第三方工具面向普通投资者的「全平台资产分析攻略」，解决"多账户分散看不清"；图2 是国信证券等专业机构的「全账户基金诊断」，在聚合之上强调"相关性、成本、风格、评级"等归因诊断。结合《多多贝》"克制、专业、温暖"的设计语言，以及个人开发者的服务器与成本约束，本文把这两类能力拆解为可落地的三阶段计划，并在此基础上回应一个更关键的工程诉求：**降低后端对基础数据的维护与存储成本，探索把部分数据下沉到前端 / 开源静态源的可行性**。

本文是 `import-page-ux-and-monetization-review-2026-08-15.md` 与 `monetization-strategy-plan-2026-08-15.md` 的延伸，并吸收了 `docs/spec/importer-architecture.md`（持仓导入规范，已定稿未落地）的现状。

## 1. 现状对照（能力 vs 仓库现状）

| 规划能力 | 仓库现状 | 结论 |
|---|---|---|
| 优先级一：基金E账户导入 | `importer-architecture.md` §3/§4 已定稿；`positions` 表去重字段（`import_hash/source/source_import_id/source_broker`）已随 #928 落地；但**无「基金E账户」专属解析器** | 数据模型就绪，缺解析器 + 持仓导入流程 |
| 优先级二：资产透视饼图 | ECharts 已完整集成，已有可复用组件 `frontend/src/components/Charts/AssetAllocationDonut.vue`，颜色按 `--chart-01~08` 循环取色 | 基建近免费，主要接线 |
| 优先级三：Pro 深度诊断 | 由 issue #994（持仓详情页高级洞察 Pro 面板：归因/风险/配置 + 付费墙）与 #1000 承接；Pro 边界在 `monetization-strategy-plan-2026-08-15.md` 已定稿（免费永不转收费、Pro 只做加法） | 勿重议商业化，执行 #994 |
| 规则驱动静态诊断 | 与项目既有哲学（OCR 护栏、用量配额、零实时 LLM）一致 | 无需反驳，直接采纳 |

## 2. 三处必须修正的判断（来自首次评估）

2.1 **基金E账户导出的是「持仓快照」而非「交易流水」**。现有 6 个解析器（支付宝/天天基金/同花顺等）全是交易级（交割单/对账单），落在 `transactions` 表。E账户直接给持仓（代码、名称、份额、市值、成本），解析比交易流水果然更简单，但它走 `positions` 的 upsert 路径、不是 `transactions`——这是一条独立代码通道，不能复用交易解析器。

2.2 **E账户只覆盖公募基金，不覆盖股票、银行理财、债券**。所谓"全平台资产"经 E账户 = "全平台公募基金持仓"。股票仍需各券商交易导入（已支持）。引导文案须明确，否则用户会问"股票怎么没进来"。

2.3 **「防爆/降本」建议已被架构吸收**。SQLite 单进程后端解析 + 批量 upsert 几十万行并无压力，真正瓶颈是前端渲染（已正确识别）。`import_hash` 唯一约束已防重复写。"上传 → 服务端解析 → upsert → 返回报告"大半已设计，v1 不必真上后台异步 job，同步解析 + 跳转即可，异步仅锦上添花。

## 3. 数据去中心化评估：哪些数据可下沉到前端 / 开源静态源

### 3.1 后端当前维护的数据盘点（代码调研）

- **基金静态元数据 enrich**：`fund_detail_enrich_job.py` 经 xalpha/akshare 补充分类、公司、费率、拼音，写入 `Fund/FundType/FundCompany/FeeRatio` 等表。这是后端"维护数据太多"的主要来源之一。
- **净值 / 价格历史**：`price_history_job` / `fund_nav_job` 抓取并入库，前端聚合图表依赖它。
- **全A 中位 PB 基线**：`services/thermometer/data/all_pb.csv`（已入库、禁止删、pre-commit 守卫），温度计基线。
- **行业拥挤度分母**：行业分类数据。
- **用户数据**：持仓、交易、账户（Supabase 云端权威 + 本地缓存，隐私）。

### 3.2 分类矩阵：可前端化 / 必须后端 / 用户数据

| 数据维度 | 当前落点 | 建议 | 理由 |
|---|---|---|---|
| 净值 / 价格历史 | 后端抓取入库 | **保持后端** | 东财反爬（后端 TLS patch 已解）、用户分散直连会放大风控与失败率，集中抓取 + 缓存才是成本最优 |
| 基金分类 / 行业 / 风格标签 / 基准指数清单 | 后端 enrich 逐基金入库 | **前端化** | 变动慢、与用户无关，属"参考主数据"；可前端内置静态 JSON 或自有 Edge 托管轻量数据集，后端不再逐基金维护这些展示维度 |
| 拼音 / 首字母（搜索排序、自选分组） | 后端 pypinyin（3.2MB 重型依赖，延迟导入） | **前端化** | 前端 `pinyin-pro` 纯 npm 包零后端依赖，可卸载后端展示用途（后端分组逻辑若仍需可保留） |
| 费率科普表（"管理费一般 1.5%、托管费 0.25%"） | 散落 | **前端内置静态** | 常识展示无需入库；但用户持仓的**精确 per-fund 费率仍须后端** |
| 用户持仓 / 交易 / 账户 | Supabase 云端 | **不动** | 隐私，受 AGENTS 数据分级约束 |
| 全A PB 基线 `all_pb.csv` | 后端入库基线 | **不动** | 温度计分母兜底，已冻结 |

### 3.3 落地方案

把"参考主数据"（基金分类、行业、风格九宫格标签、基准清单、费率科普）从"后端逐基金抓取并入库"改为"前端 / 开源静态源"：① 前端内置或 Edge 静态托管一个轻量 JSON（零后端计算成本），`localStorage` 缓存、低频更新；② 净值等高频市场数据仍后端集中抓取 + 缓存。这样后端只维护用户数据与真正高频变动的市场数据。

### 3.4 约束与风险

- **CORS**：浏览器直连东财 / 天天基金大概率被拦。解法不是真让浏览器裸连，而是"静态内置"或"自有 Edge 托管小 JSON"，把"前端开源拉取"理解为参考数据的下沉，而非浏览器直连第三方。
- **合规**：只开放市场数据（AGENTS 数据分级），用户券商持仓绝不前端化。
- **更新**：静态数据集需随新发基金更新（你们发版带入，或 Edge 托管 JSON 独立更新），比后端 enrich 维度更易受控。
- **离线**：参考数据集前端可缓存，弱网下不影响展示。

### 3.5 与痛点的呼应

- **自动化不一定靠谱** → 减少后端 enrich 维度（分类前端算），少一处抓取维度就少一处腐烂源。
- **后期存储成本** → 参考数据集不进 DB，省存储与备份开销。
- **E账户本身即最大降本点** → 用户自带全平台公募基金持仓，规避我们维护各券商交易格式（现有 6 个交易解析器各自维护样本），一个统一格式解析器覆盖全市场公募，是"导入"侧最省维护成本的入口。

## 4. 排期（含 issue 草案与关联）

**P0 基础数据中枢（约 2 周，图表近免费）**

| 任务 | 工作量 | issue | 关联 |
|---|---|---|---|
| 基金E账户持仓解析器（新，阻塞于脱敏样本 XLSX） | 3–5 天 | I-新1（待建） | #929、importer-architecture §4 |
| 导入向导新增「持仓导入」模式（扩展 `refactor/split-import-wizard` 分支，positions upsert + import_hash；协调在途 wizard 拆分） | 3–4 天 | I-新2（待建） | #928、#929 |
| 2 张基础图表（复用 `AssetAllocationDonut`，资产分布 + 基金类型分布卡片） | 2–3 天 | I-新3（待建） | — |
| 参考数据前端化起点（基金分类 / 行业 / 风格 / 基准清单下沉前端静态 JSON，后端不再逐基金维护展示维度） | 2–3 天 | I-新4（待建，降本核心） | §3 |

**P1 Pro 组合体检（约 2–3 周，本质执行 #994）**

| 任务 | 工作量 | issue | 关联 |
|---|---|---|---|
| 综合组合管理费率透视（先固化管理费/托管费 per-fund 字段 + 加权计算） | 数据 2–3 天 + UI 2 天 | #994 子项（不独立建） | #994、§3.2 费率数据缺口 |
| 持仓相关性 / 集中度（基于重叠 NAV 历史 Pearson；price_history 覆盖不全须标注） | 3–4 天 | #994 子项 | #994 |
| 业绩走势 vs 基准 + 风格标签 | 3–5 天 | #994 子项 | #994 |

**P2 分享 / 智能快照（约 1–2 周，风险最低）**

| 任务 | 工作量 | issue | 关联 |
|---|---|---|---|
| `html2canvas` 持仓全景长图海报 | 2–3 天 | I-新7（待建） | — |
| 规则驱动静态诊断卡片（无 LLM，规则引擎） | 2–3 天 | I-新8（待建） | #823 配额哲学 |

## 5. 原子 issue 草案（内联）

- **I-新1 `feat(import): 基金E账户持仓解析器`**：新增 `EAccountHoldingParser(BaseHoldingParser)`，输出 `StandardHoldingRecord` 并经 `PositionService.upsert_from_holding` upsert `positions`（不建交易流水，带 `import_hash`）。复用/解耦设计见 **§8**。前置：须先取得一份脱敏样本 XLSX 才能写列映射与断言测试（importer-architecture §2.4）。建议独立建 issue。
- **I-新2 `feat(import): 导入向导新增「持仓导入」模式`**：扩展当前正在重构的 wizard（`refactor/split-import-wizard`），与交易导入解耦，复用 #928 去重机制。建议独立建 issue。
- **I-新3 `feat(chart): 资产透视区块（资产分布 / 基金类型分布环形图）`**：复用 `AssetAllocationDonut.vue`，新增「资产透视」卡片区。建议独立建 issue（近免费）。
- **I-新4 `refactor(data): 基金分类/行业/风格等参考主数据前端化`**：降本核心。把展示维度从后端 enrich 改为前端 / Edge 静态托管 JSON，后端不再逐基金维护。建议独立建 issue。
- **I-新5 / I-新6**：综合费率透视、相关性集中度，均为 #994 的执行子项，**不独立建 issue**，在 #994 下拆 checklist 或子任务引用。
- **I-新7 `feat(share): 持仓全景长图海报（html2canvas）`**：P2。建议独立建 issue。
- **I-新8 `feat(insight): 规则驱动静态诊断卡片`**：P2，无 LLM。建议独立建 issue。

已复用、勿重建：#928（positions 去重已落地）、#929（持仓导入复用）、#994（Pro 高级洞察面板）、#1000（自选上限 Pro）、#823（OCR 配额护栏）、#826（分层定稿）、importer-architecture.md。

## 8. E账户解析器：复用与解耦设计（#1012 深化，设计态）

> 本节把 §2.1 的判断落到「代码管线」层面，明确 E账户解析器如何复用现有基础设施、又与交易解析器解耦。仅设计，不落地代码。

### 8.1 确认：你的理解对，但边界要厘清

- **对的部分**：E账户导出的是「持仓快照」（代码、名称、份额、市值、成本），必须落 `positions`，**绝不能落 `transactions`**。现有 `BaseImportParser` / `orchestrator.commit` / `PositionService.process_buy_or_deposit` 整条链路都会 `TransactionService.create`（`position_service.py:312`），当前没有任何「写持仓但不建流水」的出口。所以确实要新设计一条分支。
- **修正的部分**：持仓侧的**数据模型**已经就绪——`positions.import_hash`、`source`、`source_import_id`、`source_broker` 字段与 `uq_positions_import_hash` 唯一约束已随 #928 落地，`compute_position_hash`（`records.py:41`）也已存在。换句话说，缺的是**解析器契约 + 编排器/服务管线**这两层代码，而不是数据模型或去重机制。因此「重新设计」是**新增一条并行的持仓分支**，不是推翻现有 7 个交易解析器。

### 8.2 复用清单（保持不动，避免重造）

- **文件读取工具**：`BaseImportParser._read_excel` / `_read_csv` / `_decode_bytes`、`FAST_ENCODINGS` / `EXCEL_ENGINES` 等。E账户是 XLSX，直接复用 `_read_excel`。
- **持仓去重三件套**：`compute_position_hash`（已建）、`uq_positions_import_hash`（已上约束）、`import_hash`/`source` 字段（已上模型）。无需新建。
- **名称/类型补全**：`orchestrator._batch_query_asset_info` / `_fill_names_and_types` 按代码解析基金名称与品种（含货币基金识别），持仓同样需要，可共享或轻量适配。
- **金额单位换算**：`Money.shares_to_min_unit` / `yuan_to_cents` / `multiply_price_quantity`，新 upsert 方法直接复用。
- **注册表机制**：`register_parser` / `get_parser` / `PARSER_REGISTRY`（`registry.py`）本身与「交易/持仓」无关，可直接挂 E账户 source。

### 8.3 解耦清单（必须新增，互不污染）

- **`StandardHoldingRecord`（新 dataclass，`records.py`）**：持仓形态输出，字段含 `symbol / name / asset_type / shares / avg_cost(元) / market_value(元) / snapshot_date / account_name / ledger_id / source / import_hash`。**无** `trade_date` / `transaction_id` / `fee` / `business_type`——这些交易概念对快照无意义，硬塞进 `StandardTransactionRecord` 会污染交易语义。
- **`FileParsingMixin`（提取，非新增大改造）**：把文件读取工具从 `BaseImportParser` 抽为共享 mixin（或模块级函数），让 `BaseImportParser`（交易）与新建 `BaseHoldingParser`（持仓）都继承它。这样两个基类各有清晰独立的 `parse()` 返回类型，避免「一个基类扛两种契约」的模糊。
- **`BaseHoldingParser`（新基类）**：继承 `FileParsingMixin`，声明抽象 `parse(file_bytes) -> List[StandardHoldingRecord]` 与 `validate(...)`；自带 `target = 'holding'`（交易基类 `target = 'transaction'`）。E账户解析器 `EAccountHoldingParser(BaseHoldingParser)` 只实现文件列映射。
- **注册表加 `target` 判别**：`PARSER_REGISTRY` 不变，但每个解析器携带 `target`。编排器据此决定走交易落库还是持仓落库，7 个交易解析器无需改动。
- **编排器分叉**：在 `orchestrator.py` 新增 `parse_and_preview_holdings()` 与 `commit_holdings()`，与现有 `parse_and_preview` / `commit`（交易）**完全并行**。预览阶段同样做「按 `positions.import_hash` 集合查重 → 标 `is_duplicate`」的幂等检查，复用交易预览的去重套路。
- **`PositionService.upsert_from_holding(data)`（**新核心方法，治本点**）**：以 `(ledger_id, symbol)` 为业务键做 upsert，**只更新 `quantity` / `avg_price` / `snapshot_date` / `import_hash` / `source` 等溯源字段，绝不调用 `TransactionService.create`**。这是与 `process_buy_or_deposit` 最本质的区别，也是「导入持仓而非流水」的落点。
- **端点**：导入向导（#1013 在途重构）的端点带 `mode`/`target` 判别（或并行 `holding` 端点），前端 wizard 据此切换预览/落库分支；与 #1013 协调避免冲突。

### 8.4 通道 × 数据类型：2×2 矩阵与「入口两处分立」设计决定

导入这件事有两条**正交**的轴，必须分开看，否则极易混淆：

- **轴一 通道（入口形态）**：① 文件上传（XLSX/CSV/PDF，格式确定，走解析器）；② AI 截图/文本识别（图片或粘贴文本，走 `ai_recognizer` LLM 识别）。
- **轴二 数据类型（落库目标）**：① 交易流水/交割单 → `transactions` 表；② 持仓快照 → `positions` 表（不建流水）。

两条轴交叉成 4 个组合，**每个组合都是独立的解析器/入口，但只汇向两个落库汇点之一**（transactions 汇点 `process_buy_or_deposit` / positions 汇点 `upsert_from_holding`）：

| 通道＼数据类型 | 交易流水/交割单（→ transactions） | 持仓快照（→ positions，不建流水） |
|---|---|---|
| 文件上传 | 现有 7 个交易解析器（支付宝/天天基金/同花顺…） | **E账户解析器 #1012**（新建）→ `upsert_from_holding` |
| AI 截图/文本识别 | `txn_recognizer`（**已存在**，`source='ai_txn'`）→ `process_buy_or_deposit` | **`holding_recognizer`（缺失，需新建）** → `upsert_from_holding` |

**关键设计决定（回应「入口两处」诉求，用户观点正确）**：AI 截图识别必须拆为「**持仓导入**」与「**交易流水/交割单导入**」两个**独立入口**，**不可合并为一个「自动识别」入口**。理由：用户截「持仓页」（显示份额/市值/成本）与截「交割单页」（显示买卖流水）是两种明确不同的意图，混在一个入口靠模型猜类别会混淆、易错、难追溯、且预览表格字段完全不同（持仓无 `trade_date`/`fee`，交易无 `market_value`）；显式选择更克制、专业、可预期，契合《多多贝》"克制、专业、温暖"的设计语言。文件上传通道同理——E账户（持仓）入口与交易交割单入口也必须分立。

**现状对齐**：前端 `frontend/src/api/ocr.ts` 的 `OcrScenario` 目前只有 `watchlist_import`（自选）与 `txn_import`（交易），**缺 `holding_import`（持仓）**；后端 `services/ai_recognizer/` 已有 `txn_recognizer.py` 与 `watchlist_recognizer.py`，**缺 `holding_recognizer.py`**。落地时：新增 `holding_import` 场景，与 `txn_import` **平级分立**（自选 `watchlist_import` 是第三种、既非持仓也非交易，不在此矩阵内）。

**共用汇点修正（呼应 §8 复用主线）**：E账户文件解析器（持仓）与 OCR 持仓识别（`holding_recognizer`）汇向**同一个** `upsert_from_holding`；OCR 交易识别（`txn_recognizer`，已存在）与 7 个文件交易解析器汇向**同一个** transactions 汇点。两个汇点各自内部复用，跨汇点不混——这正是「复用 + 解耦」的平衡点：通道（文件 vs OCR）可以不同，但同数据类型的落库逻辑只有一套。

**附带修正一个潜在隐患（已登记为 #1018，详见 §8.8）**：当前 AI 预览 `orchestrator.preview_records`（默认 `source='ai_txn'`）最终经 `commit_from_preview → commit → process_buy_or_deposit` 会**误建交易流水**。这意味着现在若用 AI 识别「持仓截图」，会被错误地当成交易流水写库——这是一个真实的数据完整性缺陷，已单独立 issue #1018 跟踪，待 §8 的 `holding_recognizer` + `upsert_from_holding` 落地后消除。

### 8.5 两个唯一约束的分工（去重语义澄清）

- `uq_positions_ledger_symbol`（ledger_id + symbol）：业务唯一键，保证一个账户下某标的一份汇总持仓。E账户 re-import 时靠它定位既有行做 upsert（刷新数量/成本/快照日）。
- `uq_positions_import_hash`（import_hash 单列）：内容指纹，用于「同一份快照重复上传」的幂等拦截。**预览阶段**就查 `positions.import_hash` 集合标记 `is_duplicate`，提交时跳过——同日期重复上传被标重、不写；**换快照日**则哈希不同、不被标重、upsert 刷新该行。两个约束分工清晰，不冲突。

### 8.6 待决（不阻塞设计，落地前定）

- **快照数量语义：SET 还是 MERGE？** 快照是某日点位的「绝对值」，直觉上应 `SET quantity = 快照值`（替换）。但 `process_buy_or_deposit` 现有合并语义是**累加**。E账户落地前须明确：是按快照**整条替换**（快照为准），还是**累加合并**（兼容手动录 + 快照）。建议默认「按快照替换该 symbol 的 quantity/avg_price」，因为快照已是全市场公募真实持仓，比手动录更权威；手动录入的孤立持仓若无对应快照则保留。
- **`snapshot_date` 来源**：E账户导出含「数据日期/基准日」字段，直接映射为 `snapshot_date` 喂给 `compute_position_hash`。若样本无该字段则降级为落库当日（§3.3 既有降级规则）。

### 8.7 小结（#1012 落地前的设计结论）

导入 = **通道（文件上传 / AI 截图）** × **数据类型（交易流水 / 持仓）** 的 2×2 矩阵，4 个组合各自是独立入口，但只汇向两个落库汇点之一：交易汇点 `process_buy_or_deposit`（7 个文件交易解析器 + 已存在的 `txn_recognizer`）与持仓汇点 `upsert_from_holding`（新建的 E账户 `EAccountHoldingParser` + 待建的 `holding_recognizer`）。

持仓分支的落地形态（#1012）= `StandardHoldingRecord` + `BaseHoldingParser`(共享文件读取 mixin) + 注册表 `target` 判别 + 编排器 `commit_holdings` + **`PositionService.upsert_from_holding`（不建流水）**。与交易分支并行、互不修改。**AI 截图识别必须拆「持仓导入」与「交易流水导入」两个独立入口、不可合并**（用户已确认此 UX 决定）；前端 `OcrScenario` 需新增 `holding_import` 平级分立。硬阻塞仍是 §7 的脱敏样本 XLSX——拿到样本后才能写 `EAccountHoldingParser` 的列映射与断言测试。

### 8.8 已知隐患与待修缺陷（跟踪：#1018）

- **隐患**：当前 AI 预览 `orchestrator.preview_records`（默认 `source='ai_txn'`）最终经 `commit_from_preview → commit → process_buy_or_deposit` 会**误建交易流水**。用户若截取「持仓页」（份额/市值/成本）走 AI 导入，识别结果会被错误地当成交易流水写入 `transactions` 表，造成持仓数据污染且难追溯。根因：后端只有一个交易落库汇点，缺「写持仓但不建流水」的 `upsert_from_holding` 与 `holding_recognizer`。
- **已建 issue**：#1018（`fix(import): AI 持仓截图/文本识别误经交易管线建流水，须新增 holding_recognizer 改走持仓汇点`），已挂 Project 3 看板、设象限 Q2、正文首行含 `[AI 创建]` 标注，并与本文档 §8.4 互引。
- **修复落点**：与 §8.4 的 `holding_recognizer`（待建）+ `upsert_from_holding`（待建）同源——修复即「持仓类识别改走持仓汇点」。该缺陷在 #1012 的持仓汇点就绪前无法消除，故与 #1012 协同排期；但作为独立数据完整性缺陷单独立 issue 跟踪（原子化，不塞进 #1012）。
- **状态**：设计态，未落地。待 #1012 持仓汇点就绪后一并修复并回归验证。

## 6. 关联引用

- `docs/spec/importer-architecture.md`（持仓导入规范 SSOT）
- `docs/working-notes/import-page-ux-and-monetization-review-2026-08-15.md`
- `docs/working-notes/monetization-strategy-plan-2026-08-15.md`
- `frontend/src/components/Charts/AssetAllocationDonut.vue`（现成环形图）
- `backend/app/services/sync/jobs/fund_detail_enrich_job.py`（后端 enrich 维度，降本对象）
- GitHub：#928 / #929 / #994 / #1000 / #823 / #826

## 7. 待确认

- 是否将 I-新1~I-新4、I-新7、I-新8 创建为 GitHub issue（按惯例须标注 `[AI 创建]` + UTF-8 环境；建议由用户定夺后我再建）。注：I-新1~I-新4、I-新7、I-新8 已于 2026-08-16 实际创建为 #1012/#1013/#1014/#1015/#1016/#1017（挂 Project 3 看板、设象限、中文校验通过），本条待确认已落地，无需再建。
- E账户脱敏样本 XLSX 的获取是 P0 唯一硬阻塞，须优先。
- I-新4 的"参考主数据前端化"是否与正在进行的其他前端重构（如自选页 redesign）共用同一份静态数据集，避免重复造。
- **§8.6 待决**：E账户快照的数量语义（SET 替换 vs MERGE 累加）与 `snapshot_date` 缺失降级规则，落地 #1012 前须与用户敲定。

## 9. 状态与变更记录

> 约定：本文档与 GitHub issue **互相引用、不各写各的**；任何相关代码/设计落地后，须及时回写本节状态与对应章节，保持文档为最新真相（single source of truth）。

- 2026-08-16：创建计划文档；#1012~#1017 落地（E账户解析器等原子 issue，挂 Project 3 看板、设象限）。
- 2026-08-16：深化 §8 复用/解耦设计（E账户 + OCR 共用持仓汇点 `upsert_from_holding`、AI 截图「入口两处分立」决定）。
- 2026-08-16：识别并登记「AI 持仓识别误建流水」隐患为 **#1018**（Q2），本文档 §8.4 / §8.8 与 #1018 互引；issue 正文亦回引本文档。
- 2026-08-16：**E账户持仓解析器后端落地**（分支 `feat/e-account-holding-import`，5 个分步提交，rebase 至本地 main-v2 基线）：
  - 解析器契约：`StandardHoldingRecord` + 抽 `FileParsingMixin` + `BaseHoldingParser`（target='holding'）+ `EAccountHoldingParser`（表头定位容错：扫描前 20 行定位含「基金代码」+「持有份额」的表头行，兼容带/不带个人信息两种上传形态；列名清洗去换行；坏行收集不中断）；
  - 落库汇点：`PositionService.upsert_from_holding`（SET 语义整条替换、**绝不建交易流水**、avg_price 缺失降级为净值近似、溯源元数据 1:1 写 `position_import_meta`）；
  - 编排器持仓分支：`parse_and_preview_holdings` / `commit_holdings`，与交易分支完全并行；
  - 聚合账户：`ledger_type` 扩展 `e_account`，首次导入自动创建「基金E账户」聚合账户（用户确认方案 B）；
  - 溯源表：新增 `position_import_meta`（基金管理人/份额类别/基金账户/交易账户/分红方式/销售机构/市值，用户确认专用表方案）；
  - API：`POST /api/importers/holdings/parse` + `/holdings/confirm`；ledger 统计分支适配 e_account；
  - 测试：脱敏样本 fixtures（两种变体）+ 17 个断言用例全过，全量 741 无回归。
  - **待办**：前端导入向导「持仓导入」模式（#1013，后端完成后规划）；`holding_recognizer`（#1018，OCR 持仓识别改走持仓汇点）；真实样本回归验证（当前用脱敏样本）。
