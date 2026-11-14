# -*- coding: utf-8 -*-
"""账本精灵·基金级只读工具包（#3111）。

为什么单独一个模块，而不是继续堆进 ``tools.py``
------------------------------------------------
``tools.py`` 现有 10 个工具全部是**账户/家庭维度**（总资产、组合 XIRR、逐持仓盈亏、
基准对比、归因、行为画像、市场温度、自选、再平衡）。基金级问题（「这只基金重仓什么」
「风格换了没有」）在它里面没有位置，而且该文件 644 行已被
``scripts/guard_service_size.py`` 冻结在 ``lines: 644``（只减不增）——新工具塞进去必然红灯。
故本模块承载基金级工具，``tools.py`` 只保留 2 行接线（导入 + ``install_fund_tools``）。

三条硬纪律（比账户级工具更严，逐条都有单测）
--------------------------------------------
1. **严格只读**：不 ``commit``、不回填、不出网。``build_fund_profile`` 默认末尾会做
   「基金公司」单只回填（``fund_company_backfill.ensure_fund_company``：写库 + 可能抓上游），
   工具路径必须传 ``allow_backfill=False``——否则一个「查询」会静默写库。
2. **出参投影**：原始 service 出参直接回给模型会挤掉上下文（风格历史 60 个时点 ≈ 9KB，
   持仓全量可能上百行）。每个工具只保留叙事需要的字段，单次 ≤ 2KB。
3. **缺数据如实**：基金不存在回 ``found: false``；存在但无披露回 ``applicable: false`` /
   ``has_data: false``。不补零、不编占位值——模型拿不到数字就只能说「没有」，
   这正是 ``_L1_DATA_TRUTH`` 要的。

DB 会话走 market 域（``db_factory.market_session_factory``）：基金档案 / 净值 / 持仓 /
风格四张表都在 market 库。引用方式必须是**模块级** ``db_factory.market_session_factory()``，
不能 from-import（测试靠 monkeypatch 工厂，早绑定会让测试落到真实 dev 库，#1608 晚绑定守卫）。
"""

from __future__ import annotations

from contextlib import closing
from typing import Any, Callable, Dict, List, Optional

from app.core import db_factory  # 模块级引用（#1608 晚绑定守卫）
from app.services.fund_holdings_detail import build_fund_holdings_detail
from app.services.fund_performance import build_fund_performance
from app.services.fund_profile import build_fund_profile
from app.services.fund_style_service import get_fund_style_box, get_fund_style_history

# 投影上限：够叙事用，又不会把 prompt 撑爆（详见各工具 docstring）
_MAX_MANAGERS = 3
_MAX_FEE_TIERS = 4
_MAX_INDUSTRY_ROWS = 8
_MAX_HOLDING_ROWS = 10
_MAX_STYLE_TILES = 3
_STYLE_HISTORY_POINTS = 12


def _market_session():
    """market 域只读会话（调用方负责 ``closing``）。"""
    return closing(db_factory.market_session_factory()())


def _fund_exists(db, fund_code: str) -> bool:
    """基金是否在本库名录里（区分「不存在」与「存在但无某类数据」）。"""
    from app.domains.funds.models import Fund

    return db.query(Fund.id).filter(Fund.fund_code == fund_code).first() is not None


# ── 1. 档案 + 最新净值 ───────────────────────────────────────────────────
def _tool_get_fund_profile(params: dict) -> dict:
    """单只基金的档案与最新净值（含经理、费率阶梯）。

    只读保证：``allow_backfill=False``——公司名缺失时**不**触发单只回填
    （回填会 ``db.commit()`` 且可能请求上游，见 ``fund_profile`` 模块 docstring）。

    费率两条单位约定随字段名下发，不让模型自己猜（``fundFeeFormat.ts`` 已钉住同一条）：
    ``rate_pct`` 是百分数（``1.5`` 表示 1.5%）；``end_day_exclusive`` /
    ``end_quota_exclusive`` 为 ``None`` 表示该档无上限，且区间是**半开**——
    ``days: [0, 7)`` 要读作「不足 7 天」，不是「0~7 天」。
    ``fee_amount`` 与 ``rate`` 互斥：大额档常是「每笔 1000 元」，此时 ``rate_pct`` 为 0，
    只读费率会把它说成「免费申购」。
    """
    code = params['fund_code']
    with _market_session() as db:
        profile = build_fund_profile(db, code, allow_backfill=False)

    if profile is None:
        return {'fund_code': code, 'found': False}
    fees = profile.get('fee_rates') or {}
    # 费率阶梯**接口不保证顺序**（后端查询无 ORDER BY，见 fundFeeFormat.ts 的踩坑记录）：
    # 不排序会让模型把某一档当成「首档」念给用户，故一律按区间下界升序后再截断。
    purchase = sorted(fees.get('purchase') or [], key=lambda t: t.get('start_quota') or 0)[:_MAX_FEE_TIERS]
    redeem = sorted(fees.get('redeem') or [], key=lambda t: t.get('start_day') or 0)[:_MAX_FEE_TIERS]
    return {
        'fund_code': profile['fund_code'],
        'found': True,
        'name': profile.get('name'),
        'full_name': profile.get('full_name'),
        'fund_type': profile.get('fund_type'),
        'fund_variety': profile.get('fund_variety'),
        'company': profile.get('company'),
        'scale': profile.get('scale'),
        'create_time': profile.get('create_time'),
        'risk_level': profile.get('risk_level'),
        'benchmark': profile.get('benchmark'),
        'unit_nav': profile.get('unit_nav'),
        'nav_date': profile.get('nav_date'),
        'change_pct': profile.get('change_pct'),
        'morningstar_rating': profile.get('morningstar_rating'),
        'managers': [
            {'name': m.get('name'), 'appointment_date': m.get('appointment_date')}
            for m in (profile.get('managers') or [])[:_MAX_MANAGERS]
        ],
        'purchase_fee_tiers': [
            {
                'start_quota': tier.get('start_quota'),
                'end_quota_exclusive': tier.get('end_quota'),
                'rate_pct': _pct_of(tier.get('rate')),
                'fee_amount': tier.get('fee_amount'),
            }
            for tier in purchase
        ],
        'redeem_fee_tiers': [
            {
                'start_day': tier.get('start_day'),
                'end_day_exclusive': tier.get('end_day'),
                'rate_pct': _pct_of(tier.get('rate')),
            }
            for tier in redeem
        ],
        'source': profile.get('source'),
    }


def _pct_of(rate: Optional[float]) -> Optional[float]:
    """小数费率 → 百分数（``0.015`` → ``1.5``）；``None`` 原样返回，不补 0。"""
    return round(float(rate) * 100, 2) if rate is not None else None


# ── 2. 业绩与风险 ────────────────────────────────────────────────────────
def _tool_get_fund_performance(params: dict) -> dict:
    """单只基金的区间业绩与风险指标。

    消费方必须守住的四条（否则会误读或越界）：
    - ``intervals`` 是**区间涨幅**（近1周…近3年），不是年化；年化看 ``annual_return``；
    - ``max_drawdown`` 是**历史最大回撤**（负值或绝对值按 ``max_drawdown_basis`` 说明），
      ``current_drawdown`` 是「距上一个高点」的当前回撤，两者不是一回事；
    - ``peer_percentiles`` 是**同类内分位**（100 = 同类最好），分母是同类样本、
      不是全市场；分位可读绝对值不可跨类别比；
    - 本工具只回已发生的数字。**不做预测、不评价基金好坏、不给买卖方向**——
      这类问题由 ``intent_guard`` 在输入侧拦截，不在本工具兜。

    ``shape_gain`` / ``shape_gain2``（拟涨幅，四期滚动加权的实验口径）**刻意不投影**：
    它是内部研究指标、口径复杂，进叙事只会被模型讲错。
    """
    code = params['fund_code']
    with _market_session() as db:
        perf = build_fund_performance(db, code)

    if perf is None:
        return {'fund_code': code, 'found': False}
    if not perf.get('applicable', True):
        # 存在但算不出（新基金不足一年 / 货基走另一条口径）：如实回，不塞近似值
        return {
            'fund_code': code,
            'found': True,
            'applicable': False,
            'fund_kind': perf.get('fund_kind'),
            'basis': perf.get('basis'),
            'as_of': perf.get('as_of'),
            'source': perf.get('source'),
        }

    bench = perf.get('benchmark') or {}
    return {
        'fund_code': code,
        'found': True,
        'applicable': True,
        'fund_kind': perf.get('fund_kind'),
        'basis': perf.get('basis'),
        'as_of': perf.get('as_of'),
        'intervals': [{'label': it.get('label'), 'value': it.get('value')} for it in perf.get('intervals') or []],
        'max_drawdown': perf.get('max_drawdown'),
        'max_drawdown_basis': perf.get('max_drawdown_basis'),
        'max_drawdown_window': perf.get('max_drawdown_window'),
        'max_drawdown_as_of': perf.get('max_drawdown_as_of'),
        'current_drawdown': perf.get('current_drawdown'),
        'current_drawdown_days': perf.get('current_drawdown_days'),
        'annual_return': perf.get('annual_return'),
        'annual_volatility': perf.get('annual_volatility'),
        'sharpe': perf.get('sharpe'),
        'sortino': perf.get('sortino'),
        'calmar': perf.get('calmar'),
        'win_rate': perf.get('win_rate'),
        'win_rate_period': perf.get('win_rate_period'),
        'peer_percentiles': perf.get('peer_percentiles'),
        'risk_window': perf.get('risk_window'),
        'risk_sample_points': perf.get('risk_sample_points'),
        'benchmark': {
            'name': bench.get('name'),
            'code': bench.get('code'),
            'available': bench.get('available'),
            'as_of': bench.get('as_of'),
            'fund_annual_return': bench.get('fund_annual_return'),
            'bench_annual_return': bench.get('bench_annual_return'),
            'excess_return': bench.get('excess_return'),
            'information_ratio': bench.get('information_ratio'),
        },
        'risk_caveats': perf.get('risk_caveats'),
        'source': perf.get('source'),
    }


# ── 3. 行业配置 + 持仓明细 ───────────────────────────────────────────────
def _tool_get_fund_holdings(params: dict) -> dict:
    """单只基金的行业配置与前十大持仓（穿透到个股）。

    三条口径（消费方须原样转述，不得自行合并或换算）：
    - 行业按 ``scheme`` **分区**（csrc 证监会门类 / gics 板块），**禁止跨体系相加**——
      两套体系语义不重叠，相加会得出「制造业与非必需消费品同级」的荒谬结论；
      主口径由 ``is_primary`` 标出；
    - ``basis_label`` 说明持仓是**季报前十大**还是**半年报全量**：只披露 10 只
      ≠ 只买了 10 只，转述时必须带上口径，否则用户会误读集中度；
    - ``shown_total_ratio`` 是「所示各行合计」，不是「前十大合计」（全量口径下含义不同）。
    """
    code = params['fund_code']
    with _market_session() as db:
        detail = build_fund_holdings_detail(
            db,
            code,
            industry_top_n=_MAX_INDUSTRY_ROWS,
            holding_top_n=_MAX_HOLDING_ROWS,
        )

    if detail is None:
        return {'fund_code': code, 'found': False}
    if not detail.get('applicable'):
        return {
            'fund_code': code,
            'found': True,
            'applicable': False,
            'fund_name': detail.get('fund_name'),
            'as_of': detail.get('as_of'),
            'source': detail.get('source'),
        }

    industries = detail.get('industries') or []
    primary = next((b for b in industries if b.get('is_primary')), industries[0] if industries else {})
    holdings = detail.get('holdings') or {}
    return {
        'fund_code': code,
        'found': True,
        'applicable': True,
        'fund_name': detail.get('fund_name'),
        'as_of': detail.get('as_of'),
        'source': detail.get('source'),
        'industry_scheme': primary.get('scheme_label'),
        'industry_report_period': primary.get('report_period'),
        'industry_total_ratio': primary.get('total_ratio'),
        'industries': [
            {'name': it.get('industry_name'), 'ratio': it.get('ratio')}
            for it in primary.get('items') or []
            if it.get('industry_name')
        ],
        'holding_basis_label': holdings.get('basis_label'),
        'holding_report_period': holdings.get('report_period'),
        'holding_shown_total_ratio': holdings.get('shown_total_ratio'),
        'holdings': [
            {
                'rank': row.get('rank'),
                'stock_code': row.get('stock_code'),
                'stock_name': row.get('stock_name'),
                'ratio': row.get('ratio'),
            }
            for row in holdings.get('rows') or []
        ],
    }


# ── 4. 风格箱 + 漂移 ─────────────────────────────────────────────────────
def _tool_get_fund_style(params: dict) -> dict:
    """单只基金的风格箱与风格漂移信号。

    回答的是「**宣称风格 vs 实际持仓风格**」这一层：各风格占比是第三方（韭圈儿）
    按持仓穿透测算的，**不是基金合同的承诺**，转述时须带上来源。

    ``dominant_history`` 是近 12 个时点的主导风格序列（倒序取回后翻转成时间正序），
    只有「主导风格切换」这一层信号；``dominant_changed`` 只比较最近两个时点。
    占比全为 0 的时点主导风格记 ``None``（不拿 0 值猜一个风格）。
    """
    code = params['fund_code']
    with _market_session() as db:
        box = get_fund_style_box(db, code)
        if box is None:
            return {'fund_code': code, 'found': _fund_exists(db, code), 'has_data': False}
        history = get_fund_style_history(db, code, limit=_STYLE_HISTORY_POINTS)

    tiles = [t for t in box.get('styles') or [] if t.get('value')]
    tiles.sort(key=lambda t: t.get('value') or 0, reverse=True)
    points = list(reversed(history.get('points') or []))
    return {
        'fund_code': code,
        'found': True,
        'has_data': True,
        'as_of': box.get('stat_date'),
        'dominant_style': box.get('dominant_style'),
        'dominant_pct': next(
            (t.get('value') for t in tiles if t.get('style_name') == box.get('dominant_style')),
            None,
        ),
        'top_styles': [{'style': t.get('style_name'), 'pct': t.get('value')} for t in tiles[:_MAX_STYLE_TILES]],
        'prev_dominant_style': box.get('prev_dominant_style'),
        'prev_period': box.get('prev_period'),
        'dominant_changed': box.get('dominant_changed'),
        'dominant_history': [
            {'period': p.get('stat_date'), 'dominant': _dominant_of(p.get('styles') or {})} for p in points
        ],
        'history_points': history.get('count'),
        'source': box.get('source'),
    }


def _dominant_of(styles: Dict[str, Any]) -> Optional[str]:
    """某时点占比最高的风格；全为 0 / 空时返回 ``None``（不猜）。"""
    ranked = [(name, v) for name, v in styles.items() if v]
    return max(ranked, key=lambda pair: pair[1])[0] if ranked else None


# ── 注册 + 元信息 ────────────────────────────────────────────────────────
_FUND_TOOL_FUNCS: Dict[str, Callable[[dict], dict]] = {
    'get_fund_profile': _tool_get_fund_profile,
    'get_fund_performance': _tool_get_fund_performance,
    'get_fund_holdings': _tool_get_fund_holdings,
    'get_fund_style': _tool_get_fund_style,
}

_FUND_CODE_SCHEMA = {'type': 'string', 'pattern': r'^\d{6}$', 'description': '6 位基金代码，如 "110011"'}

FUND_TOOLS_METADATA: List[dict] = [
    {
        'name': 'get_fund_profile',
        'description': '查单只基金的档案与最新净值：名称/全名/类型/公司/规模/成立日/风险等级/'
        '基金经理/申购与赎回费率阶梯/最新单位净值与日涨跌。当用户问「这只基金是什么类型」'
        '「谁在管这只基金」「规模多大」「申购赎回费率多少」「最新净值多少」时使用。'
        '问业绩与回撤用 get_fund_performance，问它投了什么行业与股票用 get_fund_holdings。'
        '返回 found=false 表示本库没有这只基金，如实告知，不要用通用知识补它的资料',
        'parameters': {
            'type': 'object',
            'properties': {'fund_code': _FUND_CODE_SCHEMA},
            'required': ['fund_code'],
        },
    },
    {
        'name': 'get_fund_performance',
        'description': '查单只基金的区间业绩与风险指标：近1周/1月/3月/6月/1年等区间涨幅、'
        '历史最大回撤与当前回撤、年化收益与波动、夏普/索提诺/卡玛比率、胜率、同类分位，'
        '以及对应基准的同区间年化收益与超额。当用户问「这只基金近一年涨了多少」'
        '「回撤多大」「波动大不大」「同类里排第几」时使用。'
        '只回已发生的数字：不预测涨跌、不评价基金好坏、不给买卖方向；'
        'intervals 是区间涨幅不是年化，peer_percentiles 是同类分位（100=同类最好）',
        'parameters': {
            'type': 'object',
            'properties': {'fund_code': _FUND_CODE_SCHEMA},
            'required': ['fund_code'],
        },
    },
    {
        'name': 'get_fund_holdings',
        'description': '查单只基金的行业配置与前十大持仓明细（穿透到个股）：行业占比、'
        '所示合计占比、报告期；持仓含股票代码/名称/占净值比。当用户问「这只基金重仓什么行业」'
        '「前十大持仓是哪些股票」「是不是重仓白酒/半导体」时使用。'
        '行业按 scheme 分区（证监会门类 / GICS），**禁止跨体系相加**；'
        'holding_basis_label 说明是季报前十大还是半年报全量——只披露 10 只不等于只买了 10 只，'
        '转述必须带口径；applicable=false 表示该基金没有披露数据',
        'parameters': {
            'type': 'object',
            'properties': {'fund_code': _FUND_CODE_SCHEMA},
            'required': ['fund_code'],
        },
    },
    {
        'name': 'get_fund_style',
        'description': '查单只基金的风格箱与风格漂移：最新时点各风格占比（大盘/中盘/小盘 × '
        '成长/价值，另有港股与固收风格）、主导风格、上一时点主导风格、是否发生切换、'
        '近 12 个时点的主导风格序列。当用户问「这只基金什么风格」「风格有没有漂移/换过风格」'
        '「实际持仓是成长还是价值」时使用。风格占比是第三方（韭圈儿）按持仓穿透测算，'
        '不是基金合同的承诺，转述须带来源；has_data=false 表示该基金暂无风格测算数据',
        'parameters': {
            'type': 'object',
            'properties': {'fund_code': _FUND_CODE_SCHEMA},
            'required': ['fund_code'],
        },
    },
]


def install_fund_tools(register: Callable[[str, Callable], None], metadata: List[dict]) -> None:
    """把基金级工具接入 ``tools.py`` 的注册表与元数据清单。

    显式调用而非 import 副作用：调用点只有一处（``tools.py``），
    「是否真的接上了」由单测集合相等断言钉住，不靠 import 顺序碰运气。
    """
    for name, func in _FUND_TOOL_FUNCS.items():
        register(name, func)
    metadata.extend(FUND_TOOLS_METADATA)


__all__ = ['FUND_TOOLS_METADATA', 'install_fund_tools']
