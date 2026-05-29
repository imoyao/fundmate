# backend/tests/test_positions.py
"""测试持仓相关接口及标签字段"""

from datetime import date, timedelta


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
                'purchase_date': '2026-05-01',
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
                'purchase_date': '2026-05-01',
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
                'purchase_date': '2026-05-02',
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
                'purchase_date': '2026-05-01',
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
                'purchase_date': '2026-05-03',
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
                'purchase_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 50, 'avg_price': 190, 'purchase_date': '2026-05-05'},
        )
        assert resp.status_code == 200
        assert resp.get_json()['message'] == '持仓已清空'

    def test_sell_missing_position_id_fails(self, client):
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'quantity': 10, 'avg_price': 100, 'purchase_date': '2026-05-01'},
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
                'purchase_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 20, 'avg_price': 200, 'purchase_date': '2026-05-02'},
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
                'purchase_date': old_date,
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
                'purchase_date': recent_date,
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
                'purchase_date': '2026-05-01',
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
                'purchase_date': '2026-05-01',
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
                'purchase_date': '2026-05-01',
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
                'purchase_date': '2026-05-01',
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
                'purchase_date': '2026-05-01',
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
                'symbol': '00700.HK',
                'name': '腾讯',
                'type': 'stock',
                'market': 'CN_HK',
                'account_name': '富途',
                'quantity': 50,
                'avg_price': 350,
                'currency': 'HKD',
                'purchase_date': '2026-05-01',
            },
        )
        list_resp = _get(client, '/api/positions/')
        pos_id = list_resp.get_json()['data'][0]['id']

        # 尝试卖出 30 股（应被拒绝，因为不足一手且未全卖）
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 30, 'avg_price': 400, 'purchase_date': '2026-05-03'},
        )
        assert resp.status_code == 400  # 或前端限制无法触发

        # 全部卖出 50 股（应成功）
        resp = _post(
            client,
            '/api/positions/',
            {'op_type': 'sell', 'position_id': pos_id, 'quantity': 50, 'avg_price': 400, 'purchase_date': '2026-05-03'},
        )
        assert resp.status_code == 200
