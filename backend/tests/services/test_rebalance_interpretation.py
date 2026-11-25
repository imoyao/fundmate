# -*- coding: utf-8 -*-
"""调仓解读（#3259 · L4）—— 结构化解读 + 「说的 vs 做的」分歧识别。

重点覆盖（对齐 issue #3259 验收标准）：

1. **结构化输出**：输入组合 + 最近调仓，产出方向 / 成分变化 / 分歧三部分；
2. **分歧识别**：reason 与实际动作方向不一致时 ``divergence=True``，一致时 ``False``，
   reason 无信息量（模板话术）时 ``unknown``；
3. **方向解读**：加权益（股票/混合型加仓）vs 加债（债券型加仓）正确区分；
4. **降级契约**：组合不存在 → found=False；无调仓 → has_rebalance=False；
5. **最近一次粒度**：只取最新 adjust_date，不铺开多期。

数据域：``advisor_adjust_histories`` 在 market 域，测试走路由会话 `db` 跨域读写
（与 ``test_advisor_comparison`` 同口径）。
"""

from contextlib import closing
from datetime import date

from app.core.db_factory import market_session_factory
from app.domains.funds.models import AdvisorAdjustHistory, AdvisorPortfolio, Fund, FundType
from app.services.rebalance_interpretation import (
    _reason_direction,
    _resolve_divergence,
    build_rebalance_interpretation,
)


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


def _seed_adjust(db, code, fund_code, adjust_date, reason, pre_ratio, after_ratio, op_code, op_name):
    pid = db.query(AdvisorPortfolio.id).filter(AdvisorPortfolio.code == code).scalar()
    db.add(
        AdvisorAdjustHistory(
            portfolio_id=pid,
            adjust_date=adjust_date,
            reason=reason,
            fund_code=fund_code,
            fund_name=f'基金{fund_code}',
            pre_ratio=pre_ratio,
            after_ratio=after_ratio,
            op_code=op_code,
            op_name=op_name,
            source='qieman_official',
        )
    )
    db.flush()


# ── 纯函数：方向与分歧判定 ────────────────────────────────────────────────


def test_reason_direction_add():
    assert _reason_direction('基于估值判断，增加权益仓位') == 'add'
    assert _reason_direction('看好成长，增配股票型基金') == 'add'


def test_reason_direction_reduce():
    assert _reason_direction('市场不确定性上升，降低仓位防守') == 'reduce'
    assert _reason_direction('减持权益，增加债券配置') == 'reduce'


def test_reason_direction_unknown_on_template():
    # 天天基金极简模板话术：无方向信息 → None（不强行判定）
    assert _reason_direction('资产配置结构优化。') is None
    assert _reason_direction('') is None


def test_divergence_conflict_true():
    assert _resolve_divergence('add', 'reduce')['divergence'] is True
    assert _resolve_divergence('reduce', 'add')['divergence'] is True


def test_divergence_consistent_false():
    assert _resolve_divergence('add', 'add')['divergence'] is False
    assert _resolve_divergence('reduce', 'reduce')['divergence'] is False


def test_divergence_unknown_when_either_unknown():
    assert _resolve_divergence(None, 'add')['divergence'] == 'unknown'
    assert _resolve_divergence('add', None)['divergence'] == 'unknown'


# ── 端到端：build_rebalance_interpretation ───────────────────────────────


def test_not_found(db):
    result = build_rebalance_interpretation(db, 'NOSUCH')
    assert result['found'] is False


def test_no_rebalance(db):
    _seed_advisor(db, 'ZH990001')
    db.commit()
    result = build_rebalance_interpretation(db, 'ZH990001')
    assert result['found'] is True
    assert result['has_rebalance'] is False


def test_rebalance_direction_add_equity(db):
    """加股票型基金 → 方向 action=add，成分含该基金。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '000001', '股票型')
        mdb.commit()

    _seed_advisor(db, 'ZH990002', '远足')
    _seed_adjust(db, 'ZH990002', '000001', date(2026, 11, 24), '看好权益，加仓', 10.0, 20.0, 2, '加仓')
    db.commit()

    result = build_rebalance_interpretation(db, 'ZH990002')
    assert result['found'] is True
    assert result['has_rebalance'] is True
    assert result['adjust_date'] == '2026-11-24'
    assert result['direction']['action'] == 'add'
    assert result['direction']['equity_added_count'] == 1
    assert len(result['components']) == 1
    assert result['components'][0]['delta'] == 10.0


def test_rebalance_direction_add_bond(db):
    """加债券型基金 → 不算加权益（bond_added_count=1，action=None）。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '000002', '债券型')
        mdb.commit()

    _seed_advisor(db, 'ZH990003', '稳健组合')
    _seed_adjust(db, 'ZH990003', '000002', date(2026, 11, 24), '降低风险，加债券', 5.0, 15.0, 2, '加仓')
    db.commit()

    result = build_rebalance_interpretation(db, 'ZH990003')
    assert result['direction']['action'] is None  # 无净权益变化
    assert result['direction']['bond_added_count'] == 1
    assert result['direction']['equity_added_count'] == 0


def test_divergence_conflict_end_to_end(db):
    """reason 说加权益，实际减权益 → divergence=True。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '000003', '股票型')
        mdb.commit()

    _seed_advisor(db, 'ZH990004', '言行不一组合')
    # 说的：看好权益加仓；做的：实际减仓（pre 20 → after 10，op 减仓）
    _seed_adjust(db, 'ZH990004', '000003', date(2026, 11, 24), '看好权益，增配股票', 20.0, 10.0, 3, '减仓')
    db.commit()

    result = build_rebalance_interpretation(db, 'ZH990004')
    assert result['divergence']['divergence'] is True
    assert result['divergence']['said'] == 'add'
    assert result['divergence']['done'] == 'reduce'


def test_divergence_unknown_on_template_reason(db):
    """reason 模板话术无法判定方向 → divergence=unknown。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '000004', '股票型')
        mdb.commit()

    _seed_advisor(db, 'ZH990005', '模板话术组合')
    _seed_adjust(db, 'ZH990005', '000004', date(2026, 11, 24), '资产配置结构优化。', 10.0, 15.0, 2, '加仓')
    db.commit()

    result = build_rebalance_interpretation(db, 'ZH990005')
    assert result['divergence']['divergence'] == 'unknown'


def test_latest_adjust_date_only(db):
    """只取最近一次调仓：多期调仓时 components 只含最新 adjust_date 的成分。"""
    with closing(market_session_factory()()) as mdb:
        _seed_fund(mdb, '000005', '股票型')
        _seed_fund(mdb, '000006', '混合型')
        mdb.commit()

    _seed_advisor(db, 'ZH990006', '多期组合')
    _seed_adjust(db, 'ZH990006', '000005', date(2026, 10, 1), '早期调仓', 10.0, 12.0, 2, '加仓')
    _seed_adjust(db, 'ZH990006', '000006', date(2026, 11, 24), '最近调仓', 5.0, 8.0, 2, '加仓')
    db.commit()

    result = build_rebalance_interpretation(db, 'ZH990006')
    assert result['adjust_date'] == '2026-11-24'
    assert len(result['components']) == 1
    assert result['components'][0]['fund_code'] == '000006'
