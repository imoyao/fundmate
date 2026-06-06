# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:58
# File : test_importers.py
"""测试文件导入解析接口（重构后版本：新解析器架构）"""

import hashlib
import io
from datetime import date

from app.core.constants import OP_TYPE_LABEL
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction


class TestStandardCSVParse:
    """新股票标准模板解析测试（使用 standard_stock 模板）"""

    # 新股票模板表头
    STOCK_HEADER = '确认日期,交易日期,股票代码,股票名称,业务类型,数量(股),成交均价,成交金额,手续费,账户名称,合同编号\n'

    def test_parse_valid_csv(self, client, db):
        csv_content = self.STOCK_HEADER + (
            '2025-06-15,2025-06-15,600519,贵州茅台,买入,100,1650.00,165000.00,12.50,华泰证券,\n'
        )
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 1
        row = data[0]
        assert row['symbol'] == 'SH600519'  # 标准化后
        assert row['op_type'] == 'buy'
        assert row['quantity'] == 100
        assert row['price'] == 1650.0
        assert row['fee'] == 12.5
        assert row['is_duplicate'] is False
        assert row['is_cash_transfer'] is False

    def test_missing_required_column(self, client):
        # 缺少必填列 '股票代码'
        csv_content = (
            '确认日期,交易日期,股票名称,业务类型,数量(股),成交均价,成交金额,手续费,账户名称,合同编号\n'
            '2025-06-15,2025-06-15,贵州茅台,买入,100,1650.00,165000.00,12.50,华泰证券,\n'
        )
        resp = client.post(
            '/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test2.csv')}
        )
        assert resp.status_code == 400

    def test_duplicate_detection(self, client, db):
        symbol = 'SH600519'
        trade_date = '2025-06-15'
        business_type = 'buy'
        quantity = 100.0
        price = 1650.0
        source = 'standard_stock'
        # 统一哈希规则
        raw = f'{source}|{trade_date}|{symbol}|{business_type}|{quantity:.4f}|{price:.4f}'
        hash_val = hashlib.md5(raw.encode()).hexdigest()

        txn = Transaction(
            txn_type='buy',
            trade_date=date(2025, 6, 15),
            quantity=quantity,
            price=price,
            amount=165000.0,
            position_name='贵州茅台',
            account_name='华泰证券',
            import_hash=hash_val,
        )
        db.add(txn)
        db.commit()

        csv_content = self.STOCK_HEADER + (
            '2025-06-15,2025-06-15,600519,贵州茅台,买入,100,1650.00,165000.00,12.50,华泰证券,\n'
        )
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')})
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['import_hash'] == hash_val
        assert row['is_duplicate'] is True

    def test_duplicate_detection_on_import(self, client, db):
        """同一份文件导入两次后，第二次解析应显示重复行"""
        csv_content = self.STOCK_HEADER + (
            '2025-06-15,2025-06-15,600519,贵州茅台,买入,100,1650.00,165000.00,12.50,华泰证券,\n'
        )
        # 第一次上传解析
        resp1 = client.post(
            '/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        assert resp1.status_code == 200
        rows1 = resp1.get_json()['data']
        assert len(rows1) == 1
        assert not rows1[0]['is_duplicate']

        # 模拟确认导入（将这条数据真正写入数据库）
        confirm_resp = client.post('/api/importers/confirm', json=rows1)
        assert confirm_resp.status_code == 200
        assert confirm_resp.get_json()['data']['imported'] == 1

        # 第二次上传同一文件
        resp2 = client.post(
            '/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        assert resp2.status_code == 200
        rows2 = resp2.get_json()['data']
        assert len(rows2) == 1
        assert rows2[0]['is_duplicate']  # 应被标记为重复

    def test_import_uses_selected_ledger(self, client, db):
        # 创建 Ledger
        ledger_resp = client.post('/api/ledgers/', json={'name': '华泰证券', 'default_allocation': 'longterm'})
        ledger_name = ledger_resp.get_json()['data']['name']
        # 解析文件
        csv_content = self.STOCK_HEADER + (
            '2025-06-15,2025-06-15,600519,贵州茅台,买入,100,1650.00,165000.00,12.50,华泰证券,\n'
        )
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')})
        rows = resp.get_json()['data']
        # 模拟设置账户和配置目标（前端操作）
        rows[0]['account_name'] = ledger_name
        rows[0]['allocation'] = 'longterm'
        # 确认导入
        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        assert confirm_resp.get_json()['data']['imported'] == 1
        # 验证持仓表中的账户和配置目标
        pos = db.query(Position).filter_by(symbol='SH600519').first()
        assert pos is not None
        assert pos.account_name == '华泰证券'
        assert pos.allocation == 'longterm'

    def test_import_should_not_duplicate_across_ledgers(self, client, db):
        """同一份文件在不同账户下重复导入，应被标记为重复"""
        # 1. 创建两个 Ledger
        client.post('/api/ledgers/', json={'name': '账户A'})
        client.post('/api/ledgers/', json={'name': '账户B'})
        # 2. 第一次导入到账户A
        csv_content = self.STOCK_HEADER + (
            '2025-06-15,2025-06-15,600519,贵州茅台,买入,100,1650.00,165000.00,12.50,账户A,\n'
        )
        resp1 = client.post(
            '/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        rows1 = resp1.get_json()['data']
        rows1[0]['account_name'] = '账户A'
        client.post('/api/importers/confirm', json=rows1)

        # 3. 第二次导入同一文件到账户B
        resp2 = client.post(
            '/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        rows2 = resp2.get_json()['data']
        rows2[0]['account_name'] = '账户B'
        # 第二次导入应成功（因为不同账户），但 import_hash 检测会标记为 duplicate，然后 /confirm 会跳过
        # 因此最终 skipped = 1, imported = 0
        confirm_resp = client.post('/api/importers/confirm', json=rows2)
        data = confirm_resp.get_json()['data']
        assert data['imported'] == 0
        assert data['skipped'] == 1

    # ── 操作类型与孤立交易测试 ──────────────────────────

    def test_sell_with_existing_position(self, client, db):
        """有持仓的情况下卖出，应正常扣减持仓"""
        # 先导入一笔买入
        csv_buy = self.STOCK_HEADER + ('2025-01-10,2025-01-10,601318,中国平安,买入,200,50.00,10000.00,5.00,华泰证券,\n')
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_buy.encode('utf-8')), 'buy.csv')})
        rows = resp.get_json()['data']
        buy_symbol = rows[0]['symbol']  # 标准化后应为 SH601318
        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        assert confirm_resp.get_json()['data']['imported'] == 1

        # 再导入一笔卖出（相同账户和 symbol）
        csv_sell = self.STOCK_HEADER + ('2025-03-15,2025-03-15,601318,中国平安,卖出,100,55.00,5500.00,5.00,华泰证券,\n')
        resp2 = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_sell.encode('utf-8')), 'sell.csv')})
        rows2 = resp2.get_json()['data']
        confirm_resp2 = client.post('/api/importers/confirm', json=rows2)
        assert confirm_resp2.status_code == 200
        data = confirm_resp2.get_json()['data']
        assert data['imported'] == 1
        assert data['orphan_count'] >= 0

        # 验证持仓数量变为 100
        pos = db.query(Position).filter_by(symbol=buy_symbol).first()
        assert pos is not None
        assert pos.quantity == 100

    def test_sell_without_position_creates_orphan(self, client, db):
        """卖出时无对应持仓，应生成孤立交易，不影响持仓表"""
        csv_sell = self.STOCK_HEADER + ('2025-02-20,2025-02-20,000858,五粮液,卖出,50,150.00,7500.00,5.00,华泰证券,\n')
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_sell.encode('utf-8')), 'sell.csv')})
        rows = resp.get_json()['data']
        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        data = confirm_resp.get_json()['data']
        assert data['imported'] == 1
        assert data['orphan_count'] == 1

        # 持仓表不应有任何记录
        assert db.query(Position).filter_by(symbol='SZ000858').first() is None

        # 交易流水应存在且 entry_status='orphan'
        txn = db.query(Transaction).filter_by(txn_type='sell', position_name='五粮液').first()
        assert txn is not None
        assert txn.entry_status == 'orphan'

    def test_dividend_without_position_creates_orphan(self, client, db):
        """分红时无持仓，应生成孤立交易，且金额正确记录"""
        csv_div = self.STOCK_HEADER + ('2025-06-01,,600036,招商银行,现金分红,0,0,30.00,0,招商证券,\n')
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_div.encode('utf-8')), 'div.csv')})
        rows = resp.get_json()['data']
        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        data = confirm_resp.get_json()['data']
        assert data['orphan_count'] == 1

        txn = db.query(Transaction).filter_by(txn_type='dividend', entry_status='orphan').first()
        assert txn is not None
        assert txn.amount == 30.0
        assert txn.quantity == 0

    def test_mixed_operations_time_order_and_orphan_count(self, client, db):
        """
        混合操作：先买后卖 -> 正常扣减；先卖后买 -> 卖出成为孤立；另一卖出无对应 -> 孤立。
        验证按时间排序回放以及 orphan_count 汇总。
        """
        csv_content = self.STOCK_HEADER + (
            '2024-01-15,,600519,贵州茅台,买入,100,1800,180000,0,华泰证券,\n'
            '2024-03-20,,600519,贵州茅台,卖出,50,1850,92500,0,华泰证券,\n'
            '2024-02-10,,000001,平安银行,卖出,200,12,2400,0,华泰证券,\n'
            '2024-06-01,,600519,贵州茅台,现金分红,0,0,500,0,华泰证券,\n'
        )
        resp = client.post(
            '/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'mixed.csv')}
        )
        assert resp.status_code == 200
        rows = resp.get_json()['data']
        assert len(rows) == 4

        # 获取标准化后的 600519 symbol
        buy_row = next(r for r in rows if r['op_type'] == 'buy')
        maotai_symbol = buy_row['symbol']  # SH600519

        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        data = confirm_resp.get_json()['data']
        # 4条记录：buy(持仓创建)、sell(有持仓)、sell(无持仓->孤立)、dividend(有持仓)
        # 孤立数量应为1（000001的卖出）
        assert data['imported'] == 4
        assert data['orphan_count'] == 1

        # 验证持仓状态：贵州茅台应剩 50 股
        pos = db.query(Position).filter_by(symbol=maotai_symbol).first()
        assert pos is not None
        assert pos.quantity == 50

        # 验证分红流水正常关联持仓
        div_txn = db.query(Transaction).filter_by(txn_type='dividend', entry_status=None).first()
        assert div_txn is not None
        assert div_txn.position_id == pos.id
        # 确认孤立交易
        orphan_txn = db.query(Transaction).filter_by(txn_type='sell', entry_status='orphan').first()
        assert orphan_txn is not None
        assert orphan_txn.position_name == '平安银行'

    def test_cash_transfer_imported_on_confirm(self, client, db):
        fake_rows = [
            {
                'symbol': '__CASH__',
                'name': '银行转证券',
                'op_type': 'deposit',
                'amount': 10000,
                'trade_date': '2025-01-01',
                'account_name': '默认证券账户',
                'type': 'cash',  # 关键：资产类型为现金
                'is_duplicate': False,
                'error': None,
                'import_hash': 'fakehash',
                'quantity': 0,
                'price': 0,
                'fee': 0,
                'currency': 'CNY',
                'notes': '',
                'allocation': 'liquid',
            }
        ]
        confirm_resp = client.post('/api/importers/confirm', json=fake_rows)
        data = confirm_resp.get_json()['data']
        # 新架构中资金划转直接 skipped
        assert data['imported'] == 0
        assert data['skipped'] == 1


class TestTHSCSVParser:
    """同花顺交割单解析测试（保持不变）"""

    def test_ths_buy_stock(self, client):
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '110067\t华安转债\t证券买入\t30\t112.5\t3375\t30\t-3375.17\t0.17\t0\t0\t1\t0001008807\t20230203\t华安转债\t0.17\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'ths.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['symbol'] == 'SH110067'  # 沪市可转债
        assert row['op_type'] == 'buy'
        assert row['quantity'] == 30
        assert row['price'] == 112.5
        assert row['fee'] == 0.17  # 佣金
        assert row['contract_id'] == '0001008807'
        assert row['is_cash_transfer'] is False

    def test_ths_cash_transfer(self, client):
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '\t\t银行转证券\t0\t0\t0\t0\t100000\t0\t0\t0\t100000\t\t20221206\t\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'ths.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['is_cash_transfer'] is True
        assert row['op_type'] == 'deposit'
        assert row['amount'] == 100000.0

    def test_ths_dividend(self, client):
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '970164\t银河水星现金添利\t基金红利拨入\t0\t0\t45.52\t0\t45.52\t0\t0\t0\t46.48\t\t20230119\t银河水星现金添利\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'ths.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['op_type'] == 'dividend_cash'
        assert row['is_cash_transfer'] is False

    def test_ths_fund_purchase_amount(self, client):
        """基金申购拨出：成交金额为0时，应以发生金额的绝对值作为交易金额"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '970164\t银河水星现金添利\t基金申购拨出\t0\t0\t0\t0\t-10000\t0\t0\t0\t0\t\t20221223\t银河水星现金添利\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'ths.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['op_type'] == 'buy'
        assert row['amount'] == 10000.0  # 实际扣款金额
        assert row['trade_amount'] == 0.0  # 原始成交金额
        assert row['net_amount'] == 10000.0  # 净发生金额

    def test_ths_duplicate_on_import(self, client, db):
        content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '110067\t华安转债\t证券买入\t30\t112.5\t3375\t30\t-3375.17\t0.17\t0\t0\t1\t0001008807\t20230203\t华安转债\t0.17\t0\t0\t人民币'
        )
        # 第一次解析并导入
        resp1 = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(content.encode('utf-8')), 'ths.csv')}
        )
        assert resp1.status_code == 200
        row1 = resp1.get_json()['data'][0]
        client.post('/api/importers/confirm', json=[row1])

        # 第二次解析
        resp2 = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(content.encode('utf-8')), 'ths.csv')}
        )
        assert resp2.get_json()['data'][0]['is_duplicate']

    def test_ths_tax_confirm_orphan(self, client, db):
        """扣税确认后应生成金额为负的孤儿交易流水"""
        csv_tax = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '600036\t招商银行\t股息红利差异扣税\t0\t0\t0\t0\t-5.0\t0\t0\t0\t0\t\t20230602\t招商银行\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_tax.encode('utf-8')), 'tax.csv')}
        )
        rows = resp.get_json()['data']
        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        data = confirm_resp.get_json()['data']
        assert data['imported'] == 1
        assert data['orphan_count'] == 1

        txn = db.query(Transaction).filter_by(txn_type='dividend_tax').first()
        assert txn is not None
        assert txn.amount == -5.0
        assert txn.entry_status == 'orphan'

    def test_ths_op_type_labels_complete(self):
        """验证所有新增操作类型都有对应的中文标签"""
        required_labels = ['bond_redeem', 'tax']
        for op_type in required_labels:
            assert op_type in OP_TYPE_LABEL, f'OP_TYPE_LABEL 缺少 {op_type}'
        assert OP_TYPE_LABEL['bond_redeem'] == '债券兑付'
        assert OP_TYPE_LABEL['tax'] == '扣税'

    # ── 操作类型映射与关联 ID 测试 ──────────────────────────

    def test_ths_bond_interest_parsing(self, client):
        """债券兑息应解析为 dividend，债券兑息兑付应解析为 tax"""
        # 构造两条记录：债券兑息 + 债券兑息兑付
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '113527\t维格转债\t债券兑息\t20\t2.0\t40.0\t0\t40.0\t0\t0\t0\t1\t\t20240123\t维格转债\t0\t0\t0\t人民币\n'
            '113527\t维格转债\t债券兑息兑付\t20\t2.0\t8.0\t0\t-8.0\t0\t0\t0\t1\t\t20240123\t维格转债\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths',
            data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'interest.csv')},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 2

        # 第一条：债券兑息
        row1 = data[0]
        assert row1['op_type'] == 'dividend_cash'
        assert row1['op_type_label'] == '现金分红'
        assert row1['amount'] == 40.0
        assert row1['notes'] == '债券兑息'
        assert row1.get('is_cash_transfer') is False

        # 第二条：债券兑息兑付
        row2 = data[1]
        assert row2['op_type'] == 'tax'
        assert row2['op_type_label'] == '扣税'
        assert row2['amount'] == -8.0  # 注意：解析时 amount 取的是成交金额列，这里是 8.0，发生金额是 -8.0
        assert row2['net_amount'] == 8.0  # net_amount 为绝对值的发生金额
        assert row2['notes'] == '债券兑息兑付'

    def test_ths_bond_interest_link_group(self, client):
        """同日期同代码的债券兑息和债券兑息兑付应获得相同的 link_group_id"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '113527\t维格转债\t债券兑息\t20\t2.0\t40.0\t0\t40.0\t0\t0\t0\t1\t\t20240123\t维格转债\t0\t0\t0\t人民币\n'
            '113527\t维格转债\t债券兑息兑付\t20\t2.0\t8.0\t0\t-8.0\t0\t0\t0\t1\t\t20240123\t维格转债\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths',
            data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'interest.csv')},
        )
        assert resp.status_code == 200
        rows = resp.get_json()['data']
        assert len(rows) == 2

        # 两条记录应有相同的 link_group_id
        gid1 = rows[0].get('link_group_id')
        gid2 = rows[1].get('link_group_id')
        assert gid1 is not None
        assert gid1 == gid2

    def test_ths_bond_redeem_parse(self, client):
        """债券兑付应解析为 bond_redeem"""
        csv_redeem = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '110067\t华安转债\t债券兑付\t30\t100.0\t3000.0\t0\t3000.0\t0\t0\t0\t1\t\t20230601\t华安转债\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_redeem.encode('utf-8')), 'redeem.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['op_type'] == 'bond_redeem'
        assert row['op_type_label'] == '债券兑付'
        assert row['amount'] == 3000.0

    def test_ths_tax_parse(self, client):
        """股息红利差异扣税应解析为 tax，且标签为‘扣税’"""
        csv_tax = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '600036\t招商银行\t股息红利差异扣税\t0\t0\t0\t0\t-5.0\t0\t0\t0\t0\t\t20230602\t招商银行\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_tax.encode('utf-8')), 'tax.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['op_type'] == 'tax'
        assert row['op_type_label'] == '扣税'

    def test_ths_bond_redeem_confirm_orphan(self, client, db):
        """债券兑付确认后应生成 orphan 流水"""
        # 先创建持仓
        csv_buy = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '110067\t华安转债\t证券买入\t30\t112.5\t3375.0\t30\t-3375.17\t0.17\t0\t0\t1\t0001\t20230203\t华安转债\t0.17\t0\t0\t人民币'
        )
        resp1 = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_buy.encode('utf-8')), 'buy.csv')}
        )
        rows = resp1.get_json()['data']
        client.post('/api/importers/confirm', json=rows)

        # 债券兑付
        csv_redeem = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '110067\t华安转债\t债券兑付\t30\t100.0\t3000.0\t0\t3000.0\t0\t0\t0\t1\t\t20230601\t华安转债\t0\t0\t0\t人民币'
        )
        resp2 = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_redeem.encode('utf-8')), 'redeem.csv')}
        )
        rows2 = resp2.get_json()['data']
        confirm_resp = client.post('/api/importers/confirm', json=rows2)
        assert confirm_resp.status_code == 200
        data = confirm_resp.get_json()['data']
        assert data['imported'] == 1
        assert data['orphan_count'] == 1

        txn = db.query(Transaction).filter_by(txn_type='bond_redeem').first()
        assert txn is not None
        assert txn.amount == 3000.0
        assert txn.entry_status == 'orphan'

    def test_confirm_import_rollback_on_error(self, client, db):
        """测试导入过程中出错时，已处理的数据应回滚"""
        # 导入一条正常买入
        csv_buy = (
            '确认日期,交易日期,股票代码,股票名称,业务类型,数量(股),成交均价,成交金额,手续费,账户名称,合同编号\n'
            '2024-01-15,,600519,贵州茅台,买入,100,1800,180000,0,华泰证券,\n'
        )
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_buy.encode('utf-8')), 'buy.csv')})
        rows = resp.get_json()['data']
        # 在中间插入一条无效记录，使导入失败
        rows.append(
            {
                'symbol': 'invalid',
                'name': '',
                'op_type': 'buy',
                'quantity': -1,
                'price': 0,
                'trade_date': '2024-01-16',
                'account_name': '华泰证券',
            }
        )
        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        data = confirm_resp.get_json()['data']
        assert data['imported'] == 1  # 第一条成功导入
        assert len(data['errors']) == 1  # 第二条被记录为错误

    def test_ths_money_fund_code_normalization(self, client):
        """券商现金管理产品代码应被识别为 money_fund"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '970164\t银河水星现金添利\t基金申购拨出\t0\t0\t0\t0\t-10000\t0\t0\t0\t0\t\t20221223\t银河水星现金添利\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['type'] == 'money_fund'
        assert row['allocation'] == 'liquid'

    def test_ths_money_fund_import(self, client, db):
        """现金管理产品应被正确导入为孤立交易，不影响持仓"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '970164\t银河水星现金添利\t基金申购拨出\t0\t0\t0\t0\t-10000\t0\t0\t0\t0\t\t20221223\t银河水星现金添利\t0\t0\t0\t人民币'
        )
        # 先导入一条，确认不会报错
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        rows = resp.get_json()['data']
        confirm_resp = client.post('/api/importers/confirm', json=rows)
        assert confirm_resp.status_code == 200
        data = confirm_resp.get_json()['data']
        assert data['imported'] == 1
        assert data['orphan_count'] == 1

        # 验证流水已生成
        txn = db.query(Transaction).filter_by(txn_type='buy', entry_status='orphan').first()
        assert txn is not None
        assert txn.amount == 10000.0

    def test_ths_money_fund_duplicate(self, client, db):
        """现金管理产品重复导入应被检测"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '970164\t银河水星现金添利\t基金申购拨出\t0\t0\t0\t0\t-10000\t0\t0\t0\t0\t\t20221223\t银河水星现金添利\t0\t0\t0\t人民币'
        )
        # 第一次导入
        resp1 = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        rows1 = resp1.get_json()['data']
        confirm1 = client.post('/api/importers/confirm', json=rows1)
        assert confirm1.get_json()['data']['imported'] == 1

        # 第二次导入同一文件
        resp2 = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')}
        )
        rows2 = resp2.get_json()['data']
        assert rows2[0]['is_duplicate']  # 应被标记为重复

        # 确认导入应跳过重复行
        confirm2 = client.post('/api/importers/confirm', json=rows2)
        data = confirm2.get_json()['data']
        assert data['imported'] == 0
        assert data['skipped'] == 1

    def test_ths_cash_transfer_symbol_is_cash(self, client):
        """资金划转记录的 symbol 应为 __CASH__，且 is_cash_transfer 为 True"""
        csv_content = (
            '证券代码\t证券名称\t操作\t成交数量\t成交均价\t成交金额\t股票余额\t发生金额\t手续费\t印花税\t其他杂费\t资金余额\t合同编号\t交收日期\t证券中文全称\t佣金\t过户费\t清算费(B股)\t币种\n'
            '\t\t银行转证券\t0\t0\t0\t0\t100000\t0\t0\t0\t100000\t\t20221206\t\t0\t0\t0\t人民币'
        )
        resp = client.post(
            '/api/importers/parse?template=ths', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'ths.csv')}
        )
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['symbol'] == '__CASH__'
        assert row['is_cash_transfer'] is True
        assert row['op_type'] == 'deposit'
        assert row['name'] == '银行转证券'
        assert row['amount'] == 100000.0
