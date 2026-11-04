# -*- coding: utf-8 -*-
"""账本精灵工具包（ToolExecutor + 工具注册表）。

职责（D19 铁律）：工具内只做**只读查询与数值计算**，绝不让模型写代码；
执行结果只回传指标值给 AgentLoop 拼回 prompt 叙事。

- TOOLS_METADATA：工具元信息（name / description / parameters），同时给模型看 + 给代码做 schema 校验；
- ToolExecutor.run：服务端上下文覆盖（P1）→ schema 校验 → 派发 → {status, data|msg}；
- 出错时上层 AgentLoop 负责「最多 1 次重试」（error-as-observation），本层不重试、不崩；
- 每次执行必留 `[agent.tool]` 结构化日志（成功 ok / 失败 fail，含耗时），
  线上排障按 tag 过滤（#1121 S1-C）。

P1 越权防护（2026-09-26，#1121 S1-A）：
前端回传的 collected_params 与模型生成的 tool_params 都只是**候选值**；
服务端权威值（server_ctx，如 family_id）在 run() 内强制覆盖同名候选。
覆盖只对「该工具 schema 声明过的键」生效——未声明 family_id 的工具（如 get_fund_nav）
若被塞入 family_id，会在校验期被当**未知参数**拒绝，两头都堵死。
服务端不传 server_ctx 时 family_id 回退 1，与 core.auth.get_family_id 的单用户口径一致；
HTTP 路径由 views 层必传，不存在「前端可指定」的入口。
"""

import re
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional

from loguru import logger
from sqlalchemy import func

from app.core import database  # 模块级引用，禁止 from-import get_session（#1608 晚绑定守卫）
from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.analytics.benchmark_comparison import build_benchmark_comparison
from app.services.analytics.trading_behavior import build_trading_behavior
from app.services.bias.constants import BENCHMARK_INDICES
from app.services.nav_service import NavService
from app.services.performance.calculators import calculate_portfolio_xirr
from app.services.pnl_calendar import compute_range_attribution
from app.services.position_scope import exclude_cleared
from app.services.position_valuation import market_value_cents
from app.services.summary_service import get_summary_data
from app.services.thermometer.service import TemperatureService
from app.services.watchlist_service import build_home_summary

# name -> 实现函数（注册表）
_FUNCTION_MAP: Dict[str, Callable] = {}


def register_tool(name: str, func: Callable) -> None:
    """注册一个工具实现函数。"""
    _FUNCTION_MAP[name] = func


# ── P1：服务端权威上下文 ────────────────────────────────────────────────────
def apply_server_context(tool_name: str, params: dict, server_ctx: dict) -> dict:
    """把服务端权威值覆盖进候选参数（只覆盖该工具 schema 声明过的键）。

    候选参数 = 前端 collected_params + 模型 tool_params；权威值 = 鉴权上下文。
    返回新 dict，不原地修改入参。
    """
    if not server_ctx:
        return params
    meta = next((t for t in TOOLS_METADATA if t['name'] == tool_name), None)
    if not meta:
        return params  # 未知工具：原样交给 _validate_params 报「未知工具」
    props = meta['parameters'].get('properties', {})
    merged = dict(params)
    for key, value in server_ctx.items():
        if key in props:
            merged[key] = value
    return merged


def _server_family_id(params: dict) -> int:
    """取注入后的 family_id；缺省回退 1（与 core.auth.get_family_id 口径一致）。"""
    try:
        return int(params.get('family_id') or 1)
    except (TypeError, ValueError):
        return 1


def _jsonable(value: Any) -> Any:
    """date/datetime → isoformat 递归转换（工具数据进 JSON 信封的兜底）。"""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


# ── 工具实现（全部只读，复用既有 service，零裸 SQL） ────────────────────────
def _tool_get_assets_overview(params: dict) -> dict:
    """家庭资产总览：总资产 / 负债 / 净资产 / 已实现与未实现盈亏（元）。"""
    with database.get_session() as db:
        return get_summary_data(db, family_id=_server_family_id(params))


def _tool_get_portfolio_performance(params: dict) -> dict:
    """组合年化收益 XIRR：投入 / 市值 / 总收益（元，family 维度）。"""
    with database.get_session() as db:
        return calculate_portfolio_xirr(
            db,
            family_id=_server_family_id(params),
            include_cash_equivalents=bool(params.get('include_cash_equivalents', False)),
        )


def _tool_list_position_pnl(params: dict) -> dict:
    """逐持仓盈亏明细（#1711）：成本 / 市值 / 盈亏额 / 盈亏率，按盈亏率降序。

    口径同源持仓页（position_presenter.enrich_position_dict）：
    - 市值走唯一口径 position_valuation.market_value_cents（本币直算，不查库不出网）；
    - 盈亏 = (现价 − 成本均价) × 份额（整数分，Money.multiply_price_quantity），
      无成本均价（avg_price=0）时盈亏记 0——与持仓页盈亏列逐字同口径；
    - 成本 = 成本均价 × 份额（与 position_aggregation._position_cost_cents 同式）；
    - 盈亏率 = 盈亏 / 成本（整数分相除后转百分比，2 位小数），成本为 0 时 None
      （聚合页对应显示 "--"，不参与排序、沉底）。
    """
    with database.get_session() as db:
        positions = exclude_cleared(db.query(Position).filter(Position.family_id == _server_family_id(params))).all()

    items = []
    for p in positions:
        mv_cents = market_value_cents(p)
        cost_cents = Money.multiply_price_quantity(p.avg_price, p.quantity) if p.avg_price else 0
        pnl_cents = Money.multiply_price_quantity(p.current_price - p.avg_price, p.quantity) if p.avg_price else 0
        pnl_rate = round(pnl_cents / cost_cents * 100, 2) if cost_cents > 0 else None
        items.append(
            {
                'symbol': p.symbol,
                'name': p.name,
                'type': p.asset_type,
                'account_name': p.account_name,
                'quantity': Money.min_unit_to_shares(p.quantity),
                'avg_price': Money.price_units_to_yuan(p.avg_price),
                'current_price': Money.price_units_to_yuan(p.current_price),
                'cost': Money.cents_to_yuan(cost_cents),
                'market_value': Money.cents_to_yuan(mv_cents),
                'pnl': Money.cents_to_yuan(pnl_cents),
                'pnl_rate': pnl_rate,
            }
        )
    # 盈亏率降序（赚在前、亏在后）；无成本价的 None 沉底，不参与排序
    items.sort(key=lambda r: (r['pnl_rate'] is not None, r['pnl_rate'] or 0), reverse=True)
    return {'items': items, 'count': len(items)}


def _tool_get_trading_behavior(params: dict) -> dict:
    """交易行为画像（#2619）：持有期分布 / 换手 / 买卖结构 / 买点分位。

    与 `list_position_pnl`（盈亏明细）、`get_return_attribution`（收益归因）的区别：
    本工具回答的是**操作习惯**，不涉及盈亏。

    消费方必须守住的三条（否则会误读或幻觉）：
    - 只给客观统计，**不做好坏评价**：不要据此说「你换手太高/爱追涨」；
    - `buy_price_percentile.coverage_pct` 可能很低（真库仅部分标的有历史价格），
      低覆盖时不得把均值当作全样本结论；
    - `holding.samples` 是分位数样本量，为 0/1 时分位数无意义（None）；
      `trading.buy_sell_ratio` 在零卖出时为 None（不是 0）。
    """
    with database.get_session() as db:
        return build_trading_behavior(
            db,
            family_id=_server_family_id(params),
            start_date=params.get('start_date'),
            end_date=params.get('end_date'),
            symbol=params.get('symbol'),
        )


def _tool_get_portfolio_vs_benchmark(params: dict) -> dict:
    """组合同期基准对比（#2620）：区间收益 / 基准收益 / 超额 / 回撤 / 相关系数。

    与 `get_portfolio_performance`（绝对年化 XIRR）的分工：本工具回答「跑赢了吗」，
    即「收益是本事还是市场给的」。全部字段复用既有基准链路
    （`analytics.benchmark_comparison` → `build_scope_excess` / `index_daily`），
    零新表、零外部请求。

    口径要点（消费方须知道，否则会误读）：
    - 超额 = 组合区间收益 − 基准区间涨跌幅（百分点），**同期、同复权**，不是年化；
    - 最大回撤用日收益连乘（TWR 链式），缺口日跳过不填 0；
    - 相关系数按**对齐后的日收益**算，样本数一并返回（< 3 或零波动回 None）；
    - `available=False` 时**不许**用近似值补：读 `unavailable_reason` 与
      `coverage_gaps`（基准缺哪段）如实告知用户。
    """
    with database.get_session() as db:
        return build_benchmark_comparison(
            db,
            family_id=_server_family_id(params),
            start_date=params.get('start_date'),
            end_date=params.get('end_date'),
            benchmark_code=params.get('benchmark'),
        )


def _earliest_confirm_date(db, family_id: int) -> Optional[str]:
    """本家庭最早一笔流水的确认日（归因「缺省全期」的起点）。

    用 `confirm_date` 而不是 `trade_date`：真库实测 trade_date 有 63% 为空
    （2026-10-25 核对 1927 笔中 1211 笔无发起日），confirm_date 100% 填充，
    且 pnl 引擎本身按确认日结算。
    """
    earliest = db.query(func.min(Transaction.confirm_date)).filter(Transaction.family_id == family_id).scalar()
    return earliest.isoformat() if earliest else None


def _tool_get_return_attribution(params: dict) -> dict:
    """收益贡献归因（#2618）：区间收益按标的 / 账户拆到贡献占比。

    与 `list_position_pnl`（#1711）的分工——**明细 ≠ 归因**：
    前者是每行绝对盈亏，各行不可相加成组合总收益（分母不同）；本工具把区间
    收益额拆到每个标的/账户，`contribution_pct` 各行相加 ≈ 100。

    口径（全部复用既有唯一算账，不在本层重写）：
    - 收益额来自 `pnl_calendar.compute_range_attribution`（#2135），与收益日历
      同一次 `_compute_days` 遍历 ⇒ `Σ items.pnl ≡ 区间合计` 由构造保证；
    - 占比 = 该标的分位整数分 / 区间合计整数分 × 100（合计为 0 时 None，
      「没赚没赔」的占比无意义，与 #2135 的 `pct` 同纪律）；
    - 缺省区间为**全期**（最早一笔流水的确认日起），显式传日期则按传入区间；
    - 整窗无价的持仓进 `unpriced_count`、不进合计（不造 0 明细）。

    dimension=instrument 按持仓（多账户同一标的各自成行，便于定位账户）；
    dimension=account 先按 ledger 聚合金额再算占比（聚合只做整数分相加）。
    """
    dimension = params.get('dimension') or 'instrument'
    with database.get_session() as db:
        family_id = _server_family_id(params)
        start_date = params.get('start_date') or _earliest_confirm_date(db, family_id)
        attr = compute_range_attribution(
            db,
            family_id=family_id,
            start_date=start_date,
            end_date=params.get('end_date'),
        )
        account_names: Dict[int, str] = {}
        if dimension == 'account':
            ledger_ids = {r['ledger_id'] for r in attr['positions'] if r['ledger_id'] is not None}
            if ledger_ids:
                account_names = {
                    led.id: led.name
                    for led in db.query(Ledger).filter(Ledger.id.in_(ledger_ids), Ledger.family_id == family_id).all()
                }

    total_cents = Money.yuan_to_cents(attr['total_pnl']) if attr['total_pnl'] is not None else None

    def _pct(pnl_cents: int) -> Optional[float]:
        return round(pnl_cents / total_cents * 100, 2) if total_cents else None

    if dimension == 'account':
        buckets: Dict[Optional[int], dict] = {}
        for row in attr['positions']:
            ledger_id = row['ledger_id']
            bucket = buckets.setdefault(
                ledger_id,
                {
                    'ledger_id': ledger_id,
                    'account_name': account_names.get(ledger_id),
                    'pnl_cents': 0,
                    'positions_count': 0,
                },
            )
            bucket['pnl_cents'] += Money.yuan_to_cents(row['pnl'])
            bucket['positions_count'] += 1
        rows = sorted(buckets.values(), key=lambda b: abs(b['pnl_cents']), reverse=True)
    else:
        rows = [
            {
                'symbol': row['symbol'],
                'name': row['name'],
                'asset_type': row['asset_type'],
                'ledger_id': row['ledger_id'],
                'pnl_cents': Money.yuan_to_cents(row['pnl']),
                'positions_count': 1,
            }
            for row in attr['positions']
        ]

    items = [
        {
            **{k: v for k, v in row.items() if k != 'pnl_cents'},
            'pnl': Money.cents_to_yuan(row['pnl_cents']),
            'contribution_pct': _pct(row['pnl_cents']),
        }
        for row in rows
    ]
    # 不把内部整数分暴露给模型：单位纪律要求出参一律元（#2610 同一条）。
    return {
        'dimension': dimension,
        'scope': attr['scope'],
        'start_date': attr['start_date'],
        'end_date': attr['end_date'],
        'total_pnl': attr['total_pnl'],
        'items': items,
        'count': len(items),
        'has_any_computable': attr['has_any_computable'],
        'unpriced_count': len(attr['unpriced_positions']),
    }


def _tool_get_fund_nav(params: dict) -> dict:
    """基金最新净值（只读本地已同步净值；allow_remote=False，工具自身不出网）。"""
    fund_codes: List[str] = params.get('fund_codes') or []
    with database.get_session() as db:
        dated = NavService.get_latest_navs_with_dates(db, fund_codes, allow_remote=False)
    return {
        'navs': [
            {'fund_code': code, 'unit_nav': nav, 'nav_date': nav_date.isoformat()}
            for code, (nav, nav_date) in dated.items()
        ]
    }


def _tool_get_market_temperature(params: dict) -> dict:
    """市场温度计概览：综合温度 / 短中长期档位 / 结论 / 数据新鲜度。"""
    overview = TemperatureService.get_overview()
    composites = overview.get('composites') or {}
    return {
        'composite_temperature': composites.get('composite_temperature'),
        'temperature_bands': composites.get('temperature_bands'),
        'conclusion': overview.get('conclusion'),
        'freshness': overview.get('freshness'),
        'updated_at': overview.get('updated_at'),
    }


def _tool_get_watchlist_overview(params: dict) -> dict:
    """自选首页摘要：置顶与持仓标的最新价 / 涨跌幅 / 持仓市值（最多 5 条）。"""
    with database.get_session() as db:
        items = build_home_summary(db, family_id=_server_family_id(params))
    return {'items': _jsonable(items)}


register_tool('get_assets_overview', _tool_get_assets_overview)
register_tool('get_portfolio_performance', _tool_get_portfolio_performance)
register_tool('get_portfolio_vs_benchmark', _tool_get_portfolio_vs_benchmark)
register_tool('list_position_pnl', _tool_list_position_pnl)
register_tool('get_trading_behavior', _tool_get_trading_behavior)
register_tool('get_return_attribution', _tool_get_return_attribution)
register_tool('get_fund_nav', _tool_get_fund_nav)
register_tool('get_market_temperature', _tool_get_market_temperature)
register_tool('get_watchlist_overview', _tool_get_watchlist_overview)


# 工具元信息：模型据此选工具，代码据此校验参数。
# family_id 只出现在 properties、不进 required——它是服务端注入字段，
# 模型/前端提供也无效（会被覆盖）；required 里放它会让离线直调误报缺参。
TOOLS_METADATA = [
    {
        'name': 'get_assets_overview',
        'description': '获取家庭资产总览：总资产/总负债/净资产/已实现与未实现盈亏（单位：元）。'
        '当用户问「我有多少资产」「净资产多少」「负债多少」这类**存量**问题时使用。'
        '本工具的盈亏是账面存量（已实现+未实现之和），不做时间加权；'
        '问「赚了多少 / 收益率 / 年化」时用 get_portfolio_performance（XIRR 口径），不要用本工具',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
            },
        },
    },
    {
        'name': 'get_portfolio_performance',
        'description': '计算整个投资组合的年化收益率 XIRR：总投入/当前市值/总收益（单位：元）。'
        '当用户问「赚了多少钱」「收益率多少」「年化多少」「总共赚了多少」时使用——'
        '凡问法里带「赚 / 收益 / 收益率」的，优先本工具；'
        '问「我有多少资产 / 净资产 / 负债」用 get_assets_overview（那是资产存量总览，不是收益口径）',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
                'include_cash_equivalents': {
                    'type': 'boolean',
                    'description': '是否把现金/货基/逆回购并入分母，默认 false（仅投资类资产）',
                },
            },
        },
    },
    {
        'name': 'get_portfolio_vs_benchmark',
        'description': '组合同期基准对比：组合区间收益、基准（默认沪深300）同期涨跌幅、'
        '超额（百分点）、组合与基准最大回撤、日收益相关系数。当用户问「我跑赢沪深300了吗」'
        '「今年比大盘好还是差」「收益是本事还是市场给的」时使用。'
        '返回 available=false 时必须如实告知口径不可用及缺口区间，不得用近似值代替；'
        'unavailable_reason=no_baseline 表示区间起点时账户还没有资产（收益率无分母），'
        '此时应建议用户指定一个更晚的起始日期',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
                'start_date': {
                    'type': 'string',
                    'pattern': r'^\d{4}-\d{2}-\d{2}$',
                    'description': '区间起始日 YYYY-MM-DD，缺省为全期（最早一笔流水确认日）',
                },
                'end_date': {
                    'type': 'string',
                    'pattern': r'^\d{4}-\d{2}-\d{2}$',
                    'description': '区间结束日 YYYY-MM-DD，缺省为今日',
                },
                'benchmark': {
                    'type': 'string',
                    'enum': sorted(BENCHMARK_INDICES),
                    'description': '基准指数代码，缺省沪深300（000300.SH）。'
                    '可选值：' + '、'.join(f'{code}={name}' for code, name in sorted(BENCHMARK_INDICES.items())),
                },
            },
        },
    },
    {
        'name': 'list_position_pnl',
        'description': '逐持仓盈亏明细：列出当前每个持仓的成本/市值/盈亏额（元）与盈亏率（%），'
        '按盈亏率从高到低排序。当用户问「我哪些持仓在亏钱」「亏得最多的是哪只」「逐个持仓的盈亏」'
        '等需要逐持仓（而非组合汇总）盈亏的问题时使用',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
            },
        },
    },
    {
        'name': 'get_trading_behavior',
        'description': '交易行为画像：平均持有天数与 25/50/75 分位、区间买卖笔数与买卖比、'
        '换手率、连续加仓次数、割肉后回补次数、买入时点价格分位均值。'
        '当用户问「我平均一只基金拿多久」「我是不是爱加仓/爱割肉回补」「我换手高不高」'
        '「我是不是跌了才买」等操作习惯问题时使用。只给客观统计，不做好坏评价',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
                'start_date': {
                    'type': 'string',
                    'pattern': r'^\d{4}-\d{2}-\d{2}$',
                    'description': '统计窗口起始日 YYYY-MM-DD，缺省为全期',
                },
                'end_date': {
                    'type': 'string',
                    'pattern': r'^\d{4}-\d{2}-\d{2}$',
                    'description': '统计窗口结束日 YYYY-MM-DD，缺省为今日',
                },
                'symbol': {
                    'type': 'string',
                    'description': '限定单个标的代码，缺省统计全部标的',
                },
            },
        },
    },
    {
        'name': 'get_return_attribution',
        'description': '收益贡献归因：把区间收益额拆到每个标的（或每个账户），给出每行'
        '收益额（元）与对区间总收益的贡献占比（%，各行相加≈100），按贡献绝对值降序。'
        '当用户问「我这些年赚的钱主要是哪几只赚的」「亏损里最大一块是哪个」「收益都来自'
        '哪个账户」等需要占比（而非逐行绝对盈亏）的问题时使用；只看单只赚亏多少用 '
        'list_position_pnl。缺省区间为全期',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
                'start_date': {
                    'type': 'string',
                    'pattern': r'^\d{4}-\d{2}-\d{2}$',
                    'description': '区间起始日 YYYY-MM-DD，缺省为全期（最早一笔流水确认日）',
                },
                'end_date': {
                    'type': 'string',
                    'pattern': r'^\d{4}-\d{2}-\d{2}$',
                    'description': '区间结束日 YYYY-MM-DD，缺省为今日',
                },
                'dimension': {
                    'type': 'string',
                    'enum': ['instrument', 'account'],
                    'description': '归因维度：instrument=按标的（默认），account=按账户聚合',
                },
            },
        },
    },
    {
        'name': 'get_fund_nav',
        'description': '查询基金最新单位净值与净值日期（只读本地已同步数据，支持多只批量）',
        'parameters': {
            'type': 'object',
            'properties': {
                'fund_codes': {
                    'type': 'array',
                    'items': {'type': 'string', 'pattern': r'^\d{6}$'},
                    'description': '基金代码列表，6 位数字字符串，如 ["110011"]',
                },
            },
            'required': ['fund_codes'],
        },
    },
    {
        'name': 'get_market_temperature',
        'description': '获取市场温度计概览：综合温度、短/中/长期档位、结论副文案与数据新鲜度'
        '（数据最新日期 / 距今天数 / 是否过期）。短期档 temperature_bands.short 即韭圈儿恐惧贪婪指数'
        '（贪恐指数）：0-100，高=贪婪、低=恐惧，返回里名称显示为「短期情绪」；'
        '问市场情绪、贪恐 / 恐惧贪婪指数、数据是否已更新到最新日期时使用',
        'parameters': {'type': 'object', 'properties': {}},
    },
    {
        'name': 'get_watchlist_overview',
        'description': '获取自选列表首页摘要：置顶与持仓标的的最新价/涨跌幅/持仓市值（最多 5 条）',
        'parameters': {
            'type': 'object',
            'properties': {
                'family_id': {
                    'type': 'integer',
                    'description': '家庭 id（服务端自动注入，调用方无需提供）',
                },
            },
        },
    },
]


# 类型检查表：schema type -> 断言函数（integer 显式排除 bool，Python 里 bool 是 int 子类）
_TYPE_CHECKS: Dict[str, Callable[[Any], bool]] = {
    'string': lambda v: isinstance(v, str),
    'integer': lambda v: isinstance(v, int) and not isinstance(v, bool),
    'number': lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    'boolean': lambda v: isinstance(v, bool),
    'array': lambda v: isinstance(v, list),
    'object': lambda v: isinstance(v, dict),
}


def _validate_value(key: str, value: Any, spec: dict) -> None:
    """按单个参数的 schema 校验值（类型 / enum / pattern / 数组元素递归）。"""
    check = _TYPE_CHECKS.get(spec.get('type', ''))
    if check is not None and not check(value):
        raise ValueError(f'参数 {key} 类型应为 {spec.get("type")}')
    if 'enum' in spec and value not in spec['enum']:
        raise ValueError(f'参数 {key}={value} 不在允许值 {spec["enum"]}')
    if 'pattern' in spec and not re.fullmatch(spec['pattern'], str(value)):
        raise ValueError(f'参数 {key}={value} 不匹配格式 {spec["pattern"]}')
    if isinstance(value, list) and isinstance(spec.get('items'), dict):
        for i, item in enumerate(value):
            _validate_value(f'{key}[{i}]', item, spec['items'])


def _validate_params(tool_name: str, params: Any) -> None:
    """按 TOOLS_METADATA 校验参数；非法即抛 ValueError（由 run 捕获为 error）。"""
    meta = next((t for t in TOOLS_METADATA if t['name'] == tool_name), None)
    if not meta:
        raise ValueError(f'未知工具: {tool_name}')
    props = meta['parameters'].get('properties', {})
    required = meta['parameters'].get('required', [])
    params = params or {}
    if not isinstance(params, dict):
        raise ValueError('params 必须为对象')
    for r in required:
        if r not in params:
            raise ValueError(f'缺少必填参数: {r}')
    for k, v in params.items():
        if k not in props:
            raise ValueError(f'未知参数: {k}')
        _validate_value(k, v, props[k])


class ToolExecutor:
    """工具执行原子刀：P1 覆盖 → schema 校验 → 派发 → 结构化结果（不崩、不重试）。"""

    @staticmethod
    def run(name: str, params: Any, server_ctx: Optional[dict] = None) -> dict:
        """执行工具，返回 {status:'success'|'error', data|msg}。

        server_ctx：服务端权威上下文（如 {'family_id': int}），在 schema 校验前
        覆盖同名候选值——保证「进工具的 scope 字段只可能是服务端给的值」。
        """
        started = time.monotonic()
        try:
            candidate: Any = params if isinstance(params, dict) else (params or {})
            merged = apply_server_context(name, candidate, server_ctx or {})
            _validate_params(name, merged)
            func = _FUNCTION_MAP.get(name)
            if not func:
                logger.warning(
                    '[agent.tool] fail name={} reason=未注册 elapsed={:.2f}s',
                    name,
                    time.monotonic() - started,
                )
                return {'status': 'error', 'msg': f'未注册工具: {name}'}
            data = func(merged)
            logger.info('[agent.tool] ok name={} elapsed={:.2f}s', name, time.monotonic() - started)
            return {'status': 'success', 'data': data}
        except Exception as e:  # noqa: BLE001  兜底：工具内部异常不让 AgentLoop 崩
            logger.warning(
                '[agent.tool] fail name={} params={} elapsed={:.2f}s err={}',
                name,
                params,
                time.monotonic() - started,
                e,
            )
            return {'status': 'error', 'msg': str(e)}


__all__ = ['TOOLS_METADATA', 'ToolExecutor', 'apply_server_context', 'register_tool']
