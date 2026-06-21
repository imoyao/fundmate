# ShowBuy 项目需求规格说明书

**版本**: v4.3.4
**最后更新**: 2026-06-21
**状态**: 账户详情页 UI/UX 深度重构完成；简记弹窗核心体验优化；账户列表页分组与样式统一；布局渲染问题修复；资产录入 `ledger_id` 问题定位，待应用修复。

**核心原则**: 本项目为**个人使用、本地优先、完全合规**的投资记账工具。

**文档属性**: 项目唯一事实标准，所有开发必须严格遵守，禁止私自变更规则。本版本保留**全量决策细节、进度追溯、技术细节、踩坑记录**，用于长期维护、后期回忆、迭代复盘。

## 更新记录

| 版本 | 日期 | 变更说明 |
|------|------|---------|
| **v4.3.4** | **2026-06-21** | 前端账户详情页 UI/UX 深度重构：卡片矩阵布局重设计（涨红跌绿强制规范）；新增资产配置环形图（`getComputedStyle` 动态读取 CSS 变量）；抽取 `PositionTransactionsDrawer.vue` 独立抽屉组件替换行内展开；修复 `<Transition>` 单根节点警告；简记弹窗优化：买入/卖出 Tab 切换、金额/份额 prepend 插槽、账户缩写标签、交易日期与下单时间合并、手续费智能折叠、基金卖出浮点精度修正、极简创建账户增加类型选择；账户列表页分组标题汇总信息、类型缩写 Badge、未归置卡片恢复；修复 Layout 中 `LayHeader` 渲染导致抽屉无法弹出的问题；`ledger_id` 缺失定位（简记弹窗已修复、资产录入方案已出）。 |
| v4.3.3 | 2026-06-18 | 代码审查发现 8 个遗留 Bug/缺失：SQL 聚合市值分母错误、Python/SQL 数据单位混用导致市值放大 100 倍、`get_ledger_summary` 分支逻辑错误（bank/property 无数据）、货基统计传参错误、`delete_ledger`/`migrate_positions` 未适配 `ledger_id`、前端响应解析路径不匹配、列表接口缺摘要字段；修正技术债务和进度描述；新增「放弃 SQL 聚合」决策 |
| v4.3.2 | 2026-06-18 | 账户体系重构：`positions`、`transactions`、`assets` 新增 `ledger_id` 外键并回填数据；新建 `LedgerService` 提取业务逻辑；`overview` 改用 SQL 聚合；全面切换基于 `ledger_id` 的查询与写入；统一账户类型为 `bank/stock/fund/property`；修复 28 个测试；前端 API 层扩展；页面重构待继续 |
| v4.3.1 | 2026-06-16 | 修复金融精度改造后续数据混合问题、修复 SafeNumeric 类型适配、修复 XIRR 测试断言、修复交易时间范围测试、新增 `Ledger.ledger_type` 缺少 `property` 类型等技术债务条目；新增版本号管理规范 |
| v4.3   | 2026-06-16 | 金融精度改造完成：所有金额/价格字段改为Integer存储分（元×100），份额字段改为Integer存储最小单位（份×10000），净值字段改为Decimal(18,6)；新增`Money`精度转换工具类；改造全部写入/读取路径；数据迁移脚本；修复前端账户详情页显示异常（数据混合问题）；编写全链路精度测试；技术债务新增接口性能优化、`confirm_date`回填、`type`列空值等 |
| v4.2.1 | 2026-06-14 | 持仓管理增强：交易明细下钻（行点击展开）、持仓删除（可选清理关联交易）、费率编辑（证券/基金类型折叠面板）、批量迁移端点（`POST /api/ledgers/{id}/migrations/`）；新增 `transactions.symbol` 字段作为不可更改快照；前端表格合并规范（名称/代码/类型复合列）；修复删除弹窗误删 Bug；测试用例补全（持仓交易明细、删除持仓、批量迁移）；更新进度总览、技术债务、决策记录与核心文件清单 |
| v4.2   | 2026-06-14 | 账户管理重构：资金全景卡片（净资产/分类汇总/游离提示）、账户列表按类型分组、关联现金账户（`linked_cash_ledger_id`）及校验、删除保护（有持仓禁止删除）；引入 `CURRENT_USER_ID` 常量统一用户隔离、`LEDGER_TYPE_LABELS` 映射；视图函数错误响应标准化（`return jsonify`）；技术债务新增 overview 聚合性能风险、`fee_config` 重复逻辑；测试用例补全（关联现金、overview 等 46 个用例全通过） |
| v4.1   | 2026-06-13 | P1-12 投资组合后端编码完成，策略视图上线（含标签管理、分组展示、负债过滤、浮点精度临时兜底）；策略标签 CRUD 与 overview 接口；组合详情页增加持仓明细、收益率自动加载、全量排序、账户关联选择与已关联组合标签展示；技术债务新增浮点精度、type 列空值、跨日划转过滤、Ledger views 重构；测试用例覆盖策略标签 10 个场景 |
| v4.0   | 2026-06-13 | P1-12 Portfolio 后端编码完成：数据模型实现（砍掉 risk_level 冗余字段）、CRUD API 上线（含软删除自动解绑账户）、Ledger 关联字段实现、组合收益率计算扩展（含内部划转过滤）、XIRR 端点扩展 portfolio_id 参数；更新进度总览、技术债务（新增 Ledger views 重构需求）、决策记录与核心文件清单 |
| v3.9   | 2026-06-13 | P1-12 投资组合设计完成；交易规则引擎重构；测试修复 |
| v3.8   | 2026-06-12 | P1-10 年化收益率核心功能上线：XIRR 计算引擎（pyxirr + 纯 Python 兜底）、单持仓与组合维度 API、前端仪表盘展示；`Transaction` 表新增 `asset_type` 字段支持资产类型过滤；现金流规则修正（排除 deposit/withdraw）；货币基金识别临时关键词方案；`confirm_date` 语义修复（positions 表 purchase_date → confirm_date）；导入模块测试全面通过；更新进度总览、技术债务、决策记录与核心文件清单 |
| v3.7   | 2026-06-11 | 补充历史讨论遗漏内容：基于 Quicken 对标分析新增 P2 功能（按平台分组统计盈亏、交易记录全量导出、隐私保护）；新增投资组合管理（Portfolio）规划；新增持仓分布可视化规划；补充 xalpha 概念辨析决策记录；更新进度总览和技术债务 |
| v3.6   | 2026-06-11 | 支付宝 PDF 解析器上线（支持跨页合并、净值计算）；基金净值接口修复与响应重构（返回数组）；异步回填锁冲突修复（WAL 模式、超时、分批提交）；持仓不足自动转为孤儿交易；前端交互优化（重复行按钮、抽屉关闭）；腾讯理财通评估为复杂格式，记录为技术债务；新增 PDF 解析器全覆盖测试；更新任务进度、技术债务、决策记录与核心文件清单 |
| v3.5   | 2026-06-10 | 导入系统全面完善：支付宝解析器上线、净值自动填充功能实现、基金代码匹配抽屉交互完成、前端组件轻量重构、`enrich` 逻辑拆分与优化、净值获取服务抽取独立模块、事务安全加固、性能大幅提升；更新任务进度、技术债务、决策记录与核心文件清单 |
| v3.4   | 2026-06-06 | 导入系统架构全面重构完成：删除旧 TransactionParser 和 StandardCompatParser，所有解析器迁移至新架构；哈希规则全局统一；commit 分支使用 BusinessType 枚举消除魔术字符串；dividend_cash/dividend_reinvest 分支完善；修复 net_amount 传递及 skipped 计数 bug；导入测试全部通过 |
| v3.3   | 2026-05-31 | 货币基金万份收益计算与独立存储完成；费率规则表、基金详情补充、静默回填全部落地；决策优先级调整：P1-09（基金交割单导入）优先于 P1-10（年化收益率）；技术债务更新 |
| v3.2   | 2026-05-31 | 元数据同步系统全面重构：基类统一流程，目标代码解析上提到Orchestrator，引入分层更新（核心池/全量/CSV导入），新增费率规则表、基金详情补充Job、静默历史数据回填、人类可读同步摘要输出；更新任务进度、技术债务、决策记录 |
| v3.1   | 2026-05-29 | 简记弹窗全面重构完成；Ledger 模型扩展；交易规则落地；交易日校验与基金确认日 API 上线；基于 Quicken 对标分析新增 P2 功能规划 |
| v3.0   | 2026-05-24 | 原始完整版 |

# 1. 项目概述

## 1.1 项目愿景

为个人投资者提供一个安全、私密、可长期维护的全资产记账与投资分析工具，标准化解决两大核心问题：「我的全部资产分布在哪里」「我的投资收益与行为如何复盘优化」。区别于普通记账工具，本项目主打**数据绝对私有、投资分析专业、全资产全覆盖**。

## 1.2 核心价值主张

- **绝对数据主权**：全量数据本地 SQLite 存储，不上云、不采集、不泄露，用户100%掌控自有数据，无第三方数据风险
- **绝对合规性**：仅支持手动逐条录入、标准 CSV/JSON 文件导入，全程无自动登录券商、无爬虫抓包、无接口窃取数据等违规行为，完全合规
- **记账+分析闭环**：不止流水记录，支持基金持仓穿透、组合年化计算、收益复盘、风险集中度分析、配置目标优化，形成投资闭环
- **全资产统一管理**：统一覆盖股票、基金、ETF 交易资产，同时兼容现金、固收、房产、保险、应收、负债等广义资产，真正做到「一张表看全身家」

## 1.3 技术栈规范

- **后端**：Python 3.12+、APIFlask、SQLAlchemy 2.0 原生ORM、SQLite（本地开发）。统一手动返回 `{data, message}` 结构，不依赖自动范式，为未来平滑迁移 FastAPI 预留架构空间
- **前端**：Vue3 + Vite + TypeScript、pure-admin-thin 骨架、Element Plus 组件库、ECharts 可视化
- **代码质量规范**：后端 ruff 静态校验，前端严格遵循 pure-admin 官方编码与目录规范
- **数据源体系**：xalpha（主力基金净值/分析引擎）+ AKShare（证券行情备用），通过统一 DataSourceAdapter 防腐层封装，隔离第三方接口变更

# 2. 全局强制设计规范（不可变更、永久追溯）

本章节所有规则为**硬性红线约束**，所有开发、迭代、重构、UI 修改必须严格遵守，禁止私自变通。所有规则均来自实际踩坑复盘，用于规避重复问题。

## 2.1 数据合规与安全规范

- 合法录入渠道仅两种：用户手动 Web 表单录入、用户自行上传标准结构化文件导入
- 系统全程无任何自动爬取、自动登录、自动抓包、自动同步券商数据逻辑，永久禁用

## 2.2 核心业务分层规范（核心架构边界）

- **positions（交易资产）**：可实时买卖、有市价波动的金融资产（股票、基金、ETF、可转债），所有可交易持仓统一入此表
- **assets（非交易资产/负债）**：无法实时交易、静态盘点类资产/负债（现金、房产、理财、保险、应收、信用卡负债、房贷）
- API-First 严格契约：前后端接口字段、参数、状态码、分页结构一经定型，禁止私自修改
- 渐进式交付：优先保障核心数据正确、流程闭环，再迭代体验与美化

## 2.3 用户体验通用原则

- 30秒全局原则：首页仪表盘可在30秒内让用户掌握总资产、盈亏、配置分布核心信息
- 分层信息架构：高频操作入口浅、步骤少；低频复杂分析功能深层级，保证日常使用轻量化

## 2.4 重构与版本兼容强制规范

- 任何后端重构、服务层抽取、代码优化，**对外 API 必须完全兼容**，请求参数、响应字段、嵌套结构、状态码不可变动
- 前端筛选参数、分页参数、类型枚举参数属于全局契约，变更必须同步更新前端、测试、文档并记录 Breaking Change

## 2.5 测试强制规范

- 新增接口、重构接口必须覆盖：正常增删改查、边界值、空数据、异常报错、权限/状态分支
- 业务逻辑变更必须同步更新测试用例，提交前 pytest 全量通过方可合并

## 2.6 RESTful 与 URL 统一规范

- 所有 API 端点强制尾部斜杠，杜绝 308 重定向导致的前端异常
- 资源名词复数化，URL 不包含动词，动作语义由 HTTP Method 表达
- 嵌套资源严格遵循层级语义，保证接口可读性与统一性

## 2.7 全局命名规范

- 模型类必须带领域前缀（WatchlistItem / FundManager），杜绝全局命名冲突
- 所有变量、参数禁止单字母缩写，语义自解释
- Pydantic Schema 严格对齐模型字段，后缀区分 Create / Update / Out
- 蓝图变量名绑定业务领域，清晰可维护

## 2.8 第三方库与工具类开发规范

- 仅调用第三方库官方公开稳定 API，禁止编造参数、私有方法、不存在属性
- 所有工具函数、转换器、解析器必须编写完整单元测试，覆盖正常、异常、空值、边界场景

## 2.9 业务永久锁定决策（可回溯细节）

- **配置目标优先级（五笔钱）**：Ledger账户默认目标 → 导入流水单行配置覆盖 → Position持仓最终生效，三层优先级不可逆
- **首页快速记账限制**：首页弹窗仅开放股票/基金简单买卖，分红、定投、划转、复杂调仓统一引导至全面盘点页面，防止简易录入造成数据不规范
- **导入与录入强制绑账户**：所有资产新增、文件导入必须选择已有 Ledger 账户，彻底杜绝游离资产、孤儿数据
- **标签唯一数据源后端化**：所有类型标签、配置标签文本全部由后端枚举输出 label，前端只展示不翻译，彻底杜绝前后端文案不一致
- **负债隔离规则**：负债属于资产负债表减项，无增值属性，不参与五笔钱配置、不参与资产配置统计、不参与收益分析

## 2.10 资产正负值统一流转规范（零歧义核心规则）

全局唯一数值标准，所有统计、计算、图表、入库必须严格遵循，杜绝正负混乱：

1. **用户录入层**：资产、负债全部录入正数，用户无需理解正负逻辑，降低出错率
2. **后端存储层**：后端根据资产大类自动转换，资产存正、负债存负
3. **接口输出层**：统一输出 `signed_amount` 字段，作为唯一计算字段
4. **业务计算层**：总资产、净值、盈亏、占比、图表汇总，**只使用 signed_amount**，前端禁止二次运算正负
5. **界面展示层**：负债文本展示可用绝对值美化，颜色风险化区分，但不改变计算数据源

## 2.11 金融数据精度强制规范（新增）

> 所有直接关联用户资金的字段，必须使用整数存储分（最小货币单位）或最小份额单位，禁止使用 float/double。非资金类字段（如基金净值）使用 DECIMAL 精确存储。所有读写操作必须通过 `Money` 工具类进行单位转换，禁止在业务代码中直接进行乘除运算。

# 3. 前端 UI 全局强制统一规范（根治样式杂乱、长期可维护）

本章节为项目**UI 统一强制标准**，用于彻底解决页面丑陋、风格割裂、随意写样式、新旧页面不统一的问题，所有组件、页面、样式必须遵守。

## 3.1 色彩体系零硬编码规范

- 全局禁止任何 `#xxxxxx` 十六进制色值硬编码，全部使用 `colors.css` 语义变量
- 金融涨跌色固定：涨红、跌绿，完全贴合国内用户习惯，禁止反色、自定义色
- 功能色固定：主色、成功、警告、危险、信息色全局统一
- 标签、图表、分类配色统一使用项目12色莫兰迪色板，保证全站视觉一致性

## 3.2 布局、间距、圆角、对齐强制统一

- **对齐**：所有行内组合（输入框+按钮+选择器）统一垂直居中，无顶部/底部对齐乱象
- **间距阶梯**：仅允许 12px / 16px / 24px / 32px 四档间距，禁止 10px、14px、15px 等非标间距
- **圆角阶梯**：仅 8px（常规组件）、16px（大卡片弹窗）两档，无异形圆角
- **卡片标准**：纯白背景、标准圆角、柔和统一阴影，无自定义卡片样式

## 3.3 表单全局统一规范

- 全局表单统一 large 尺寸，44px 标准行高，禁止尺寸混用
- 标签居中对齐、辅助文字统一色值与字号
- 聚焦样式统一：主色边框+透明阴影，无自定义聚焦效果
- 必填星号危险色、选填标签弱化色，全站统一

## 3.4 按钮层级视觉规范（固定权重）

- 主按钮：实心主色，用于保存、提交、确认、刷新核心操作
- 次按钮：边框透明，用于重置、取消、新增辅助操作
- 文本按钮：仅文字变色，用于极次要操作
- 所有 hover、active 效果全局统一，禁止自定义动效

## 3.5 文字层级固定规范

- 一级文本（标题、核心数据）：主色文本
- 二级文本（正文、列表、标签）：次要文本
- 三级文本（备注、时间、说明）：弱化文本

## 3.6 图标与资源规范

- 全站禁止 Emoji 表情，保持专业工具调性
- 所有图标统一使用 IconifyIconOffline，禁止混杂图片图标、本地svg

## 3.7 页面结构统一模板

所有功能页面强制统一结构：页面标题+描述说明 → 筛选/操作区 → 核心卡片容器 → 表格/表单主体 → 底部操作按钮，杜绝结构混乱。

## 3.8 持仓/资产列表通用展示规范

- **复合列强制合并**：所有展示持仓或资产的表格，必须将“名称、代码、资产类型”合并为单一复合列。名称使用大号字体，代码使用小号灰色字体前缀 `#`，资产类型以标签形式内联展示。参照导入页 `Inventory.vue` 中的产品单元格样式。
- **交易明细下钻规范**：持仓明细表格支持点击行展开关联交易记录，交易明细显示在表格下方的独立区域，形成主-从视图。

# 4. 开发踩坑准则（长期维护避坑、细节追溯）

## 4.1 问题诊断准则

异常排查优先打印数据、核对数据库、核对路由注册、核对请求参数，**禁止盲猜改代码**，所有问题必须数据定位。

## 4.2 测试数据库隔离准则

所有测试必须共用统一 db fixture，禁止直接导入 SessionLocal，避免测试内存数据库不互通、数据查不到的隐性Bug。

## 4.3 模型-Schema 联动准则

模型增删改字段，必须同步更新所有关联 Out/Create/Update Schema，字段不一致=严重Bug。

## 4.4 重构彻底性准则

重构完成必须全局搜索旧字段、旧函数、旧路由、旧变量，彻底清除残留代码，避免隐性冲突。

## 4.5 前端接口封装准则

所有请求统一封装在 src/api，组件内禁止直接写 http、axios 原生调用。

## 4.6 数据库变更准则

模型结构变更后，开发环境必须重建数据库文件，保证表结构完全同步。

## 4.7 体验优化时间盒准则

非功能性UI优化单次最长2小时，超时直接归档 IDEAS.md，不阻塞主线功能迭代。

## 4.8 路由与组件名强一致准则

组件 defineOptions.name 必须与路由 name 完全一致，否则 keep-alive 缓存失效、页面白屏。

# 5. 核心数据模型完整规范（可维护细节版）

## 5.1 positions 可交易持仓资产

核心存储用户股票、基金、ETF 持仓，记录成本、数量、配置目标、归属账户，是收益计算、配置分析的核心数据源。关键字段：symbol、name、market、asset_type、account_name、quantity、avg_price、current_price、confirm_date、allocation、snapshot 相关审计字段。

**精度规范**（v4.4）：`quantity` 为 Integer，存储最小份额单位（份×10000）；`avg_price` 和 `current_price` 为 Integer，存储分（元×100）。所有读写通过 `Money` 工具类转换。

## 5.2 transactions 交易流水

存储每一笔买入、卖出、分红、定投记录，保留 position_name、account_name 快照。新增 `symbol` 字段作为资产代码快照（不可更改），新增 `asset_type` 字段作为资产类型快照，用于过滤和统计。目的：持仓删除后，历史流水不丢失，保证复盘数据永久可追溯。

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | String(30) | 资产代码快照，不可更改，用于关联查询和盈亏曲线 |
| asset_type | String(20) | 资产类型快照，用于过滤和统计 |
| position_name | String(100) | 持仓名称快照 |
| account_name | String(100) | 账户名称快照 |

**精度规范**（v4.4）：`price`、`amount`、`fee` 为 Integer，存储分；`quantity` 为 Integer，存储最小份额单位。

## 5.3 assets 通用资产负债表

承载全量非交易资产与负债，是资产全景视图的底层支撑。核心区分：amount（用户原始录入正数）、signed_amount（系统计算唯一统计字段）。负债统一归入此类，不进入持仓体系。

**精度规范**（v4.4）：`amount` 为 Integer，存储分。

## 5.4 金融元数据体系

securities、funds、fund_companies、managers、fund_managers、daily_worth 全套基础金融数据，支撑搜索、行情刷新、净值获取、持仓穿透。

**精度规范**（v4.4）：`daily_worth.unit_nav` 和 `acc_nav` 改为 `DECIMAL(18,6)`，避免浮点误差。

## 5.5 自选关注体系

分组、标签、资产关联、异动提醒、清仓持仓快照，支撑用户自定义资产监控体系。

## 5.6 数据分析扩展模型

price_history 历史行情、benchmark_indices 基准数据、user_preferences 用户偏好、review_notes 复盘笔记，为年化、回撤、对比回测提供数据底座。

## 5.7 代码标准化工具

所有市场代码统一归一化，自动识别沪/深/港/美基金代码，统一格式后再请求数据源，避免多格式导致的数据丢失。

## 5.8 费率与规则模型

### 5.8.1 purchase_rules（申购费率规则）

存储按金额区间的申购/认购费率阶梯。关键字段：start_quota（起始金额，包含）、end_quota（结束金额，不包含，NULL 表示正无穷）。**精度规范**（v4.4）：`start_quota`、`end_quota` 为 Integer，存储分。

### 5.8.2 redeem_rules（赎回费率规则）

存储按持有天数区间的赎回费率阶梯。关键字段：start_day（起始天数，包含）、end_day（结束天数，不包含，NULL 表示正无穷）。

### 5.8.3 fee_ratios（基金费率关联表）

关联基金与费率规则，存储具体费率值。关键字段：fund_code、fee_type（purchase/redeem/management）、rate（费率百分比）、fee_amount（固定金额，与 rate 互斥）、purchase_rule_id、redeem_rule_id。**精度规范**（v4.4）：`rate` 改为 `DECIMAL(10,6)`，`fee_amount` 改为 Integer 存储分。

**设计要点**：
- 相同区间的规则被多只基金复用，减少冗余。
- 创建规则前先查询是否已存在完全相同的规则，存在则复用，不存在则新增。
- 修改规则时检查引用计数：引用数 > 1 时创建新规则，引用数 = 1 时可原地修改。

## 5.9 基金表新增字段

- `is_active`：是否参与净值同步，默认 True。连续失败3次后自动标记为 False。
- `last_nav_check`：最后一次净值检查时间。
- `nav_fail_count`：连续获取净值失败次数。
- `pinyin_abbr`：拼音首字母简拼（仿天天基金规则），用于搜索。

## 5.10 货币基金独立净值模型

### 5.10.1 money_fund_daily_worth（货币基金每日万份收益）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| fund_code | String(6) | 基金代码 |
| date | Date | 日期 |
| nav_per_10k | **Integer** | 万份收益（分） |
| annual_return_7d | Float | 七日年化收益率（暂不计算），精度校验 round(value, 4) |

**万份收益计算**：从 `xalpha.mfundinfo().price` 的累计净值反向计算 `(今日累计净值 - 昨日累计净值) × 10000`，四舍五入保留 4 位小数。

**设计原因**：
- 货币基金无单位净值概念，与普通场外基金的数据结构完全不同。
- 混合存储会导致字段语义混乱，影响后续收益率计算和统计。
- 独立建表可复用普通基金的去重、分批写入等基础设施。
-
**精度规范**（v4.4）：`nav_per_10k` 改为 Integer 存储分。`annual_return_7d` 保留 Float，但写入前强制 `round(value, 4)` 控制精度。

## 5.11 投资组合 (Portfolio)（已实现）

**设计定位**：回答“我的钱按什么策略投资”。与 Ledger（账户：钱放哪里）和 Allocation（五笔钱：风险等级）互补，为可选的高级分析工具。

**核心约束**：
- 一个 Ledger 最多关联一个 Portfolio（多对一），不拆分持仓。
- 组合收益率 = 合并关联 Ledger 的现金流后计算 XIRR，自动过滤内部划转。
- 渐进暴露，默认隐藏入口，不侵入记账主流程。

### 5.11.1 portfolios 表（已实现）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer | 主键 |
| name | String(100) | 组合名称（必填） |
| description | String(500) | 组合描述 |
| purpose | String(200) | 投资目的，如“养老金”（原 Objective 概念降级并入） |
| target_return | Numeric(5,2) | 年化目标收益率（%） |
| target_amount | Numeric(15,2) | 目标金额 |
| target_date | Date | 目标日期 |
| benchmark | String(50) | 基准指数（如 CSI300） |
| is_deleted | Boolean | 软删除标记（默认 False） |
| created_at / updated_at | DateTime | 时间戳 |

> 注：原计划中的 `risk_level` 字段已移除，`purpose` 已能表达风险偏好，避免概念重叠。

### 5.11.2 ledgers 表新增字段（已实现）

| 字段 | 类型 | 说明 |
|------|------|------|
| portfolio_id | Integer (FK) | 关联 portfolios 表，`ON DELETE SET NULL`，删除组合时自动解绑 |
| linked_cash_ledger_id | Integer (FK) | 关联的现金账户（仅 stock/fund 类型可用），`ON DELETE SET NULL` |

**注**：原计划添加的 `objective` 字段已移除，语义与 `Portfolio.purpose` 重叠，精简模型。

### 5.11.3 策略标签（持仓风格分析）（已实现）

**设计定位**：纯展示层分析工具，用于按投资风格（如“成长”“价值”“大盘”）分类查看持仓。不参与 XIRR 计算，不影响 Portfolio 资金流隔离逻辑。

**数据模型**：
- `strategy_tags` 表：`id / name（UNIQUE）/ created_at`
- `position_strategy_tags` 关联表：`position_id (FK → positions.id, ON DELETE CASCADE) / strategy_tag_id (FK → strategy_tags.id, ON DELETE CASCADE)`，联合唯一约束
- 与自选标签物理隔离，互不干扰

**API 端点**：
- `GET/POST /api/strategy/` — 标签列表、创建
- `DELETE /api/strategy/{id}/` — 删除标签（级联解绑）
- `POST/DELETE /api/strategy/{tag_id}/positions/{position_id}/` — 绑定/解绑
- `GET /api/strategy/relations/` — 获取全部持仓-标签关联映射
- `GET /api/strategy/overview/` — 策略视图全局数据（持仓、资产、标签、关联一次返回）

**消费场景**：策略视图页 `/asset/strategies`，按标签分组展示持仓，含汇总卡片和分组内分页。负债已在后端自动过滤。

## 5.12 账户类型与资产归属规范（v4.3.1 最终确定）

### 5.12.1 账户类型定义

系统仅支持四种账户类型，不再增减：

| 类型 | 标识 | 含义 | 示例 |
|------|------|------|------|
| 银行账户 | `bank` | 一张具体的银行卡，承载该卡内所有资产（活期、货币基金、银行理财、通过该行购买的基金等） | "招商银行卡(6214)" |
| 证券账户 | `stock` | 券商账户，承载股票、ETF、可转债等交易所资产 | "华泰证券" |
| 场外基金平台 | `fund` | 独立基金销售平台，承载场外公募基金 | "支付宝基金""天天基金" |
| 实物资产 | `property` | 房产、车辆、黄金、收藏品等非金融资产 | "家庭房产" |

### 5.12.2 核心规则（硬规则，无智能判断）

1. **同账户内操作**：用户在同一个 `bank` 账户内记"买入理财"，系统视为**资产形态转换**（活期→理财），不生成出入金流水。
2. **跨账户操作**：资金离开当前账户时，用户必须使用"转账"操作关联两个账户，系统生成标准转账流水。
3. **用户自主决策**：系统不判断"银行体系内外"。用户通过选择账户和操作类型，自然决定资金流向规则。

### 5.12.3 银行渠道买基金的归属

用户通过银行 App 直接购买的基金（钱未离开银行卡），持仓直接记录在该银行卡账户下，不单独创建 `fund` 账户。交易记录的 `source` 字段标记购买渠道（如"招商银行"）。

### 5.12.4 交易类型（固定，不膨胀）

`bank` 账户仅支持 5 个通用操作：`存入活期` / `取出资金` / `买入理财` / `赎回理财` / `转账`。

用户选择"买入理财"后，自由输入：资产名称（如"朝朝宝"）、资产类型（从 6 个通用标签中选择）、金额。

### 5.12.5 资产类型标签

预设 6 个通用标签：`活期存款` / `货币基金` / `定期理财` / `债券基金` / `股票基金` / `混合资产`。用户可在设置中手动新增自定义标签（如"黄金积存"），系统不自动新增。

### 5.12.6 防错提示原则

仅对不可逆操作（删除账户、删除持仓、大额转账）进行二次确认。日常记账操作不弹出"你是不是想选另一个操作"类提示——用户选什么就执行什么。

# 6. 第三方集成架构（xalpha 完整边界定义）

- **职责边界**：仅负责外部数据获取、净值解析、组合数学计算，不参与业务入库、不参与前端交互、不参与权限逻辑
- **缓存策略**：独立文件夹本地缓存，与业务数据库物理隔离，可手动清理（xalpha 使用 `xa.set_backend("csv", path="data/xalpha_cache")` 启用）
- **调用方式**：全部通过后端 adapter 层统一封装，业务层不直接裸调用第三方库
- **容错策略**：失败重试、超时处理、数据异常兜底，保证系统稳定性

# 7. 高级能力设计细节

## 7.1 持仓穿透冷热分层设计

热数据（持仓+流水）实时读写；温数据（穿透明细）定时缓存、过期刷新；冷数据（历史行情）归档存储，平衡速度、性能、时效性。

## 7.2 旧项目架构继承说明

完整继承 fundmate 核心设计：枚举体系、基金经理多对多、自选体系、费率体系思想，重构后架构更干净、可扩展、无历史技术债。

## 7.3 元数据同步系统设计

### 7.3.1 分层更新策略

同步目标按优先级分为三层：
1. **核心池**（每日更新）：用户持仓 + 自选标的
2. **CSV导入池**：通过 `--target-file` 参数指定
3. **全量池**：`--full-sync` 时触发全市场同步

### 7.3.2 基类重构（v2.0）

`SyncJob` 基类统一流程：
- `run(full_sync, targets)` 不再被子类覆盖。
- 分批逻辑内置，子类只需设置 `batch_size`。
- 空数据保护通过 `_allow_empty_data` 控制。
- 目标代码由 `DataSyncOrchestrator.resolve_targets()` 统一解析后注入。

### 7.3.3 静默历史数据回填

用户新增持仓或自选标的时，后台异步回填该标的的全部历史净值/行情。使用 `threading.Thread` 实现，不阻塞前端请求，失败静默处理。

### 7.3.4 基金详情补充任务

`FundDetailEnrichJob` 负责补充核心池基金的分类、公司、风险等级、成立日期、业绩基准、拼音简拼、费率规则等静态信息。数据源：`ak.fund_info_ths`（详情） + `xalpha.fundinfo`（费率）。

### 7.3.5 人类可读同步摘要

每次同步完成后，输出自然语言格式的摘要报告，包含：各任务成功/失败状态、新增/跳过记录数、失败原因。

# 8. 核心 API 完整端点清单（可对接追溯）

|方法|接口路径|功能说明|
|---|---|---|
|GET/POST|/api/positions/|持仓列表查询、新增持仓|
|PATCH/DELETE|/api/positions/{id}/|更新、删除单条持仓（支持 `delete_transactions` 参数）|
|**GET**|**/api/positions/{id}/transactions/**|**获取持仓的关联交易明细**|
|GET|/api/transactions/|交易流水分页筛选查询|
|GET/POST|/api/assets/|通用资产负债查询（支持 `exclude` 参数排除负债）、新增|
|PATCH/DELETE|/api/assets/{id}/|更新、删除通用资产|
|GET|/api/summary/|仪表盘总资产汇总数据|
|GET|/api/funds/search/|基金模糊搜索|
|GET|/api/funds/managers/search/|基金经理搜索|
|GET|/api/securities/search/|证券股票搜索|
|GET/POST|/api/watchlist/items/|自选资产列表、新增|
|PATCH/DELETE|/api/watchlist/items/{item_id}/|更新、删除自选|
|GET/POST|/api/watchlist/groups/|自选分组列表、创建|
|PATCH/DELETE|/api/watchlist/groups/{group_id}/|更新、删除分组|
|POST/DELETE|/api/watchlist/items/{item_id}/groups/{group_id}/|资产绑定/解绑分组|
|GET/POST|/api/watchlist/tags/|标签列表、创建|
|DELETE|/api/watchlist/tags/{tag_id}/|删除标签|
|POST/DELETE|/api/watchlist/items/{item_id}/tags/{tag_id}/|资产绑定/解绑标签|
|POST|/api/funds/nav/|基金净值批量查询（响应格式为数组）|
|GET|/api/performance/xirr/|年化收益率查询（扩展 `portfolio_id` 参数，支持组合维度 XIRR）|
|**GET/POST**|**/api/portfolios/**|**组合列表（返回 id/name/purpose/created_at）、创建组合**|
|**GET/PATCH**|**/api/portfolios/{id}/**|**获取详情、更新组合**|
|**DELETE**|**/api/portfolios/{id}/**|**软删除组合（自动解绑关联账户）**|
|**GET**|**/api/portfolios/{id}/holdings/**|**组合持仓明细（聚合关联账户的 positions + assets）**|
|PATCH|/api/ledgers/{id}/|更新账户时已支持设置 `portfolio_id`、`linked_cash_ledger_id`、`fee_config`|
|**GET**|**/api/ledgers/overview/**|**账户资金全景（按类型分组市值、负债、净资产、已删除账户）**|
|**POST**|**/api/ledgers/{id}/migrations/**|**批量迁移持仓到同类型目标账户**|
|**GET/POST**|**/api/strategy/**|**策略标签列表、创建**|
|**DELETE**|**/api/strategy/{id}/**|**删除策略标签（级联解绑）**|
|**POST/DELETE**|**/api/strategy/{tag_id}/positions/{position_id}/**|**持仓绑定/解绑策略标签**|
|**GET**|**/api/strategy/relations/**|**获取全部持仓-标签关联映射**|
|**GET**|**/api/strategy/overview/**|**策略视图全局数据（持仓、资产、标签、关联，一次返回）**|

> 注：`/api/portfolios/{id}/summary/` 组合概览端点计划在 P2 实现，当前不提供。

# 9. 项目四象限路线图 & 完整进度表（2026-06-16 更新）

## 9.1 四象限优先级定义（永久标准）

- **第一象限｜重要且紧急**：阻塞核心流程、产生数据错误、影响上线的任务，48小时内闭环
- **第二象限｜重要不紧急**：决定产品核心价值、长期能力的功能，固定排期迭代
- **第三象限｜不重要但紧急**：临时环境、依赖、报错问题，极简快速修复
- **第四象限｜不重要不紧急**：UI美化、细节打磨、远期创意，统一延后归档

### 9.2 完整 P1 任务进度总表

| 编号 | 任务名称 | 状态 | 重要度 | 紧急度 | 象限 | 说明 |
|------|---------|------|--------|--------|------|------|
| P1-03 | 全面盘点导入页面 | **✅ 已完成** | ⭐⭐⭐⭐⭐ | 🔴 | Ⅰ | UI 重构、批量修正、配置目标分组全部完成 |
| P1-04 | 股票/基金元数据填充 | **✅ 已完成** | ⭐⭐⭐⭐⭐ | 🔴 | Ⅰ | 搜索接口可用 |
| P1-02 | 简记弹窗强化 | **✅ 已完成（重构版）** | ⭐⭐⭐⭐⭐ | 🔴 | Ⅰ | 抽屉重构、买入/卖出分离、金额/份额切换、费率预设、一手规则、交易日校验、基金确认日 |
| — | 债券利息+扣税关联 | **✅ 已完成** | ⭐⭐⭐⭐⭐ | 🔴 | Ⅰ | link_group_id + 树形展示 |
| — | 现金管理产品识别 | **✅ 已完成** | ⭐⭐⭐⭐ | 🔴 | Ⅰ | money_fund / reverse_repo |
| — | 导入事务一致性修复 | **✅ 已完成** | ⭐⭐⭐⭐⭐ | 🔴 | Ⅰ | 全部成功或全部回滚 |
| — | 后端标签统一 | **✅ 已完成** | ⭐⭐⭐⭐ | 🟡 | Ⅰ | type_label / allocation_label 后端化 |
| — | Ledger 模型扩展 | **✅ 已完成** | ⭐⭐⭐⭐ | 🟡 | Ⅱ | ledger_type + fee_config JSON + linked_cash_ledger_id |
| — | 交易日校验与基金确认日 API | **✅ 已完成** | ⭐⭐⭐⭐ | 🟡 | Ⅱ | trading-days/{date} / fund-confirm-dates/ |
| P1-07 | price_history 历史行情填充 | **✅ 已完成** | ⭐⭐⭐⭐⭐ | 🟡 | Ⅱ | 已实现全量/增量同步、分批写入、断点续传 |
| — | 元数据同步系统重构 | **✅ 已完成** | ⭐⭐⭐⭐⭐ | 🔴 | Ⅰ | 基类统一流程、分层更新、费率规则表、静默回填、人类可读摘要、货币基金独立表 |
| **P1-09** | **基金交割单导入模板 + 解析器** | **🔄 核心完成，收尾完成** | ⭐⭐⭐⭐⭐ | 🔴 | Ⅰ | 天天基金解析器上线、支付宝解析器上线（含余额宝现金处理、基金代码自动匹配、净值自动填充）；同花顺股票解析器稳定；支付宝 PDF 解析器上线（支持跨页合并、净值计算）；基金代码匹配抽屉交互完成；前端组件轻量重构；净值获取服务已抽取为独立模块；导入预览页面增加净值自动填充和一键确认功能；持仓不足自动转为孤儿交易；腾讯理财通待后续支持 |
| **P1-10** | **组合年化收益率计算（XIRR）** | **🔄 后端完成，前端仪表盘卡片上线** | ⭐⭐⭐⭐⭐ | 🟡 | Ⅱ | XIRR 计算引擎（pyxirr + 纯 Python 兜底）已上线，支持组合整体维度；`Transaction` 新增 `asset_type` 字段支持资产类型过滤；现金流规则已修正（排除 deposit/withdraw）；前端仪表盘年化收益率卡片已展示；持仓详情页单持仓 XIRR 前端延后 |
| **P1-12** | **投资组合 (Portfolio) CRUD** | **🟡 后端编码完成，前端策略视图与账户管理上线，金融精度改造完成** | ⭐⭐⭐⭐ | 🟢 | Ⅱ | Portfolio 模型/API/收益率计算已实现；策略视图支持标签分组分析；账户管理重构（资金全景卡片、按类型分组、关联现金账户、删除保护、批量迁移）；金融精度改造（整数分存储）；`transactions.symbol` 快照字段；剩余：接口性能优化、type 列数据回填、跨日划转过滤 |
| P1-20 | 定时任务体系 (APScheduler) | ⏸️ 未开始 | ⭐⭐⭐ | 🟢 | Ⅱ | 统一管理净值、行情、异动，以及孤儿交易自动回填 |
| P1-08 | 特别关注页面功能增强 | 基础完成 | ⭐⭐⭐ | 🟢 | Ⅳ | 暂缓优化 |
| P1-06 | 全局UI细节微调 | **✅ 已完成** | ⭐⭐ | 🟢 | Ⅳ | 永久停止投入 |
| P1-13 | 移动端响应式 / PWA | 未开始 | ⭐⭐ | 🟢 | Ⅳ | 长期规划 |

### 9.3 新增 P2 功能规划（基于 Quicken Classic 对标分析）

| 编号 | 任务名称 | 说明 | 对标 Quicken 功能 |
|------|---------|------|-------------------|
| P2-1 | 完整手动记账页面 | 股票/基金/可转债/ETF 专用表单 | — |
| P2-2 | 基金净值自动获取 | 确认日后自动回填净值（已通过静默更新实现） | — |
| P2-8 | 资金划转导入处理 | 调用 LedgerService.transfer() | 全能中枢 |
| P2-9 | 对账模式 | 差异对比 + 确认 | 对账工具 |
| P2-10 | 资产配置穿透分析 | 场外基金穿透到底层股票，行业分布，重叠度检测 | Morningstar X-Ray |
| P2-11 | 贷款与应收款管理 | LOAN_OUT / LOAN_IN 类型支持，还款进度追踪 | Loan to Others |
| P2-12 | 税务成本估算 | 美股/港股资本利得税简易估算 | Capital Gain Estimator |
| P2-13 | 财务目标追踪 | 用户设定目标金额与日期，计算缺口 | Lifetime Planner |
| P2-14 | 按平台分组统计盈亏 | 按 source 字段分组展示各平台（支付宝/同花顺/天天基金）的盈亏汇总，支持与平台账单对账 | 全能中枢 |
| P2-15 | 交易记录全量导出备份 | 交易记录页面增加"导出 CSV"按钮，复用 StandardTransactionRecord 逻辑 | 数据备份 |
| P2-16 | 隐私保护（隐藏金额） | 一键隐藏所有金额，适合公共场合使用 | 隐私保护 |

### 9.4 当前进度总览

| 模块 | 完成度 | 剩余核心任务 |
|------|--------|------------|
| 导入模块（股票） | **100%** | ✅ 已完成 |
| 导入模块（基金） | **95%** | 支付宝 PDF 解析器完成，天天基金稳定，腾讯理财通待支持（P2） |
| 导入模块（通用） | **95%** | 解析器架构稳定，事务安全加固，持仓不足自动转为孤儿交易 |
| 简记弹窗 | **98%** | 买入/卖出交互优化已完成；需拆分 BuyForm/SellForm（下一阶段重构） |
| 手动记账（完整页面） | 0% | 全部待开发（P2-1） |
| **仪表盘** | **90%** | 年化收益率卡片上线；资产配置环形图已实现；盈亏走势图基础占位铺设（P1-20 数据接入后可激活）。 |
| 数据基建 | **97%** | `ledger_id` 外键迁移完成；`delete_ledger`/`migrate_positions` 已适配 `ledger_id`；SQL 聚合 Bug 已修复；`positions.type` 和 `confirm_date` 回填待执行 |
| **全局 UI** | **92%** | 详情页布局重构、色彩规范及移动端适配基础完成；组件拆分抽离持续推进；列表页分组与缩写标签已优化。 |
| **投资组合** | **92%** | 后端与策略视图完成；账户管理重构遗留 Bug 已修复；接口性能优化完成，type 列数据回填、跨日划转过滤待处理 |
| **账户管理** | **85%** | **后端 Service 层 Bug 已修复；前端详情页 UI 重构与独立抽屉组件已完成；列表页分组、未归置卡片已完善。资产录入 `ledger_id` 问题待应用修复。** |

# 10. 技术债务 & 开口项明细

| 问题描述 | 优先级 | 产生原因 | 处理策略 |
|---|---|---|---|
| （保留原 4 个后端 BUG） | 🔴 致命 | `Position.current_price`(分) × `Position.quantity`(最小单位) 正确市值(分) = 乘积 / 1,000,000，代码中 `/10000` 导致放大 100 倍；同时 Python 聚合和 SQL 聚合返回的数据单位不一致（分 vs 元），前端展示混乱 | 统一改为 Python 聚合调用 `Money.multiply_price_quantity` + `Money.cents_to_yuan`，移除所有 SQL 市值聚合 |
| **成交价格与净值自动填充及校验接口** | 中 | 目前买入/卖出仅依赖手动输入价格。为提升用户体验并防止误操作，需要后端提供股票/基金的当日价格区间（股票需要最高/最低价校验，基金需要按确认日净值自动回填）。 | **P2 阶段细化实现**。设计接口：股票（`GET /api/securities/{symbol}/price-range/?date=...`），基金（`GET /api/funds/{code}/nav/?date=...`）。前端在 `BuyForm` 和 `SellForm` 选中产品后调用，自动填入默认值，并限制用户输入的数值在价格区间内（用于股票）。 |
| （保留原 `get_ledger_summary` 问题） | 🔴 严重 | bank/property 分支写在 `if ledger_type in ('stock','fund')` 的 elif 中，永远不执行 | 将 bank/property 提升为与 stock/fund 同级的独立分支 |
| （保留原前端 API 路径问题） | 🔴 严重 | 后端返回 `{data: [...], total, page}`，前端解析为 `res.data.data` | 后端统一包裹为 `{data: {items, total, page, per_page}}` |
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
| 组合收益计算未支持跨日划转识别 | 低 | 需要交易级时间戳 + 人工标记，MVP 仅支持同日配对 | 当用户反馈超过 5% 的 Portfolio 存在跨日划转需求时启动修复 |
| `Transaction.confirm_date` 存在 NULL 值 | 高 | 写入源头未统一赋值 | 回填历史数据，修复所有写入入口 |
| `positions.type` 列存在 NULL/空值 | 高 | 部分导入解析器/手动录入未写入 `asset_type` | 统一回填所有持仓的 `asset_type`，并修复所有写入入口，完成后移除临时关键词匹配逻辑 |
| **`get_money_fund_stats` 调用传入 `ledger.name` 而非 `ledger.id`** | 🟡 中 | 参数类型为 `int` 但传入了字符串，导致货基占比/金额永远为空 | 改为传入 `ledger.id` |
| **`delete_ledger` / `migrate_positions` 未跟随 `ledger_id` 迁移** | 🟡 中 | 仍使用 `Position.account_name == ledger.name` 过滤，账户改名后会产生漏删/漏迁 | 改为 `Position.ledger_id == ledger_id`，迁移时同步更新 `account_name` 快照 |
| **`GET /api/ledgers/` 未返回账户摘要数据** | 🔴 严重 | 列表页卡片依赖 `total_market_value`、`pnl`、`position_count` 等字段，但接口只返回基础字段 | 在 `list_ledgers` 中为每个账户附加摘要统计 |
| **`position_ratio` 返回类型不一致** | 🟡 中 | `get_position_page` 中 `round()` 结果可能因单位混用而异常，且类型可能是 float 或 str | 修 B1 后统一确保返回 float |
| **同花顺解析器操作类型映射不完整** | 中 | `test_ths_otc_cash_format` 测试中 `OTC现金宝交` 的操作类型无法从映射表确定方向，测试被跳过 | 完善 `THS_OP_TYPE_MAP` 映射，补全测试断言 |
| **`get_ledgers_overview` 中总资产计算依赖净资产的推导** | 低 | 当前总资产通过 `net_worth + liability_total` 反推，而非直接从各组市值汇总 | 在 Service 层增加 `total_assets` 字段，直接汇总各类型市值 |
| **导入模块视图层仍较厚** | 低 | `app/domains/importers/views.py` 未完全拆分，部分校验逻辑耦合在视图函数中 | 后续提取 ImportService |

# 11. 远期 IDEAS 归档明细（不参与当前迭代）

- 资金划转自动归集现金资产
- 基金申购净值自动回填（已通过静默更新实现）
- JS 驱动呼吸动画骨架屏
- 盘点对账差异对比模式
- 自选页 Sparkline 迷你走势图
- 标签颜色实时预览
- 表格行内编辑快捷键切换

# 12. 重要决策完整记录表（带日期+细节，永久回溯）

| 决策日期 | 决策主题 | 完整决策细节 |
|---------|---------|-------------|
| 2026-06-21 | ECharts 图表颜色动态读取 CSS 变量 | 放弃在组件中硬编码十六进制颜色，改为通过 JS `getComputedStyle` 在运行时动态读取 `colors.css` 中定义的变量（如 `--invest-stock`、`--sankey-liquid`），确保图表颜色与全局主题保持严格一致，且能响应未来可能的暗黑模式或主题切换。 |
| 2026-06-21 | 抽取独立抽屉组件 `PositionTransactionsDrawer.vue` | 原详情页中点击持仓行在表格下方展开交易明细，导致父组件逻辑膨胀且交互受限。决定将其重构为右侧 `el-drawer` 独立组件，接收 `position-data` prop 并内部调用 `GET /api/positions/{id}/transactions/` 获取数据，实现关注点分离和更灵活的布局。 |
| 2026-06-21 | 简记弹窗买入/卖出交互优化 | 将“买入/卖出”由 `el-radio-group` 改为 `el-tabs` 切换；合并交易日期与下单时间至同一行并采用 `el-radio-button` 组；金额/份额切换改为 `el-input` 的 `prepend` 插槽实现下拉选择模式；基金卖出份额支持小数精度（4 位）；极简账户创建增加必选的账户类型下拉框，类型选项排除 `property`。 |
| 2026-06-21 | 账户列表页分组标题增加汇总信息及缩写 Badge | 在每个分组标题（如“银行账户”）后显示账户数与总金额（如 `(2 个账户 · ¥12,345)`）；卡片内类型标签由完整名称改为单字缩写（银/股/基/物），使用与分组标题匹配的半透明彩色背景小徽章，降低视觉冗余。 |
| 2026-06-21 | 修复 Layout 中 `LayHeader` 渲染导致全局抽屉无法弹出 | `LayHeader` 原本在 `<script setup>` 中使用 `defineComponent` + `h()` 渲染，导致插槽上下文丢失，影响全局 `TransactionDrawer` 的挂载。修复方案：去除 `defineComponent` 定义，直接在模板中替换为原始 HTML 结构，保持功能完全一致。 |
| 2026-06-21 | `ledger_id` 缺失写入入口排查与修复方案 | 发现资产录入 (`AssetEntry.vue`) 和简记弹窗早期版本均未传递 `ledger_id` 导致数据游离。简记弹窗已修复：账户选择改为绑定 `ledger_id`，提交时传递该字段。资产录入同样需改为 `ledger_id` 绑定，方案已定待应用。 |
| 2026-06-21 | 账户详情页概览卡片重构与图表规划 | 将原有卡片改为网格布局，强制涨红跌绿；新增环形图展示资产配置分布；预留走势图位置（依赖 P1-20 快照数据）。图表颜色全部通过 CSS 变量获取，保证零硬编码。 |
| 2026-06-18 | 放弃 SQL 聚合，统一使用 Python 聚合计算市值 | SQL 中 `price(分) × quantity(最小单位) / 10000` 与正确的 `Money.multiply_price_quantity` 内部逻辑不一致，且分母应为 1,000,000 而非 10,000，导致市值放大 100 倍。同时 Python 聚合和 SQL 聚合返回值单位（分 vs 元）在后续转换中产生混用。鉴于当前数据量下性能无差异，决定统一改用 Python 聚合，消除双路径维护成本和单位混淆风险。 |
| 2026-06-17 | 账户类型体系最终确定 | 砍掉 `family`/`general`/`cash`，最终保留四种类型：`bank`（银行账户）、`stock`（证券账户）、`fund`（场外基金平台）、`property`（实物资产）。核心规则：同账户内操作 = 资产形态转换，跨账户操作 = 转账。银行渠道买基金直接挂在银行卡账户下，不单独建 `fund` 账户。 |
| 2026-06-17 | `cash` 账户类型重命名为 `bank` | 将原先的现金/活钱账户类型从 `cash` 改为 `bank`，语义更清晰，表示一张具体的银行卡，承载活期、理财、基金等全部行内资产。同时 `linked_cash_ledger_id` 的校验也改为检查 `ledger_type='bank'`。 |
| 2026-06-18 | 引入 `ledger_id` 外键替代字符串关联 | `positions`、`transactions`、`assets` 增加 `ledger_id` 字段，通过外键与 `ledgers` 关联。`account_name` 保留为快照字段。所有核心查询和写入均基于 `ledger_id`，提升性能和数据完整性。 |
| 2026-06-15 | 金融数据存储精度方案（最终决策） | 所有直接关联用户资金的字段（金额、份额）采用整数存储分（×100）或最小份额单位（×10000）。基金净值改为 DECIMAL(18,6)。所有读写通过 `Money` 工具类统一转换，禁止业务代码直接乘除。详细变更见 5.1-5.10 节。 |
| 2026-06-15 | 前端数据异常根因 | `LedgerDetail.vue` 中 `fetchData` 自行计算市值（`marketValue = quantity * current_price`），而后端 `_enrich_position_dict` 已将单位转为元/份额。数据库新旧数据混合导致前端计算结果异常。最终通过彻底统一数据库数据（执行二次迁移）解决。 |
| 2026-06-15 | XIRR 计算适配精度改造 | `generate_cashflows` 和 `generate_portfolio_cashflows` 中读取 `Transaction.amount` 时用 `Money.cents_to_yuan` 转换，`calculators.py` 中所有持仓市值计算统一使用 Money 工具类。 |
| 2026-06-14 | 新增 `transactions.symbol` 快照字段 | 在 Transaction 表中新增 `symbol` 列作为资产代码的不可更改快照，用于关联查询和盈亏曲线生成。与 `position_name`、`account_name` 同为快照设计模式。 |
| 2026-06-14 | 持仓/资产列表通用展示规范 | 所有展示持仓或资产的表格，必须将“名称、代码、资产类型”合并为单一复合列。名称大字体，代码小字灰色前缀 `#`，类型标签内联。参照导入页 `Inventory.vue` 的产品单元格样式。 |
| 2026-06-14 | 批量迁移持仓端点设计 | 采用 `POST /api/ledgers/{id}/migrations/` 嵌套资源端点，目标账户 ID 放在请求体。限定同类型账户迁移，防止数据混乱。 |
| 2026-06-14 | 持仓删除可选清理交易 | `DELETE /api/positions/{id}/?delete_transactions=true`，默认仅删持仓保留交易记录，传参则级联删除关联交易。 |
| 2026-06-14 | 交易明细下钻展示位置 | 持仓明细表格点击行展开关联交易记录，交易明细显示在表格下方的独立区域，形成主-从视图，避免行内展开导致的横向空间不足。 |
| 2026-06-14 | 引入 `CURRENT_USER_ID` 常量统一用户隔离 | 在 `app/core/constants.py` 中定义 `CURRENT_USER_ID = 1`，所有硬编码 `user_id == 1` 的地方改为引用此常量。未来多用户时只需修改一处即可切换为从认证上下文获取。 |
| 2026-06-14 | 新增 `LEDGER_TYPE_LABELS` 枚举映射 | 在 `app/core/constants.py` 中新增 `LEDGER_TYPE_LABELS` 字典，统一账户类型中文文案（证券账户、基金平台、现金/活钱等），`_ledger_type_label()` 函数和前端映射均引用此常量，消除多处理编码不一致。 |
| 2026-06-14 | 删除账户时增加持仓关联检查 | 在 `DELETE /api/ledgers/{id}/` 中增加检查：若存在关联持仓且未勾选"同时删除持仓"，返回 400 错误并提示用户先清空或迁移持仓。勾选后级联删除。 |
| 2026-06-14 | 视图函数错误响应标准化 | 将所有 `abort(400, 'msg')` 替换为 `return jsonify({'data': None, 'message': 'msg'}), 400`，确保自定义错误消息在统一响应格式中正确返回。 |
| 2026-06-13 | 策略标签独立建模，不混用自选标签 | 策略标签作用域为实际持仓，语义为“我的持仓属于什么风格”，与自选标签（“我在关注什么”）物理隔离，分别建表。两者概念不重叠，互不干扰。 |
| 2026-06-13 | 策略视图负债过滤机制 | 负债不参与任何收益或风格分析，后端 `/api/strategy/overview/` 在查询资产时自动排除 `major_category='liability'`，前端无需任何过滤代码。`/api/assets/` 接口新增 `exclude` 参数供策略视图使用，不影响其他页面。 |
| 2026-06-13 | 策略视图数据合并为单一接口 | 为避免前端四次请求的延迟，新增 `GET /api/strategy/overview/` 一次性返回持仓、资产、标签、关联关系，性能提升显著。 |
| 2026-06-13 | 浮点精度临时兜底方案 | 发现 `Float` 存储金额/数量导致市值出现 `1999.995` 等误差。短期在接口层用 `round(value×100)/100` 消除多余小数；长期将存储改为整数分（`Integer`），彻底消除浮点误差。历史数据需一次性迁移。 |
| 2026-06-13 | 投资组合 (Portfolio) 核心设计原则 | 采用「用账户隔离策略」：Ledger 关联 Portfolio，通过账户自然隔离不同策略，不拆分持仓。同一账户内多策略区分场景不予支持，引导用户创建子账户。 |
| 2026-06-13 | 移除 Portfolio.risk_level 字段 | `purpose` 已可表达投资风险倾向（如“短线博弈”），`risk_level` 与其语义重叠且无业务逻辑消费，为遵守“概念降噪”原则予以删除。 |
| 2026-06-13 | 组合收益率内部划转过滤策略 | 采用同日配对识别：同一日期、金额按分精度匹配、相反方向、两账户同属一个组合的 deposit/withdraw 双向排除，防止收益率失真。跨日划转暂不处理。 |
| 2026-06-13 | 金融数据存储精度方案 | 发现 `Float` 存储金额/数量导致市值、盈亏出现 `1999.995` 等误差。决定采用“整数分”存储（`Integer`，单位为分），彻底消除浮点误差。所有输入/输出乘以/除以 100。历史数据需一次性迁移。此为长期方案，短期保留接口层 `round(×100)/100` 作为兜底。 |
| 2026-06-12 | deposit/withdraw 不参与 XIRR 计算 | 账户资金划转（deposit/withdraw）属于内部资金调度，不是投资行为。将其作为现金流会严重拉高投入基数导致 XIRR 异常。XIRR 现金流只包含 buy、sell、dividend_cash、dividend_reinvest 四种投资交易类型 |
| 2026-06-12 | Transaction 表新增 asset_type 字段 | 为交易记录增加资产类型快照字段，与 `position_name`、`account_name` 同属快照设计模式。解决孤儿交易无法判断资产类型的问题，避免 XIRR 计算时 JOIN 表查询。历史数据通过 SQL 回填，新数据在导入时自动写入 |
| 2026-06-12 | 货币基金识别临时关键词方案 | 在元数据同步未完全覆盖所有货币基金名称前，`_fill_names_and_types` 增加临时关键词匹配（货币、现金、宝、增利、天天益）。待元数据同步覆盖率足够后移除该逻辑 |
| 2026-06-12 | 持仓详情页单持仓 XIRR 前端展示延后 | 后端接口已可用，因持仓详情页页面路径未确定，前端卡片暂未实现，记录为技术债务，延后至 P2 |
| 2026-06-11 | xalpha 概念辨析：封闭系统 vs 开放系统 | ShowBuy 用户场景是典型的开放系统（随时买卖、定投、赎回），对应 xalpha 的 `mul` 系统。净值曲线仅在无资金进出的时间段有意义，多数场景应使用 XIRR 衡量投资效果。TWR（时间加权收益率）更适合作封闭系统的业绩归因，属于 P2 功能 |
| 2026-06-11 | 货币基金/逆回购不参与收益率计算 | 货币基金、逆回购属于"活钱管理"，收益率极低且无净值波动，不纳入 XIRR 计算。其收益率在仪表盘单独展示（P2） |
| 2026-06-11 | 红利再投资的现金流处理 | 红利再投资（dividend_reinvest）视为一笔负现金流。本质是用分红金额买入更多份额，简化为一笔等额现金流出 |
| 2026-06-11 | 支付宝 PDF 解析器上线 | 支付宝基金交易确认单 PDF 通过 pdfplumber 解析，支持36列表头页与12列数据页混合提取，跨页断裂通过“有效日期前缀”精确合并；字段级拼接避免数据错乱；输出标准化为 StandardTransactionRecord 进入导入流水线 |
| 2026-06-11 | 净值接口响应结构重构 | POST /api/funds/nav/ 返回格式改为数组，每个元素包含 fund_code、unit_nav、date，增强自解释性和前端可靠性 |
| 2026-06-11 | 异步回填数据库锁解决 | 采用 WAL 模式、连接超时30s、分批写入且直接 commit 释放锁，解决多线程导入时 database is locked 问题 |
| 2026-06-11 | 持仓不足处理策略 | 导入卖出/赎回时若持仓数量不足，由 process_orphan_sell_or_withdraw 内部捕获异常并转为孤儿交易（entry_status='orphan'），保证数据不丢失，待 P1-20 定时任务自动回填 |
| 2026-06-10 | 净值获取服务独立抽取 | `get_fund_nav_map` 从视图层抽取到 `app/services/fund_data_service.py`，同时供导入 orchestrator 和 API 接口复用。数据库无净值时通过 xalpha 实时拉取并存入 `daily_worth`，后续查询直接命中 |
| 2026-06-10 | 余额宝交易统一视为活钱 | 支付宝账单中所有余额宝相关交易（转入、转出、收益发放）标记为 `asset_type='cash'`、`is_cash_transfer=True`，不产生基金持仓。收益发放、转入映射为 `deposit`，转出映射为 `withdraw`，归入活钱管理 |
| 2026-06-10 | 支付宝 CSV 分隔符确定为逗号 | 实测支付宝导出文件使用逗号分隔（非制表符），解析器统一使用 `delimiter=','` 配合 `csv.reader` 处理引号内逗号 |
| 2026-06-10 | 解析性能优化：单次 csv.reader 读取 + 分批净值查询 | 不再逐行创建 `csv.reader`，改为一次性读取所有数据行；编码检测只读取前 1KB；`_fill_missing_nav_and_shares` 按日期分组并用 `IN` 查询，每批最多 50 个代码；`daily_worth` 表增加 `(fund_code, date)` 联合索引 |
| 2026-06-10 | 基金代码匹配增强：清洗名称 + 数据库 LIKE 查询 | 不再加载全表到内存，改用 SQL `LIKE` 查询并限制返回 10 条；清洗名称去除类别词（LOF/ETF/联接/发起等）后双向匹配；多个候选时按名称长度差选最佳，相同则放弃自动匹配 |
| 2026-06-10 | 导入预览增加净值自动填充和一键确认 | 用户匹配基金代码后，前端自动调用 `/api/funds/nav/` 获取净值并计算份额，标记 `is_calculated=true`，表格显示“待确认”标签；提供“确认所有推算数据”按钮一键清除标签 |
| 2026-06-10 | 导入事务安全加固 | `commit` 方法在每处理一条记录前创建保存点（`begin_nested`），单条失败只回滚当前保存点，不影响其他已成功记录 |
| 2026-05-31 | P1-09 优先于 P1-10 | 基金交割单导入是用户数据输入的瓶颈，必须优先实现。没有准确的交易数据，年化收益率计算无法开展 |
| 2026-05-31 | 货币基金独立建表 | 货币基金的万份收益与普通基金的单位净值含义完全不同，混存会导致计算复杂、查询困难。独立建表语义清晰 |
| 2026-05-31 | 元数据同步系统采用分层更新策略 | 核心池（持仓+自选）每日更新；CSV导入按需更新；全量同步仅手动触发。避免每日全量同步 1.2 万只基金带来的资源浪费 |
| 2026-05-31 | 费率规则采用规则映射模式 | 申购/赎回费率区间（PurchaseRule / RedeemRule）与基金多对多关联（FeeRatio），规则复用减少冗余，修改时通过引用计数保护 |
| 2026-05-31 | 静默回填历史数据 | 用户新增持仓/自选时，后台异步回填该标的历史净值/行情，使用 threading.Thread 实现，不阻塞前端 |
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

# 13. 断点续传协议

后续任何会话接续开发，只需携带：
1. 本完整 SPEC 文档（v4.3.3）
2. 当前进度一句话，如："账户体系重构遗留了 8 个 Bug/缺失，包括市值计算错误、summary 分支死代码、前端数据提取不匹配等，待修复"
3. 核心文件清单（更新于 2026-06-18）：

| 文件路径 | 作用说明 |
|---------|---------|
| `backend/app/main.py` | 项目入口、全局蓝图注册（含 portfolios、strategy 蓝图） |
| `backend/app/core/database.py` | 数据库基类、会话工厂（WAL 模式、连接超时） |
| `backend/app/core/symbol_utils.py` | 全市场证券代码标准化 |
| `backend/app/core/time_utils.py` | 统一时区工具（上海时区） |
| `backend/app/core/db_utils.py` | 批量插入去重工具（含 bulk_insert_if_not_exists） |
| `backend/app/core/constants.py` | 全局常量（TYPE_LABELS、ALLOCATION_LABELS、CURRENT_USER_ID、LEDGER_TYPE_LABELS 等） |
| **`backend/app/core/money.py`** | **金融精度转换工具类（元↔分、份额↔最小单位）** |
| `backend/app/services/ledger_service.py` | **账户维度数据聚合与计算服务（新，存在 4 个 Bug 待修复）** |
| `backend/app/services/importer/orchestrator.py` | 导入协调器（含 asset_type 写入和货币基金识别，已适配 Money 转换） |
| `backend/app/services/importer/parsers/alipay_fund.py` | 支付宝交易记录解析器 |
| `backend/app/services/importer/parsers/alipay_pdf.py` | 支付宝基金交易 PDF 解析器 |
| `backend/app/services/importer/parsers/tiantian_fund.py` | 天天基金交易记录解析器 |
| `backend/app/services/importer/registry.py` | 解析器注册表 |
| `backend/app/services/fund_data_service.py` | 基金数据服务：批量获取净值、实时拉取并存入数据库 |
| `backend/app/domains/positions/views.py` | 持仓核心业务接口（含交易明细查询、删除含级联清理交易，已适配 Money 读取转换） |
| `backend/app/domains/positions/schemas.py` | 持仓 Schema 定义 |
| **`backend/app/services/position_service.py`** | **持仓业务逻辑服务层（含持仓不足转孤儿交易、confirm_date 写入，已适配 Money 写入转换）** |
| `backend/app/domains/transactions/models.py` | 交易流水模型（新增 `symbol` 快照字段，金额/份额字段改为 Integer） |
| `backend/app/domains/ledgers/models.py` | Ledger 模型定义（新增 portfolio_id、linked_cash_ledger_id 字段） |
| `backend/app/domains/ledgers/views.py` | Ledger API（已重构，存在 `delete_ledger`、`migrate_positions` 未适配 `ledger_id` 的问题） |
| `backend/app/domains/assets/views.py` | 资产 API（支持 exclude 参数排除负债，已适配 Money 转换） |
| `backend/app/domains/assets/models.py` | 资产模型，新增 `ledger_id` 外键 |
| `backend/app/domains/utils/views.py` | 交易日校验与基金确认日 API |
| `backend/app/core/utils.py` | 通用工具函数 |
| `backend/app/services/sync/` | 元数据同步系统（适配器、Job、Orchestrator） |
| `backend/app/services/sync/money_fund_utils.py` | 货币基金万份收益计算 |
| `backend/app/services/async_backfill.py` | 静默历史数据回填（修复锁冲突） |
| `backend/app/tools/sync_metadata.py` | 元数据同步 CLI 入口 |
| `backend/app/domains/funds/models.py` | 基金、费率规则、净值、货币基金净值等模型（金额/净值字段已适配精度改造） |
| `backend/app/domains/funds/views.py` | 基金 API：净值批量查询接口（响应重构为数组） |
| `backend/app/domains/funds/schemas.py` | 基金请求 Schema |
| `backend/app/domains/securities/models.py` | 证券模型 |
| `backend/app/domains/price_history/models.py` | 历史行情模型 |
| `backend/app/models/sync_log.py` | 同步审计日志模型 |
| `backend/app/services/performance/__init__.py` | 年化收益率服务模块导出 |
| `backend/app/services/performance/constants.py` | XIRR 计算共享常量 |
| `backend/app/services/performance/xirr_engine.py` | XIRR 核心算法、现金流生成、组合现金流生成与内部划转过滤（已适配 Money 转换） |
| `backend/app/services/performance/calculators.py` | 单持仓/组合/指定组合年化收益率计算器（已适配 Money 转换） |
| `backend/app/domains/performance/views.py` | 年化收益率 API 端点（扩展 portfolio_id 参数） |
| `backend/app/domains/performance/schemas.py` | 请求/响应 Schema |
| `backend/app/domains/portfolios/models.py` | 投资组合数据模型 |
| `backend/app/domains/portfolios/views.py` | 投资组合 CRUD API（含软删除自动解绑、持仓明细，已适配 Money 转换） |
| `backend/app/domains/portfolios/schemas.py` | 投资组合请求/响应 Schema |
| `backend/app/domains/strategy/models.py` | 策略标签模型（StrategyTag、PositionStrategyTag） |
| `backend/app/domains/strategy/views.py` | 策略标签 CRUD、绑定/解绑、relations、overview 接口（已适配 Money 转换） |
| `backend/app/domains/strategy/schemas.py` | 策略标签请求/响应 Schema |
| `frontend/src/layout/index.vue` | **全局布局文件，已修复 `LayHeader` 渲染问题** |
| `frontend/src/components/QuickEntry/TransactionDrawer.vue` | **简记弹窗核心组件（已优化交互、修复 `ledger_id`）** |
| `frontend/src/components/QuickEntry/QuickFab.vue` | 全局悬浮按钮，触发简记弹窗 |
| `frontend/src/views/asset/ledgers/index.vue` | 账户列表页（已增加分组汇总、缩写标签、未归置卡片） |
| `frontend/src/views/asset/ledgers/detail.vue` | 账户详情页（已重构卡片、图表、抽屉触发） |
| `frontend/src/views/asset/ledgers/components/PositionTransactionsDrawer.vue` | **新增独立抽屉组件，展示单持仓交易明细** |
| `frontend/src/views/asset/entry/index.vue` (AssetEntry.vue) | 资产录入页面（`ledger_id` 待修复） |
| `frontend/src/views/asset/inventory/index.vue` (InventoryHome.vue) | 全面盘点页面（投资类资产入口待调整） |
| `backend/app/services/ledger_service.py` | 账户服务层（Bug 已全部修复） |
| `backend/app/domains/ledgers/views.py` | 账户 API（`delete_ledger` / `migrate_positions` 已适配 `ledger_id`） |
| `backend/app/domains/positions/schemas.py` | 持仓 Schema（已增加 `ledger_id` 字段） |
| `backend/app/domains/assets/views.py` | 资产 API（需确认创建资产时接受 `ledger_id`） |
| `frontend/src/components/QuickEntry/TransactionDrawer.vue` | 简记弹窗（抽屉）组件 |
| `frontend/src/views/asset/investment/import/index.vue` | 导入工作台（含支付宝 PDF 选项） |
| `frontend/src/views/asset/investment/import/components/FundMatchDrawer.vue` | 基金代码匹配抽屉组件 |
| `frontend/src/views/welcome/index.vue` | 仪表盘首页（含年化收益率卡片） |
| `frontend/src/views/asset/ledgers/index.vue` | 账户管理列表页（待重构，接口数据未匹配） |
| `frontend/src/views/asset/ledgers/detail.vue` | 账户详情页（待重构，接口数据未匹配） |
| `frontend/src/views/asset/ledgers/components/AccountFormFields.vue` | 账户表单复用组件（类型/现金账户/组合选择/费率折叠面板） |
| `frontend/src/views/asset/ledgers/components/DeleteLedgerDialog.vue` | 删除账户确认对话框（可选清理持仓） |
| `frontend/src/views/asset/portfolio/index.vue` | 投资组合列表页 |
| `frontend/src/views/asset/portfolio/detail.vue` | 投资组合详情页（收益、持仓明细、关联账户管理） |
| `frontend/src/views/asset/strategies/index.vue` | 策略视图页（标签管理、分组展示、汇总卡片） |
| `frontend/src/api/positions.ts` | 前端持仓请求封装（含 deletePosition、getPositionTransactions） |
| `frontend/src/api/ledger.ts` | 前端 Ledger 请求封装（含 overview、deleteLedgerWithOptions、migrateLedgerPositions、新增 7 个详情接口） |
| `frontend/src/api/importer.ts` | 导入 API 封装 |
| `frontend/src/api/funds.ts` | 前端基金 API 封装 |
| `frontend/src/api/performance.ts` | 前端年化收益率 API 封装 |
| `frontend/src/api/portfolio.ts` | 投资组合 API 封装 |
| `frontend/src/api/strategy.ts` | 策略标签 API 封装 |
| `frontend/src/api/utils.ts` | 前端工具 API 封装 |
| `tests/domains/test_funds.py` | 基金 API 测试（适配新响应格式） |
| `tests/services/importer/test_alipay_pdf_parser.py` | 支付宝 PDF 解析器测试 |
| `tests/services/performance/test_xirr_engine.py` | XIRR 核心算法测试 |
| `tests/domains/test_portfolios.py` | 投资组合 API 测试（含持仓端点） |
| `tests/domains/test_strategy.py` | 策略标签 API 测试（10 个用例覆盖 CRUD、绑定/解绑、relations、overview） |
| `tests/domains/test_ledgers.py` | Ledger API 测试（46 个用例，覆盖 CRUD、配置目标标签、持仓归入、fee_config、关联现金账户、overview、批量迁移） |
| `tests/domains/test_positions.py` | 持仓 API 测试（26 个用例，覆盖 CRUD、交易明细查询、删除含级联清理交易） |
| **`tests/core/test_money.py`** | **Money 工具类精度测试（30 个用例）** |
| **`tests/domains/test_e2e_precision.py`** | **全链路精度验证测试** |

4. 最新的报错截图或要解决的具体问题

# 14. 最终编码通用守则

- 数据准确性优先级最高，优于视觉美化、功能花哨
- 所有代码、样式、接口、命名、交互严格统一
- 禁止私自变更既定架构与业务规则，所有优化必须遵守时间盒与优先级
- 所有问题可追溯、所有决策有记录、所有规范可落地

# 14.1 版本号管理规范（新增）

本项目遵循语义化版本规范（Semantic Versioning 2.0），所有版本号升级必须严格遵守以下规则：

| 版本位 | 变更类型 | 典型场景 |
|--------|---------|---------|
| **主版本** (X.0.0) | 架构级重构、不兼容的 API 变更、核心业务逻辑颠覆 | 从 SQLite 迁移到 PostgreSQL、放弃 APIFlask 改用 FastAPI |
| **次版本** (0.X.0) | 新功能模块上线、成片区的 P1 任务完成、大规模精度改造 | P1-12 完成、金融精度改造完成 |
| **修订号** (0.0.X) | Bug 修复、小优化、单条技术债务消除、测试补全、文档修正 | 修复 SafeNumeric、修复测试断言、新增债务条目 |

**升级判断标准**：
- **修订号升级**：改动仅影响代码质量或修复缺陷，不涉及新功能或 API 变更。
- **次版本升级**：完成一个独立的 P1 任务或新增一个完整的功能模块。
- **主版本升级**：发生不可逆的架构变更或破坏性 API 改动。

**禁止行为**：
- 禁止因单次 Bug 修复或文档更新而升级次版本号。
- 禁止将多个修订号变更合并为一次次版本升级。
- 主版本升级前必须经过完整的技术评审和迁移方案设计。

# 15. AI编码行为强制约束规范（Karpathy准则增补·最终闭环）

本章为项目底层**强制编码执行标准**，补齐项目规范体系中缺失的编码思维、修改边界、工程尺度、落地验证规则，彻底规避AI编码常见问题：主观假设需求、过度工程设计、冗余代码堆积、随意改动存量逻辑、无验证迭代等问题。项目所有新增开发、代码修改、Bug修复、架构重构、功能优化工作，均需严格遵守本章节所有规则，与前文技术规范、业务规范具备同等强制效力。

本章为项目**AI 编码底层强制规范**，补齐原有体系缺失的编码思维、边界控制、防过度工程、落地验证能力，专门杜绝AI编码通病：盲目假设、过度架构、冗余臃肿、乱改存量代码、无验证迭代。所有新增、修改、重构、Bug修复、迭代优化必须严格遵守。

## 15.1 编码前思考规则（禁止假设、禁止藏疑、必须权衡）

- 禁止私自假设任何业务逻辑、字段含义、接口规则、需求细节，存在任何不确定点，必须前置澄清，不猜测编码
- 需求、逻辑、边界存在歧义时，必须列出多种可行方案及对应的利弊权衡，不默认自选方案直接执行
- 发现现有代码、架构、方案存在冗余、不合理、可优化问题时，必须主动提出异议并说明具体理由，不盲从旧逻辑
- 自身存在困惑、认知模糊、逻辑看不懂的场景，立即暂停开发，优先澄清问题，严格遵循**存疑不编码、不懂不改动、模糊不落地**

## 15.2 简洁优先规则（禁止过度工程、禁止臃肿冗余）

- 严格按需开发，只实现需求明确要求的功能，不新增需求以外的逻辑、配置、扩展能力、兼容逻辑
- 拒绝过度工程化，简单业务逻辑、一次性执行逻辑，禁止强行封装多层抽象、通用类、工具方法、复杂架构
- 不为极低概率、线上不可能发生的异常场景编写冗余容错、兜底、兼容代码，避免无效代码堆积
- 代码以「精简、直白、可维护」为核心标准，同等功能下优先更少代码、更简单逻辑，杜绝50行可实现逻辑扩为数百行臃肿架构
- 落地校验标准：以资深工程师视角判断，若存在过度设计、多余抽象、冗余代码，必须无条件简化重构

## 15.3 精准修改规则（严控改动边界、禁止无效乱改）

- 所有迭代修改、Bug修复仅改动本次任务必需的代码、配置、文件，禁止改动任何无关代码、注释、格式、样式、变量、空行
- 线上正常运行、无Bug、无业务问题的存量代码，严格遵循**不坏不修改、稳定不重构**，禁止私自优化、重构、微调格式
- 修改存量代码时，严格沿用项目现有编码风格、命名习惯、代码结构，不强行替换为个人风格、新式写法
- 仅允许删除**本次改动直接产生**的冗余导入、无效变量、废弃函数、孤儿代码；项目原有历史死代码、冗余代码，禁止私自删除，可备注提示留存
- 所有代码改动内容必须100%可追溯至用户明确需求、任务要求、Bug问题点，无溯源的改动一律禁止

## 15.4 目标驱动执行规则（先定标准、分步验证、闭环落地）

- 所有开发、修复、重构、优化任务，**开发前必须先定义可量化、可验证的成功标准**，无标准不开发
- Bug修复强制闭环：先编写可稳定复现问题的测试用例 → 针对性修复问题 → 验证测试用例全部通过，禁止无测试、无验证的盲修
- 代码重构强制闭环：保证业务功能零变更、对外接口完全兼容、全量测试用例通过，禁止破坏性重构、隐性改逻辑
- 多步骤复杂任务必须提前拆分执行步骤，明确每一步的落地目标与验证标准，分步执行、分步自检，避免做偏、做漏、做一半
- 任务全部完成后，必须自主全量校验，确认完全达成预设成功标准、无副作用、无遗留问题，方可收尾提交

---

**文档结束语**：本文档为 ShowBuy 项目唯一权威、完整闭环的长期维护标准，覆盖项目愿景、业务规则、架构设计、UI规范、开发准则、测试要求、进度管理、决策追溯、技术债务、AI编码约束全维度内容。所有规则均来自实战踩坑复盘与标准化落地总结，无模糊定义、无冲突规则、无遗漏约束，可完全支撑项目长期迭代、自主维护、版本复盘、开发接续与项目交接，为全生命周期开发提供统一、唯一、不可私自变更的事实依据。

> （注：文档部分内容可能由 AI 生成）
