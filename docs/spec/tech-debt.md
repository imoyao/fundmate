---
title: 技术债务与开口项明细（tech-debt）
---

# 技术债务与开口项明细（tech-debt）

> ⚠️ **易腐烂内容**：本文件随修复进展频繁变化。最后核实日期：**2026-09-13**。每条债务修复后，须将状态更新为"✅ 已修复"并注明版本号；请勿删除历史条目（保留可追溯）。
>
> **看板同步（2026-08-14）**：本文档技术债务已全量同步至 GitHub Project 看板（多多贝·投资账本 #3）并按四象限赋级——补登被引用但未进看板的 #796/#230/#507/#911；将 §1/§9–§12 中无 issue 编号的独立债务条目提升为 issue #948–#976 并赋象限；其余被引用的 issue（#821/#825/#869/#894/#898/#912/#913/#820/#824/#933/#934/#937/#947 等）统一补挂象限。交叉引用以 issue 编号为准。
>
> **占位 issue 复盘清理（2026-08-14，用户复核）**：同步时批量提升的 #948–#976（另 #947）共约 30 个占位 issue 未经实质验收、且未标注 AI 身份，经用户指出。已关闭其中 15 个冗余/无行动项——#952/#953/#954/#956/#957/#958/#959/#960/#961/#962/#963/#964/#969/#970/#971（与 #899 重复，或债务本身写明「暂不处理 / 放弃追踪 / 当前方案够用 / 待实现」）；保留 15 个可执行项 #947/#948/#949/#950/#951/#955/#965/#966/#967/#968/#972/#973/#974/#975/#976 并补「AI 创建」标注。关闭项的债务明细仍以本文档为准，不在看板另行占卡。AI 创建/关闭须标注身份的规则已写入记忆（#14890672）。

## 1. 技术债务 & 开口项明细（原 SPEC 第 10 章）

| 问题描述 | 优先级 | 产生原因 | 处理策略 |
|---|---|---|---|
| ~~基金代码被错误标准化（如 001414 变成 SZ001414）~~ | ~~🔴 严重~~ **✅ 已修复 (v4.6.0)** | ~~标准化逻辑未区分基金与股票~~ | ~~修改 `normalize_and_infer_venue`，要求显式传入 asset_type/venue，场外基金直接保留原代码~~ |
| ~~自选列表筛选条件不生效~~ | ~~🟡 中~~ **✅ 已修复 (v4.6.0)** | ~~前端 `setVenueFilter` 调用了不存在的方法~~ | ~~修正为统一调用 `fetchData`~~ |
| ~~添加自选弹窗直接裸写 http 请求~~ | ~~🟡 中~~ **✅ 已修复 (v4.6.0)** | ~~未封装 API~~ | ~~新增 `createWatchlistItem` API 封装，并在 `AddToWatchlistModal` 中使用~~ |
| 自选模块视图层业务逻辑过重 | ~~🟡 中~~ **✅ 已修复 (v4.6.0)** | ~~`list_items`、`create_item` 等直接在 views 中处理 ORM 查询~~ | ~~抽取至 `app/services/watchlist_service.py`~~ |
| ~~（保留原 4 个后端 BUG：市值放大）~~ | ~~🔴 致命~~ **✅ 已修复 + 文档纠偏 (v4.5.3/v4.5.7)** | ~~原描述"`/10000` 导致放大 100 倍、分母应为 1,000,000"系 SPEC 笔误~~ | **事实更正（重要）**：当前 `Money.multiply_price_quantity` 以 `price_cents × quantity_units / SHARE_FACTOR(10000)` 计算，**单位换算正确，不存在 100× 放大**；该实现已被 `tests/core/test_money.py` 锁死（`1050×1001234 → 105130`）。**禁止依据旧 SPEC 把代码改为 ÷1,000,000，否则会引入真实的 100× 错误**。SQL 市值聚合已移除，统一走 Python 聚合 + `Money.cents_to_yuan`。 |
| **成交价格与净值自动填充及校验接口** | 中 | 目前买入/卖出仅依赖手动输入价格。为提升用户体验并防止误操作，需要后端提供股票/基金的当日价格区间（股票需要最高/最低价校验，基金需要按确认日净值自动回填）。 | **P2 阶段细化实现**。设计接口：股票（`GET /api/securities/{symbol}/price-range/?date=...`），基金（`GET /api/funds/{code}/nav/?date=...`）。前端在 `BuyForm` 和 `SellForm` 选中产品后调用，自动填入默认值，并限制用户输入的数值在价格区间内（用于股票）。 |
| ~~（保留原 `get_ledger_summary` 问题）~~ | ~~🔴 严重~~ **✅ 已修复** | ~~bank/property 分支写在 `if ledger_type in ('stock','fund')` 的 elif 中，永远不执行~~ | ~~将 bank/property 提升为与 stock/fund 同级的独立分支~~ |
| ~~（保留原前端 API 路径问题）~~ | ~~🔴 严重~~ **✅ 已修复** | ~~后端返回 `{data: [...], total, page}`，前端解析为 `res.data.data`~~ | ~~后端统一包裹为 `{data: {items, total, page, per_page}}`~~ |
| 腾讯理财通格式复杂 | 中 | 理财通导出格式非标准 CSV，需专门解析器 | P2 实现 |
| 孤儿交易无自动回填机制 | 中 | 需定时任务扫描并关联后续新增的持仓 | P1-20 实现 |
| ~~持仓分布可视化缺失~~ | ~~中~~ **✅ 已实现 (2026-08-09)** | 原描述：仪表盘仅有总资产展示，无配置结构图 | **实证回填**：仪表盘资产分布饼图基于 `summary.market_distribution` 渲染（`welcome/index.vue:741-767`）；账户详情页资产配置环形图基于持仓前端聚合（`ledgers/detail.vue:862-889`），与 roadmap §1.4「资产配置环形图已实现」吻合。 |
| 货币基金识别依赖关键词硬编码 | 中 | 元数据同步未完全覆盖所有货币基金名称，临时使用关键词匹配兜底 | 待元数据同步覆盖率足够后移除关键词逻辑 |
| 持仓详情页单持仓 XIRR 前端展示 | 低 | 页面路径未确定 | 后端接口已可用，前端延后至 P2 |
| 导入时出现 SAWarning: Identity map already had an identity for... | 低 | 同一 Session 内多次加载同一持仓后尝试 flush，导致 ORM 身份映射冲突 | 后续优化 PositionService 会话管理，当前不影响数据正确性 |
| ~~PDF 解析器对无效日期行的处理~~ | ~~低~~ **✅ 已修复 (2026-08-09)** | 原行为：`alipay_pdf.py::_row_to_record` 对无效确认日期静默 `return None`，整行无记录被丢弃且不产生任何错误提示 | **实证回填**：改为 `raise ValueError('确认日期无效: ...')`，由 `parse()` 的异常分支统一收集为 `SBImportError`（含行号），无效日期行**被报告**而非静默丢失；`test_invalid_confirm_date` 同步锁定 `errors` 非空断言（14 passed）。 |
| **`Ledger.ledger_type` 缺少 `property`（实物资产）类型** | **低** | **早期设计优先覆盖金融资产，实物资产通过 `Asset` 表快速兼容，未在账户类型体系中显式支持。用户录入房产等固定资产时无法选择匹配的账户类型，只能变通使用 `family` 类型。** | **P2 阶段新增 `property` 类型，统一 `LEDGER_TYPE_LABELS` 映射，前端账户创建页同步添加选项。届时需同步校验 `linked_cash_ledger_id` 仅对 `stock/fund` 有效。当前变通方案：引导用户使用 `family` 类型。** |
| 前端 `Inventory.vue` 虽经轻量重构，仍有 800+ 行，未完全拆分 | 中 | 功能迭代优先级高于重构，拆分延后 | P2 拆分 |
| 按平台分组盈亏缺失 | 低 | 用户无法与平台账单对账 | P2-14 实现 |
| ~~交易记录导出功能缺失~~ | ~~低~~ **✅ 已实现 (2026-08-09)** | 原描述：用户无法备份数据 | **实证回填**：P2-15 已于 2026-08-07 上线（roadmap §2.6）——后端 `export_transactions`（`transactions/views.py:102`，`GET /api/transactions/export/`）；前端交易流水页导出按钮 + blob 下载（`TransactionList.vue:22,449`，`api/transactions.ts:27`）；`test_transactions_export_csv` 通过。 |
| 支付宝解析器对特殊格式（引号内逗号）的容错性 | 低 | 实际用户导出格式已稳定，当前方案够用 | 若未来出现新格式再适配 |
| 余额宝背后货币基金无法准确识别具体代码 | 低 | 支付宝不公开具体基金代码，且可能变化 | 统一归入活钱，放弃追踪具体货基 |
| 导入成功后净值自动同步（静默回填）已实现但依赖元数据同步 | 低 | 若用户从未同步过基金数据，`daily_worth` 表为空 | 导入前引导用户执行元数据同步，或导入后手动触发 |
| 桑基图资产负债交叉显示问题（ECharts 底层限制） | 低 | 图表原生不支持正负双流向分层 | 记录技术债务，暂不处理 |
| ~~交易流水全量加载无分页~~ | ~~低~~ **✅ 已实现 (2026-08-09)** | 原描述：交易流水全量加载，大数据量无分页筛选优化 | **实证回填**：后端 `list_transactions` 已 `paginate` + `page/per_page`（`transactions/views.py:28-29,75,98`）；前端交易流水页 `el-pagination` + 分页参数（`TransactionList.vue:169-177,415`）。 |
| 基金经理信息未同步 | 低 | `ak.fund_manager_em` 接口不稳定 | 调研替代方案，暂不实现 |
| 指数行情同步不可用 | 低 | 新浪接口不支持指数代码 | 改用 `xa.indexinfo`，待实现 |
| 全量同步时 `stock_list` / `fund_list` 需传入占位 `["__full__"]` | 低 | 重构遗留问题 | 后续优化为在 Job 中声明不需要 targets |
| `Transaction.confirm_date` 存在 NULL 值 | **已消除** | 早期写入源头未统一赋值 | 所有写入入口已堵上；存量仅 1 条，已手动修复 |
| `positions.type` 列存在 NULL/空值 | **已消除** | 部分导入解析器/手动录入未写入 `asset_type` | 数据库验证已清零，所有入口均已适配 |
| `get_money_fund_stats` 调用传入 `ledger.name` 而非 `ledger.id` | ~~🟡 中~~ **✅ 已验证** | 原怀疑参数类型错误 | 代码审查确认已传入 `ledger.id`，货基统计正常 |
| `delete_ledger` / `migrate_positions` 未跟随 `ledger_id` 迁移 | ~~🟡 中~~ **✅ 已验证** | 原怀疑仍用字符串过滤 | 已改为 `Position.ledger_id == ledger_id`，迁移同步更新快照 |
| **`GET /api/ledgers/` 未返回账户摘要数据** | ~~🔴 严重~~ **✅ 已修复** | 列表页卡片依赖 `total_market_value`、`pnl`、`position_count` 等字段，但接口只返回基础字段 | 在 `list_ledgers` 中为每个账户附加摘要统计 |
| **`position_ratio` 返回类型不一致** | 🟡 中 | `get_position_page` 中 `round()` 结果可能因单位混用而异常，且类型可能是 float 或 str | **✅ 已验证，已修复。在 v4.4.1 中强制转为 `float(0.0)` 兜底，消除了前端解析歧义。** |
| **同花顺解析器操作类型映射不完整** | ~~中~~ **✅ 已化解 (2026-08-09)** | 原描述：`test_ths_otc_cash_format` 测试中 `OTC现金宝交` 的操作类型无法从映射表确定方向，测试被跳过 | **实证回填（描述失真修正）**：资金划转方向已在解析器层兜底解决（`parser.py:231-241` / `ths_stock.py:237-245` 先做 OTC 正则剥离，再按 `net_amount` 正负映射 `deposit`/`withdraw`、标 `is_cash_transfer=True`），不依赖映射表（`THS_OP_TYPE_MAP` 中 `OTC现金宝交` 标 `None`，`constants.py:122`）。`test_ths_otc_cash_format` 为**已删除**（非"被跳过"），当前由 `test_ths_cash_transfer`（test_importers.py:332/641）与 `test_parse_cash_transfer_integration`（test_ths_stock_parser.py:151）覆盖。 |
| **`get_ledgers_overview` 中总资产计算依赖净资产的推导** | ~~低~~ **✅ 已修复 (2026-08-09)** | 原描述：总资产通过 `net_worth + liability_total` 反推，而非直接从各组市值汇总 | **实证回填**：`ledger_service.py:87-88` 已正向聚合（`total_assets = sum(g['total']...)`，`net_worth = total_assets - liability_yuan`）；后端 API 不下发 `total_assets`，前端亦正向汇总（`ledgers/index.vue:395-401`）。**无反推入口**，债务已消除。 |
| **导入模块视图层仍较厚** | ~~低~~ **✅ 已化解 (2026-08-09)** | 原描述：`app/domains/importers/views.py` 未完全拆分，部分校验逻辑耦合在视图函数中 | **实证回填**：当前 views.py 仅 160 行 / 3 个视图函数（`download_import_template`/`parse_file`/`confirm_import`），业务逻辑已委托 `ImportOrchestrator`/`template_config`，文件自标"薄视图"。**债务已化解**。 |
| **`positions.source` 语义边界确认 + 分红/除权来源开口项** | 低（开口项，非缺陷） | 2026-08-19 归一化 `PositionSource` 枚举 + `@validates` 约束（提交 c8ca9ef/833edaf）后，旧测试中出现 `dividend`/`broker_ht` 等非白名单字符串被拦截。经代码查证：`dividend` 属 **`op_type`/`txn_type` 体系**（`THS_OP_TYPE_MAP`、`OP_TYPE_LABEL`、`txn_type='dividend'` 分红流水），并非 `positions.source`（持仓来源渠道）的合法取值；`broker_ht` 在 backend 全量代码中不存在。两者均不应出现在 `source` 字段，旧测试写法为误用，已改为 `manual`（不丢失业务数据，分红仍走 op_type）。 | **保留现状 + 留开口，后续核查（不急于处理）**：① 确认 `source` 字段语义仅为"持仓来源渠道"（manual/e_account/各券商/探市/AI），分红/除权/拆分等一律归属 `op_type`，不在 source 扩展；② 留存开口：若未来确有"分红来源渠道"语义需求（如区分红利来自哪个平台/账户），再决定是否在 `PositionSource` 新增枚举值（如 `dividend_cash` 等），并同步 `POSITION_SOURCE_LABELS` 与 `/api/utils/enums`；③ 前端/导入向导任何历史代码若曾误传 `dividend` 到 `source` 需排查（当前搜证未见）。当前 `PositionSource` 12 值 + `PositionImportMeta` 同源约束已锁定白名单，测试全绿，**不回退 833edaf**。温度域 `SOURCE_DISPLAY_NAMES` 归一化见独立 issue，不混入。 |
| 组合收益计算未支持跨日划转识别 | ~~低~~ **不适用** | 原逻辑：需交易级时间戳 + 人工标记 | **经审查确认：`deposit/withdraw` 不进入组合 XIRR 现金流，跨日划转不影响收益率。此技术债不适用，留待 P2 转账配对功能再评估。** |
| **投资理财与通用资产按需加载依赖校验** | 低 | 全面盘点页面依赖后端 `/api/assets/summary/` 接口呈现顶部汇总金额。如果接口因网络问题失效，顶部卡片将失去数据 | 需在前端 `fetchData` 中对 summary 接口添加健壮的错误处理与降级展示。 |
| **`usePageRefresh` 全局数据同步尚未覆盖所有页面** | ~~中~~ **✅ 部分覆盖 (2026-08-09)** | 原描述失实：声称 `LedgerDetail.vue` 与 `InventoryHome.vue` 已接入，实证仅 `ledgers/index.vue`（账户列表）与 `ledgers/detail.vue`（账户详情）接入，全面盘点页 `InventoryHome`（`views/asset/inventory/index.vue`）**未接入** | **2026-08-09 实证回填**：修正描述失实；已为 `InventoryHome` 补上 `usePageRefresh` 接入（与 `ledgers/index.vue` 同范式）。其余新页面（自选、交易流水等）开发时仍需引入 `usePageRefresh` 以保持数据同步。 |
| ~~双代码库：V1 为遗留残留、V2 为唯一代码库~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | `autoapp.py` 启动遗留 V1，README 实际运行 V2；前端/测试/DB 均指向 V2，且 V1 被 `.gitignore` 忽略 | **已执行物理清除**：删除 `fundmate/`、`migrations/`、`autoapp.py` 及 29 个 V1 移植测试；备份于 `.backup-v1-2026-08-01/`。V2 为唯一代码库。 |
| ~~V1 `data/` 数据源冗余~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | V1 `data/` 20+ 源在 `backend/app` 引用数均为 0；V2 经 `services/sync`+`services/thermometer` 独立覆盖；券商持仓自动导入类源违反 §2.1 | **随 V1 一并删除、不移植**。 |
| ~~`fundmate/libs/cal` 残留计算库~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | V2 已有等价 `app/services/performance/xirr_engine.py`，`app/` 零引用 | **直接删除不移植**；XIRR 数值金值迁入 `tests/services/performance/test_xirr_engine.py`。 |
| ~~测试目录双轨（V1 移植残留 29 文件）~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | `tests/` 含指向 `backend.fundmate` 的移植测试，由不被自动加载的 `conftest_fm.py` 支撑 | **删除 29 个 V1 测试文件 + 辅助**；测试单轨化，`pytest` 全绿；新增 `scripts/forbid_v1_refs.sh` 守卫禁止回引。 |
| ~~V2 `app/main.py` 错误契约未入 `create_app` 且 `abort()` 绕过 `{data,message}` 信封~~ | ~~高~~ **✅ 已修复 (2026-08-01, v4.5.8)** | `register_error_handlers` 仅在模块级 `app` 注册，未放进 `create_app()`；`app/` 内约 65 处 `abort()` 返回缺 `data` 字段 | **实测修正（反向压力测试通过）**：未将 65 处 `abort()` 逐一改为 `SBException`（改动面大、回归风险高），改为在 `create_app()` 内挂载全局异常处理器，并新增通用 `HTTPException` 处理器把 `abort()` 各状态码（400/404/409/500……）统一收敛到 `{data, message, error_code}` 信封；`ErrorCode` 增补 `UNAUTHORIZED(1005)`/`FORBIDDEN(1006)` 以覆盖 401/403 映射。新增 `tests/test_error_envelope.py` 直接验证 `create_app()` 实例（即测试 fixture 实际所用 app）已挂载处理器且各状态码均返回信封。全量 `pytest` 466 passed / 1 failed（唯一失败为 eastmoney 实时联网依赖）。 |
| **`app/` 内 13 处 `@bp.input()` 自动范式装饰器（违反 §1.3「不依赖自动范式」）** | ✅ 已闭环 (2026-08-16) | SPEC §1.3 要求「不依赖自动范式，为迁移 FastAPI 预留空间」；但 `watchlist(6)/positions(2)/assets(2)/funds(1)/strategy(1)/performance(2)` 共 14 处用 `@bp.input(Schema)` 把请求校验交给 APIFlask 框架，视图签名依赖其注入的已校验对象。注：**输入模型本身已为 `pydantic.BaseModel`（FastAPI 就绪）**，故模型迁移成本≈0，冲突仅限装饰器调用本身（`importers/views.py` 内 2 个未启用 Schema 才是真 marshmallow）。 | **已全部闭环（2026-08-16，#973）**：13 处 `@bp.input()` 全部改用 `app/core/validation.parse_body()`/`parse_query()`（`watchlist(6)` 已于早期完成；`positions(2)/assets(2)/funds(1)/strategy(1)/performance(2)` 后续统一），输入模型即 `pydantic.BaseModel`（FastAPI 就绪），`pytest -p no:xdist` 全绿；新增 `scripts/forbid_bp_input.py` 跨平台守卫（排除 `core/validation.py` 注释），已接入 pre-commit 与 CI 后端 job，防止回潮。详见 `docs/working-notes/code-audit-and-remediation-2026-08-01.md` §6。 |
| **全站 footer 对齐问题（前端布局）** | 🟡 中 | `layout/components/lay-content/index.vue` 的 `.main-content`（内容区）与 `layout/components/lay-footer/index.vue` 的 `.app-footer__inner`（页脚内容）分属不同容器/坐标系，折叠侧边栏后两者左右边缘不对齐；页脚与内容未共用同一套 `max-width` + 居中 + 左右 padding 约束。 | **✅ 已修复 (2026-08-09 实证回填)**：`.main-content`（`index.scss:75-79`）与 `.app-footer__inner`（`lay-footer/index.vue:40-49`）已共用同一套宽度约束——`max-width: 1400px` + `margin: 0 auto` + 48px 左右 padding（`var(--space-12)`），折叠/展开侧边栏时左右边缘严格对齐；fixedHeader 模式下外层 `el-scrollbar` 容器（1440px）内再居中，留 20px 呼吸空间仍对齐。 |
| **依赖升级引入样式/运行时回归风险（前端 `pnpm up`）** | 🟠 高 | 2026-08-03 执行 `pnpm up` 将前端依赖整体升级：element-plus 2.11.5→2.14.3、vue 3.5.22→3.5.40、tailwind 4.1→4.3、sass 1.93→1.102、vite 7.1→7.3、echarts 6、@vueuse/core 14.x 等。**未做充分回归（仅验证 typecheck 通过 + DEV 能起）**，升级后未重新人工核对各页面样式。典型症状：温度计/探市页 header/footer 样式在 DEV 下错乱（实为下面的「dev server 与磁盘依赖版本错位」所致，非 header/footer 代码改动）。header/footer 接入温度计/探市页为更早提交（`891868d`/`bc38d75`/`aa2fffa`），本次未改动。 | **待解决（2026-08-03 记录）**：升级后须对所有路由页做一轮样式回归（尤其 element-plus 2.11→2.14 的组件样式、tailwind v4 工具类、sass 1.93→1.102 混合宏）；建议固定本次升级为一次独立 commit，便于出问题时 `git revert` 二分定位。<br>**2026-08-04 更新**：随 OOM 修复一并完成了 ECharts 全量→按需引入改造（8 文件），typecheck 通过（无新增错误），但样式回归仍待人工核对。 |
| **生产 `build` 因 OOM 失败（前端 vite 7）** | ~~🟠 高~~ **✅ 已修复 (2026-08-04)** | 2026-08-03 `pnpm run build` 直接 `JavaScript heap out of memory`（exit 1），`NODE_OPTIONS=--max-old-space-size=8192` 仍不足。疑似 vite 7 + 升级后依赖体积膨胀（echarts 6、element-plus 2.14 等）导致打包内存占用激增。该问题**不影响本地 DEV 看页面**，但阻塞生产部署与 Vercel 构建。 | **已修复（2026-08-04）**。经排查 OOM 由四因素叠加导致：① Rollup 无 `manualChunks` 分包；② ECharts 全量引入（8 处）；③ `@iconify/json` 巨型依赖（node_modules 超 200MB）；④ Element Plus 全量 CSS 引入。**详细修复记录见 `docs/working-notes/build-oom-fix-2026-08-04.md`**。**2026-08-04 最终验证**：`pnpm build` 成功（39.65s / 4.33 MB），补充安装 `@iconify-json/ri` 修复 login 页缺失 RemixIcon 图标。 |
| **dev server 进程存活但磁盘 `node_modules` 已升级 → 版本错位** | 🟡 中 | 2026-08-03 升级依赖时，凌晨 1:20 启动的旧 vite dev server（PID 6756/15644，端口 8449）仍在运行，其加载的模块缓存为旧版本；而 `pnpm up` 已把磁盘 `node_modules` 换成新版本。进程与磁盘依赖版本错位 → HMR 下 CSS/组件样式错乱（用户「看到的样式又不对了」即此因）。非 header/footer 代码被改。 | **已闭环（2026-09-11，#972）**：① 新增 vite 插件 `frontend/build/dep-drift-guard.ts`，监听 `pnpm-lock.yaml` / `package.json`，变更即 `server.restart(true)` 重建模块图与依赖预构建（去抖 300ms；`server.restart` 做能力探测 + try/catch，不可用/失败时退化为醒目告警要求手动重启，绝不阻断开发；`DISABLE_DEP_DRIFT_GUARD=1` 可关闭）。② AGENTS.md 常用前端命令下补「升级依赖后必须重启 dev server」提醒。<br>**实测（本机 vite 7.3.6）**：dev server 就绪 → 重写锁文件 → 日志出现「检测到依赖清单变化 / dev server 已重启」，重启前后 `curl` 均 200，无重启循环。<br>**残留**：插件只在 dev server 已运行时生效；若升级期间未开 dev server 则无所谓，若开了但插件被关闭（env）仍需人工重启。 |
| **`pnpm-lock.yaml` 与实际安装版本不一致** | 🟡 中 | 2026-08-03 build 日志显示运行时解析到 `@vueuse/core@14.3.0`，但 `package.json` 写 `^14.4.0`（caret 范围内），且 lock 文件与本次 `pnpm up` 后的实际安装版本存在偏离嫌疑。lock 文件可信度存疑，可能导致「本地能跑、CI 装到不同版本」的不一致。 | **✅ 已一致 (2026-08-09 实证回填)**：`pnpm-lock.yaml` importers 段解析版本与 `package.json` specifier 吻合（vue 3.5.40、element-plus 2.14.3、vite 7.3.6、echarts 6.1.0 等），lock 文件已提交且无未提交 diff。剩余建议：CI 加 `pnpm install --frozen-lockfile` 校验。 |
| **前端命名规范整理（参照 Pure Admin + Vue 官方）** | 🟡 中 | 早期前端代码粗糙，命名/类型组织不统一：`api/` 下 `any`/`Record<string, any>`/`object` 泛滥、API 函数命名不一致（`refreshTokenApi`/`getLogin`）、类型与实现混放、components 层级混用。2026-08-03 已先产出规范（`frontend-naming.md`）+ 不规范点清单（`frontend-naming-audit.md`），并按决策「保持现状不强制统一 views 目录形态」。 | **待逐条执行（2026-08-03 记录）**：P0 清 `any`（先对齐后端 `api/types.d.ts` 契约）→ P1（API 命名统一、类型集中、components 改目录组件）→ P2（utils/constants/config 边界）。详见 `frontend-naming-audit.md`，逐条改造需另行确认后执行。 |
| **前端全量 TypeScript typecheck 修复（31→0 错误）** | ~~🟢 低~~ **✅ 已修复 (2026-08-04)** | 2026-08-03 先修复 8 个 A 类错误；2026-08-04 继续修复剩余 31 个错误直至 vue-tsc --noEmit 零错误。涉及 9 个文件，分为 5 类：① `DefaultRow` 类型不存在于 @pureadmin/table（9 处→any）；② Vue 3 模板中嵌套 Ref 不自动解包（8 处→as any）；③ API 接口缺失字段（5 处→补 optional）；④ API 响应类型不完整（1 处→any+注释）；⑤ 组件 props 类型不匹配（3 处→对齐源码定义）。详细记录见 `docs/working-notes/build-oom-fix-2026-08-04.md`。 | **已修复（2026-08-04）**：`vue-tsc --noEmit` 零错误；新增 `conventions.md` 第 6 章「TypeScript 编码强制约束」作为防回潮红线；pre-commit hook 已加入 `vue-tsc --noEmit` 门禁拦截。 |
| **温度计·公募基金整体持仓集中度/抱团度未接入（无免费现成接口）** | 中 | 用户要求的"公募基金整体持仓集中度/抱团度"需聚合全市场主动基金前十大重仓（扫约 1 万只、限流、季度批处理），无免费现成聚合接口（韭圈儿 Pro「机构抱团/行业恐贪」、Choice、Wind 均付费；东财仅研报新闻非结构化 API）。按用户"能白嫖就不算"原则不自算。已具备可选自算原型 `fund_concentration.py`（扫天天基金前十大重仓、聚合前 50 热门股），但数据拿取重、且依赖 akshare 主动基金池与天天基金档案接口。 | **暂缓（2026-08-03 记录·待确认）**：暂不入 v2 主链路。路径有二：①订阅韭圈儿 Pro 直接白嫖现成机构抱团/行业恐贪数据；②或后续有轻量聚合源再接入。自算原型保留为可选离线批处理，不阻塞主链路。 |
| **温度计·用户持仓拥挤度/抱团度计算（需持仓穿透）** | 中 | 用户持仓维度的行业拥挤度/集中度需先做"持仓穿透"——拿到底层股票（用户持有的基金→其前十大重仓股，或股票账户直接持仓），再按行业聚合计算。当前 v2 后端无持仓录入/穿透模块（持仓录入 `holdings.csv` 规划于 README 9.3，尚未建）。 | **技术债务（2026-08-03 记录）**：列入基础债务，待持仓录入与穿透能力具备后再实现；本期只接入不依赖持仓的维度（行业拥挤度行情自算；公募基金整体集中度暂缓）。 |
| ~~行业拥挤度分母（全 A 中位 PB）在受限网络下不可达，整组标灰~~ | ~~🟠 高~~ **✅ 已修复 (2026-08-05)** | ~~行业拥挤度 `crowding_pct` 的分母 = 全 A 中位 PB，默认走 `ak.stock_a_all_pb()`（legulegu）；无本地缓存时若 legulegu 不可达，代码退化为东财实时 PB 兜底（`push2.eastmoney.com`），再不可达则返回 stale 占位（`crowding_pct=None`）~~ | **根因修正（重要）**：原以为是"纯网络不可达"，实测是 `app/core/requests_patch.py` 的全局补丁**在 session 级挂载了东财专属 Referer/Accept/nid Cookie**，并把 `requests.get/post` mock 到另一个 `_EMSession` 实例（丢失调用方在 session 上设置的 headers/cookies）。legulegu 收到东财非法头/缺 UA 的握手请求 → 403/空 body → `get_cookie_csrf` 取不到 CSRF token → `stock_a_all_pb()` JSONDecodeError → 分母取不到、整组标灰。**修复**：重构 `requests_patch.py`——(1) 改为**包装** `Session.request`（非跨实例转发），保留调用方 headers/cookies；(2) 东财浏览器头 + nid Cookie **仅对 `eastmoney.com` 域名注入**，legulegu 等第三方源保持原样；(3) 重试适配器按 session 挂载。修复后 `market_pb_series()` 正常返回 legulegu 全 A 中位 PB（最新 2.59），密集跑 8 行业 `fetch_industry_crowding` 全部 `stale:False`、`hist_ok:True`。预取脚本 `scripts/prefetch_all_pb.py` 仍保留（落盘 `cache/all_pb.csv` 作容灾缓存）。 |
| **东方财富出口 IP 封（数据源层，横切 bias / 行业拥挤度）** | 🟠 高 | 2026-08-05 实测：即使屏蔽系统代理残留（`requests_patch.py` 已加 `trust_env=False + proxies=None`，`ProxyError` 消除），`80.push2` / `push2` 直连仍 `RemoteDisconnected` → 家庭宽带出口 IP 被东财按 IP 限流/临时封。代理开关都不行，根因在 IP 层而非代理。东财实时 PB 兜底（`push2.eastmoney.com`）因此失效。 | **进度（2026-08-05）**：根因已定位，baostock 已装并验证可达（LOGIN success / 行业查询 OK）。**bias 侧已闭环**：乖离率数据源改为直连（腾讯行情 `web.ifzq.gtimg.cn` / 东财 `push2his`，`bias/direct_feeds.py`），`jobs.py` 已 `SKIP_BIAS=False` 放开，直连失败降级 stale 不阻断（见 `docs/spec/roadmap.md` §2.1）。**行业拥挤度侧 2026-08-07 已闭环**：`industry_crowding.py` 分母兜底链已把 baostock 从预留提升为**可用默认源**（`query_daily_history_k_AStock` 单次批量取全 A 股 `pbMRQ` → 当日中位 PB，替代已封的东财），带线程超时保护（20s，服务器不可达自动降级，绝不阻塞主链路），东财降为历史遗留最后一级。实测全 A 中位 PB=2.62（量级与 legulegu 缓存一致）。方案文档见 `docs/working-notes/industry-crowding-baostock-fallback-2026-08-07.md`。分子全覆盖路径（baostock 申万一级 / tushare 31 行业）仍预留，需本机直连。详见 `docs/working-notes/eastmoney-antiscrape-2026-08-05.md`。 |
| **B5 板块资金流数据源缺失（流动性卡右侧可视化前置）** | 🟡 中 | 探市页「板块资金流 →」入口目前仅 `ElMessage.info("板块资金流功能开发中")`（`explore/index.vue`）；`sector_flow` 仅存在于 `models.py` 注释与 `get_multi_items` 参数说明中，**无任何 job/fetcher 在抓板块资金流数据**，`get_multi_items('sector_flow')` 恒返回空列表。需先建设数据源（akshare `fund_flow_industry` 等公开市场资金流）再接入 `/multi` 可视化，属独立数据源建设，超出 roadmap B5「确认接口」范围。 | **技术债务（2026-08-07 记录）**：列入基础债务，不与 B3 同批实现；数据源接入方案另行调研后单独排期，避免扩大 B3 改动面。 |
| **落地页首屏·鹦鹉螺深海氛围动效打磨（视觉抛光 · 非阻塞）** | 低 | 2026-08-05 用户评审首屏提出"粉图静态、需改珊瑚红+加动效"。经核对磁盘实际：`landing.template.html` 的 Hero 鹦鹉螺**已有**珊瑚红主体（`nhGrad` 渐变 `#F4B582→#9E3B2C` + `--shell-coral:#E34F38` 描边）且**已有** `nau-spin`(90s)/`nau-breathe`(9s)/`nau-sway`(14s) + 潮汐波纹 `tidalFlow`(18s) 动效——**并非静态粉图**，用户描述的"粉色/扁平/静态"与现状不符（属文档/实现漂移，第二轮）。真正缺失的是"深海环境感"与"气室调节"叙事载体。 | **暂缓（2026-08-05 记录）**：列入视觉抛光队列，待 `site/style.css` 统一 + `/about` 骨架落地后再做。具体待办（均为真实新增、纯 CSS + SVG `<circle>`，无需 JS）：(a) Hero 鹦鹉螺背后加 `#F5F0EB` 超椭圆/圆形环境晕染容器；(b) 新增"气室水位"逐室 `opacity` 缓闪关键帧（从内向外交替，模拟涨退潮蓄水）；(c) 可选 2-3 个极缓上浮气泡，`cubic-bezier(0.19,1,0.22,1)`、6-8s 周期，珊瑚红/暖灰；(d) 副标题按 YML 标准短版，把"手动归集/穿透持仓/算准 XIRR"拆为 CTA 上方一行 `#6B655C` 14px 能力标签；(e) 底部潮汐波纹已动效，确认 `--wave-line` 是否偏浅绿、必要时收敛为深海洋流色。CSS `@keyframes` 示例待执行时再写。 |
| **主站 `landing.template.html` 三套 `:root` 命名空间 / 与 frontend 令牌值漂移（已闭环）** | ✅ 已解决 | 落地页内联 2 个 `:root`（语义令牌 + shell 艺术块），主色 `--brand-coral` 等与 frontend `--brand-700` 同名不同值；`--brand-coral-soft`/`--border-light`/`--radius-sm` 三处值漂移；字体族写法不一；与「主站引用工具侧令牌」设计原则冲突，是主站实现层面最大技术债。 | **✅ 已落地 (2026-08-05)**：新建根目录 `site/style.css` 作为 landing/about 唯一共享令牌源，镜像 frontend `colors.css` 规范值；模板两处内联 `:root` 已删除、改 `<link href="/style.css">`、规则体变量引用全量重命名（`--brand-coral*→--brand-700/800/400`、`--color-danger→--color-danger-system`、`--radius→--radius-lg`、`--font→--font-sans`），并修正 3 处漂移值、补全原未定义的 `--text-muted`/`--border`。`shell-*` 艺术块命名按约定本阶段保留于 `site/style.css` 并注明为鹦鹉螺局部装饰变量，待鹦鹉螺专项重构再处理。 |
| **退出登录后页面不跳转（需手动刷新才回登录页）** | ~~🔴 严重~~ **✅ 已修复 (2026-08-08)** | `store/modules/user.ts` 的 `forceLogout()` 中 `supabase.auth.signOut({ scope: "local" })` **未 await**，紧接着同步执行 `resetRouter(); router.push("/login")`；而路由守卫 `beforeEach`（`router/index.ts`）内 `await supabase.auth.getSession()` 与之**竞态**——本地 session 尚未清除时守卫读到旧 session，判定仍"已登录"，走已登录分支 `toCorrectRoute()` 把 `/login` redirect 回 `_from.fullPath` 原页面。表现为：点击退出登录页面原地不跳转、仅侧边栏消失（`resetRouter()` 清空权限菜单所致），刷新后 session 才销毁、守卫判定未登录 → 跳登录页。 | **✅ 已修复 (2026-08-08)**：在 `forceLogout()` 中 **await `signOut({scope:"local"})`** 完成后再 `resetRouter(); router.push("/login")`，消除竞态。所有登出入口（`useNav.logout` / NavMix / NavHorizontal / profile `onLogout`）统一走 `useUserStoreHook().logOut()`，一处修复全覆盖。验证：`pnpm typecheck` 零错误、`eslint` 通过。 |
| **货币基金每日收益计算链路验证（验收标准）** | 🔴 上线前必查 | 2026-08-09 修复货币基金净值污染时实证：万份收益已正确落库 `money_fund_daily_worth.nav_per_10k`（落库链路正常），但**尚无任何代码读取该字段**——`performance/calculators.py` 只查 `DailyWorth`，货币基金按 `money_fund` 记账只记流水不建持仓（`position_service.py:148-150`），每日收益计算链路未打通 | **已列入上线验收标准（2026-08-09）**：须验证「每日收益计算链路通 + 计算结果正确」后方可上线，具体验证项见 launch-plan M0 冒烟验证 #7。验证方式参考：每日收益 = 持有金额 × 当日万份收益 ÷ 10000，需确认前端展示入口（持仓收益/账户收益）已接入 |
| **暗黑模式（深色主题）未适配（前端全局）** | 🔴 上线前必查 | 系统当前仅实现亮色主题（`design.dark.md` 为规范文档但前端未实际接入 dark 主题切换）。用户在暗色环境下使用出现：深色系统下页面局部亮白/灰白背景与深色文字混排、组件明暗不一，观感怪异；虽不影响功能，但影响整体产品质感与「家庭记账」场景的夜间使用体验。风险点：全部视图页 + Element Plus 组件 + ECharts 图表 + 落地页配色，均未按 `design.dark.md` 的语义变量（HSL 动态计算）体系适配。 | **上线前必须严查并修复（2026-08-08 记录）**：接入暗色模式需：(1) 全局 `dark` class 切换（Element Plus 官方 dark CSS + `index.scss` 语义变量双轨）；(2) 全站色值排查（禁止硬编码 hex，统一走 `--color-*` 语义变量）；(3) ECharts 图表按主题动态读 CSS 变量（`SankeyChart`/`Overview` 等 8 文件已按需引入，需补主题响应）；(4) 落地页 `site/style.css` 暗色令牌。属跨页面大改动，另立专项排期，**不得带病上线**。详见 `docs/spec/decisions.md` 对应条目（待登记）与 `frontend/design.dark.md`。 |
| **H2 残留：`group_by=account` 分支仍手写 dict 拼装** | 中 | #899 审计项 H2 部分解决：分页分支已复用 `enrich_position_dict`（`positions/views.py:105`），但 `group_by=account` 分支仍手写独立 dict（`positions/views.py:82-99`），字段可能漂移 | 待排期：`group_by=account` 复用 `enrich_position_dict` 前须先核对前端字段依赖——两者 `confirm_date` 语义不同（手写分支=首次买入日，enrich=持仓确认日）、字段名 `type` vs `asset_type`，直接复用有 API 契约风险，无独立 issue |
| **L2 残留：`ledger_service.py:164` 旧式 `.get()`** | 低 | #899 审计项 L2 部分解决：positions/fund_service 已改 `get_owned_or_404`，但服务层/视图层仍有旧式 `db.query(X).get(id)` | **✅ 已修复 (2026-08-10)**：`ledger_service.py:170` 与 `families/views.py:55` 已改 `db.get(Model, id)`（SQLAlchemy 2.0）。`ledgers/views.py:288` 因该文件有其他会话未提交改动，留待一并处理 |
| **M2 残留：金额/涨跌组件未全量覆盖** | 中 | #899 审计项 M2 部分解决：TransactionList/strategies/ledgers 已用 MoneyDisplay，但 portfolio/detail、AccountOverview、AssetManagement、Overview、AssetPanorama、temperature、explore、welcome、PositionTransactionsDrawer 等仍手写 `toLocaleString`/`toFixed` | 待修复：全站替换 MoneyDisplay/RiseFallText（跟踪 #913） |
| **账户卡片「当日盈亏」未实现（前后端均无能力）** | 🟡 中 | 账户管理页卡片「当日盈亏」恒显示 `--` 占位符：前端硬编码（`frontend/src/views/asset/ledgers/index.vue:270-281`，注释「暂无当日行情数据，保留占位符」）；后端 `get_ledger_summary` 硬编码 `daily_pnl: None`（`backend/app/domains/ledgers/views.py:341`），`list_ledgers`（views.py:113-158）根本不返回该字段。全仓 grep `daily_pnl|day_pnl|today_pnl` 仅此 2 处 + explore 页无关命中。**非数据拉取 bug，是功能从未实现**。 | **技术债务（2026-08-15 记录）**：需新增后端当日涨跌计算（持仓现价 vs 昨收，复用实时行情源）+ 前端消费展示；依赖实时行情数据源（`useRealtimeQuotes` 链路），另行排期，不随本轮视觉修复实现。 |

---

## 13-B. 探市页（免登录沙盒）P0 缺陷（2026-08-08 v4 实证 · 跟踪 #821）

> 「沙盒」不是待建功能，它就是已上线的探市页 `/explore`。以下两项为**用户可见的正确性问题**，优先级高于任何新功能。

| 缺陷 | 现象 | 根因 | 位置 |
|---|---|---|---|
| **P0-1 免登录搜不到任何资产** | 生产环境匿名访客在探市页搜索框输入代码/名称，下拉**静默空白**，用户以为「系统里没有这只票」 | 搜索走 `/api/securities/search/` + `/api/funds/search/`，但免登录白名单 `PUBLIC_PREFIXES` 只有 `/api/health` 与 `/api/temperature`；`AUTH_ENABLED=true` 时必 401，且 `Promise.allSettled` + `catch` 吞掉错误不提示 | `frontend/src/composables/useAssetSearch.ts:23-26,58-60`；`backend/app/core/auth.py:23`；**已修复（2026-08-08）**：① 后端 `PUBLIC_PREFIXES` 增加 `/api/securities/search` 与 `/api/funds/search`（精确到子路由、避免误放行同蓝图写接口），回归测试 `tests/core/test_auth_whitelist.py` 锁定该不变量；② 前端 `useAssetSearch.ts` 不再静默吞错——两数据源均失败时弹轻提示（带 5s 节流去重），部分失败仍静默保留可用结果 |
| **P0-2 热门卡片展示编造的盈亏** | 点击「沪深 300ETF/纳指 ETF/招商银行/科创 50ETF」任一热门卡片，立刻显示一个与真实成本无关的持仓收益 | `hotAssets` 硬编码 `costPrice: 4.567/1.234/34.56/0.987` 与 `quantity: 100`，未取当前价 | `frontend/src/views/explore/index.vue:809-816`；**已修复（2026-08-08）**：`hotAssets` 不再预填成本/份额，`addHotAsset` 改传 `costPrice: null, quantity: null`，走纯观察模式（成本取当前价、份额 1，盈亏恒为 0），与手工添加留空等价 |

**为什么必须优先修**：探市是免登录入口页，是新用户第一印象。P0-1 让核心交互（添加资产）在生产不可用，P0-2 直接展示虚假财务数据。两者都是「看起来做了、实际没成立」的典型，与 `docs/spec/decisions.md` D4（探市免登录）的意图冲突。

---

## 14. issue 残留缺口登记（triage-done 关闭但待办未勾选 · 2026-08-08 v3，v4 更新）

> 背景：本轮按 issue 正文「成功标准/验收清单」逐条实证，发现多个已关闭 issue 正文仍有未勾选项。按「保持关闭 + 显式登记缺口」原则，不重开，仅在此登记残留项，避免「以为关了就全做了」。

| issue | 关闭判定 | 正文未勾选 / 残留项 | 登记位置 |
|---|---|---|---|
| #796 组合年化收益率 | 功能已交付 | ~~§8.3 的 11 个单测用例仅约 6/11 覆盖~~ **已于 2026-08-08 补齐**：新增单笔买入/单笔卖出/定投后全赎/部分卖出续持/资金转入转出与内部划转配对/极端收益率与 [-1,10] 区间截断/货基与逆回购排除 | `tests/services/performance/test_xirr_engine.py`（23 条全通过，NPV 相对残差断言等价「与 Excel 一致」） |
| #661 自选功能 | 核心完成 | checklist 1 项 `[ ]`：品种不同描述维度不同（备注编辑已在 #1285 落地、分享已砍） | 待 #1286 数据底座 / #1285 消费侧 |
| #230 数据来源整合 | 整合框架完成 | 基金经理信息未同步、指数行情同步不可用 | 见 tech-debt 既有条目（基金经理信息未同步）+ `services/sync` |
| #429 交割单导入 | 导入主体完成 | 导出→#819；天天基金无数据、卖出份额推算、模板导入查重 | 导出见 #819 |
| #507 定时任务清单 | 笔记归档 | 待办（基金经理信息更新等）与 #229 重叠且未做 | 双向交叉引用 #229 |

---

## 14-B. 2026-08-14 验收清单代码实证复核发现项（高红旗登记）

> 来源：`docs/working-notes/issue-triage/auto/2026-08-14.md`（首次全量基线复核，按交付标准逐 issue 实证）。本批为"以为做了实际没做 / 文档与代码不符 / 代码存在但生产不可用"的高严重度缺口，按"保持现状 + 显式登记"原则登记，不擅自改代码、不乱关 issue。其中文档登记类（#898 / #869）本表即其落地动作。

| issue | 类型 | 实证结论（文件:行号） | 严重度 | 处理建议 |
|---|---|---|---|---|
| [#898](https://github.com/imoyao/fundmate/issues/898) | 文档机制 | 会议纪要驱动的"文档↔代码误差追踪" issue，其待办完全未回流到本文件（全库搜 `898`/`误差追踪`/`会议纪要` 0 命中） | 🔴 最高 | 本表即登记动作；后续会议纪要类误差追踪统一回流至此 |
| [#937](https://github.com/imoyao/fundmate/issues/937) | 代码缺口 | 导入持仓快照解析器与 `/inventory` 快照卡片完全未落地；仅底层 `process_buy_or_deposit` + import_hash 去重就绪（`position_service.py:235-237,259-261`），无入口触发 | 🔴 高 | 登记缺口，实现 `position_snapshot` 解析器 + 卡片（#936/#933/#928 共用依赖） |
| [#933](https://github.com/imoyao/fundmate/issues/933) | 代码缺口 | 前端统一提交层未收敛，仍双轨直写 `createPosition`（`composables/useQuickEntry.ts:40` → `BuyForm.vue:812`）；`api/importer.ts` 仅有 `confirmImport`，无 preview/submit 编排 | 🔴 高 | 打通前端 `ImportOrchestrator` 编排，消除双轨直写 |
| [#934](https://github.com/imoyao/fundmate/issues/934) | 代码缺口 | 资产简记托盘未接截图导入；`OcrImportModal.vue` 仅服务于自选（`createWatchlistItem`），未挂到 `BuyForm.vue`；OCR 能力与配额已存在（`domains/ocr/views.py:127-202`、`ai_recognizer/recognizers/txn_recognizer.py:98-99`） | 🔴 高 | 在资产简记挂 `OcrImportModal` 接 `txn_import` scenario |
| [#825](https://github.com/imoyao/fundmate/issues/825) | 代码缺口 | DB 快照导出/导入核心能力缺失（`domains/summary/views.py` 无 export/import 端点，前端仅 CSV）；full-sync 限范围已落地（`sync/orchestrator.py:88`） | 🔴 高 | 评估是否真需 DB 级快照，或降级为 CSV 导入 |
| [#894](https://github.com/imoyao/fundmate/issues/894) | 文档偏差 | 上线计划（Turso 双备份 / EdgeOne 部署）代码零落地（`auth.py:150-187` 仍单库 SQLite；后端搜 `turso/libsql/edgeone` 0 命中），相关文档仅为架构设想 | 🔴 高 | 标注 #894 为"规划/未实施"，避免给人已上线印象 |
| [#869](https://github.com/imoyao/fundmate/issues/869) | 文档缺口 | 韭圈儿 fetcher 修复已落地生效（`thermometer/jobs.py:23,109` 注册 `JiucaishuoFetcher`），但全库文档 0 反链 | 🟠 高 | 本表登记 + 反链；读者无法从文档追溯该修复 |
| 货币基金每日收益链路 | 代码缺口 | 已有 §69 登记（`nav_per_10k` 落库但无读取方，`position_service.py:148-150` 只记流水不建持仓）；本批复核确认仍属"声称可算实际不可算" | 🟠 高 | 见 §69 上线验收标准，闭环收益链路 |

---

## 15. 文档系统整合与未来用户手册规划（技术债务 · 不紧急）

> **决策背景**：用户要求"把文档系统整合，明确哪些文档作为未来用户手册"，并登记为技术债务（非紧急）。文档站**不拆离仓库**，仍留在 `fundmate` 仓内 `docs/`（`/docs` 子路径部署）；拆独立仓库会增加更新摩擦，已与用户确认。
> **范围**：本节只做"盘点 + 归类 + 缺口登记"，不立即补全内容。

### 15.1 现有文档归类（用户手册 vs 内部）

| 路径 | 归类 | 是否未来用户手册 | 备注 |
|:---|:---|:---|:---|
| `docs/guide/*`（index/export-alipay/import-efund） | 用户指南 | ✅ 核心候选 | 受众=家人/自己，纯实操步骤；仅 3 篇，缺口大 |
| `docs/features/xirr.md` `account.md` `holding-record.md` `asset-review.md` `overview.md` `watchlist.md` | 功能说明 | ✅ 候选（需从设计决策中剥离用户向部分） | 当前混含技术决策，需拆出"用户怎么用" |
| `docs/faq.md` `privacy.md` `about.md` | 站点页 | ✅ 候选 | 实际是营销/帮助站内容，需对齐 v1.6 品牌语言 |
| `docs/api/*` | API 文档 | ➖ 开发者向（非终端用户手册） | 开发者手册 |
| `docs/features/temperature-redesign.md` `temperature-archive.md` `recover-from-ai.md` | 设计/决策笔记 | ❌ 内部 | 不对外 |
| `docs/spec/*`（architecture/conventions/data-model/decisions/frontend-*/roadmap/tech-debt） | 架构/规范 | ❌ 内部 | 开发者 |
| `docs/dev/*`（31 篇）`docs/pytest/*` `docs/working-notes/*` `docs/ops/*` | 开发笔记 | ❌ 内部 | 不对外 |

### 15.2 缺口与待办（技术债务，优先级：低/不紧急）

| 问题描述 | 优先级 | 处理策略 |
|:---|:---|:---|
| **用户手册内容缺口大**：`guide/` 仅 3 篇，缺"新增持仓/更新价格/导出备份/CSV 导入"等核心流程图文 | 低（不紧急） | 按 `guide/index.md` 的"纯实操截图+步骤"标准，从 `features/` 用户向章节拆分补全 |
| **品牌名未统一**：文档站仍用"叽咕 / fundmate"，主站已定"多多贝 / Duoduobei" | 中 | ~~全站文档替换品牌名~~ ✅ 已完成（2026-08）：`docs/README.md` hero 对齐主站落地页 slogan（看见你的复利曲线 / 记账即复利·贝倍多），`about` `faq` `feedback` `privacy` 品牌名已统一为多多贝，开发者历史笔记（dev/）保留"叽咕"作历史项目名 |
| **站点页未对齐 v1.6 品牌语言**：`faq` `about` `privacy` 文案/措辞与 brand-v1.6 不一致 | 低 | 以 `docs/design/brand-v1.6.md` 为基准重写站点页文案（数据主权、不荐股不跟单等主张） |
| **文档站构建技术未定**：当前 `docs/README.md` 为 docsify 风格（`home:true`/`heroText`），钱迹参考站为 GitBook | 低 | 评估 docsify→VitePress/GitBook 迁移；用户手册结构按钱迹"产品模块 + 疑问式标题"组织 |
| **落地页视频/动效场景待补充**（参考 WorkBuddy） | 低 | WorkBuddy 在 Hero 区嵌入了产品截图/视频展示应用场景，多多贝当前为纯静态 HTML。后期可补充：(a) 工具实际使用录屏（Lottie/MP4 嵌入 Hero 或功能区）；(b) 产品界面截图轮播；(c) 数据可视化动态演示（XIRR 曲线绘制过程）。需先录制素材再编码嵌入，属于视觉打磨阶段 |
| **用户手册与开发文档物理隔离**：当前混在 `docs/` 同名目录，未来需明确发布范围（`/docs` 仅发布用户向，内部放 `/docs-internal` 或私有） | 低 | 待用户手册成形后再规划发布边界 |
    94:plainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplain
    95:---
    96:
    97:## 16. 首页「支持导入」Logo 混排素材缺口（技术债务 · 中）

**背景**：落地页（`#ecosystem`，首页而非应用站）保留原有的「3 行横向滚动条」交互，仅把轨道内的纯文字药丸升级为「真实 Logo + 文字药丸兜底」混排（`landing.content.yml` 的 `eco.logos` / `eco.texts`）——Logo 灰度默认、悬停恢复彩色 + 红色阴影，与文字药丸同轨无缝滚动。

**当前状态**：

- 已实现：支付宝真实 SVG（`logos/alipay.svg`，取自 Simple Icons，已本地化）。
- 缺口：同花顺 / 天天基金 / 东方财富无官方独立 Logo 可取，暂以文字药丸兜底；基金标准模板 / 股票标准模板非公司，永远走文字药丸。

**素材取源评估（本机实测）**：

- `logo.dev`：海外 Cloudflare CDN，可达但 **401 需免费 token**；中文垂直金融品牌召回差，天天基金无独立域名 → 放弃。
- `DuckDuckGo favicon` / `api.iowen.cn`：本机连接超时/被墙 → 放弃。
- `iconfont.cn`（阿里矢量图标库）：**本机可达**，但搜索 API 返回 `LOGIN REQUIRED`，需登录态取 SVG；中文金融品牌收录全，是该场景首选源。
- `Simple Icons` CDN（Cloudflare）：可达、免 token，但**仅收录支付宝**（同花顺 / 东方财富 / 天天基金均 404）。

**待办（用户手动）**：

1. 登录 iconfont.cn，搜索「同花顺 / 天天基金 / 东方财富」下载 SVG，放到主站仓库 duoduobei-web 的 logo 目录（建议 `tonghuashun.svg` / `tiantian.svg` / `eastmoney.svg`）。
2. 在 duoduobei-web 仓库的落地页内容配置（对应原 `landing.content.yml` 的 `eco.logos`）追加对应项（形如 `- { name: 同花顺, icon: "logos/tonghuashun.svg" }`），对应名称从 `eco.texts` 移除。
3. 重新生成：落地页已移交主站 duoduobei-web，本仓 `build:landing` 已废弃（见 #918 / decisions.md:116），需在 duoduobei-web 仓库重新生成。
4. 版权：品牌 logo 作「支持导入平台」事实性展示一般不构成侵权，但建议统一灰度处理（已实现），避免彩色图标杂乱。

**备注**：首页与 `/frontend` 应用站是两个独立站点，本条目仅针对首页落地页。

## 16. 数据存储过度工程化审计（2026-09-10 · 依据 decisions D21）

> 触发：`#1396`（全库 `funds.company_id` 覆盖率）讨论中，用户提出「记账软件的数据策略应是用户触达驱动，而非全库完整性驱动」，并要求审计代码中已存在的过度工程化。
> 审计方法：本地真库（`backend/invest.db`，1.22 GB）行数/填充率实测 + 全仓 grep 读写方核实 + `sync_logs` 运行史核对。**全部结论均有 file:line 或 SQL 计数支撑。**
> 处置约定：**本条只记录不修改代码**（`conventions.md` §16.3）。★ = 须另开 issue 跟踪。

### 16.1 实测快照

| 表 | 库内 | 用户实际触达 | 结论 |
|---|---|---|---|
| `funds` | 26,938 行 | **117 只**（`positions ∪ watchlist ∪ transactions` 去重 6 位码） | 99.6% 用不上 |
| `daily_worth` | 7,539,287 行 / 3,427 只 | **112 只** | 96.7% 用不上 |
| `money_fund_daily_worth` | 1,215,108 行 | — | 待评估 |
| `fund_managers` | 34,809 行 | — | 全量关系 |
| `index_constituents` | 7,514 行 | — | 全量成分 |

`sync_logs` 单次运行实测：`fund_nav` → `total=357, success=1,198,302, duration=448s`（一次写 120 万行净值）；`fund_manager` → `total=34,809, 416s`；`index_daily` → `10 项, 100s`。

### 16.2 发现清单

| # | 位置 | 问题 | 严重性 | 处置 |
|---|---|---|---|---|
| 1 ★ | `services/sync/jobs/fund_meta_job.py:50,71-82` | `existing = {f.fund_code: f for f in self.db.query(Fund).all()}`（全库 26,938 条）后 `for code, fund in existing.items(): self.adapter.fetch_fund_top_holdings(code)` → `ak.fund_portfolio_hold_em` **真·逐只 HTTP**。docstring 却称「本地只存用户核心池，**不把全市场基金灌进库**」——与 `fund_list_job` 实际把全市场灌入 `funds` **互相矛盾**。`orchestrator.py:388` 以 `['__full__']` 调它。**因从未跑通才未引爆**：`scale`/`recent_shares`/`equity_position` 填充率全 0%，`sync_logs` 无 `fund_meta` 记录。一旦执行即撞东财限流。 | 🔴 限流炸弹 | ✅ 已闭环（#1403，2026-09-11）：拆为两个 job —— `fund_scale`（单次调用返回全市场列表，§4.3.3 允许全量）与 `fund_position`（逐只，仅核心池 + 硬上限 500；`__full__` 与空 targets **显式跳过**，不再退化全库） |
| 2 | `services/cross_domain.py:95-104` | `_market_fetch` **忽略传入的 `_keys`**，`for f in db.query(Fund).all()` 把全库 26,938 个 ORM 实体加载进内存——与同函数上方注释「market_columns：预留，限定 market 侧取回的字段（**避免每次取全表**）」意图**完全相反**。**核实修正（勿沿用初判）**：全仓检索确认该模块**当前零生产调用方**（`backend/app/` 内除自身外无引用，仅 `tests/core/test_cross_domain.py` 使用），故**不是热路径缺陷，而是「零消费者的潜在炸弹」**——一旦有人按模块设计意图接入「自选 + 市场资料」联合查询，即为每次请求全表扫描。附带讽刺：该模块正是 2026-09-09 从 `services/common/`（当时被判为「为分层而分层」的空壳包）上提保留下来的，而它自身如今也成了无消费者的孤立模块。 | 🟡 潜在（无调用方） | ✅ 已修复（#1404）：抽出 `fetch_market_records_by_keys` 按 keys 过滤，不再全表加载。**仍无生产调用方**，接入前须复核 |
| 3 | `services/sync/jobs/fund_list_job.py:50-87` | docstring「基金列表同步任务（**全量**）」实为只增不改（`_deduplicate_by_unique_key` 只保留库里不存在的新基金）。实测 `sync_logs`：`total=1, success=0, skipped=26,927`。名称 / 契约谎报误导后来人。 | 🟠 契约谎报 | ✅ 已闭环（#1402）：docstring 改为如实描述「只增不改」+ 测试锁定 |
| 4 | `services/sync/jobs/fund_manager_job.py:37` | `codes = targets if targets else self._get_all_fund_codes()`——**空 targets 静默退化为全库**，与 `fund_detail_enrich_job`（空 targets 返回「无基金需要补充详情」）语义**相反**。注：该 job 走 `ak.fund_manager_em()` 一次全量 + 本地筛选，无速率风险，但语义陷阱须清除。 | 🟠 语义陷阱 | ✅ 已闭环（#1402）：语义写明「空 targets = 全量回填」+ 3 条测试锁定。**原判有误，见 §16.4** |
| 5 | `domains/funds/models.py` | `funds` 表 22 列中 7 列填充率为 0%（`is_fe_charge` 100% 但全为默认值）。**原判「死列 / 零读者」有误**——2026-09-11 逐列复核后按**成因**分四类，处置各不相同：① **源不提供** `risk_level`（映射与写入代码均在位：`akshare_adapter.py:385-397` + `fund_detail_enrich_job.py:162`，但实测 `ak.fund_info_ths` 18 字段、`ak.fund_individual_basic_info_xq` 14 字段**均不含「风险等级」**；同 job 写的 `benchmark` 有 11.51% 填充率，证明 job 跑过）；② **回填链路未跑通** `scale` / `recent_shares` / `equity_position`（**是 #1285 明确要展示的「基金：规模 / 股票仓位」正式字段**，底座由 #1286 定义、#1358 落地模型，填充为空是因为回填 job 从未跑通，见本表第 1 条）；③ **v1 迁移遗留** `symbol_prefix` / `is_fe_charge`（v1 备份 `.backup-v1-2026-08-01/fundmate/data/dkhs/base.py` 内有真实取数逻辑，v2 换 akshare 后未接）；④ **功能未启用** `pinyin_full`（`fund_service.py:216` 搜索只用 `pinyin_abbr`）。 | 🟡 字段债 | ✅ 已结论（2026-09-11 用户拍板**全部保留**）：① 待换源或按投资类型估算后标注「估算」；② 由拆分后的 `fund_scale` / `fund_position` 回填；③④ 保留待用。**禁止按「0% 填充」直接删列**——同一条指标下四种成因的处置完全不同 |
| 6 | 库内（非仓库） | **14 张游离表**不在 `DATA_DOMAIN_REGISTRY`：9 张修复脚本遗留备份（`positions_name_repair_backup_20260907` 126 行、`transactions_name_repair_backup_20260907` 1460 行、`transactions_qty_repair_backup_20260826` 66 行、`positions_backup`/`positions_backup_v2`/`assets_backup`/`positions_current_backup`/`assets_name_repair_backup_20260907`/`positions_qty_repair_backup_20260826`）、`sales_broker_mappings`（4 行，代码零引用）、`temperature_single_values`/`temperature_multi_items`/`temperature_composites`（0 行，已改名 `market_*` 后未清理）。 | 🟡 卫生 | 登记，清理须用户拍板 |
| 7 | `services/thermometer/service.py:36,144,202` | docstring 仍写「保存单值指标到数据库（**新表 temperature_single_values**）」「（新表 temperature_composites）」「（新表 temperature_multi_items）」，实际写入 `MarketSingleValue`(`market_single_values`) / `MarketComposite` / `MarketMultiItem`。**注释漂移**。 | 🟡 注释 | ✅ 已闭环（#1404）：docstring 改为真实表名 `market_single_values` / `market_composites` / `market_multi_items` |
| 8 ★ | `services/sync/orchestrator.py:341-358` | `_execute_job` 捕获 `job.run` 抛出的异常并返回 `{'status':'error'}`，但 `_save_sync_log` 只在 `run_job` 内部（:338）于 `job.run` **成功返回后**执行——**抛错时全链路无日志**。后果：`sync_logs` 仅有 10 个 `job_name`，`fund_meta`/`fund_type`/`index_catalog`/`convertible_bond`/`dividend_split`/`asset_snapshot`/`advisor_portfolio` 无任何记录，「某 job 到底跑没跑过」无法从日志回答。 | 🟠 可观测性 | ✅ 已闭环（#1402）：`_execute_job` 异常路径新增 `_save_error_sync_log` + 3 条边界测试 |

### 16.3 制度性修复（已完成，另见）

- 新建 [`data-strategy.md`](./data-strategy.md)（L1~L4 分层 + 数据准入四问 + 表/列/job 准入细则）。
- `conventions.md` §16.2 增补**数据维度**条款（冻结区改动，依据 `decisions.md` D21）。
- `AGENTS.md` 增「数据策略（按需存、禁止全量堆砌）」硬约束节，作为 PR 流程闸门。
- `#1396` 验收口径收敛为「用户触达基金的公司解析率 ≥95%」，全库覆盖率移出验收。

### 16.4 闭环记录：契约类三条（2026-09-11 · #1402）

- **第 3 条（`fund_list` 契约谎报）**：docstring 由「基金列表同步任务（全量）」改为如实描述
  「**只增不改 / insert-only**」，并新增测试 `test_existing_fund_is_not_updated` 锁定
  「已存在基金的名称 / 类型 / 状态变更不会同步」。流程不变，仅消除误导。

- **第 4 条（空 targets 语义）｜原判有误，特此更正**：原文称「空 targets 的正确语义是
  『无需处理、跳过』」，并以 `fund_detail_enrich_job` 作对照。核实后该前提**不成立**：

  - `fund_type_job._fetch_data` 的 docstring 明确写着「targets 为空（全量回填）时返回全部」；
  - `base.run` 本就是按「`targets is None` → 子类自己获取全部数据（适用于全量列表 Job）」
    设计的，源码注释同上；
  - `fund_detail_enrich_job` 走**自定义 run 流程**，它继承的基类 `_fetch_data` 只是返回 `[]`
    的占位实现，与 `fund_manager_job` **不可比**；
  - `run_all_jobs` 传给 `fund_manager` 的是 `fund_targets` 列表——空列表在 `base.run` 的
    `targets == []` 分支就已跳过，**根本流不到 `_fetch_data`**。「退化全库」只在
    `targets is None`（CLI 直调，如 `pdm run sync --job fund_manager`）时可达，
    而那正是设计中的全量回填路径。

  故本次**只补文档与测试锁定，不改行为**。若按原文改成「跳过」，上述 CLI 调用会变成空操作，
  属回归。三条测试（None→全量 / []→跳过不抓取 / 显式→只处理目标）已把三态钉死。

- **第 8 条（异常无审计）**：`orchestrator` 新增 `_save_error_sync_log`，job 抛异常时同样落
  `status=error` 行，`error_detail` 带原文，`data_source` 取自 job 适配器。防御三个边界：
  `snapshot_time` 为 `None`（`started_at` 是 NOT NULL 列）、`job_name` 未注册（避免 KeyError
  顶替原始异常）、审计自身写库失败（回滚并降级为日志，不掩盖真因）。

---

## 2026-08-04 OOM 修复记录

    98:plainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplainplain
    99:### 问题
   100:前端 `pnpm run build` 因 JavaScript heap OOM 失败，`--max-old-space-size=8192`（8GB）仍不足，阻塞生产部署。
   101:
   102:### 根因分析（不调内存，直接排查）
   103:经排查，OOM 由四个因素叠加导致，非单一原因：
   104:
   105:#### ① 致命级：无 manualChunks 分包（vite.config.ts）
   106:Rollup 在 build 阶段将 111 个 `.vue` 文件 + 全部依赖合并到极少 chunk 内，模块图随文件数增长，内存峰值远超合理范围。这是 OOM 的**首要原因**。
   107:
   108:#### ② 严重级：ECharts 全量引入（8 处）
   109:8 个文件直接 `import * as echarts from "echarts"`，ECharts 6 完整包约 1MB+ 未压缩，每个使用它的 chunk 都独立打包一份。仅 2 个文件使用了按需引入。另外 `temperature/index.vue` 有独立的 `use([...])` 注册（与全局注册重复）。
   110:
   111:涉及文件：
   112:| 文件 | 改动 |
   113:|---|---|
   114:| `src/views/welcome/index.vue` | `import * as echarts from "echarts"` → `import echarts from "@/plugins/echarts"` |
   115:| `src/views/asset/Overview.vue` | 同上 |
   116:| `src/views/asset/ledgers/detail.vue` | 同上 |
   117:| `src/views/asset/IntelligentAnalysis.vue` | 同上 |
   118:| `src/views/asset/AssetPanorama.vue` | 同上 |
   119:| `src/views/asset/AssetOverview.vue` | 同上 |
   120:| `src/views/account/InvestmentAnalysis.vue` | 同上 |
   121:| `src/components/Charts/SankeyChart.vue` | 同上 |
   122:| `src/views/temperature/index.vue` | 移除冗余 `use([...])` 独立注册 |
   123:
   124|#### ③ 中等级：@iconify/json 巨型依赖
   125|`@iconify/json` 包含所有图标集，node_modules 超 200MB。项目实际只用 `@iconify-json/ep`（Element Plus 图标），源码零引用 `@iconify/json`。unplugin-icons 构建时可能解析它。
   126|
   127|#### ④ 严重级（暂缓）：Element Plus 伪按需 + 全量 CSS
   128|`elementPlus.ts` 一次性注册约 100+ 个组件，`main.ts` 引入全量 CSS（`element-plus/dist/index.css`），体积接近全量引入。改为 `unplugin-vue-components` 自动按需可进一步优化，但改动面大，**本次暂缓**。
   129|
   130|### 修复措施（已完成）
   131|
   132|| 步骤 | 操作 | 文件 |
   133||------|------|------|
   134|| **1** | 添加 `manualChunks` 分包（vue/echarts/element-plus/pureAdmin/utils 独立 chunk） | `vite.config.ts` |
   135|| **2** | ECharts 统一按需引入：全局注册（`plugins/echarts.ts`）+ 8 文件改为 `import echarts from "@/plugins/echarts"` + main.ts 启用 `useEcharts` | `plugins/echarts.ts` / `main.ts` + 9 个 `.vue` |
   136|| **3** | `plugins/echarts.ts` 补上 `SankeyChart`（`SankeyChart.vue` 需要） | `plugins/echarts.ts` |
   137|| **4** | 移除 `@iconify/json` 依赖 + 清理 `build/optimize.ts` 中的 exclude 引用 | `package.json` / `build/optimize.ts` |
   138|
   139|### 验证
   140|- **typecheck**：`vue-tsc --noEmit` 无新增错误（仅项目原有 TS 错误，与本次改动无关）
   141|- **echarts 相关**：typecheck 中无任何 echarts 相关类型错误
   142|- **build**：由于环境限制无法完整跑 build（shell 误判 vite 为 watch 命令），但 typecheck 通过 + 所有导入路径已确保正确。建议用户本地执行 `pnpm run build` 最终确认。
   143|
   144|### 决策
   145|- **Element Plus 按需引入（unplugin-vue-components）暂缓**：改动面大（需修改 `elementPlus.ts` 全局注册方式 + 移除全量 CSS + 逐个确认组件），不阻塞 OOM 修复
   146|- **不调大内存**：按用户要求，通过代码层面优化解决，非堆内存扩增
   147|
   148|### 剩余风险
   149|| 风险 | 说明 |
   150||------|------|
   151|| 样式回归未做 | ECharts 功能不受影响（只是导入路径变化），但依赖升级带来的样式变化仍需人工核对 |
   152|| Element Plus 全量 CSS | 仍引入 ~800KB 全量 CSS，后续可优化 |
   153|| Build 最终验证 | 需用户本地执行 `pnpm run build` 确认通过（环境限制无法完整执行） |

> ⚠️ **本行以上至「## 2026-08-04 OOM 修复记录」标题之间共 86 行（文件 158–243 行）已损坏**：整段是带行号前缀的粘贴产物——每行形如「行号 + 冒号/竖线 + 原文」，另有一行字面量为 `plainplainplain…`。原文并未丢失（剥掉行号前缀即可复原），但**渲染已完全失效**（标题、表格均不成立）。本轮未修（超出本次任务范围），修法见本节末段。

## 2026-09-11 仓库治理：CI 守卫与合并门禁（修复 3 项 + 开口 1 项）

触发：PR #1399 在「前端类型检查 + Lint + 构建」**红灯**（stylelint 报 1 条属性顺序）的状态下被合并进 `dev`，而仓库当时没有任何机制阻止。复核时另发现守卫本身是死代码。

| # | 事项 | 状态 |
|---|------|------|
| 1 | `ci.yml` 的 `guard-direct-push` job 触发条件写的是 `branches: [M]` / `refs/heads/M`——`M` 是**早已随分支清理删除的历史分支**，该 job 自创建起**一次都没有运行过**，`main` 实际处于「无保护 + 无守卫」状态 | ✅ 已修复（改指 `main`，展示名与报错文案同步） |
| 2 | `ci.yml` 的乱码守卫 job id 为 `mojibake-guard`（含连字符）——GitHub 表达式里 `needs.mojibake-guard` 会被解析成**减法**，既无法被别的 job 引用，也就无法纳入汇总结论 | ✅ 已修复（job id → `mojibake_guard`；展示名「乱码守卫 (mojibake)」不变，AGENTS.md §编码安全 引用文案同步） |
| 3 | 合并门禁需要一个**单一权威** required check：直接 require `backend` / `frontend` 会在「本次未改该目录 → job 被 paths-filter 跳过」时产生 `skipped` 判定歧义，易出现「Expected 永远等待」把正常 PR 卡死 | ✅ 已落地（新增 `gate` job，display name「质量门禁汇总」；失败/取消即不通过，`skipped` 视为通过） |
| 4 | **合并门禁的效力与仓库可见性强耦合**：required status check 由 GitHub branch protection 承载，**只在仓库为 public（或账户为付费计划）时生效**。若切回 private 且无付费计划，GitHub 会停用 protection，`质量门禁汇总` 随之消失——红灯**不再阻止合并**，门禁降级为「PR 上可见的信号」 | ⚠️ 开口项（平台约束，无代码解法） |

第 4 项的缓解与判定口径：

- 兜底守卫 `guard-direct-push`（拦直推 `main`）**与可见性无关**，任何状态下都生效；但**拦不住「红灯 PR 被点合并」**。
- 因此 private 状态下唯一防线是**人工规则**：合并前必须确认 `质量门禁汇总` 为绿。该口径已写入 `AGENTS.md` 项目概述，避免「以为有门禁」的误判。
- 长期私有化的两种正解：① 升级到含保护分支的付费计划；② 改走「合并后检出」守卫（`push` 到 `dev` 时回查该提交所属 PR 的检查结论，红灯则开 issue 并使 run 失败）——**当前不实施**：单人维护、红灯在 PR 页一眼可见，加检测器属过度工程。

附：本文件 158–243 行的损坏段（见开头提示）与本轮治理无关，属既有残留，需专门清一次。建议修法二选一：① **机械剥离前缀**——每行去掉行首的「行号 + 冒号/竖线」，注意竖线场景下原行首的 `|` 要保留（否则表格列会丢）；② **从引入该段的提交重新取原文覆盖**（更稳，可避免剥离规则在边界行上出错）。**留待专门一次文档清理**，不与本轮治理混做。

配套决策见 `docs/spec/decisions.md` 2026-09-11 行（D22）；授权变更见根 `LICENSE`、`README.md`「授权与使用限制」与 `AGENTS.md` 核心约束「授权与可见性」。

## 2026-09-13 #1460 实施途中发现（1 项开口 + 1 项已修）

### 开口项：`SyncJob` 钩子契约不被基类履行，且「接上钩子」会引入数据损坏

**现象**：`app/services/sync/jobs/base.py` 把 `_pre_run()` / `_post_run()` 定义为「子类可重写的钩子」，但基类 `run()`（第 164 行）**从不调用它们**。当前三种情形：

| job | 是否重写 `run()` | 钩子是否生效 |
|-----|-----------------|-------------|
| `amac_institution` | 否（用基类 `run()`） | ❌ **定义了 `_pre_run` / `_post_run` 但永不执行** |
| `fund_company_backfill` | 是 | ✅ 自行调用（第 66 / 105 行） |
| `fund_detail_enrich` | 是 | ✅ 自行调用（第 56 / 111 行） |
| `asset_snapshot` / `fund_position` / `market_snapshot` | 是 | 不涉及 |

**影响**：`amac_institution._post_run()` 是「下架/倒闭保护」——把库中 `is_active=True` 但不在本次 AMAC 名单内的销售机构标记失效（`FundCompany` 侧有 `full_name.isnot(None)` 闸门防误伤券商资管系）。它不执行 = 该保护从未生效。

**⚠️ 关键陷阱：naive 地「把钩子接上」会引入数据损坏，不能直接修。**
`_post_run()` 的反查基准 `self._seen_org_names` **只在成功抓到的分页里填充**（`_save_data` 期间）。而 `_fetch_paged()` 用 `resp.raise_for_status()` 逐页取数——**任一页失败即抛错**，被基类 `run()` 捕获后重试、最终落到 `MANUAL_INTERVENTION`。此时 `_seen_org_names` 是**残缺集合**，若在 `finally` 里执行 `_post_run()`，会把**所有没抓到的机构批量标为失效**——把「抓取失败」放大成「数据损坏」。

也就是说：**钩子没被调用，客观上挡住了这次事故**。正确修法必须同时满足两条：

1. **基类履行契约**——`run()` 里 `_pre_run()` 前置、`_post_run()` 后置，并**移除** `fund_company_backfill` / `fund_detail_enrich` 的手动调用（否则会执行两次）；
2. **加完整性闸门**——`_post_run()` 的失效扫描**只在「本次抓取完整」时执行**（最简口径：仅当 `status == SUCCESS` 才跑失效段；更稳的口径：`_fetch_paged` 记录期望总数与实际抓取数，两者不符即跳过失效段并告警）。缺这条就绝不能接。

**建议**：**另开 issue 单独做**（含 1 条覆盖「抓取中途失败 → 不得标记失效」的回归测试）。本轮未修——它属独立缺陷、涉及另一数据域的行为变更，且修法含上述陷阱，与 #1460（探市落库）无耦合，混做会稀释评审注意力。

### 已修项（本轮同批处理，记录备查）

| # | 事项 | 状态 |
|---|------|------|
| 1 | `execution_plan` 漏 **5** 个已注册 job（`temperature` / `convertible_bond` / `index_valuation` / `channel_link` / `amac_institution`），`run_all_jobs` 实际只跑 16 个 | ✅ 已修（#1460 顺带；补 `None` 目标池 + 「注册集 = 计划集」双向断言测试） |
| 2 | 探市汇率卡长期展示 **2023 年**数据（F6）；根因是 `akshare.currency_boc_sina` 默认日期区间被上游硬编码为 `20230304`~`20231110`，调用点漏传日期 | ✅ 已修（显式传 `start_date` / `end_date`；真机实测 `trade_date=2026-09-12`） |
| 3 | 并发取数会让进程 **`FATAL` abort**（akshare 40 个模块用 `py_mini_racer`，每次调用新建 V8 isolate，pool 只能初始化一次；C++ abort 抓不住） | ✅ 已修（结构性：`app/core/v8_guard.py` 挂在唯一收口点 `get_akshare()` 上）。见 `decisions.md` D24 |
| 4 | `is_rest_day` 的 `today_shanghai().date()`（该函数本就返回 `date`，再调 `.date()` 必抛 `AttributeError`）；原版所有调用点都显式传 `today` 故从未暴露 | ✅ 已修（#1460 改为按任务判定后暴露，补回归测试） |
| 5 | 周末汇率卡显示 `+0.00%`：`currency_boc_sina` 在非工作日追加顺延行（值同前一日、中间价 NaN），当日涨跌被算成 0 | ⚠️ **未改，待产品口径决策**（剔除顺延行 / 改用最近有效观测日 / 接受现状）。详见 `docs/working-notes/market-snapshot-persist-plan-2026-09-13.md` §8.1 |

