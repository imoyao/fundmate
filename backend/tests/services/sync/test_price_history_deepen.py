# -*- coding: utf-8 -*-
"""行情加深通道（#2860）：判据、写库语义、以及「不误伤」的边界。

三件事必须钉住，否则这条通道会以静态失败的方式骗人：

1. **只挑库内起点晚于应有起点的标的**。判据写反（拿 max 比、或用「库内最新日」判），
   会把 39 个已覆盖的标的每轮重抓一遍——数据没错，但请求量与耗时数倍膨胀，且日志里
   一切正常；
2. **必须整段覆盖写，不是只插前缀**。只追加前缀会让一段序列里混两代前复权锚点，
   除权日凭空多出一段涨跌（#2464 实测 -5.235pp）；
3. **取不到与已到底必须可分**。取取回 0 行记 `empty`、库里原有行不动；源侧本来就只有
   这么多（已退市转债）时记 `achieved_first` 仍晚于目标，但不报错。
"""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.jobs.price_history_job import PriceHistorySyncJob

TODAY = date(2026, 11, 3)
BASELINE = date(2021, 11, 3)  # 今天 − 5 年，即无流水标的的保底起点


def _security(db, symbol, sec_type='stock'):
    sec = Security(symbol=symbol, name=symbol, market='CN_A', type=sec_type, currency='CNY')
    db.add(sec)
    db.commit()
    return sec


def _price(db, security_id, symbol, day, close=10.0):
    db.add(
        PriceHistory(
            security_id=security_id,
            symbol=symbol,
            trade_date=day,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1000,
            adj_close=close,
            source='akshare_sina',
        )
    )
    db.commit()


def _txn(db, symbol, day, asset_type='stock'):
    from app.domains.transactions.models import Transaction

    db.add(
        Transaction(
            position_id=None,
            ledger_id=None,
            family_id=1,
            txn_type='buy',
            symbol=symbol,
            asset_type=asset_type,
            position_name=symbol,
            quantity=100,
            price=10000,
            amount=10000,
            trade_date=datetime(day.year, day.month, day.day, 10, 0, 0),
            confirm_date=day,
            status='success',
        )
    )
    db.commit()


def _bars(symbol, start, end, close=9.0):
    """逐日（简化：每 30 天一根）造出 start~end 的行情行。"""
    out = []
    day = start
    while day <= end:
        out.append(
            {
                'symbol': symbol,
                'trade_date': day,
                'open': close,
                'high': close,
                'low': close,
                'close': close,
                'volume': 1000,
                'adj_close': close,
                'source': 'akshare_sina',
            }
        )
        day += timedelta(days=30)
    return out


@pytest.fixture
def job(db):
    adapter = MagicMock()
    adapter.get_name.return_value = 'mock_akshare'
    return PriceHistorySyncJob(adapter, db)


class TestDeepenPlan:
    def test_plans_only_symbols_whose_start_is_later_than_needed(self, job, db):
        """已覆盖到保底的标的一条都不发请求；老标的发生。"""
        deep = _security(db, 'SH113649')
        fresh = _security(db, 'SZ159857')
        # 老标的：2023 买入，但库内只有 2025 之后 ⇒ 起点晚于 5 年保底
        _txn(db, 'SH113649', date(2023, 2, 17))
        _price(db, deep.id, 'SH113649', date(2025, 11, 3))
        # 新标的：库内起点早于保底 ⇒ 无需加深
        _price(db, fresh.id, 'SZ159857', date(2021, 1, 5))

        result = job.deepen(dry_run=True)

        symbols = [d['symbol'] for d in result['details']]
        assert symbols == ['SH113649']
        assert result['planned'] == 1
        assert result['skipped'] == 1
        assert result['details'][0]['stored_first'] == date(2025, 11, 3)
        assert result['details'][0]['target_start'] == BASELINE
        job.adapter.fetch_stock_price.assert_not_called()

    def test_symbol_without_transactions_still_gets_baseline(self, job, db):
        """无流水的标的（纯自选）也要补到保底——否则 5Y 档对它永远降级。"""
        sec = _security(db, 'SH600519')
        _price(db, sec.id, 'SH600519', date(2024, 1, 5))

        result = job.deepen(dry_run=True)

        assert [d['symbol'] for d in result['details']] == ['SH600519']
        assert result['details'][0]['target_start'] == BASELINE

    def test_zero_row_symbol_from_transactions_is_planned(self, job, db):
        """有流水但**零行情**的标的必须进 deepen 的默认目标（#2859）。

        它没有 `PriceHistory` 行，而此前的默认 targets 只取
        `price_history` 里已有的 symbol ⇒ 这条恰恰是最需要补的，却连一条请求
        都发不出去（清仓后持仓行被删的那批就是此形态）。
        """
        _security(db, 'SH110074', sec_type='bond')
        _txn(db, 'SH110074', date(2023, 5, 10), asset_type='bond')

        result = job.deepen(dry_run=True)

        assert [d['symbol'] for d in result['details']] == ['SH110074']
        assert result['details'][0]['stored_first'] is None
        assert result['details'][0]['target_start'] == BASELINE

    def test_no_plan_when_everything_is_covered(self, job, db):
        sec = _security(db, 'SH600519')
        _price(db, sec.id, 'SH600519', date(2020, 1, 5))

        result = job.deepen(dry_run=True)

        assert result['planned'] == 0
        assert result['details'] == []


class TestDeepenWrite:
    def test_deepened_symbol_gains_prefix_rows_and_earlier_start(self, job, db):
        """加深后库内起点前移，且总行数增加（是补齐，不是替换）。"""
        sec = _security(db, 'SH113649')
        _txn(db, 'SH113649', date(2023, 2, 17))
        for day in (date(2025, 11, 3), date(2026, 6, 3), date(2026, 11, 3)):
            _price(db, sec.id, 'SH113649', day)

        def _fetch(symbol, start_date=None, end_date=None):
            assert start_date == BASELINE, '加深必须从应有起点起抓'
            return _bars(symbol, start_date, end_date)

        job.adapter.fetch_stock_price.side_effect = _fetch

        result = job.deepen()

        assert result['deepened'] == 1
        assert result['empty'] == []
        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH113649').all()
        starts = min(r.trade_date for r in rows)
        assert starts == BASELINE
        assert len(rows) > 3, '前缀行必须真的落库，而不是被去重丢掉'
        assert result['details'][0]['achieved_first'] == BASELINE

    def test_empty_result_keeps_existing_rows_and_is_reported(self, job, db):
        """取回 0 行 ⇒ 记 `empty` 告警、库里原有行一行不动（绝不拿空当重算完成）。

        刻意**不**记 `errors`：适配器把异常也收敛成 `[]`，调用方分不清「源侧没有」与
        「这次挂了」。本机 3 个停牌/退市标的换窗口也是 0 行；把它们报成失败会让这条
        可重复执行的命令次次亮红灯。
        """
        sec = _security(db, 'SH113649')
        _txn(db, 'SH113649', date(2023, 2, 17))
        _price(db, sec.id, 'SH113649', date(2025, 11, 3))

        job.adapter.fetch_stock_price.return_value = []

        result = job.deepen()

        assert result['deepened'] == 0
        assert result['empty'] == [{'symbol': 'SH113649', 'stored_first': date(2025, 11, 3), 'target_start': BASELINE}]
        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH113649').all()
        assert [r.trade_date for r in rows] == [date(2025, 11, 3)]

    def test_source_bottomed_out_is_not_reported_at_all(self, job, db):
        """源侧只有近两年（已退市转债）⇒ 起点照实前移，既不进 empty 也不算失败。"""
        sec = _security(db, 'SH111000', sec_type='bond')
        _txn(db, 'SH111000', date(2023, 7, 21), asset_type='bond')
        _price(db, sec.id, 'SH111000', date(2025, 11, 3))

        job.adapter.fetch_stock_price.return_value = _bars('SH111000', date(2024, 6, 3), TODAY)

        result = job.deepen()

        assert result['deepened'] == 1
        assert result['empty'] == []
        detail = result['details'][0]
        assert detail['achieved_first'] == date(2024, 6, 3)
        assert detail['achieved_first'] > detail['target_start']


class TestFirstSyncWindow:
    def test_brand_new_symbol_uses_its_own_first_transaction(self, job, db):
        """首次同步不再「今天 −365」，而是首笔流水日（更早时按首笔，否则 5 年保底）。"""
        sec = _security(db, 'SH601012')
        _txn(db, 'SH601012', date(2020, 3, 2))

        start, end = job._resolve_window(
            'SH601012',
            {},  # 库内无该标的
            TODAY,
            False,
            date(2020, 3, 2),
        )

        assert start == date(2020, 2, 17)
        assert end == TODAY
        assert start < TODAY - timedelta(days=365), '不得再退回近一年'

    def test_brand_new_symbol_without_transactions_falls_back_to_baseline(self, job, db):
        """查不到流水时不退回 365 天，而是 5 年保底（5Y 档要能点开）。"""
        start, _end = job._resolve_window('SH601012', {}, TODAY, False, None)
        assert start == BASELINE
