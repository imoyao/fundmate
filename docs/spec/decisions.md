# 重要决策记录（decisions）

本文件收录项目重要决策完整记录表（原 SPEC 第 12 章），属于 **append-only（仅追加，不修改历史条目）** 的永久回溯记录。新增决策时追加新行，禁止修改或删除既有条目。

## 1. 重要决策完整记录表（原 SPEC 第 12 章）

| 决策日期       | 决策主题                                      | 完整决策细节 |
|------------|-------------------------------------------|-------------|
| **2026-08-03** | **前端命名规范制定（参照 Pure Admin + Vue 官方）** | 早期前端代码粗糙，命名/类型组织不统一。决策：**先固化规范 + 出不规范点清单，后续逐条确认再改，不一次性大改**。规范落地于 `docs/spec/frontend-naming.md`（conventions 第 2.7 节前端补充），清单见 `frontend-naming-audit.md`。核心约定：① 文件命名 Vue 组件 PascalCase、工具/API camelCase、组合式 `useXxx`、目录全项目统一风格；② 内置封装沿用 Pure Admin `Re` 前缀，业务组件禁用于此前缀；③ 变量/函数 camelCase 语义自解释、常量 UPPER_SNAKE、类型 PascalCase 禁 I 前缀；④ **类型安全红线：禁止 `any`/`Record<string, any>`/`object` 作 API 入参响应，须对齐后端 `api/types.d.ts` 契约**（与既有 B 类 typecheck 债务同源，改造须先核对后端）；⑤ 类型集中管理，跨模块实体抽至 `api/types.d.ts` 或 `types/`。**关于 views 目录组织（index.vue 包裹 vs PascalCase 平铺）**：调研 Vue 官方风格指南与社区结论——官方只要求「项目内大小写风格一致」，不强制目录形态；「目录组件」为 Nuxt/Pure Admin 等可选约定非官方红线。故决策**保持现状不强制统一**，仅保证各自大小写一致。执行顺序 P0（清 any，先对齐契约）→ P1（API 命名统一、类型集中、components 改目录组件）→ P2（utils/constants/config 边界）。 |
| **2026-08-01** | **乖离率（BIAS）模块设计与落地** | 决定采用刘晨明减法版乖离率算法（`(ln(close) - EMA20(ln(close))) × 100`），覆盖31个申万一级行业 + 6个宽基指数。行业代码写死在 `constants.py`（无需外部维护），用户持仓/自选品种动态获取。数据保留30天，午间（12:00）和盘后（15:30）双次计算。乖离率模块独立于温度模块（`services/bias/`），计算结果存入 `market_multi_items` 表，通过 `/api/temperature/overview` 的 `multi.bias` 字段返回前端。 |
| **2026-08-01** | **二鸟说手抄报自动化 P1 完成与 P2 规划** | 确认火山引擎 `ARK_MODEL=doubao-seed-2-1-pro-260628` 可用，P1「链接归档 + Ark 结构化抽取」跑通并推送到 `main-v2`；仓库仅保留 `docs/er-niao/index.json`（约 1KB/期），正文不入库、前端直接跳雪球原文。将「AI 根据结构化数据 + 搜索生成每周行情综述/研判」作为 P2-17 写入 SPEC，待数据稳定后实施。 |
| **2026-08-01** | **二鸟说拆分为独立项目 WeChatRSS（可插拔扩展）** | 决定把二鸟说数据抽取从 fundmate 拆出，迁入已有的 **WeChatRSS**（微信公众号→RSS 摄取底座，自带 mp 原文链接）。采用「双轨」：WeChatRSS 内置 `src/analyzers/erniao.py` 可插拔分析器（CI 主链路）+ WorkBuddy 自动化作为手动重放/兜底。fundmate 侧**删除**后端死代码（`ErNiaoFetcher`/`ER_NIAO_SOURCES`/`jobs.py` 二鸟说分支/`/parse-er-niao` 端点/`scripts/erniao_*.py`/`docs/er-niao/`，干净分离）。二鸟说结构化数据现位于 `WeChatRSS/data/er-niao/index.json`；P2-17 数据源相应更新。 |
| **2026-08-01** | **V1（`backend/fundmate/`）退役清除（实测闭环）** | 经核实 `autoapp.py` 指向 V1 为**陈旧残留入口**（README 实际以 `flask --app app.main:app` 运行 V2）；前端 API 契约、测试 conftest、DB 模型均指向 V2；V1 整体被 `.gitignore` 忽略、不在版本控制。决策：**V2 为唯一代码库，V1 受控退役**。执行：删除 `fundmate/`、`migrations/`、`autoapp.py` 及 29 个 V1 移植测试；`libs/cal` 因 V2 已有等价 `xirr_engine` 直删不移植（XIRR 金值已迁入 V2 测试）；删前物理备份 `.backup-v1-2026-08-01/`（15.9MB，可回滚）。结果：V2 测试 459→460 全绿（唯一失败为 eastmoney 实时联网测试、属网络环境依赖）；新增 `tests/test_exceptions.py`、`scripts/forbid_v1_refs.sh` 守卫。详见 `docs/working-notes/code-audit-and-remediation-2026-08-01.md`。 |
| **2026-08-01** | **错误信封契约闭环（高优先级技术债 v4.5.8）** | 实证定位根因：`register_error_handlers` 仅挂在 `main.py` 模块级 `app`，而测试 fixture 直接 `create_app()` 得到另一实例 → 处理器在测试环境未挂载；约 71 处 `abort()` 仅 404/500 被覆盖，其余状态码绕 SPEC `{data,message,error_code}` 信封。决策：**不逐一改写 `abort()` 为 `SBException`**（改动面大、回归风险高），改为在 `create_app()` 内挂载处理器 + 新增通用 `HTTPException` 处理器统一收敛 `abort()` 各状态码到信封；`ErrorCode` 增补 `UNAUTHORIZED(1005)`/`FORBIDDEN(1006)`。`PROPAGATE_EXCEPTIONS` 维持 `True` 不变（避免改动测试既有行为）；APIFlask 校验错误（`HTTPError`，非 `HTTPException`）仍走框架 422 JSON（自带 `message`，前端已兼容）。验证：新增 `tests/test_error_envelope.py` 直接断言 `create_app()` 实例已挂载处理器且 400/404/409/500/SBException 均返回信封；全量 `pytest` 466 passed / 1 failed（唯一失败为 eastmoney 实时联网依赖，非回归）。 |
| **2026-07-15** | **自选模块标准化逻辑修正与前端体验优化** | 决定强制要求前端传递 `venue` 或 `asset_type` 字段，后端不再自动猜测资产类型，避免基金代码被错误标准化。同时将自选业务逻辑彻底抽取至服务层，视图层仅保留参数校验。前端增加基金标识标签、涨跌箭头、操作按钮 Hover 显隐等 UI 优化。 |
| 2026-07-14 | **v4.5.1 严重技术债务清理** | 确认三个严重 Bug 已修复：`get_ledger_summary` 分支逻辑、前端 API 路径解析、`GET /api/ledgers/` 摘要数据返回。修改相应的技术债务状态为"✅ 已修复"。 |
| 2026-07-08 | **赎回费率估算与单基金费率同步策略** | 决定将赎回费率估算接口重构为一次请求返回全仓持有分布（holdings）和指定份额卖出分布（sell），前端不再并行请求两次。同时，当费率数据缺失时，不自动跳转，而是通过 POST /api/funds/{fund_code}/fee-sync/ 允许用户在当前页面一键同步费率，避免上下文丢失。后端服务层合并 fund_data_service.py 和 fund_fee_service.py 为 FundService，消除重复，遵循"薄视图、厚服务"原则。 |
| 2026-07-08 | **卖出表单账户切换清空交互优化** | 经过多次尝试，最终采用 v-if + :key + nextTick 组合方式，在赎回操作切换账户时强制清空持仓下拉框，避免残留旧持仓数据。申购操作（BuyForm）保持原有行为，只清空产品选择。该逻辑被封装在 SellForm 的 clearFormData 中，不影响其他组件。 |
| 2026-07-02 | 后端 Service 命名规范化与 B5 精度强制 | 将 LedgerService 中模糊的分页方法 get_position_page 和 get_transaction_page 重命名为 get_positions_paginated 和 get_transactions_paginated。同时修复 position_ratio 精度隐患，当 total_mv_cents 为 0 时，明确返回 float(0.0) 而不是整数 0，从源头彻底消除前端数字类型解析隐患。 |
| **2026-07-01** | **提取全局组件与组合式函数** | **1. 全局组件 `ProductDisplay`**：统一全站持仓/资产表格的"名称、代码、类型"复合列展示，彻底消灭各行其是的 DOM 结构。**2. 组合式函数 `usePageRefresh`**：采用全局 `mitt` 事件总线与组件挂载/销毁生命周期自解绑机制，规范所有页面在"简记记账成功"后的数据刷新逻辑，替代早期的暴力 `:key` 重绘方案。 |
| **2026-07-01** | **"全面盘点"页按需加载策略（降维打击）** | 为解决"进入页面全量拉取 500+ 条通用资产"的性能隐患，新增轻量汇总接口 `/api/assets/summary/`。页面初始化仅拉取 `positions` 和各类资产汇总金额，点击"固定资产/负债"等具体标签时，触发 `watch` 实现该分类数据的"懒加载"与前端 `assetCache` 缓存，实现毫秒级切换。 |
| **2026-07-01** | **前端布局操作前置与排版核心策略** | 将"操作入口"统一提至所有分类的"投资分布/资产明细"摘要卡片下方，确立"先看摘要、再做操作、后看明细"的动线。全站二级标题统一定义边距为 `mt-10 mb-10`，彻底解决模块间因 `margin` 杂乱导致的忽大忽小问题。 |
| **2026-06-27** | **通用业务组件封装决策（新增）** | 决定封装 `MoneyDisplay` 和 `RiseFallText` 两个通用业务组件，统一全站金额和涨跌文本的展示规范。组件路径：`@/components/MoneyDisplay/` 和 `@/components/RiseFallText/`。编码红线：所有金额/涨跌展示必须使用这两个组件，禁止手写格式化逻辑。 |
| **2026-06-27** | **UI 设计规范 v2.3.2 及暗色模式 v1.4 同步** | 完成设计语言体系封箱：亮色模式 `/frontend/design.md`（v2.3.2），暗色模式 `/frontend/design.dark.md`（v1.4）。强制决策同步至 SPEC：涨红跌绿与品牌色统一（品牌色即涨色）、前端色彩变量编码红线（禁止直接调用 `--brand-*`）、数字显示规范、组件交互反馈规范（主按钮位移、软按钮遮罩）、暗色模式预埋约束（HSL 动态计算）、可访问性自动化测试约束。 |
| 2026-06-21 | 跨日划转过滤不适用于当前架构 | 审查 `generate_portfolio_cashflows` 确认：deposit/withdraw 被归入 `transfer_candidates`，从始至终未加入 XIRR 现金流列表。组合收益率只计算买入/卖出/分红等投资类交易。无论同日还是跨日，资金划转都不会污染收益率计算。"跨日划转过滤"技术债标记为不适用，待 P2 转账配对功能上线后再评估。 |
| 2026-06-21 | 卖出表单补上基金确认日计算 | `SellForm.vue` 新增 `fetchConfirmDate` 逻辑，卖出基金时调用 `calcFundConfirmDate` API 获取确认日，与 `BuyForm.vue` 完全对称。卖出非基金时 `confirm_date` 直接用 `trade_date`（股票/ETF T日成交即确定）。 |
| 2026-06-21 | 资产录入不拆分为多页面 | 通用资产录入保持单一 `AssetEntry.vue`，投资理财类资产等专门功能上线后再决定是否分离。extra 扩展字段的录入模板延后至 P2，与资产详情页展示同步实现。 |
| 2026-06-21 | ECharts 图表颜色动态读取 CSS 变量 | 放弃在组件中硬编码十六进制颜色，改为通过 JS `getComputedStyle` 在运行时动态读取 `colors.css` 中定义的变量（如 `--invest-stock`、`--sankey-liquid`），确保图表颜色与全局主题保持严格一致，且能响应未来可能的暗黑模式或主题切换。 |
| 2026-06-21 | 抽取独立抽屉组件 `PositionTransactionsDrawer.vue` | 原详情页中点击持仓行在表格下方展开交易明细，导致父组件逻辑膨胀且交互受限。决定将其重构为右侧 `el-drawer` 独立组件，接收 `position-data` prop 并内部调用 `GET /api/positions/{id}/transactions/` 获取数据，实现关注点分离和更灵活的布局。 |
| 2026-06-21 | 简记弹窗买入/卖出交互优化 | 将"买入/卖出"由 `el-radio-group` 改为 `el-tabs` 切换；合并交易日期与下单时间至同一行并采用 `el-radio-button` 组；金额/份额切换改为 `el-input` 的 `prepend` 插槽实现下拉选择模式；基金卖出份额支持小数精度（4 位）；极简账户创建增加必选的账户类型下拉框，类型选项排除 `property`。 |
| 2026-06-21 | 账户列表页分组标题增加汇总信息及缩写 Badge | 在每个分组标题（如"银行账户"）后显示账户数与总金额（如 `(2 个账户 · ¥12,345)`）；卡片内类型标签由完整名称改为单字缩写（银/股/基/物），使用与分组标题匹配的半透明彩色背景小徽章，降低视觉冗余。 |
| 2026-06-21 | 修复 Layout 中 `LayHeader` 渲染导致全局抽屉无法弹出 | `LayHeader` 原本在 `<script setup>` 中使用 `defineComponent` + `h()` 渲染，导致插槽上下文丢失，影响全局 `TransactionDrawer` 的挂载。修复方案：去除 `defineComponent` 定义，直接在模板中替换为原始 HTML 结构，保持功能完全一致。 |
| 2026-06-21 | `ledger_id` 缺失写入入口排查与修复方案 | 发现资产录入 (`AssetEntry.vue`) 和简记弹窗早期版本均未传递 `ledger_id` 导致数据游离。简记弹窗已修复：账户选择改为绑定 `ledger_id`，提交时传递该字段。资产录入同样需改为 `ledger_id` 绑定，方案已定待应用。 |
| 2026-06-21 | 账户详情页概览卡片重构与图表规划 | 将原有卡片改为网格布局，强制涨红跌绿；新增环形图展示资产配置分布；预留走势图位置（依赖 P1-20 快照数据）。图表颜色全部通过 CSS 变量获取，保证零硬编码。 |
| 2026-06-18 | 放弃 SQL 聚合，统一使用 Python 聚合计算市值（**除数描述已纠偏 v4.5.3**） | SQL 市值聚合与 `Money.multiply_price_quantity` 单位/路径不一致，产生双路径维护成本与单位混淆风险，故统一改用 Python 聚合。⚠️ **历史备注"分母应为 1,000,000、÷10000 放大 100 倍"为笔误**：当前 `Money` 以 ÷`SHARE_FACTOR(10000)` 计算且被测试锁定，正确无放大；**切勿据此把代码改为 ÷1e6**。 |
| 2026-06-17 | 账户类型体系最终确定 | 砍掉 `family`/`general`/`cash`，最终保留四种类型：`bank`（银行账户）、`stock`（证券账户）、`fund`（场外基金平台）、`property`（实物资产）。核心规则：同账户内操作 = 资产形态转换，跨账户操作 = 转账。银行渠道买基金直接挂在银行卡账户下，不单独建 `fund` 账户。 |
| 2026-06-17 | `cash` 账户类型重命名为 `bank` | 将原先的现金/活钱账户类型从 `cash` 改为 `bank`，语义更清晰，表示一张具体的银行卡，承载活期、理财、基金等全部行内资产。同时 `linked_cash_ledger_id` 的校验也改为检查 `ledger_type='bank'`。 |
| 2026-06-18 | 引入 `ledger_id` 外键替代字符串关联 | `positions`、`transactions`、`assets` 增加 `ledger_id` 字段，通过外键与 `ledgers` 关联。`account_name` 保留为快照字段。所有核心查询和写入均基于 `ledger_id`，提升性能和数据完整性。 |
| 2026-06-15 | 金融数据存储精度方案（最终决策） | 所有直接关联用户资金的字段（金额、份额）采用整数存储分（×100）或最小份额单位（×10000）。基金净值改为 DECIMAL(18,6)。所有读写通过 `Money` 工具类统一转换，禁止业务代码直接乘除。详细变更见 5.1-5.10 节。 |
| 2026-06-15 | 前端数据异常根因 | `LedgerDetail.vue` 中 `fetchData` 自行计算市值（`marketValue = quantity * current_price`），而后端 `enrich_position_dict ` 已将单位转为元/份额。数据库新旧数据混合导致前端计算结果异常。最终通过彻底统一数据库数据（执行二次迁移）解决。 |
| 2026-06-15 | XIRR 计算适配精度改造 | `generate_cashflows` 和 `generate_portfolio_cashflows` 中读取 `Transaction.amount` 时用 `Money.cents_to_yuan` 转换，`calculators.py` 中所有持仓市值计算统一使用 Money 工具类。 |
| 2026-06-14 | 新增 `transactions.symbol` 快照字段 | 在 Transaction 表中新增 `symbol` 列作为资产代码的不可更改快照，用于关联查询和盈亏曲线生成。与 `position_name`、`account_name` 同为快照设计模式。 |
| 2026-06-14 | 持仓/资产列表通用展示规范 | 所有展示持仓或资产的表格，必须将"名称、代码、资产类型"合并为单一复合列。名称大字体，代码小字灰色前缀 `#`，类型标签内联。参照导入页 `Inventory.vue` 的产品单元格样式。 |
| 2026-06-14 | 批量迁移持仓端点设计 | 采用 `POST /api/ledgers/{id}/migrations/` 嵌套资源端点，目标账户 ID 放在请求体。限定同类型账户迁移，防止数据混乱。 |
| 2026-06-14 | 持仓删除可选清理交易 | `DELETE /api/positions/{id}/?delete_transactions=true`，默认仅删持仓保留交易记录，传参则级联删除关联交易。 |
| 2026-06-14 | 交易明细下钻展示位置 | 持仓明细表格点击行展开关联交易记录，交易明细显示在表格下方的独立区域，形成主-从视图，避免行内展开导致的横向空间不足。 |
| 2026-06-14 | 引入 `CURRENT_USER_ID` 常量统一用户隔离 | 在 `app/core/constants.py` 中定义 `CURRENT_USER_ID = 1`，所有硬编码 `user_id == 1` 的地方改为引用此常量。未来多用户时只需修改一处即可切换为从认证上下文获取。 |
| 2026-06-14 | 新增 `LEDGER_TYPE_LABELS` 枚举映射 | 在 `app/core/constants.py` 中新增 `LEDGER_TYPE_LABELS` 字典，统一账户类型中文文案（证券账户、基金平台、现金/活钱等），`_ledger_type_label()` 函数和前端映射均引用此常量，消除多处理编码不一致。 |
| 2026-06-14 | 删除账户时增加持仓关联检查 | 在 `DELETE /api/ledgers/{id}/` 中增加检查：若存在关联持仓且未勾选"同时删除持仓"，返回 400 错误并提示用户先清空或迁移持仓。勾选后级联删除。 |
| 2026-06-14 | 视图函数错误响应标准化 | 将所有 `abort(400, 'msg')` 替换为 `return jsonify({'data': None, 'message': 'msg'}), 400`，确保自定义错误消息在统一响应格式中正确返回。 |
| 2026-06-13 | 策略标签独立建模，不混用自选标签 | 策略标签作用域为实际持仓，语义为"我的持仓属于什么风格"，与自选标签（"我在关注什么"）物理隔离，分别建表。两者概念不重叠，互不干扰。 |
| 2026-06-13 | 策略视图负债过滤机制 | 负债不参与任何收益或风格分析，后端 `/api/strategy/overview/` 在查询资产时自动排除 `major_category='liability'`，前端无需任何过滤代码。`/api/assets/` 接口新增 `exclude` 参数供策略视图使用，不影响其他页面。 |
| 2026-06-13 | 策略视图数据合并为单一接口 | 为避免前端四次请求的延迟，新增 `GET /api/strategy/overview/` 一次性返回持仓、资产、标签、关联关系，性能提升显著。 |
| 2026-06-13 | 浮点精度临时兜底方案 | 发现 `Float` 存储金额/数量导致市值出现 `1999.995` 等误差。短期在接口层用 `round(value×100)/100` 消除多余小数；长期将存储改为整数分（`Integer`），彻底消除浮点误差。历史数据需一次性迁移。 |
| 2026-06-13 | 投资组合 (Portfolio) 核心设计原则 | 采用「用账户隔离策略」：Ledger 关联 Portfolio，通过账户自然隔离不同策略，不拆分持仓。同一账户内多策略区分场景不予支持，引导用户创建子账户。 |
| 2026-06-13 | 移除 Portfolio.risk_level 字段 | `purpose` 已可表达投资风险倾向（如"短线博弈"），`risk_level` 与其语义重叠且无业务逻辑消费，为遵守"概念降噪"原则予以删除。 |
| 2026-06-13 | 组合收益率内部划转过滤策略 | 采用同日配对识别：同一日期、金额按分精度匹配、相反方向、两账户同属一个组合的 deposit/withdraw 双向排除，防止收益率失真。跨日划转暂不处理。 |
| 2026-06-13 | 金融数据存储精度方案 | 发现 `Float` 存储金额/数量导致市值、盈亏出现 `1999.995` 等误差。决定采用"整数分"存储（`Integer`，单位为分），彻底消除浮点误差。所有输入/输出乘以/除以 100。历史数据需一次性迁移。此为长期方案，短期保留接口层 `round(×100)/100` 作为兜底。 |
| 2026-06-12 | deposit/withdraw 不参与 XIRR 计算 | 账户资金划转（deposit/withdraw）属于内部资金调度，不是投资行为。将其作为现金流会严重拉高投入基数导致 XIRR 异常。XIRR 现金流只包含 buy、sell、dividend_cash、dividend_reinvest 四种投资交易类型 |
| 2026-06-12 | Transaction 表新增 asset_type 字段 | 为交易记录增加资产类型快照字段，与 `position_name`、`account_name` 同属快照设计模式。解决孤儿交易无法判断资产类型的问题，避免 XIRR 计算时 JOIN 表查询。历史数据通过 SQL 回填，新数据在导入时自动写入 |
| 2026-06-12 | 货币基金识别临时关键词方案 | 在元数据同步未完全覆盖所有货币基金名称前，`_fill_names_and_types` 增加临时关键词匹配（货币、现金、宝、增利、天天益）。待元数据同步覆盖率足够后移除该逻辑 |
| 2026-06-12 | 持仓详情页单持仓 XIRR 前端展示延后 | 后端接口已可用，因持仓详情页页面路径未确定，前端卡片暂未实现，记录为技术债务，延后至 P2 |
| 2026-06-11 | xalpha 概念辨析：封闭系统 vs 开放系统 | 多倍贝 用户场景是典型的开放系统（随时买卖、定投、赎回），对应 xalpha 的 `mul` 系统。净值曲线仅在无资金进出的时间段有意义，多数场景应使用 XIRR 衡量投资效果。TWR（时间加权收益率）更适合作封闭系统的业绩归因，属于 P2 功能 |
| 2026-06-11 | 货币基金/逆回购不参与收益率计算 | 货币基金、逆回购属于"活钱管理"，收益率极低且无净值波动，不纳入 XIRR 计算。其收益率在仪表盘单独展示（P2） |
| 2026-06-11 | 红利再投资的现金流处理 | 红利再投资（dividend_reinvest）视为一笔负现金流。本质是用分红金额买入更多份额，简化为一笔等额现金流出 |
| 2026-06-11 | 支付宝 PDF 解析器上线 | 支付宝基金交易确认单 PDF 通过 pdfplumber 解析，支持36列表头页与12列数据页混合提取，跨页断裂通过"有效日期前缀"精确合并；字段级拼接避免数据错乱；输出标准化为 StandardTransactionRecord 进入导入流水线 |
| 2026-06-11 | 净值接口响应结构重构 | POST /api/funds/nav/ 返回格式改为数组，每个元素包含 fund_code、unit_nav、date，增强自解释性和前端可靠性 |
| 2026-06-11 | 异步回填数据库锁解决 | 采用 WAL 模式、连接超时30s、分批写入且直接 commit 释放锁，解决多线程导入时 database is locked 问题 |
| 2026-06-11 | 持仓不足处理策略 | 导入卖出/赎回时若持仓数量不足，由 process_orphan_sell_or_withdraw 内部捕获异常并转为孤儿交易（entry_status='orphan'），保证数据不丢失，待 P1-20 定时任务自动回填 |
| 2026-06-10 | 净值获取服务独立抽取 | `get_fund_nav_map` 从视图层抽取到 `app/services/fund_data_service.py`，同时供导入 orchestrator 和 API 接口复用。数据库无净值时通过 xalpha 实时拉取并存入 `daily_worth`，后续查询直接命中 |
| 2026-06-10 | 余额宝交易统一视为活钱 | 支付宝账单中所有余额宝相关交易（转入、转出、收益发放）标记为 `asset_type='cash'`、`is_cash_transfer=True`，不产生基金持仓。收益发放、转入映射为 `deposit`，转出映射为 `withdraw`，归入活钱管理 |
| 2026-06-10 | 支付宝 CSV 分隔符确定为逗号 | 实测支付宝导出文件使用逗号分隔（非制表符），解析器统一使用 `delimiter=','` 配合 `csv.reader` 处理引号内逗号 |
| 2026-06-10 | 解析性能优化：单次 csv.reader 读取 + 分批净值查询 | 不再逐行创建 `csv.reader`，改为一次性读取所有数据行；编码检测只读取前 1KB；`_fill_missing_nav_and_shares` 按日期分组并用 `IN` 查询，每批最多 50 个代码；`daily_worth` 表增加 `(fund_code, date)` 联合索引 |
| 2026-06-10 | 基金代码匹配增强：清洗名称 + 数据库 LIKE 查询 | 不再加载全表到内存，改用 SQL `LIKE` 查询并限制返回 10 条；清洗名称去除类别词（LOF/ETF/联接/发起等）后双向匹配；多个候选时按名称长度差选最佳，相同则放弃自动匹配 |
| 2026-06-10 | 导入预览增加净值自动填充和一键确认 | 用户匹配基金代码后，前端自动调用 `/api/funds/nav/` 获取净值并计算份额，标记 `is_calculated=true`，表格显示"待确认"标签；提供"确认所有推算数据"按钮一键清除标签 |
| 2026-06-10 | 导入事务安全加固 | `commit` 方法在每处理一条记录前创建保存点（`begin_nested`），单条失败只回滚当前保存点，不影响其他已成功记录 |
| 2026-05-31 | P1-09 优先于 P1-10 | 基金交割单导入是用户数据输入的瓶颈，必须优先实现。没有准确的交易数据，年化收益率计算无法开展 |
| 2026-05-31 | 货币基金独立建表 | 货币基金的万份收益与普通基金的单位净值含义完全不同，混存会导致计算复杂、查询困难。独立建表语义清晰 |
| 2026-05-31 | 元数据同步系统采用分层更新策略 | 核心池（持仓+自选）每日更新；CSV导入按需更新；全量同步仅手动触发。避免每日全量同步 1.2 万只基金带来的资源浪费 |
| 2026-05-31 | 费率规则采用规则映射模式 | 申购/赎回费率区间（PurchaseRule / RedeemRule）与基金多对多关联（FeeRatio），规则复用减少冗余，修改时通过引用计数保护 |
| 2026-05-31 | 静默回填历史数据 | 用户新增持仓/自选时，后台异步回填该标的的历史净值/行情，使用 threading.Thread 实现，不阻塞前端 |
| 2026-05-31 | 目标代码解析统一到 Orchestrator | Job 不再自行查询持仓/自选/CSV，由 Orchestrator.resolve_targets() 统一提供，消除 Job 内部分支逻辑 |
| 2026-05-31 | 拼音全称字段冗余 | `pinyin_full` 无实际使用场景，暂不填充，保留字段供未来扩展 |
| 2026-05-29 | 简记弹窗载体由弹窗改为抽屉 | 全局可用，不打断用户工作流；QuickFab + TransactionDrawer 挂载至 Layout.vue |
| 2026-05-29 | 场外基金确认日采用后端计算 | 安装 chinese-calendar，提供 trading-days/{date} 和 fund-confirm-dates/ 两个 RESTful 端点 |
| 2026-05-29 | Ledger 增加 fee_config JSON 字段 | 股票账户存佣金/印花税等；基金账户存 subscription_discount；前端自动继承费率 |
| 2026-05-29 | 交易规则严格执行一手规则 | A 股主板/创业板 100 股整数倍；科创板 200 股起支持 1 股递增；美股 1 股起；可转债 10 张一手 |
| 2026-05-29 | 负债不参与五笔钱配置 | （已有决策，保持不变） |
| 2026-05-29 | 标签文案完全后端化 | （已有决策，保持不变） |
| 2026-05-24 | 强制绑定账户、杜绝游离数据 | （已有决策，保持不变） |
| 2026-05-20 | 全局色彩规范升级 | （已有决策，保持不变） |
