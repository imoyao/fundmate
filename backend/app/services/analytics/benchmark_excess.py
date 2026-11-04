# -*- coding: utf-8 -*-
# Author : imoyao
"""#2134 账户/组合区间收益 vs 基准指数超额收益（账本对齐-D）。

用户打开账户/组合详情要回答的是：「这段时间我赚了 X%，同期沪深300 涨了 Y%，
超额 Z%」——记账软件里「收益是市场给的还是自己选的」的唯一入口。

## 三条口径（与 docs/spec/data-model.md「同期口径」一节互为镜像，改一处须同步另一处）

1. **scope 区间收益率 `range_rate`**：一律复用 `pnl_calendar.build_daily_pnl_series`
   （区间盈亏 / 区间前一天净资产，单位 %）——**唯一口径，前端禁止二次计算**。
   组合级 = Σ成员账户区间盈亏 ÷ Σ成员区间前一天净资产（成员各自走同一引擎，
   分母取引擎同源的 `range_baseline` 字段）；**不是**把成员收益率做平均——平均
   无视了各成员资产规模，10 万的账户跌 50% 与 1 千的账户涨 50% 平均出 +25% 是错数。
2. **指数区间涨跌幅**：`index_daily` 在 `[start, end]` 内**首、末两个可得交易日收盘**
   之比 − 1。不足 2 个点、或首/末点距区间边界超过容差（7 天，见
   `_COVERAGE_TOLERANCE_DAYS`——覆盖区间起点/终点附近的报价才算「同期」，
   否则 2015 年查 2019 年才上市的科创50 会拿 2020 年的涨幅冒充整段）→ 降级 None，
   **不造 0**。响应带 `bench_start_date` / `bench_end_date` 供复核对账。
3. **超额 `excess_return` = range_rate − 指数区间涨跌幅**（百分点）；任一为 None
   → None。所有算不出的都带 `*_reason` 落原因，前端显示「—」。

## 基准选取（`resolve_benchmark_code`，复核实施要点 1/3）

- scope 持仓含非 CN_A 市场（CN_HK/US/CRYPTO 及任何未识别值）→ 降级
  `non_cn_a_holdings`——`BENCHMARK_INDICES` 只有 A 股宽基，拿沪深300 代表
  港美持仓是造数；
- `Portfolio.benchmark` 非空（字段注释的存储惯例如 `CSI300`）→ 按
  code / 中文名 / 别名归一到 `BENCHMARK_INDICES`；**认不出的（恒生/标普…）
  → 降级 `unrecognized_benchmark`，不顶替**——`BENCHMARK_INDICES` 是映射唯一
  真相源，本模块 `_BENCHMARK_TEXT_ALIASES` 只是 text→code 的归一化糖，
  归一结果必须落在 `BENCHMARK_INDICES`，**不是第二份指数映射表**；
- 空（组合未设 / 账户级无此字段）→ 默认 `000300.SH` 沪深300。

数据准入（AGENTS.md 数据策略四问）：零新增表、零新增外部请求——指数序列复用
`index_daily_job` 已同步的 `index_daily`（公开市场数据、已在本地库），与
analytics 包纪律 1「不引入**外部**数据源」不冲突（本卡复核结论同）。
"""

import datetime as dt
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.domains.indices.models import IndexDaily
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position
from app.services.bias.constants import BENCHMARK_INDICES
from app.services.pnl_calendar import build_daily_pnl_series

DEFAULT_BENCHMARK_CODE = '000300.SH'
# 非 A股市场：宽基表没有对应序列 ⇒ 诚实降级，不拿沪深300 顶替（复核实施要点 3）。
# 未知/历史形态一律落进本集合的方向（未识别 ⇒ 降级），宁可降级不造数。
NON_CN_A_MARKETS = frozenset({'CN_HK', 'US', 'CRYPTO'})
# scope 市场判定中视为「A 股可比」的值：规范形态 CN_A；''/NULL = 现金类/无市场属性。
A_SHARE_MARKERS = frozenset({'CN_A', '', None})
# text → code 归一化糖：只认 BENCHMARK_INDICES 已有的 code（CSI300/CSI500 是
# `Portfolio.benchmark` 字段注释给出的存储惯例）。归一结果必须 ∈ BENCHMARK_INDICES。
_BENCHMARK_TEXT_ALIASES: Dict[str, str] = {
    'CSI300': '000300.SH',
    'HS300': '000300.SH',
    'CSI500': '000905.SH',
    'ZZ500': '000905.SH',
    'CSI1000': '000852.SH',
    'ZZ1000': '000852.SH',
}
# 区间覆盖容差：指数首/末报价须落在 [start, start+TOL] / [end-TOL, end]，
# 否则视为「区间起点/终点无该指数数据」（见模块 docstring 口径 2）。
_COVERAGE_TOLERANCE_DAYS = 7


def _normalize_benchmark_text(text: Optional[str]) -> Optional[str]:
    """把用户/系统存的基准文本归一到 `BENCHMARK_INDICES` 的 code；认不出回 None。"""
    t = (text or '').strip()
    if not t:
        return None
    upper = t.upper()
    for code, name in BENCHMARK_INDICES.items():
        if upper == code.upper() or t == name:
            return code
    # 裸码：'000300' / '000300.sh' → '000300.SH'
    bare = upper.split('.')[0]
    for code in BENCHMARK_INDICES:
        if code.split('.')[0] == bare:
            return code
    alias = _BENCHMARK_TEXT_ALIASES.get(upper) or _BENCHMARK_TEXT_ALIASES.get(t)
    # 归一结果必须是真相源里存在的 code——别名表写了真相源没有的码也视为认不出
    return alias if alias in BENCHMARK_INDICES else None


def _scope_ledger_ids(
    db: Session,
    family_id: int,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> Optional[List[int]]:
    """scope 涉及的账户 id 列表；family 级回 None（= 全 family，不筛）。"""
    if ledger_id is not None:
        return [ledger_id]
    if portfolio_id is not None:
        rows = db.query(Ledger.id).filter(Ledger.family_id == family_id, Ledger.portfolio_id == portfolio_id).all()
        return [r[0] for r in rows]
    return None


def resolve_benchmark_code(
    db: Session,
    family_id: int,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
    benchmark_text: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """解析 scope 的基准指数 code。回 `(code, None)` 或 `(None, reason)`。

    reason 枚举：`non_cn_a_holdings`（含港美/未识别市场持仓）、
    `unrecognized_benchmark`（用户填了宽基表认不出的基准）。
    """
    ledger_ids = _scope_ledger_ids(db, family_id, ledger_id, portfolio_id)
    q = db.query(Position.market).filter(Position.family_id == family_id)
    if ledger_ids is not None:
        if not ledger_ids:
            return None, 'no_members'
        q = q.filter(Position.ledger_id.in_(ledger_ids))
    markets = {m for (m,) in q.distinct().all()}
    if not markets <= A_SHARE_MARKERS:
        return None, 'non_cn_a_holdings'
    if benchmark_text and benchmark_text.strip():
        code = _normalize_benchmark_text(benchmark_text)
        if code is None:
            return None, 'unrecognized_benchmark'
        return code, None
    return DEFAULT_BENCHMARK_CODE, None


def _index_close_rows(db: Session, index_code: str, start: dt.date, end: dt.date):
    """`[start, end]` 内可得收盘点（按日期升序）。

    单值（`interval_benchmark_return`）与逐日曲线共用这一处取数，
    避免两处 filter 各自演化出「一个要 not null、一个不要」的漂移。
    """
    return (
        db.query(IndexDaily.trade_date, IndexDaily.close)
        .filter(
            IndexDaily.index_code == index_code,
            IndexDaily.trade_date >= start,
            IndexDaily.trade_date <= end,
            IndexDaily.close.isnot(None),
        )
        .order_by(IndexDaily.trade_date)
        .all()
    )


def interval_benchmark_return(
    db: Session,
    index_code: str,
    start: dt.date,
    end: dt.date,
) -> Dict[str, Any]:
    """指数在 `[start, end]` 的区间涨跌幅（%）+ 实际取数首末日期。

    降级一律回 `range_return=None` + `reason`（不借 0 兜底）：
    - `index_insufficient_data`：区间内不足 2 个可得收盘点；
    - `coverage_start_insufficient` / `coverage_end_insufficient`：首/末点距
      区间边界超过 `_COVERAGE_TOLERANCE_DAYS`（该指数在区间边界没有报价，
      涨跌幅覆盖的不是「同期」整段）。
    """
    rows = _index_close_rows(db, index_code, start, end)
    name = BENCHMARK_INDICES.get(index_code, index_code)

    def _result(range_return, reason, first=None, last=None):
        return {
            'code': index_code,
            'name': name,
            'range_return': range_return,
            'bench_start_date': first.isoformat() if first else None,
            'bench_end_date': last.isoformat() if last else None,
            'reason': reason,
        }

    if len(rows) < 2:
        return _result(None, 'index_insufficient_data')
    first_date, first_close = rows[0]
    last_date, last_close = rows[-1]
    if (first_date - start).days > _COVERAGE_TOLERANCE_DAYS:
        return _result(None, 'coverage_start_insufficient', first_date, last_date)
    if (end - last_date).days > _COVERAGE_TOLERANCE_DAYS:
        return _result(None, 'coverage_end_insufficient', first_date, last_date)
    if not first_close or first_close <= 0:
        return _result(None, 'index_insufficient_data', first_date, last_date)
    rate = round((float(last_close) / float(first_close) - 1) * 100, 2)
    return _result(rate, None, first_date, last_date)


def _empty_scope_result(
    scope: str,
    ledger_id: Optional[int],
    portfolio_id: Optional[int],
    start: dt.date,
    end: dt.date,
    reason: str,
) -> Dict[str, Any]:
    """scope 收益算不出时的统一骨架（benchmark 照常解析，excess 恒 None）。"""
    return {
        'scope': scope,
        'ledger_id': ledger_id,
        'portfolio_id': portfolio_id,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'range_rate': None,
        'range_pnl': None,
        'range_baseline': None,
        'range_reason': reason,
        'benchmark': None,
        'excess_return': None,
        'series': [],
    }


def _build_cum_series(
    db: Session,
    payload_by_id: Dict[int, dict],
    range_baseline: Optional[float],
    code: Optional[str],
    bench: Dict[str, Any],
    start: dt.date,
    end: dt.date,
) -> List[Dict[str, Any]]:
    """逐日累计收益曲线（#2685；账户 / 组合同一份，**末点 ≡ 卡片上的单值**）。

    - **分母固定**为区间前一日净资产（`range_baseline`），分子是逐日累计盈亏：
      `cum = 累计盈亏 / |baseline| * 100`，故末点 ≡ `range_rate`。刻意**不用**
      「日收益复利连乘」——那会让末点与单值差几个 bp，被当成 bug 反复解释。
    - 组合级：成员逐日 `daily_pnl` 按日期求和（某成员该日缺值就跳过，**不补 0**），
      与 `range_pnl = Σ month_total` 同源。
    - 基准线只在 `bench['range_return']` 可算时填（与卡片同判据）：未识别 / 覆盖不足
      ⇒ `benchmark_cum_pct` 全 None，前端只画组合线并给降级文案，
      **不画一条 0 线冒充基准**。
    """
    if not payload_by_id or not range_baseline:
        return []
    denom = abs(float(range_baseline))
    if not denom:
        return []

    pnl_by_date: Dict[str, float] = {}
    for payload in payload_by_id.values():
        for day in payload.get('days') or []:
            if day.get('daily_pnl') is None:
                continue
            key = day['date']
            pnl_by_date[key] = pnl_by_date.get(key, 0.0) + float(day['daily_pnl'])
    if not pnl_by_date:
        return []

    series: List[Dict[str, Any]] = []
    acc = 0.0
    for date_key in sorted(pnl_by_date):
        acc += pnl_by_date[date_key]
        series.append({'date': date_key, 'scope_cum_pct': round(acc / denom * 100, 2), 'benchmark_cum_pct': None})

    if code is None or bench.get('range_return') is None:
        return series

    rows = _index_close_rows(db, code, start, end)
    if not rows or not rows[0][1]:
        return series
    base = float(rows[0][1])
    bench_by_date = {
        trade_date.isoformat(): round((float(close) / base - 1) * 100, 2) for trade_date, close in rows if close
    }
    for point in series:
        # 基准当日无报价（停牌 / 未收录）留 None 断线，不用前值伪装成「走平」
        point['benchmark_cum_pct'] = bench_by_date.get(point['date'])
    return series


def build_scope_excess(
    db: Session,
    family_id: int,
    start_date: str,
    end_date: str,
    ledger_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> Dict[str, Any]:
    """区间收益 vs 基准指数：一个作用域（family / ledger / portfolio）一份结果。

    ValueError：日期格式非法、区间倒挂、ledger_id 与 portfolio_id 同时传、
    portfolio_id 指向的组合不存在（端点层映射 400）。
    """
    if ledger_id is not None and portfolio_id is not None:
        raise ValueError('ledger_id 与 portfolio_id 不能同时传')
    try:
        start = dt.date.fromisoformat(str(start_date))
        end = dt.date.fromisoformat(str(end_date))
    except (ValueError, TypeError) as e:
        raise ValueError(f'日期格式须为 YYYY-MM-DD: {e}') from e
    if start > end:
        raise ValueError('start_date 不能晚于 end_date')

    scope = 'portfolio' if portfolio_id is not None else ('ledger' if ledger_id is not None else 'family')

    benchmark_text = None
    portfolio: Optional[Portfolio] = None
    if portfolio_id is not None:
        portfolio = (
            db.query(Portfolio)
            .filter(Portfolio.id == portfolio_id, Portfolio.family_id == family_id, Portfolio.is_deleted.is_(False))
            .first()
        )
        if portfolio is None:
            raise ValueError('组合不存在或已删除')
        benchmark_text = portfolio.benchmark

    # ── scope 区间收益（唯一口径 = build_daily_pnl_series）──
    if portfolio is not None:
        member_ids = _scope_ledger_ids(db, family_id, portfolio_id=portfolio_id) or []
        if not member_ids:
            payload_by_id: Dict[int, dict] = {}
            range_rate = None
            range_pnl = None
            range_baseline = None
            range_reason = 'no_members'
        else:
            payload_by_id = {
                lid: build_daily_pnl_series(db, family_id, start_date, end_date, ledger_id=lid) for lid in member_ids
            }
            # 分母任一成员取不到 ⇒ 组合基线不完整，整组不报（引擎对单账户同规则：
            # baseline None ⇒ rate None，不借 0 兜底）。
            baselines = [p['range_baseline'] for p in payload_by_id.values()]
            range_pnl = round(sum(p['month_total'] for p in payload_by_id.values()), 2)
            has_computable = any(d['daily_pnl'] is not None for p in payload_by_id.values() for d in p['days'])
            if any(b is None for b in baselines):
                range_rate = None
                range_baseline = None
                range_reason = 'baseline_missing'
            else:
                range_baseline = round(sum(b for b in baselines if b is not None), 2)
                if range_baseline == 0:
                    range_rate = None
                    range_reason = 'no_baseline'
                elif not has_computable:
                    range_rate = None
                    range_reason = 'no_computable_day'
                else:
                    range_rate = round(range_pnl / abs(range_baseline) * 100, 2)
                    range_reason = None
    else:
        payload = build_daily_pnl_series(db, family_id, start_date, end_date, ledger_id=ledger_id)
        payload_by_id: Dict[int, dict] = {0: payload}  # 单一作用域也装进同一结构，曲线只写一份
        range_rate = payload['range_rate']
        range_pnl = payload['month_total']
        range_baseline = payload['range_baseline']
        if range_rate is None:
            total_positions = payload.get('coverage', {}).get('total_positions', 0)
            range_reason = 'no_position' if total_positions == 0 else 'not_computable'
        else:
            range_reason = None

    # ── 基准解析 + 指数区间涨跌幅 ──
    code, bench_reason = resolve_benchmark_code(
        db, family_id, ledger_id=ledger_id, portfolio_id=portfolio_id, benchmark_text=benchmark_text
    )
    if code is not None:
        bench = interval_benchmark_return(db, code, start, end)
    else:
        bench = {
            'code': None,
            'name': None,
            'range_return': None,
            'bench_start_date': None,
            'bench_end_date': None,
            'reason': bench_reason,
        }

    excess = None
    if range_rate is not None and bench['range_return'] is not None:
        excess = round(range_rate - bench['range_return'], 2)

    series = _build_cum_series(db, payload_by_id, range_baseline, code, bench, start, end)

    result = {
        'scope': scope,
        'ledger_id': ledger_id,
        'portfolio_id': portfolio_id,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'range_rate': range_rate,
        'range_pnl': range_pnl,
        'range_baseline': range_baseline,
        'range_reason': range_reason,
        'benchmark': bench,
        'excess_return': excess,
        # 逐日累计曲线（#2685）：末点 ≡ range_rate / benchmark.range_return，前端画双线用
        'series': series,
    }
    logger.info(
        '基准超额计算 scope={} 区间={}~{} range_rate={} bench={}({}) excess={}',
        scope,
        start,
        end,
        range_rate,
        bench['range_return'],
        bench['reason'] or bench['code'],
        excess,
    )
    return result
