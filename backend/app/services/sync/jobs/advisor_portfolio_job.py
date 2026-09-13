# -*- coding: utf-8 -*-
"""投顾组合数据同步任务（#1167）。

天天基金平台：公开接口自动抓取（概览/当前持仓/行业配置/历史调仓），
targets 为 tgCode 列表；缺省取库内 platform=TIANTIAN 且在售的组合。

且慢平台（#1392 / #1468）：走官方 MCP（QIEMAN_API_KEY，与温度计同 key）自动抓取——
- 概览 / 风险收益指标：GetStrategyDetails（名称、管理人、风险等级、成立日、
  区间收益、最大回撤、波动率、夏普比率）
- 当前持仓：BatchGetStrategiesComposition
组合清单来自 app/domains/funds/advisor_catalog.py（元数据注册表），由
scripts/seed_advisors.py 建档。仍保留 import_qieman_holdings() 手动导入入口
（source='qieman_manual'）作为兜底。

⚠️ 且慢组合代码命名空间不统一（ZHxxxx / LONG_WIN / J7 / WALLET / SIxxxx），
**禁止按代码前缀判定平台归属**，一律以 AdvisorPortfolio.platform 为准。

覆盖式更新语义：
- 当前持仓/行业配置：同一 (portfolio, as_of_date) 先删后插；
- 历史调仓：同一 (portfolio, adjust_date) 先删后插，调仓理由随行冗余。
"""

import datetime as _dt
from typing import Any, List, Optional

from loguru import logger
from sqlalchemy import func

from app.core.constants import ADVISOR_ADJUST_OP_NAME
from app.domains.funds.advisor_catalog import get_qieman_strategy
from app.domains.funds.models import AdvisorAdjustHistory, AdvisorHolding, AdvisorIndustryAlloc, AdvisorPortfolio
from app.services.sync.adapters.qieman_advisor_adapter import QiemanAdvisorAdapter
from app.services.sync.jobs.base import SyncJob

SOURCE_TIANTIAN = 'tiantian'
SOURCE_QIEMAN = 'qieman_manual'  # 手动导入（import_qieman_holdings）
SOURCE_QIEMAN_AUTO = 'qieman'  # 自动抓取（#1392 MCP）


def _parse_date(v: Any) -> Optional[_dt.date]:
    """容忍多种日期形态（'2026-04-01' / '2026-04-01 00:00:00' / date）。"""
    if v is None or v == '':
        return None
    if isinstance(v, _dt.date):
        return v
    s = str(v).strip()[:10]
    try:
        return _dt.datetime.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def flatten_qieman_composition(data: dict, strategy_code: Optional[str] = None) -> List[dict]:
    """把且慢组合持仓 JSON（BatchGetStrategiesComposition 实测结构）摊平。

    输入形如 {策略代码: {基金类型: {持有成分: [{基金代码, 基金名称, 持仓占比,
    最新更新时间, ...}], 分类占比}}}；输出基金级持仓列表（跨分类去重，
    同基金在多个分类出现时保留首个——且慢同一基金只归一个分类）。
    占比字符串 '10.30%' → float 10.30。

    strategy_code 指定时只摊平该组合（文件可能同时含多个组合的实测数据）。
    """
    if not isinstance(data, dict):
        raise ValueError('且慢持仓 JSON 顶层必须是对象 {策略代码: {分类: {...}}}')
    out: List[dict] = []
    seen: set = set()
    as_of = None
    strategies = (data or {}).items()
    if strategy_code:
        strategies = [(strategy_code, (data or {}).get(strategy_code) or {})]
    for _strategy, categories in strategies:
        if not isinstance(categories, dict):
            continue
        for _cat, info in categories.items():
            for f in (info or {}).get('持有成分') or []:
                code = str(f.get('基金代码') or '').strip()
                if not code or code in seen:
                    continue
                seen.add(code)
                ratio = str(f.get('持仓占比') or '').rstrip('%')
                try:
                    ratio_f = float(ratio)
                except ValueError:
                    ratio_f = None
                # 实测：不同组合/版本返回 最新更新时间 / 调仓时间 / 最新净值日期 之一，全部兜底
                d = _parse_date(f.get('最新更新时间') or f.get('调仓时间') or f.get('最新净值日期'))
                if d and (as_of is None or d > as_of):
                    as_of = d
                out.append({'fund_code': code, 'fund_name': f.get('基金名称'), 'after_ratio': ratio_f})
    for item in out:
        item['as_of_date'] = as_of
    return out


class AdvisorPortfolioSyncJob(SyncJob):
    """投顾组合元数据 + 持仓/行业/调仓历史同步（天天基金公开接口 + 且慢 MCP 自动抓取）。"""

    batch_size = 10  # 每批组合数（每个组合 4 个接口请求，batch 过大拉长单事务）

    def __init__(self, adapter, db):
        super().__init__(adapter, db)
        # 且慢持仓自动抓取复用 MCP（与温度计同 key），独立于天天适配器
        self.qieman_adapter = QiemanAdvisorAdapter()

    @property
    def _allow_empty_data(self) -> bool:
        # 库内无待抓组合时静默跳过，不报错阻断整体同步
        return True

    def get_name(self) -> str:
        return 'advisor_portfolio'

    # ── 目标解析 ──

    @staticmethod
    def _infer_platform(code: str) -> str:
        """库内未建档时的平台兜底：且慢元数据注册表命中即 QIEMAN，否则按天天基金。

        不能按代码前缀猜平台——且慢码含 LONG_WIN / LONG_WIN_S / J7 / WALLET / SIxxxx
        等非 ``ZH`` 命名空间，前缀判定会把它们误送进天天适配器。
        """
        return 'QIEMAN' if get_qieman_strategy(code) else 'TIANTIAN'

    def _resolve_targets(self, targets: List[str]) -> List[tuple]:
        """解析本轮待抓组合 → ``[(code, platform), ...]``。

        - 显式 targets：按 code 回查库内 platform；库内未建档的代码再用
          :meth:`_infer_platform`（且慢注册表）兜底。
        - 占位符 '__full__' 或空：回退库内全部在售的天天基金 + 且慢组合。
        """
        real = [t for t in (targets or []) if t != '__full__']
        if real:
            rows = (
                self.db.query(AdvisorPortfolio.code, AdvisorPortfolio.platform)
                .filter(AdvisorPortfolio.code.in_(real))
                .all()
            )
            known = {r.code: (r.platform or 'TIANTIAN') for r in rows}
            return [(c, known.get(c) or self._infer_platform(c)) for c in real]
        rows = (
            self.db.query(AdvisorPortfolio.code, AdvisorPortfolio.platform)
            .filter(AdvisorPortfolio.is_active.is_(True))
            .filter(AdvisorPortfolio.platform.in_(['TIANTIAN', 'QIEMAN']))
            .all()
        )
        return [(r.code, r.platform) for r in rows]

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        pairs = self._resolve_targets(targets)
        if not pairs:
            return []
        payloads = []
        for tg, platform in pairs:
            tg = (tg or '').strip()
            if not tg:
                continue
            if platform == 'QIEMAN':
                # 且慢（#1392/#1468）：概览（GetStrategyDetails）+ 持仓（MCP）
                overview = self.qieman_adapter.fetch_overview(tg)
                holdings = self.qieman_adapter.fetch_holdings(tg)
                funds = [
                    {'fund_code': h['code'], 'fund_name': h.get('name'), 'after_ratio': h.get('ratio')}
                    for h in holdings
                ]
                adj_dates = [h['adj_time'] for h in holdings if h.get('adj_time')]
                as_of = _parse_date(max(adj_dates)) if adj_dates else None
                self.logger.info(
                    f'且慢组合 {tg} 抓取概览 {"有" if overview else "无"} / 持仓 {len(funds)} 条 (as_of={as_of})'
                )
                payloads.append(
                    {
                        'tgcode': tg,
                        'platform': 'QIEMAN',
                        'overview': overview,
                        'holdings': {'funds': funds, 'adjust_date': as_of},
                    }
                )
            else:
                self.logger.info(f'抓取投顾组合 {tg} ...')
                payloads.append(
                    {
                        'tgcode': tg,
                        'platform': 'TIANTIAN',
                        'overview': self.adapter.fetch_overview(tg),
                        'industry': self.adapter.fetch_industry(tg),
                        'holdings': self.adapter.fetch_current_holdings(tg),
                        'history': self.adapter.fetch_adjust_history(tg),
                    }
                )
        return payloads

    # ── 校验 / 去重 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for p in raw_data:
            tg = (p.get('tgcode') or '').strip()
            if not tg:
                continue
            # 四个数据面全空的组合视为无效（接口可能已下架），本轮跳过
            has_any = bool(
                p.get('overview') or p.get('industry') or (p.get('holdings') or {}).get('funds') or p.get('history')
            )
            if not has_any:
                self.logger.warning(f'投顾组合 {tg} 四类数据均空，跳过（可能已下架或接口变更）')
                continue
            p['tgcode'] = tg
            out.append(p)
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 覆盖式更新，不做去重剔除
        return data

    # ── 落库 ──

    def _get_or_create_portfolio(self, tgcode: str, platform: str = 'TIANTIAN') -> AdvisorPortfolio:
        row = self.db.query(AdvisorPortfolio).filter_by(platform=platform, code=tgcode).first()
        if row is None:
            row = AdvisorPortfolio(platform=platform, code=tgcode, name=tgcode)
            self.db.add(row)
            self.db.flush()
        return row

    def _apply_holdings(self, portfolio: AdvisorPortfolio, funds: List[dict], as_of, source: str) -> int:
        if not as_of or not funds:
            return 0
        # 同快照日整体覆盖
        self.db.query(AdvisorHolding).filter_by(portfolio_id=portfolio.id, as_of_date=as_of).delete()
        rows = [
            {
                'portfolio_id': portfolio.id,
                'as_of_date': as_of,
                'fund_code': f['fund_code'],
                'fund_name': f.get('fund_name'),
                'pre_ratio': f.get('pre_ratio'),
                'after_ratio': f.get('after_ratio'),
                'op_code': f.get('op_code'),
                'op_name': f.get('op_name'),
                'source': source,
            }
            for f in funds
        ]
        self.db.bulk_insert_mappings(AdvisorHolding, rows)
        return len(rows)

    #: 且慢概览（GetStrategyDetails 归一化键）中可直接落 AdvisorPortfolio 的数值列
    _QIEMAN_OVERVIEW_NUM_COLS = (
        'annual_return',
        'max_drawdown',
        'volatility',
        'sharpe_ratio',
        'nav',
        'return_1d',
        'return_1w',
        'return_1m',
        'return_1q',
        'return_6m',
        'return_1y',
        'return_since_incep',
    )

    def _apply_qieman_overview(self, portfolio: AdvisorPortfolio, ov: dict) -> None:
        """把且慢概览（GetStrategyDetails）写入组合档案（#1468）。

        只覆盖官方权威字段（名称 / 管理人 / 风险等级 / 成立日 / 简介 / 策略说明 /
        净值与净值日 / 组合链接 / 各类收益指标），**一次抓取全部落库**，
        避免日后为拿单个字段再手动抓。

        ``host`` / ``allocation`` / ``product_type`` 属**策展字段**（来源
        app/domains/funds/advisor_catalog.py 注册表），此处不动，避免被接口空值冲掉。
        """
        if not ov:
            return
        if ov.get('name'):
            portfolio.name = ov['name'][:100]
        if ov.get('org_name'):
            portfolio.org_name = ov['org_name'][:100]
        if ov.get('risk_level'):
            portfolio.risk_level = ov['risk_level'][:20]
        if ov.get('summary'):
            portfolio.strategy_summary = ov['summary'][:300]
        if ov.get('url'):
            portfolio.source_url = ov['url'][:120]
        estab = _parse_date(ov.get('estab_date'))
        if estab:
            portfolio.estab_date = estab
        nav_date = _parse_date(ov.get('nav_date'))
        if nav_date:
            portfolio.nav_date = nav_date
        desc = ov.get('desc') or ov.get('summary')
        if desc:
            portfolio.strategy_desc = desc[:500]
        for col in self._QIEMAN_OVERVIEW_NUM_COLS:
            if ov.get(col) is not None:
                setattr(portfolio, col, ov[col])

    def _derive_qieman_adjust(self, portfolio: AdvisorPortfolio, as_of) -> int:
        """由「本次快照 vs 上一快照」推导且慢调仓明细，落 advisor_adjust_histories（#1468）。

        且慢 MCP **没有**历史调仓接口（只有当前持仓，以及每只基金自带的调仓时间），
        因此调仓历史由我们自己的快照序列推导：同一组合按 ``as_of_date`` 逐次快照，
        相邻两次占比之差即本次调仓的「调仓前 / 调仓后占比」与方向（加仓 / 减仓 / 新增）。

        - 首次快照没有前值可对比，**跳过**（不编造 0 → X 的假建仓记录）；
        - ``reason`` 记录推导来源（前一次快照日），便于回溯；
        - 天天基金有官方 adjustHistory，不走此路径。

        返回写入行数。
        """
        if not as_of:
            return 0
        prev_date = (
            self.db.query(func.max(AdvisorHolding.as_of_date))
            .filter(AdvisorHolding.portfolio_id == portfolio.id, AdvisorHolding.as_of_date < as_of)
            .scalar()
        )
        if prev_date is None:
            return 0

        def _snapshot(day) -> dict:
            return {
                r.fund_code: (float(r.after_ratio) if r.after_ratio is not None else None, r.fund_name)
                for r in self.db.query(AdvisorHolding).filter_by(portfolio_id=portfolio.id, as_of_date=day).all()
            }

        prev, cur = _snapshot(prev_date), _snapshot(as_of)
        rows = []
        for code in sorted(set(prev) | set(cur)):
            b, b_name = prev.get(code, (None, None))
            a, a_name = cur.get(code, (None, None))
            if b is None and a is None:
                continue
            if b is None:
                op = 4  # 新增
            elif a is None:
                op = 3  # 减仓（清仓至 0）
            elif a > b:
                op = 2  # 加仓
            elif a < b:
                op = 3  # 减仓
            else:
                op = 5  # 持平
            rows.append(
                {
                    'portfolio_id': portfolio.id,
                    'adjust_date': as_of,
                    'reason': f'由 {prev_date} 持仓快照推导'[:300],
                    'fund_code': code,
                    'fund_name': a_name or b_name,
                    'pre_ratio': b if b is not None else 0.0,
                    'after_ratio': a if a is not None else 0.0,
                    'op_code': op,
                    'op_name': ADVISOR_ADJUST_OP_NAME.get(op),
                    'source': SOURCE_QIEMAN_AUTO,
                }
            )
        if not rows:
            return 0
        # 同调仓日整体覆盖（与天天历史调仓同语义）
        self.db.query(AdvisorAdjustHistory).filter_by(portfolio_id=portfolio.id, adjust_date=as_of).delete()
        self.db.bulk_insert_mappings(AdvisorAdjustHistory, rows)
        return len(rows)

    def _save_data(self, new_data: List[dict]) -> None:
        for p in new_data:
            platform = p.get('platform', 'TIANTIAN')
            portfolio = self._get_or_create_portfolio(p['tgcode'], platform)
            ov = p.get('overview') or {}

            if platform == 'TIANTIAN':
                # 天天：概览 + 区间收益（SYL_* 实测映射，见 tiantian_advisor_adapter）
                if ov.get('name'):
                    portfolio.name = ov['name']
                if ov.get('risk_level'):
                    portfolio.risk_level = ov['risk_level']
                if ov.get('strategy_desc'):
                    portfolio.strategy_desc = ov['strategy_desc'][:500]
                estab = _parse_date(ov.get('estab_date'))
                if estab:
                    portfolio.estab_date = estab
                returns = ov.get('returns') or {}
                for col in ('return_1w', 'return_1m', 'return_1y', 'return_ytd', 'return_since_incep'):
                    if returns.get(col) is not None:
                        setattr(portfolio, col, returns[col])
            elif platform == 'QIEMAN':
                # 且慢：概览 / 风险收益指标（GetStrategyDetails，#1468）
                self._apply_qieman_overview(portfolio, ov)

            # 持仓：两平台通用，source 区分
            holdings = p.get('holdings') or {}
            as_of = _parse_date(holdings.get('adjust_date'))
            source = SOURCE_QIEMAN_AUTO if platform == 'QIEMAN' else SOURCE_TIANTIAN
            n_hold = self._apply_holdings(portfolio, holdings.get('funds') or [], as_of, source)

            if platform == 'TIANTIAN':
                # 行业配置：快照日随当前持仓日（接口不单独给日期）
                industry = p.get('industry') or []
                if industry and as_of:
                    self.db.query(AdvisorIndustryAlloc).filter_by(portfolio_id=portfolio.id, as_of_date=as_of).delete()
                    self.db.bulk_insert_mappings(
                        AdvisorIndustryAlloc,
                        [
                            {
                                'portfolio_id': portfolio.id,
                                'as_of_date': as_of,
                                'industry_name': r['industry_name'],
                                'ratio': r.get('ratio'),
                                'source': SOURCE_TIANTIAN,
                            }
                            for r in industry
                        ],
                    )
                # 历史调仓：逐调仓日覆盖
                n_hist = 0
                for node in p.get('history') or []:
                    hd = _parse_date(node.get('adjust_date'))
                    if not hd or not node.get('funds'):
                        continue
                    self.db.query(AdvisorAdjustHistory).filter_by(portfolio_id=portfolio.id, adjust_date=hd).delete()
                    self.db.bulk_insert_mappings(
                        AdvisorAdjustHistory,
                        [
                            {
                                'portfolio_id': portfolio.id,
                                'adjust_date': hd,
                                'reason': (node.get('reason') or '')[:300],
                                'fund_code': f['fund_code'],
                                'fund_name': f.get('fund_name'),
                                'pre_ratio': f.get('pre_ratio'),
                                'after_ratio': f.get('after_ratio'),
                                'op_code': f.get('op_code'),
                                'op_name': f.get('op_name'),
                                'source': SOURCE_TIANTIAN,
                            }
                            for f in node['funds']
                        ],
                    )
                    n_hist += len(node['funds'])
                self.db.commit()
                self.logger.info(
                    f'投顾组合 {p["tgcode"]} 落库: 持仓 {n_hold} 条(as_of={as_of}), 行业 {len(industry)} 条, 历史 {n_hist} 条'
                )
            else:
                # 且慢（#1392/#1468）：概览 + 持仓自动抓取；调仓明细由快照序列推导。
                # host/allocation/product_type 等策展字段由 advisor_catalog 注册表 seed 维护。
                n_adj = self._derive_qieman_adjust(portfolio, as_of) if n_hold else 0
                self.db.commit()
                self.logger.info(
                    f'且慢组合 {p["tgcode"]} 落库: 概览 {len(ov)} 字段, 持仓 {n_hold} 条 (as_of={as_of}), '
                    f'推导调仓 {n_adj} 条'
                )


def import_qieman_holdings(db, data: dict, portfolio_code: str) -> int:
    """且慢组合持仓手动导入（无免费公开接口，source=qieman_manual）。

    data 为 BatchGetStrategiesComposition 原始 JSON；组合须已存在
    （platform=QIEMAN, code=portfolio_code），持仓按最新更新时间整体覆盖。
    返回写入行数。
    """
    portfolio = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code=portfolio_code).first()
    if portfolio is None:
        raise ValueError(f'且慢组合 {portfolio_code} 不存在，请先在 advisor_portfolios 建档')
    funds = flatten_qieman_composition(data, strategy_code=portfolio_code)
    if not funds:
        logger.warning(f'且慢组合 {portfolio_code} 数据为空，跳过导入')
        return 0
    as_of = funds[0].get('as_of_date')
    if as_of is None:
        logger.warning(f'且慢组合 {portfolio_code} 无有效更新时间，跳过导入')
        return 0
    db.query(AdvisorHolding).filter_by(portfolio_id=portfolio.id, as_of_date=as_of, source=SOURCE_QIEMAN).delete()
    db.bulk_insert_mappings(
        AdvisorHolding,
        [
            {
                'portfolio_id': portfolio.id,
                'as_of_date': as_of,
                'fund_code': f['fund_code'],
                'fund_name': f.get('fund_name'),
                'after_ratio': f.get('after_ratio'),
                'source': SOURCE_QIEMAN,
            }
            for f in funds
        ],
    )
    db.commit()
    logger.info(f'且慢组合 {portfolio_code} 导入 {len(funds)} 条持仓 (as_of={as_of})')
    return len(funds)
