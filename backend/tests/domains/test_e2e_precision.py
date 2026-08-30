# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/15 22:54
# File : test_e2e_precision.py
# tests/domains/test_e2e_precision.py
"""端到端精度验证：确保写入、读取、计算全链路使用一致的单位"""

from unittest.mock import patch

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction


class TestE2EPrecision:
    def test_buy_and_read_position(self, client, db):
        """模拟买入一只股票，验证返回的金额和份额是否与输入一致"""
        ledger = Ledger(name='测试账户', ledger_type='stock')
        db.add(ledger)
        db.commit()

        # 1. 通过 API 买入
        # 视图会用真实行情校验价格区间（use_live_fallback=True），本测试只验证
        # 单位换算链路、与真实行情无关 → mock 掉以隔离网络。否则测试结果会随
        # 行情漂移（1600 元未必落在 2026-06-15 的真实区间内，曾致 400 失败）。
        with patch(
            'app.domains.positions.views.resolve_security_price_range',
            return_value=None,
        ):
            resp = client.post(
                '/api/positions/',
                json={
                    'symbol': '600519',
                    'name': '贵州茅台',
                    'type': 'stock',
                    'market': 'CN_A',
                    'account_name': '测试账户',
                    'quantity': 100,
                    'avg_price': 1600.0,
                    'currency': 'CNY',
                    'trade_date': '2026-06-15',
                    'op_type': 'buy',
                },
            )
        assert resp.status_code == 200
        data = resp.json['data']
        assert data['quantity'] == 100.0  # 份额
        assert data['avg_price'] == 1600.0  # 元
        assert data['current_price'] == 1600.0  # 元

        # 2. 通过持仓列表查询
        list_resp = client.get('/api/positions/')
        assert list_resp.status_code == 200
        items = list_resp.json['data']
        assert len(items) == 1
        pos = items[0]
        assert pos['quantity'] == 100.0
        assert pos['avg_price'] == 1600.0
        assert pos['current_price'] == 1600.0

        # 3. 验证数据库内部存储单位（分/最小单位）
        db_pos = db.query(Position).first()
        assert db_pos.quantity == 1000000  # 100股 × 10000
        assert db_pos.avg_price == 16000000  # 1600元 × 10000（price_units）
        assert db_pos.current_price == 16000000

        # 4. 验证交易流水
        txn = db.query(Transaction).first()
        assert txn.quantity == 1000000
        assert txn.price == 16000000
        assert txn.amount == 16000000  # 100股 × 1600元 = 160000元 → 16000000分

        # 5. 验证交易流水 API 返回值
        txn_resp = client.get('/api/transactions/')
        assert txn_resp.status_code == 200
        txn_data = txn_resp.json['data'][0]
        assert txn_data['quantity'] == 100.0
        assert txn_data['price'] == 1600.0
        assert txn_data['amount'] == 160000.0
