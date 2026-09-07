# -*- coding: utf-8 -*-
"""测试 AdvisorPortfolioSyncJob：天天基金投顾组合落库 + 且慢手动导入（#1167）。"""

import json
import os
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.domains.funds.models import (
    AdvisorAdjustHistory,
    AdvisorHolding,
    AdvisorIndustryAlloc,
    AdvisorPortfolio,
)
from app.services.sync.jobs.advisor_portfolio_job import (
    AdvisorPortfolioSyncJob,
    flatten_qieman_composition,
    import_qieman_holdings,
)

FIXTURE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'fixtures', 'qieman_holdings_sample.json')
)


@pytest.fixture
def job(db):
    adapter = MagicMock()
    adapter.fetch_overview.return_value = {
        'name': '越海',
        'risk_level': '4',
        'strategy_desc': '均衡风格',
        'estab_date': '2021-07-26',
    }
    adapter.fetch_industry.return_value = [
        {'industry_name': '电子', 'ratio': 9.16},
        {'industry_name': '基础化工', 'ratio': 4.69},
    ]
    adapter.fetch_current_holdings.return_value = {
        'adjust_date': '2026-04-01',
        'funds': [
            {
                'fund_code': '012153',
                'fund_name': '博时研究慧选混合A',
                'pre_ratio': 15.77,
                'after_ratio': 16.0,
                'op_code': 5,
                'op_name': '持平',
            },
            {
                'fund_code': '005827',
                'fund_name': '易方达蓝筹精选混合',
                'pre_ratio': 10.0,
                'after_ratio': 8.0,
                'op_code': 3,
                'op_name': '减仓',
            },
        ],
    }
    adapter.fetch_adjust_history.return_value = [
        {
            'adjust_date': '2026-04-01',
            'reason': '常规调仓',
            'funds': [
                {
                    'fund_code': '012153',
                    'fund_name': '博时研究慧选混合A',
                    'pre_ratio': 15.0,
                    'after_ratio': 16.0,
                    'op_code': 2,
                    'op_name': '加仓',
                },
            ],
        },
    ]
    return AdvisorPortfolioSyncJob(adapter, db)


def test_sync_end_to_end(job, db):
    """四类数据面一次落库：组合建档 + 持仓/行业/历史。"""
    result = job.run(full_sync=True, targets=['XCOVSEX'])
    assert result['status'] == 'success'

    p = db.query(AdvisorPortfolio).filter_by(platform='TIANTIAN', code='XCOVSEX').one()
    assert p.name == '越海'
    assert str(p.estab_date) == '2021-07-26'
    assert p.strategy_desc == '均衡风格'

    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id).all()
    assert len(hs) == 2
    assert {h.fund_code for h in hs} == {'012153', '005827'}

    ind = db.query(AdvisorIndustryAlloc).filter_by(portfolio_id=p.id).all()
    assert {r.industry_name for r in ind} == {'电子', '基础化工'}

    hist = db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).all()
    assert len(hist) == 1
    assert hist[0].reason == '常规调仓'
    assert hist[0].op_name == '加仓'


def test_holdings_cover_replace(job, db):
    """同一快照日重复同步：持仓整体覆盖而非追加（贴合生产：先 seed 旧行再单次运行）。"""
    p = AdvisorPortfolio(platform='TIANTIAN', code='XCOVSEX', name='越海')
    db.add(p)
    db.flush()
    db.add_all(
        [
            AdvisorHolding(
                portfolio_id=p.id,
                as_of_date=date(2026, 4, 1),
                fund_code='012153',
                fund_name='旧持仓A',
                after_ratio=50.0,
                source='tiantian',
            ),
            AdvisorHolding(
                portfolio_id=p.id,
                as_of_date=date(2026, 4, 1),
                fund_code='011111',
                fund_name='旧持仓B',
                after_ratio=50.0,
                source='tiantian',
            ),
        ]
    )
    db.commit()

    job.run(full_sync=True, targets=['XCOVSEX'])
    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id).all()
    assert {h.fund_code for h in hs} == {'012153', '005827'}
    assert next(h for h in hs if h.fund_code == '012153').fund_name == '博时研究慧选混合A'


def test_validate_skips_empty_payload(job):
    """四类数据面全空的组合（可能已下架）应被校验剔除。"""
    empty = {'tgcode': 'X', 'overview': {}, 'industry': [], 'holdings': {'funds': []}, 'history': []}
    assert job._validate_data([empty]) == []


def test_resolve_targets_from_db(job, db):
    """缺省 targets 时只抓库内 TIANTIAN 在售组合。"""
    db.add(AdvisorPortfolio(platform='TIANTIAN', code='ABC123', name='t'))
    db.add(AdvisorPortfolio(platform='QIEMAN', code='ZH999999', name='q'))
    db.commit()
    assert job._resolve_targets([]) == ['ABC123']


def test_flatten_qieman_composition():
    data = {
        'ZH012926': {
            '货币基金': {
                '持有成分': [
                    {
                        '基金代码': '000509',
                        '基金名称': '广发钱袋子A',
                        '持仓占比': '1.21%',
                        '最新更新时间': '2026-07-21 00:00:00',
                    }
                ],
                '分类占比': '1.21%',
            },
            '混合基金': {
                '持有成分': [
                    {
                        '基金代码': '006567',
                        '基金名称': '中泰星元灵活配置混合A',
                        '持仓占比': '10.30%',
                        '最新更新时间': '2026-07-21 00:00:00',
                    }
                ],
                '分类占比': '98.79%',
            },
        }
    }
    funds = flatten_qieman_composition(data)
    assert len(funds) == 2
    assert {f['fund_code'] for f in funds} == {'000509', '006567'}
    assert funds[0]['after_ratio'] == 1.21
    assert str(funds[0]['as_of_date']) == '2026-07-21'


def test_qieman_import(db):
    """且慢实测 JSON 导入 fixture → advisor_holdings（source=qieman_manual）。"""
    with open(FIXTURE, encoding='utf-8') as f:
        data = json.load(f)
    db.add(AdvisorPortfolio(platform='QIEMAN', code='ZH012926', name='远足'))
    db.commit()

    n = import_qieman_holdings(db, data, 'ZH012926')
    assert n == 12  # 货基 1 + 混合 11，跨分类无重复

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH012926').one()
    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id, source='qieman_manual').all()
    assert len(hs) == n
    assert all(h.after_ratio is not None for h in hs)
    # 重复导入按同快照日覆盖
    assert import_qieman_holdings(db, data, 'ZH012926') == n

    # 未建档组合应报错而非静默建卡
    with pytest.raises(ValueError):
        import_qieman_holdings(db, {'ZH888888': {}}, 'ZH888888')
