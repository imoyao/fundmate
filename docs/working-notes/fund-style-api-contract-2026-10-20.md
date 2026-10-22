# 基金投资风格箱 · 接口契约与实施记录（#2478）

> 日期：2026-10-20　性质：**接口契约留档 + 实施记录**
> 上游可行性评估：`docs/working-notes/fund-style-tag-feasibility-2026-10-20.md`（同内容已随本卡讨论交付）
> 实现：`backend/app/services/fund_style_service.py` · `domains/funds/views.py` · `sync/jobs/fund_style_job.py`
> issue 号 `#2478`（2026-10-21 建卡落地，原占位号 #2256 与既有 issue 撞车已全局替换）。

---

## 0. 结论先行

| 项 | 结论 |
|---|---|
| 数据源 | 韭圈儿免登录 `POST /v2/tubiao/get-style-history`（唯一实测可用免费完整源，9/9 覆盖） |
| 存储 | 新表 `fund_style_exposures`（long，append-only，无清理）+ `funds.dominant_style/style_period` 派生标量 |
| 采集 | `FundStyleSyncJob` 逐只抓取，目标池限量（`MAX_TARGETS=500`），**月度** cron（`30 22 2 * *`） |
| 读取 | 3 个只读端点（见 §2），全部走 service 纯读层 |
| 测试 | `tests/services/test_fund_style.py` **19 passed**（离线、确定性） |
| 状态 | 后端链路已完成（adapter→job→service→views）；前端消费（详情页/组合页）未做，属 #1968 范围 |

---

## 1. 数据契约（存储层）

### 1.1 `fund_style_exposures`（market 域）

| 字段 | 类型 | 说明 |
|---|---|---|
| fund_code | String(6) | 业务键（裸码） |
| stat_date | Date | 上游时点：月末 + 当月最新点，原样保留 |
| style_name | String(20) | 上游原文 8 分类：大盘成长/大盘价值/中盘成长/中盘价值/小盘成长/小盘价值/港股风格/固收风格 |
| value | SafeNumeric(6,2) | 暴露值(%)，每时点 8 项合计 = 100 |
| source | String(30) | `jiucaishuo_style` |

- **long 而非 wide**：风格名保留上游原文，上游增删分类免迁移表结构（与 `MarketSingleValue` 同构）。
- **append-only**：`UniqueConstraint(fund_code, style_name, stat_date)`，job 去重后纯插入 = 断点续传 + 月度增量。
- **无清理策略**：上游不提供历史回补，断档即永久缺口，故无限保留（与 composite/multi 的 1 年保留不同）。
- 已在 `db_factory.DATA_DOMAIN_REGISTRY` 登记为 market 域（建库守卫强制，漏登记直接 `init_db` 失败）。

### 1.2 `funds` 派生标量

| 字段 | 说明 |
|---|---|
| dominant_style | 最新 stat_date 时点暴露值最大的风格（并列取上游序列首位，确定性） |
| style_period | 上述时点 ISO 串（口径与版本留痕） |

「无源即不派生」：抓不到风格箱的基金保持 NULL，不用 '未知' 或旧值冒充（同 `equity_position` 先例）。
筛选场景（列表页按风格过滤）应排除 QDII 后使用本字段——韭圈儿对海外资产映射存疑（270042 纳指100 实测「固收风格 81.28」）。

---

## 2. 读取接口契约（3 个只读端点）

统一约定：成功 `{"data": ..., "message": "ok"}`；**数据不足回 `data: null` / 空数组，不编造占位值**；后端不返回颜色（配色是前端令牌的事）。

### 2.1 `GET /api/funds/<fund_code>/style/latest/` — 最新风格箱（详情页）

```json
{
  "data": {
    "fund_code": "000001",
    "stat_date": "2026-10-16",
    "styles": [
      {"style_name": "大盘成长", "value": 45.6},
      {"style_name": "大盘价值", "value": 18.0}
    ],
    "dominant_style": "大盘成长",
    "style_period": "2026-10-16",
    "prev_dominant_style": "大盘价值",
    "prev_period": "2026-09-30",
    "dominant_changed": true,
    "source": "jiucaishuo_style"
  },
  "message": "ok"
}
```

- `styles` 恒 8 项，**固定展示序**（大盘成长→固收风格；上游调序不影响响应，未知名追加末尾）。
- `prev_*` / `dominant_changed` = 上一时点主导风格与漂移信号（最粗粒度「宣称 vs 实际」监控；细粒度曲线走 2.2）。
- 无数据 → `data: null`，前端降级「—」。

### 2.2 `GET /api/funds/<fund_code>/style/history/?limit=N` — 漂移序列（月度倒序）

```json
{
  "data": {
    "fund_code": "000001",
    "count": 3,
    "points": [
      {"stat_date": "2026-10-16", "styles": {"大盘成长": 45.6, "大盘价值": 18.0}},
      {"stat_date": "2026-09-30", "styles": {"大盘成长": 42.0, "大盘价值": 19.0}}
    ]
  },
  "message": "ok"
}
```

- **wide 形态**（每时点一个 `{风格名: 值}` 字典）——前端画 8 条风格曲线少一次客户端透视。
- `limit` = 时点数，默认 60（≈5 年），硬上限 500（覆盖上游实测最长 283 点）；非法值**静默回退默认**，不 400（展示接口不该因查询参数报错）。

### 2.3 `GET /api/funds/style/portfolio/` — 组合加权风格暴露（家庭作用域）

```json
{
  "data": {
    "styles": [
      {"style_name": "大盘成长", "value": 45.0},
      {"style_name": "大盘价值", "value": 10.0},
      {"style_name": "固收风格", "value": 45.0}
    ],
    "fund_count": 2,
    "covered_market_value_cents": 4000,
    "total_market_value_cents": 6000,
    "coverage_pct": 66.67,
    "period_from": "2026-09-30",
    "period_to": "2026-09-30",
    "uncovered": [{"symbol": "000003", "name": "某基金", "market_value_cents": 2000}],
    "source": "jiucaishuo_style"
  },
  "message": "ok"
}
```

口径（与 `strategy_engine/allocation.py` 一致，勿在 service 外重写市值逻辑）：

1. 持仓范围 = `asset_type ∈ (fund, money_fund, etf)`；股票不在风格箱口径内。
2. 市值 = `position_valuation.market_value_cents`（净值走 `NavService` 本地读 `allow_remote=False`，外币按 `EXCHANGE_RATES` 折 CNY）；同一 symbol 多账户先合并。
3. 每只基金取**各自最新时点**箱体加权（不强制对齐共同日期——新基金时点少，对齐会整体排除、低估覆盖）；单只箱体合计 = 100，故加权合计恒 = 100。
4. **无箱体持仓不计入加权，但全额进分母与 `uncovered`**——覆盖率是结果的一部分。
5. 全 0 市值（如仅 balance 模式未录市值）→ `styles: []`、`coverage_pct: 0`，不显示全零箱体。

---

## 3. 采集与调度

- **cron**：`30 22 2 * *`（每月 2 日 22:30，错开 22:00 advisor / 22:15 position_price）。上游按月更新（月末点 + 当月最新点），日变更量为 0，每日跑纯属浪费。
- **目标池**：`('fund', 'etf')` 两池裸码；`__full__` / 空 targets = 显式跳过，禁止退化全库（data-strategy.md §4.3.3）；超 500 截断告警。
- **不剔货基**（与 fund_position 的关键差异）：货基/债基的固收风格箱是有效数据。
- **freshness**：抓取失败记 `stats.errors`（#1833 同款），由 freshness 观察暴露；断档时点永久缺失（上游无回补）。
- 已入 `SYMBOL_BACKFILL_JOBS` 守卫名单：裸 `--full-sync` 不带范围会被 `require_full_sync_scope` 拒绝（`test_full_sync_scope.py` 同步登记）。

---

## 4. 测试证据（2026-10-20，`PYENV_VERSION=3.11.1`）

`tests/services/test_fund_style.py` **19 passed**，分四组钉口径：

| 组 | 用例数 | 钉住的口径 |
|---|---|---|
| adapter 解析 | 5 | 端点常量；等长矩阵解析；**长度不一致抛错**（错位比失败更糟）；空响应抛错；`cycle='1y'` |
| job | 6 | ETF 归一化/股票剔除；空池与 `__full__` 跳过；500 截断；空池不触发抓取；**复合键去重 = 断点续传**（二次跑 0 新行）；无源不派生 |
| service | 7 | 固定展示序；dominant/prev_dominant/漂移信号；无数据回 None；history wide+limit 收敛；**组合加权数学 + 覆盖率 + uncovered**；ETF 前缀归一化 + 快照价回退；零市值回空 |
| views | 1 | 三端点 200 + 载荷断言 + 无数据 `data: null` + 非法 limit 不 400 |

回归：`tests/services/sync/ + thermometer + industry_emotion + fund_style` 共 **470 passed, 0 failed**。
全量套件（`pytest tests/`，2026-10-20）：**3506 passed / 7 skipped / 17 failed**，失败全部与本次改动无关，逐条归因：

| 失败组 | 数量 | 归因 | 证据 |
|---|---|---|---|
| `test_issue_refs_check` | 9 | 环境：本树为 tarball 解包无 `.git`，测试按设计依赖 `origin/dev` ref | 测试文件 docstring 自述「CI 无 ref 必挂」；备份树同败 |
| `test_guard_mojibake` | 3 | 环境：git 依赖 | 备份树同败 3 |
| `test_industry_crowding` | 2 | 存量失败 | 备份树同败 2 |
| `test_xirr_engine::test_case10_extreme_loss` | 1 | 存量失败（纯函数数值） | 备份树同败 1 |
| `test_api_conventions` | 1 | **本次改动引入并已修**：新端点未同步 api.md 自动段 → `--write` 重建（与上游纯净树 diff 精确等于 3 个风格端点） | 修复后复跑通过 |
| `test_manager_profile_chain` | 1 | 共享库自污染：该测试不走 app 夹具、写 git 随附的 `invest.db`，首跑留株、次跑种子插入撞唯一约束；清株后 7/7 过 | 清残留复跑验证；与代码无关 |

---

## 5. 已知边界（诚实披露）

1. **QDII 映射存疑**：韭圈儿把海外资产映射进 A 股风格箱（270042 纳指100 → 固收风格 81.28）。落库原值，消费方（筛选/组合透视）应排除或注明来源。
2. **裸 6 位股票码无法与基金码区分**：`resolve_pool` 对裸码一律按基金进池（与 fund_position 同构），上游对股票返空 → `_allow_empty_data` 跳过，无副作用但多一次请求。
3. **展示层未做**：详情页风格箱/漂移图（#1968 范围）、筛选器风格维度、组合页条形图均待前端消费本契约。
