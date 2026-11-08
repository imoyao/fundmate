# -*- coding: utf-8 -*-
"""名录缺口计算 + 单只查询解析（离线，不真联网）。

覆盖：缺口 = 流水 − 名录、品种白名单排除、secid 映射（沪深北/裸码/非法）、
上游各形态响应的降级路径、并发闸门。
"""

import pytest

from app.domains.securities.models import Security
from app.domains.transactions.models import Transaction
from app.services import securities_catalog
from app.services.adapters import eastmoney_security_lookup as lookup
from app.services.securities_catalog import missing_catalog_symbols


def _seed_txn(db, symbol, asset_type='stock'):
    db.add(Transaction(symbol=symbol, asset_type=asset_type, family_id=1))


class TestMissingCatalogSymbols:
    def test_gap_is_held_minus_catalog(self, db):
        """缺口 = 流水里的场内标的 − 名录里已有的。"""
        _seed_txn(db, 'SH600519')  # 名录里有 → 不算缺口
        _seed_txn(db, 'SH501018')  # LOF，名录里没有 → 缺口
        db.add(Security(symbol='SH600519', name='贵州茅台', market='CN_A', type='stock'))
        db.commit()

        assert missing_catalog_symbols(db) == ['SH501018']

    def test_no_transaction_means_no_gap(self, db):
        assert missing_catalog_symbols(db) == []

    def test_non_exchange_types_excluded(self, db):
        """场外基金走净值、现金没有行情，都不该进缺口（白名单见 price_depth）。"""
        _seed_txn(db, '004369', 'fund')
        _seed_txn(db, '__CASH__', 'cash')
        _seed_txn(db, 'MGR_abc', 'manager')
        db.commit()

        assert missing_catalog_symbols(db) == []

    def test_gap_shrinks_after_backfill(self, db):
        """补上之后缺口自动缩小——这是「幂等可重算」的实际含义。"""
        _seed_txn(db, 'SH600519')
        db.commit()
        assert missing_catalog_symbols(db) == ['SH600519']

        db.add(Security(symbol='SH600519', name='贵州茅台', market='CN_A', type='stock'))
        db.commit()
        assert missing_catalog_symbols(db) == []

    @pytest.mark.parametrize('code', ['370181', '072550', '732543'])
    def test_subscription_codes_are_not_gaps(self, db, code):
        """申购代码永远进不了名录（名录存的是上市代码），不能当成缺口反复补。

        370/072 尤其危险：三、零开头会被 market_of_cn_a_code 判成 SZ，
        看起来完全像上市代码 —— 不显式排除就会每次导入报一次 failed。
        """
        _seed_txn(db, code, 'bond')
        db.commit()
        assert missing_catalog_symbols(db) == []

    def test_bare_code_matches_prefixed_catalog_entry(self, db):
        """裸码与带前缀名录是同一只：归一后比对，否则每次都重打上游。"""
        _seed_txn(db, '603543')
        db.add(Security(symbol='SH603543', name='某新股', market='CN_A', type='stock'))
        db.commit()

        assert missing_catalog_symbols(db) == []


class TestToSecid:
    @pytest.mark.parametrize(
        ('symbol', 'expected'),
        [
            ('SH600519', '1.600519'),
            ('SZ000001', '0.000001'),
            # 北交所与深市同为 0：不能按「9 开头 → 沪市」类推（实测 0.920019 才对）
            ('BJ920019', '0.920019'),
            ('sh600519', '1.600519'),
            ('600519', '1.600519'),
            ('000001', '0.000001'),
            ('920019', '0.920019'),
            ('', None),
            ('   ', None),
            ('ABC', None),
            ('12345', None),
            ('SH60051', None),
        ],
    )
    def test_mapping(self, symbol, expected):
        assert lookup.to_secid(symbol) == expected


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeSession:
    """假 Session：记录调用参数，回放固定 payload。"""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({'url': url, 'params': params, 'timeout': timeout})
        return _FakeResp(self.payload)


@pytest.fixture
def patch_session(monkeypatch):
    """替换模块级 Session，返回安装函数。"""

    def install(payload):
        session = _FakeSession(payload)
        monkeypatch.setattr(lookup, '_get_session', lambda: session)
        return session

    return install


class TestFetchSecurityBySymbol:
    def test_happy_path(self, patch_session):
        session = patch_session({'data': {'f57': '600519', 'f58': '贵州茅台'}})

        record = lookup.fetch_security_by_symbol('SH600519')

        assert record == {
            'symbol': 'SH600519',
            'name': '贵州茅台',
            'market': 'CN_A',
            'type': 'stock',
            'currency': 'CNY',
        }
        assert session.calls[0]['params'] == {'secid': '1.600519', 'fields': 'f57,f58'}

    def test_missing_data_returns_none(self, patch_session):
        """未上市 / 已退市 / 代码不存在：上游 data 为 null，返回 None（绝不编造）。"""
        patch_session({'data': None})
        assert lookup.fetch_security_by_symbol('SH732543') is None

    def test_blank_name_returns_none(self, patch_session):
        patch_session({'data': {'f57': '600519', 'f58': '  '}})
        assert lookup.fetch_security_by_symbol('SH600519') is None

    def test_undecidable_type_returns_none(self, patch_session):
        """深市 11xxxx 既不是转债也不是 ETF，品类测不出 → 宁留缺口也不写错品类。"""
        patch_session({'data': {'f57': '110001', 'f58': '某品种'}})
        assert lookup.fetch_security_by_symbol('SZ110001') is None

    def test_unmappable_symbol_skips_network(self, patch_session):
        session = patch_session({'data': {'f57': '600519', 'f58': '贵州茅台'}})
        assert lookup.fetch_security_by_symbol('ABC') is None
        assert session.calls == []  # 判定不出市场就不打上游

    def test_network_error_returns_none(self, monkeypatch):
        class _Boom:
            def get(self, *a, **kw):
                raise ConnectionError('boom')

        monkeypatch.setattr(lookup, '_get_session', lambda: _Boom())
        assert lookup.fetch_security_by_symbol('SH600519') is None

    def test_bond_and_etf_types(self, patch_session):
        patch_session({'data': {'f57': '123291', 'f58': '佐力转债'}})
        assert lookup.fetch_security_by_symbol('SZ123291')['type'] == 'bond'

        patch_session({'data': {'f57': '162411', 'f58': '华宝油气LOF'}})
        assert lookup.fetch_security_by_symbol('SZ162411')['type'] == 'etf'


class TestTriggerGuard:
    def test_second_trigger_is_skipped_while_running(self, monkeypatch):
        """并发闸门：同一进程内只跑一轮，重复导入不会把上游打三遍。"""
        monkeypatch.setattr(securities_catalog, '_backfill_running', True)
        try:
            assert securities_catalog.trigger_catalog_backfill_async() is False
        finally:
            monkeypatch.setattr(securities_catalog, '_backfill_running', False)

    def test_trigger_starts_thread_and_resets_flag(self, monkeypatch):
        """正常触发：起线程并把标志复位（否则之后永远触发不了）。"""
        done = []

        def fake_run():
            done.append(1)
            with securities_catalog._backfill_lock:
                securities_catalog._backfill_running = False

        monkeypatch.setattr(securities_catalog, '_run_backfill', fake_run)
        monkeypatch.setattr(securities_catalog, '_backfill_running', False)

        assert securities_catalog.trigger_catalog_backfill_async() is True
        for _ in range(100):
            if done:
                break
            import time

            time.sleep(0.01)
        assert done == [1]
        assert securities_catalog._backfill_running is False
