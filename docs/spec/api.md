---
title: 核心 API 端点清单（api）
---

# 核心 API 端点清单（api）

本文件收录核心 API 完整端点清单（原 SPEC 第 8 章），属于**随代码演进**的事实标准。路由以 `backend/app/domains/*/views.py` 为准。

> **文档分工（#1611 修订，2026-09-19）**：本文件分两部分——
> ① **第 1 节「核心端点」**：人工维护，带功能说明，用于快速检索「这个能力由哪个接口提供」；
> ② **文末「全量端点清单」自动生成段**：由 `scripts/check_api_conventions.py --write` 从
> `app.url_map` **逐条生成**（131 条），是**全量且与实现一致**的权威清单。
> 此前该文件只列 30/131 条却自称「事实标准」，被 #1611 判定为**已滞后**；现由守卫
> （同名脚本，接入 CI + pre-commit）保证自动段与实现零漂移——改路由后重跑 `--write` 即可。

## 1. 核心端点（人工维护，带功能说明）

|方法|接口路径|功能说明|
|---|---|---|
|POST|/api/funds/redeem-fee/estimate/|预估基金赎回费用及费率分布，支持全仓与指定份额模式|
|POST|/api/funds/{fund_code}/fee-sync/|同步单只基金的申购/赎回费率信息|
|GET/POST|/api/positions/|持仓列表查询、新增持仓|
|PATCH/DELETE|/api/positions/{id}/|更新、删除单条持仓（支持 `delete_transactions` 参数）|
|**GET**|**/api/positions/{id}/transactions/**|**获取持仓的关联交易明细**|
|GET|/api/transactions/|交易流水分页筛选查询|
|**GET**|**/api/transactions/export/**|**交易记录一键导出 CSV**（P2-15）：全家庭交易流水，列与导入模板对齐（交易日期/确认日期/资产类型/代码/名称/业务类型/账户/数量/价格/手续费/金额/状态/备注）；金额用 `Money` 精度换算分→元；响应 `Content-Type: text/csv` + `Content-Disposition: attachment; filename="transactions_{YYYY-MM-DD}.csv"`；需鉴权（JWT），非探市公开端点。|
|GET/POST|/api/assets/|通用资产负债查询（支持 `exclude` 参数排除负债）、新增|
|PATCH/DELETE|/api/assets/{id}/|更新、删除通用资产|
|**GET**|**/api/assets/summary/**|**新增轻量汇总接口**：返回 `cash/fixed/liability/receivable/insurance` 各资产大类汇总金额（`value`）及中文标签（`label`），用于"全面盘点"顶部卡片按需快速展示。|
|GET|/api/summary/|仪表盘总资产汇总数据|
|GET|/api/funds/search/|基金模糊搜索|
|GET|/api/funds/managers/search/|基金经理搜索|
|GET|/api/funds/advisors/{code}/holdings/|投顾组合当前持仓（#1468）：最新快照日的成分基金与占比，每只带 `in_local_db` 标注是否已收录本地 `funds` 表|
|GET|/api/funds/advisors/{code}/adjusts/|投顾组合调仓明细（#1468）：按调仓日倒序分组，`?limit=N`（缺省 10 上限 50）、`?date=YYYY-MM-DD` 精确取某日；且慢明细由持仓快照序列推导，无官方历史接口|
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
|**GET**|**/api/temperature/overview**|**获取温度概览（含综合温度、单值指标、复合指标、多维列表数据如乖离率）** ✅ 已实现|

> 注：`/api/portfolios/{id}/summary/` 组合概览端点计划在 P2 实现，当前不提供。

<!-- AUTO-ENDPOINTS:START（由 scripts/check_api_conventions.py --write 生成，勿手改） -->

全量端点清单（共 **132** 条）：由 `scripts/check_api_conventions.py --write` 从
`backend/app/domains/**/views.py` 的 `@<bp>.<method>(...)` 装饰器静态生成，**禁止手改**——
改路由后重跑该命令即可；CI 守卫会校验本段与实现逐条一致（不一致即红灯）。

| 方法 | 路径 | 处理函数 |
|---|---|---|
| POST | `/api/agent/chat/` | `agent_chat` |
| GET | `/api/assets/` | `list_assets` |
| POST | `/api/assets/` | `create_asset` |
| DELETE | `/api/assets/<int:id>/` | `delete_asset` |
| PATCH | `/api/assets/<int:id>/` | `update_asset` |
| GET | `/api/assets/summary/` | `get_assets_summary` |
| POST | `/api/auth/logout/` | `logout` |
| GET | `/api/auth/me/` | `me` |
| POST | `/api/auth/resolve/` | `resolve_identifier` |
| POST | `/api/e-account/attribution/` | `attribution` |
| POST | `/api/e-account/reconcile/` | `reconcile` |
| GET | `/api/e-account/reconciliation/` | `reconciliation` |
| POST | `/api/families/` | `create_family` |
| GET | `/api/families/<int:family_id>/members/` | `list_family_members` |
| GET | `/api/funds/<string:fund_code>/fee-rates/` | `get_fund_fee_rates` |
| POST | `/api/funds/<string:fund_code>/fee-sync/` | `sync_fund_fees` |
| GET | `/api/funds/<string:fund_code>/nav/` | `get_fund_nav` |
| GET | `/api/funds/advisors/<string:code>/adjusts/` | `get_advisor_adjusts` |
| GET | `/api/funds/advisors/<string:code>/holdings/` | `get_advisor_holdings` |
| GET | `/api/funds/managers/search/` | `search_managers` |
| POST | `/api/funds/nav/` | `get_fund_nav_by_date` |
| POST | `/api/funds/redeem-fee/estimate/` | `estimate_redeem_fee` |
| GET | `/api/funds/search/` | `search_funds` |
| GET | `/api/health` | `health_check` |
| POST | `/api/importers/confirm/` | `confirm_import` |
| POST | `/api/importers/holdings/confirm/` | `confirm_holding_import` |
| POST | `/api/importers/holdings/parse/` | `parse_holding_file` |
| POST | `/api/importers/parse/` | `parse_file` |
| GET | `/api/importers/template/<template_type>/` | `download_import_template` |
| GET | `/api/ledgers/` | `list_ledgers` |
| POST | `/api/ledgers/` | `create_ledger` |
| DELETE | `/api/ledgers/<int:ledger_id>/` | `delete_ledger` |
| GET | `/api/ledgers/<int:ledger_id>/` | `get_ledger` |
| PATCH | `/api/ledgers/<int:ledger_id>/` | `update_ledger` |
| POST | `/api/ledgers/<int:ledger_id>/archive/` | `archive_ledger` |
| POST | `/api/ledgers/<int:ledger_id>/migrations/commit/` | `commit_migration` |
| POST | `/api/ledgers/<int:ledger_id>/migrations/preview/` | `preview_migration` |
| GET | `/api/ledgers/<int:ledger_id>/pending-estimate/` | `get_ledger_pending_estimate` |
| GET | `/api/ledgers/<int:ledger_id>/positions/` | `get_ledger_positions` |
| DELETE | `/api/ledgers/<int:ledger_id>/positions/<int:position_id>/` | `delete_ledger_position` |
| PATCH | `/api/ledgers/<int:ledger_id>/positions/<int:position_id>/` | `update_ledger_position` |
| GET | `/api/ledgers/<int:ledger_id>/summary/` | `get_ledger_summary` |
| GET | `/api/ledgers/<int:ledger_id>/transactions/` | `get_ledger_transactions` |
| PATCH | `/api/ledgers/<int:ledger_id>/transactions/<int:transaction_id>/` | `update_ledger_transaction` |
| POST | `/api/ledgers/<int:ledger_id>/unarchive/` | `unarchive_ledger` |
| GET | `/api/ledgers/fund-aggregation/` | `get_fund_aggregation` |
| DELETE | `/api/ledgers/orphan/` | `delete_orphan_data` |
| GET | `/api/ledgers/orphan/detail/` | `get_orphan_detail` |
| POST | `/api/ledgers/orphan/migrations/` | `migrate_orphan_data` |
| GET | `/api/ledgers/overview/` | `get_ledgers_overview` |
| PATCH | `/api/ledgers/reorder/` | `reorder_ledgers` |
| GET | `/api/ledgers/sales-institutions/` | `list_sales_institutions` |
| GET | `/api/ledgers/securities-aggregation/` | `get_securities_aggregation` |
| GET | `/api/market/overview/` | `get_market_overview` |
| POST | `/api/ocr/parse/` | `ocr_parse_text` |
| POST | `/api/ocr/recognize/` | `ocr_recognize` |
| GET | `/api/performance/money-fund-income/` | `get_money_fund_income` |
| GET | `/api/performance/xirr/` | `get_xirr` |
| GET | `/api/portfolios/` | `list_portfolios` |
| POST | `/api/portfolios/` | `create_portfolio` |
| DELETE | `/api/portfolios/<int:portfolio_id>/` | `delete_portfolio` |
| GET | `/api/portfolios/<int:portfolio_id>/` | `get_portfolio` |
| PATCH | `/api/portfolios/<int:portfolio_id>/` | `update_portfolio` |
| GET | `/api/portfolios/<int:portfolio_id>/holdings/` | `get_portfolio_holdings` |
| GET | `/api/positions/` | `list_positions` |
| POST | `/api/positions/` | `create_position` |
| DELETE | `/api/positions/<int:id>/` | `delete_position` |
| PATCH | `/api/positions/<int:id>/` | `update_position` |
| GET | `/api/positions/<int:id>/transactions/` | `get_position_transactions` |
| POST | `/api/positions/allocate-value/` | `allocate_position_value` |
| POST | `/api/positions/validate/` | `validate_trade_order` |
| POST | `/api/reconciliation/adjustments/` | `apply_adjustment` |
| GET | `/api/reconciliation/discrepancies/` | `list_discrepancies` |
| POST | `/api/reconciliation/discrepancies/<int:discrepancy_id>/ignore/` | `ignore_discrepancy` |
| GET | `/api/reconciliation/ledger-consistency/` | `ledger_consistency` |
| POST | `/api/reconciliation/run/` | `run_reconciliation` |
| GET | `/api/search/assets/` | `search_assets` |
| GET | `/api/securities/<symbol>/price-range/` | `get_price_range` |
| GET | `/api/securities/search/` | `search_securities` |
| GET | `/api/strategy/` | `list_tags` |
| POST | `/api/strategy/` | `create_tag` |
| DELETE | `/api/strategy/<int:tag_id>/` | `delete_tag` |
| DELETE | `/api/strategy/<int:tag_id>/positions/<int:position_id>/` | `unbind_position_tag` |
| POST | `/api/strategy/<int:tag_id>/positions/<int:position_id>/` | `bind_position_tag` |
| GET | `/api/strategy/overview/` | `get_strategy_overview` |
| GET | `/api/strategy/relations/` | `get_all_position_tags` |
| GET | `/api/summary/` | `summary` |
| GET | `/api/summary/distributions/` | `distributions` |
| GET | `/api/summary/ghost-duplicates/` | `ghost_duplicates` |
| GET | `/api/summary/groups/` | `position_groups` |
| GET | `/api/summary/sankey/` | `sankey` |
| GET | `/api/summary/snapshots/` | `list_snapshots` |
| POST | `/api/summary/snapshots/` | `create_snapshot` |
| GET | `/api/temperature/crowding-history` | `get_crowding_history` |
| GET | `/api/temperature/history` | `get_temperature_history` |
| GET | `/api/temperature/multi` | `get_multi_items` |
| GET | `/api/temperature/overview` | `get_temperature_overview` |
| GET | `/api/transactions/` | `list_transactions` |
| DELETE | `/api/transactions/<int:transaction_id>/` | `delete_transaction` |
| GET | `/api/transactions/export/` | `export_transactions` |
| GET | `/api/usage/<feature>/` | `get_usage` |
| GET | `/api/users/` | `list_family_members` |
| PATCH | `/api/users/me/` | `update_me` |
| GET | `/api/users/record-stats/` | `record_stats` |
| GET | `/api/utils/config/` | `get_platform_config` |
| GET | `/api/utils/enums/` | `get_enums` |
| GET | `/api/utils/fund-confirm-dates/` | `calc_fund_confirm_date` |
| GET | `/api/utils/trading-days/<date>/` | `get_trading_day` |
| GET | `/api/watchlist/favorites/` | `list_favorites` |
| GET | `/api/watchlist/groups/` | `list_groups` |
| POST | `/api/watchlist/groups/` | `create_group` |
| DELETE | `/api/watchlist/groups/<int:group_id>/` | `delete_group` |
| PATCH | `/api/watchlist/groups/<int:group_id>/` | `update_group` |
| GET | `/api/watchlist/holding-gaps/` | `holding_gaps` |
| GET | `/api/watchlist/home-summary/` | `home_summary` |
| GET | `/api/watchlist/items/` | `list_items` |
| POST | `/api/watchlist/items/` | `create_item` |
| DELETE | `/api/watchlist/items/<int:item_id>/` | `delete_item` |
| PATCH | `/api/watchlist/items/<int:item_id>/` | `update_item` |
| POST | `/api/watchlist/items/<int:item_id>/favorite/` | `toggle_favorite` |
| DELETE | `/api/watchlist/items/<int:item_id>/groups/<int:group_id>/` | `remove_item_from_group` |
| POST | `/api/watchlist/items/<int:item_id>/groups/<int:group_id>/` | `add_item_to_group` |
| GET | `/api/watchlist/items/<int:item_id>/smart-prompt-conditions/` | `get_smart_prompt_conditions` |
| DELETE | `/api/watchlist/items/<int:item_id>/tags/<int:tag_id>/` | `remove_tag_from_item` |
| POST | `/api/watchlist/items/<int:item_id>/tags/<int:tag_id>/` | `add_tag_to_item` |
| GET | `/api/watchlist/items/export/` | `export_items` |
| POST | `/api/watchlist/reconcile/` | `reconcile_watchlist` |
| GET | `/api/watchlist/tags/` | `list_tags` |
| POST | `/api/watchlist/tags/` | `create_tag` |
| DELETE | `/api/watchlist/tags/<int:tag_id>/` | `delete_tag` |
| PATCH | `/api/watchlist/tags/<int:tag_id>/` | `update_tag` |
| GET | `/api/watchlist/trends/` | `list_trends` |

<!-- AUTO-ENDPOINTS:END -->
