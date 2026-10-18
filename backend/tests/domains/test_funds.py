# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/11 19:34
# File : test_funds.py
from contextlib import contextmanager
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex

from app.core.migrations import migrate_fee_unique_indexes
from app.core.money import Money
from app.domains.funds.models import DailyWorth, FeeRatio, Fund, Manager, PurchaseRule, RedeemRule
from app.services.fund_service import FundService

#: 费率三表的唯一约束（2026-10-18）。与 app.core.migrations / 模型 __table_args__ 同名。
FEE_UNIQUE_INDEX_NAMES = ('uq_fee_ratios_scope', 'uq_redeem_rules_range', 'uq_purchase_rules_quota')


@contextmanager
def _allow_legacy_dirty_fee_rows(db):
    """临时摘掉费率唯一索引，用于构造**存量脏数据**形态。

    ## 为什么还需要这种用例

    唯一约束上线后，新写入不可能再产生重复行——那正是它存在的意义。但读侧的容错
    仍必须保留：存量库、快照导入、人工修数都可能带进这种行（2026-05-31 那次整表
    复制就是这么进来的）。本上下文让用例能造出「约束之前的世界」，钉住那份容错。

    ## 用法约定

    调用方**必须在块内**把造出来的重复行删掉（``_delete_duplicate_fee_ratios``）：
    脏行还在时恢复唯一索引必然失败（UNIQUE constraint failed），那正是约束在起作用。
    恢复语句带 ``IF NOT EXISTS``，因此块内若已自行建过索引也不会撞车。
    """
    engine = db.get_bind()
    ddl: dict[str, str] = {}
    for table in (FeeRatio, RedeemRule, PurchaseRule):
        for idx in table.__table__.indexes:
            if idx.name in FEE_UNIQUE_INDEX_NAMES:
                ddl[idx.name] = str(CreateIndex(idx).compile(dialect=engine.dialect))
    for name in ddl:
        db.execute(text(f'DROP INDEX IF EXISTS {name}'))
    db.commit()
    try:
        yield
    finally:
        for sql in ddl.values():
            db.execute(text(sql.replace('CREATE UNIQUE INDEX', 'CREATE UNIQUE INDEX IF NOT EXISTS', 1)))
        db.commit()


def _delete_duplicate_fee_ratios(db) -> int:
    """删掉「同一 (fund, type, rule) 多行」里的多余行（保留 MIN(id)），返回删除行数。"""
    ids = [
        row[0]
        for row in db.execute(
            text(
                'SELECT id FROM fee_ratios WHERE id NOT IN ('
                '  SELECT MIN(id) FROM fee_ratios'
                '  GROUP BY fund_code, fee_type, COALESCE(purchase_rule_id, -1), COALESCE(redeem_rule_id, -1)'
                ')'
            )
        ).fetchall()
    ]
    for fid in ids:
        db.execute(text('DELETE FROM fee_ratios WHERE id = :i'), {'i': fid})
    if ids:
        db.commit()
    return len(ids)


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


def test_get_fund_nav_realtime_fetch(client, db, monkeypatch):
    """正向测试：数据库中无净值时，走实时拉取兜底并返回。

    mock 掉外部接口与持久化：单测不依赖真实网络（CI 数据中心 IP 易被上游拒绝）；
    _persist_navs 内部早绑定真实库 SessionLocal，也须一并隔离。
    """
    from decimal import Decimal

    fund = db.query(Fund).filter_by(fund_code='000001').first()
    if not fund:
        fund = Fund(fund_code='000001', name='华夏成长')
        db.add(fund)
        db.commit()

    test_date = date.today() - timedelta(days=1)
    if test_date.weekday() >= 5:
        test_date -= timedelta(days=test_date.weekday() - 4)

    monkeypatch.setattr(
        FundService,
        '_fetch_one_nav',
        staticmethod(lambda code, target: Decimal('1.2345') if target == test_date else None),
    )
    monkeypatch.setattr(FundService, '_persist_navs', staticmethod(lambda *args, **kwargs: None))

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

    # 外键约束：DailyWorth.fund_code 引用 funds.fund_code，须先建父记录
    fund = db.query(Fund).filter_by(fund_code='000001').first()
    if not fund:
        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.flush()

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

    def test_estimate_redeem_fee_dedupes_identical_fee_ratio_rows(self, client, db, make_position, make_transaction):
        """存量脏数据防线：同档逐字相同的副本行不得让费率分布每档出现两次

        ``fee_ratios`` 无唯一约束，库里存在一次整表复制留下的逐字相同副本
        （重复对的 rate/currency/created_at/updated_at 全同，2026-10-17 实测
        3410/3412 只基金中招）。读取侧不去重时「赎回费率分布」弹窗每一档都
        显示两遍、份额数一模一样——即用户报的「表格显示两次」。
        """
        sell_date = date(2026, 7, 10)

        fund = Fund(fund_code='000004', name='副本行测试基金')
        db.add(fund)
        db.flush()

        r1 = RedeemRule(start_day=0, end_day=7)
        r2 = RedeemRule(start_day=7, end_day=None)

        # 第 1 档故意写两行逐字相同的副本（第 2 档只有一行）
        # 唯一约束已于 2026-10-18 上线，这种行新写入进不来，故临时摘掉约束来复现存量形态
        with _allow_legacy_dirty_fee_rows(db):
            db.add_all([r1, r2])
            db.flush()
            db.add(FeeRatio(fund_code='000004', fee_type='redeem', rate=0.015, redeem_rule_id=r1.id))
            db.add(FeeRatio(fund_code='000004', fee_type='redeem', rate=0.015, redeem_rule_id=r1.id))
            db.add(FeeRatio(fund_code='000004', fee_type='redeem', rate=0.0, redeem_rule_id=r2.id))
            db.commit()

            # 本用例的前提：库里确实存在重复行（否则断言的是空前提）
            assert db.query(FeeRatio).filter(FeeRatio.fund_code == '000004', FeeRatio.fee_type == 'redeem').count() == 3

            try:
                position = make_position(
                    symbol='000004',
                    name='副本行测试基金',
                    asset_type='fund',
                    quantity=1000,
                    avg_price=1.0,
                )
                db.flush()
                txn = make_transaction(
                    position_id=position.id,
                    ledger_id=position.ledger_id,
                    txn_type='buy',
                    quantity=1000,
                    price=1.0,
                    confirm_date=sell_date - timedelta(days=3),  # 落在 0~7 天档
                )
                db.add(txn)
                db.commit()

                resp = client.post(
                    '/api/funds/redeem-fee/estimate/',
                    json={'position_id': position.id, 'sell_date': sell_date.strftime('%Y-%m-%d')},
                )
                assert resp.status_code == 200
                data = resp.get_json()['data']

                # 每档只出现一次，且顺序按持有天数
                assert len(data['holdings']) == 2, f'档位重复或缺失: {data["holdings"]}'
                assert [d['range'] for d in data['holdings']] == ['0~7天(不含)', '≥7天']
                assert data['holdings'][0]['shares'] == 1000
                # 费率不被重复行放大：1000 份 * 1.0 元 * 1.5% = 15.0
                assert data['total_fee'] == 15.0

                # 费率查询接口同样要去重（同一份脏数据，两个读取口）
                rates_resp = client.get(f'/api/funds/{fund.fund_code}/fee-rates/')
                assert rates_resp.status_code == 200
                assert len(rates_resp.get_json()['data']['redeem']) == 2
            finally:
                # 收尾必须清掉脏行：脏行还在时恢复唯一索引必然失败
                _delete_duplicate_fee_ratios(db)

    def test_estimate_redeem_fee_keeps_conflicting_rates_in_same_range(
        self, client, db, make_position, make_transaction
    ):
        """区间相同但费率不同 = 真实歧义（解析缺陷产物），读侧不得静默折叠

        真实数据里 000513 的 0~7 天同时存在 1.5% 与 0.75%。这不是重复行，
        读侧无权替用户选一个——折叠掉会让费率分布少一档、并改变取到的费率。
        唯一约束上线后这种行同样进不来（同一 rule 只能有一条费率），故临时摘掉约束复现。
        """
        sell_date = date(2026, 7, 10)

        fund = Fund(fund_code='000005', name='费率歧义基金')
        db.add(fund)
        db.flush()

        rule = RedeemRule(start_day=0, end_day=7)
        db.add(rule)
        db.flush()

        with _allow_legacy_dirty_fee_rows(db):
            db.add(FeeRatio(fund_code='000005', fee_type='redeem', rate=0.015, redeem_rule_id=rule.id))
            db.add(FeeRatio(fund_code='000005', fee_type='redeem', rate=0.0075, redeem_rule_id=rule.id))
            db.commit()

            try:
                position = make_position(
                    symbol='000005', name='费率歧义基金', asset_type='fund', quantity=1000, avg_price=1.0
                )
                db.flush()
                txn = make_transaction(
                    position_id=position.id,
                    ledger_id=position.ledger_id,
                    txn_type='buy',
                    quantity=1000,
                    price=1.0,
                    confirm_date=sell_date - timedelta(days=3),
                )
                db.add(txn)
                db.commit()

                resp = client.post(
                    '/api/funds/redeem-fee/estimate/',
                    json={'position_id': position.id, 'sell_date': sell_date.strftime('%Y-%m-%d')},
                )
                assert resp.status_code == 200
                data = resp.get_json()['data']

                # 两个费率都在表里：份额按各自费率分列，合计等于全部持有
                assert len(data['holdings']) == 2
                assert sorted(d['rate'] for d in data['holdings']) == [0.0075, 0.015]
                assert sum(d['shares'] for d in data['holdings']) == 1000
            finally:
                _delete_duplicate_fee_ratios(db)


class TestSyncFundFeesRepairsBadTiers:
    """`sync_fund_fees` 是存量错误阶梯的修复入口（前端「更新费率」按钮走的就是它）

    旧实现只有「查不到才插」，所以库里那批被解析缺陷写坏的数据**同步多少次都不会变**
    （2026-10-18 查实：本机 245 只基金的赎回阶梯结构损坏）。修复后它是 upsert + 清残档。
    """

    def test_sync_repairs_wrong_tier(self, db):
        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.flush()

        # 存量形态：区间 (0,7) 上挂着 0.75%（000513 曾经就是这个错值）
        bad_rule = RedeemRule(start_day=0, end_day=7)
        db.add(bad_rule)
        db.flush()
        db.add(FeeRatio(fund_code='000001', fee_type='redeem', rate=0.0075, redeem_rule_id=bad_rule.id))
        db.commit()

        adapter = MagicMock()
        adapter.fetch_fund_fee.return_value = {
            'redemption_schedule': [{'start_day': 0, 'end_day': 8, 'rate': 1.5}],
        }
        with patch('app.services.fund_service.XalphaAdapter', return_value=adapter):
            assert FundService.sync_fund_fees(db, '000001') is True

        rows = db.query(FeeRatio).filter_by(fund_code='000001', fee_type='redeem').all()
        assert len(rows) == 1, '旧档应被删除、新档写入，只剩一行'
        assert float(rows[0].rate) == 0.015
        kept = db.query(RedeemRule).filter(RedeemRule.id == rows[0].redeem_rule_id).one()
        assert (kept.start_day, kept.end_day) == (0, 8)

    def test_sync_keeps_existing_data_when_schedule_invalid(self, db):
        """上游阶梯结构非法 → 拒写，既有数据原样保留（费率缺失优于金额算错）"""
        fund = Fund(fund_code='000001', name='测试基金')
        db.add(fund)
        db.flush()
        rule = RedeemRule(start_day=0, end_day=7)
        db.add(rule)
        db.flush()
        db.add(FeeRatio(fund_code='000001', fee_type='redeem', rate=0.015, redeem_rule_id=rule.id))
        db.commit()

        adapter = MagicMock()
        adapter.fetch_fund_fee.return_value = {
            'redemption_schedule': [
                {'start_day': 0, 'end_day': 7, 'rate': 1.5},
                {'start_day': 0, 'end_day': 7, 'rate': 0.75},
            ],
        }
        with patch('app.services.fund_service.XalphaAdapter', return_value=adapter):
            assert FundService.sync_fund_fees(db, '000001') is True

        rows = db.query(FeeRatio).filter_by(fund_code='000001', fee_type='redeem').all()
        assert len(rows) == 1
        assert float(rows[0].rate) == 0.015


class TestFeeUniqueConstraints:
    """费率三表的唯一约束（2026-10-18）

    这是本轮修复的**最后一道、也是唯一会让错误当场报错**的一道：应用层的
    upsert / 结构校验 / 清残档都只在已知写路径上生效，而这三张表此前一个索引都没有，
    12,732 组重复副本行因此能静默存在五个月。
    """

    def test_duplicate_tier_is_rejected_by_database(self, db):
        """同一 (fund, fee_type, rule) 的重复费率必须被数据库拒绝"""
        rule = RedeemRule(start_day=0, end_day=7)
        db.add(rule)
        db.flush()
        db.add(FeeRatio(fund_code='000001', fee_type='redeem', rate=0.015, redeem_rule_id=rule.id))
        db.commit()

        db.add(FeeRatio(fund_code='000001', fee_type='redeem', rate=0.015, redeem_rule_id=rule.id))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_duplicate_range_rule_is_rejected(self, db):
        """同一持有天数区间的第二条规则行必须被拒绝"""
        db.add(RedeemRule(start_day=0, end_day=7))
        db.commit()

        db.add(RedeemRule(start_day=0, end_day=7))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_last_tier_with_null_end_day_still_constrained(self, db):
        """末档 end_day IS NULL 也必须被约束住

        这是必须用表达式索引（COALESCE）的原因：普通唯一索引在 SQLite 下对 NULL
        不生效，「无上限」那一档会完全不受约束。
        """
        db.add(RedeemRule(start_day=7, end_day=None))
        db.commit()

        db.add(RedeemRule(start_day=7, end_day=None))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_migration_is_fail_closed_on_legacy_duplicates(self, db):
        """存量库有重复行时迁移必须报错并指明清理命令，不许静默跳过

        跳过等于把刚修好的问题原样放回去，且没人会知道——重复行正是这样静默存在了五个月。
        """
        rule = RedeemRule(start_day=0, end_day=7)
        db.add(rule)
        db.flush()

        with _allow_legacy_dirty_fee_rows(db):
            db.add_all(
                [
                    FeeRatio(fund_code='000001', fee_type='redeem', rate=0.015, redeem_rule_id=rule.id),
                    FeeRatio(fund_code='000001', fee_type='redeem', rate=0.015, redeem_rule_id=rule.id),
                ]
            )
            db.commit()

            with pytest.raises(RuntimeError) as exc:
                migrate_fee_unique_indexes(db.get_bind())
            assert 'cleanup_fee_ratio_dupes' in str(exc.value), '报错必须指明处置命令'

            # 清掉重复行后迁移应能通过（顺带验证 finally 里索引能被恢复）
            for row in db.query(FeeRatio).filter_by(fund_code='000001').order_by(FeeRatio.id.desc()).limit(1):
                db.delete(row)
            db.commit()
            assert 'uq_fee_ratios_scope' in migrate_fee_unique_indexes(db.get_bind())

    def test_migration_is_idempotent(self, db):
        """重复执行不应报错（init_db 每次启动都会跑）"""
        assert 'uq_fee_ratios_scope' in migrate_fee_unique_indexes(db.get_bind())
        assert 'uq_fee_ratios_scope' in migrate_fee_unique_indexes(db.get_bind())

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
