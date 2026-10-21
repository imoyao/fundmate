# 相似基金 · 接口契约与实施记录（#2480）

> 日期：2026-10-21　性质：**接口契约留档 + 实施记录**
> 评估来源：多多贝调研成果包（2026-10-21）韭圈儿 APK 逆向盘点，能力台账裁决「✅ 第二优先」
> 实现：`backend/app/services/adapters/jiucaishuo_adapter.py` · `services/similar_fund_service.py` · `domains/funds/views.py`
> 测试：`backend/tests/services/test_jiucaishuo_similar_pbroe.py`（离线、确定性）

---

## 0. 结论先行

| 项 | 结论 |
|---|---|
| 数据源 | 韭圈儿免登录 `POST /v2/fund-lists/simfund`（2026-10-21 实测 code=0） |
| 存储 | **不落库**——相似度是快照概念、名单月变，建历史无消费场景（「按需存」） |
| 采集 | 无 job。按需取 + `CacheService` 两级缓存（进程 LRU + 文件，TTL 6h） |
| 读取 | `GET /api/funds/<fund_code>/similar/` 单端点 |
| 降级 | 上游失败/超时/形态异常 → `items=[] + degraded=true`，**不 500**（验收第 3 条） |
| 状态 | 后端链路已完成；前端详情页「相似基金」块待消费 |

---

## 1. 上游契约（原始响应结构备查）

请求：`POST /v2/fund-lists/simfund`，payload `{fund_code, type: 'h5', version: '2.5.9', ss: ''}`。

```json
{
  "code": 0,
  "message": "相似基金",
  "data": [
    {"fund_code": "210004", "fund_simple_name": "金鹰稳健成长混合",
     "fund_income_12": "8.33", "fund_income_1000": "3.3974",
     "param": "近1年", "sml_topn_fd": "100"}
  ]
}
```

字段语义（2026-10-21 实测 + 三组样本交叉验证）：

| 上游字段 | 处理 | 说明 |
|---|---|---|
| `fund_code` / `fund_simple_name` | 透出 | 裸码与简称 |
| `sml_topn_fd` | → `similarity`（float） | 0-100 相似度分。**只给前若干名打分，其余为 null**——保持 None 不补 0：「没打分」与「得分 0」是两件事 |
| `fund_income_12` | → `income_1y_pct`（float） | 近 1 年收益率 %（字符串） |
| `param` | → `window` | 上游收益口径标签（如「近1年」），逐条原样带上 |
| `fund_income_1000` | **不透出** | 三种候选口径（万份收益/成立以来/千元收益）经货基（000198）与主动基金（110011）三组样本交叉验证**全部自相矛盾**，语义未实证的数字不进公开响应——宁缺毋假。仅在本契约与 parse docstring 记原始字段名备查 |

空 `data` 是合法形态（上游无相似基金）→ 空列表；`data` 键缺失（None）才是接口形态变更 → 抛错由上层降级。

---

## 2. 读取接口契约

### `GET /api/funds/<fund_code>/similar/`

```json
{
  "data": {
    "fund_code": "000001",
    "items": [
      {"fund_code": "210004", "fund_name": "金鹰稳健成长混合", "similarity": 100.0, "income_1y_pct": 8.33, "window": "近1年"},
      {"fund_code": "000549", "fund_name": "华安大国新经济股票A", "similarity": null, "income_1y_pct": 0.73, "window": "近1年"}
    ],
    "degraded": false,
    "error": null,
    "source": "jiucaishuo_similar",
    "fetched_at": 0.842
  },
  "message": "ok"
}
```

- 上游失败时 `degraded=true`、`items=[]`、`error` 有值——前端显示「暂时取不到」而非空白或报错页。
- `similarity=null` = 上游未打分，前端渲染「—」，**不得当作 0 排序垫底之外的意义**（可排序，但与 0 区分展示）。
- 相似度口径是上游黑盒，前端须注明「数据来源：韭圈儿」。
- `fetched_at` 为本次取数耗时（秒），调试用；缓存命中时同样存在（命中值 = 首次取数的值）。

### 缓存与节流

- `CacheService(namespace='similar_funds')`，TTL 6h（相似度名单月变量级；抗详情页重复打开）。
- adapter 侧另有 2s 模块级节流 + 3 次指数退避（既有 `_post` 机制），与全韭圈儿源共享。
- 单次返回 `SIMILAR_MAX_ITEMS=20` 条封顶（上游实测 5-6 条；防上游异常放大）。

---

## 3. 已知边界（诚实披露）

1. **相似度口径黑盒**：上游未公开算法，不做「宣称 vs 实际」解读；仅作参照列表。
2. **QDII / 海外基金**未验证：上游对海外资产的相似逻辑未实测，前端不做特殊承诺。
3. **展示层未做**：详情页「相似基金」块待前端消费本契约。
4. **不落库的代价**：无历史名单、无法做「相似名单漂移」分析——当前无消费场景，若出现再立项（届时优先考虑落 `fund_similar_snapshots` 日快照表）。
