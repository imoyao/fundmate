# -*- coding: utf-8 -*-
"""调仓聚合提醒（#3258 · L1）—— 检测 + 聚合 + 落通知 的核心逻辑回归。

覆盖的判据（对齐 issue #3258 验收标准）：

1. **聚合**：多组合同期调仓合并成**一条**通知（非逐组合刷屏）；
2. **客观陈述**：标题/正文不含「建议/买入/卖出/替换」等指令措辞；
3. **幂等 dedup**：同一天重复 emit 只留一条（跨天才是新的）；
4. **空集不产生空通知**：adjustments 为空时返回 0，不写任何行；
5. **降级**：组合名缺失回退 code；超长折叠为计数。

数据域：`rebalance_alert` 只查 `advisor_portfolios`（market 域，组合名）与写
`notifications`（user 域）。测试用路由会话 `db` 跨域读写（与 `test_advisor_comparison`
同口径）。
"""

from datetime import date

from app.domains.funds.models import AdvisorPortfolio
from app.services import notification_service as ns
from app.services.rebalance_alert import (
    CATEGORY_REBALANCE,
    SOURCE_TYPE_REBALANCE,
    emit_rebalance_alerts,
)


def _seed_advisor(db, code, name='测试投顾组合'):
    row = db.query(AdvisorPortfolio).filter(AdvisorPortfolio.code == code).first()
    if row is None:
        row = AdvisorPortfolio(code=code, name=name, platform='QIEMAN')
        db.add(row)
        db.flush()
    return row


def test_empty_adjustments_produces_no_notification(db):
    """空集契约：无新调仓时不产生空通知。"""
    assert emit_rebalance_alerts(db, 1, []) == 0
    assert ns.total_count(db, 1) == 0


def test_single_portfolio_emits_one_notification(db):
    """单组合同期调仓 → 一条 category=rebalance 通知。"""
    _seed_advisor(db, 'ZH012926', '远足')
    db.commit()

    created = emit_rebalance_alerts(db, 1, [{'code': 'ZH012926', 'adjust_date': '2026-11-24'}])
    assert created == 1
    row = ns.list_notifications(db, 1)[0]
    assert row.category == CATEGORY_REBALANCE
    assert row.source_type == SOURCE_TYPE_REBALANCE
    assert '远足' in row.title


def test_multi_portfolio_aggregates_into_one(db):
    """多组合同期调仓 → 合并成**一条**通知（聚合，不逐组合刷屏）。"""
    _seed_advisor(db, 'ZH012926', '远足')
    _seed_advisor(db, 'ZH012927', '成长五剑')
    _seed_advisor(db, 'ZH012928', '越海')
    db.commit()

    created = emit_rebalance_alerts(
        db,
        1,
        [
            {'code': 'ZH012926', 'adjust_date': '2026-11-24'},
            {'code': 'ZH012927', 'adjust_date': '2026-11-24'},
            {'code': 'ZH012928', 'adjust_date': '2026-11-24'},
        ],
    )
    assert created == 1
    assert ns.total_count(db, 1) == 1
    row = ns.list_notifications(db, 1)[0]
    assert '3' in row.title  # 客观陈述「N 个组合」


def test_idempotent_within_same_day(db):
    """dedup：同一天重复触发只留一条。"""
    _seed_advisor(db, 'ZH012926', '远足')
    db.commit()
    assert emit_rebalance_alerts(db, 1, [{'code': 'ZH012926', 'adjust_date': '2026-11-24'}]) == 1
    assert emit_rebalance_alerts(db, 1, [{'code': 'ZH012926', 'adjust_date': '2026-11-24'}]) == 0
    assert ns.total_count(db, 1) == 1


def test_title_has_no_directive_wording(db):
    """合规：标题/正文不含指令措辞（建议/买入/卖出/替换）。"""
    _seed_advisor(db, 'ZH012926', '远足')
    db.commit()
    emit_rebalance_alerts(db, 1, [{'code': 'ZH012926', 'adjust_date': '2026-11-24'}])
    row = ns.list_notifications(db, 1)[0]
    for forbidden in ('建议', '买入', '卖出', '替换', '加仓', '减仓'):
        assert forbidden not in row.title, f'标题不得含指令措辞「{forbidden}」'
        assert forbidden not in (row.body or ''), f'正文不得含指令措辞「{forbidden}」'


def test_missing_name_falls_back_to_code(db):
    """组合名缺失（未建档案）时回退 code，不因 KeyError 崩。"""
    created = emit_rebalance_alerts(db, 1, [{'code': 'ZH999999', 'adjust_date': '2026-11-24'}])
    assert created == 1
    row = ns.list_notifications(db, 1)[0]
    assert 'ZH999999' in row.title


def test_duplicate_adjust_dates_deduped(db):
    """同组合同一天的多笔调仓行去重为一次。"""
    _seed_advisor(db, 'ZH012926', '远足')
    db.commit()
    created = emit_rebalance_alerts(
        db,
        1,
        [
            {'code': 'ZH012926', 'adjust_date': '2026-11-24'},
            {'code': 'ZH012926', 'adjust_date': '2026-11-24'},  # 同组合同日重复
        ],
    )
    assert created == 1
    # 标题应陈述 1 个组合，而非被重复行撑成 2 个
    row = ns.list_notifications(db, 1)[0]
    assert '2' not in row.title


def test_dedup_key_contains_day(db):
    """去重键含日期：跨天是新的提醒（节流粒度 = 天）。"""
    # 直接验证 rebalance_alert 的去重键构造口径（通过 service 内部函数）
    from app.services.rebalance_alert import _build_dedup_key

    assert _build_dedup_key(1, date(2026, 11, 24)) == 'rebalance:1:2026-11-24'
    assert _build_dedup_key(1, date(2026, 11, 25)) != _build_dedup_key(1, date(2026, 11, 24))
