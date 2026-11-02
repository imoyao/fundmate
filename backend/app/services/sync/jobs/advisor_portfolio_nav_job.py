# -*- coding: utf-8 -*-
"""投顾组合净值序列同步任务（投顾详情页走势图底数）。

## 为什么单独成一个 job，而不并进 ``AdvisorPortfolioSyncJob``

那个 job 同步的是「组合现在持有什么、调过什么」——四个数据面都围绕**当日快照**，
每晚 22:00 跑一次、覆盖式写入。净值序列是**十年历史**（ZH012926 实测 2250 行），
写入量与失败面完全不同：一个组合一次调用就能拉回全量，但 100 个组合就是 100 次
外部调用。混进同一个 job 的结果是「组合概览更新得好好的，却因为某只组合的净值
序列超时整轮重试」。分开后各自的失败互不牵连，调度时间也能错开。

## 目标池：只抓用户触达的组合（**不做全库刷**）

``docs/spec/data-strategy.md`` 的数据准入第 3 问要求「抓取目标池必须显式」，
且明令禁止 ``targets if targets else 全库`` 这类静默退化。投顾组合的目标池
与基金/股票不同，``orchestrator.resolve_targets()`` 只产 fund/stock 两类，
故这里自己解析：:func:`app.services.advisor_nav.tracked_codes`（自选 ∪ 持仓，
清仓行也算——用户回看清仓标的的详情页同样需要走势）。

用户一个组合都没关注时目标池为空，这是**合法状态**（`_allow_empty_data=True`），
不是故障；库内其余组合在首次被查看时由 ``advisor_nav.ensure_series`` 按需补拉。

## 显式 targets

``pdm run sync --job advisor_portfolio_nav --targets ZH012926`` 时按给定 code 抓，
用于补数据 / 排查单只。``--full-sync`` 无特殊语义（本 job 每次拉的都是全历史，
即天然全量），故不登记进 ``SYMBOL_BACKFILL_JOBS``——那条规则防的是「逐标的回填
触发上游封禁」，本 job 的目标池本来就受用户触达范围约束。
"""

from typing import Any, Dict, List, Optional

from app.domains.funds.models import AdvisorPortfolio
from app.services import advisor_nav
from app.services.adapters.advisor_source import (
    AdvisorPortfolioSource,
    AdvisorSourceRegistry,
    UnknownAdvisorPlatform,
)
from app.services.job_base import SyncJob
from app.services.mcp.errors import McpError, McpTokenMissing


class AdvisorPortfolioNavSyncJob(SyncJob):
    """投顾组合净值序列同步（且慢 MCP ``GetPortfolioNavHistory``）。"""

    #: 每批组合数。每只组合一次 MCP 调用、返回可达 3000+ 行，10 只是「单事务不过大」与
    #: 「失败重试面不过宽」之间的折中。
    batch_size = 10

    def __init__(
        self,
        adapter: Optional[AdvisorSourceRegistry] = None,
        db=None,
        sources: Optional[Dict[str, AdvisorPortfolioSource]] = None,
    ):
        # 审计（sync_logs.data_source）需要 get_name/get_version，与 advisor_portfolio 同款
        super().__init__(adapter or AdvisorSourceRegistry(sources), db)

    def get_name(self) -> str:
        return 'advisor_portfolio_nav'

    @property
    def _allow_empty_data(self) -> bool:
        # 用户没有关注任何投顾组合时目标池为空：跳过即可，不阻断整轮同步
        return True

    # ── 目标解析 ──

    def _resolve_portfolios(self, targets: List[str]) -> List[AdvisorPortfolio]:
        """本轮待抓组合实体。

        - 显式 targets：按 code 回查库内组合（``__full__`` 占位符忽略）；
        - 否则：用户触达范围（自选 ∪ 持仓），见 :func:`advisor_nav.tracked_portfolios`。
        """
        codes = [advisor_nav.normalize_code(t) for t in (targets or []) if t and t != '__full__']
        codes = [c for c in codes if c]
        if not codes:
            return advisor_nav.tracked_portfolios(self.db)
        rows = self.db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code.in_(codes)).all()
        by_code = {r.code: r for r in rows}
        missing = [c for c in codes if c not in by_code]
        for code in missing:
            # 库内未建档 ⇒ 拿不到 platform，无法选适配器。这是「我们还不认识它」，
            # 不是「它没有数据」，必须留痕而不是静默跳过。
            self.logger.warning(f'跳过投顾组合 {code}：advisor_portfolios 未建档，无法确定平台')
            self.stats['errors'].append(f'{code} 未建档')
        return [by_code[c] for c in codes if c in by_code]

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """逐只取净值序列，失败按组合隔离。

        与 ``AdvisorPortfolioSyncJob`` 的差别：那边按平台**批量**（概览 / 持仓接口都收
        多个 code），而 ``GetPortfolioNavHistory`` 的入参只有单个 ``poCode``，没有批量
        语义（也不该为了省请求去拼——上游没承诺，猜错就是整批空序列）。

        失败语义：
        - ``McpTokenMissing``：**未配置 Token = 该平台功能关闭**，不记 ``errors``
          （不制造假红灯），只记 ``degraded``（「本轮没更新」要可见）；
        - 其它 ``McpError``：记 ``errors``（人话）+ ``degraded``，该组合本轮跳过；
        - ``UnknownAdvisorPlatform``：库内存在尚无适配器的平台，跳过该组合即可。
        """
        portfolios = self._resolve_portfolios(targets)
        if not portfolios:
            return []

        # 同一平台只记一次 degraded 原因，避免 100 只组合刷 100 行同样的话
        degraded_reasons: List[str] = self.stats.setdefault('degraded_reasons', [])
        payloads: List[dict] = []

        for portfolio in portfolios:
            code = portfolio.code
            try:
                source = self.adapter.get(portfolio.platform)
            except UnknownAdvisorPlatform as exc:
                self.logger.warning(f'跳过投顾组合 {code}：{exc}')
                continue

            try:
                rows = source.fetch_nav_history(code) or []
            except McpTokenMissing as exc:
                self.logger.warning(f'投顾组合 {code} 跳过：{exc.user_message}')
                self._mark_degraded(exc.user_message, degraded_reasons)
                continue
            except McpError as exc:
                self.logger.error(f'投顾组合 {code} 净值序列取数失败：{exc}')
                self.stats['errors'].append(f'{code} 取数失败：{exc.user_message}')
                self._mark_degraded(exc.user_message, degraded_reasons)
                continue

            self.logger.info(f'抓取投顾组合 {code}({portfolio.platform}) 净值序列 {len(rows)} 条')
            payloads.append(
                {
                    'portfolio_id': portfolio.id,
                    'code': code,
                    'source': advisor_nav.source_of(portfolio),
                    'rows': rows,
                }
            )
        return payloads

    def _mark_degraded(self, reason: str, reasons: List[str]) -> None:
        """记「本轮有组合没更新」——``degraded`` 与 ``errors`` 语义不同（同 advisor_portfolio）。"""
        self.stats['degraded'] = int(self.stats.get('degraded') or 0) + 1
        if reason not in reasons:
            reasons.append(reason)

    # ── 校验 / 去重 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """丢掉没有序列的组合，但把它们的代码记进 ``stats['empty_series']``。

        **空序列不是错误**：且慢实测 ``LONG_WIN`` / ``LONG_WIN_S`` / ``J7`` / ``WALLET`` /
        ``SI000186`` 是计划型 / 钱包类，上游本来就返回 ``[]``。这类组合不进 ``errors``
        （否则每轮都红，真故障被淹没——#171 同族）。

        但它们也**不会**落进基类的 ``skipped``：``skipped`` 数的是「通过校验、被去重剔除」
        的条目，而这些在 ``_validate_data`` 这一层就被剔了。若只丢掉不记账，同步审计行
        就是 ``total=1 / success=0 / skipped=0 / errors=[]``——日志里看不出「上游给了空」。
        故这里显式记一份 ``empty_series``（``sync_logs.stats`` 存的是 stats 的字符串形态，
        排查时直接可见）。
        """
        valid = [p for p in raw_data if p.get('rows')]
        empty = [p.get('code') for p in raw_data if not p.get('rows')]
        if empty:
            self.stats['empty_series'] = empty
            self.logger.info(f'以下投顾组合上游未提供净值序列（计划型 / 钱包型，非故障）：{empty}')
        return valid

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """按组合去重（同一组合出现在多批时取最后一份）。"""
        seen: Dict[Any, dict] = {}
        for item in data:
            seen[item.get('portfolio_id')] = item
        return [v for v in seen.values() if v.get('portfolio_id') is not None]

    # ── 落库 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """按唯一键 (portfolio_id, nav_date) 幂等写入，见 :func:`advisor_nav.save_nav_rows`。"""
        total = 0
        for item in new_data:
            written = advisor_nav.save_nav_rows(
                self.db, item['portfolio_id'], item.get('rows') or [], item.get('source') or 'unknown'
            )
            total += written
            self.logger.info(f'投顾组合 {item.get("code")} 写入净值 {written} 行')
        self.logger.info(f'投顾组合净值序列本轮合计写入 {total} 行')
