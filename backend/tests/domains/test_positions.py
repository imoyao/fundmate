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
from app.services.importer.records import compute_position_hash
from app.services.position_service import PositionService


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
        assert data[0]['trade_date'] == recent_date

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
                # 用港股市场（无整手限制），避免买入碎股被 A股整手规则拦截
                'market': 'CN_HK',
                'account_name': '测试账户',
                'quantity': 10,
                'avg_price': 10,
                'currency': 'HKD',
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

    def test_sell_below_lot_size(self, client, db):
        """卖出不足一手时，应只能全部卖出

        碎股来源：A股碎股只能由分红/配股/拆细等产生（买入不允许碎股），
        此处用 db 直接构造一条 50 股碎股持仓来模拟该真实状态。
        """
        ledger = Ledger(name='碎股测试账本', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        db.add(
            Position(
                symbol='SH600519',
                name='贵州茅台',
                asset_type='stock',
                market='CN_A',
                ledger_id=ledger.id,
                family_id=1,
                quantity=Money.shares_to_min_unit(50),
                avg_price=35000,  # 分
                source='dividend',
            )
        )
        db.commit()
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

    def test_lot_rule_a_stock_main(self, client, db):
        """A股主板：不足一手只能全卖，一手以上必须整数倍

        碎股持仓由分红产生（买入不允许碎股），用 db 直接构造 80 股碎股。
        """
        ledger = Ledger(name='主板碎股账本', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        db.add(
            Position(
                symbol='SZ000001',
                name='平安银行',
                asset_type='stock',
                market='CN_A',
                ledger_id=ledger.id,
                family_id=1,
                quantity=Money.shares_to_min_unit(80),
                avg_price=1200,  # 分
                source='dividend',
            )
        )
        db.commit()
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

    def test_lot_rule_star_market(self, client, db):
        """科创板：一手200股，不足一手只能全卖，足一手需整数倍

        碎股来源：科创板碎股由分红/配股产生（买入不允许碎股），用 db 直接
        构造 688001 的 150 股碎股持仓模拟该真实状态。
        """
        ledger = Ledger(name='科创板碎股账本', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.flush()
        db.add(
            Position(
                symbol='SH688001',
                name='华兴源创',
                asset_type='stock',
                market='CN_A',
                ledger_id=ledger.id,
                family_id=1,
                quantity=Money.shares_to_min_unit(150),
                avg_price=3000,  # 分
                source='dividend',
            )
        )
        db.commit()
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


class TestPositionMarketValuePnl:
    """分页列表应产出 market_value/pnl（修复 Inventory「市值/盈亏」恒 ¥0.00）"""

    def test_list_contains_market_value_and_pnl(self, client):
        """创建持仓并更新现价后，分页列表应返回正确的市值与浮动盈亏"""
        _post(
            client,
            '/api/positions/',
            {
                'symbol': '600519',
                'name': '贵州茅台',
                'type': 'stock',
                'market': 'CN_A',
                'account_name': '华泰证券',
                'quantity': 100,
                'avg_price': 10.5,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # 更新现价为 12.5 元（默认 0 分 → 1250 分）
        resp = client.patch(f'/api/positions/{pos_id}/', json={'current_price': 12.5})
        assert resp.status_code == 200

        data = _get(client, '/api/positions/').get_json()['data']
        assert len(data) == 1
        item = data[0]
        assert 'market_value' in item
        assert 'pnl' in item
        # 市值 = 100 份 × 12.5 元 = 1250.0；盈亏 = (12.5 - 10.5) × 100 = 200.0
        assert item['market_value'] == 1250.0
        assert item['pnl'] == 200.0

    def test_pnl_zero_when_no_cost_price(self, client):
        """未设置成本价（avg_price=0）时 pnl 应为 0.0 而非报错"""
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
                'avg_price': 10.0,
                'currency': 'CNY',
                'trade_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # avg_price 置 0（模拟无成本价的持仓）
        resp = client.patch(f'/api/positions/{pos_id}/', json={'avg_price': 0})
        assert resp.status_code == 200

        data = _get(client, '/api/positions/').get_json()['data']
        item = data[0]
        assert item['pnl'] == 0.0
        # 市值仍应按现价计算
        assert item['market_value'] == 100 * 10.0

    def test_market_value_in_create_response(self, client):
        """创建持仓的响应也应含 market_value/pnl（复用 enrich_position_dict）"""
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
                'currency': 'USD',
                'trade_date': '2026-05-01',
            },
        )
        data = resp.get_json()['data']
        assert 'market_value' in data
        assert 'pnl' in data
        # 新建时 current_price 初始化为成本价（position_service:232）
        # → 市值 10 股 × 180 元 = 1800.0，盈亏 0.0
        assert data['market_value'] == 1800.0
        assert data['pnl'] == 0.0


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


class TestTransactionAssetType:
    """历史债回归：手动路径流水 asset_type 必须正确落库。

    背景：PositionCreate.asset_type 使用 validation_alias='type'，
    model_dump() 输出 key 为 `asset_type`（而非别名 `type`），
    历史实现 `data.get('type')` 恒为 None → 流水 asset_type 写 NULL。
    修复后统一经 _get_asset_type 兼容两个 key。
    """

    def test_buy_creates_txn_with_asset_type(self, client):
        """手动买入（请求体用 asset_type）→ 流水 asset_type 正确落库"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '000001',
                'name': '某基金',
                'asset_type': 'fund',
                'market': 'CN_A',
                'account_name': '测试账户',
                'quantity': 1000,
                'avg_price': 1.5,
                'trade_date': '2026-05-01',
                'op_type': 'buy',
            },
        )
        assert resp.status_code == 200
        pos_id = resp.get_json()['data']['id']

        # 验证流水 asset_type 已正确落库（修复前为 NULL）
        with client.application.app_context():
            from app.core.database import get_db

            with get_db() as db:
                txn = db.query(Transaction).filter(Transaction.position_id == pos_id).first()
                assert txn is not None
                assert txn.asset_type == 'fund'

    def test_sell_creates_txn_with_asset_type(self, client, db, make_position):
        """手动卖出 → 流水 asset_type 正确落库"""
        pos = make_position(
            symbol='000001',
            name='某股票',
            asset_type='stock',
            account_name='测试账户',
            market='CN_A',
            quantity=100,
            avg_price=10.0,
            current_price=10.0,
        )
        resp = _post(
            client,
            '/api/positions/',
            {
                'position_id': pos.id,
                'asset_type': 'stock',
                'quantity': 100,
                'avg_price': 11.0,
                'trade_date': '2026-05-02',
                'op_type': 'sell',
            },
        )
        assert resp.status_code == 200

        txn = db.query(Transaction).filter(Transaction.position_id == pos.id).first()
        assert txn is not None
        assert txn.asset_type == 'stock'

    def test_orphan_cash_txn_keeps_asset_type(self, client, db):
        """现金管理产品（货基）孤儿流水 → asset_type 正确落库"""
        resp = _post(
            client,
            '/api/positions/',
            {
                'symbol': '511880',
                'name': '银华日利',
                'asset_type': 'money_fund',
                'market': 'CN_A',
                'account_name': '证券账户',
                'quantity': 10000,
                'avg_price': 100.0,
                'trade_date': '2026-05-03',
                'op_type': 'buy',
            },
        )
        assert resp.status_code == 200

        txn = (
            db.query(Transaction)
            .filter(Transaction.asset_type == 'money_fund')
            .filter(Transaction.entry_status == 'orphan')
            .first()
        )
        assert txn is not None


class TestPositionImportHash:
    """Issue #928：持仓去重哈希 + 溯源字段 + 撞 key upsert 语义。

    持仓是汇总结果，import_hash = source|ledger_id|symbol|snapshot_date，
    不含数量/成本，故同一天同一产品只保留一条汇总记录（撞 key 转 upsert）。
    """

    def _make_ledger(self, db, name='证券账户A'):
        ledger = db.query(Ledger).filter_by(name=name).first()
        if ledger is None:
            ledger = Ledger(name=name, ledger_type='stock', family_id=1)
            db.add(ledger)
            db.flush()
        return ledger.id

    def _buy(self, db, ledger_id, source, symbol='600519', qty=100, price=1800.0):
        data = {
            'symbol': symbol,
            'name': '贵州茅台',
            'asset_type': 'stock',
            'market': 'CN_A',
            'ledger_id': ledger_id,
            'family_id': 1,
            'quantity': qty,
            'avg_price': price,
            'op_type': 'buy',
            'source': source,
        }
        return PositionService.process_buy_or_deposit(db, data)

    def test_import_hash_generated_and_source_persisted(self, db):
        """新建持仓应生成 import_hash 并落库 source 字段（白名单透传）。"""
        ledger_id = self._make_ledger(db)
        pos = self._buy(db, ledger_id, source='manual')
        db.commit()
        assert pos.import_hash is not None
        assert len(pos.import_hash) == 32  # md5 hex
        assert pos.source == 'manual'
        # 与 compute_position_hash 口径一致（无 confirm_date 降级为落库当日）
        expected = compute_position_hash(
            source='manual', ledger_id=ledger_id, symbol='SH600519', snapshot_date=date.today()
        )
        assert pos.import_hash == expected

    def test_duplicate_import_hash_upserts_not_duplicate(self, db):
        """同内容两次导入（不同 source，同 ledger/symbol/同日）撞 hash → upsert 合并，不产生两条。"""
        ledger_id = self._make_ledger(db)
        # 第一次：手动录入
        p1 = self._buy(db, ledger_id, source='manual', qty=100, price=1800.0)
        # 第二次：交割单导入，同 ledger/symbol/同日 → 相同 import_hash → 应 upsert
        # 注意：二次买入 100 股（A股一手起买），验证买入不受持有量限制、且撞 hash 合并
        p2 = self._buy(db, ledger_id, source='broker_ht', qty=100, price=1800.0)
        db.commit()
        positions = db.query(Position).filter_by(ledger_id=ledger_id, symbol='SH600519').all()
        assert len(positions) == 1  # 未产生两条
        assert positions[0].id == p1.id == p2.id  # upsert 同一记录
        # 数量累加 100+100=200
        assert positions[0].quantity == Money.shares_to_min_unit(200)
        # 溯源字段保留（以末次写入的 source 为准）
        assert positions[0].source == 'broker_ht'

    def test_different_day_distinct_hash(self, db):
        """不同快照日 → 不同 import_hash（即便 source/ledger/symbol 相同）。"""
        ledger_id = self._make_ledger(db)
        h_today = compute_position_hash('manual', ledger_id, 'SH600519', date.today())
        h_yesterday = compute_position_hash('manual', ledger_id, 'SH600519', date.today() - timedelta(days=1))
        assert h_today != h_yesterday

    def test_missing_confirm_date_falls_back_to_today(self, db):
        """未提供 confirm_date 时快照日降级为落库当日（不产生 'unknown' 占位）。"""
        ledger_id = self._make_ledger(db)
        pos = self._buy(db, ledger_id, source='manual')
        db.commit()
        expected = compute_position_hash(
            source='manual', ledger_id=ledger_id, symbol='SH600519', snapshot_date=date.today()
        )
        assert pos.import_hash == expected

    def test_buy_qty_not_limited_by_holdings(self, db):
        """回归：买入数量只校验自身合法（>0、起买单位/步长），不受当前持有量限制。

        历史上 validate_buy 误把 current_hold 卷入买入校验，导致「已持有 100 股时
        再次买入被错误拦截」。本测试确认：即便已持有，再次买入一手仍成功，且
        「买入不能超过持仓」这种错误约束不存在（那是卖出的职责）。
        """
        ledger_id = self._make_ledger(db)
        p1 = self._buy(db, ledger_id, source='manual', qty=100, price=1800.0)
        db.commit()
        assert p1 is not None
        # 已持有 100 股，再次买入一手（100 股）应成功，而非被「超过持有」误拦
        p2 = self._buy(db, ledger_id, source='manual', qty=100, price=1800.0)
        db.commit()
        # 撞 import_hash upsert 合并为 200 股，证明买入未被持有量上限拦截
        assert p2.id == p1.id
        assert p2.quantity == Money.shares_to_min_unit(200)
