# 核心 API 端点清单（api）

本文件收录核心 API 完整端点清单（原 SPEC 第 8 章），属于**随代码演进**的事实标准。路由以 `backend/app/domains/*/views.py` 为准。

## 1. 核心 API 完整端点清单（原 SPEC 第 8 章）

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
