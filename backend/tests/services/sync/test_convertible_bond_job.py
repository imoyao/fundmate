# -*- coding: utf-8 -*-
"""测试 ConvertibleBondSyncJob：三源合并 + 可转债代码归一 + 覆盖式落库（#1285/#1393/#2575）。

假数据字段名对齐 akshare 1.18.91 实测列名（`bond_cb_redeem_jsl` / `bond_zh_cov`）
与东财 `RPT_BOND_CB_LIST` 实测列名（2026-10-24）。
"""

from app.domains.securities.models import ConvertibleBondTerm
from app.services.adapters.akshare_adapter import AkshareAdapter
from app.services.sync.jobs.convertible_bond_job import ConvertibleBondSyncJob


class _FakeAdapter:
    """假数据源：强赎（集思录）+ 基本信息（东财）+ 条款增强（东财批量报表口）。

    验证 Job 合并/归一逻辑（无需网络）。条款增强源的数据取自 2026-10-24 实测样本
    （洪城转债 110077 的真实条款原文），使 YTM 计算走的是与生产一致的路径。
    """

    def fetch_convertible_bond_redeem(self):
        return [
            {
                'bond_code': '113050',
                'name': '南银转债',
                'price': 118.5,
                'stock_name': '南京银行',
                'stock_code_raw': '601009',
                'issue_size': 200.0,
                'remain_size': 199.9,
                'convert_price': 8.22,
                'force_redeem_price': 10.69,
                'redeem_trigger_ratio': 130.0,
                'redeem_count': 3,
                'redeem_required': 15,
                'redeem_status': '已满足强赎条件',
                'redeem_clause': '近30交易日有15日收盘价≥转股价130%',
                'maturity_date': '2027-06-15',
                # #1491 评审：上游给空串时不得覆盖基本信息源的有效值（如 name / rating）
                'rating': '',
                'source': 'akshare_jsl',
            },
        ]

    def fetch_convertible_bond_basic(self):
        return [
            {
                'bond_code': '113050',
                'name': '南银转债',
                'rating': 'AA+',
                'convert_value': 105.2,
                'premium_rate': 12.3,
                'stock_name': '南京银行',
                'stock_code_raw': '601009',
                'source': 'akshare_bond_zh_cov',
            },
            # 仅有基本信息（如已到期 / 未上市）的也落库，保证名录完整
            {
                'bond_code': '128145',
                'name': '测试转债',
                'rating': 'AA',
                'premium_rate': 8.8,
                'source': 'akshare_bond_zh_cov',
            },
        ]

    def fetch_convertible_bond_terms(self):
        """条款增强源（#2575）：正股 PB + YTM 自算所需条款原文。

        样本取自东财 `RPT_BOND_CB_LIST` 2026-10-24 实测（110077 洪城转债）。
        """
        return [
            {
                'bond_code': '113050',
                'name': '南银转债',
                'stock_pb': 0.53,
                'coupon_schedule_text': '票面利率:第一年0.2%、第二年0.4%、第三年0.6%、第四年0.8%。',
                'redeem_clause': (
                    '(1)到期赎回条款在本次发行的可转换公司债券期满后五个交易日内,公司将按'
                    '本次发行的可转债票面面值的108%(含最后一期年度利息)的价格向投资者赎回'
                    '全部未转股的可转债。'
                ),
                'expire_date': '2027-06-15',
                'start_date': '2021-06-15',
                'pay_interest_day': '06-15',
                'par_value': 100.0,
                'source': 'eastmoney_RPT_BOND_CB_LIST',
            },
            # 深度价内（现价 191.9 ≥ 面值×1.5）→ YTM 必须**不出值**，不能是 -554%
            {
                'bond_code': '110077',
                'name': '洪城转债',
                'stock_pb': 1.12,
                'coupon_schedule_text': '票面利率:第一年0.2%、第二年0.4%、第三年0.6%、第四年0.8%、第五年1.5%、第六年2.0%。',
                'redeem_clause': (
                    '(1)到期赎回条款在本次发行的可转换公司债券期满后五个交易日内,公司将按'
                    '本次发行的可转债票面面值的110%(含最后一期年度利息)的价格向投资者赎回'
                    '全部未转股的可转债。'
                ),
                'expire_date': '2026-11-20',
                'start_date': '2020-11-24',
                'pay_interest_day': '11-20',
                'par_value': 100.0,
                'source': 'eastmoney_RPT_BOND_CB_LIST',
            },
        ]


def test_convertible_bond_job_upsert_and_merge(db):
    job = ConvertibleBondSyncJob(_FakeAdapter(), db)
    result = job.run()
    assert result['status'] == 'success'

    rows = db.query(ConvertibleBondTerm).all()
    # 3 条：113050（基本信息+强赎+条款增强）、128145（仅基本信息）、110077（仅条款增强）
    assert len(rows) == 3

    r = db.query(ConvertibleBondTerm).filter_by(bond_code='113050').one()
    assert r.symbol == 'SH113050'
    # 强赎源（真实计数分子/分母 + 状态 + 到期日）
    assert r.redeem_count == 3
    assert r.redeem_required == 15
    assert r.redeem_status == '已满足强赎条件'
    assert r.maturity_date is not None
    # 基本信息源（评级 / 转股价值 / 溢价率）；强赎源的空串不得覆盖基本信息源的有效值
    assert r.rating == 'AA+'
    assert r.name == '南银转债'
    assert float(r.premium_rate) == 12.3
    assert float(r.convert_value) == 105.2
    assert r.stock_symbol is not None

    # 仅有基本信息的记录也应落库（无强赎字段）
    r2 = db.query(ConvertibleBondTerm).filter_by(bond_code='128145').one()
    assert r2.rating == 'AA'
    assert r2.redeem_count is None
    # 条款增强源未覆盖到的记录，增强列保持 None（**不是 0**）
    assert r2.stock_pb is None
    assert r2.ytm is None


def test_convertible_bond_job_enhanced_columns(db):
    """条款增强两列落库（#2575）：正股 PB + YTM。"""
    job = ConvertibleBondSyncJob(_FakeAdapter(), db)
    job.run()

    r = db.query(ConvertibleBondTerm).filter_by(bond_code='113050').one()
    # 正股 PB 直接落东财带出的值
    assert float(r.stock_pb) == 0.53
    # YTM 自算：现价 118.5、剩余票息 0.2+0.4+0.6+0.8-0.8(末期已含在赎回价)、
    # 到期赎回价 108 → 总收 108.6，剩余 2 次付息、剩余约 0.64 年
    assert r.ytm is not None
    assert float(r.ytm) < 0  # 现价 118.5 > 兑付 108.6 → 到期是负收益
    assert float(r.ytm) > -30  # 不得是 -500% 这类荒谬值


def test_convertible_bond_job_deep_in_money_has_no_ytm(db):
    """深度价内债**不出 YTM**（#2575 护栏一）。

    洪城转债实测现价 191.938（≥ 面值 100 × 1.5），「持有到期」的前提不成立——
    算出来是 -554% 这种无意义数。宁缺勿滥。
    """
    job = ConvertibleBondSyncJob(_FakeAdapter(), db)
    job.run()

    row = db.query(ConvertibleBondTerm).filter_by(bond_code='110077').one()
    assert row is not None
    assert row.ytm is None


def test_convertible_bond_job_ytm_cleared_when_becomes_invalid(db):
    """**本期确定算不出来**的 YTM 必须清空旧值（不是「这轮没取到」）。

    先让 113050 算出 YTM，再把它变成深度价内 → 旧值必须消失，否则用户会看到
    一只早已不该有 YTM 的债的过期收益率。
    """
    job = ConvertibleBondSyncJob(_FakeAdapter(), db)
    job.run()
    r = db.query(ConvertibleBondTerm).filter_by(bond_code='113050').one()
    assert r.ytm is not None

    class _DeepInMoneyAdapter(_FakeAdapter):
        def fetch_convertible_bond_redeem(self):
            rows = super().fetch_convertible_bond_redeem()
            rows[0]['price'] = 191.938  # 深度价内
            return rows

    job2 = ConvertibleBondSyncJob(_DeepInMoneyAdapter(), db)
    job2.run()
    r2 = db.query(ConvertibleBondTerm).filter_by(bond_code='113050').one()
    assert r2.ytm is None
    # PB 是「取不到就保留旧值」的那类字段，不该被清
    assert float(r2.stock_pb) == 0.53


def test_convertible_bond_job_idempotent(db):
    job = ConvertibleBondSyncJob(_FakeAdapter(), db)
    job.run()
    job.run()
    # 覆盖式 upsert：重复跑不产生重复行
    assert db.query(ConvertibleBondTerm).count() == 3


def test_parse_redeem_count():
    """集思录强赎天计数形如 `3/15 | 3` → (已达, 所需)。"""
    assert AkshareAdapter._parse_redeem_count('3/15 | 3') == (3, 15)
    assert AkshareAdapter._parse_redeem_count('12/30 | 12') == (12, 30)
    assert AkshareAdapter._parse_redeem_count(None) == (None, None)
