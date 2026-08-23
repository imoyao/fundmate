# -*- coding: utf-8 -*-
"""价格区间/基金净值回填接口测试（#948）。"""

from datetime import date, timedelta

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
