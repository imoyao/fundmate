# -*- coding: utf-8 -*-
"""测试 PriceHistorySyncJob"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security
from app.services.sync.jobs.price_history_job import _HISTORY_START, PriceHistorySyncJob


class TestPriceHistorySyncJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_akshare'
        return PriceHistorySyncJob(adapter, db)

    def test_validate_normal(self, job):
        """正常行情数据通过校验"""
        raw = [
            {
                'security_id': 1,
                'trade_date': date(2025, 1, 2),
                'open': 100.0,
                'high': 105.0,
                'low': 99.0,
                'close': 102.0,
                'volume': 10000,
                'adj_close': 101.5,
                'source': 'akshare',
            }
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        item = validated[0]
        assert item['open'] == 100.0

    def test_validate_default_adj_close(self, job):
        """未提供 adj_close 时自动使用 close 填充"""
        raw = [
            {
                'security_id': 1,
                'trade_date': date(2025, 1, 2),
                'close': 50.0,
                'open': 49.0,
                'high': 51.0,
                'low': 48.0,
            }
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['adj_close'] == 50.0
        assert validated[0]['source'] == 'mock_akshare'

    def test_validate_missing_key_fields(self, job):
        """缺失必填字段的记录应被过滤"""
        raw = [
            {'trade_date': date(2025, 1, 1), 'close': 100.0},
            {'security_id': 1, 'close': 100.0},
            {'security_id': 2, 'trade_date': date(2025, 1, 3), 'close': 99.0},
        ]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['security_id'] == 2

    def test_deduplicate_passes_rows_through(self, job, db):
        """#2464：去重不再丢弃已存在的行——重写语义下移到 `_save_data` 的 upsert。

        原实现把已存在的 `(security_id, trade_date)` 直接丢掉，于是「重算」永远
        落不了库：修正了断点，下一次增量抓取又把旧口径写回去，断裂修不掉。
        现在这些行不是「跳过」，而是被**重写**（见 `_save_data`）。
        """
        # 外键约束：price_history.security_id 引用 securities.id，须先建 id=1 的父记录
        sec = db.query(Security).filter_by(id=1).first()
        if not sec:
            sec = Security(id=1, symbol='TEST1', name='测试证券', market='CN_A', type='stock', currency='CNY')
            db.add(sec)
            db.flush()

        db.add(
            PriceHistory(
                security_id=1,
                symbol='TEST1',  # 新增，任意非空字符串
                trade_date=date(2025, 1, 1),
                close=10.0,
            )
        )
        db.commit()

        data = [
            {'security_id': 1, 'trade_date': date(2025, 1, 1), 'close': 10.0},
            {'security_id': 1, 'trade_date': date(2025, 1, 2), 'close': 11.0},
            {'security_id': 2, 'trade_date': date(2025, 1, 1), 'close': 20.0},
        ]
        assert len(job._deduplicate(data)) == 3

    def test_run_integration(self, job, db):
        """端到端测试：增量同步写入行情数据"""
        sec = Security(symbol='SH600519', name='茅台', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()

        job.adapter.fetch_stock_price.return_value = [
            {
                'symbol': 'SH600519',
                'trade_date': date(2025, 1, 2),
                'open': 100,
                'high': 105,
                'low': 99,
                'close': 102,
                'volume': 1000,
            },
            {
                'symbol': 'SH600519',
                'trade_date': date(2025, 1, 3),
                'open': 102,
                'high': 106,
                'low': 101,
                'close': 104,
                'volume': 1200,
            },
        ]

        result = job.run(full_sync=True, targets=['SH600519'])
        assert result['status'] == 'success'
        assert result['stats']['total'] == 1
        assert result['stats']['success'] == 2

        rows = db.query(PriceHistory).all()
        assert len(rows) == 2


class TestAdjAnchorContinuity:
    """#2464：前复权序列在抓取批次边界断裂（源侧锚点随批次变）。

    事实：`adj_close` 是前复权价，源侧以「抓取那一刻的最新价」为锚；一次分红 / 送转
    之后源侧把**全部历史**乘上新因子。库内旧行不动、只追加新行，边界处就凭空多出
    一段涨跌：SZ000568 2026-07-20→21，`close` 口径 -2.806%、`adj_close` 口径
    -8.041%，而那天不是任何除息日。

    三条判据（对应实现里的三步）：增量窗口**含**库内最后一行 → 用 `adj_close/close`
    比值判定锚点是否移动 → 移动则整段重抓并**覆盖**写入。
    """

    SYMBOL = 'SZ000568'

    @pytest.fixture
    def job(self, db):
        return PriceHistorySyncJob(MagicMock(), db)

    def _prepare(self, db):
        sec = Security(symbol=self.SYMBOL, name='泸州老窖', market='CN_A', type='stock', currency='CNY')
        db.add(sec)
        db.commit()
        return sec

    @staticmethod
    def _bar(symbol, day, close, adj, source='akshare_sina'):
        return {
            'symbol': symbol,
            'trade_date': day,
            'open': close,
            'high': close,
            'low': close,
            'close': close,
            'volume': 1000,
            'adj_close': adj,
            'source': source,
        }

    @staticmethod
    def _install(job, window_rows, full_rows):
        """假适配器：窗口抓取与整段重抓返回不同数据，并记录调用参数。"""
        calls = []

        def _fetch(symbol, start_date=None, end_date=None):
            calls.append((symbol, start_date, end_date))
            if start_date == _HISTORY_START:
                return [dict(r) for r in full_rows]
            return [dict(r) for r in window_rows]

        job.adapter.fetch_stock_price.side_effect = _fetch
        return calls

    def test_incremental_window_includes_last_stored_date(self, job):
        """增量窗口从库内最后一行起（含），否则没有可比对的同一个日期。"""
        last = date(2026, 7, 21)
        start, end = job._resolve_window(self.SYMBOL, {self.SYMBOL: last}, date(2026, 7, 23), False)
        assert start == last
        assert end == date(2026, 7, 23)

    def test_full_sync_window_starts_from_1990(self):
        """全量窗口必须是具体日期：`None` 在适配器里会退化成近 365 天，重算覆盖不到更早的行。"""
        start, _end = PriceHistorySyncJob._resolve_window(self.SYMBOL, {}, date(2026, 7, 23), True)
        assert start == _HISTORY_START

    @pytest.mark.parametrize(
        'stored,rows,expected',
        [
            # 库内无该标的 ⇒ 没有可比样本，不下结论
            (None, [{'trade_date': date(2026, 7, 21), 'close': 97.0, 'adj_close': 92.0, 'source': 's'}], False),
            # 窗口为空 ⇒ 同上
            ((date(2026, 7, 21), 97.0, 92.0, 's'), [], False),
            # 窗口里没有这一天（停牌 / 源侧缺）⇒ 不得把「没拿到」读成「变了」
            (
                (date(2026, 7, 21), 97.0, 92.0, 's'),
                [{'trade_date': date(2026, 7, 22), 'close': 97.0, 'adj_close': 92.0, 'source': 's'}],
                False,
            ),
            # 换数据源 ⇒ 复权实现不同，比值不可比
            (
                (date(2026, 7, 21), 97.0, 92.0, 'akshare_tx'),
                [{'trade_date': date(2026, 7, 21), 'close': 97.0, 'adj_close': 92.0, 'source': 'akshare_sina'}],
                False,
            ),
            # 比值未变 ⇒ 锚点没动（源侧改了 close，分子分母同比例挪动）
            (
                (date(2026, 7, 21), 100.0, 95.0, 's'),
                [{'trade_date': date(2026, 7, 21), 'close': 97.0, 'adj_close': 92.15, 'source': 's'}],
                False,
            ),
            # 比值跳变 ⇒ 锚点挪了
            (
                (date(2026, 7, 21), 97.0, 97.0, 's'),
                [{'trade_date': date(2026, 7, 21), 'close': 97.0, 'adj_close': 92.0, 'source': 's'}],
                True,
            ),
        ],
    )
    def test_anchor_moved_judgement(self, stored, rows, expected):
        assert PriceHistorySyncJob._anchor_moved(stored, rows) is expected

    def test_anchor_shift_triggers_full_refetch_and_rewrites_history(self, job, db):
        """锚点挪了 ⇒ 整段重抓 + 覆盖旧行（不是「留旧值」也不是「插重复行」）。"""
        sec = self._prepare(db)
        db.add_all(
            [
                PriceHistory(
                    security_id=sec.id,
                    symbol=self.SYMBOL,
                    trade_date=date(2026, 7, 20),
                    close=100.0,
                    adj_close=100.0,
                    source='akshare_sina',
                ),
                PriceHistory(
                    security_id=sec.id,
                    symbol=self.SYMBOL,
                    trade_date=date(2026, 7, 21),
                    close=97.0,
                    adj_close=97.0,
                    source='akshare_sina',
                ),
            ]
        )
        db.commit()

        # 此刻源侧已按新锚点复权（除息后）：旧行整体下移，并多出 07-22
        window_rows = [self._bar(self.SYMBOL, date(2026, 7, 21), 97.0, 91.96)]
        full_rows = [
            self._bar(self.SYMBOL, date(2026, 7, 20), 100.0, 94.8),
            self._bar(self.SYMBOL, date(2026, 7, 21), 97.0, 91.96),
            self._bar(self.SYMBOL, date(2026, 7, 22), 96.0, 91.008),
        ]
        calls = self._install(job, window_rows, full_rows)

        job.run(full_sync=False, targets=[self.SYMBOL])

        # 先按重叠窗口抓一次，再整段重抓一次
        assert [c[1] for c in calls] == [date(2026, 7, 21), _HISTORY_START]
        assert job.stats['adj_rebuilt_symbols'] == [self.SYMBOL]

        rows = db.query(PriceHistory).filter_by(symbol=self.SYMBOL).order_by(PriceHistory.trade_date).all()
        assert [r.trade_date for r in rows] == [date(2026, 7, 20), date(2026, 7, 21), date(2026, 7, 22)]
        assert [r.adj_close for r in rows] == [94.8, 91.96, 91.008]
        assert job.stats['updated'] == 2

    def test_unchanged_anchor_keeps_single_fetch(self, job, db):
        """锚点没动就只抓一次重叠窗口，不做多余的全量请求。"""
        sec = self._prepare(db)
        db.add(
            PriceHistory(
                security_id=sec.id,
                symbol=self.SYMBOL,
                trade_date=date(2026, 7, 21),
                close=97.0,
                adj_close=97.0,
                source='akshare_sina',
            )
        )
        db.commit()

        window_rows = [
            self._bar(self.SYMBOL, date(2026, 7, 21), 97.0, 97.0),
            self._bar(self.SYMBOL, date(2026, 7, 22), 98.0, 98.0),
        ]
        calls = self._install(job, window_rows, [])

        job.run(full_sync=False, targets=[self.SYMBOL])

        assert len(calls) == 1
        assert 'adj_rebuilt_symbols' not in job.stats
        assert db.query(PriceHistory).filter_by(symbol=self.SYMBOL).count() == 2

    def test_full_sync_overwrites_existing_rows(self, job, db):
        """`--full-sync` = 存量修复入口：抓全历史并覆盖旧行（原来是只插不更新）。"""
        sec = self._prepare(db)
        db.add(
            PriceHistory(
                security_id=sec.id,
                symbol=self.SYMBOL,
                trade_date=date(2026, 7, 20),
                close=100.0,
                adj_close=100.0,
                source='akshare_sina',
            )
        )
        db.commit()

        calls = self._install(job, [], [self._bar(self.SYMBOL, date(2026, 7, 20), 100.0, 94.8)])

        job.run(full_sync=True, targets=[self.SYMBOL])

        assert calls[0][1] == _HISTORY_START
        rows = db.query(PriceHistory).filter_by(symbol=self.SYMBOL).all()
        assert len(rows) == 1
        assert rows[0].adj_close == 94.8
        assert job.stats['updated'] == 1

    def test_suspended_symbol_still_reported_as_empty(self, job, db):
        """窗口含重叠行后，「取到重叠行」不得被当成「有新行情」（#2277 不能退化）。"""
        sec = self._prepare(db)
        db.add(
            PriceHistory(
                security_id=sec.id,
                symbol=self.SYMBOL,
                trade_date=date(2026, 7, 21),
                close=97.0,
                adj_close=97.0,
                source='akshare_sina',
            )
        )
        db.commit()

        self._install(job, [self._bar(self.SYMBOL, date(2026, 7, 21), 97.0, 97.0)], [])

        job.run(full_sync=False, targets=[self.SYMBOL])

        assert job.stats['empty_symbols'] == [self.SYMBOL]

    def test_full_sync_empty_source_does_not_crash(self, job, db):
        """全量窗口原为 ``(None, None)``，空结果走到 ``start_date <= end_date`` 直接 TypeError。

        #2464 把全量起点改成具体日期后顺带修掉；这里钉住「空结果不炸」。
        """
        self._prepare(db)
        self._install(job, [], [])

        result = job.run(full_sync=True, targets=[self.SYMBOL])

        assert result['status'] == 'success'
