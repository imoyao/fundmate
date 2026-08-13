# 自选页表格信息密度提升设计提案

> 性质：内部备忘（`docs/working-notes/` 全目录屏蔽出构建，不对外）
> 触发：用户反馈自选页表格列过少、信息密度不足，要求补齐持仓管理必需字段，并参考「基股」（即基估宝 / 叽咕，仓库统一称「叽咕」）设计
> 结论形态：先对齐既有设计基线与竞品能力，再给出视图自适应的列方案与数据依赖，分 P0/P1/P2 落地

## 执行摘要

当前自选页（`frontend/src/views/asset/watchlist/index.vue`）实际只渲染 5 个数据列：代码/名称、最新价、涨跌幅、持仓市值，外加选择/标记/操作列，远未达到 `docs/features/watchlist.md §1.5.4` 早已定义的设计基线，也未对齐基估宝（jigu）v2.4.1 的「估值涨跌／持仓收益／每日收益」能力（见 issue #893 纪要）。本提案在复用现有实时估值引擎（`valuationEngine.ts`）与历史行情表（`price_history`）的基础上，按「身份／价格／持仓／收益」四类分组补齐列，并区分「前端即可算出」与「需后端 enrich」的字段，分 P0（复用既有能力）、P1（历史行情 join）、P2（列显隐持久化与排序）三阶段落地。

## 背景与现状

用户明确指出：自选页对持仓管理不够用，最起码要显示「添加自选日」，并希望股票显示持有股数、基金（若持有）显示持有份额与最新净值，再补齐添加后涨幅、估算涨幅、昨日收益、最新涨幅、估算收益、当日收益。需求本质是把自选页从「观察列表」升级为「盯盘＋持仓管理」一体化视图。

盘点现状：

后端 `WatchlistItemOut`（`backend/app/domains/watchlist/schemas.py`）已携带 `created_at`（添加时间）、`cost_price` 与 `quantity`，但后两者是「探市迁移透传的观察参考值」，并非真实持仓。真正的持仓在 `positions` 表（`quantity` 以 0.0001 份/单位整数存储、`avg_price` 成本均价分、`current_price` 当前市价分）。`_enrich_item`（`backend/app/domains/watchlist/views.py:80`）目前只向外暴露 `current_price`（持仓表均价）、`change_pct`（硬编码为 `None`）、`position_market_value`（持仓表 `quantity*current_price` 求和），**没有把真实持仓数量单独吐出**。

前端实时估值引擎（`valuationEngine.ts`）对每个持仓计算出 `currentPrice / changePct / marketValue / pnl / pnlPercent`，但只对比成本（`costPrice`），不提供「对比昨收」的当日收益，也不含估算净值分时。实时行情源（`realtimeDataSources.ts`）对基金返回的是天天基金 `gsz`（估算净值）与 `gszzl`（估算涨跌幅），对股票返回实时价与涨跌幅——也就是说「估算涨幅」与「当日/估算收益」在前端用 `changePct + currentPrice + 持有量` 即可推导，无需新增接口字段。

## 设计基线已有但未实现

`docs/features/watchlist.md §1.5.4` 早已定义默认列表头，只是前端一直没落地：

全部视图基线：代码｜名称｜场内/场外标签｜最新价/净值｜涨跌幅/估算涨幅｜持仓市值｜浮动盈亏｜盈亏比例｜经理（场外）。
场内视图基线：代码｜名称｜最新价｜涨跌幅｜涨跌额｜持仓数量｜持仓市值｜浮动盈亏｜盈亏比例。
场外视图基线：代码｜名称｜单位净值｜累计净值｜日涨幅(估算)｜持仓份额｜持仓市值｜浮动盈亏｜基金经理。

本提案在此基线上，叠加用户本次点名的字段，并补齐收益类列。

## 基估宝（叽咕）竞品基准

issue #893（`探市 × 自选 重新评估纪要`）实证了基估宝 v2.4.1 的列表/卡片能力，按用户点名的 6 个收益列逐一对应如下：

估值涨跌（估值涨跌幅）→ 本方案的「估算涨幅」；持仓收益（持仓盈亏）→ 本方案「浮动盈亏／持仓收益」；持有金额 → 本方案「持仓市值」；历史净值＋每日收益（`FundDailyEarnings`、`FundHistoryNetValue`）→ 本方案「昨日收益／当日收益／添加后涨幅」；排序规则支持「估值涨跌／持仓收益／持有金额」组合 → 本方案列默认排序与可切换建议的来源。

这意味着用户想要的列，竞品已验证是高频刚需，且本仓库的「自选／每日收益日历」在 issue #893 §9.6 中明确为免费不限次，没有付费墙顾虑。

## 数据可得性判定

前端实时可得（无需后端改动）：最新涨幅（≡ 涨跌幅，realtime `changePct`）、估算涨幅（基金 `gszzl`、股票盘中涨跌幅）、当日收益与估算收益（由 `changePct + currentPrice + 持有量` 推导，基金盘中即估值口径）、最新净值（基金 `current_price` 或实时 `gsz`）。

需后端 enrich 新增：真实持有数量 `holding_quantity`（按 symbol 汇总 `positions.quantity`）、加权平均成本 `holding_cost_price`（`positions.avg_price` 加权）；昨日收益所需的「昨收」与「前收」来自 `price_history.close`（按 `symbol + trade_date` 取最近两个交易日）；添加后涨幅所需的「添加日行情」同样来自 `price_history` 在 `created_at` 附近的交易日收盘价。注意 `price_history` 由 `price_history_job.py` 同步填充，覆盖率依赖回填，缺数据时对应列降级显示 `--`。

## 推荐列方案（视图自适应）

把用户的 6 个收益列做语义归并，避免重复堆砌：最新涨幅与涨跌幅同源，统一显示为「涨跌幅（最新）」；估算涨幅仅对场外基金有意义（估值涨跌幅），场内股票与之重合可隐藏；当日收益与估算收益对股票完全等价，对基金盘中「当日」取实时、「估算」取估值，收盘后两者合一——建议默认只放「当日收益」，基金盘中额外标「估」徽标，不强行拆两列。

按四类分组，默认可见列（核心，P0）建议为：

身份组：代码/名称（现有）｜类型标签（场内/场外，基线已有）｜添加自选日（★用户点名，直接取 `created_at`）｜分组/标签。

价格组：最新价/净值（现有，基金显示净值）｜涨跌幅＝最新涨幅（现有）｜估算涨幅（基金估值涨跌幅）。

持仓组：持有数量/份额（★股票股数／基金份额，需后端吐 `holding_quantity`）｜持仓市值（现有）｜成本价（新增，算浮动盈亏用）｜浮动盈亏／盈亏比例（基线已有，复用估值引擎 `pnl/pnlPercent`）。

收益组：当日收益（★realtime 推导，对齐 explore 页「当日盈亏」）｜昨日收益（★需 `price_history` 昨收）｜添加后涨幅（★需 `price_history` 添加日行情）。

进阶可切换列（P1/P2，复用现有 `settingsDrawer` 列显隐）：累计净值、基金经理（场外）、估算收益（与当日收益并列时）、添加天数、观察参考成本价/份额（迁移透传值，与真实持仓区分标注）。

场内／场外视图差异沿用基线：场内强调「最新价／涨跌额／持仓数量」，场外强调「单位净值／累计净值／持仓份额／基金经理／估值涨跌幅」。

## 后端改动清单

`_enrich_item` 需扩展：①新增 `holding_quantity`（按 `family_id + symbol` 汇总 `Position.quantity`，注意分存储单位换算）；②新增 `holding_cost_price`（加权均价）；③新增 `yesterday_close` 与 `day_before_close`（join `price_history` 最近两交易日），用于派生昨日收益；④新增 `price_at_added`（join `price_history` 接近 `created_at` 的交易日），用于派生添加后涨幅。`change_pct` 仍为 `None` 没关系，前端用实时 `changePct` 覆盖即可。真实持仓数量请勿复用 `WatchlistItemOut.quantity`（那是迁移透传的观察参考值，可能为空或过期）。

## 前端改动清单

`index.vue` 新增列模板，收益/涨跌一律走 `RiseFallText` 组件与 `--color-rise/--color-fall` 语义变量（禁止硬编码 hex、禁止 emoji）；持有数量/份额、成本价、浮动盈亏复用估值引擎与实时 quote；当日收益＝`(currentPrice - prevClose) × holding_quantity`，其中 `prevClose = currentPrice / (1 + changePct/100)`；昨日收益＝`(yesterday_close - day_before_close) × holding_quantity`；添加后涨幅＝`(currentPrice - price_at_added) / price_at_added`。列显隐设置接入既有 `settingsDrawer` 并做本地持久化；默认排序参考基估宝，支持按涨跌幅/持仓收益/持有金额组合。

## 落地节奏

P0：补齐添加自选日、真实持有数量/份额、最新净值、估算涨幅、持仓市值、当日收益，全部基于已存在的数据与实时引擎，零后端新接口即可上线大部分。
P1：后端 enrich 昨收/添加日行情，前端上线昨日收益与添加后涨幅，并处理 `price_history` 缺数据的 `--` 降级。
P2：列显隐持久化、组合排序规则、分组持仓收益汇总、基金估值分时 hover（基估宝 `FundValuationTrendChart` 思路）。

## 结论

自选页信息密度不足的症结在于：设计基线（`watchlist.md §1.5.4`）与竞品（基估宝，见 #893）早已定义完整列集合，但前端长期只渲染了 5 列。补齐的核心障碍不是「算不出」，而是「后端没把真实持仓数量与历史行情 join 出来」。按本提案分三阶段落地，即可在不引入付费墙、不新增数据源成本的前提下，把自选页做成真正服务于持仓管理与盯盘的密集表格。

## 局限

昨日收益与添加后涨幅的准确性依赖 `price_history` 的回填覆盖率，添加日早于历史数据起始点的标的会降级显示；基金「估算」与「当日」在收盘后重合，盘中才是估值口径；`WatchlistItemOut.quantity/cost_price` 为迁移透传的观察参考值，必须与真实持仓严格区分，避免误导。

## 参考

1. [docs/features/watchlist.md §1.5.4 默认列表头设计基线](docs/features/watchlist.md)
2. [docs/working-notes/explore-watchlist-enhancement-2026-08-12.md 自选增强方案（含基估宝列映射）](docs/working-notes/explore-watchlist-enhancement-2026-08-12.md)
3. [docs/working-notes/explore-watchlist-replan-2026-08-08.md 探市/自选重规划（基估宝复刻列）](docs/working-notes/explore-watchlist-replan-2026-08-08.md)
4. [GitHub Issue #893 探市 × 自选 重新评估纪要（基估宝 v2.4.1 能力实证）](https://github.com/imoyao/fundmate/issues/893)
5. [GitHub Issue #807 自选页面实时估值功能开发计划](https://github.com/imoyao/fundmate/issues/807)
6. [GitHub Issue #808 自选「探市」体验版设计文档与任务计划](https://github.com/imoyao/fundmate/issues/808)
7. [GitHub Issue #661 自选功能实现（已归档）](https://github.com/imoyao/fundmate/issues/661)
8. 源码：`frontend/src/utils/valuationEngine.ts`、`frontend/src/utils/realtimeDataSources.ts`、`frontend/src/views/asset/watchlist/index.vue`、`frontend/src/views/explore/index.vue`、`backend/app/domains/watchlist/views.py`、`backend/app/domains/watchlist/schemas.py`、`backend/app/domains/positions/models.py`、`backend/app/domains/price_history/models.py`
