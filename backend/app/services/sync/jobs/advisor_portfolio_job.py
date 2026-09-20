# -*- coding: utf-8 -*-
"""投顾组合数据同步任务（#1167 / #1392）。

**平台无关**：本任务不认识任何具体平台，只按 ``AdvisorPortfolio.platform``
从 :class:`AdvisorSourceRegistry` 取对应适配器（Port 契约见
``app/services/adapters/advisor_source.py``）。新增平台 = 加一个适配器，**不改本文件**。

平台能力差异与落库语义的分工：

| 谁 | 负责 |
|---|---|
| 适配器 | 把平台原始响应翻译成 canonical（概览 / 持仓 / 行业 / 官方调仓） |
| 本任务 | 平台无关的落库语义：覆盖式快照、策展字段不被覆盖、快照推导调仓 |

落库语义（与平台无关，新平台自动继承）：
- 概览指标：只覆盖**非 None** 值（接口缺字段 / 抓取失败不清空已有数据）；
  `host`/`allocation`/`product_type` 是策展字段（`advisor_catalog` 注册表维护），永不被抓取覆盖；
- 当前持仓/行业配置：同一 (portfolio, as_of_date) 先删后插；
- 历史调仓：同一 (portfolio, adjust_date) 先删后插，调仓理由随行冗余；
- 无官方调仓接口的平台（如且慢）：由持仓快照序列推导调仓明细，且**只记真实变化**——
  仅 `|Δratio| > ADVISOR_ADJUST_MIN_DELTA_PCT` 的基金入账，**过滤后为空就不写任何行**。
  （#1622 的教训：且慢的占比是**市值口径**、每天随净值自然漂移，原实现对所有基金逐行落库
  ——没变的写 `op=5 持平`——且无阈值，于是每个交易日都生成一整组"调仓"，真实调仓被淹没。）

⚠️ 且慢组合代码命名空间不统一（ZHxxxx / LONG_WIN / J7 / WALLET / SIxxxx），
**禁止按代码前缀判定平台归属**，一律以 AdvisorPortfolio.platform 为准。

仍保留 import_qieman_holdings() 手动导入入口（source='qieman_manual'）作为兜底。
"""

import datetime as _dt
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy import func

from app.core.constants import ADVISOR_ADJUST_OP_NAME
from app.domains.funds.advisor_catalog import get_qieman_strategy
from app.domains.funds.models import AdvisorAdjustHistory, AdvisorHolding, AdvisorIndustryAlloc, AdvisorPortfolio
from app.services.adapters.advisor_source import (
    CANONICAL_OVERVIEW_COLUMNS,
    CURATED_OVERVIEW_KEYS,
    DEFAULT_ADVISOR_PLATFORM,
    EXTRA_KEY,
    OVERVIEW_DATE_KEYS,
    AdvisorPortfolioSource,
    AdvisorSourceRegistry,
    UnknownAdvisorPlatform,
)
from app.services.job_base import SyncJob

#: 数据来源标识（落 advisor_holdings / advisor_adjust_histories / advisor_industry_allocs 的 source 列）。
#: 自动抓取统一取 ``platform.lower()``——tiantian / qieman，与 #1167/#1468 起已落库的数据同口径；
#: 手动导入另用 :data:`SOURCE_QIEMAN_MANUAL` 与自动抓取的 ``qieman`` 区分，便于回溯数据来历。
SOURCE_QIEMAN_MANUAL = 'qieman_manual'

#: 判定「真调仓」的最小占比变化（百分点，市值口径）。低于此值视为净值漂移，**有意不记录**。
#:
#: 标定依据（#1622，开发库 102 个且慢组合 / 301 组相邻快照 / 4880 个基金级差异）：
#: 漂移 |Δratio| 的 p50 = 0.01pp、p90 = 0.05pp、p99 = 0.23pp（最大 6.71pp 已是真实调仓）；
#: 真实调仓单只基金的变化通常 ≥ 1pp，且快照对的 Σ|Δ| 呈**双峰**（漂移日 1~2pp vs 真调仓日 16~60pp）。
#: 取 0.5pp ≈ 2×p99：既能滤掉漂移噪声，又不丢真实调仓。
ADVISOR_ADJUST_MIN_DELTA_PCT = 0.5


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
    """投顾组合概览 + 持仓/行业/调仓历史同步（多平台，Ports & Adapters）。"""

    batch_size = 10  # 每批组合数（每个组合 4 个接口请求，batch 过大拉长单事务）

    def __init__(
        self,
        adapter: Optional[AdvisorSourceRegistry] = None,
        db=None,
        sources: Optional[Dict[str, AdvisorPortfolioSource]] = None,
    ):
        """``adapter`` 必须是 :class:`AdvisorSourceRegistry`（审计需要 get_name/get_version）。

        ``sources`` 为显式注入的 ``{platform: 适配器实例}``（测试 / 特殊场景）；
        未注入的平台按注册表懒构造，故**新增平台无需改本任务**。
        """
        if adapter is None:
            adapter = AdvisorSourceRegistry(sources)
        elif not isinstance(adapter, AdvisorSourceRegistry):
            raise TypeError(
                'AdvisorPortfolioSyncJob 的 adapter 必须是 AdvisorSourceRegistry（#1392 起一任务多平台）；'
                '只想测单个平台请用 sources={platform: 适配器实例}'
            )
        super().__init__(adapter, db)

    @property
    def _allow_empty_data(self) -> bool:
        # 库内无待抓组合时静默跳过，不报错阻断整体同步
        return True

    def get_name(self) -> str:
        return 'advisor_portfolio'

    # ── 数据源 ──

    def _source(self, platform: str) -> AdvisorPortfolioSource:
        """按平台取适配器（注册表懒构造 + 实例缓存）。"""
        return self.adapter.get(platform)

    # ── 目标解析 ──

    @staticmethod
    def _infer_platform(code: str) -> str:
        """库内未建档时的平台兜底：且慢元数据注册表命中即 QIEMAN，否则按天天基金。

        不能按代码前缀猜平台——且慢码含 LONG_WIN / LONG_WIN_S / J7 / WALLET / SIxxxx
        等非 ``ZH`` 命名空间，前缀判定会把它们误送进天天适配器。
        """
        return 'QIEMAN' if get_qieman_strategy(code) else DEFAULT_ADVISOR_PLATFORM

    def _resolve_targets(self, targets: List[str]) -> List[tuple]:
        """解析本轮待抓组合 → ``[(code, platform), ...]``。

        - 显式 targets：按 code 回查库内 platform；库内未建档的代码再用
          :meth:`_infer_platform`（且慢注册表）兜底。
        - 占位符 '__full__' 或空：回退库内全部在售、且**已有适配器**的平台组合
          （平台列表取自注册表，新增适配器后自动纳入全量，无需改这里）。
        """
        real = [t for t in (targets or []) if t != '__full__']
        if real:
            rows = (
                self.db.query(AdvisorPortfolio.code, AdvisorPortfolio.platform)
                .filter(AdvisorPortfolio.code.in_(real))
                .all()
            )
            known = {r.code: (r.platform or DEFAULT_ADVISOR_PLATFORM) for r in rows}
            return [(c, known.get(c) or self._infer_platform(c)) for c in real]
        rows = (
            self.db.query(AdvisorPortfolio.code, AdvisorPortfolio.platform)
            .filter(AdvisorPortfolio.is_active.is_(True))
            .filter(AdvisorPortfolio.platform.in_(self.adapter.platforms()))
            .all()
        )
        return [(r.code, r.platform) for r in rows]

    # ── 抓取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """按平台取适配器抓四个数据面——本方法**不含任何平台分支**。"""
        pairs = self._resolve_targets(targets)
        if not pairs:
            return []
        payloads = []
        for code, platform in pairs:
            code = (code or '').strip()
            if not code:
                continue
            try:
                src = self._source(platform)
            except UnknownAdvisorPlatform as e:
                # 库内可能存在尚无适配器的平台（如蛋卷）：跳过该组合即可，不炸整轮同步
                self.logger.warning(f'跳过投顾组合 {code}：{e}')
                continue
            overview = src.fetch_overview(code)
            holdings = src.fetch_holdings(code)
            self.logger.info(
                f'抓取投顾组合 {code}({platform})：概览 {"有" if overview else "无"} / '
                f'持仓 {len((holdings or {}).get("funds") or [])} 条'
            )
            payloads.append(
                {
                    'code': code,
                    'platform': platform,
                    # 能力位随 payload 走：落库层无需再回查注册表
                    'derive_rebalances': src.derive_rebalances_from_snapshots,
                    'overview': overview,
                    'holdings': holdings,
                    'industries': src.fetch_industries(code),
                    'rebalances': src.fetch_rebalances(code),
                }
            )
        return payloads

    # ── 校验 / 去重 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        out = []
        for p in raw_data:
            code = (p.get('code') or '').strip()
            if not code:
                continue
            # 四个数据面全空的组合视为无效（接口可能已下架），本轮跳过
            has_any = bool(
                p.get('overview')
                or (p.get('holdings') or {}).get('funds')
                or p.get('industries')
                or p.get('rebalances')
            )
            if not has_any:
                self.logger.warning(f'投顾组合 {code} 四类数据均空，跳过（可能已下架或接口变更）')
                continue
            p['code'] = code
            out.append(p)
        return out

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 覆盖式更新，不做去重剔除
        return data

    # ── 落库 ──

    def _get_or_create_portfolio(self, code: str, platform: str = DEFAULT_ADVISOR_PLATFORM) -> AdvisorPortfolio:
        row = self.db.query(AdvisorPortfolio).filter_by(platform=platform, code=code).first()
        if row is None:
            row = AdvisorPortfolio(platform=platform, code=code, name=code)
            self.db.add(row)
            self.db.flush()
        return row

    def _apply_holdings(self, portfolio: AdvisorPortfolio, funds: List[dict], as_of, source: str) -> int:
        """当前持仓按快照日整体覆盖（平台无关）；无快照日或无持仓则不写。"""
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

    #: 文本列的截断长度（与 models.py 列定义一致）：接口偶尔给出超长文本，
    #: 直接写入在 SQLite 会静默截断、在 Postgres 会报错，故在此显式收口。
    _TEXT_LIMITS = {
        'name': 100,
        'org_name': 100,
        'risk_level': 20,
        'strategy_summary': 300,
        'strategy_desc': 500,
        'source_url': 120,
    }

    def _apply_overview(self, portfolio: AdvisorPortfolio, ov: dict, source: str) -> int:
        """把 canonical 概览写入组合档案（平台无关），返回覆盖的字段数。

        - **只覆盖非 None 值**：接口缺字段 / 抓取失败（``{}``）不得把库内已有数据冲成空；
        - **策展字段**（:data:`CURATED_OVERVIEW_KEYS`：主理人 / 五笔钱 / 产品类型）由
          ``advisor_catalog`` 注册表维护，抓取永不覆盖（#1468 结论，此处做成硬约束）；
        - canonical 未覆盖的平台特有字段落 ``extra``（JSON 原样保留，便于日后补列回填）；
        - ``source`` 记录本次写入来源，回答「这行数据是谁写的」。
        """
        if not ov:
            return 0
        changed = 0
        for col in CANONICAL_OVERVIEW_COLUMNS:
            if col in CURATED_OVERVIEW_KEYS:
                continue
            value = ov.get(col)
            if value is None:
                continue
            if col in OVERVIEW_DATE_KEYS:
                value = _parse_date(value)
                if value is None:
                    continue
            elif col in self._TEXT_LIMITS:
                value = str(value)[: self._TEXT_LIMITS[col]]
            setattr(portfolio, col, value)
            changed += 1
        extra = ov.get(EXTRA_KEY)
        if extra:
            portfolio.extra = extra
            changed += 1
        portfolio.source = source
        return changed

    def _apply_industries(self, portfolio: AdvisorPortfolio, industries: List[dict], as_of, source: str) -> int:
        """行业配置按快照日整体覆盖（平台无关）。

        接口不单独给行业配置日期，沿用当日持仓快照日；无快照日则不写
        （宁可缺一天，也不落到一个来路不明的日期上）。
        """
        if not industries or not as_of:
            return 0
        self.db.query(AdvisorIndustryAlloc).filter_by(portfolio_id=portfolio.id, as_of_date=as_of).delete()
        rows = [
            {
                'portfolio_id': portfolio.id,
                'as_of_date': as_of,
                'industry_name': r['industry_name'],
                'ratio': r.get('ratio'),
                'source': source,
            }
            for r in industries
        ]
        self.db.bulk_insert_mappings(AdvisorIndustryAlloc, rows)
        return len(rows)

    def _apply_rebalances(self, portfolio: AdvisorPortfolio, rebalances: List[dict], source: str) -> int:
        """**官方**历史调仓逐调仓日覆盖（平台无关）；返回写入行数。

        无官方调仓接口的平台返回空列表 → 本方法无操作，改走
        :meth:`_derive_adjust_from_snapshots`。
        """
        n = 0
        for node in rebalances or []:
            adjust_date = _parse_date(node.get('adjust_date'))
            if not adjust_date or not node.get('funds'):
                continue
            self.db.query(AdvisorAdjustHistory).filter_by(portfolio_id=portfolio.id, adjust_date=adjust_date).delete()
            self.db.bulk_insert_mappings(
                AdvisorAdjustHistory,
                [
                    {
                        'portfolio_id': portfolio.id,
                        'adjust_date': adjust_date,
                        'reason': (node.get('reason') or '')[:300],
                        'fund_code': f['fund_code'],
                        'fund_name': f.get('fund_name'),
                        'pre_ratio': f.get('pre_ratio'),
                        'after_ratio': f.get('after_ratio'),
                        'op_code': f.get('op_code'),
                        'op_name': f.get('op_name'),
                        'source': source,
                    }
                    for f in node['funds']
                ],
            )
            n += len(node['funds'])
        return n

    def _derive_adjust_from_snapshots(self, portfolio: AdvisorPortfolio, as_of, source: str) -> int:
        """由「本次快照 vs 上一快照」推导**真实**调仓明细，落 advisor_adjust_histories。

        适用于**没有官方历史调仓接口**的平台（如且慢：MCP 只给当前持仓）。历史由我们自己的
        持仓快照序列推导，但判据是「**真的有变化**」而不是「快照日又推进了一天」（#1622）：

        1. **阈值**：只有 ``|Δratio| > ADVISOR_ADJUST_MIN_DELTA_PCT``（0.5pp）的基金入账，
           新增 / 清仓同样按阈值过滤。且慢占比是**市值口径**，每天随净值自然漂移
           （实测 p50=0.01pp / p99=0.23pp），不加阈值就会把漂移记成加仓/减仓。
        2. **无真实变化 → 不写任何行**：过滤后为空直接返回 0，当日视为"没调仓"；
           不再写 ``op=5 持平``——"没变"不是调仓，原实现正是靠它把每个交易日都填满。
        3. **基准取「上一次快照」**（而非上次调仓状态）：漂移是**逐日**量级，逐日比较不会被
           累积放大；实测真实调仓是**单日原子完成**（相邻快照对 Σ|Δ|：漂移日 1~2pp vs
           真调仓日 16~60pp），因此逐日比较不会漏掉真调仓。
           **已知代价**：若某次调仓分多日、每天变化都低于阈值，会漏记——实测数据里没有这种形态；
           若日后出现，应改为「累计变化」口径并重标阈值。

        首次快照没有前值可对比 → 跳过（不编造 0 → X 的假建仓记录）。
        有官方调仓接口的平台走 :meth:`_apply_rebalances`，不进此路径。返回写入行数。
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
        if not cur or not prev:
            return 0

        rows = []
        for code in sorted(set(prev) | set(cur)):
            b, b_name = prev.get(code, (None, None))
            a, a_name = cur.get(code, (None, None))
            before = float(b) if b is not None else 0.0
            after = float(a) if a is not None else 0.0
            if abs(after - before) <= ADVISOR_ADJUST_MIN_DELTA_PCT:
                # 净值漂移 / 无实质变化：不是调仓，跳过（原实现这里写 op=5 持平行）
                continue
            if b is None:
                op = 4  # 新增
            elif a is None:
                op = 3  # 减仓（清仓至 0）
            elif after > before:
                op = 2  # 加仓
            else:
                op = 3  # 减仓
            rows.append(
                {
                    'portfolio_id': portfolio.id,
                    'adjust_date': as_of,
                    'reason': f'由 {prev_date} 持仓快照推导（变化>{ADVISOR_ADJUST_MIN_DELTA_PCT}pp）'[:300],
                    'fund_code': code,
                    'fund_name': a_name or b_name,
                    'pre_ratio': before,
                    'after_ratio': after,
                    'op_code': op,
                    'op_name': ADVISOR_ADJUST_OP_NAME.get(op),
                    'source': source,
                }
            )
        if not rows:
            # 无真实变化：不写任何调仓记录（#1622 的核心修复）
            return 0
        # 同调仓日整体覆盖（与官方调仓同语义）
        self.db.query(AdvisorAdjustHistory).filter_by(portfolio_id=portfolio.id, adjust_date=as_of).delete()
        self.db.bulk_insert_mappings(AdvisorAdjustHistory, rows)
        return len(rows)

    def _save_data(self, new_data: List[dict]) -> None:
        """平台无关的落库：概览 + 持仓 + 行业 + 调仓（+ 快照推导），逐组合提交。

        逐组合单独 commit：一轮可能跨上百个组合，整批共用一个事务会把失败半径放大到
        整批，也让 SQLite 写锁长时间不释放。

        本方法**不含平台分支**：数据来源标识统一取 ``platform.lower()``
        （TIANTIAN→tiantian、QIEMAN→qieman，与历史已落库数据同口径）；
        「无官方调仓接口」这类能力差异由 payload 的 ``derive_rebalances`` 位驱动。
        """
        for p in new_data:
            platform = p.get('platform') or DEFAULT_ADVISOR_PLATFORM
            source = platform.lower()
            portfolio = self._get_or_create_portfolio(p['code'], platform)
            n_ov = self._apply_overview(portfolio, p.get('overview') or {}, source)

            holdings = p.get('holdings') or {}
            as_of = _parse_date(holdings.get('as_of_date'))
            n_hold = self._apply_holdings(portfolio, holdings.get('funds') or [], as_of, source)
            n_ind = self._apply_industries(portfolio, p.get('industries') or [], as_of, source)
            n_hist = self._apply_rebalances(portfolio, p.get('rebalances') or [], source)
            # 无官方调仓接口的平台：由快照序列推导本次调仓（首次快照无前值，自动跳过）
            n_derived = (
                self._derive_adjust_from_snapshots(portfolio, as_of, source)
                if p.get('derive_rebalances') and n_hold
                else 0
            )
            self.db.commit()
            self.logger.info(
                f'投顾组合 {p["code"]}({platform}) 落库: 概览 {n_ov} 字段, 持仓 {n_hold} 条(as_of={as_of}), '
                f'行业 {n_ind} 条, 官方调仓 {n_hist} 条, 推导调仓 {n_derived} 条'
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
    db.query(AdvisorHolding).filter_by(
        portfolio_id=portfolio.id, as_of_date=as_of, source=SOURCE_QIEMAN_MANUAL
    ).delete()
    db.bulk_insert_mappings(
        AdvisorHolding,
        [
            {
                'portfolio_id': portfolio.id,
                'as_of_date': as_of,
                'fund_code': f['fund_code'],
                'fund_name': f.get('fund_name'),
                'after_ratio': f.get('after_ratio'),
                'source': SOURCE_QIEMAN_MANUAL,
            }
            for f in funds
        ],
    )
    db.commit()
    logger.info(f'且慢组合 {portfolio_code} 导入 {len(funds)} 条持仓 (as_of={as_of})')
    return len(funds)
