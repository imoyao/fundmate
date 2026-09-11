# -*- coding: utf-8 -*-
"""且慢投顾组合适配器（#1392）：复用且慢 MCP（stargate.yingmi.com）自动抓组合持仓。

前置：QIEMAN_API_KEY 已配置（与温度计同 key）。组合持仓通过
BatchGetStrategiesComposition 获取，真实返回结构（实测 2026-09）：
    {"<code>": {"<基金类别>": {"持有成分":[{基金代码,基金名称,持仓占比,
    最新净值,调仓时间,...}], "分类占比":...}, ...}}
解析由 QiemanFetcher.fetch_strategy_composition 完成（已按该结构实现，遍历类别打平）。

组合概览（名称/策略/收益）不在该接口，由 advisor_portfolios 建档（seed）或 job 配置提供；
本适配器只负责持仓自动抓取，替代原 import_qieman_holdings 手动 JSON 导入。
"""

from app.services.thermometer.fetchers import QiemanFetcher


class QiemanAdvisorAdapter:
    """且慢组合数据源（持仓自动抓取）。"""

    def __init__(self) -> None:
        self._fetcher = QiemanFetcher()

    def fetch_holdings(self, strategy_code: str) -> list:
        """组合当前基金级持仓（归一化列表）。

        返回 [{code, name, ratio, category, nav, nav_date, adj_time, fund_type}]；
        ratio 为占比 float(%)，adj_time 为调仓时间字符串（"2026-09-10 00:00:00"）。
        无 key / 无效 code → 空列表。
        """
        return self._fetcher.fetch_strategy_composition(str(strategy_code))
