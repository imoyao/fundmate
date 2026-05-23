# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:58
# File : test_importers.py
"""测试文件导入解析接口"""

import hashlib
import io
from datetime import date

from app.domains.importers.parser import TransactionParser
from app.domains.importers.templates import STANDARD_TEMPLATE
from app.domains.transactions.models import Transaction


class TestStandardCSVParse:
    """标准模板解析测试"""

    def test_parse_valid_csv(self, client, db):
        csv_content = (
            '代码,名称,市场,产品类型,所属账户,操作类型,数量,成交价格,币种,交易日期,手续费,备注\n'
            '00700.HK,腾讯控股,CN_HK,stock,富途证券,buy,100,350.00,HKD,2025-06-15,0.50,初始建仓'
        )
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data) == 1
        row = data[0]
        assert row['symbol'] == 'HK00700'  # 标准化后
        assert row['op_type'] == 'buy'
        assert row['quantity'] == 100
        assert row['price'] == 350.0
        assert row['fee'] == 0.5
        assert row['is_duplicate'] is False
        assert row['is_cash_transfer'] is False

    def test_missing_required_column(self, client):
        csv_content = (
            '代码,名称,市场,产品类型,所属账户,操作类型,数量,成交价格,币种,交易日期\n'
            '00700.HK,腾讯控股,CN_HK,stock,富途证券,buy,100,350.00,HKD,2025-06-15'
        )
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')})
        assert resp.status_code == 200  # 缺少手续费列（但手续费是可选，实际应通过）
        # 标准模板手续费可选，所以不应该报错，调整预期
        # 需要检查模板定义：required_columns 不含手续费，因此这条应该成功
        # 实际上我们模板 required_columns 是 代码,操作类型,数量,成交价格,交易日期，不含手续费
        # 所以上面用例会成功，这里改一下预期
        # 我们改成缺少必要列"成交价格"的用例
        csv_content2 = (
            '代码,名称,市场,产品类型,所属账户,操作类型,数量,币种,交易日期,手续费,备注\n'
            '00700.HK,腾讯控股,CN_HK,stock,富途证券,buy,100,HKD,2025-06-15,0.50,初始建仓'
        )
        resp2 = client.post(
            '/api/importers/parse', data={'file': (io.BytesIO(csv_content2.encode('utf-8')), 'test2.csv')}
        )
        assert resp2.status_code == 400

    def test_duplicate_detection(self, client, db):
        parser = TransactionParser(STANDARD_TEMPLATE)
        row_data = {
            'symbol': 'HK00700',
            'trade_date': '2025-06-15',
            'op_type': 'buy',
            'quantity': 100.0,
            'price': 350.0,
        }
        raw = f"{row_data['symbol']}|{row_data['trade_date']}|{row_data['op_type']}|{row_data['quantity']}|{row_data['price']}"
        hash_val = hashlib.md5(raw.encode()).hexdigest()

        txn = Transaction(
            txn_type='buy',
            trade_date=date(2025, 6, 15),
            quantity=100,
            price=350.0,
            amount=35000.0,
            position_name='腾讯控股',
            account_name='富途证券',
            import_hash=hash_val,
        )
        db.add(txn)
        db.commit()

        csv_content = (
            '代码,名称,市场,产品类型,所属账户,操作类型,数量,成交价格,币种,交易日期,手续费,备注\n'
            '00700.HK,腾讯控股,CN_HK,stock,富途证券,buy,100,350.00,HKD,2025-06-15,0.50,重复导入'
        )
        resp = client.post('/api/importers/parse', data={'file': (io.BytesIO(csv_content.encode('utf-8')), 'test.csv')})
        assert resp.status_code == 200
        row = resp.get_json()['data'][0]
        assert row['import_hash'] == hash_val
        assert row['is_duplicate'] is True

    def test_duplicate_detection_on_import(self, client, db):
        """同一份文件导入两次后，第二次解析应显示重复行"""
        csv_content = (
            '代码,名称,市场,产品类型,所属账户,操作类型,数量,成交价格,币种,交易日期,手续费,备注\n'
            '00700.HK,腾讯控股,CN_HK,stock,富途证券,buy,100,350.00,HKD,2025-06-15,0.50,初始建仓'
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
        csv_content = (
            '代码,名称,市场,产品类型,所属账户,操作类型,数量,成交价格,币种,交易日期,手续费,备注\n'
            '00700.HK,腾讯控股,CN_HK,stock,富途证券,buy,100,350.00,HKD,2025-06-15,0.50,建仓'
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
        from app.domains.positions.models import Position

        pos = db.query(Position).filter_by(symbol='HK00700').first()
        assert pos is not None
        assert pos.account_name == '华泰证券'
        assert pos.allocation == 'longterm'

    def test_import_should_not_duplicate_across_ledgers(self, client, db):
        """同一份文件在不同账户下重复导入，应被标记为重复"""
        # 1. 创建两个 Ledger
        client.post('/api/ledgers/', json={'name': '账户A'})
        client.post('/api/ledgers/', json={'name': '账户B'})
        # 2. 第一次导入到账户A
        csv_content = (
            '代码,名称,市场,产品类型,所属账户,操作类型,数量,成交价格,币种,交易日期,手续费,备注\n'
            '00700.HK,腾讯控股,CN_HK,stock,富途证券,buy,100,350.00,HKD,2025-06-15,0.50,建仓'
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
        # 预期：标记为重复，因为 import_hash 不随账户变化
        assert rows2[0]['is_duplicate']

        # 确认导入会跳过重复行
        confirm_resp = client.post('/api/importers/confirm', json=rows2)
        assert confirm_resp.get_json()['data']['imported'] == 0
        assert confirm_resp.get_json()['data']['skipped'] == 1


class TestTHSCSVParser:
    """同花顺交割单解析测试"""

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
        assert row['op_type'] == 'dividend'
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
