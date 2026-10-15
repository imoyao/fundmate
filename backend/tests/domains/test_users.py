# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/10
# File : test_users.py
"""用户 API 测试 — record_stats 首笔交易日期与累计记账天数（P4#14）。

修复契约：首笔交易按 COALESCE(trade_date, confirm_date) 排序取值，
trade_date 缺失（历史导入数据只有 confirm_date）时回退 confirm_date，
不再因 SQLite NULL 排最前而恒返回空状态。
"""

from datetime import date, datetime


def _get(client, url, params=None):
    return client.get(url if url.endswith('/') else url + '/', query_string=params)


class TestRecordStats:
    """GET /api/users/record-stats/"""

    def _create_position(self, make_position):
        return make_position(
            symbol='000001',
            name='测试持仓',
            account_name='测试账户',
            quantity=100,
            avg_price=1.0,
        )

    def _create_txn(self, db, make_transaction, pos, *, trade_date, confirm_date, **kwargs):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            txn_type='buy',
            quantity=100,
            price=1.0,
            trade_date=trade_date,
            confirm_date=confirm_date,
            **kwargs,
        )
        db.commit()

    def test_single_null_trade_date_falls_back_to_confirm_date(self, client, db, make_position, make_transaction):
        """只有一条 trade_date=NULL、confirm_date 有值的交易 → 首笔日期取 confirm_date"""
        confirm = date(2025, 1, 1)
        pos = self._create_position(make_position)
        self._create_txn(
            db,
            make_transaction,
            pos,
            trade_date=None,
            confirm_date=confirm,
            allow_null_trade_date=True,
        )

        resp = _get(client, '/api/users/record-stats/')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['message'] == 'ok'
        data = body['data']
        assert data['first_entry_date'] == confirm.isoformat()
        assert data['record_days'] > 0

    def test_mixed_null_and_value_takes_earliest(self, client, db, make_position, make_transaction):
        """混合数据：trade_date 缺失与有值并存 → 取最早的非 NULL 日期（COALESCE 语义）"""
        pos = self._create_position(make_position)
        # 更早的一条：trade_date 有值
        self._create_txn(
            db,
            make_transaction,
            pos,
            trade_date=datetime(2024, 1, 1, 9, 30),
            confirm_date=date(2024, 1, 2),
        )
        # 较晚的一条：trade_date 缺失，仅 confirm_date
        self._create_txn(
            db,
            make_transaction,
            pos,
            trade_date=None,
            confirm_date=date(2025, 1, 1),
            allow_null_trade_date=True,
        )

        resp = _get(client, '/api/users/record-stats/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['first_entry_date'] == '2024-01-01'
        assert data['record_days'] > 0

    def test_no_transactions_returns_empty(self, client):
        """无任何交易 → first_entry_date=None、record_days=0"""
        resp = _get(client, '/api/users/record-stats/')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['message'] == 'ok'
        data = body['data']
        assert data['first_entry_date'] is None
        assert data['record_days'] == 0

    def test_normal_dual_date_data(self, client, db, make_position, make_transaction):
        """正常双日期数据 → 首笔日期取 trade_date，天数正确"""
        trade = datetime(2025, 1, 1, 9, 30)
        pos = self._create_position(make_position)
        self._create_txn(
            db,
            make_transaction,
            pos,
            trade_date=trade,
            confirm_date=date(2025, 1, 3),
        )

        resp = _get(client, '/api/users/record-stats/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['first_entry_date'] == '2025-01-01'
        expected_days = max((date.today() - trade.date()).days, 0)
        assert data['record_days'] == expected_days


class TestUserPreferences:
    """GET/PUT /api/users/preferences/<key>/（#1337 方案 B 跨设备同步）。

    测试走开发模式默认用户（无 token 回退默认身份），另一用户行由测试直插。
    """

    KEY = 'watchlist-column-settings'

    def test_get_missing_key_returns_null(self, client):
        """无值返回 200 + data=null（前端按无偏好处理，不是 404）"""
        resp = client.get(f'/api/users/preferences/{self.KEY}/')
        assert resp.status_code == 200
        assert resp.get_json()['data'] is None

    def test_put_then_get_roundtrip(self, client, db):
        """PUT upsert 后 GET 回读一致，updated_at 随写入生成（供合并策略比较）"""
        payload = {'hidden': ['pe_ratio'], 'shown': ['manager_name'], 'order': ['price']}
        resp = client.put(f'/api/users/preferences/{self.KEY}/', json={'value': payload})
        assert resp.status_code == 200
        body = resp.get_json()['data']
        assert body['key'] == self.KEY
        assert body['value'] == payload
        assert body['updated_at'] is not None

        got = client.get(f'/api/users/preferences/{self.KEY}/').get_json()['data']
        assert got['value'] == payload

    def test_put_same_key_overwrites_single_row(self, client, db):
        """同 key 二次 PUT 覆盖同一行（唯一约束生效，不重复建行）"""
        client.put(f'/api/users/preferences/{self.KEY}/', json={'value': {'hidden': ['a']}})
        client.put(f'/api/users/preferences/{self.KEY}/', json={'value': {'hidden': ['b']}})

        got = client.get(f'/api/users/preferences/{self.KEY}/').get_json()['data']
        assert got['value'] == {'hidden': ['b']}

        from app.domains.users.models import UserPreference

        db.expire_all()
        rows = db.query(UserPreference).filter_by(key=self.KEY).all()
        assert len(rows) == 1

    def test_preferences_are_isolated_per_user(self, client, db):
        """按 user_id 私有：另一用户同 key 值互不可见、互不覆盖"""
        from app.domains.users.models import User, UserPreference

        other = User(family_id=1, username='other-pref-user')
        db.add(other)
        db.commit()
        db.add(UserPreference(user_id=other.id, key=self.KEY, value='{"hidden": ["other"]}'))
        db.commit()

        my_payload = {'hidden': ['mine']}
        client.put(f'/api/users/preferences/{self.KEY}/', json={'value': my_payload})

        got = client.get(f'/api/users/preferences/{self.KEY}/').get_json()['data']
        assert got['value'] == my_payload

        db.expire_all()
        other_row = db.query(UserPreference).filter_by(user_id=other.id, key=self.KEY).first()
        assert other_row.value == '{"hidden": ["other"]}'

    def test_put_non_object_value_rejected(self, client):
        """value 必须是 JSON 对象：裸数组/标量拒收"""
        resp = client.put(f'/api/users/preferences/{self.KEY}/', json={'value': [1, 2]})
        assert 400 <= resp.status_code < 500

    def test_overlong_key_rejected(self, client):
        """key 超过 100 字符 → 400"""
        resp = client.get(f'/api/users/preferences/{"k" * 101}/')
        assert resp.status_code == 400
