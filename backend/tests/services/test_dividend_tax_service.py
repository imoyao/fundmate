# -*- coding: utf-8 -*-
"""红利税「待补记」识别回归（#541）。

判据（改实现前先看 `services/dividend_tax_service.py` 模块 docstring）：

1. 一笔现金分红**没有**配到扣税流水 ⇒ 报出来；
2. 配到了（同标的同账户、扣税日在分红日之后 N 天内）⇒ 不报；
3. **逐笔**判据：同一年有两次分红、只扣了一次税 ⇒ 第二次仍然要报（2026-10-19 修正，
   此前按年匹配，会让第二次分红等到明年才被看见——用户原话是「过了几个月才提醒，
   这消息有什么价值」）；
4. 红利再投不算、债券/存款派息不算、金额非正不算、无 symbol 不算、超窗口不催；
5. 通知粒度 = **每笔分红一条**，dedup_key 含分红日、不含今天 ⇒ 同一笔永不重复提醒，
   新分红立即提醒；
6. 已记税但比例超过 20%（红利税上限）⇒ 单独提示复核；
7. 补记入口 `record_tax` 幂等（同标的同一天只落一笔）。
"""

from datetime import date, timedelta

import pytest

from app.domains.transactions.models import Transaction
from app.services.dividend_tax_service import (
    SOURCE_TYPE,
    SOURCE_TYPE_SUSPECT,
    STATUS_PENDING,
    STATUS_SUSPECT,
    build_notification_candidates,
    compute_import_hash,
    record_tax,
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
    kwargs.setdefault('notes', '红利入账')
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
        assert items[0].status == STATUS_PENDING
        assert items[0].dividend_cents == 50000
        assert items[0].dividend_on == date(2026, 6, 20)

    def test_dividend_with_tax_nearby_is_not_reported(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0)
        assert scan_pending_tax(db, 1, today=TODAY) == []

    # ── 逐笔判据（本次的核心修正）─────────────────────────────────────────
    def test_second_dividend_still_reported_when_only_one_tax(self, db, holding, make_transaction):
        """同一年两次分红、只扣了一次税 ⇒ **第二次必须仍然报出来**。

        这是「按年匹配」换成「逐笔匹配」的直接证据：按年的写法下，第一笔的税会把
        7 月那笔也顺手「结清」，而用户要到明年才会再被提醒一次 —— 提醒失去意义。
        """
        _div(holding, make_transaction, amount=500.0, day=date(2026, 6, 20))
        _tax(holding, make_transaction, amount=100.0, day=date(2026, 6, 25))
        _div(holding, make_transaction, amount=800.0, day=date(2026, 7, 20))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert len(items) == 1
        assert items[0].dividend_cents == 80000
        assert items[0].dividend_on == date(2026, 7, 20)

    def test_second_dividend_not_reported_when_it_has_its_own_tax(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0, day=date(2026, 6, 20))
        _tax(holding, make_transaction, amount=100.0, day=date(2026, 6, 25))
        _div(holding, make_transaction, amount=800.0, day=date(2026, 7, 20))
        _tax(holding, make_transaction, amount=80.0, day=date(2026, 7, 23))
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_tax_before_dividend_does_not_clear_it(self, db, holding, make_transaction):
        """扣税日**早于**分红日的不算配对（那是上一笔的税，串过来就是漏提醒）。"""
        _tax(holding, make_transaction, amount=100.0, day=date(2026, 6, 1))
        _div(holding, make_transaction, amount=500.0, day=date(2026, 6, 20))
        _tax(holding, make_transaction, amount=100.0, day=date(2025, 12, 1))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert [i.dividend_on for i in items] == [date(2026, 6, 20)]

    def test_tax_outside_window_does_not_clear(self, db, holding, make_transaction):
        """窗口外（默认 30 天）的扣税不配对：上上季的合并扣税不该掩盖这一笔。"""
        _div(holding, make_transaction, amount=500.0, day=date(2026, 3, 1))
        _tax(holding, make_transaction, amount=100.0, day=date(2026, 6, 20))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert len(items) == 1

    def test_one_tax_cannot_clear_two_dividends(self, db, holding, make_transaction):
        """一笔扣税只能用一次（额度不会被两笔分红同时认领）。"""
        _div(holding, make_transaction, amount=300.0, day=date(2026, 6, 10))
        _div(holding, make_transaction, amount=300.0, day=date(2026, 6, 20))
        _tax(holding, make_transaction, amount=60.0, day=date(2026, 6, 25))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert len(items) == 1
        # 两笔金额相同 ⇒ 按分红日升序，配早的那笔
        assert items[0].dividend_on == date(2026, 6, 20)

    def test_merged_tax_clears_only_one(self, db, holding, make_transaction):
        """合并扣税（一笔税对应多笔分红）⇒ 只结清一笔，另一笔继续提醒。

        刻意不做「按金额拆着分摊」：券商怎么合并的我们无从得知，
        均摊出来的结果是编的。宁可多提醒用户一次，不可漏提醒一笔。
        """
        _div(holding, make_transaction, amount=100.0, day=date(2026, 6, 10))
        _div(holding, make_transaction, amount=500.0, day=date(2026, 6, 20))
        _tax(holding, make_transaction, amount=60.0, day=date(2026, 6, 25))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert len(items) == 1
        # 优先结清**大额**那笔（税按股息金额收，先贴大额才不会把它的税藏在尾巴里）
        assert items[0].dividend_on == date(2026, 6, 10)

    # ── 排除项 ──────────────────────────────────────────────────────────
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

    def test_interest_income_is_not_a_dividend(self, db, holding, make_transaction):
        """「利息归本」也落 `txn_type='dividend'`，但它是存款/理财利息，没有红利税。

        不排掉它，用户会被推着去给一笔利息补一笔根本不存在的税 —— 一次误提醒
        就足以让这个提醒功能失去信任。
        """
        _div(holding, make_transaction, amount=300.0, notes='利息归本')
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_bond_interest_is_not_a_dividend(self, db, holding, make_transaction):
        """可转债派息是利息（且「债券兑息兑付」在导入侧还被映射成扣税行）。"""
        _div(holding, make_transaction, amount=300.0, notes='债券兑息')
        assert scan_pending_tax(db, 1, today=TODAY) == []
        # 流水自带 `asset_type='bond'`（持仓表里同代码是股票）⇒ 仍按利息排除
        _div(holding, make_transaction, amount=300.0, notes='利息入账', asset_type='bond')
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_non_dividend_notes_is_skipped(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=300.0, notes='配股退款退息')
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_non_positive_amount_is_skipped(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=0.0)
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_out_of_lookback_window_is_not_reported(self, db, holding, make_transaction):
        """一年以上的旧账不催：那笔税早已在券商交割单里结清。"""
        old_day = TODAY - timedelta(days=500)
        _div(holding, make_transaction, amount=500.0, day=old_day)
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_tax_on_other_symbol_does_not_clear(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0, symbol='000001')
        assert len(scan_pending_tax(db, 1, today=TODAY)) == 1

    def test_tax_on_other_account_does_not_clear(self, db, holding, make_transaction):
        """同标的不同券商账户是两本账，税不能互相冲抵。"""
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0, account_name='另一个账户')
        assert len(scan_pending_tax(db, 1, today=TODAY)) == 1

    def test_other_family_is_not_visible(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        assert scan_pending_tax(db, 2, today=TODAY) == []

    def test_sorted_by_dividend_date_desc(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=100.0, day=date(2026, 3, 10))
        _div(holding, make_transaction, amount=900.0, day=date(2026, 6, 20))
        items = scan_pending_tax(db, 1, today=TODAY)
        assert [i.dividend_on for i in items] == [date(2026, 6, 20), date(2026, 3, 10)]


class TestSuspectRatio:
    """已记税但比例离谱 ⇒ 单独提示「是不是记错了品种」。"""

    def test_ratio_over_cap_is_reported_as_suspect(self, db, holding, make_transaction):
        """1000 元分红扣了 300 元（30% > 20% 上限）⇒ 不可能是红利税，提示核对。"""
        _div(holding, make_transaction, amount=1000.0)
        _tax(holding, make_transaction, amount=300.0)
        items = scan_pending_tax(db, 1, today=TODAY)
        assert len(items) == 1
        assert items[0].status == STATUS_SUSPECT
        assert items[0].tax_cents == 30000

    def test_ratio_within_cap_is_silent(self, db, holding, make_transaction):
        _div(holding, make_transaction, amount=1000.0)
        _tax(holding, make_transaction, amount=200.0)
        assert scan_pending_tax(db, 1, today=TODAY) == []

    def test_small_dividend_is_not_checked_for_ratio(self, db, holding, make_transaction):
        """小额分红不查比例：几块钱的东西算出来 25% 也不说明问题，提示只会让人烦。"""
        _div(holding, make_transaction, amount=50.0)
        _tax(holding, make_transaction, amount=30.0)
        assert scan_pending_tax(db, 1, today=TODAY) == []


class TestNotificationCandidates:
    def test_one_candidate_per_dividend(self, db, holding, make_transaction):
        """两次分红、都没扣税 ⇒ 两条候选（各说各的日期与金额）。"""
        _div(holding, make_transaction, amount=300.0, day=date(2026, 3, 10))
        _div(holding, make_transaction, amount=200.0, day=date(2026, 6, 20))
        candidates = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        assert len(candidates) == 2
        assert {c['source_type'] for c in candidates} == {SOURCE_TYPE}

    def test_dedup_key_carries_the_dividend_date(self, db, holding, make_transaction):
        """dedup_key 必须钉在**分红日**上，且**不含今天**。

        ⚠️ 断言不能写 `'2026' in dedup_key`：今天也是 2026 年，去掉业务日期照样命中
        （这条弱断言的教训上一次已经踩过）。要绑在「标的紧挨着完整分红日」这个形态上。
        """
        _div(holding, make_transaction, amount=300.0, day=date(2026, 3, 10))
        candidates = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        assert candidates[0]['dedup_key'] == f'{SOURCE_TYPE}:600519:2026-03-10'

    def test_dedup_key_does_not_roll_with_today(self, db, holding, make_transaction):
        """**幂等的核心**：换个「今天」再算一次，键必须一模一样。

        首版用的是 `build_dedup_key(...)`（末尾追加今天），等于同一笔分红
        每天都能冒出来一条新消息 —— 用户原话「不能重复提醒」直接落空。
        """
        _div(holding, make_transaction, amount=300.0, day=date(2026, 3, 10))
        items = scan_pending_tax(db, 1, today=TODAY)
        key_today = build_notification_candidates(items, today=TODAY)[0]['dedup_key']
        key_tomorrow = build_notification_candidates(items, today=TODAY + timedelta(days=1))[0]['dedup_key']
        assert key_today == key_tomorrow

    def test_new_dividend_gets_a_new_key(self, db, holding, make_transaction):
        """新分红 ⇒ 新键 ⇒ **立刻**能提醒（不必等到下一年）。"""
        _div(holding, make_transaction, amount=300.0, day=date(2026, 3, 10))
        first = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        _div(holding, make_transaction, amount=200.0, day=date(2026, 6, 20))
        second = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        assert len({c['dedup_key'] for c in first + second}) == 2

    def test_title_states_symbol_date_and_amount(self, db, holding, make_transaction):
        """标题必须让用户知道「哪只、哪天、多少钱」——只说「有未扣税」等于让他自己再数。"""
        _div(holding, make_transaction, amount=420.0, day=date(2026, 6, 20))
        candidates = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        title = candidates[0]['title']
        assert '420.00' in title and '06-20' in title

    def test_body_says_we_do_not_auto_calculate(self, db, holding, make_transaction):
        """正文必须诚实交代「不自动算税」，否则用户会以为账上的分红已是净额。"""
        _div(holding, make_transaction, amount=420.0)
        candidates = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        assert '不自动' in candidates[0]['body']

    def test_suspect_candidate_uses_its_own_source_type(self, db, holding, make_transaction):
        """「比例异常」与「未扣税」是两种诉求，不能共用一个 source_type（否则前端无法分色）。"""
        _div(holding, make_transaction, amount=1000.0)
        _tax(holding, make_transaction, amount=300.0)
        candidates = build_notification_candidates(scan_pending_tax(db, 1, today=TODAY), today=TODAY)
        assert candidates[0]['source_type'] == SOURCE_TYPE_SUSPECT
        assert '核对' in candidates[0]['title']

    def test_no_items_no_candidates(self):
        assert build_notification_candidates([], today=TODAY) == []


class TestRecordTax:
    """补记入口：提醒里点一下就记上，且同一天重复点只落一笔。"""

    def test_records_negative_tax_txn(self, db, holding):
        txn = record_tax(db, 1, symbol='600519', amount_cents=12345, tax_on=date(2026, 6, 25))
        db.commit()
        assert txn.txn_type == 'dividend_tax'
        assert txn.amount == -12345
        assert txn.confirm_date == date(2026, 6, 25)
        assert txn.family_id == 1

    def test_same_symbol_same_day_is_idempotent(self, db, holding):
        first = record_tax(db, 1, symbol='600519', amount_cents=12345, tax_on=date(2026, 6, 25))
        db.commit()
        second = record_tax(db, 1, symbol='600519', amount_cents=99999, tax_on=date(2026, 6, 25))
        db.commit()
        assert second.id == first.id
        assert db.query(Transaction).filter(Transaction.txn_type == 'dividend_tax').count() == 1

    def test_out_of_range_amount_is_rejected(self, db, holding):
        with pytest.raises(ValueError):
            record_tax(db, 1, symbol='600519', amount_cents=0)

    def test_missing_symbol_is_rejected(self, db):
        with pytest.raises(ValueError):
            record_tax(db, 1, symbol='  ', amount_cents=100)

    def test_import_hash_is_stable_and_short(self):
        key = compute_import_hash('600519', date(2026, 6, 25))
        assert key == compute_import_hash('600519', date(2026, 6, 25))
        assert len(key) <= 64

    def test_import_hash_distinguishes_symbols(self):
        """幂等键必须含标的：否则「同一天给两只股票各补一笔税」会被自己的去重挡掉。

        这个洞的复现门槛很高（要同一天记两只票的税，再靠唯一约束撞出来），
        `record_tax` 的「先查」分支会把它掩盖，所以直接钉在键的形态上。
        """
        assert compute_import_hash('600519', date(2026, 6, 25)) != compute_import_hash('000001', date(2026, 6, 25))

    def test_recorded_tax_clears_the_reminder(self, db, holding, make_transaction):
        """记完之后这笔分红就不再出现在待办里（闭环）。"""
        _div(holding, make_transaction, amount=500.0, day=date(2026, 6, 20))
        assert len(scan_pending_tax(db, 1, today=TODAY)) == 1
        record_tax(db, 1, symbol='600519', amount_cents=10000, tax_on=date(2026, 6, 25))
        db.commit()
        assert scan_pending_tax(db, 1, today=TODAY) == []


class TestApiEndpoint:
    """`/api/reconciliation/dividend-tax/` 的端到端形态。

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
        assert body['data']['pending_count'] == 1
        assert body['data']['total_cents'] == 50000
        assert body['data']['items'][0]['symbol'] == '600519'

    def test_endpoint_empty_when_cleared(self, client, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        _tax(holding, make_transaction, amount=100.0)
        db.commit()
        data = client.get('/api/reconciliation/dividend-tax/').get_json()['data']
        assert data['items'] == [] and data['count'] == 0 and data['total_cents'] == 0

    def test_endpoint_writes_a_notification_visible_to_home(self, client, db, holding, make_transaction):
        """读完对账台后，首页那条「未读消息」就能看见（#541 的核心诉求）。

        这里断言的是**接线**而不是扫描：扫描用例全绿也可能一条通知都没写，
        用户仍不知道有这回事（AGENTS.md「宿主有没有把 isDirty 接进守卫」同型）。
        """
        _div(holding, make_transaction, amount=500.0)
        db.commit()
        client.get('/api/reconciliation/dividend-tax/')

        body = client.get('/api/notifications/').get_json()['data']
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

    def test_record_endpoint_creates_tax(self, client, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        db.commit()
        resp = client.post(
            '/api/reconciliation/dividend-tax/record/',
            json={'symbol': '600519', 'amount': 100.0, 'tax_on': '2026-06-25'},
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['amount_cents'] == -10000
        titles = [n['title'] for n in client.get('/api/notifications/').get_json()['data']['items']]
        # 记完之后对账台已无待办
        data = client.get('/api/reconciliation/dividend-tax/').get_json()['data']
        assert data['count'] == 0
        assert all('分红未记扣税' not in t for t in titles)

    def test_record_endpoint_is_idempotent(self, client, db, holding, make_transaction):
        _div(holding, make_transaction, amount=500.0)
        db.commit()
        first = client.post(
            '/api/reconciliation/dividend-tax/record/',
            json={'symbol': '600519', 'amount': 100.0, 'tax_on': '2026-06-25'},
        )
        second = client.post(
            '/api/reconciliation/dividend-tax/record/',
            json={'symbol': '600519', 'amount': 100.0, 'tax_on': '2026-06-25'},
        )
        assert first.get_json()['data']['id'] == second.get_json()['data']['id']
        assert db.query(Transaction).filter(Transaction.txn_type == 'dividend_tax').count() == 1

    def test_record_endpoint_rejects_bad_payload(self, client, db, holding):
        assert client.post('/api/reconciliation/dividend-tax/record/', json={}).status_code == 400
        assert client.post('/api/reconciliation/dividend-tax/record/', json={'symbol': '600519'}).status_code == 400
        assert (
            client.post(
                '/api/reconciliation/dividend-tax/record/',
                json={'symbol': '600519', 'amount': 10, 'tax_on': '2026/06/25'},
            ).status_code
            == 400
        )
