# -*- coding: utf-8 -*-
"""`GET /api/products/fund-risk-ranking/` 端点测试（#167）。

端点层只管三件事，各自都有明确的失败形态：
1. **`fund_type_id` 必填** —— 不给就 400（不是「默认全市场」）；
2. **指标白名单** —— 不在名单内 400（`as_of` 这种可排序但无意义的列不能被当榜单指标）；
3. **`order` 只认 asc/desc** —— 拼错就 400，而不是静默回落。

数据一律造在 **market 域**会话（`fund_risk_metrics` 属 market 域，生产下是独立引擎）。
"""

from contextlib import closing
from datetime import date

import pytest

from app.core.db_factory import market_session_factory
from app.domains.funds.models import FundRiskMetrics
from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

URL = '/api/products/fund-risk-ranking/'


@pytest.fixture(autouse=True)
def _clean_snapshot():
    """每个用例前后清空 `fund_risk_metrics`。

    清空**必须经 `market_session_factory()`**——端点就是用它读的表；用 `db` 夹具
    （另一条会话）看不到对方未提交/已提交状态在测试库上的差异，清了个寂寞，
    于是上一个用例的种子会漂进下一个用例的断言里（表现为「莫名多了一行」）。
    """
    from app.domains.funds.models import FundRiskMetrics as _M

    def _purge():
        with closing(market_session_factory()()) as session:
            session.query(_M).delete()
            session.commit()

    _purge()
    yield
    _purge()


def _seed(code, type_id, sharpe, *, basis='acc_nav'):
    """落一行快照（幂等：先删同 (code, as_of) 再插）。

    种子表与端点共用同一个内存库，多个用例反复种同一批代码会撞唯一约束
    （`uq_fund_risk_metrics_code_asof`），报错指向插入语句而看起来像端点坏了。
    """
    with closing(market_session_factory()()) as db:
        db.query(FundRiskMetrics).filter(
            FundRiskMetrics.fund_code == code, FundRiskMetrics.as_of == date(2026, 10, 13)
        ).delete()
        db.add(
            FundRiskMetrics(
                fund_code=code,
                as_of=date(2026, 10, 13),
                fund_type_id=type_id,
                sharpe=sharpe,
                max_drawdown=-10.0,
                sample_points=700,
                basis=basis,
                window_label='近3年',
                caliber_version=CALIBER_VERSION,
            )
        )
        db.commit()


def test_requires_fund_type_id(client, db):
    """不传 fund_type_id ⇒ 被拒（**不存在「全市场榜」这个默认**）。

    状态码是 422：必填查询参数缺失由 APIFlask 的入参校验拦下（`FundRiskRankingRequest`
    把 `fund_type_id` 声明为必填），比进服务层再判更早。这里断言「被拒 + 带信封」，
    不锁死具体码值——框架层与业务层的分工不该由本用例固化。
    """
    resp = client.get(f'{URL}?metric=sharpe')
    assert resp.status_code in (400, 422)
    assert resp.get_json().get('error_code') is not None


def test_rejects_metric_outside_whitelist(client, db):
    """`as_of` 可排序但作为榜单指标无意义 ⇒ 400（白名单而非黑名单）。"""
    resp = client.get(f'{URL}?fund_type_id=1&metric=as_of')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001


def test_rejects_bad_order_value(client, db):
    """`order=up` 拼错就 400，不静默回落成 desc——静默回落会让用户以为按他说的排了。"""
    resp = client.get(f'{URL}?fund_type_id=1&metric=sharpe&order=up')
    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001


def test_returns_ranked_rows(client, db):
    _seed('000001', 7, 0.5)
    _seed('000002', 7, 2.5)
    _seed('000003', 7, 1.5)

    resp = client.get(f'{URL}?fund_type_id=7&metric=sharpe')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['metric'] == 'sharpe'
    assert data['order'] == 'desc'
    assert [r['fund_code'] for r in data['rows']] == ['000002', '000003', '000001']
    assert data['caliber_version'] == CALIBER_VERSION


def test_ascending_order_param_is_honoured(client, db):
    _seed('000001', 7, 0.5)
    _seed('000002', 7, 2.5)

    resp = client.get(f'{URL}?fund_type_id=7&metric=sharpe&order=asc')
    data = resp.get_json()['data']
    assert data['order'] == 'asc'
    assert [r['fund_code'] for r in data['rows']] == ['000001', '000002']


def test_distorted_excluded_and_counted(client, db):
    """口径可疑的默认剔除，且把剔除条数回显（否则「榜空」会被读成「同类无数据」）。"""
    _seed('000001', 7, 1.0)
    _seed('000009', 7, 99.0, basis='distorted')

    resp = client.get(f'{URL}?fund_type_id=7&metric=sharpe')
    data = resp.get_json()['data']
    assert [r['fund_code'] for r in data['rows']] == ['000001']
    assert data['excluded_distorted'] == 1

    resp2 = client.get(f'{URL}?fund_type_id=7&metric=sharpe&include_distorted=true')
    codes = [r['fund_code'] for r in resp2.get_json()['data']['rows']]
    assert set(codes) == {'000001', '000009'}


def test_only_same_type_returned(client, db):
    _seed('000001', 7, 1.0)
    _seed('000002', 8, 9.9)  # 他类

    resp = client.get(f'{URL}?fund_type_id=7&metric=sharpe')
    assert [r['fund_code'] for r in resp.get_json()['data']['rows']] == ['000001']
