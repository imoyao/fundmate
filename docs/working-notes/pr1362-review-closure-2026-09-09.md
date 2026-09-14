# PR #1362 复审收束报告（2026-09-09）

> 对应 PR：`feat/watchlist-unified-code-search`（#1362，目标 `dev`）
> 关联：#1286 统一编码 / #275 指数日线 / #1365 指数名录三源 / #1366 名录源实测
> 提交：`51cb0ba`（评审 #1 指数加自选崩溃）→ `b86d4b2`（第一轮收束）→ `0db30b8`（第二轮：行内评审 + 万得指数补齐）

## 一、评审意见总览与处置

PR #1362 上的评审意见分两批：owner 自评 6 条（第一轮收束，见 commit `b86d4b2`）与 AI review 行内评论 18 条（第二轮收束，见 commit `0db30b8`）。

### 1.1 owner 自评 6 条（第一轮）

| # | 意见 | 处置 |
|---|---|---|
| 1 | 指数无法加入自选（严重） | `51cb0ba` 修复：`watchlist_service` 补 `index` 分支 |
| 2 | index 分支 market 不一致 | 随 #1 一并解决 |
| 3 | 唯一键迁移未自动执行 | `b86d4b2`：迁移收敛进 `app/core/migrations.py`，`init_db` / `init_db_split` 启动期自动执行（幂等），附 SQLite 引擎守卫 |
| 4 | `migrate_index_catalog_core_fields.py` 疑似死代码 | owner 自纠：非死代码，保留 |
| 5 | 指数前缀码搜索不匹配 | `b86d4b2`：`_search_indices` 加 `exchange||index_code` 拼接匹配 |
| 6 | 测试覆盖不足 | `b86d4b2`：补 API 回归与迁移单元测试 |

### 1.2 AI 行内评审 18 条（第二轮）

**已修 8 处**：

1. `search/views.py` 两处响应缺 `error_code` → 补齐契约三字段 `{data, message, error_code}`；前端 `search.ts` 类型同步；`test_asset_search.py` 断言信封完整性。
2. `watchlist.venue` 补 `nullable=False`（与 `market` 列一致）。
3. **新增迁移 `migrate_watchlist_venue_not_null`**：回填历史 NULL venue。SQLite `UNIQUE` 中 NULL 互不相等，存量 NULL 会让 `(symbol, market, venue)` 对该行静默失效——这是第一轮 #3 修复漏掉的「数据回填」半边。
4. `useAssetSearch.ts` **[主要]** 防抖被新输入打断时旧 Promise 永不 settle → `await` 方永久挂起。修法：打断时先 `settlePending([])`。
5. `useAssetSearch.ts` **[次要]** 晚到旧响应覆盖新结果 → 加请求序号 `seq` 丢弃过期响应，`loading` 仅由最新请求收尾。
6. `index_catalog_job._save_data` 空数据防御性 return（该方法整体 DELETE 重建名录）。
7. `test_watchlist_unified_code.py` portfolio 用例补 `venue == ''` 断言。
8. 文档：changelog 版本元数据同步 v4.8.6；`watchlist.md` 回查路由改「先按 `asset_type` 判定再回查实体表」（原按 `MGR_` 前缀会把基金/股票/指数误路由到投顾组合）；1.3.8/1.3.9 编号空洞补说明（不复用编号）。

**不采纳 5 条（误报）**：

| 意见 | 驳回理由 |
|---|---|
| 指数表未注册数据域 | `index_catalog`/`index_daily` 已在 `db_factory.DATA_DOMAIN_REGISTRY` L71-72 |
| loguru 应用 `{}` 占位符 | 全项目（含 `SyncJob` 基类）统一 f-string，单独改反而不一致 |
| 空数据 DELETE 清表 | 基类 `run()` 已用 `if new_data:` 守住（L155/L191），不会触发 |
| `ak.index_stock_info_sina()` 返回成份股 | 代码用 `ak.index_stock_info()`（非 `_sina` 版），已兼容新旧列名（#1366 实测） |
| working-notes 索引遗漏两条 | 对应两文件已删除，索引无误 |

## 二、万得指数覆盖确认与补齐

### 2.1 背景

用户在韭圈儿页面可见 8 个万得指数，质疑 `WIND_INDEX_TARGETS`（13 个）覆盖不全。用 `JiucaishuoAdapter.fetch_index_daily(gu, 12)` 逐个实测，**8 个全部可取**，原清单仅覆盖 3 个。

### 2.2 实测结果（2026-09-09）

| 代码 | 名称 | 近12月 | 全量落库 | 价格模式 | 原清单 |
|---|---|---|---|---|---|
| 881001.WI | 万得全A | 242 | 6465（2000-01-04 起） | anchored | 已有 |
| 881003.WI | 万得全A(除金融、石油石化) | 239 | 6458（2000-01-04 起） | anchored | **漏抓→已补** |
| 881007.WI | 万得300除金融 | 242 | 4074（2009-11-30 起） | anchored | **漏抓→已补** |
| 8841425.WI | 万得小市值指数 | 186 | 3662（2011-01-04 起） | anchored | **漏抓→已补** |
| 8841431.WI | 万得微盘股指数 | 242 | 6466（1999-12-30 起） | normalized | **漏抓→已补** |
| 885000.WI | 万得普通股票型基金指数 | 237 | 5504（2003-12-31 起） | normalized | 已有 |
| 885007.WI | 万得混合债券型二级基金指数 | 237 | 5504（2003-12-31 起） | normalized | 已有 |
| 889033.WI | 万得可转债等权指数 | 239 | 2104（2017-12-29 起） | normalized | **漏抓→已补** |

补齐后清单 18 个目标。历史完整性已跑 `pdm run python -m app.tools.sync_cli job index_daily --full-sync` 并查库确认（全量 `date='all'` 取成立来；每日增量拉近 12 月为自愈窗口，upsert 覆盖同日，锚点平移属预期）。

### 2.3 数据口径备注

- **8841425（小市值）近 12 月仅 186 条**（同期 239–242），源侧序列偏短，代码已注释「待观察」。
- **8841431 / 889033 无收盘价锚**，走 `normalized`（起点归一化 1000）；适配器原注释「normalized 仅用于 885 系」已修正。
- **881003 全量截止 2026-09-07**，比其他指数晚一个交易日，源侧延迟，每日增量自愈。
- 清单中 8 个 `⏳ 未收录`（885002/885005/885006/885008/885072-075）保留，收录后自动生效。
- 韭圈儿无指数枚举端点，「够不够」只能按已知候选码逐个实测，无法穷举。
- **估值分位未落库**：`index-basic` 返回的 `pe_pct`（韭圈儿页面「近5年市盈率百分位」）未存 `IndexDaily`，如需展示属新需求（建议单开 issue）。

## 三、验证与遗留

- 后端全量单进程 pytest：1289 passed；`ruff check` 全过；pre-commit 全绿（含中文乱码守卫）。
- 前端 `tsc --noEmit` 无错误（本机 `pnpm typecheck` 报 `tsc is not recognized` 系 pnpm `.bin` shim 缺失的环境问题，改用 `node node_modules/typescript/bin/tsc` 验证）。
- `test_default_targets_cover_wind_family` 由硬编码 `len == 13` 改为「必须覆盖品种」断言，避免每次补品种改数字。

**遗留项**：
1. 8841425 源侧序列偏短需持续观察，做长周期对比时注意防御。
2. PE/PB 估值分位落库（新需求，未在本 PR 做）。
3. 8 个未收录指数每次同步各消耗一次失败重试（约 28s/个），可考虑降频探测。

[AI 创建] · AI-Created-By: CodeBuddy AI · 2026-09-09
