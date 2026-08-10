# 资产总览同比真实化：历史快照方案（2026-08-09）

## 背景与问题

`frontend/src/views/asset/AssetPanorama.vue` 顶部总览大卡片存在硬编码假数据：

- `L50`：`<RiseFallText :value="12.3" .../>`「较上月」——**写死 12.3%**
- `L54`：`<RiseFallText :value="8.7" .../>`「较去年同期」——**写死 8.7%**
- `L67`：`中等风险` 徽标——**写死**
- `L73`：`风险评分：65/100`——**写死**

「较上月/较去年同期」需要上月末、去年同月末的总资产作为基准，但**后端无任何历史总资产存储**（见下），因此这三个展示位要么造假、要么降级。

## 根因（实证）

后端现状（grep `snapshot|历史|period|月度` 于 `backend/app`）：

| 能力 | 有无 | 说明 |
|---|---|---|
| 总资产/净资产历史快照表 | ❌ 无 | 无 `asset_snapshots` 类表 |
| assets / positions 历史版本 | ❌ 无 | 仅当前值（`created_at/updated_at`），无历史值 |
| transactions 流水 | ✅ 有 | 买卖记录带日期，但**无价格历史无法估值** |
| price_history 证券行情 | ✅ 有 | 仅覆盖部分证券（价格历史非全量） |
| 现金/房产类静态资产历史 | ❌ 无 | 无历史，流水回放无法重建 |

结论：**计算真实月度/年度同比必须先新增「总资产快照」存储**，从今天起积累；历史期（过去月份）无数据，界面降级展示。

## 方案对比与选型

### 方案 A：资产快照表（推荐）

新增 `asset_snapshots` 表，每日记录一次当日总资产/负债/净资产，前端读取计算同比。

- **优点**：模型简单、准确（用当日实时聚合值，不依赖价格历史）；从今天起即可积累，属正确长期方向；与家庭账本「云端权威」架构一致
- **缺点**：历史空白——过去月份无快照，同比需「积累期」才能显示（月度约 1 个月、年度约 1 年）
- **回填**：可用 transactions 流水做「近似回填」属可选增强（方案 B 的子集），首版不做

### 方案 B：交易流水回放重建历史资产

给定日期 D，用当日全部交易 + 价格历史推演该日持仓市值，再叠静态资产倒推总额。

- **优点**：可回溯历史
- **缺点**：严重依赖 price_history 全量覆盖（现状非全量）；静态资产（现金/房产）无历史无法回放；实现复杂度高、正确性难保证；财务记账场景「近似值」容易误导
- **结论**：现阶段不做，列为远期（P3）

## 方案 A 详细设计

### 1. 数据模型（`backend/app/domains/summary/models.py` 新增）

```python
class AssetSnapshot(Base):
    __tablename__ = 'asset_snapshots'
    id = Column(Integer, primary_key=True)
    user_id = Column(String(36), nullable=False, index=True)   # 多用户私有
    snapshot_date = Column(Date, nullable=False)               # 本地日期（上海时区）
    total_assets = Column(Integer, nullable=False)             # 整数分（Money 精度）
    total_liabilities = Column(Integer, nullable=False)
    net_worth = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    # 唯一约束 (user_id, snapshot_date)，幂等 upsert
    __table_args__ = (UniqueConstraint('user_id', 'snapshot_date'),)
```

约定：金额一律整数分（×100），换算走 `app/core/money.py`；`snapshot_date` 用 `now_shanghai().date()`（`core/time_utils.py`）。

### 2. 写入时机（推荐组合，首版取 A1）

- **A1 惰性写入（首版）**：前端总览页每次打开调用 `POST /api/summary/snapshots/`，后端按当日 `upsert` 快照（同日存在则更新为最新）。无 cron 依赖、无后台任务，页面打开即积累，失败静默不阻塞。
- **A2 每日 sync job（后续增强）**：`grab` 调度链加一个轻量 job 每日记录，与 A1 幂等不冲突。

### 3. 接口（`backend/app/domains/summary/views.py` 新增）

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/summary/snapshots/` | POST | 记录当日快照（幂等 upsert；body 可选 `snapshot_date` 用于回填，默认今天） |
| `/api/summary/snapshots/` | GET | 查询快照列表，`?start_date=&end_date=`（含）按日期升序；带 `monthly_change_pct`/`yearly_change_pct` 由后端计算（基准：上月同日/去年同日的最近一条；无数据为 `null`） |

响应统一 `{data, message, error_code}` 信封；GET 返回分页结构（与项目其它列表一致）。**同比百分比由后端算**，前端不二次运算。

- `monthly_change_pct = (本月值 - 上月最近值) / 上月最近值 * 100`
- `yearly_change_pct = (本月值 - 去年同月最近值) / 去年同月最近值 * 100`
- 基准取「最近一条不晚于基准日」的快照；找不到 → `null`

### 4. 前端改动（`AssetPanorama.vue`）

- `mounted` 后异步调 `POST /api/summary/snapshots/`（失败静默，不阻塞首屏）
- `fetchData` 并行拉 `GET /api/summary/snapshots/`，把 `monthly_change_pct`/`yearly_change_pct` 接入 L50/L54 的 `RiseFallText`
- 无数据时（`null`）降级展示：`——` + tooltip「暂无上月/去年同期数据，持续使用后自动积累」，**彻底删除硬编码 12.3/8.7**
- 新增 `frontend/src/api/summary.ts` 的 `postSnapshot` / `getSnapshots` + 类型

### 5. 风险评分处置（需决策）

「中等风险 65/100」无任何后端引擎支撑，与同比同属假数据。选项：

- a) **删除**该行展示（推荐，不造假，待未来接入真实风控再恢复）
- b) 隐藏并保留注释占位
- c) 保留现状（不推荐）

## 影响范围与回滚

- **后端**：纯新增（表 + 2 端点 + service），不改现有接口契约，`market_value/pnl` 等不动
- **DB**：`migrations/` 不入库，模型变更后需重建 DB 或手动建表（`create_all` 会补新表）；不影响既有数据
- **前端**：仅 `AssetPanorama.vue` + `api/summary.ts`
- **回滚**：前端 git revert；后端删表删端点即可，零副作用（未动既有行为）

## 验证

- 后端：pytest 新增 `TestSnapshotsEndpoint`（upsert 幂等、分页、同比计算正确、无历史返回 null、多用户隔离、`snapshot_date` 越界 400）
- 前端：`pnpm typecheck` + eslint/prettier；手动打开总览页确认同比显示与降级
- 后端全量单进程 pytest 回归

## 待确认决策点

1. 快照写入时机：首版 A1（页面惰性 upsert）是否可行？还是要叠加 A2 每日 job？
2. 风险评分「中等风险 65/100」：删除 / 隐藏 / 保留？
3. 同比基准：取「基准日当天或之前最近一条」还是「月初/月末对齐」？（推荐前者）

## 实施结论（2026-08-10 落地）

1. **写入时机 = A1 首版**：采用页面惰性 upsert（`AssetPanorama.mounted` 静默 `POST /api/summary/snapshots/`，同日幂等覆盖）。A2 每日 sync job 暂不叠加，后续如需再单独加，与 A1 幂等不冲突。
2. **风险评分 = a) 删除**：按方案推荐删除「中等风险 65/100」硬编码展示行，不造假；未来接入真实风控引擎再恢复。
3. **同比基准 = 「基准日当天或之前最近一条」**：月度对上月同日、年度对去年同日前最近一条快照（`_nearest_before` + `_shift_months`）。积累期无历史返回 `null`，前端降级「—— + tooltip」。
4. **模型隔离键修正**：方案初稿用 `user_id`，落地时按代码实况（D1 家庭共享层）统一为 **`family_id`**，与 `get_family_id()` / 其余账本聚合一致，unlimited 快照同 family 可见（家庭账本语义）。
