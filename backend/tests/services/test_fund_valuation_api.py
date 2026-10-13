# -*- coding: utf-8 -*-
"""#2141 收盘估值定格端点契约测试。

锁定三件事：
1. 路由与响应信封符合 AGENTS.md 接口契约（{data, message}，成功无 error_code）；
2. date / fund_code 过滤生效；日期非法回 400 + error_code 1001；
3. 需登录：AUTH_ENABLED 强制模式下无 token 访问回 401。
"""

from datetime import date

from app.domains.funds.models import FundValuationDaily


def _seed(db, code='000001', est_date=None, nav='1.2345'):
    est_date = est_date or date(2026, 10, 13)
    db.add(
        FundValuationDaily(
            fund_code=code,
            est_date=est_date,
            estimated_nav=nav,
            change_pct='0.56',
            source='tiantian_gsz',
            source_time='2026-10-13 15:00',
            status='estimated',
        )
    )
    db.commit()


class TestFundValuationEndpoint:
    def test_query_default_today(self, client, db, monkeypatch):
        """不传 date → 查今日；seed 今日行能查到"""
        from app.core.time_utils import today_shanghai

        today = today_shanghai()
        _seed(db, est_date=today)
        resp = client.get('/api/summary/fund-valuation/')
        assert resp.status_code == 200
        payload = resp.get_json()
        assert 'data' in payload and 'message' in payload
        rows = payload['data']
        assert len(rows) == 1
        assert rows[0]['fund_code'] == '000001'
        assert rows[0]['source'] == 'tiantian_gsz'
        assert rows[0]['status'] == 'estimated'

    def test_query_with_date_filter(self, client, db):
        """指定 date → 只返回该日行"""
        _seed(db, est_date=date(2026, 10, 13))
        _seed(db, code='000002', est_date=date(2026, 10, 14))
        resp = client.get('/api/summary/fund-valuation/?date=2026-10-13')
        assert resp.status_code == 200
        rows = resp.get_json()['data']
        assert len(rows) == 1
        assert rows[0]['fund_code'] == '000001'

    def test_query_fund_code_filter(self, client, db):
        """fund_code 过滤生效"""
        _seed(db, code='000001', est_date=date(2026, 10, 13))
        _seed(db, code='000002', est_date=date(2026, 10, 13))
        resp = client.get('/api/summary/fund-valuation/?date=2026-10-13&fund_code=000002')
        assert resp.status_code == 200
        rows = resp.get_json()['data']
        assert len(rows) == 1
        assert rows[0]['fund_code'] == '000002'

    def test_invalid_date_format_returns_400(self, client):
        """日期格式非法 → 400 + error_code 1001"""
        resp = client.get('/api/summary/fund-valuation/?date=not-a-date')
        assert resp.status_code == 400
        payload = resp.get_json()
        assert payload['error_code'] == 1001
        assert payload['data'] == []

    def test_requires_auth_when_auth_enabled(self, client, monkeypatch):
        """强制登录模式：无 token / 无 X-User-Id → 401"""
        monkeypatch.setenv('AUTH_ENABLED', 'true')
        resp = client.get('/api/summary/fund-valuation/')
        assert resp.status_code == 401
