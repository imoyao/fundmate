# -*- coding: utf-8 -*-
"""按风险指标横向筛（同类内榜）测试（#167）。

**用真库夹具（内存 SQLite）而不是查询替身**：本模块的核心判据全是 filter 语义
（同类分组、口径版本、可疑口径剔除、NULL 不进榜），替身里的 `filter` 是个 no-op，
那些判据会「测了个寂寞」——跑绿但没验任何东西。真库下它们是真正的 SQL。

判据重点：
- **必填 fund_type_id**：不传就报错，不存在「全市场榜」这个默认；
- **口径版本过滤**：旧口径的行不进榜（混排是本模块最危险的形态）；
- **可疑口径剔除 + 报告剔除条数**：「榜上只剩 3 只」与「同类只有 3 只有数据」必须可区分；
- **NULL 不进榜**：没算出来 ≠ 排最后一名。
"""

from datetime import date

import pytest

from app.domains.funds.models import FundRiskMetrics
from app.services.fund_risk_ranking import MAX_LIMIT, SORTABLE_METRICS, list_by_metric
from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION


def _add(db, code, type_id, *, basis='acc_nav', version=CALIBER_VERSION, **metrics):
    """落一行快照（未给的指标留 NULL）。"""
    row = FundRiskMetrics(
        fund_code=code,
        as_of=metrics.pop('as_of', date(2026, 10, 13)),
        fund_type_id=type_id,
        sample_points=metrics.pop('sample_points', 700),
        basis=basis,
        window_label='近3年',
        caliber_version=version,
    )
    for m in (
        'max_drawdown',
        'current_drawdown',
        'annual_return',
        'annual_volatility',
        'sharpe',
        'sortino',
        'calmar',
        'ulcer_index',
        'upi',
        'return_drawdown_ratio',
        'win_rate',
    ):
        if m in metrics:
            setattr(row, m, metrics[m])
    db.add(row)
    db.commit()


class TestGuards:
    def test_requires_fund_type_id(self, db):
        """**不做跨类榜**：不传 fund_type_id 直接报错，不给「全市场」默认。"""
        with pytest.raises(ValueError, match='fund_type_id'):
            list_by_metric(db, fund_type_id=0, metric='sharpe')

    def test_rejects_unknown_metric(self, db):
        with pytest.raises(ValueError, match='不支持的排序指标'):
            list_by_metric(db, fund_type_id=1, metric='as_of')

    def test_sortable_metrics_whitelist_covers_the_reported_ones(self):
        for m in ('max_drawdown', 'current_drawdown', 'calmar', 'sortino', 'sharpe'):
            assert m in SORTABLE_METRICS

    def test_limit_is_clamped(self):
        from app.services.fund_risk_ranking import _clamp_limit

        assert _clamp_limit(None) == 20
        assert _clamp_limit(0) == 20
        assert _clamp_limit(99999) == MAX_LIMIT


class TestPeerOnly:
    def test_only_same_type_appears(self, db):
        """别的类型的行不进榜——这是「同类内排序」的第一条。"""
        _add(db, 'a1', 1, sharpe=1.0)
        _add(db, 'b1', 2, sharpe=9.9)  # 他类，且数值最高
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert [r['fund_code'] for r in out['rows']] == ['a1']

    def test_orders_by_metric_desc(self, db):
        _add(db, 'lo', 1, sharpe=0.5)
        _add(db, 'hi', 1, sharpe=2.5)
        _add(db, 'mid', 1, sharpe=1.5)
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert [r['fund_code'] for r in out['rows']] == ['hi', 'mid', 'lo']

    def test_drawdown_desc_puts_shallowest_first(self, db):
        """回撤是负数：降序 = 浅的在前。-8 应排在 -25 之前。"""
        _add(db, 'deep', 1, max_drawdown=-25.0)
        _add(db, 'shallow', 1, max_drawdown=-8.0)
        out = list_by_metric(db, fund_type_id=1, metric='max_drawdown')
        assert [r['fund_code'] for r in out['rows']] == ['shallow', 'deep']
        assert out['order'] == 'desc'

    def test_volatility_ascending_puts_lowest_first(self, db):
        """波动率正数越小越好 ⇒ 升序。"""
        _add(db, 'high', 1, annual_volatility=30.0)
        _add(db, 'low', 1, annual_volatility=5.0)
        out = list_by_metric(db, fund_type_id=1, metric='annual_volatility')
        assert [r['fund_code'] for r in out['rows']] == ['low', 'high']
        assert out['order'] == 'asc'


class TestCaliberFilter:
    def test_old_caliber_version_excluded(self, db):
        """旧口径的行不进榜——混排是「看起来完全正常」的最危险形态。"""
        _add(db, 'new', 1, sharpe=1.0, version=CALIBER_VERSION)
        _add(db, 'old', 1, sharpe=9.0, version=CALIBER_VERSION - 1)
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert [r['fund_code'] for r in out['rows']] == ['new']

    def test_explicit_caliber_version_selects_that_generation(self, db):
        _add(db, 'new', 1, sharpe=1.0, version=CALIBER_VERSION)
        _add(db, 'old', 1, sharpe=9.0, version=CALIBER_VERSION - 1)
        out = list_by_metric(db, fund_type_id=1, metric='sharpe', caliber_version=CALIBER_VERSION - 1)
        assert [r['fund_code'] for r in out['rows']] == ['old']


class TestDistortedFilter:
    def test_distorted_excluded_by_default_and_counted(self, db):
        """口径可疑（净值被折算污染）的基金默认剔除，且剔除条数必须回显。

        它的夏普可能是全类第一，而那个数是假的——排进榜比漏掉它危险得多。
        「榜上只有 1 只」与「同类只有 1 只有数据」是两回事，靠 `excluded_distorted` 区分。
        """
        _add(db, 'good', 1, sharpe=1.0)
        _add(db, 'distorted', 1, sharpe=99.0, basis='distorted')
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert [r['fund_code'] for r in out['rows']] == ['good']
        assert out['excluded_distorted'] == 1

    def test_insufficient_basis_excluded(self, db):
        """样本不足（basis='insufficient'）同样不进榜。"""
        _add(db, 'good', 1, sharpe=1.0)
        _add(db, 'thin', 1, sharpe=50.0, basis='insufficient')
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert [r['fund_code'] for r in out['rows']] == ['good']

    def test_include_distorted_flag_brings_them_back(self, db):
        _add(db, 'good', 1, sharpe=1.0, basis='acc_nav')
        _add(db, 'distorted', 1, sharpe=99.0, basis='distorted')
        out = list_by_metric(db, fund_type_id=1, metric='sharpe', include_distorted=True)
        codes = [r['fund_code'] for r in out['rows']]
        assert set(codes) == {'good', 'distorted'}
        # 带出来时必须逐条能看到 basis（否则读数的人不知道这行口径可疑）
        assert {r['basis'] for r in out['rows']} == {'acc_nav', 'distorted'}


class TestNullHandling:
    def test_null_metric_does_not_appear_as_last_place(self, db):
        """NULL 不进榜：没算出来 ≠ 排最后一名。"""
        _add(db, 'has', 1, sharpe=1.0)
        _add(db, 'none', 1, sortino=1.0)  # sharpe 为 NULL
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert [r['fund_code'] for r in out['rows']] == ['has']

    def test_null_rows_not_counted_as_distorted(self, db):
        """NULL 不是「口径可疑」——两件事分开计数，否则剔除数会虚高。"""
        _add(db, 'has', 1, sharpe=1.0)
        _add(db, 'none', 1, sortino=1.0)
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert out['excluded_distorted'] == 0


class TestPayload:
    def test_payload_carries_values_and_caliber(self, db):
        _add(db, '000001', 7, sharpe=1.23, max_drawdown=-12.5, sample_points=731)
        out = list_by_metric(db, fund_type_id=7, metric='sharpe')
        r = out['rows'][0]
        assert r['fund_code'] == '000001'
        assert r['sharpe'] == 1.23
        assert r['max_drawdown'] == -12.5
        assert r['sample_points'] == 731
        assert r['basis'] == 'acc_nav'
        assert r['as_of'] == '2026-10-13'
        assert r['window_label'] == '近3年'

    def test_limit_is_applied(self, db):
        for i in range(5):
            _add(db, f'c{i}', 1, sharpe=float(i))
        out = list_by_metric(db, fund_type_id=1, metric='sharpe', limit=2)
        assert len(out['rows']) == 2


class TestFundName:
    """榜单行带基金名称（2026-10-17）：只显示 6 位代码用户认不出产品。

    名称来自 `funds` 表两步法查（market 域内）；funds 缺该 code 时降级 None，
    前端回退显示代码——不编造名称。
    """

    def test_fund_name_joined_from_funds_table(self, db):
        from app.domains.funds.models import Fund

        db.add(Fund(fund_code='000001', name='测试优选混合'))
        db.commit()
        _add(db, '000001', 1, sharpe=1.0)
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert out['rows'][0]['fund_name'] == '测试优选混合'

    def test_fund_name_none_when_funds_row_missing(self, db):
        """funds 表没有该 code（资料未同步）⇒ None，不编造、不报错。"""
        _add(db, '999999', 1, sharpe=1.0)
        out = list_by_metric(db, fund_type_id=1, metric='sharpe')
        assert out['rows'][0]['fund_name'] is None
