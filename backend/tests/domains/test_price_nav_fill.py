# -*- coding: utf-8 -*-
"""价格区间/基金净值回填接口测试（#948）。"""

from datetime import date, timedelta

from app.domains.ledgers.models import Ledger
from app.domains.price_history.models import PriceHistory
from app.domains.securities.models import Security


def _seed_security(db, symbol):
    sec = Security(symbol=symbol, name='测试证券', market='CN_A', type='stock')
    db.add(sec)
    db.commit()
    return sec


class TestSecurityPriceRange:
    def test_range_latest_and_by_date(self, client, db):
        sec = _seed_security(db, 'SH600519')
        today = date.today()
        rows = []
        for i, (low, high, close) in enumerate([(10.0, 12.0, 11.0), (11.0, 13.0, 12.5)]):
            rows.append(
                PriceHistory(
                    security_id=sec.id,
                    symbol='SH600519',
                    trade_date=today - timedelta(days=i),
                    low=low,
                    high=high,
                    close=close,
                )
            )
        db.add_all(rows)
        db.commit()

        # 缺省 date：取最近交易日（i=0 → 今天，low/high = 10/12）
        resp = client.get('/api/securities/SH600519/price-range/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['date'] == today.isoformat()
        assert (data['low'], data['high']) == (10.0, 12.0)

        # 指定 date：取 ≤ 该日的最近一条（昨天那根 K 线 11/13）
        resp2 = client.get(
            '/api/securities/SH600519/price-range/',
            query_string={'date': (today - timedelta(days=1)).isoformat()},
        )
        data2 = resp2.get_json()['data']
        assert data2['date'] == (today - timedelta(days=1)).isoformat()
        assert (data2['low'], data2['high']) == (11.0, 13.0)

    def test_range_no_data_returns_null(self, client):
        resp = client.get('/api/securities/SZ999999/price-range/')
        assert resp.status_code == 200
        assert resp.get_json()['data'] is None

    def test_range_bad_date_format_400(self, client):
        resp = client.get(
            '/api/securities/SH600519/price-range/',
            query_string={'date': 'not-a-date'},
        )
        assert resp.status_code == 400


class TestFundNavLookup:
    def test_nav_latest_and_fallback(self, client, db):
        from app.domains.funds.models import DailyWorth, Fund

        db.add(Fund(fund_code='110011', name='易方达中小盘'))
        db.commit()
        today = date.today()
        db.add_all(
            [
                DailyWorth(
                    fund_code='110011',
                    date=today - timedelta(days=3),
                    unit_nav=1.5,
                ),
                DailyWorth(
                    fund_code='110011',
                    date=today - timedelta(days=1),
                    unit_nav=1.6,
                    acc_nav=2.0,
                ),
            ]
        )
        db.commit()

        # 缺省：最新一条
        resp = client.get('/api/funds/110011/nav/')
        assert resp.get_json()['data']['unit_nav'] == 1.6

        # ≤ 指定日回退：取该日之前最近一条
        resp2 = client.get(
            '/api/funds/110011/nav/',
            query_string={'date': (today - timedelta(days=2)).isoformat()},
        )
        data2 = resp2.get_json()['data']
        assert data2['unit_nav'] == 1.5

    def test_nav_unknown_fund_returns_null(self, client):
        resp = client.get('/api/funds/999999/nav/')
        assert resp.status_code == 200
        assert resp.get_json()['data'] is None


class TestBackendPriceRangeInterception:
    """后端成交价区间拦截（#948 续）：证券类成交价须在交易日 [low, high] 内（#948）。

    与前端 SellForm/BuyForm 的区间校验保持一致——即便绕过前端直接调 API 也会被拦。
    """

    TRADE_DATE = '2026-06-15'
    SYMBOL = '600519'  # 归一化后为 SH600519

    def _seed(self, db):
        _seed_security(db, 'SH600519')
        db.add(
            PriceHistory(
                security_id=1,
                symbol='SH600519',
                trade_date=date.fromisoformat(self.TRADE_DATE),
                low=1500.0,
                high=1700.0,
                close=1650.0,
            )
        )
        db.add(Ledger(name='测试账户', ledger_type='stock'))
        db.commit()

    def _buy(self, client):
        resp = client.post(
            '/api/positions/',
            json={
                'symbol': self.SYMBOL,
                'name': '贵州茅台',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '测试账户',
                'quantity': 200,
                'avg_price': 1600.0,  # 区间内，买入应通过校验
                'currency': 'CNY',
                'trade_date': self.TRADE_DATE,
                'op_type': 'buy',
            },
        )
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()['data']['id']

    def test_buy_in_range_ok(self, client, db):
        self._seed(db)
        # 买入价在区间内 → 成功，说明区间校验未误杀合法成交
        assert self._buy(client) > 0

    def test_sell_out_of_range_blocked(self, client, db):
        self._seed(db)
        pos_id = self._buy(client)
        # 卖出价远超当日区间 → 后端拦截，返回 400 并提示超出区间
        resp = client.post(
            '/api/positions/',
            json={
                'symbol': self.SYMBOL,
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '测试账户',
                'position_id': pos_id,
                'quantity': 100,
                'avg_price': 99999.0,  # 超出 [1500, 1700]
                'currency': 'CNY',
                'trade_date': self.TRADE_DATE,
                'op_type': 'sell',
            },
        )
        assert resp.status_code == 400
        assert '超出' in resp.get_json()['message']

    def test_sell_in_range_ok(self, client, db):
        self._seed(db)
        pos_id = self._buy(client)
        # 卖出价在区间内 → 成功
        resp = client.post(
            '/api/positions/',
            json={
                'symbol': self.SYMBOL,
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '测试账户',
                'position_id': pos_id,
                'quantity': 100,
                'avg_price': 1600.0,  # 区间内
                'currency': 'CNY',
                'trade_date': self.TRADE_DATE,
                'op_type': 'sell',
            },
        )
        assert resp.status_code == 200

    def test_no_price_history_not_blocked(self, client, db, monkeypatch):
        """本地与实时兜底都拿不到区间数据时，放行（不阻塞手输；不误杀）。

        对应 #948 后续修复的降级语义：use_live_fallback=True 仅在「本地或实时任一可达」
        时才拦截；两者皆不可达（如完全离线）则放行。
        """
        _seed_security(db, 'SH600519')
        db.add(Ledger(name='测试账户', ledger_type='stock'))
        db.commit()
        # 模拟「本地无数据 + 实时兜底也不可达」的降级情形
        monkeypatch.setattr(
            'app.domains.positions.views.resolve_security_price_range',
            lambda symbol, trade_date, use_live_fallback=False: None,
        )
        resp = client.post(
            '/api/positions/',
            json={
                'symbol': self.SYMBOL,
                'name': '贵州茅台',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '测试账户',
                'quantity': 100,
                'avg_price': 99999.0,  # 无区间数据，不应被拦截
                'currency': 'CNY',
                'trade_date': self.TRADE_DATE,
                'op_type': 'buy',
            },
        )
        assert resp.status_code == 200

    def test_live_fallback_blocks_when_no_local_history(self, client, db, monkeypatch):
        """#948 后续修复验证：本地无 PriceHistory 时，启用实时兜底也能拦住异常成交价。

        这正是「用户以 100 元卖出隆基（缺本地行情）却未被拦截」的根因修复点：
        写路径区间校验改为 use_live_fallback=True，腾讯/akshare 兜底可达即拦截。
        """
        _seed_security(db, 'SH600519')
        db.add(Ledger(name='测试账户', ledger_type='stock'))
        db.commit()
        fallback = {'symbol': 'SH600519', 'date': self.TRADE_DATE, 'low': 1500.0, 'high': 1700.0, 'close': 1650.0}
        monkeypatch.setattr('app.services.price_range_service.fetch_tencent_price_range', lambda s, t: fallback)
        monkeypatch.setattr('app.services.price_range_service.fetch_live_price_range', lambda s, t: fallback)
        resp = client.post(
            '/api/positions/',
            json={
                'symbol': self.SYMBOL,
                'name': '贵州茅台',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '测试账户',
                'quantity': 100,
                'avg_price': 99999.0,  # 超出兜底区间 → 应被拦截
                'currency': 'CNY',
                'trade_date': self.TRADE_DATE,
                'op_type': 'buy',
            },
        )
        assert resp.status_code == 400
        assert '超出' in resp.get_json()['message']


class TestPriceRangeFallbackChain:
    """实时兜底链：腾讯财经优先（仅当日），历史日退 akshare（mock 验证，避免依赖网络）。"""

    def test_tencent_preferred_for_today(self, db, monkeypatch):
        from app.services.price_range_service import resolve_security_price_range

        _seed_security(db, 'SH600519')
        today = date.today().isoformat()
        tencent = {'symbol': 'SH600519', 'date': today, 'low': 10.0, 'high': 20.0, 'close': 15.0}
        akshare = {'symbol': 'SH600519', 'date': today, 'low': 1.0, 'high': 2.0, 'close': 1.5}
        monkeypatch.setattr('app.services.price_range_service.fetch_tencent_price_range', lambda s, t: tencent)
        monkeypatch.setattr('app.services.price_range_service.fetch_live_price_range', lambda s, t: akshare)
        # 本地无 PriceHistory → 走实时兜底，腾讯优先
        assert resolve_security_price_range('SH600519', today, use_live_fallback=True) == tencent

    def test_akshare_used_for_past_date(self, db, monkeypatch):
        from app.services.price_range_service import resolve_security_price_range

        _seed_security(db, 'SH600519')
        akshare = {'symbol': 'SH600519', 'date': '2026-06-15', 'low': 10.0, 'high': 20.0, 'close': 15.0}
        tencent = {'symbol': 'SH600519', 'date': date.today().isoformat(), 'low': 1.0, 'high': 2.0, 'close': 1.5}
        # 真实 fetch_tencent_price_range 仅当日有效；mock 复刻该约束，历史日返回 None
        monkeypatch.setattr(
            'app.services.price_range_service.fetch_tencent_price_range',
            lambda s, t: tencent if t == date.today() else None,
        )
        monkeypatch.setattr('app.services.price_range_service.fetch_live_price_range', lambda s, t: akshare)
        # 历史日：腾讯实时不适用 → 应取 akshare 历史日线
        assert resolve_security_price_range('SH600519', '2026-06-15', use_live_fallback=True) == akshare

    def test_no_fallback_when_disabled(self, db, monkeypatch):
        from app.services.price_range_service import resolve_security_price_range

        _seed_security(db, 'SH600519')
        monkeypatch.setattr(
            'app.services.price_range_service.fetch_tencent_price_range',
            lambda s, t: {
                'symbol': 'SH600519',
                'date': date.today().isoformat(),
                'low': 1.0,
                'high': 2.0,
                'close': 1.5,
            },
        )
        # use_live_fallback=False → 即便有兜底函数也不调用，本地无数据则 None
        assert resolve_security_price_range('SH600519', date.today().isoformat(), use_live_fallback=False) is None
