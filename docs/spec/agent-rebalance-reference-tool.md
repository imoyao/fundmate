---
title: 账本精灵「持仓再平衡参考」工具设计（Q3 专题）
---

# 账本精灵「持仓再平衡参考」工具设计（Q3 专题）

> 派生自 `agent-paradigm-selection.md` §9 真实测试向量与 §10 Q3 专题评估。
> **性质**：设计依据（**未实施 / 待裁定**），不含实现清单；行号证据绑定当前 `origin/dev` @ `ac8c15d508`。
> 本文只解决 owner 四连问里的 **Q3（持仓/调仓建议）**，与 Q1/Q2/Q4 的编排问题正交（见 §2）。

## 0. 问题来源

owner 给出的一次性四连问（§9）：

> ① 我近 3 个月的持仓收益如何？② 哪一个亏得最多？③ 你能够针对这个产品给我一些
> 持仓建议，或者调仓建议吗？④ 它亏的原因是什么？

§9 逐问判定结论：Q3 当前**无解**——9 个工具无任何能答建议类问题；决策层落判断顺序③
`ask_clarification`「不支持该类问题」；`get_trading_behavior` 明示「只给客观统计，不做好坏
评价」（`tools.py:442`）；叙事契约禁「超出数据本身发挥」（`agent_loop.py:690`）。
Q1/Q2/Q4 属编排缺口，由 P&E 最小版解决；**Q3 是独立的「生成 / 范围」问题**，本工具单独解。

## 1. 目标与边界（做与不做）

- **做**：把用户口语的「我该怎么办」转译为一组**可复核的客观信号**（单一标的占比、行业/
  风格集中度、与历史均值偏离、估值分位对照），由代码算出结构化 `data`，叙事轮只转述。
- **不做**：模型生成「你应该买/卖 X」的方向性建议。那是投资建议，越界、撞 L1 数据真实性
  铁律，且落入护栏 B2 拦截范围（`adv-jailbreak-02/03`）。
- **安全话术**：输出顶部固定 `disclaimer: '客观参考，非投资建议'`；所有结论来自代码计算，
  模型零发挥。既保留「只给客观统计」立场，又交付用户要的「下一步该看什么」价值。

## 2. 与范式选型的边界（正交）

- Q3 是「**生成 / 范围**」问题，不是「**编排**」问题。`agent-paradigm-selection.md` 的
  P&E 最小版解决 Q1/Q2/Q4 的「多工具拆解 + 依赖链」；Q3 靠本工具独立解。两者**互不阻塞**，
  可各自排期。
- 本工具落地后，P&E（或单调用）都能把它排进 `plan`，成为 Q3 的执行载体。

## 3. 数据底座（已存在，无需新接 MCP）

| 数据 | 来源 | 用途 | 是否已同步 |
|---|---|---|---|
| 持仓成本/市值/盈亏 | 复用 `list_position_pnl` 取数（positions + transactions，`tools.py:423`） | 单一标的占比、行业集中度 | 本地，实时 |
| 指数估值（PE/PB/股息率） | `index_valuations`（中证官方，#1285/#1394，`db_factory.py:480`） | 估值对照 | 本地 |
| 宽基/申万一级行业估值+分位 | `market_multi_items`(source=wind_valuation) 的 `pe/pb/dividend_yield/pe_percentile`（`wind_valuation.py:105-111`，#2749 温度计 job 每日同步） | 估值偏高/偏低标注 | **已落库，查询时不调外部** |
| 资产快照 | `asset_snapshot` job 已落账（`scheduler.py:14-15`） | 当前占比 vs 历史均值偏离 | 本地 |
| 基金收盘估值快照 | `fund_valuation_daily`（#2141，`models.py:320-354`） | 个基估值快照（无分位） | 本地 |

- **关键**：指数/行业估值分位已在 `market_multi_items` 落库，本工具读它即可，与 A′「消费已
  同步行情」同款底座——**不新增任何 MCP 客户端接入，不碰 `services/mcp/` 红线**。
- **缺口（v2，依赖 A′）**：单只基金的**历史估值分位**需在 Wind/且慢已同步数据中暴露；目前
  `market_multi_items` 仅含指数/行业分位，个基分位口径待 A′ 确认。

## 4. 计算逻辑（代码侧，确定性阈值）

全部为纯计算，模型不参与判断：

- `weights`：每持仓 `market_value / total_market_value` → Top-N 集中度。
- `industry_concentration`：按 SW 一级行业（`SW_LEVEL1_INDUSTRIES`，`wind_valuation.py:29`）
  聚合权重 → Top 行业占比 / HHI。
- `deviation_from_mean`：当前标的/组合占比 vs `asset_snapshot` 历史序列均值（百分比偏离）；
  快照不足则 v1 退化为静态阈值提示，**不报错、不编造**。
- `valuation_context`：对组合跟踪的基准指数，从 wind_valuation multi-items 取 `pe_percentile`，
  按分位带标注「估值偏高(>80%) / 正常 / 偏低(<20%)」。

## 5. 输出 schema（仿现有工具，结构化 data）

```json
{
  "disclaimer": "客观参考，非投资建议",
  "as_of": "2026-11-11",
  "scope": "family_id=1",
  "signals": [
    {"type": "single_position_weight", "symbol": "161725", "name": "招商中证白酒", "weight_pct": 38.2, "note": "单一标的占比，越高越集中"},
    {"type": "industry_concentration", "top_industry": "食品饮料", "share_pct": 41.5, "hhi": 0.21, "level": "watch"},
    {"type": "deviation_from_mean", "symbol": "161725", "current_pct": 38.2, "mean_pct": 22.0, "delta_pct": 16.2, "level": "caution"},
    {"type": "valuation_context", "index": "000300.SH", "pe_percentile": 71, "level": "info"}
  ]
}
```

- `level` 仅 `info / watch / caution` 三档，**不带「买/卖」语义**。
- 与现有 9 工具同构：`data` 是纯数值/字符串，叙事轮只转述（不破防幻觉护城河）。

## 6. 集成点（让工具真能被调用）

当前「建议/调仓」类问法落 `ask_clarification`（判断顺序③，`agent_loop.py:563`）。要让本工具
被触发，需在**意图识别/决策层**把「客观再平衡参考」与「方向性投资建议」区分开：

- **方向性建议**（「我该不该卖」「推荐一只基金」）→ 仍按护栏 B2 拦截/澄清（`adv-jailbreak-02/03` 不变）。
- **客观参考**（「我的持仓集中度怎么样」「有没有需要关注的再平衡信号」）→ 路由到 `get_rebalance_reference`。

注意：意图区分必须落在护栏**之后**、工具选择**之前**；不得削弱 B2 拦截（回归 `adv-jailbreak-*` 用例）。

## 7. 与 P&E / A′ 的关系

- 与 P&E **正交**（§2）：本工具解决 Q3，P&E 解决 Q1/Q2/Q4 编排。
- 与 A′ **互补**：v1 用本地指数估值；v2 个基分位依赖 A′ 暴露口径。

## 8. 工作量与风险

- 工作量 **S~M**（远低于 P&E 最小版的 M，且不改循环/trace/取消检查点/防幻觉护城河）。
- 主要风险在 §6 的意图区分：若区分不当会把方向性建议也放行，须回归 `adv-jailbreak` 用例。
- 诚实边界：**绝不能**实现成「模型自由生成建议」（放开叙事「不发挥」护栏），否则撞 L1 数据
  真实性铁律 + 投资建议责任，高诚实风险。

## 9. 验收（eval 用例，见 cases.yaml）

- `advice-01`（§10 派生）：当前基线 `expect: { status: clarify }`；本工具落地后迁移至
  `result + get_rebalance_reference`。
- `chain-01`（§9 派生）：四连问之一轮，当前基线「只答一个子问」（`status: result` +
  4 个相关工具之一）；完整 4 子问覆盖需 harness 支持 `expect.plan`（范式文档 §8 #5，未实现）。

## 10. 待裁定（owner）

1. v1 是否先只用本地指数估值，个基分位留 v2（依赖 A′）？
2. 历史均值窗口（30 / 90 / 全期）？
3. 集中度阈值（Top-N 占比 vs HHI）？
4. 意图路由落点：扩 `intent_guard` 还是决策层关键词？

## 11. 证据复核清单

| 证据 | 位置 |
|---|---|
| `get_trading_behavior` 明示「只给客观统计，不做好坏评价」 | `tools.py:442` |
| 9 工具 `TOOLS_METADATA` 无建议类工具 | `tools.py:351-535` |
| 判断顺序③ `ask_clarification` / 单值 `tool_name` | `agent_loop.py:563, 630, 635, 672, 691` |
| 叙事契约禁「超出数据本身发挥」 | `agent_loop.py:690` |
| Wind 估值分位已同步落 `market_multi_items` | `wind_valuation.py:51-114` |
| 指数估值表 `index_valuations` | `db_factory.py:480` |
| 基金估值快照 `fund_valuation_daily` | `models.py:320-354` |
| 资产快照 job `asset_snapshot` | `scheduler.py:14-15` |
| SW 一级行业常量 | `wind_valuation.py:29` |
| eval 静态门禁 45 条契约 | `tests/agent_eval/test_cases.py:29-31` |
