# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 18:13
# File : test_async_backfill.py
# tests/services/test_async_backfill.py


import threading
import time
from datetime import date
from unittest.mock import patch

import pytest
from sqlalchemy import exc as sa_exc

from app.domains.funds.models import DailyWorth
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services import async_backfill
from app.services.async_backfill import _backfill_stock_price


class TestBackfillStockPrice:
    """测试股票行情异步回填"""

    def test_backfill_stock_price_success(self, db):
        """正常回填股票行情，symbol 字段正确写入"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()
        sec_id = sec.id

        mock_records = [
            {
                'trade_date': date(2024, 1, 2),
                'open': 10.0,
                'high': 10.5,
                'low': 9.8,
                'close': 10.2,
                'volume': 1000000.0,
                'symbol': 'SH601012',
            },
            {
                'trade_date': date(2024, 1, 3),
                'open': 10.2,
                'high': 10.8,
                'low': 10.1,
                'close': 10.6,
                'volume': 1200000.0,
                'symbol': 'SH601012',
            },
        ]

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.core.database.get_session') as mock_session,
        ):
            mock_adapter = mock_adapter_class.return_value
            mock_adapter.fetch_stock_price.return_value = mock_records
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 2
        assert rows[0].security_id == sec_id
        assert rows[0].symbol == 'SH601012'
        assert rows[0].close == 10.2

    def test_backfill_stock_price_filters_unknown_columns(self, db):
        """多余字段被过滤，不引发插入错误"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()

        mock_records = [
            {
                'trade_date': date(2024, 1, 2),
                'open': 10.0,
                'close': 10.2,
                'volume': 1000000.0,
                'symbol': 'SH601012',
                'unknown_col': 'should_be_filtered',
            },
        ]

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.core.database.get_session') as mock_session,
        ):
            mock_adapter_class.return_value.fetch_stock_price.return_value = mock_records
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 1
        assert rows[0].close == 10.2

    def test_backfill_stock_price_security_not_found(self, db):
        """证券不存在时静默返回，不抛异常"""
        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.core.database.get_session') as mock_session,
        ):
            mock_session.return_value = db

            _backfill_stock_price('SH999999')

            mock_adapter_class.assert_not_called()

    def test_backfill_stock_price_empty_records(self, db):
        """适配器返回空数据时不写入"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.core.database.get_session') as mock_session,
        ):
            mock_adapter_class.return_value.fetch_stock_price.return_value = []
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 0

    def test_backfill_stock_price_duplicate_handling(self, db):
        """已存在的行情数据不重复插入"""
        sec = Security(symbol='SH601012', name='隆基绿能', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()
        sec_id = sec.id

        existing = PriceHistory(
            security_id=sec_id,
            symbol='SH601012',
            trade_date=date(2024, 1, 2),
            close=10.0,
        )
        db.add(existing)
        db.commit()

        mock_records = [
            {'trade_date': date(2024, 1, 2), 'close': 10.5, 'symbol': 'SH601012'},
            {'trade_date': date(2024, 1, 3), 'close': 11.0, 'symbol': 'SH601012'},
        ]

        with (
            patch('app.services.async_backfill.AkshareAdapter') as mock_adapter_class,
            patch('app.core.database.get_session') as mock_session,
        ):
            mock_adapter_class.return_value.fetch_stock_price.return_value = mock_records
            mock_session.return_value = db

            _backfill_stock_price('SH601012')

        rows = db.query(PriceHistory).filter(PriceHistory.symbol == 'SH601012').all()
        assert len(rows) == 2


class _StubSession:
    """只为 `_write_with_retry` 的 rollback 调用准备的桩（不碰真库）。"""

    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


class TestBackfillWriteGate:
    """写库闸门：`database is locked` 必须重试，其余异常不得重试（2026-10-28 事故回归）。"""

    def test_locked_error_is_retried_then_succeeds(self, monkeypatch):
        """第一次 locked → rollback + 重试 → 第二次成功，不再静默丢整批净值。"""
        stub = _StubSession()
        calls = []

        def fake_bulk_insert(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise sa_exc.OperationalError('INSERT OR IGNORE INTO daily_worth', {}, Exception('database is locked'))
            return 7

        monkeypatch.setattr(async_backfill, 'bulk_insert_if_not_exists', fake_bulk_insert)
        monkeypatch.setattr(async_backfill.time, 'sleep', lambda *_: None)

        assert async_backfill._insert_rows(stub, DailyWorth, [], ['fund_code', 'date']) == 7
        assert len(calls) == 2, 'locked 必须重试一次'
        assert stub.rollbacks == 1, '重试前必须回滚，否则仍在过期快照上失败'

    def test_lock_exhausted_raises(self, monkeypatch):
        """重试耗尽仍 locked → 抛出，由调用方留下明确痕迹（不得伪装成普通失败）。"""
        stub = _StubSession()

        def always_locked(*args, **kwargs):
            raise sa_exc.OperationalError('INSERT OR IGNORE INTO daily_worth', {}, Exception('database is locked'))

        monkeypatch.setattr(async_backfill, 'bulk_insert_if_not_exists', always_locked)
        monkeypatch.setattr(async_backfill.time, 'sleep', lambda *_: None)

        with pytest.raises(sa_exc.OperationalError):
            async_backfill._insert_rows(stub, DailyWorth, [], ['fund_code', 'date'])
        assert stub.rollbacks == async_backfill._WRITE_ATTEMPTS - 1

    def test_non_locked_operational_error_is_not_retried(self, monkeypatch):
        """「表不存在」这类真 bug 只跑一次——重试 5 次只会让报错更难定位。"""
        stub = _StubSession()
        calls = []

        def fake_bulk_insert(*args, **kwargs):
            calls.append(args)
            raise sa_exc.OperationalError('INSERT', {}, Exception('no such table: daily_worth'))

        monkeypatch.setattr(async_backfill, 'bulk_insert_if_not_exists', fake_bulk_insert)

        with pytest.raises(sa_exc.OperationalError):
            async_backfill._insert_rows(stub, DailyWorth, [], ['fund_code', 'date'])
        assert len(calls) == 1
        assert stub.rollbacks == 0


class TestTriggerBackfillDedupe:
    """in-flight 去重：同一标的重复触发不得各起一个线程重复写全历史。

    为什么直接驱动 `_dispatch_backfill` 而不是 `trigger_backfill`：`tests/conftest.py` 有
    autouse 夹具把 `trigger_backfill` 换成空实现（避免测试期真起线程打网络），从测试里调入口
    只会调到一个 lambda。判据因此钉在真正的动作上——去重与释放都在这一层。
    """

    def setup_method(self):
        async_backfill._INFLIGHT.clear()

    def teardown_method(self):
        async_backfill._INFLIGHT.clear()

    @staticmethod
    def _wait_drained(timeout=2.0):
        """等 in-flight 自清（线程是 daemon，无法 join，只能轮询标记）。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with async_backfill._INFLIGHT_LOCK:
                if not async_backfill._INFLIGHT:
                    return True
            time.sleep(0.01)
        return False

    def test_same_target_triggered_twice_runs_once(self):
        started = threading.Event()
        release = threading.Event()
        calls = []

        def fake_backfill(code):
            calls.append(code)
            started.set()
            release.wait(timeout=5)

        assert async_backfill._dispatch_backfill(('fund', '000001'), fake_backfill, '000001') is True
        assert started.wait(timeout=5), '回填线程没能启动'
        # 第二次触发：同一标的在跑 → 必须拒绝，且不得再起线程
        assert async_backfill._dispatch_backfill(('fund', '000001'), fake_backfill, '000001') is False
        release.set()

        assert self._wait_drained(), '跑完没有释放 in-flight 标记'
        assert calls == ['000001'], '同一标的的第二次触发应被去重'

    def test_inflight_released_after_finish(self):
        """跑完必须释放标记，否则按需首屏回填会被永久跳过。"""
        done = threading.Event()

        def fake_backfill(code):
            done.set()

        async_backfill._dispatch_backfill(('fund', '000002'), fake_backfill, '000002')
        assert done.wait(timeout=5)

        assert self._wait_drained()
        with async_backfill._INFLIGHT_LOCK:
            assert ('fund', '000002') not in async_backfill._INFLIGHT

    def test_released_even_when_target_raises(self):
        """目标函数抛错也必须释放 —— 否则该标的此后所有回填都被静默跳过。"""
        done = threading.Event()

        def boom(code):
            done.set()
            raise RuntimeError('抓取炸了')

        async_backfill._dispatch_backfill(('fund', '000003'), boom, '000003')
        assert done.wait(timeout=5)

        assert self._wait_drained()
        with async_backfill._INFLIGHT_LOCK:
            assert ('fund', '000003') not in async_backfill._INFLIGHT
