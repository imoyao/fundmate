# -*- coding: utf-8 -*-
"""且慢投顾组合适配器（#1392）：复用且慢 MCP（stargate.yingmi.com）自动抓组合持仓与概览。

实现 :class:`~app.services.adapters.advisor_source.AdvisorPortfolioSource`：
把 MCP 归一化结果翻译成 canonical（差异只在少量别名），平台细节（工具名 / 中文键 / 百分号串）
全部留在 ``thermometer/fetchers.QiemanFetcher`` 与本文件内。

前置：QIEMAN_API_KEY 已配置（与温度计同 key）。

- 组合持仓：BatchGetStrategiesComposition，真实返回结构（实测 2026-09）：
    {"<code>": {"<基金类别>": {"持有成分":[{基金代码,基金名称,持仓占比,
    最新净值,调仓时间,...}], "分类占比":...}, ...}}
  解析由 QiemanFetcher.fetch_strategy_composition 完成（已按该结构实现，遍历类别打平）。
- 组合概览：GetStrategyDetails（#1468），提供名称/管理人/风险等级/成立日/区间收益/
  最大回撤/波动率/夏普等，解析由 QiemanFetcher.fetch_strategy_details 完成。
  组合代码命名空间不统一（ZHxxxx / LONG_WIN / J7 / WALLET / SIxxxx），
  故平台归属一律由调用方按 DB 的 platform 判定，不得按代码前缀猜。
- **无行业配置、无历史调仓接口**：前者返回空，后者由落库层用持仓快照序列推导
  （见 ``derive_rebalances_from_snapshots``）。

本适配器替代原 import_qieman_holdings 手动 JSON 导入。
"""

from app.services.adapters.advisor_source import (
    CANONICAL_OVERVIEW_COLUMNS,
    EXTRA_KEY,
    AdvisorPortfolioSource,
    register_advisor_source,
)
from app.services.adapters.qieman_fetcher import QiemanFetcher


@register_advisor_source
class QiemanAdvisorAdapter(AdvisorPortfolioSource):
    """且慢组合数据源（概览 + 持仓自动抓取）。"""

    platform = 'QIEMAN'
    #: 且慢 MCP 没有历史调仓工具，调仓明细只能由我们的持仓快照序列推导
    has_official_rebalances = False
    derive_rebalances_from_snapshots = True

    #: QiemanFetcher 归一化键 → canonical 键（仅别名不同，其余同名直接透传）
    _OVERVIEW_ALIASES = {
        'summary': 'strategy_summary',
        'desc': 'strategy_desc',
        'url': 'source_url',
    }

    def __init__(self) -> None:
        self._fetcher = QiemanFetcher()

    def get_name(self) -> str:
        """数据源标识（与 orchestrator 审计落库口径一致）。"""
        return 'qieman_advisor'

    def get_version(self) -> str:
        return 'v1'

    def fetch_overview(self, strategy_code: str) -> dict:
        """组合概览 / 风险收益指标（canonical 字典）。

        键见 ``CANONICAL_OVERVIEW_COLUMNS``；canonical 未覆盖的原始字段
        （管理人简介 / 头像 / 实名认证等）进 ``extra``，不做丢弃。
        无 key / 无效 code → ``{}``（落库层不会因此清空已有数据）。
        """
        code = str(strategy_code).strip()
        return self.fetch_overviews([code]).get(code) or {}

    def fetch_overviews(self, strategy_codes: list) -> dict:
        """批量概览（且慢优化）：一次 ``GetStrategyDetails`` 拿多只，按 code 切分。

        底层 ``fetch_strategy_details`` 已按 ``QIEMAN_STRATEGY_BATCH_SIZE``（50）分批，
        故 111 只组合 = 3 次工具调用（原实现逐只调 = 111 次）。
        只返回拿到的 code（缺失即缺席），语义与 ``fetch_overview`` 的 ``{}`` 一致。
        """
        codes = [str(c).strip() for c in (strategy_codes or []) if str(c).strip()]
        if not codes:
            return {}
        rows = self._fetcher.fetch_strategy_details(codes)
        by_code = {str(r.get('code')): r for r in rows if isinstance(r, dict) and str(r.get('code') or '').strip()}
        return {c: self._to_canonical_overview(by_code[c]) for c in codes if c in by_code}

    def _to_canonical_overview(self, raw: dict) -> dict:
        """单条 fetcher 概览 → canonical（含 extra / desc 回退）。"""
        ov = {self._OVERVIEW_ALIASES.get(k, k): v for k, v in raw.items() if k != 'code'}
        # 策略描述缺失时回退策略简介：详情抽屉需要一段可读描述（既有行为，勿丢）
        if not ov.get('strategy_desc') and ov.get('strategy_summary'):
            ov['strategy_desc'] = ov['strategy_summary']
        mapped = set(self._OVERVIEW_ALIASES) | set(CANONICAL_OVERVIEW_COLUMNS)
        ov[EXTRA_KEY] = {k: v for k, v in raw.items() if k not in mapped and k != 'code' and v is not None}
        return ov

    def fetch_holdings(self, strategy_code: str) -> dict:
        """组合当前基金级持仓快照（canonical）。

        返回 ``{'as_of_date': 'YYYY-MM-DD HH:MM:SS'|None, 'funds': [...]}``；
        且慢同一组合多个类别可能给出不同调仓时间，取**最晚**者作为快照日
        （日期解析交给落库层）。且慢无调仓前占比，``pre_ratio`` / 操作类型留空。
        无 key / 无效 code → ``{'as_of_date': None, 'funds': []}``。
        """
        code = str(strategy_code).strip()
        return self.fetch_holdings_batch([code]).get(code) or {'as_of_date': None, 'funds': []}

    def fetch_holdings_batch(self, strategy_codes: list) -> dict:
        """批量持仓（且慢优化）：一次 ``BatchGetStrategiesComposition`` 传多只。

        降级逐只的判据在 fetcher 内（批量响应缺某 code 的键 ⇒ 该 code 单只重取），
        因此这里拿到的每只都是「有值或确认为空」，不会把批量失败写成空快照。
        """
        codes = [str(c).strip() for c in (strategy_codes or []) if str(c).strip()]
        if not codes:
            return {}
        rows_by_code = self._fetcher.fetch_strategy_composition_batch(codes)
        return {c: self._to_canonical_holdings(rows_by_code.get(c) or []) for c in codes}

    @staticmethod
    def _to_canonical_holdings(rows: list) -> dict:
        """单只归一化持仓列表 → canonical 快照字典。"""
        funds = []
        adj_times = []
        for h in rows or []:
            code = str(h.get('code') or '').strip()
            if not code:
                continue
            funds.append(
                {
                    'fund_code': code,
                    'fund_name': h.get('name'),
                    'pre_ratio': None,
                    'after_ratio': h.get('ratio'),
                    'op_code': None,
                    'op_name': None,
                }
            )
            if h.get('adj_time'):
                adj_times.append(str(h['adj_time']))
        return {'as_of_date': max(adj_times) if adj_times else None, 'funds': funds}

    def fetch_industries(self, strategy_code: str) -> list:
        """且慢 MCP 无行业配置工具 → 恒为空（契约要求返回空集合而非报错）。"""
        return []

    def fetch_rebalances(self, strategy_code: str) -> list:
        """且慢 MCP 无历史调仓工具 → 恒为空。

        调仓明细由落库层按 ``derive_rebalances_from_snapshots`` 用持仓快照推导，
        推导算法统一放在 job 侧（适配器拿不到历史快照，无法自给）。
        """
        return []
