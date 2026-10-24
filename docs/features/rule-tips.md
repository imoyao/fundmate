# 规则驱动静态诊断（持仓小贴士）

> 实现：`backend/app/services/insight/`（规则注册表 + 快照取数）、`GET /api/insight/tips/`、
> 前端 `views/asset/inventory/components/RuleTipsCard.vue`。源 issue `#1017`。

## 它是什么，不是什么

| 是 | 不是 |
|---|---|
| 固定规则在本地算出的**结构风险提示**（集中度、分散度、行业敞口、单日回撤） | 不是大模型生成的观点，不调用任何外部服务 |
| 只陈述「哪条规则此刻成立」+ 触发数值 | 不是买卖建议 |
| 同一账户同一时点**必然相同**的派生结果，不落库 | 不是「历史提示」——没有时间维度语义 |

与 `services/strategy_engine/diagnosis.py`（#2225）的分工：那边回答「标的处于什么状态」
（趋势成立 / 走弱），这边回答「这笔账有什么结构风险」。两者不合并——依据不同，合并后
任何一边都改不动。

## 怎么加一条规则（这是「规则可维护」的全部内容）

1. 在 `backend/app/services/insight/rules.py` 写一个 `check(snapshot) -> dict | None`；
2. 在同一个文件的 `RULES` 列表里加一项（`code` / `severity` / `title` / `rationale` / `check`）；
3. 阈值写成模块级常量，`rationale` 里写清判据。

**不需要改**：视图、契约、前端、API 文档（`code`/`severity` 是字符串，前端按 severity 上色）。
若规则需要快照里没有的数据，才去 `engine.build_snapshot` 加字段——一次查询、所有规则共享。

## 现有规则与阈值

| code | 严重度 | 判据 | 阈值 |
|---|---|---|---|
| `single_name_concentration` | risk | 单一标的市值 / 投资持仓总市值 | ≥ 25% |
| `industry_concentration` | warn | 主口径（csrc）最大行业 / 已穿透市值，且穿透率 ≥ 30% | ≥ 60% |
| `low_diversification` | warn | 投资持仓标的数 | < 3 |
| `portfolio_day_drop` | info | 最近有效交易日组合收益率 | ≤ -2% |

## 数据来源与降级

| 快照字段 | 来源 |
|---|---|
| holdings / 总市值 | `position_aggregation.get_fund_aggregation` + `get_securities_aggregation`（与持仓页同一入口） |
| 行业占比 / 穿透率 | `penetration.build_penetration`（主口径 `csrc`） |
| 最近交易日收益率 | `pnl_calendar.build_daily_pnl_series` 的最近有效日 |

任一路取数失败 → 该维度置空、对应规则不触发，**其余规则照跑**（一条数据源挂掉不该让整页提示消失）。
取不到就不提示，不用 0 冒充：`null` 与「收益率 0」是两件事。

## 已知限制

- **行业口径**：只能用基金定期报告的行业配置（`fund_industry_allocs`），穿透率通常远低于 100%；
  因此行业规则加了「穿透率 ≥ 30% 才提示」的门槛，避免拿 10% 的样本断言「行业集中」。
  「前十大个股 → 行业」目前算不出来（`fund_holdings` 没有 industry 列）。
- **集中度含货基**：分母是全部投资持仓市值（含货币基金）。货基会稀释集中度，即偏保守，不会误报。
- **单日回撤**：用组合级日收益率，不是逐标的跌幅；它回答「昨天整账跌了多少」，不回答「哪只拖累」。
