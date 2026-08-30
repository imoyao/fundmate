# 未竟之蹊（/the-road-not-taken）页面复活（2026-08-30）

> 关联：`docs/features/watchlist.md` §1.5.7「未竟之蹊」、`frontend/design.md`「Filter & Selection」「空状态与加载态」。
> 结论先行：页面已按设计基线重写为 Masonry 卡片流，主体数据全部接真实接口；**基金经理追踪仍为占位**（后端无实体与接口），复盘日期本次顺带补齐了后端字段。

## 1. 旧页面的问题

`views/asset/favorites/index.vue` 原实现处于「呆萌」状态，主要问题：

- **瀑布流参数用错版本**：`package.json` 装的是 `v3-waterfall@2.x`，但页面传的是 v1 的 `width` / `gutter` / `breakpoints`，v2 实际只认 `colWidth` / `gap`，列宽与列数实际未生效。
- **卡片是空壳**：走势图是写死的「价格走势积累中...」占位 div，`holding_days` / `cycle_count` / `type` 等字段后端根本不返回，卡片等于永远渲染不出内容。
- **类型系统失真**：`store/favorites.ts` + `types/favorites.d.ts` 维护了一套后端没有的 `FavoriteItem`（`type: stock|fund|manager|portfolio`、`cleared_return_pct` 等），与真实接口长期脱节。
- **视觉不成体系**：诗句卡用 `el-alert` 硬编码 `#faf7f2` 等 hex，绕开设计令牌；空状态是干瘪的「暂无特别关注资产」，违反 design.md 空状态硬规范。

## 2. 数据 / 接口可行性评估

| 设计元素 | 数据来源 | 结论 |
|---|---|---|
| 卡片主体（名称/代码/类型/场所/笔记/标签/置顶） | `GET /api/watchlist/favorites/`（已 enrich `display_name` / `tag_ids` / `notes_summary`） | ✅ 真实 |
| 封面走势缩略图 | `GET /api/watchlist/trends/?symbols=&days=`（price_history 回填，#990 已有） | ✅ 真实（无数据降级「走势积累中」） |
| 对比数据条（自选以来 / 区间涨跌 / 持仓收益） | `price_at_added` + `current_price`；trend 首尾；`holding_pnl_percent` | ✅ 真实派生，缺项不显示该格 |
| 状态胶囊（持仓中 / 观察中 / 已清仓） | `holding_quantity` + `GET /api/watchlist/items/?status=cleared` 的 symbol 集合推导（后端不存 CLEARED 状态，见 watchlist.md §1.3.1） | ✅ 真实推导 |
| 标签 chips 增删 | `POST|DELETE /api/watchlist/items/{id}/tags/{tagId}/` | ✅ 真实 |
| 批量置顶 / 批量移出 | `PATCH /api/watchlist/items/{id}/`（`is_pinned` / `favorite`） | ✅ 真实 |
| **下次复盘日期** | 原为 `watchlist` 表缺失字段 | ✅ **本次补齐**（见 §3） |
| **基金经理卡片** | 后端无经理实体/接口（`managers`/`fund_managers` 在 market 域有表但抓取 job 被跳过、无 API） | ⚠️ **占位**：一级胶囊保留「经理」分类，用「设计预览」开关承载示例卡 |
| 清仓次数 / 清仓后对比基准 | `cleared_positions` 有表但无接口，基准指数无落地 | ⚠️ 不展示（禁止编造数值） |

## 3. 本次后端改动（最小增量）

复盘提醒是这一页的核心（`watchlist.md` §1.5.7：标记特别关注时问「什么时候提醒复盘」），但 `watchlist` 表没有落点，故补齐：

- `app/domains/watchlist/models.py`：`next_review_date = Column(Date)`。
- `app/domains/watchlist/schemas.py`：`WatchlistItemOut` / `WatchlistItemUpdate` 增加该字段（PATCH 走 `model_dump(exclude_unset=True)` + `setattr`，无需改视图）。
- `scripts/migrate_watchlist_review_date.py`：幂等 ALTER，覆盖 `invest.db` / `invest.dev.db` / `invest.user.dev.db`（`core/database._validate_schema` 会因模型多列而拒绝启动，故加列必须配套迁移；脚本已在本机执行）。
- **生产 Supabase 需手工执行**：`ALTER TABLE watchlist ADD COLUMN IF NOT EXISTS next_review_date DATE;`

## 4. 前端实现清单

```
views/asset/favorites/
├── index.vue                      页面骨架：诗句卡 + 筛选 + 瀑布流 + 分页
├── constants.ts                   两级胶囊配置、类型色/标签映射、示例卡
├── helpers.ts                     涨跌幅派生、复盘文案（纯函数，无编造值）
├── composables/useRoadNotTaken.ts 数据编排（favorites/trends/tags/cleared）+ 筛选排序分页 + 批量/单卡操作
└── components/
    ├── RoadPoemBanner.vue         弗罗斯特《未选择的路》引言卡（原文保留）
    ├── RoadFilterBar.vue          两级胶囊 + 搜索/排序/管理/示例开关
    ├── RoadBatchToolbar.vue       管理态：已选 N 项 / 批量置顶 / 批量移出
    ├── RoadCard.vue               卡片容器（浏览 / 编辑 / 选中三态）
    ├── RoadCardEditor.vue         编辑态表单（标签增删 + 笔记 + 复盘日期）
    ├── RoadTagChips.vue           胶囊标签组（浏览只读 / 编辑可删）
    ├── RoadSparkline.vue          封面走势 SVG（涨红跌绿，区域渐变）
    └── RoadEmptyState.vue         鹦鹉螺插画 + 「潮有涨落，壳有深浅。算得清，才无患。」
```

删除：`components/BaseFavoriteCard.vue`、`components/NoteEditor.vue`、`store/favorites.ts`（已被新实现取代，无其它引用）。

设计落点（小红书风格 + 品牌）：三列不等高 Masonry（`colWidth` 按容器实宽反推，1440 下严格三列铺满）、封面大图用真实走势 SVG 替代照片、圆角 16px、胶囊标签、底部互动图标、暖奶油底 + 珊瑚红强调。

「让用户慢下来」的处理：卡片只讲三件事——你为什么在意它（笔记摘要）、它现在怎么样（对比数据条）、你打算什么时候回看（复盘提醒）。排序默认「最近更新」，另有「复盘日期」排序把该复盘的顶到前面；趋势/涨跌幅一律降级显示「—」而不编造。

## 5. 后续待办（未做，留痕）

1. **基金经理实体**：需先决策 `managers`/`fund_managers` 是否启用抓取（`fund_manager_job` 当前被跳过），再建 watchlist 侧的经理关注表与接口。
2. **清仓周期接口**：`cleared_positions` 有完整字段（持仓天数/清仓次数/已实现盈亏/基准），但无 API；接入后可替换卡片占位文案，并支撑 `watchlist.md` §1.5.8 清仓分析页。
3. **基准对比**：卡片的「同期基准」需 `benchmark_indices` 落地后再加，当前不展示。
4. **示例卡下线**：`constants.ts` 的 `DEMO_ITEMS` 与「设计预览」开关在经理能力落地后应移除。
