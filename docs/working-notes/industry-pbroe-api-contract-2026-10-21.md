# 行业 PB-ROE 散点 · 接口契约与实施记录（#2481）

> 日期：2026-10-21　性质：**接口契约留档 + 实施记录**
> 评估来源：多多贝调研成果包（2026-10-21）韭圈儿 APK 逆向盘点，能力台账裁决「✅ 第三优先」
> 实现：`backend/app/services/adapters/jiucaishuo_adapter.py` · `sync/jobs/industry_pbroe_job.py` · `services/industry_pbroe_service.py` · `domains/market/views.py`
> 测试：`backend/tests/services/test_jiucaishuo_similar_pbroe.py`（离线、确定性）

---

## 0. 结论先行

| 项 | 结论 |
|---|---|
| 数据源 | 韭圈儿免登录 `POST /v2/guzhi-new2/pbroe-sg2`（2026-10-21 实测 code=0，申万一级全行业一次请求） |
| 存储 | 复用 `market_composites`（`source='jiucaishuo_pbroe'`，一日一快照，删旧写新） |
| 采集 | `IndustryPbroeSyncJob`，日频 cron `40 18 * * *`（错开 index_valuation 18:20 / temperature 20:00） |
| 读取 | `GET /api/market/industry-pbroe/` 单端点，读库即回 |
| 无数据 | job 失败日不落库 → 读侧 `data: null`，前端「暂无数据」 |
| 状态 | 后端链路已完成；前端探市行业比较散点待消费 |

---

## 1. 上游契约（原始响应结构备查）

请求：`POST /v2/guzhi-new2/pbroe-sg2`，payload `{type: 'h5', version: '2.5.9', ss: ''}`（无业务参数）。

```json
{
  "code": 0,
  "message": "请求成功",
  "data": {
    "title": "A股行业PB-ROE",
    "desc": "PB-ROE模型……",
    "_x": "ROE(%)",
    "_y": "PB",
    "update_time": "2026-10-21",
    "series": [
      {"x1": 2.71, "y1": 2.4, "name": "农林牧渔", "color": "#FF5B5B", "bg": "rgba(255,91,91,0.1)"},
      {"x1": -16.78, "y1": 0.78, "name": "房地产", "color": "#FFD249", "bg": "rgba(255,210,73,0.1)"}
    ]
  }
}
```

| 上游字段 | 处理 | 说明 |
|---|---|---|
| `series[].name` | → `industry` | 行业名（上游原文） |
| `series[].x1` | → `roe` | ROE(%)，TTM。**可负**——房地产实测 -16.78，PB-ROE 模型下负盈利行业照样在图上，不剔除 |
| `series[].y1` | → `pb` | PB，最新 |
| `title` / `_x` / `_y` / `update_time` | 透出 | 坐标轴标签与上游数据日期 |
| `color` / `bg` | **不透出** | 上游散点配色（韭圈儿品牌色），前端用自己的设计令牌 |

空 `series`（或解析后为空）= 接口形态变更 → 抛错，job 记 errors，当日不落库。

---

## 2. 读取接口契约

### `GET /api/market/industry-pbroe/`

```json
{
  "data": {
    "title": "A股行业PB-ROE",
    "x_label": "ROE(%)",
    "y_label": "PB",
    "update_time": "2026-10-21",
    "series": [
      {"industry": "农林牧渔", "roe": 2.71, "pb": 2.4},
      {"industry": "房地产", "roe": -16.78, "pb": 0.78}
    ],
    "collected_at": "2026-10-21",
    "source": "jiucaishuo_pbroe"
  },
  "message": "ok"
}
```

- 无快照（从未成功 / job 未跑）→ `data: null`，前端「暂无数据」。
- `update_time` 是上游数据日期、`collected_at` 是本地落库日，前端须标注「数据更新至 update_time」——不伪装实时。
- 读侧只看 `stale=False` 的最近一行（与 temperature 读侧同构）。

---

## 3. 存储决策与保留期

**为什么复用 `market_composites` 而不是新表**：本期只有「当日散点」一个消费场景；历史对比（ROE/PB 时序变化）待有真实场景再立项——提前建表违反「按需存」。`(source, collected_at)` 唯一键天然支持按日幂等。

**保留期注意**：`cleanup_old_data` 清理 composite 超 365 天数据——对「当日快照」无影响（每日新行），但本表**不适合**未来长期对比场景；届时按需迁独立表，勿在此表上堆历史依赖。

**cron**：`40 18 * * *`。错开 index_valuation（18:20）与 temperature（20:00），避免上游短时压力叠加。

---

## 4. 已知边界（诚实披露）

1. **行业口径 = 上游原文**（申万一级）：未做本地行业映射，上游改名/增删行业前端原样渲染。
2. **无历史**：365 天外的 composite 行会被清理，且本就没建历史消费；「行业估值分位变化」类需求出现时重新评估（落独立表 + 全历史）。
3. **展示层未做**：探市行业比较 PB-ROE 散点待前端消费本契约（负 ROE 行业须在图上可见，不得被坐标轴裁掉——建议 x 轴范围自动包含负值）。
