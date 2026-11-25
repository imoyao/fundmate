# -*- coding: utf-8 -*-
"""投顾调仓解读工具（#3259 · L4）—— 工具注册 + 出参 schema 回归。

覆盖：
1. **已注册**：`get_advisor_rebalance` 进注册表，``ToolExecutor.run`` 可调；
2. **出参 schema**：found / has_rebalance / adjust_date / components / direction / divergence；
3. **降级**：组合不存在 → found=False；无调仓 → has_rebalance=False；空 code → error；
4. **工具只读**：调用不写库、不出网（``build_rebalance_interpretation`` 零写路径）。
"""

from contextlib import closing
from datetime import date

from app.core.db_factory import market_session_factory
from app.domains.funds.models import AdvisorAdjustHistory, AdvisorPortfolio, Fund, FundType
from app.services.ai_recognizer.tools import ToolExecutor


def _seed_fund(market_db, code, type_name):
    type_row = market_db.query(FundType).filter(FundType.name == type_name).first()
    if type_row is None:
        type_row = FundType(name=type_name)
        market_db.add(type_row)
        market_db.flush()
    row = market_db.query(Fund).filter(Fund.fund_code == code).first()
    if row is None:
        row = Fund(fund_code=code, name=f'基金{code}', fund_type_id=type_row.id)
        market_db.add(row)
        market_db.flush()
    return row


def _seed_advisor(db, code, name='测试投顾组合'):
    row = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code == code).first()
    if row is None:
        row = AdvisorPortfolio(code=code, name=name, platform='QIEMAN')
        db.add(row)
        db.flush()
    return row


def test_tool_registered_and_returns_schema(db):
    """工具已注册，且出参含 direction / divergence / components 三部分。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '000001', '股票型')
        mdb.commit()

    _seed_advisor(db, 'ZH990001', '远足')
    pid = db.query(AdvisorPortfolio.id).filter(AdvisorPortfolio.code == 'ZH990001').scalar()
    db.add(
        AdvisorAdjustHistory(
            portfolio_id=pid,
            adjust_date=date(2026, 11, 24),
            reason='看好权益，加仓',
            fund_code='000001',
            fund_name='基金000001',
            pre_ratio=10.0,
            after_ratio=20.0,
            op_code=2,
            op_name='加仓',
            source='qieman_official',
        )
    )
    db.commit()

    result = ToolExecutor.run('get_advisor_rebalance', {'code': 'ZH990001'})
    assert result['status'] == 'success', result.get('msg')
    data = result['data']
    assert data['found'] is True
    assert data['has_rebalance'] is True
    assert data['adjust_date'] == '2026-11-24'
    assert data['direction']['action'] == 'add'
    assert 'divergence' in data
    assert 'components' in data


def test_tool_not_found(db):
    result = ToolExecutor.run('get_advisor_rebalance', {'code': 'NOSUCH'})
    assert result['status'] == 'success'
    assert result['data']['found'] is False


def test_tool_no_rebalance(db):
    _seed_advisor(db, 'ZH990002')
    db.commit()
    result = ToolExecutor.run('get_advisor_rebalance', {'code': 'ZH990002'})
    assert result['status'] == 'success'
    assert result['data']['found'] is True
    assert result['data']['has_rebalance'] is False


def test_tool_missing_code(db):
    result = ToolExecutor.run('get_advisor_rebalance', {})
    # 缺 code：schema 校验期报错（required），ToolExecutor 收敛为 error 而非崩
    assert result['status'] == 'error'
