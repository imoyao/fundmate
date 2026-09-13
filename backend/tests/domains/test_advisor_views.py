# -*- coding: utf-8 -*-
"""投顾组合明细只读接口单测（#1468）。

advisor_holdings / advisor_adjust_histories 此前一直「只写不读」：同步任务落库，但全后端
没有任何接口暴露，调仓与持仓数据事实上锁在库里。本文件为补上的两个只读接口
（GET /api/funds/advisors/<code>/holdings/ 与 /adjusts/）守住行为：

1. 持仓取**最新快照日**的成分，并标注该基金是否收录进本地 funds 表；
2. SafeNumeric 读回是 Decimal，必须显式转 float（Flask 会把 Decimal 序列化成字符串）；
3. 调仓明细按调仓日倒序分组，同日多条聚合；
4. limit / date 参数边界与非法入参兜底；
5. 组合不存在 → 404。
"""

from datetime import date

from app.domains.funds.models import AdvisorAdjustHistory, AdvisorHolding, AdvisorPortfolio, Fund


def _seed(db, code='ZH012926', platform='QIEMAN'):
    """建一个组合 + 本地名录 + 两份持仓快照 + 一批调仓明细。

    本地 funds 表只收录 000001，不收录 000002 —— 覆盖 in_local_db 的两种取值。
    """
    db.add_all([Fund(fund_code='000001', name='华夏成长混合')])
    p = AdvisorPortfolio(code=code, name='远足', platform=platform)
    db.add(p)
    db.flush()

    # 两份快照：09-01 旧、09-11 新 → holdings 接口必须只回 09-11 那份
    db.add_all(
        [
            AdvisorHolding(
                portfolio_id=p.id,
                as_of_date=date(2026, 9, 1),
                fund_code='000001',
                fund_name='华夏成长混合',
                after_ratio=10.0,
                source='qieman',
            ),
            AdvisorHolding(
                portfolio_id=p.id,
                as_of_date=date(2026, 9, 11),
                fund_code='000001',
                fund_name='华夏成长混合',
                pre_ratio=10.0,
                after_ratio=15.5,
                op_name='加仓',
                source='qieman',
            ),
            AdvisorHolding(
                portfolio_id=p.id,
                as_of_date=date(2026, 9, 11),
                fund_code='000002',
                fund_name='未收录基金',
                after_ratio=8.25,
                op_name='新增',
                source='qieman',
            ),
        ]
    )
    # 调仓明细：09-11 两条、08-20 一条 → 验证按日分组 + 倒序
    db.add_all(
        [
            AdvisorAdjustHistory(
                portfolio_id=p.id,
                adjust_date=date(2026, 9, 11),
                fund_code='000001',
                fund_name='华夏成长混合',
                pre_ratio=10.0,
                after_ratio=15.5,
                op_name='加仓',
                reason='由 2026-09-01 持仓快照推导',
                source='qieman',
            ),
            AdvisorAdjustHistory(
                portfolio_id=p.id,
                adjust_date=date(2026, 9, 11),
                fund_code='000002',
                fund_name='未收录基金',
                after_ratio=8.25,
                op_name='新增',
                reason='由 2026-09-01 持仓快照推导',
                source='qieman',
            ),
            AdvisorAdjustHistory(
                portfolio_id=p.id,
                adjust_date=date(2026, 8, 20),
                fund_code='000001',
                fund_name='华夏成长混合',
                pre_ratio=12.0,
                after_ratio=10.0,
                op_name='减仓',
                source='qieman',
            ),
        ]
    )
    db.commit()
    return p


def test_holdings_returns_latest_snapshot_with_local_db_flag(client, db):
    """只回最新快照日；占比转 float；in_local_db 标出未收录的基金"""
    _seed(db)
    resp = client.get('/api/funds/advisors/ZH012926/holdings/')
    assert resp.status_code == 200
    data = resp.get_json()['data']

    assert data['as_of_date'] == '2026-09-11'
    assert data['platform'] == 'QIEMAN'
    assert len(data['holdings']) == 2  # 09-01 那条旧快照不应出现

    by_code = {h['fund_code']: h for h in data['holdings']}
    # SafeNumeric 读回是 Decimal，没转会变成字符串 "15.5"
    assert by_code['000001']['after_ratio'] == 15.5
    assert isinstance(by_code['000001']['after_ratio'], float)
    assert by_code['000001']['in_local_db'] is True
    # 000002 不在本地 funds 表 → 前端据此不提供跳转
    assert by_code['000002']['in_local_db'] is False
    # 按占比倒序
    assert [h['fund_code'] for h in data['holdings']] == ['000001', '000002']


def test_adjusts_grouped_by_date_desc(client, db):
    """按调仓日倒序分组，同日多条聚合，reason 冗余取首条"""
    _seed(db)
    resp = client.get('/api/funds/advisors/ZH012926/adjusts/')
    assert resp.status_code == 200
    adjusts = resp.get_json()['data']['adjusts']

    assert [a['adjust_date'] for a in adjusts] == ['2026-09-11', '2026-08-20']
    assert len(adjusts[0]['items']) == 2
    assert adjusts[0]['source'] == 'qieman'
    assert adjusts[0]['reason'] == '由 2026-09-01 持仓快照推导'

    first = adjusts[0]['items'][0]
    assert first['pre_ratio'] == 10.0
    assert first['after_ratio'] == 15.5
    assert first['op_name'] == '加仓'


def test_adjusts_limit_and_date_params(client, db):
    """limit 截断 / 非法 limit 兜底 / date 精确过滤"""
    _seed(db)
    assert len(client.get('/api/funds/advisors/ZH012926/adjusts/?limit=1').get_json()['data']['adjusts']) == 1
    assert len(client.get('/api/funds/advisors/ZH012926/adjusts/?limit=50').get_json()['data']['adjusts']) == 2
    # 非法 limit 退回缺省 10，不 500
    assert len(client.get('/api/funds/advisors/ZH012926/adjusts/?limit=abc').get_json()['data']['adjusts']) == 2

    resp = client.get('/api/funds/advisors/ZH012926/adjusts/?date=2026-08-20')
    adjusts = resp.get_json()['data']['adjusts']
    assert len(adjusts) == 1
    assert adjusts[0]['adjust_date'] == '2026-08-20'
    # 不存在的日期 → 空列表，不报错
    assert client.get('/api/funds/advisors/ZH012926/adjusts/?date=1999-01-01').get_json()['data']['adjusts'] == []


def test_advisor_not_found_returns_404(client, db):
    _seed(db)
    for path in ('holdings', 'adjusts'):
        resp = client.get(f'/api/funds/advisors/NO_SUCH_CODE/{path}/')
        assert resp.status_code == 404
        assert resp.get_json()['data'] is None


def test_no_holdings_returns_empty_not_error(client, db):
    """组合存在但无任何持仓 / 调仓时返回空结构，不 404、不 500"""
    db.add(AdvisorPortfolio(code='EMPTY_ONE', name='空组合', platform='QIEMAN'))
    db.commit()

    resp = client.get('/api/funds/advisors/EMPTY_ONE/holdings/')
    assert resp.status_code == 200
    assert resp.get_json()['data']['as_of_date'] is None
    assert resp.get_json()['data']['holdings'] == []

    resp = client.get('/api/funds/advisors/EMPTY_ONE/adjusts/')
    assert resp.status_code == 200
    assert resp.get_json()['data']['adjusts'] == []
