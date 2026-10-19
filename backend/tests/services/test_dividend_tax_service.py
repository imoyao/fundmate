# -*- coding: utf-8 -*-
"""红利税「待补记」识别回归（#541）。

判据（改实现前先看 `services/dividend_tax_service.py` 模块 docstring）：

1. 有现金分红、该年该标的**无** `dividend_tax` ⇒ 报出来；
2. 同一年同标的有 `dividend_tax` ⇒ 不报（宁可漏报，不可滥报）；
3. 红利再投**不算**（份额已增加，没有「该扣的现金税」）；
4. 无 symbol / 金额非正的行不参与；
5. 超出回溯窗口的旧分红不催账；
6. 通知粒度 = 每标的每年一条，dedup_key 含年份（同一笔钱不会被提醒两次）。
"""

from datetime import date, timedelta

import pytest

from app.services.dividend_tax_service import (
    SOURCE_TYPE,
    build_notification_candidates,
    scan_pending_tax,
)

TODAY = date(2026, 9, 29)


@pytest.fixture
def holding(make_position):
    return make_position(
        symbol='600519',
        name='测试股票',
        asset_type='stock',
        account_name='测试账户',
        quantity=1000,
        avg_price=10.0,
        current_price=12.0,
    )


def _div(holding, make_transaction, *, amount=500.0, day=date(2026, 6, 20), **kwargs):
    return make_transaction(
        position_id=holding.id,
        ledger_id=holding.ledger_id,
        txn_type='dividend',
        quantity=0,
        price=0,
        amount=amount,
        confirm_date=day,
        symbol=kwargs.pop('symbol', holding.symbol),
        **kwargs,
    )


def _tax(holding, make_transaction, *, amount=100.0, day=date(2026, 6, 25), **kwargs):
    """扣税流水：金额为负（与 orchestrator_commit 的落库口径一致）。"""
    return make_transaction(
        position_id=None,
        ledger_id=holding.ledger_id,
        txn_type='dividend_tax',
        quantity=0,
        price=0,
        amount=-abs(amount),
        confirm_date=day,
        symbol=kwargs.pop('symbol', holding.symbol),
        **kwargs,
    )


class TestScanPendingTax:
    def test_dividend_without_tax_is_reported(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        items = scan_pending_tax(db, 1, today=TODAY)
        assert len(items) == 1
        assert items[0].symbol == '600519'
        assert items[0].year == 2026
        assert items[0].dividend_cents == 50000

    def test_dividend_with_tax_same_year_is_not_reported(self, db, holding, make_transaction):
        """同标的同一年已有扣税流水 ⇒ 视为已结清（合并申报，逐笔对不上是常态）。"""
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0)
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_tax_in_other_year_does_not_clear_this_year(self, db, holding, make_transaction):
        """税是**按年**匹配的：去年的扣税不能抵扣今年的分红。"""
        _div(holding, make_transaction, amount=500.0, day=date(2026, 6, 20))
        _tax(holding, make_transaction, amount=100.0, day=date(2025, 6, 25))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert [i.year for i in items] == [2026]

    def test_tax_on_other_symbol_does_not_clear(self, db, holding, make_transaction):
        """别的标的记过税，不能抵这只标的的。"""
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0, symbol='000001')
        assert len(scan_pending_tax(db, 1, today=TODAY)) == 1

    def test_tax_on_other_account_does_not_clear(self, db, holding, make_transaction):
        """同标的不同券商账户是两本账，税不能互相冲抵。"""
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0, account_name='另一个账户')
        assert len(scan_pending_tax(db, 1, today=TODAY)) == 1

    def test_reinvest_dividend_is_excluded(self, db, holding, make_transaction):
        """红利再投：份额已增加、没有现金到手，不该催用户补一笔现金税。"""
        group = 'g-reinvest'
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=200.0,
            confirm_date=date(2026, 6, 20),
            link_group_id=group,
            symbol=holding.symbol,
        )
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='buy',
            quantity=100,
            price=2.0,
            amount=200.0,
            confirm_date=date(2026, 6, 20),
            link_group_id=group,
            symbol=holding.symbol,
        )
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_dividend_with_lone_link_group_is_still_counted(self, db, holding, make_transaction):
        """只有配对列、没有配对申购 ⇒ 仍是现金分红（防把通用配对列误判成再投）。"""
        _div(holding, make_transaction, amount=300.0, link_group_id='lone')
        assert len(scan_pending_tax(db, 1, today=TODAY)) == 1

    def test_non_positive_amount_is_skipped(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=0.0)
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_out_of_lookback_window_is_not_reported(self, db, holding, make_transaction):
        """一年以上的旧账不催：那笔税早已在券商交割单里结清。"""
        old_day = TODAY - timedelta(days=500)
        _div(holding, make_transaction, amount=500.0, day=old_day)
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_aggregates_same_symbol_same_year(self, db, holding, make_transaction):
        """同标的同年多笔分红合成一项（提醒不该一笔一条地刷屏）。"""
        _div(holding, make_transaction, amount=300.0, day=date(2026, 3, 10))
        _div(holding, make_transaction, amount=200.0, day=date(2026, 6, 20))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert len(items) == 1
        assert items[0].dividend_cents == 50000
        assert items[0].dividend_count == 2
        assert items[0].last_dividend_on == date(2026, 6, 20)

    def test_other_family_is_not_visible(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        assert scan_pending_tax(db, 2, today=TODAY) == []

    def test_sorted_by_amount_desc(self, db, holding, make_transaction):
        make_transaction(
            position_id=holding.id,
            ledger_id=holding.ledger_id,
            txn_type='dividend',
            quantity=0,
            price=0,
            amount=100.0,
            confirm_date=date(2026, 6, 20),
            symbol='000002',
            position_name='小额',
        )
        _div(holding, make_transaction, amount=900.0)
        items = scan_pending_tax(db, 1, today=TODAY)
        assert [i.dividend_cents for i in items] == [90000, 10000]


class TestNotificationCandidates:
    def test_one_candidate_per_symbol_per_year(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=300.0, day=date(2026, 3, 10))
        _div(holding, make_transaction, amount=200.0, day=date(2026, 6, 20))
        items = scan_pending_tax(db, 1, today=TODAY)
        candidates = build_notification_candidates(items, today=TODAY)
        assert len(candidates) == 1
        assert candidates[0]['source_type'] == SOURCE_TYPE

    def test_dedup_key_carries_the_dividend_year(self, db, holding, make_transaction):
        """dedup_key 必须含**分红所属年**，否则同一标的跨年只提醒一次。

        ⚠️ 断言不能写 `'2026' in dedup_key`：`build_dedup_key` 末尾本就带今天的日期
        （今天是 2026-09-29），去掉业务年份它照样含 '2026' —— 这正是本用例首版的写法，
        回退探针显示 MISSED。判据要绑在「业务年份紧挨着标的代码」这个形态上。
        """
        _div(holding, make_transaction, amount=300.0, day=date(2026, 3, 10))
        items = scan_pending_tax(db, 1, today=TODAY)
        candidates = build_notification_candidates(items, today=TODAY)
        assert ':600519:2026:' in candidates[0]['dedup_key']

    def test_same_symbol_next_year_gets_a_new_key(self, db, holding, make_transaction):
        """跨年视图：2025 与 2026 各一条、键不同（次年该提醒时不会被上一年吃掉）。

        `view_day` 取 2026-03-01、旧分红取 2025-12-10（相隔 81 天），是为了让两笔都落在
        400 天回溯窗口内——用 TODAY（2026-09-29）配 2025-06-10 会超窗口，只剩一条，
        用例就红在一个与判据无关的地方。
        """
        view_day = date(2026, 3, 1)
        _div(holding, make_transaction, amount=300.0, day=date(2025, 12, 10))
        _div(holding, make_transaction, amount=300.0, day=date(2026, 1, 10))
        items = scan_pending_tax(db, 1, today=view_day)
        assert sorted(i.year for i in items) == [2025, 2026]
        keys = [c['dedup_key'] for c in build_notification_candidates(items, today=view_day)]
        assert len(set(keys)) == 2
        assert any(':600519:2025:' in k for k in keys)
        assert any(':600519:2026:' in k for k in keys)

    def test_title_states_the_amount(self, db, holding, make_transaction):
        """标题必须让用户知道「哪只、哪年、多少钱」——只说「有未扣税」等于让他自己再数。"""
        _div(holding, make_transaction, amount=420.0)
        candidates = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        assert '420.00' in candidates[0]['title']

    def test_body_says_we_do_not_auto_calculate(self, db, holding, make_transaction):
        """正文必须诚实交代「不自动算税」，否则用户会以为账上的分红已是净额。"""
        _div(holding, make_transaction, amount=420.0)
        candidates = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        assert '不自动' in candidates[0]['body']

    def test_no_items_no_candidates(self):
        assert build_notification_candidates([], today=TODAY) == []


class TestApiEndpoint:
    """`GET /api/reconciliation/dividend-tax/` 的端到端形态。

    视图走 `user_session()`（另一个 Session），而 `make_transaction` 只 flush 不 commit，
    故这里必须显式 `db.commit()`——否则用例会红在「看不到自己刚写的数据」，
    看起来像端点坏了，实际是两套会话没对齐。
    """

    def test_endpoint_lists_pending(self, client, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        db.commit()
        resp = client.get('/api/reconciliation/dividend-tax/')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['data']['count'] == 1
        assert body['data']['total_cents'] == 50000
        assert body['data']['items'][0]['symbol'] == '600519'

    def test_endpoint_empty_when_cleared(self, client, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0)
        db.commit()
        resp = client.get('/api/reconciliation/dividend-tax/')
        data = resp.get_json()['data']
        assert data['items'] == [] and data['count'] == 0 and data['total_cents'] == 0

    def test_endpoint_writes_a_notification_visible_to_home(self, client, db, holding, make_transaction):
        """读完对账台后，首页那条「未读消息」就能看见（#541 的核心诉求）。

        这里断言的是**接线**而不是扫描：扫描用例全绿也可能一条通知都没写，
        用户仍不知道有这回事（AGENTS.md「宿主有没有把 isDirty 接进守卫」同型）。
        """
        _div(holding, make_transaction, amount=500.0)
        db.commit()
        client.get('/api/reconciliation/dividend-tax/')

        resp = client.get('/api/notifications/')
        body = resp.get_json()['data']
        assert body['unread_count'] == 1
        assert body['items'][0]['source_type'] == SOURCE_TYPE
        assert '分红未记扣税' in body['items'][0]['title']

    def test_repeated_reads_do_not_spam(self, client, db, holding, make_transaction):
        """幂等：连刷三次对账台，只留一条提醒。"""
        _div(holding, make_transaction, amount=500.0)
        db.commit()
        for _ in range(3):
            client.get('/api/reconciliation/dividend-tax/')
        assert client.get('/api/notifications/unread-count/').get_json()['data']['unread_count'] == 1

    def test_no_dividend_no_notification(self, client, db, holding, make_transaction):
        """没有分红就别造消息——空账本打开一次对账台不该冒出一条提醒。"""
        client.get('/api/reconciliation/dividend-tax/')
        assert client.get('/api/notifications/unread-count/').get_json()['data']['unread_count'] == 0
