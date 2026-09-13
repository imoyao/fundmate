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
    """缺省 targets 时抓库内 TIANTIAN + QIEMAN 在售组合（#1392 自动抓且慢）。"""
    db.add(AdvisorPortfolio(platform='TIANTIAN', code='ABC123', name='t'))
    db.add(AdvisorPortfolio(platform='QIEMAN', code='ZH999999', name='q'))
    db.commit()
    assert set(job._resolve_targets([])) == {('ABC123', 'TIANTIAN'), ('ZH999999', 'QIEMAN')}


def test_resolve_targets_explicit_platform(job, db):
    """显式 targets 的平台解析（#1468）。

    且慢码含 LONG_WIN / J7 / SIxxxx 等非 ZH 命名空间，禁止按代码前缀判平台：
    库内以 platform 为准，库内未建档的再按 advisor_catalog 注册表兜底。
    """
    db.add(AdvisorPortfolio(platform='QIEMAN', code='LONG_WIN', name='长赢指数投资计划-150份'))
    db.commit()

    assert job._resolve_targets(['LONG_WIN']) == [('LONG_WIN', 'QIEMAN')]
    # 库内未建档、但且慢注册表收录 → QIEMAN（前缀兜底会误判为天天基金）
    assert job._resolve_targets(['J7']) == [('J7', 'QIEMAN')]
    # 库内 / 注册表均不命中 → 天天基金
    assert job._resolve_targets(['UNKNOWN_TG']) == [('UNKNOWN_TG', 'TIANTIAN')]
    # 占位符被过滤
    assert job._resolve_targets(['__full__', 'LONG_WIN']) == [('LONG_WIN', 'QIEMAN')]
    assert job._infer_platform('LONG_WIN_S') == 'QIEMAN'
    assert job._infer_platform('SI000090') == 'QIEMAN'


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
    gqb = next(f for f in funds if f['fund_code'] == '000509')
    assert gqb['after_ratio'] == pytest.approx(1.21)
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
    # 重复导入按同快照日覆盖（覆盖式更新，持仓数保持 n 而非累加）
    assert import_qieman_holdings(db, data, 'ZH012926') == n
    hs_after_second = db.query(AdvisorHolding).filter_by(portfolio_id=p.id, source='qieman_manual').all()
    assert len(hs_after_second) == n

    # 未建档组合应报错而非静默建卡
    with pytest.raises(ValueError):
        import_qieman_holdings(db, {'ZH888888': {}}, 'ZH888888')


def test_qieman_auto_fetch(job, db, monkeypatch):
    """#1392/#1468 且慢自动抓取：MCP 返回概览 + 持仓 → 组合档案 + advisor_holdings。"""
    holdings = [
        {
            'code': '110011',
            'name': '易方达中小盘',
            'ratio': 32.5,
            'category': '混合基金',
            'nav': 1.0,
            'nav_date': '2026-09-10',
            'adj_time': '2026-09-10 00:00:00',
            'fund_type': 'MIX_FUND',
        },
        {
            'code': '161725',
            'name': '招商中证白酒',
            'ratio': 18.0,
            'category': '股票基金',
            'nav': 1.0,
            'nav_date': '2026-09-10',
            'adj_time': '2026-09-10 00:00:00',
            'fund_type': 'STOCK_FUND',
        },
    ]
    overview = {
        'code': 'ZH013136',
        'name': '我要稳稳的幸福',
        'org_name': '交银施罗德',
        'risk_level': '中低风险',
        'estab_date': '2017-01-20',
        'summary': '稳健理财，力争长期稳健增值',
        'desc': None,
        'annual_return': 4.8,
        'max_drawdown': 2.79,
        'volatility': 2.36,
        'sharpe_ratio': 1.234,
        'return_1w': 0.1,
        'return_1m': 0.2,
        'return_1y': 3.3,
        'return_since_incep': 40.0,
    }
    monkeypatch.setattr(job.qieman_adapter, 'fetch_holdings', lambda code: holdings)
    monkeypatch.setattr(job.qieman_adapter, 'fetch_overview', lambda code: overview)

    result = job.run(full_sync=True, targets=['ZH013136'])
    assert result['status'] == 'success'

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH013136').one()
    # 概览 / 风险收益指标落库（#1468）
    assert p.name == '我要稳稳的幸福'
    assert p.org_name == '交银施罗德'
    assert p.risk_level == '中低风险'
    assert str(p.estab_date) == '2017-01-20'
    assert p.strategy_desc == '稳健理财，力争长期稳健增值'  # desc 为空时回退 summary
    # SafeNumeric 读出为 Decimal，比较前统一转 float
    assert float(p.annual_return) == pytest.approx(4.8)
    assert float(p.max_drawdown) == pytest.approx(2.79)
    assert float(p.volatility) == pytest.approx(2.36)
    assert float(p.sharpe_ratio) == pytest.approx(1.234)
    assert float(p.return_1y) == pytest.approx(3.3)
    # 持仓落库
    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id, source='qieman').all()
    assert {h.fund_code for h in hs} == {'110011', '161725'}
    assert next(h for h in hs if h.fund_code == '110011').after_ratio == pytest.approx(32.5)


def test_qieman_overview_empty_keeps_curated_fields(job, db, monkeypatch):
    """概览抓取为空（接口失败/无 key）时不得清空策展字段（#1468）。"""
    db.add(
        AdvisorPortfolio(
            platform='QIEMAN',
            code='ZH013136',
            name='我要稳稳的幸福',
            host='基民柠檬',
            allocation='stable',
            product_type='固收+',
        )
    )
    db.commit()
    monkeypatch.setattr(job.qieman_adapter, 'fetch_holdings', lambda code: [])
    monkeypatch.setattr(job.qieman_adapter, 'fetch_overview', lambda code: {})

    job.run(full_sync=True, targets=['ZH013136'])

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH013136').one()
    assert p.host == '基民柠檬'
    assert p.allocation == 'stable'
    assert p.product_type == '固收+'


def test_qieman_derive_adjust_from_snapshots(job, db, monkeypatch):
    """#1468 且慢调仓明细：且慢无历史调仓接口，由相邻两次持仓快照推导前后占比与方向。"""
    p = AdvisorPortfolio(platform='QIEMAN', code='ZH999888', name='测试组合')
    db.add(p)
    db.commit()
    # 上一快照（2026-06-30）：A 20% / B 10% / C 5%
    db.bulk_insert_mappings(
        AdvisorHolding,
        [
            {
                'portfolio_id': p.id,
                'as_of_date': date(2026, 6, 30),
                'fund_code': c,
                'fund_name': n,
                'after_ratio': r,
                'source': 'qieman',
            }
            for c, n, r in [('000001', 'A', 20.0), ('000002', 'B', 10.0), ('000003', 'C', 5.0)]
        ],
    )
    db.commit()

    # 本次快照（2026-09-11）：A 加仓至 25% / B 减至 4% / C 清仓 / D 新增 8%
    holdings = [
        {'code': '000001', 'name': 'A', 'ratio': 25.0, 'adj_time': '2026-09-11 00:00:00'},
        {'code': '000002', 'name': 'B', 'ratio': 4.0, 'adj_time': '2026-09-11 00:00:00'},
        {'code': '000004', 'name': 'D', 'ratio': 8.0, 'adj_time': '2026-09-11 00:00:00'},
    ]
    monkeypatch.setattr(job.qieman_adapter, 'fetch_holdings', lambda code: holdings)
    monkeypatch.setattr(job.qieman_adapter, 'fetch_overview', lambda code: {})

    job.run(full_sync=True, targets=['ZH999888'])

    rows = {
        r.fund_code: r
        for r in db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id, adjust_date=date(2026, 9, 11)).all()
    }
    assert set(rows) == {'000001', '000002', '000003', '000004'}
    # 加仓：20 → 25
    assert float(rows['000001'].pre_ratio) == pytest.approx(20.0)
    assert float(rows['000001'].after_ratio) == pytest.approx(25.0)
    assert rows['000001'].op_name == '加仓'
    # 减仓：10 → 4
    assert rows['000002'].op_name == '减仓'
    # 清仓：5 → 0（仍记减仓，after=0）
    assert rows['000003'].op_name == '减仓'
    assert float(rows['000003'].after_ratio) == pytest.approx(0.0)
    # 新增：0 → 8
    assert rows['000004'].op_name == '新增'
    assert float(rows['000004'].pre_ratio) == pytest.approx(0.0)
    assert all(r.source == 'qieman' for r in rows.values())


def test_qieman_first_snapshot_creates_no_adjust(job, db, monkeypatch):
    """首次快照没有前值可对比 → 不编造调仓记录（#1468）。"""
    db.add(AdvisorPortfolio(platform='QIEMAN', code='ZH999777', name='首建组合'))
    db.commit()
    monkeypatch.setattr(
        job.qieman_adapter,
        'fetch_holdings',
        lambda code: [{'code': '000001', 'name': 'A', 'ratio': 50.0, 'adj_time': '2026-09-11 00:00:00'}],
    )
    monkeypatch.setattr(job.qieman_adapter, 'fetch_overview', lambda code: {})

    job.run(full_sync=True, targets=['ZH999777'])

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH999777').one()
    assert db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).count() == 0
    assert db.query(AdvisorHolding).filter_by(portfolio_id=p.id).count() == 1
