# -*- coding: utf-8 -*-
"""策略引擎数据适配层（#2224）——把库内数据翻译成契约层要的纯数据。

边界
    - 只做「取数 + 单位换算 + 排序」，**不做任何策略判断**（判断在 strategy 层）；
    - 金额 / 份额换算一律走 `core.money.Money`，本模块不硬编码 10000 / 100；
    - **不跨域 JOIN**：`daily_worth` / `price_history` 属 market 域，
      `positions` / `transactions` 属 user 域，生产双库下两者不在同一会话。
      故 `market_db` 可显式注入；未注入时复用同一会话（本地单库），
      两种情况都是**分步查询**，不写任何跨表 join。

单位口径（沿用本仓既有约定，勿改）
    - quantity：0.0001 份 → `Money.min_unit_to_shares`
    - price：0.0001 元   → `Money.price_units_to_yuan`
    - daily_worth.unit_nav：元（Decimal，精度 6）
"""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable, Sequence

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.core.money import Money
from app.domains.funds.models import DailyWorth, Fund
from app.domains.positions.models import Position
from app.domains.price_history.models import PriceHistory
from app.domains.transactions.models import Transaction
from app.services.strategy_engine.behavior_profile import TradeRecord
from app.services.strategy_engine.contracts import SeriesPoint

#: 场内/场外都可能出现的前缀形态；取数字尾部 6 位作为基金裸码
_FUND_CODE_RE = re.compile(r'\d+')


@dataclass(frozen=True)
class HoldingRow:
    """归一化持仓（单位已换算：份 / 元）。"""

    position_id: int
    symbol: str
    name: str
    asset_type: str
    quantity: float
    avg_price: float


def extract_fund_code(symbol: str | None) -> str | None:
    """从展示形态 symbol 提取 6 位基金裸码；不足 6 位数字返回 None。

    例：`OTC:004369` → `004369`，`EXCHANGE:SZ159915` → `159915`。
    """
    if not symbol:
        return None
    digits = ''.join(_FUND_CODE_RE.findall(symbol))
    return digits[-6:] if len(digits) >= 6 else None


class DataProvider:
    """策略引擎的取数出口。策略层永远不直接碰 Session。"""

    def __init__(self, db: Session, market_db: Session | None = None) -> None:
        self.db = db
        self.market_db = market_db if market_db is not None else db
        # 请求内缓存（#2639）
        #     DataProvider 由视图按**请求**新建（`behavior_profiles` 内一次性传入），
        #     故实例级 dict 天然是请求作用域，不存在跨请求读到陈旧数据的问题；
        #     也正因如此才不引入进程级/外部缓存——那需要失效策略，收益不值。
        self._fund_type_cache: dict[str, int | None] = {}
        self._peer_codes_cache: dict[int, tuple[str, ...] | None] = {}
        self._peer_returns_cache: dict[tuple[int, date, int], tuple[float, ...] | None] = {}

    # ── 行情 ──

    def nav_series(
        self,
        symbol: str,
        limit: int = 260,
        start: date | None = None,
    ) -> tuple[SeriesPoint, ...]:
        """取标的的净值 / 收盘价序列（升序）。

        `start`（#2637）
            - **默认 `None`**：返回**最近 `limit` 条**。诊断路径用——趋势策略只需近端，
              260 个净值日足够，不必读全量；
            - **给定日期**：返回 `date >= start` 的**全量**，此时 `limit` 不生效。
              行为画像用——「买入后第 h 个净值日」的定位要求序列**覆盖最早买入日**，
              取近端会把窗口整体错位（见 `forward_return_metrics` 的不变式说明）。

        先查场外 `daily_worth`（基金净值），再回落场内 `price_history`（收盘价）。
        两者都是**分步查询**，无 join。取不到返回空元组——由策略层降级成 WATCH，
        本层不补零、不伪造日期。
        """
        code = extract_fund_code(symbol)
        if code:
            query = self.market_db.query(DailyWorth.date, DailyWorth.unit_nav).filter(DailyWorth.fund_code == code)
            if start is None:
                rows = list(reversed(query.order_by(DailyWorth.date.desc()).limit(limit).all()))
            else:
                rows = query.filter(DailyWorth.date >= start).order_by(DailyWorth.date.asc()).all()
            points = tuple(SeriesPoint(date=r[0], value=float(r[1])) for r in rows if r[0] and r[1] is not None)
            if points:
                return points

        query = self.market_db.query(PriceHistory.trade_date, PriceHistory.close).filter(PriceHistory.symbol == symbol)
        if start is None:
            rows = list(reversed(query.order_by(PriceHistory.trade_date.desc()).limit(limit).all()))
        else:
            rows = query.filter(PriceHistory.trade_date >= start).order_by(PriceHistory.trade_date.asc()).all()
        return tuple(SeriesPoint(date=r[0], value=float(r[1])) for r in rows if r[0] and r[1] is not None)

    # ── 同类分组（#2382 buy_percentile 用） ──

    def fund_type_id_of(self, fund_code: str) -> int | None:
        """基金小类 id（`funds.fund_type_id`）；查不到返回 None。

        分步查询：funds 表在 market 域，与 daily_worth 同库，无 join。
        请求内按 fund_code 缓存（#2639）：画像逐标的、逐买入日都会问一次同一个代码。
        """
        if fund_code in self._fund_type_cache:
            return self._fund_type_cache[fund_code]
        row = self.market_db.query(Fund.fund_type_id).filter(Fund.fund_code == fund_code).first()
        value = int(row[0]) if row and row[0] is not None else None
        self._fund_type_cache[fund_code] = value
        return value

    def _peer_codes_of(self, type_id: int) -> tuple[str, ...] | None:
        """该小类下全部基金裸码（按代码升序）；无则 None。请求内按 type 缓存（#2639）。"""
        if type_id in self._peer_codes_cache:
            return self._peer_codes_cache[type_id]
        codes = tuple(
            sorted(
                r[0] for r in self.market_db.query(Fund.fund_code).filter(Fund.fund_type_id == type_id).all() if r[0]
            )
        )
        self._peer_codes_cache[type_id] = codes or None
        return self._peer_codes_cache[type_id]

    def peer_year_returns(
        self,
        fund_code: str,
        as_of: date,
        window_days: int = 365,
    ) -> tuple[float, ...] | None:
        """单个 `(基金, 买入日)` 的同类区间收益集合；语义见 `peer_year_returns_for`。

        存在的意义只是给「只要一个键」的调用方一个短接口——实现**委托**给批量版，
        不另写一套 SQL。两份实现就是两份口径，迟早分叉。
        """
        return self.peer_year_returns_for([(fund_code, as_of)], window_days).get((fund_code, as_of))

    def peer_year_returns_for(
        self,
        requests: Iterable[tuple[str, date]],
        window_days: int = 365,
    ) -> dict[tuple[str, date], tuple[float, ...] | None]:
        """批量取「同类近 window_days 的区间收益率集合」，键为 `(基金裸码, 买入日)`。

        用于 `buy_percentile`（#2382）：判断买入时点该基金在同类中的分位。

        口径（与 #2382 一致，优化不得改动）
            - 每只同类基金取窗口内**最早**与**最晚**两条净值算区间收益
              （不要求同一起止日，诚实按各自可得数据）；
            - 窗口内无净值 / 起点为 0 的基金不计入（宁缺勿假）；
            - 返回集合**含自身**（`percentile_rank` 的中位秩口径要求 peers 含自身）；
            - 自身不在窗口内（新基金）仍返回同类集合，由调用方降级。

        为什么按类型归并、按「并集区间」一次扫（#2639 二次优化）
            计算只依赖 `(fund_type_id, as_of)`，与是哪只基金无关；而画像一次请求里
            同一类型往往有几十个买入日（真库家庭 1：type 1 有 47 个）。逐个买入日各扫
            一遍 365 天窗口，等于把高度重叠的数据反复读。真库实测（家庭 1）：

            | 类型 | 买入日 | 逐窗口合计行数 | 并集行数 | 重复倍数 |
            |---|---|---|---|---|
            | 1 | 47 | 2,636,977 | 253,794 | 10.4x |
            | 3 | 29 | 589,890 | 41,499 | 14.2x |
            | 全请求 | 115 | 3,485,249 | 386,105 | 9.0x |

            故先按类型求并集区间 `[min(as_of) - window_days, max(as_of)]` 一次取回，
            再用二分定位每个 `as_of` 的首末点。逐 `as_of` 的取值口径与「各扫一遍窗口」
            逐步等价，换掉的只是重复扫描。

        为什么把首末判定从 SQL 挪回 Python（与上一版 `GROUP BY` 下推相反）
            上一版的下推本身是对的（返回行数 11,214 → 52），但它天生只能服务**单个**
            `as_of`：「每个 as_of 各自的首末日期」在 SQLite 里要么写成 as_of × 基金
            的交叉聚合（47 × 1,381 次索引区间扫，退回到原成本），要么靠窗口函数
            （实测更慢，内层仍取全量）。并集区间取回后，二分是 O(log n)，
            比让 SQL 再扫 47 遍便宜一个数量级。

        为什么用 `text()` 而不是 ORM 列表达式（本函数最反直觉的一处，勿改回）
            这里要取回十万量级的行。ORM 列表达式会给 `date` / `unit_nav` 挂结果
            处理器——`Date` 走日期解析、`Numeric` 走 `Decimal`——实测 253,794 行
            1.76s，其中 **0.8s 纯花在这两个转换上**（同一 SQL 的裸游标只要 0.51s）。
            `text()` 不带列类型，取回的就是库里的原样值（`date` 为 ISO 字符串、
            `unit_nav` 为文本数字），既省掉转换，也正好是二分需要的比较形态：
            ISO 日期的字典序等于时间序。库内实测 678,881 行 `date` 全为
            `YYYY-MM-DD`（长度 10）、净值无 NULL，故字符串比较与日期比较同义。
        """
        grouped: dict[int | None, list[tuple[str, date]]] = {}
        for code, as_of in requests:
            grouped.setdefault(self.fund_type_id_of(code), []).append((code, as_of))

        out: dict[tuple[str, date], tuple[float, ...] | None] = {}
        for code, as_of in grouped.pop(None, []):
            out[(code, as_of)] = None  # funds 表无此代码：调用方按无同类数据降级

        for type_id, items in grouped.items():
            by_as_of = self._peer_returns_for_type(type_id, {as_of for _code, as_of in items}, window_days)
            for code, as_of in items:
                out[(code, as_of)] = by_as_of[as_of]
        return out

    def _peer_returns_for_type(
        self,
        type_id: int,
        as_ofs: set[date],
        window_days: int,
    ) -> dict[date, tuple[float, ...] | None]:
        """单个类型的批量计算：并集区间扫一次，命中的缓存键不再扫库。"""
        result: dict[date, tuple[float, ...] | None] = {}
        missing: list[date] = []
        for as_of in as_ofs:
            key = (type_id, as_of, window_days)
            if key in self._peer_returns_cache:
                result[as_of] = self._peer_returns_cache[key]
            else:
                missing.append(as_of)
        if not missing:
            return result

        peer_codes = self._peer_codes_of(type_id)
        if not peer_codes:
            for as_of in missing:
                self._peer_returns_cache[(type_id, as_of, window_days)] = None
                result[as_of] = None
            return result

        rows = self.market_db.execute(
            text(
                'SELECT fund_code, date, unit_nav FROM daily_worth '
                'WHERE fund_code IN :codes AND date >= :lo AND date <= :hi '
                'AND unit_nav IS NOT NULL ORDER BY fund_code, date'
            ).bindparams(bindparam('codes', expanding=True)),
            {
                'codes': list(peer_codes),
                'lo': (min(missing) - timedelta(days=window_days)).isoformat(),
                'hi': max(missing).isoformat(),
            },
        )
        # 结果已按 (fund_code, date) 升序：**逐只基金流式聚合**，算完就丢。
        # 不先把全部基金存进 dict 再按 as_of 遍历——那样真库 type 1 要常驻
        # 25 万条日期/净值（实测峰值 24MB），流式只需一只基金的数组 + 各 as_of 的
        # 累加器（实测 1.5MB），且更快（少一次 dict 查找/行）。
        bounds = [(as_of, (as_of - timedelta(days=window_days)).isoformat(), as_of.isoformat()) for as_of in missing]
        buckets: dict[date, list[float]] = {as_of: [] for as_of in missing}
        days: list[str] = []
        navs: list[float] = []
        current: str | None = None

        def collect() -> None:
            """把当前这只基金在**各个 as_of 窗口**内的首末净值折算成收益率。"""
            for as_of, lower, upper in bounds:
                first_at = bisect_left(days, lower)  # 窗口内最早一条
                last_at = bisect_right(days, upper) - 1  # 窗口内最晚一条
                if first_at > last_at:
                    continue
                first = navs[first_at]
                if first == 0:  # 起点为 0 无法算收益，不计入（宁缺勿假）
                    continue
                buckets[as_of].append((navs[last_at] - first) / first * 100.0)

        for code, day, nav in rows:
            if code != current:
                if days:
                    collect()
                current = code
                days, navs = [], []
            days.append(day)
            navs.append(float(nav))
        if days:
            collect()

        for as_of in missing:
            bucket = tuple(buckets[as_of])
            self._peer_returns_cache[(type_id, as_of, window_days)] = bucket
            result[as_of] = bucket
        return result

    # ── 持仓 / 流水 ──

    def holdings(self, family_id: int) -> list[HoldingRow]:
        """当前有份额的持仓（单位已换算）。"""
        rows = (
            self.db.query(Position)
            .filter(Position.family_id == family_id, Position.quantity > 0)
            .order_by(Position.id.asc())
            .all()
        )
        return [
            HoldingRow(
                position_id=r.id,
                symbol=r.symbol or '',
                name=r.name or '',
                asset_type=r.asset_type or '',
                quantity=Money.min_unit_to_shares(r.quantity),
                avg_price=Money.price_units_to_yuan(r.avg_price),
            )
            for r in rows
        ]

    def trades(
        self,
        family_id: int,
        symbol: str | None = None,
        symbols: Iterable[str] | None = None,
    ) -> list[TradeRecord]:
        """买卖流水（FIFO 配对所需）。只取 buy / sell，其余类型（分红等）不参与行为画像。"""
        query = self.db.query(Transaction).filter(
            Transaction.family_id == family_id,
            Transaction.txn_type.in_(('buy', 'sell')),
        )
        if symbol:
            query = query.filter(Transaction.symbol == symbol)
        elif symbols:
            query = query.filter(Transaction.symbol.in_(list(symbols)))

        rows = query.order_by(Transaction.trade_date.asc(), Transaction.id.asc()).all()
        out: list[TradeRecord] = []
        for r in rows:
            day = r.trade_date.date() if r.trade_date else r.confirm_date
            if day is None:  # 无日期无法参与持有天数计算，跳过而非伪造
                continue
            out.append(
                TradeRecord(
                    symbol=r.symbol or '',
                    trade_date=day,
                    side=r.txn_type,
                    quantity=Money.min_unit_to_shares(r.quantity),
                    price=Money.price_units_to_yuan(r.price),
                )
            )
        return out

    def group_trades_by_symbol(self, trades: Sequence[TradeRecord]) -> dict[str, list[TradeRecord]]:
        grouped: dict[str, list[TradeRecord]] = {}
        for t in trades:
            grouped.setdefault(t.symbol, []).append(t)
        return grouped


def last_nav_date(points: Sequence[SeriesPoint]) -> date | None:
    return points[-1].date if points else None
