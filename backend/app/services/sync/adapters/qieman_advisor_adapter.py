# -*- coding: utf-8 -*-
"""且慢投顾组合适配器（#1392）：复用且慢 MCP（stargate.yingmi.com）自动抓组合持仓与概览。

前置：QIEMAN_API_KEY 已配置（与温度计同 key）。

- 组合持仓：BatchGetStrategiesComposition，真实返回结构（实测 2026-09）：
    {"<code>": {"<基金类别>": {"持有成分":[{基金代码,基金名称,持仓占比,
    最新净值,调仓时间,...}], "分类占比":...}, ...}}
  解析由 QiemanFetcher.fetch_strategy_composition 完成（已按该结构实现，遍历类别打平）。
- 组合概览：GetStrategyDetails（#1468），提供名称/管理人/风险等级/成立日/区间收益/
  最大回撤/波动率/夏普等，解析由 QiemanFetcher.fetch_strategy_details 完成。
  组合代码命名空间不统一（ZHxxxx / LONG_WIN / J7 / WALLET / SIxxxx），
  故平台归属一律由调用方按 DB 的 platform 判定，不得按代码前缀猜。

本适配器替代原 import_qieman_holdings 手动 JSON 导入。
"""

from app.services.thermometer.fetchers import QiemanFetcher


class QiemanAdvisorAdapter:
    """且慢组合数据源（概览 + 持仓自动抓取）。"""

    def __init__(self) -> None:
        self._fetcher = QiemanFetcher()

    def get_name(self) -> str:
        """数据源标识（与 orchestrator 审计落库口径一致）。"""
        return 'qieman_advisor'

    def get_version(self) -> str:
        return 'v1'

    def fetch_overview(self, strategy_code: str) -> dict:
        """组合概览 / 风险收益指标（归一化 dict）。

        返回 {code, name, summary, desc, estab_date, risk_level, org_name, nav,
        nav_date, return_1w/1m/1y, return_since_incep, max_drawdown, sharpe_ratio,
        volatility, annual_return, url}；无 key / 无效 code → {}。
        """
        rows = self._fetcher.fetch_strategy_details([str(strategy_code)])
        return rows[0] if rows else {}

    def fetch_holdings(self, strategy_code: str) -> list:
        """组合当前基金级持仓（归一化列表）。

        返回 [{code, name, ratio, category, nav, nav_date, adj_time, fund_type}]；
        ratio 为占比 float(%)，adj_time 为调仓时间字符串（"2026-09-10 00:00:00"）。
        无 key / 无效 code → 空列表。
        """
        return self._fetcher.fetch_strategy_composition(str(strategy_code))
