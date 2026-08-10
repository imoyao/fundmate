# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 19:34
# File : test_funds.py
from datetime import date, timedelta

from app.core.money import Money
from app.domains.funds.models import DailyWorth, FeeRatio, Fund, Manager, PurchaseRule, RedeemRule
from app.services.fund_service import FundService


def test_infer_fund_currency_default_cny():
    """境内基金与无特征名称默认人民币"""
    assert FundService.infer_fund_currency('华夏成长混合', '华夏成长') == 'CNY'
    assert FundService.infer_fund_currency() == 'CNY'
    assert FundService.infer_fund_currency('   ') == 'CNY'


def test_infer_fund_currency_foreign_share():
    """QDII 外币份额按名称特征推导对应币种"""
    assert FundService.infer_fund_currency('广发纳斯达克100ETF联接(QDII)美元现汇C', '纳指ETF联接') == 'USD'
    assert FundService.infer_fund_currency('易方达恒生H股ETF联接(QDII)港币A', '恒生H股') == 'HKD'
    assert FundService.infer_fund_currency('某基金(QDII)日元份额', '') == 'JPY'


def test_infer_fund_currency_rmb_share_counted_as_cny():
    """QDII 人民币份额仍为人民币"""
    assert FundService.infer_fund_currency('广发纳斯达克100ETF联接(QDII)人民币C', '纳指ETF联接') == 'CNY'
    # 名称同时含"美元"与"人民币"时必须判定为人民币（edge case，见实现注释）
    assert FundService.infer_fund_currency('中银美元债债券(QDII)人民币A', '中银美元债') == 'CNY'


def test_search_funds(client, db):
    f = Fund(fund_code='000001', name='华夏成长', pinyin_abbr='HXCZ')
    db.add(f)
    db.commit()

    resp = client.get('/api/funds/search/', query_string={'q': '华夏'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['code'] == '000001'
    assert data[0]['type'] == 'fund'


def test_search_managers(client, db):
    m = Manager(mgr_code='MGR001', name='李四', mgr_type='fund_manager')
    db.add(m)
    db.commit()

    resp = client.get('/api/funds/managers/search/', query_string={'q': '李四'})
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['name'] == '李四'
    assert data[0]['type'] == 'fund_manager'


def test_search_funds_empty(client):
    resp = client.get('/api/funds/search/', query_string={'q': 'zzz_not_exist'})
    data = resp.get_json()['data']
    assert len(data) == 0


def test_get_fund_nav_from_db(client, db):
    """数据库中已有净值时直接返回"""
    fund = Fund(fund_code='000001', name='测试基金')
    db.add(fund)
    db.add(DailyWorth(fund_code='000001', date=date(2025, 1, 15), unit_nav=1.2345, acc_nav=1.2345))
    db.commit()

    resp = client.post('/api/funds/nav/', json={'symbols': ['000001'], 'date': '2025-01-15'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) == 1
    assert data[0]['fund_code'] == '000001'
    assert data[0]['unit_nav'] == 1.2345
    assert data[0]['date'] == '2025-01-15'


def test_get_fund_nav_no_data(client, db):
    """数据库中无净值时，触发实时拉取（可能失败或返回空）"""
    resp = client.post('/api/funds/nav/', json={'symbols': ['999999'], 'date': '2025-01-15'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data == []  # 返回空数组


def test_get_fund_nav_invalid_date(client):
    """日期格式错误应返回 400"""
    resp = client.post(
        '/api/funds/nav/',
        json={
            'symbols': ['000001'],
            'date': '2025/01/15',  # 错误格式
        },
    )
    assert resp.status_code == 422


def test_get_fund_nav_missing_params(client):
    """缺少必填参数应返回 400"""
    resp = client.post(
        '/api/funds/nav/',
        json={
            'symbols': ['000001']
            # 缺少 date
        },
    )
    assert resp.status_code == 422

    resp = client.post(
        '/api/funds/nav/',
        json={
            'date': '2025-01-15'
            # 缺少 symbols
        },
    )
    assert resp.status_code == 422


def test_get_fund_nav_empty_symbols(client):
    """symbols 为空数组应返回 400"""
    resp = client.post('/api/funds/nav/', json={'symbols': [], 'date': '2025-01-15'})
    assert resp.status_code == 422


def test_get_fund_nav_realtime_fetch(client, db):
    """正向测试：数据库中无净值时，通过 xalpha 实时拉取并返回"""
    fund = db.query(Fund).filter_by(fund_code='000001').first()
    if not fund:
        fund = Fund(fund_code='000001', name='华夏成长')
        db.add(fund)
        db.commit()

    test_date = date.today() - timedelta(days=1)
    if test_date.weekday() >= 5:
        test_date -= timedelta(days=test_date.weekday() - 4)

    resp = client.post('/api/funds/nav/', json={'symbols': ['000001'], 'date': test_date.strftime('%Y-%m-%d')})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert len(data) == 1
    item = data[0]
    assert item['fund_code'] == '000001', f'未能获取到 {test_date} 的净值'
    assert item['unit_nav'] > 0, '获取到的净值必须大于 0'
    assert item['date'] == test_date.strftime('%Y-%m-%d')


def test_safe_numeric_write_read(db):
    """验证 SafeNumeric 写入和读取的精度"""
    from datetime import date
    from decimal import Decimal

    from app.domains.funds.models import DailyWorth

    dw = DailyWorth(
        fund_code='000001',
        date=date(2025, 1, 1),
        unit_nav=Decimal('1.234567'),
        acc_nav=Decimal('1.234567'),
    )
    db.add(dw)
    db.commit()

    dw_read = db.query(DailyWorth).filter_by(fund_code='000001', date=date(2025, 1, 1)).first()
    assert dw_read.unit_nav == Decimal('1.234567')
    assert dw_read.acc_nav == Decimal('1.234567')


# ==========================================
# 新增：费率规则与赎回费估算测试
# ==========================================


class TestFundFeeRates:
    """测试基金申购和赎回费率结构接口 GET /api/funds/<fund_code>/fee-rates/"""

    def test_get_fee_rates_success(self, client, db):
        """正向测试：成功获取基金的申购和赎回阶梯费率"""

        # 1. 创建基金
        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.flush()

        # 2. 创建申购费率阶梯（0~1万元，费率 0.15%）
        purchase_rule = PurchaseRule(start_quota=0, end_quota=Money.yuan_to_cents(10000))
        db.add(purchase_rule)
        db.flush()

        # 3. 创建赎回费率阶梯（0~7天，费率 1.5%）
        redeem_rule = RedeemRule(start_day=0, end_day=7)
        db.add(redeem_rule)
        db.flush()

        # 4. 关联费率
        fee_ratio_purchase = FeeRatio(
            fund_code=fund.fund_code,
            fee_type='purchase',
            rate=0.0015,  # 0.15%
            purchase_rule_id=purchase_rule.id,
        )
        fee_ratio_redeem = FeeRatio(
            fund_code=fund.fund_code,
            fee_type='redeem',
            rate=0.015,  # 1.5%
            redeem_rule_id=redeem_rule.id,
        )
        db.add_all([fee_ratio_purchase, fee_ratio_redeem])
        db.commit()

        # 5. 调用接口
        resp = client.get(f'/api/funds/{fund.fund_code}/fee-rates/')
        assert resp.status_code == 200
        data = resp.get_json()['data']

        # 6. 断言
        assert data['currency'] == 'CNY'
        assert data['fund_code'] == '000001'
        assert len(data['purchase']) == 1
        assert data['purchase'][0]['start_quota'] == 0.0
        assert data['purchase'][0]['end_quota'] == 10000.0
        assert data['purchase'][0]['rate'] == 0.0015

        assert len(data['redeem']) == 1
        assert data['redeem'][0]['start_day'] == 0
        assert data['redeem'][0]['end_day'] == 7
        assert data['redeem'][0]['rate'] == 0.015

    def test_get_fee_rates_fund_not_found(self, client):
        """测试查询不存在的基金代码"""
        resp = client.get('/api/funds/999999/fee-rates/')
        assert resp.status_code == 404
        assert '基金代码不存在' in resp.get_json()['message']

    def test_get_fee_rates_no_rules(self, client, db):
        """测试有基金但无费率规则时返回空列表"""

        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.commit()

        resp = client.get(f'/api/funds/{fund.fund_code}/fee-rates/')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['purchase'] == []
        assert data['redeem'] == []


class TestRedeemFeeEstimate:
    """测试赎回费用估算接口 POST /api/funds/redeem-fee/estimate/"""

    def test_estimate_redeem_fee_success_fifo(self, client, db, make_position, make_transaction):
        """正向测试：严格遵循 FIFO 计算卖出份额和赎回费"""
        # 1. 准备测试日期
        sell_date = date(2026, 7, 10)

        # 2. 创建基金、赎回费率规则
        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.flush()

        r1 = RedeemRule(start_day=0, end_day=7)
        r2 = RedeemRule(start_day=7, end_day=30)
        r3 = RedeemRule(start_day=30, end_day=None)
        db.add_all([r1, r2, r3])
        db.flush()  # 保证 ID 刷新

        db.add(FeeRatio(fund_code='000001', fee_type='redeem', rate=0.015, redeem_rule_id=r1.id))
        db.add(FeeRatio(fund_code='000001', fee_type='redeem', rate=0.005, redeem_rule_id=r2.id))
        db.add(FeeRatio(fund_code='000001', fee_type='redeem', rate=0.0, redeem_rule_id=r3.id))
        db.commit()

        # 3. 创建持仓与买入交易
        position = make_position(
            symbol=fund.fund_code,
            name='测试基金',
            asset_type='fund',
            quantity=1000,
            avg_price=1.0,
            current_price=1.2,
            account_name='测试账户',
        )
        db.flush()

        txn1 = make_transaction(
            position_id=position.id,
            ledger_id=position.ledger_id,
            txn_type='buy',
            quantity=300,
            price=1.0,
            confirm_date=sell_date - timedelta(days=40),  # 最老
        )
        txn2 = make_transaction(
            position_id=position.id,
            ledger_id=position.ledger_id,
            txn_type='buy',
            quantity=400,
            price=1.0,
            confirm_date=sell_date - timedelta(days=15),
        )
        txn3 = make_transaction(
            position_id=position.id,
            ledger_id=position.ledger_id,
            txn_type='buy',
            quantity=300,
            price=1.0,
            confirm_date=sell_date - timedelta(days=3),  # 最新
        )
        db.add_all([txn1, txn2, txn3])
        db.commit()

        # 4. 执行卖出 500 份
        resp = client.post(
            '/api/funds/redeem-fee/estimate/',
            json={'position_id': position.id, 'shares': 500, 'sell_date': sell_date.strftime('%Y-%m-%d')},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']

        # 5. 断言 FIFO 结果
        # ✅ 真正 FIFO: 扣减老份额，1.5%的最新份额根本没用上。
        # 手续费 = 300(0%) * 1.0 * 0 + 200(0.5%) * 1.0 * 0.005 = 1.0 元。
        assert data['total_fee'] == 1.0

        assert data['sell'] is not None
        details = data['sell']
        assert len(details) == 3
        for d in details:
            if d['rate'] == 0.015:
                assert d['shares'] == 0
            elif d['rate'] == 0.005:
                assert d['shares'] == 200
            elif d['rate'] == 0.0:
                assert d['shares'] == 300

    def test_estimate_redeem_fee_full_position(self, client, db, make_position, make_transaction):
        """全仓模式：不传 shares，自动计算全部持仓"""
        sell_date = date(2026, 7, 10)

        fund = Fund(fund_code='000002', name='全仓测试基金')
        db.add(fund)
        db.flush()

        r = RedeemRule(start_day=0, end_day=365)
        db.add(r)
        db.flush()
        db.add(FeeRatio(fund_code='000002', fee_type='redeem', rate=0.005, redeem_rule_id=r.id))
        db.commit()

        position = make_position(
            symbol='000002',
            name='全仓测试基金',
            asset_type='fund',
            quantity=600,
            avg_price=1.2,
        )
        db.flush()

        txn1 = make_transaction(
            position_id=position.id,
            ledger_id=position.ledger_id,
            txn_type='buy',
            quantity=300,
            price=1.2,
            confirm_date=sell_date - timedelta(days=100),
        )
        txn2 = make_transaction(
            position_id=position.id,
            ledger_id=position.ledger_id,
            txn_type='buy',
            quantity=300,
            price=1.2,
            confirm_date=sell_date - timedelta(days=200),
        )
        db.add_all([txn1, txn2])
        db.commit()

        resp = client.post(
            '/api/funds/redeem-fee/estimate/',
            json={'position_id': position.id, 'sell_date': sell_date.strftime('%Y-%m-%d')},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        # 600 * 1.2 * 0.005 = 3.6
        assert data['total_fee'] == 3.6
        assert data['sell'] is None  # 全仓模式不返回 sell
        assert len(data['holdings']) == 1
        assert data['holdings'][0]['shares'] == 600

    def test_estimate_redeem_fee_insufficient_shares(self, client, db, make_position, make_transaction):
        """测试卖出份额超过持仓时返回 400"""
        fund = Fund(fund_code='000003', name='份额不足基金')
        db.add(fund)
        db.flush()

        r = RedeemRule(start_day=0, end_day=7)
        db.add(r)
        db.flush()
        db.add(FeeRatio(fund_code='000003', fee_type='redeem', rate=0.015, redeem_rule_id=r.id))
        db.commit()

        position = make_position(symbol='000003', quantity=100, asset_type='fund')
        db.flush()

        txn = make_transaction(
            position_id=position.id,
            ledger_id=position.ledger_id,
            txn_type='buy',
            quantity=50,
            price=1.0,
            confirm_date=date.today() - timedelta(days=30),
        )
        db.add(txn)
        db.commit()

        resp = client.post(
            '/api/funds/redeem-fee/estimate/',
            json={
                'position_id': position.id,
                'shares': 150,
                'sell_date': date.today().strftime('%Y-%m-%d'),
            },
        )
        assert resp.status_code == 400
        assert '持仓份额不足' in resp.get_json()['message']

    def test_estimate_redeem_fee_not_fund(self, client, db, make_position):
        """测试传入非基金类型的持仓 ID 时返回 400"""

        # 创建一个股票持仓
        position = make_position(symbol='000001', name='平安银行', asset_type='stock')
        db.commit()

        resp = client.post(
            '/api/funds/redeem-fee/estimate/',
            json={'position_id': position.id, 'shares': 100, 'sell_date': date.today().strftime('%Y-%m-%d')},
        )
        assert resp.status_code == 400
        assert '无效持仓或非基金' in resp.get_json()['message']

    def test_estimate_redeem_fee_missing_params(self, client, db, make_position):
        """测试缺少必填参数时返回 400"""
        position = make_position(symbol='000001', asset_type='fund')
        db.commit()

        # 缺少 sell_date
        resp1 = client.post(
            '/api/funds/redeem-fee/estimate/',
            json={'position_id': position.id, 'shares': 100},
        )
        assert resp1.status_code == 400
        assert '缺少卖出日期' in resp1.get_json()['message']

        # 缺少 position_id
        resp2 = client.post(
            '/api/funds/redeem-fee/estimate/',
            json={'shares': 100, 'sell_date': '2026-07-10'},
        )
        assert resp2.status_code == 400
        assert '缺少持仓 ID' in resp2.get_json()['message']

        # 全仓模式不传 shares 也应合法（但需要有买入记录和规则，此处只测试参数校验）
        # 由于缺少买入记录，实际会报业务错，但至少参数层面通过了
        resp3 = client.post(
            '/api/funds/redeem-fee/estimate/',
            json={'position_id': position.id, 'sell_date': '2026-07-10'},
        )
        # 此时会进入业务逻辑，发现没有买入记录返回 400，不是参数错误
        assert resp3.status_code == 400
