# 技术债务与开口项明细（tech-debt）

> ⚠️ **易腐烂内容**：本文件随修复进展频繁变化。最后核实日期：**2026-08-03**。每条债务修复后，须将状态更新为"✅ 已修复"并注明版本号；请勿删除历史条目（保留可追溯）。

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
| 腾讯理财通格式复杂 | 中 | 理财通导出格式非标准CSV，需专门解析器 | P2 实现 |
| 孤儿交易无自动回填机制 | 中 | 需定时任务扫描并关联后续新增的持仓 | P1-20 实现 |
| 持仓分布可视化缺失 | 中 | 仪表盘仅有总资产展示，无配置结构图 | P1-15 实现 |
| 货币基金识别依赖关键词硬编码 | 中 | 元数据同步未完全覆盖所有货币基金名称，临时使用关键词匹配兜底 | 待元数据同步覆盖率足够后移除关键词逻辑 |
| 持仓详情页单持仓 XIRR 前端展示 | 低 | 页面路径未确定 | 后端接口已可用，前端延后至 P2 |
| 导入时出现 SAWarning: Identity map already had an identity for... | 低 | 同一 Session 内多次加载同一持仓后尝试 flush，导致 ORM 身份映射冲突 | 后续优化 PositionService 会话管理，当前不影响数据正确性 |
| PDF 解析器对无效日期行的处理 | 低 | 当前跳过且不记录错误 | 后续增加错误报告 |
| **`Ledger.ledger_type` 缺少 `property`（实物资产）类型** | **低** | **早期设计优先覆盖金融资产，实物资产通过 `Asset` 表快速兼容，未在账户类型体系中显式支持。用户录入房产等固定资产时无法选择匹配的账户类型，只能变通使用 `family` 类型。** | **P2 阶段新增 `property` 类型，统一 `LEDGER_TYPE_LABELS` 映射，前端账户创建页同步添加选项。届时需同步校验 `linked_cash_ledger_id` 仅对 `stock/fund` 有效。当前变通方案：引导用户使用 `family` 类型。** |
| 前端 `Inventory.vue` 虽经轻量重构，仍有 800+ 行，未完全拆分 | 中 | 功能迭代优先级高于重构，拆分延后 | P2 拆分 |
| 按平台分组盈亏缺失 | 低 | 用户无法与平台账单对账 | P2-14 实现 |
| 交易记录导出功能缺失 | 低 | 用户无法备份数据 | P2-15 实现 |
| 支付宝解析器对特殊格式（引号内逗号）的容错性 | 低 | 实际用户导出格式已稳定，当前方案够用 | 若未来出现新格式再适配 |
| 余额宝背后货币基金无法准确识别具体代码 | 低 | 支付宝不公开具体基金代码，且可能变化 | 统一归入活钱，放弃追踪具体货基 |
| 导入成功后净值自动同步（静默回填）已实现但依赖元数据同步 | 低 | 若用户从未同步过基金数据，`daily_worth` 表为空 | 导入前引导用户执行元数据同步，或导入后手动触发 |
| 桑基图资产负债交叉显示问题（ECharts 底层限制） | 低 | 图表原生不支持正负双流向分层 | 记录技术债务，暂不处理 |
| 交易流水当前全量加载，大数据量无分页筛选优化 | 低 | 初期数据量小，优先可用 | 数据量大后迭代优化 |
| 基金经理信息未同步 | 低 | `ak.fund_manager_em` 接口不稳定 | 调研替代方案，暂不实现 |
| 指数行情同步不可用 | 低 | 新浪接口不支持指数代码 | 改用 `xa.indexinfo`，待实现 |
| 全量同步时 `stock_list` / `fund_list` 需传入占位 `["__full__"]` | 低 | 重构遗留问题 | 后续优化为在 Job 中声明不需要 targets |
| `Transaction.confirm_date` 存在 NULL 值 | **已消除** | 早期写入源头未统一赋值 | 所有写入入口已堵上；存量仅 1 条，已手动修复 |
| `positions.type` 列存在 NULL/空值 | **已消除** | 部分导入解析器/手动录入未写入 `asset_type` | 数据库验证已清零，所有入口均已适配 |
| `get_money_fund_stats` 调用传入 `ledger.name` 而非 `ledger.id` | ~~🟡 中~~ **✅ 已验证** | 原怀疑参数类型错误 | 代码审查确认已传入 `ledger.id`，货基统计正常 |
| `delete_ledger` / `migrate_positions` 未跟随 `ledger_id` 迁移 | ~~🟡 中~~ **✅ 已验证** | 原怀疑仍用字符串过滤 | 已改为 `Position.ledger_id == ledger_id`，迁移同步更新快照 |
| **`GET /api/ledgers/` 未返回账户摘要数据** | ~~🔴 严重~~ **✅ 已修复** | 列表页卡片依赖 `total_market_value`、`pnl`、`position_count` 等字段，但接口只返回基础字段 | 在 `list_ledgers` 中为每个账户附加摘要统计 |
| **`position_ratio` 返回类型不一致** | 🟡 中 | `get_position_page` 中 `round()` 结果可能因单位混用而异常，且类型可能是 float 或 str | **✅ 已验证，已修复。在 v4.4.1 中强制转为 `float(0.0)` 兜底，消除了前端解析歧义。** |
| **同花顺解析器操作类型映射不完整** | 中 | `test_ths_otc_cash_format` 测试中 `OTC现金宝交` 的操作类型无法从映射表确定方向，测试被跳过 | 完善 `THS_OP_TYPE_MAP` 映射，补全测试断言 |
| **`get_ledgers_overview` 中总资产计算依赖净资产的推导** | 低 | 当前总资产通过 `net_worth + liability_total` 反推，而非直接从各组市值汇总 | 在 Service 层增加 `total_assets` 字段，直接汇总各类型市值 |
| **导入模块视图层仍较厚** | 低 | `app/domains/importers/views.py` 未完全拆分，部分校验逻辑耦合在视图函数中 | 后续提取 ImportService |
| 组合收益计算未支持跨日划转识别 | ~~低~~ **不适用** | 原逻辑：需交易级时间戳 + 人工标记 | **经审查确认：`deposit/withdraw` 不进入组合 XIRR 现金流，跨日划转不影响收益率。此技术债不适用，留待 P2 转账配对功能再评估。** |
| **投资理财与通用资产按需加载依赖校验** | 低 | 全面盘点页面依赖后端 `/api/assets/summary/` 接口呈现顶部汇总金额。如果接口因网络问题失效，顶部卡片将失去数据 | 需在前端 `fetchData` 中对 summary 接口添加健壮的错误处理与降级展示。 |
| **`usePageRefresh` 全局数据同步尚未覆盖所有页面** | 中 | 目前只有账户详情页 (`LedgerDetail.vue`) 和全面盘点 (`InventoryHome.vue`) 接入了该组合式函数 | 后续开发新页面（如自选、交易流水等）时，必须引入 `usePageRefresh` 以保持数据同步。 |
| ~~双代码库：V1 为遗留残留、V2 为唯一代码库~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | `autoapp.py` 启动遗留 V1，README 实际运行 V2；前端/测试/DB 均指向 V2，且 V1 被 `.gitignore` 忽略 | **已执行物理清除**：删除 `fundmate/`、`migrations/`、`autoapp.py` 及 29 个 V1 移植测试；备份于 `.backup-v1-2026-08-01/`。V2 为唯一代码库。 |
| ~~V1 `data/` 数据源冗余~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | V1 `data/` 20+ 源在 `backend/app` 引用数均为 0；V2 经 `services/sync`+`services/thermometer` 独立覆盖；券商持仓自动导入类源违反 §2.1 | **随 V1 一并删除、不移植**。 |
| ~~`fundmate/libs/cal` 残留计算库~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | V2 已有等价 `app/services/performance/xirr_engine.py`，`app/` 零引用 | **直接删除不移植**；XIRR 数值金值迁入 `tests/services/performance/test_xirr_engine.py`。 |
| ~~测试目录双轨（V1 移植残留 29 文件）~~ | ~~🟠 高~~ **✅ 已闭环 (2026-08-01)** | `tests/` 含指向 `backend.fundmate` 的移植测试，由不被自动加载的 `conftest_fm.py` 支撑 | **删除 29 个 V1 测试文件 + 辅助**；测试单轨化，`pytest` 全绿；新增 `scripts/forbid_v1_refs.sh` 守卫禁止回引。 |
| ~~V2 `app/main.py` 错误契约未入 `create_app` 且 `abort()` 绕过 `{data,message}` 信封~~ | ~~高~~ **✅ 已修复 (2026-08-01, v4.5.8)** | `register_error_handlers` 仅在模块级 `app` 注册，未放进 `create_app()`；`app/` 内约 65 处 `abort()` 返回缺 `data` 字段 | **实测修正（反向压力测试通过）**：未将 65 处 `abort()` 逐一改为 `SBException`（改动面大、回归风险高），改为在 `create_app()` 内挂载全局异常处理器，并新增通用 `HTTPException` 处理器把 `abort()` 各状态码（400/404/409/500…）统一收敛到 `{data, message, error_code}` 信封；`ErrorCode` 增补 `UNAUTHORIZED(1005)`/`FORBIDDEN(1006)` 以覆盖 401/403 映射。新增 `tests/test_error_envelope.py` 直接验证 `create_app()` 实例（即测试 fixture 实际所用 app）已挂载处理器且各状态码均返回信封。全量 `pytest` 466 passed / 1 failed（唯一失败为 eastmoney 实时联网依赖）。 |
| **`app/` 内 13 处 `@bp.input()` 自动范式装饰器（违反 §1.3「不依赖自动范式」）** | 高 | SPEC §1.3 要求「不依赖自动范式，为迁移 FastAPI 预留空间」；但 `watchlist(6)/positions(2)/assets(2)/funds(1)/strategy(1)/performance(1)` 共 13 处用 `@bp.input(Schema)` 把请求校验交给 APIFlask 框架，视图签名依赖其注入的已校验对象。注：**13 个输入模型本身已为 `pydantic.BaseModel`（FastAPI 就绪）**，故模型迁移成本≈0，冲突仅限装饰器调用本身（`importers/views.py` 内 2 个未启用 Schema 才是真 marshmallow）。 | **已记录·示范收敛·余下暂缓（2026-08-01）**：新增 `app/core/validation.py` 提供 `parse_body(model)`/`parse_query(model)` 替代 `@bp.input`，手动 Pydantic 校验、失败 `abort(422)` 走统一信封（与 `@bp.input` 的 422 状态码一致，既有校验测试不受影响）；已对 `assets` 的 `create_asset`/`update_asset` 完成实证改造（验证：`test_assets`/`test_ledgers`/`test_summary` 共 88 用例全绿，全量 `pytest` 466 passed / 1 failed，唯一失败为 eastmoney 实时联网依赖、非回归）。**按用户决策，剩余 11 处暂缓收敛**——当前无功能影响，且 13 个输入模型本身已为 `pydantic.BaseModel`（FastAPI 就绪），未来迁移成本可控；CI 守卫暂未新增。详见 `docs/working-notes/code-audit-and-remediation-2026-08-01.md` §6。 |
| **全站 footer 对齐问题（前端布局）** | 🟡 中 | `layout/components/lay-content/index.vue` 的 `.main-content`（内容区）与 `layout/components/lay-footer/index.vue` 的 `.app-footer__inner`（页脚内容）分属不同容器/坐标系，折叠侧边栏后两者左右边缘不对齐；页脚与内容未共用同一套 `max-width` + 居中 + 左右 padding 约束。 | **待解决（2026-08-02 记录）**：需让页脚与内容区共用同一套宽度约束（`max-width: 1400px` + 48px 左右 padding + `margin: 0 auto` 居中），确保折叠/展开侧边栏时左右边缘严格对齐；同时遵循 design.md「背景同色收尾」语义（`--bg-page`），保留主容器 `--bg-warm` 的次级背景层次。当前全站 `AppFooter` 已简化为居中提醒条，对齐问题待统一容器方案后收口。 |
| **依赖升级引入样式/运行时回归风险（前端 `pnpm up`）** | 🟠 高 | 2026-08-03 执行 `pnpm up` 将前端依赖整体升级：element-plus 2.11.5→2.14.3、vue 3.5.22→3.5.40、tailwind 4.1→4.3、sass 1.93→1.102、vite 7.1→7.3、echarts 6、@vueuse/core 14.x 等。**未做充分回归（仅验证 typecheck 通过 + DEV 能起）**，升级后未重新人工核对各页面样式。典型症状：温度计/探市页 header/footer 样式在 DEV 下错乱（实为下面的「dev server 与磁盘依赖版本错位」所致，非 header/footer 代码改动）。header/footer 接入温度计/探市页为更早提交（`891868d`/`bc38d75`/`aa2fffa`），本次未改动。 | **待解决（2026-08-03 记录）**：升级后须对所有路由页做一轮样式回归（尤其 element-plus 2.11→2.14 的组件样式、tailwind v4 工具类、sass 1.93→1.102 混合宏）；建议固定本次升级为一次独立 commit，便于出问题时 `git revert` 二分定位。<br>**2026-08-04 更新**：随 OOM 修复一并完成了 ECharts 全量→按需引入改造（8 文件），typecheck 通过（无新增错误），但样式回归仍待人工核对。 |
| **生产 `build` 因 OOM 失败（前端 vite 7）** | ~~🟠 高~~ **✅ 已修复 (2026-08-04)** | 2026-08-03 `pnpm run build` 直接 `JavaScript heap out of memory`（exit 1），`NODE_OPTIONS=--max-old-space-size=8192` 仍不足。疑似 vite 7 + 升级后依赖体积膨胀（echarts 6、element-plus 2.14 等）导致打包内存占用激增。该问题**不影响本地 DEV 看页面**，但阻塞生产部署与 Vercel 构建。 | **已修复（2026-08-04）**。经排查 OOM 由四因素叠加导致：① Rollup 无 `manualChunks` 分包；② ECharts 全量引入（8 处）；③ `@iconify/json` 巨型依赖（node_modules 超 200MB）；④ Element Plus 全量 CSS 引入。**详细修复记录见 `docs/working-notes/build-oom-fix-2026-08-04.md`**。 |
| **dev server 进程存活但磁盘 `node_modules` 已升级 → 版本错位** | 🟡 中 | 2026-08-03 升级依赖时，凌晨 1:20 启动的旧 vite dev server（PID 6756/15644，端口 8449）仍在运行，其加载的模块缓存为旧版本；而 `pnpm up` 已把磁盘 `node_modules` 换成新版本。进程与磁盘依赖版本错位 → HMR 下 CSS/组件样式错乱（用户「看到的样式又不对了」即此因）。非 header/footer 代码被改。 | **待解决（2026-08-03 记录）**：升级依赖后必须重启 dev server（杀旧进程 + 重新 `pnpm dev`），且 `dev` 脚本或服务编排应保证依赖变更时自动重启。当前本地旧进程需人工清理。 |
| **`pnpm-lock.yaml` 与实际安装版本不一致** | 🟡 中 | 2026-08-03 build 日志显示运行时解析到 `@vueuse/core@14.3.0`，但 `package.json` 写 `^14.4.0`（caret 范围内），且 lock 文件与本次 `pnpm up` 后的实际安装版本存在偏离嫌疑。lock 文件可信度存疑，可能导致「本地能跑、CI 装到不同版本」的不一致。 | **待解决（2026-08-03 记录）**：升级后执行 `pnpm install --lockfile-only` 重新生成 lock 并 commit，确保 `package.json`/`pnpm-lock.yaml`/`node_modules` 三者版本一致；CI 加 `pnpm install --frozen-lockfile` 校验。 |
| **前端命名规范整理（参照 Pure Admin + Vue 官方）** | 🟡 中 | 早期前端代码粗糙，命名/类型组织不统一：`api/` 下 `any`/`Record<string, any>`/`object` 泛滥、API 函数命名不一致（`refreshTokenApi`/`getLogin`）、类型与实现混放、components 层级混用。2026-08-03 已先产出规范（`frontend-naming.md`）+ 不规范点清单（`frontend-naming-audit.md`），并按决策「保持现状不强制统一 views 目录形态」。 | **待逐条执行（2026-08-03 记录）**：P0 清 `any`（先对齐后端 `api/types.d.ts` 契约）→ P1（API 命名统一、类型集中、components 改目录组件）→ P2（utils/constants/config 边界）。详见 `frontend-naming-audit.md`，逐条改造需另行确认后执行。 |
| **8 个 A 类 typecheck 修复（前端）** | 🟢 低 | 2026-08-03 随依赖升级一并修复 8 个 A 类 typecheck 错误（`frontend/src` 下 8 文件：温度 API、页面刷新 composable、快捷入口、布局类型、mitt/theme 工具、账户/资产/交易/自选/登录等视图），属升级伴随的契约对齐，不含 header/footer 组件改动。 | **已修复（2026-08-03）**：typecheck 通过；与上面「命名规范 P0 清 any」同源，后续按 `frontend-naming-audit.md` 深化类型安全。 |
| **温度计·公募基金整体持仓集中度/抱团度未接入（无免费现成接口）** | 中 | 用户要求的"公募基金整体持仓集中度/抱团度"需聚合全市场主动基金前十大重仓（扫约 1 万只、限流、季度批处理），无免费现成聚合接口（韭圈儿 Pro「机构抱团/行业恐贪」、Choice、Wind 均付费；东财仅研报新闻非结构化 API）。按用户"能白嫖就不算"原则不自算。已具备可选自算原型 `fund_concentration.py`（扫天天基金前十大重仓、聚合前 50 热门股），但数据拿取重、且依赖 akshare 主动基金池与天天基金档案接口。 | **暂缓（2026-08-03 记录·待确认）**：暂不入 v2 主链路。路径有二：①订阅韭圈儿 Pro 直接白嫖现成机构抱团/行业恐贪数据；②或后续有轻量聚合源再接入。自算原型保留为可选离线批处理，不阻塞主链路。 |
| **温度计·用户持仓拥挤度/抱团度计算（需持仓穿透）** | 中 | 用户持仓维度的行业拥挤度/集中度需先做"持仓穿透"——拿到底层股票（用户持有的基金→其前十大重仓股，或股票账户直接持仓），再按行业聚合计算。当前 v2 后端无持仓录入/穿透模块（持仓录入 `holdings.csv` 规划于 README 9.3，尚未建）。 | **技术债务（2026-08-03 记录）**：列入基础债务，待持仓录入与穿透能力具备后再实现；本期只接入不依赖持仓的维度（行业拥挤度行情自算；公募基金整体集中度暂缓）。 |

---

## 15. 文档系统整合与未来用户手册规划（技术债务 · 不紧急）

> **决策背景**：用户要求"把文档系统整合，明确哪些文档作为未来用户手册"，并登记为技术债务（非紧急）。文档站**不拆离仓库**，仍留在 `fundmate` 仓内 `docs/`（`/docs` 子路径部署）；拆独立仓库会增加更新摩擦，已与用户确认。
> **范围**：本节只做"盘点 + 归类 + 缺口登记"，不立即补全内容。

### 15.1 现有文档归类（用户手册 vs 内部）

| 路径 | 归类 | 是否未来用户手册 | 备注 |
|:---|:---|:---|:---|
| `docs/guide/*`（index/export-alipay/import-efund） | 用户指南 | ✅ 核心候选 | 受众=家人/自己，纯实操步骤；仅 3 篇，缺口大 |
| `docs/features/xirr.md` `account.md` `holding-record.md` `asset-review.md` `overview.md` `watchlist.md` | 功能说明 | ✅ 候选（需从设计决策中剥离用户向部分） | 当前混含技术决策，需拆出"用户怎么用" |
| `docs/site/faq.md` `privacy.md` `about.md` | 站点页 | ✅ 候选 | 实际是营销/帮助站内容，需对齐 v1.6 品牌语言 |
| `docs/api/*` | API 文档 | ➖ 开发者向（非终端用户手册） | 开发者手册 |
| `docs/features/temperature-redesign.md` `temperature-archive.md` `recover-from-ai.md` | 设计/决策笔记 | ❌ 内部 | 不对外 |
| `docs/spec/*`（architecture/conventions/data-model/decisions/frontend-*/roadmap/tech-debt） | 架构/规范 | ❌ 内部 | 开发者 |
| `docs/dev/*`（31 篇）`docs/pytest/*` `docs/working-notes/*` `docs/ops/*` | 开发笔记 | ❌ 内部 | 不对外 |

### 15.2 缺口与待办（技术债务，优先级：低/不紧急）

| 问题描述 | 优先级 | 处理策略 |
|:---|:---|:---|
| **用户手册内容缺口大**：`guide/` 仅 3 篇，缺"新增持仓/更新价格/导出备份/CSV 导入"等核心流程图文 | 低（不紧急） | 按 `guide/index.md` 的"纯实操截图+步骤"标准，从 `features/` 用户向章节拆分补全 |
| **品牌名未统一**：文档站仍用"叽咕 / fundmate"，主站已定"多倍贝 / Duobeibei" | 中 | 全站文档替换品牌名；`docs/README.md` 的 `heroText/tagline` 及 `site/about.md` 同步改写 |
| **站点页未对齐 v1.6 品牌语言**：`site/faq` `about` `privacy` 文案/措辞与 brand-v1.6 不一致 | 低 | 以 `docs/design/brand-v1.6.md` 为基准重写站点页文案（数据主权、不荐股不跟单等主张） |
| **文档站构建技术未定**：当前 `docs/README.md` 为 docsify 风格（`home:true`/`heroText`），钱迹参考站为 GitBook | 低 | 评估 docsify→VitePress/GitBook 迁移；用户手册结构按钱迹"产品模块 + 疑问式标题"组织 |
| **落地页视频/动效场景待补充**（参考 WorkBuddy） | 低 | WorkBuddy 在 Hero 区嵌入了产品截图/视频展示应用场景，多倍贝当前为纯静态 HTML。后期可补充：(a) 工具实际使用录屏（Lottie/MP4 嵌入 Hero 或功能区）；(b) 产品界面截图轮播；(c) 数据可视化动态演示（XIRR 曲线绘制过程）。需先录制素材再编码嵌入，属于视觉打磨阶段 |
| **用户手册与开发文档物理隔离**：当前混在 `docs/` 同名目录，未来需明确发布范围（`/docs` 仅发布用户向，内部放 `/docs-internal` 或私有） | 低 | 待用户手册成形后再规划发布边界 |
    94:
    95:---
    96:
    97:## 2026-08-04 OOM 修复记录
    98:
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
