# -*- coding: utf-8 -*-
# Author : imoyao
"""analytics —— 高级洞察 Pro 的账户级分析引擎包（#994 / 里程碑 #19）。

## 为什么要有这个包

Pro 面板四模块（#994）的指标分两类：

- **基金级**（阶段收益/波动率/VaR/蒙特卡洛/相关性/穿透/PDF）：过渡期由盈米 MCP
  代理提供（#1986 检查单），自研触发条件满足后逐个迁入本包；
- **账户级**（权益分拆 XIRR / 交易行为画像 / 持有期回撤）：只用用户自己的 L1
  持仓与流水计算，盈米结构上无法提供——**永不退役的差异化锚点**（#1986
  「结构性例外」条目）。

本包是**新增分析模块**的落点：账户级指标（XIRR 除外，它在 `services/performance/`）
与触发条件满足后自建的基金级替代模块（#1986 检查单）都进这里；既有基金级实现
（fund_risk_metrics 等）保持原址，不搬家。

## 模块现状映射（2026-10-17 盘点，改动后请同步更新）

| 设计模块 | 现状 | 位置 |
|---|---|---|
| drawdown（回撤族） | ✅ 已实现（基金级，RiskMetricsResult 全家桶） | `services/fund_risk_metrics.py` |
| volatility（年化波动） | ✅ 已实现（同上 + `fund_performance._annualized_volatility`） | 同上 |
| sharpe / sortino / calmar / UI / UPI | ✅ 已实现（#167 风险指标块） | 同上 |
| penetration（持仓穿透） | ✅ 已实现（#870 Step 2） | `services/penetration.py` |
| XIRR（账户级权益分拆） | ✅ 已实现（position/symbol/portfolio 三 scope） | `services/performance/` |
| **behavior（交易行为画像）** | ✅ **本包**（账户级核心第一块） | `analytics/behavior.py` |
| **cleared_cycles（清仓周期统计）** | ✅ **本包**（#2131 账本对齐 A'，周期级汇总） | `analytics/cleared_cycles.py` |
| **benchmark_excess（基准超额收益）** | ✅ **本包**（#2134 账本对齐 D，账户/组合 vs 宽基指数） | `analytics/benchmark_excess.py` |
| **var（风险价值 VaR 95%）** | ✅ **本包**（#994 模块二，基金级：吃净值/价格序列，自建不走盈米） | `analytics/var.py` |
| correlation（相关性矩阵） | ❌ 未建——Phase 3 实质实现时落这里，**不放占位桩** | （待建） |

## 纪律

1. 账户级指标**只吃 L1 流水/持仓**，不引入外部数据源（这正是它与基金级指标的边界）；
2. 样本不足一律 `None` + 前端「—」，不缩窗口凑数、不编造（全仓「诚实降级」纪律）；
3. 口径说明随值下发（`caveats`），用户换个参数要能对上账（#167 拍板项同款）。
"""
