# -*- coding: utf-8 -*-
"""定投计划（#2138）回归网。

分三层，各锁一类东西：

1. **日期推算**（``next_due_date`` / ``last_due_date`` / ``first_due_date``）——
   一律传固定 ``today``，不依赖运行时钟；覆盖月末夹取、周对齐、end_date 截断、暂停态；
2. **派生状态**（累计投入 / 已执行期数 / 断投）——真写流水，锁「只数 buy」与
   「宽限期后才报断投」两条口径；
3. **HTTP 契约**——路由与尾斜杠、422 参数校验、家庭隔离（越权同判 404）。

``day_of_period=28`` 这类上界、``biweekly`` 拒收星期字段，都写在 schemas 的 docstring 里，
用例只是把那些约定钉住。
"""

from datetime import date, datetime, timedelta

import pytest

from app.domains.recurring.models import RecurringPlan
from app.services import recurring_service as svc


def _plan(db, **kwargs) -> RecurringPlan:
    """落一张计划。必须 commit：HTTP 用例走另一个 Session，flush 后 SQLite 仍锁表。"""
    data = {
        'family_id': 1,
        'symbol': '110011',
        'position_name': '易方达优质精选',
        'asset_type': 'fund',
        'amount': 100000,  # 1000.00 元（分）
        'frequency': 'monthly',
        'day_of_period': 15,
        'start_date': date(2026, 1, 15),
        'status': 'active',
    }
    data.update(kwargs)
    plan = RecurringPlan(**data)
    db.add(plan)
    db.commit()
    return plan


# ── 1. 日期推算 ──────────────────────────────────────────────────────────────


def test_monthly_first_due_keeps_start_month(db):
    plan = _plan(db, start_date=date(2026, 1, 15), day_of_period=15)
    assert svc.first_due_date(plan) == date(2026, 1, 15)


def test_monthly_first_due_rolls_when_day_already_passed(db):
    """start 在 15 号之后、约定 5 号 → 首期顺延到下月 5 号，而不是回头补投。"""
    plan = _plan(db, start_date=date(2026, 1, 20), day_of_period=5)
    assert svc.first_due_date(plan) == date(2026, 2, 5)


def test_monthly_clamps_to_month_end(db):
    plan = _plan(db, start_date=date(2026, 1, 28), day_of_period=28)
    assert svc.next_due_date(plan, today=date(2026, 2, 1)) == date(2026, 2, 28)


def test_monthly_next_due_is_today_when_due_today(db):
    plan = _plan(db, start_date=date(2026, 1, 15), day_of_period=15)
    assert svc.next_due_date(plan, today=date(2026, 3, 15)) == date(2026, 3, 15)
    assert svc.next_due_date(plan, today=date(2026, 3, 16)) == date(2026, 4, 15)


def test_weekly_aligns_to_weekday(db):
    """2026-01-05 是周一；约定周三(3) → 首期 01-07，之后每 7 天。"""
    plan = _plan(db, frequency='weekly', day_of_period=3, start_date=date(2026, 1, 5))
    assert svc.first_due_date(plan) == date(2026, 1, 7)
    assert svc.next_due_date(plan, today=date(2026, 1, 8)) == date(2026, 1, 14)


def test_biweekly_anchors_on_start_date(db):
    """biweekly 不按星期对齐：相位锚点是 start_date，每 14 天一期。"""
    plan = _plan(db, frequency='biweekly', day_of_period=None, start_date=date(2026, 1, 5))
    assert svc.first_due_date(plan) == date(2026, 1, 5)
    assert svc.next_due_date(plan, today=date(2026, 1, 20)) == date(2026, 2, 2)


def test_next_due_none_for_paused(db):
    plan = _plan(db, status='paused')
    assert svc.next_due_date(plan, today=date(2026, 3, 1)) is None


def test_next_due_none_after_end_date(db):
    plan = _plan(db, start_date=date(2026, 1, 15), end_date=date(2026, 2, 28))
    assert svc.next_due_date(plan, today=date(2026, 3, 2)) is None


def test_last_due_date_is_latest_past_occurrence(db):
    plan = _plan(db, start_date=date(2026, 1, 15), day_of_period=15)
    assert svc.last_due_date(plan, today=date(2026, 3, 20)) == date(2026, 3, 15)
    # 首期还没到 → 没有「已到期」的一期
    assert svc.last_due_date(plan, today=date(2026, 1, 10)) is None


# ── 2. 派生状态 ──────────────────────────────────────────────────────────────


def test_summary_counts_only_buy_transactions(db, make_transaction):
    """只有 buy 算「计划执行」；挂同一 plan_id 的 sell 不计入累计投入。"""
    plan = _plan(db)
    make_transaction(
        position_id=1,
        ledger_id=1,
        txn_type='buy',
        quantity=100,
        price=10,
        trade_date=datetime(2026, 1, 15, 10, 0),
        plan_id=plan.id,
    )
    make_transaction(
        position_id=1,
        ledger_id=1,
        txn_type='sell',
        quantity=1,
        price=9999,
        trade_date=datetime(2026, 2, 15, 10, 0),
        plan_id=plan.id,
    )

    data = svc.summarize_one(db, 1, plan, today=date(2026, 2, 20))
    assert data['executed_count'] == 1
    assert data['invested_amount'] == 100000
    assert data['last_executed_on'] == '2026-01-15'


def test_summary_flags_overdue_after_grace(db, make_transaction):
    """有过执行、最近一期已过 19 天且本期无流水 → 报断投。"""
    plan = _plan(db, start_date=date(2026, 1, 1), day_of_period=1)
    make_transaction(
        position_id=1,
        ledger_id=1,
        txn_type='buy',
        quantity=10,
        price=10,
        trade_date=datetime(2026, 1, 2, 9, 30),
        plan_id=plan.id,
    )
    data = svc.summarize_one(db, 1, plan, today=date(2026, 3, 20))
    assert data['last_due_date'] == '2026-03-01'
    assert data['is_overdue'] is True
    assert data['overdue_days'] == 19


def test_never_executed_plan_is_not_overdue(db):
    """一期都没执行过 = 尚未开始，不报断投（否则写入路径未接线时整页假警报）。"""
    plan = _plan(db, start_date=date(2026, 1, 1), day_of_period=1)
    data = svc.summarize_one(db, 1, plan, today=date(2026, 3, 20))
    assert data['executed_count'] == 0
    assert data['is_overdue'] is False
    assert data['overdue_days'] == 0


def test_summary_suppresses_overdue_inside_grace(db):
    """约定 15 号、今天 18 号（3 天）→ 宽限期内不报断投。"""
    plan = _plan(db, start_date=date(2026, 1, 15), day_of_period=15)
    data = svc.summarize_one(db, 1, plan, today=date(2026, 3, 18))
    assert data['is_overdue'] is False


def test_summary_not_overdue_when_current_period_executed(db, make_transaction):
    """本期已补录（哪怕晚一天）→ 不算断投。"""
    plan = _plan(db, start_date=date(2026, 1, 1), day_of_period=1)
    make_transaction(
        position_id=1,
        ledger_id=1,
        txn_type='buy',
        quantity=10,
        price=10,
        trade_date=datetime(2026, 3, 2, 9, 30),
        plan_id=plan.id,
    )
    data = svc.summarize_one(db, 1, plan, today=date(2026, 3, 20))
    assert data['is_overdue'] is False
    assert data['overdue_days'] == 0


def test_paused_plan_never_overdue(db):
    plan = _plan(db, start_date=date(2026, 1, 1), day_of_period=1, status='paused')
    data = svc.summarize_one(db, 1, plan, today=date(2026, 3, 20))
    assert data['is_overdue'] is False
    assert data['next_due_date'] is None


# ── 3. HTTP 契约 ─────────────────────────────────────────────────────────────


def test_create_and_list_plan(client, db):
    resp = client.post(
        '/api/recurring-plans/',
        json={
            'symbol': '110011',
            'position_name': '易方达优质精选',
            'amount': 100000,
            'frequency': 'monthly',
            'day_of_period': 15,
            'start_date': '2026-01-15',
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()['data']
    assert data['amount'] == 100000
    assert data['status'] == 'active'
    assert data['next_due_date'] is not None

    listed = client.get('/api/recurring-plans/').get_json()
    assert listed['total'] == 1
    assert listed['data'][0]['symbol'] == '110011'


def test_create_rejects_non_positive_amount(client, db):
    resp = client.post(
        '/api/recurring-plans/',
        json={'symbol': '110011', 'amount': 0, 'start_date': '2026-01-15'},
    )
    assert resp.status_code == 422


def test_create_rejects_monthly_day_31(client, db):
    """29~31 在 2 月会跳月，属于会让人漏投的静默行为，直接不收。"""
    resp = client.post(
        '/api/recurring-plans/',
        json={
            'symbol': '110011',
            'amount': 100000,
            'frequency': 'monthly',
            'day_of_period': 31,
            'start_date': '2026-01-31',
        },
    )
    assert resp.status_code == 422


def test_create_rejects_biweekly_with_day_of_period(client, db):
    resp = client.post(
        '/api/recurring-plans/',
        json={
            'symbol': '110011',
            'amount': 100000,
            'frequency': 'biweekly',
            'day_of_period': 3,
            'start_date': '2026-01-05',
        },
    )
    assert resp.status_code == 422


def test_update_rejects_end_before_start(client, db):
    plan = _plan(db)
    resp = client.patch(f'/api/recurring-plans/{plan.id}/', json={'end_date': '2025-12-01'})
    assert resp.status_code == 422


def test_update_switching_to_biweekly_clears_day_of_period(client, db):
    plan = _plan(db, day_of_period=15)
    resp = client.patch(f'/api/recurring-plans/{plan.id}/', json={'frequency': 'biweekly'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['day_of_period'] is None


def test_pause_resume_end_transitions(client, db):
    plan = _plan(db)

    paused = client.post(f'/api/recurring-plans/{plan.id}/pause/').get_json()['data']
    assert paused['status'] == 'paused'
    assert paused['next_due_date'] is None

    resumed = client.post(f'/api/recurring-plans/{plan.id}/resume/').get_json()['data']
    assert resumed['status'] == 'active'
    assert resumed['next_due_date'] is not None

    ended = client.post(f'/api/recurring-plans/{plan.id}/end/').get_json()['data']
    assert ended['status'] == 'ended'


def test_list_filters_by_status(client, db):
    _plan(db, status='active')
    _plan(db, status='paused', symbol='000001')

    active = client.get('/api/recurring-plans/?status=active').get_json()
    assert active['total'] == 1
    assert active['data'][0]['status'] == 'active'

    assert client.get('/api/recurring-plans/?status=bogus').status_code == 422


def test_other_family_plan_is_invisible(client, db):
    """家庭隔离：别家的计划既不出现在列表，也按 404 处理（不泄露存在性）。"""
    other = _plan(db, family_id=2)
    assert client.get('/api/recurring-plans/').get_json()['total'] == 0
    assert client.get(f'/api/recurring-plans/{other.id}/').status_code == 404
    assert client.patch(f'/api/recurring-plans/{other.id}/', json={'amount': 1}).status_code == 404


# ── 4. 迁移 ──────────────────────────────────────────────────────────────────


def test_transaction_plan_id_column_and_migration_idempotent(app):
    """模型列存在 + 迁移可重复跑（第二次返回「已存在」而不是抛错）。"""
    from sqlalchemy import inspect

    import app.core.database as database
    from app.core.migrations import migrate_transaction_plan_id

    cols = {c['name'] for c in inspect(database.engine).get_columns('transactions')}
    assert 'plan_id' in cols

    first = migrate_transaction_plan_id(database.engine)
    second = migrate_transaction_plan_id(database.engine)
    assert '已存在' in second, f'迁移应幂等，实际返回: {first!r} / {second!r}'


def test_registry_declares_recurring_plans_as_user_domain():
    """漏登记会在 init_db 建库时直接 ValueError，故单钉一条。"""
    from app.core.db_factory import DATA_DOMAIN_REGISTRY, DOMAIN_USER

    assert DATA_DOMAIN_REGISTRY.get('recurring_plans') == DOMAIN_USER


@pytest.mark.parametrize('freq,day', [('monthly', 1), ('monthly', 28), ('weekly', 1), ('weekly', 7)])
def test_supported_schedule_combinations_build(db, freq, day):
    """边界内的组合都该能建出首期日期（防校验过严把合法输入也拦了）。"""
    plan = _plan(db, frequency=freq, day_of_period=day, start_date=date(2026, 1, 1))
    assert svc.first_due_date(plan) >= plan.start_date


def test_overdue_grace_constant_is_a_week():
    """宽限期改动会改变用户看到的断投口径，钉住 7 天。"""
    assert svc.OVERDUE_GRACE_DAYS == 7
    assert timedelta(days=svc.OVERDUE_GRACE_DAYS) == timedelta(days=7)
