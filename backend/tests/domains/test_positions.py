# backend/tests/test_positions.py
"""
持仓相关 API 测试扩展：交易明细查询、删除持仓（含级联删除交易）
"""

from datetime import date, timedelta

from sqlalchemy import exists

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction


# 辅助函数
def _post(client, url, data):
    resp = client.post(url if url.endswith('/') else url + '/', json=data)
    # 打印后端返回的完整 JSON，便于调试
    print(f'POST {url} -> {resp.status_code}')
    try:
        print(resp.get_json())
    except Exception:
        print('响应无法解析为 JSON')
    return resp


def _get(client, url, params=None):
    return client.get(url if url.endswith('/') else url + '/', query_string=params)


class TestPositionCreate:
    """创建持仓测试"""

    def test_buy_creates_position(self, client):
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
                'allocation': 'longterm',
                'op_type': 'buy',
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['symbol'] == 'HK00700'
        assert data['quantity'] == 100
        assert data['avg_price'] == 350
        # 标签字段
        assert data['type_label'] == '股票'
        assert data['allocation_label'] == '长期增值'

    def test_buy_same_symbol_merges(self, client):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
            },
        )
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 50,
                'avg_price': 380,
                'currency': 'HKD',
                'trade_date': '2026-05-02',
                'op_type': 'buy',
            },
        )
        data = resp.get_json()['data']
        assert data['quantity'] == 150
        assert abs(data['avg_price'] - 360.0) < 0.01
        # 合并后标签应存在
        assert 'type_label' in data
        assert 'allocation_label' in data

    def test_create_position_without_allocation(self, client):
        """不传配置目标时，应默认 longterm"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '000001.SZ',
                'name': '平安银行',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '券商账户',
                'quantity': 200,
                'avg_price': 15.0,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['allocation'] == 'longterm'
        assert data['allocation_label'] == '长期增值'


class TestPositionSell:
    """卖出操作测试"""

    def test_sell_partial(self, client):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 200,  # 改为两手
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        resp = _post(
            client,
            '/api/positions/',
            {
                'op_type': 'sell',
                'position_id': pos_id,
                'quantity': 100,
                'avg_price': 400,
                'trade_date': '2026-05-03',
            },  # 卖出一手
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['quantity'] == 100  # 剩余100股
        assert data['avg_price'] == 350

    def test_sell_all_clears_position(self, client):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': 'AAPL',
                'name': '苹果',
                'type': 'stock',
                'market': 'US',
                'account_name': '富途',
                'quantity': 50,
                'avg_price': 180,
                'currency': 'USD',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 50, 'avg_price': 190, 'trade_date': '2026-05-05'},
        )
        assert resp.status_code == 200
        assert resp.get_json()['message'] == '持仓已清空'

    def test_sell_missing_position_id_fails(self, client):
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'quantity': 10, 'avg_price': 100, 'trade_date': '2026-05-01'},
        )
        assert resp.status_code == 400

    def test_sell_exceeding_quantity_fails(self, client):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': 'AAPL',
                'name': '苹果',
                'type': 'stock',
                'market': 'US',
                'account_name': '富途',
                'quantity': 10,
                'avg_price': 180,
                'currency': 'USD',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 20, 'avg_price': 200, 'trade_date': '2026-05-02'},
        )
        assert resp.status_code == 400


class TestTransactions:
    """交易流水查询测试"""

    def test_transactions_time_range(self, client):
        today = date.today()
        old_date = (today - timedelta(days=400)).isoformat()
        recent_date = (today - timedelta(days=5)).isoformat()

        _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': old_date,
                'op_type': 'buy',
            },
        )
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 50,
                'avg_price': 380,
                'currency': 'HKD',
                'trade_date': recent_date,
                'op_type': 'buy',
            },
        )

        resp = _get(client, '/api/transactions/', {'time_range': '1m'})
        data = resp.get_json()['data']
        assert len(data) == 1
        assert data[0]['trade_date'].startswith('2026-06-10')

    def test_transactions_type_filter(self, client):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
                'op_type': 'buy',
            },
        )
        resp_sell = _get(client, '/api/transactions/', {'type': 'sell'})
        assert len(resp_sell.get_json()['data']) == 0
        resp_buy = _get(client, '/api/transactions/', {'type': 'buy'})
        assert len(resp_buy.get_json()['data']) == 1


class TestPositionUpdateDelete:
    """更新和删除操作"""

    def test_update_position_price(self, client):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        resp = client.patch(f'/api/positions/{pos_id}/', json={'current_price': 400})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['current_price'] == 400
        # 标签应保留
        assert 'type_label' in data
        assert 'allocation_label' in data

    def test_delete_position(self, client):
        _post(
            client,
            '/api/positions/',
            {
                'symbol': 'TEST.DEL',
                'name': '测试删除',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '测试账户',
                'quantity': 10,
                'avg_price': 10,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        resp = client.delete(f'/api/positions/{pos_id}/')
        assert resp.status_code == 200

        list_after = _get(client, '/api/positions/')
        assert len(list_after.get_json()['data']) == 0

    def test_delete_nonexistent_position(self, client):
        resp = client.delete('/api/positions/99999/')
        assert resp.status_code == 404


class TestPositionLabels:
    """标签字段专项测试"""

    def test_position_type_label(self, client):
        """创建持仓后应返回 type_label"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 100,
                'avg_price': 350,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
            },
        )
        data = resp.get_json()['data']
        assert data['type'] == 'stock'
        assert 'type_label' in data
        assert data['type_label'] == '股票'

    def test_position_allocation_label(self, client):
        """传入配置目标应返回中文标签"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': 'AAPL',
                'name': '苹果',
                'type': 'stock',
                'market': 'US',
                'account_name': '富途',
                'quantity': 10,
                'avg_price': 180,
                'allocation': 'speculative',
                'trade_date': '2026-05-01',
            },
        )
        data = resp.get_json()['data']
        assert data['allocation'] == 'speculative'
        assert data['allocation_label'] == '高风险博弈'

    def test_position_list_labels(self, client):
        """列表接口中每个持仓都应包含标签"""
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '000001.SZ',
                'name': '平安银行',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '券商',
                'quantity': 100,
                'avg_price': 10,
            },
        )
        resp = _get(client, '/api/positions/')
        data = resp.get_json()['data']
        for pos in data:
            assert 'type_label' in pos
            assert 'allocation_label' in pos

    def test_sell_below_lot_size(self, client):
        """卖出不足一手时，应只能全部卖出"""
        # 先买入 50 股（不足一手）
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '600519',  # 改为 A 股
                'name': '贵州茅台',
                'type': 'stock',
                'market': 'CN_A',  # 改为 A 股市场
                'account_name': '华泰证券',
                'quantity': 50,
                'avg_price': 350,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # 尝试卖出 30 股（应被拒绝，因为不足一手且未全卖）
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 30, 'avg_price': 400, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 400

        # 全部卖出 50 股（应成功）
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 50, 'avg_price': 400, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 200

    def test_lot_rule_a_stock_main(self, client):
        """A股主板：不足一手只能全卖，一手以上必须整数倍"""
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '000001',
                'name': '平安银行',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '券商',
                'quantity': 80,
                'avg_price': 12.0,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # 不足一手，只能全卖，尝试卖 50 股应被拒
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 50, 'avg_price': 12.5, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 400

        # 全卖 80 股应成功
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 80, 'avg_price': 12.5, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 200

    def test_lot_rule_star_market(self, client):
        """科创板：一手200股，不足一手只能全卖，足一手需整数倍"""
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '688001',
                'name': '华兴源创',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '券商',
                'quantity': 150,
                'avg_price': 30.0,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # 不足一手（200股），只能全卖，尝试卖 100 股应被拒
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 100, 'avg_price': 32.0, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 400

        # 全卖 150 股应成功
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 150, 'avg_price': 32.0, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 200

        # 再买一手（200股），然后尝试卖 201 股（不是整数倍），应被拒
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '688002',
                'name': '测试科创',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '券商',
                'quantity': 200,
                'avg_price': 50.0,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
            },
        )
        list_resp2 = _get(client, '/api/positions/')
        pos_id2 = [p for p in list_resp2.get_json()['data'] if p['symbol'] == 'SH688002'][0]['id']
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id2, 'quantity': 201, 'avg_price': 55.0, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 400

    def test_no_lot_rule_hk(self, client):
        """港股：无一手规则限制，可任意数量卖出"""
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 50,
                'avg_price': 350.0,
                'currency': 'HKD',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # 卖出 30 股，应成功（不受A股一手规则限制）
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 30, 'avg_price': 400.0, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 200

    def test_no_lot_rule_us(self, client):
        """美股：无一手规则限制，可任意数量卖出"""
        _post(
            client,
            '/api/positions/',
            {
                'symbol': 'AAPL',
                'name': '苹果',
                'type': 'stock',
                'market': 'US',
                'account_name': '富途',
                'quantity': 5,
                'avg_price': 180.0,
                'currency': 'USD',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # 卖出 3 股，应成功（美股无一手规则）
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 3, 'avg_price': 200.0, 'trade_date': '2026-05-03'},
        )
        assert resp.status_code == 200


class TestPositionTransactions:
    """测试持仓交易明细端点"""

    def test_get_transactions_success(self, client, db):
        """有交易记录时返回正确列表"""
        ledger = Ledger(name='测试账户', ledger_type='stock')
        db.add(ledger)
        db.commit()

        pos = Position(
            symbol='000001',
            name='平安银行',
            asset_type='stock',
            account_name='测试账户',
            market='CN_A',
            quantity=100,
            avg_price=10.0,
            current_price=12.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()

        # 创建两笔交易
        txn1 = Transaction(
            symbol='000001',  # 新增
            position_name='平安银行',
            account_name='测试账户',
            asset_type='stock',
            txn_type='buy',
            quantity=Money.shares_to_min_unit(100),
            price=Money.yuan_to_cents(10.0),
            amount=Money.yuan_to_cents(1000.0),
            position_id=pos.id,
            confirm_date=date.today(),
        )
        txn2 = Transaction(
            symbol='000001',
            position_name='平安银行',
            account_name='测试账户',
            asset_type='stock',
            txn_type='sell',
            quantity=Money.shares_to_min_unit(50),
            price=Money.yuan_to_cents(12.0),
            amount=Money.yuan_to_cents(600.0),
            position_id=pos.id,
            confirm_date=date.today(),
        )
        db.add_all([txn1, txn2])
        db.commit()

        resp = client.get(f'/api/positions/{pos.id}/transactions/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2
        assert data[0]['txn_type'] == 'buy'
        assert data[1]['txn_type'] == 'sell'

    def test_get_transactions_empty(self, client, db):
        """无关联交易时返回空数组"""
        ledger = Ledger(name='空账户', ledger_type='stock')
        db.add(ledger)
        db.commit()

        pos = Position(
            symbol='000002',
            name='万科A',
            asset_type='stock',
            account_name='空账户',
            market='CN_A',
            quantity=200,
            avg_price=8.0,
            current_price=8.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()

        resp = client.get(f'/api/positions/{pos.id}/transactions/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data == []

    def test_get_transactions_position_not_found(self, client):
        """不存在的持仓返回404"""
        resp = client.get('/api/positions/99999/transactions/')
        assert resp.status_code == 404


class TestDeletePosition:
    """测试删除持仓端点"""

    def test_delete_position_only(self, client, db):
        ledger = Ledger(name='测试账户', ledger_type='stock')
        db.add(ledger)
        db.commit()

        pos = Position(
            symbol='000001',
            name='平安银行',
            asset_type='stock',
            account_name='测试账户',
            market='CN_A',
            quantity=100,
            avg_price=10.0,
            current_price=12.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()

        txn = Transaction(
            symbol='000001',
            position_name='平安银行',
            account_name='测试账户',
            asset_type='stock',
            txn_type='buy',
            quantity=100,
            price=10.0,
            amount=1000.0,
            position_id=pos.id,
            confirm_date=date.today(),
        )
        db.add(txn)
        db.commit()

        pos_id = pos.id
        txn_id = txn.id

        resp = client.delete(f'/api/positions/{pos_id}/?delete_transactions=false')
        assert resp.status_code == 200

        # 用 exists 查询验证，绕过 session 缓存
        pos_exists = db.query(exists().where(Position.id == pos_id)).scalar()
        assert not pos_exists

        txn_exists = db.query(exists().where(Transaction.id == txn_id)).scalar()
        assert txn_exists

    def test_delete_position_with_transactions(self, client, db):
        ledger = Ledger(name='测试账户', ledger_type='stock')
        db.add(ledger)
        db.commit()

        pos = Position(
            symbol='000002',
            name='万科A',
            asset_type='stock',
            account_name='测试账户',
            market='CN_A',
            quantity=200,
            avg_price=8.0,
            current_price=8.0,
            confirm_date=date.today(),
        )
        db.add(pos)
        db.commit()

        txn = Transaction(
            symbol='000002',
            position_name='万科A',
            account_name='测试账户',
            asset_type='stock',
            txn_type='buy',
            quantity=200,
            price=8.0,
            amount=1600.0,
            confirm_date=date.today(),
            position_id=pos.id,
        )
        db.add(txn)
        db.commit()

        # 保存 ID
        pos_id = pos.id
        txn_id = txn.id

        resp = client.delete(f'/api/positions/{pos_id}/?delete_transactions=true')
        assert resp.status_code == 200

        # 用 exists 查询验证，使用本地 ID 避免访问过期对象
        pos_exists = db.query(exists().where(Position.id == pos_id)).scalar()
        assert not pos_exists

        txn_exists = db.query(exists().where(Transaction.id == txn_id)).scalar()
        assert not txn_exists

    def test_delete_position_not_found(self, client):
        """删除不存在的持仓返回404"""
        resp = client.delete('/api/positions/99999/')
        assert resp.status_code == 404
