# -*- coding: utf-8 -*-
"""#2372 回归：Account ID 关联修复（快照回填 / ID 回解析 / 身份键匹配）。

Bug 三症状（基金转换记账，issue #2372）：
1. 持仓明细里产品名称没带进来（显示基金 6 位编码）；
2. 交易记录里记成「未知资产」；
3. 产品详情页交易记录账户显示「未知账户」。

根因链（真库实证：转换当天流水 id=3001 两个快照全 NULL，而 ledger_id=16 /
position_id=618 都有值；621 笔流水 position_id 悬空；48 笔 position_name 为空/不符）：
- ``position_name`` / ``account_name`` 是**冗余快照**不是外键。基金转换转入腿
  （``conversion_service`` in_data）只传 ``ledger_id`` 不传名称 → 快照落 NULL；
- 读取侧（``transaction_service`` / ``ledger_service`` / 孤儿明细）把「快照没写」
  当成「数据未知」，直接兜底「未知资产 / 未知账户」；
- 更危险的是多处查询/删除拿**可编辑的** ``account_name`` 当关联键——真库存在
  重名账户（支付宝×2 / 天天基金×2），改名即失配、重名即串账户甚至误删流水。

修复口径（本文件逐条回归）：
- 写入侧：快照缺失时按 ID 回填（symbol→基金名录 / ledger_id→ledgers）+ 存量行自愈；
- 读取侧：``resolve_transaction_display_names`` 三级回解析，快照缺失不再显示「未知」；
- 查询侧：``(symbol, account_name)`` 兜底全部改身份键 ``(ledger_id, symbol)``；
- 同步任务：分红/送股逐持仓行发记录并带 ``ledger_id``，去重键 ``(ledger_id, import_hash)``；
- 更新路径：``ledger_id`` 变更时同步 ``account_name`` 快照；
- 分组：``group_by=account`` 键为 ``str(ledger_id)``（None → ``'unfiled'``）。
"""

from datetime import date, timedelta
from decimal import Decimal

from app.core.money import Money
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.position_service import PositionService, _find_position_by_identity
from app.services.transaction_service import build_transaction_list
from app.services.txn_name_resolver import resolve_transaction_display_names

from tests.services.sync.test_dividend_split_job import _FakeAdapter
from tests.services.test_conversion_submit import (
    IDEMPOTENCY_KEY,
    _group_txns,
    _make_out_position,
    _seed_two_funds,
    _submit,
)

TODAY = date(2026, 10, 20)
# #541 起分红/送转事件有 400 天回看窗口（EVENT_LOOKBACK_DAYS）：用例事件日期
# 必须落在窗口内，否则先被过期过滤、压根走不到逐户逻辑（测了个寂寞）。
RECENT = TODAY - timedelta(days=30)


def _make_ledger(db, name):
    """建账户行并返回 id（**不去重**：重名账户是 #2372 的核心场景，必须可造）。"""
    ledger = Ledger(name=name, ledger_type='bank', family_id=1)
    db.add(ledger)
    db.flush()
    return ledger.id


def _seed_fund(db, code, name):
    fund = Fund(fund_code=code, name=name)
    db.add(fund)
    db.commit()
    return fund


# ── A 写入侧：快照按 ID 回填（症状 1/2/3 的直接根因） ─────────────────────────


def test_conversion_in_leg_backfills_snapshots_by_id(db, make_position, make_transaction):
    """转换 IN 腿只传 ledger_id：落库后持仓行与两条流水快照都必须按 ID 回填。

    复现真库流水 3001：``in_data`` 没有 name/account_name，旧代码把
    ``position.name=NULL`` 与流水两个 NULL 快照原样落库 → 持仓明细显示 6 位编码、
    交易列表显示「未知资产/未知账户」。新代码在写入侧按 symbol/ledger_id 反查补全。
    """
    _seed_two_funds(db)
    pos = _make_out_position(db, make_position, make_transaction)  # 账户名『转换测试账户』

    _submit(db, pos)

    in_pos = db.query(Position).filter_by(symbol='000002').first()
    assert in_pos is not None
    # 持仓行快照（旧代码：两个字段均 NULL）
    assert in_pos.name == '转入基金'
    assert in_pos.account_name == '转换测试账户'

    in_txn = db.query(Transaction).filter_by(link_group_id=IDEMPOTENCY_KEY, txn_type='buy', asset_type='fund').first()
    assert in_txn.position_name == '转入基金'
    assert in_txn.account_name == '转换测试账户'

    out_txn = db.query(Transaction).filter_by(link_group_id=IDEMPOTENCY_KEY, txn_type='sell').first()
    assert out_txn.position_name == '转出基金'
    assert out_txn.account_name == '转换测试账户'


def test_existing_position_snapshot_self_heals_on_buy(db, make_position):
    """存量持仓快照缺失（name=NULL）：再次买入走合并分支时按 ID 自愈回填。

    真库 618 号持仓 ``name`` 为 NULL 的修复路径：不需要用户手工改，任何一次
    正常买入都应当把缺失快照补上（仅在缺失时写，已有快照不动）。
    """
    _seed_fund(db, '000301', '自愈基金')
    ledger_id = _make_ledger(db, '自愈账户')
    pos = make_position(
        symbol='000301',
        name=None,  # 存量坏行：快照漏写
        ledger_id=ledger_id,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    assert pos.name is None and pos.account_name is None

    PositionService.process_buy_or_deposit(
        db,
        {
            'symbol': '000301',
            'op_type': 'buy',
            'asset_type': 'fund',
            'quantity': 100,
            'avg_price': 1.0,
            'fee': 0,
            'trade_date': TODAY,
            'confirm_date': TODAY,
            'ledger_id': ledger_id,
            'family_id': 1,
            'venue': 'OTC',
        },
        force_create_position=False,
    )
    db.refresh(pos)

    assert pos.name == '自愈基金'  # 按 symbol 反查基金名录
    assert pos.account_name == '自愈账户'  # 按 ledger_id 反查账户


# ── B 读取侧：快照缺失按 ID 回解析，不再显示「未知」 ─────────────────────────


def test_transaction_list_resolves_names_by_ids(db, make_position, make_transaction):
    """真库流水 3001 复现：两个快照全 NULL，ledger_id/position_id 都有值。

    读取侧必须按 ID 回解析出真实名称；旧代码直接显示「未知资产/未知账户」。
    """
    _seed_fund(db, '000401', '回解析基金')
    ledger_id = _make_ledger(db, '回解析账户')
    pos = make_position(
        symbol='000401',
        name='回解析基金',
        ledger_id=ledger_id,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    txn = make_transaction(
        position_id=pos.id,
        ledger_id=ledger_id,
        symbol='000401',
        position_name=None,  # 快照漏写
        quantity=100,
        price=1.0,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    txn.account_name = None  # 夹具对 account_name 有 '测试账户' 兜底，只能落库后置空
    db.commit()

    result = build_transaction_list(db, family_id=1, page=1, per_page=50, filters={})
    row = next(r for r in result['data'] if r['id'] == txn.id)

    assert row['position_name'] == '回解析基金'  # position_id 点查持仓
    assert row['account_name'] == '回解析账户'  # ledger_id 点查账户


def test_transaction_list_resolves_dangling_position_by_symbol(db, make_transaction):
    """position_id 悬空（真库 621 笔）：按 symbol 点查 market 名录兜底。"""
    _seed_fund(db, '000402', '悬空兜底基金')
    ledger_id = _make_ledger(db, '悬空账户')
    txn = make_transaction(
        position_id=999999,  # 指向不存在的持仓
        ledger_id=ledger_id,
        symbol='000402',
        position_name=None,
        quantity=100,
        price=1.0,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    txn.account_name = None
    db.commit()

    result = build_transaction_list(db, family_id=1, page=1, per_page=50, filters={})
    row = next(r for r in result['data'] if r['id'] == txn.id)

    assert row['position_name'] == '悬空兜底基金'  # 按 symbol 反查基金名录
    assert row['account_name'] == '悬空账户'


def test_resolver_prefers_snapshot_and_never_writes(db, make_transaction):
    """快照已在的行行为零变化；resolver 是纯读（不借机改库）。"""
    ledger_id = _make_ledger(db, '快照优先账户')
    txn = make_transaction(
        position_id=None,
        ledger_id=ledger_id,
        symbol='000403',
        position_name='快照名',
        account_name='快照账户名',
        quantity=10,
        price=1.0,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    db.commit()

    pos_names, ledger_names = resolve_transaction_display_names(db, [txn])
    assert pos_names == {} and ledger_names == {}  # 快照已在 → 不进映射
    db.refresh(txn)
    assert txn.position_name == '快照名' and txn.account_name == '快照账户名'  # 纯读未写库


def test_transaction_list_unknown_only_when_truly_unknown(db, make_transaction):
    """反向：快照、position_id、ledger_id、symbol 全无线索时才允许「未知」。"""
    txn = make_transaction(
        position_id=None,
        ledger_id=None,
        symbol='',
        position_name=None,
        account_name=None,
        asset_type='cash',
        txn_type='deposit',
        quantity=0,
        price=0,
        amount=100,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    txn.account_name = None
    db.commit()

    result = build_transaction_list(db, family_id=1, page=1, per_page=50, filters={})
    row = next(r for r in result['data'] if r['id'] == txn.id)
    assert row['position_name'] == '未知资产' and row['account_name'] == '未知账户'


# ── C 查询侧：重名账户下不得串数据 / 误删 ────────────────────────────────────


def _seed_same_name_accounts_with_positions(db, make_position, make_transaction):
    """两个**同名**账户（支付宝×2），各持同代码基金各一笔流水。"""
    ledger_a = _make_ledger(db, '支付宝')
    ledger_b = _make_ledger(db, '支付宝')
    pos_a = make_position(
        symbol='000501',
        name='重名基金A',
        ledger_id=ledger_a,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    pos_b = make_position(
        symbol='000501',
        name='重名基金B',
        ledger_id=ledger_b,
        asset_type='fund',
        quantity=200,
        avg_price=1.0,
        current_price=1.0,
    )
    txn_a = make_transaction(
        position_id=pos_a.id,
        ledger_id=ledger_a,
        symbol='000501',
        account_name='支付宝',
        position_name='重名基金A',
        quantity=100,
        price=1.0,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    txn_b = make_transaction(
        position_id=pos_b.id,
        ledger_id=ledger_b,
        symbol='000501',
        account_name='支付宝',
        position_name='重名基金B',
        quantity=200,
        price=1.0,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    db.commit()
    return ledger_a, ledger_b, pos_a, pos_b, txn_a, txn_b


def test_position_transactions_scoped_by_ledger_id(client, db, make_position, make_transaction):
    """持仓详情页「交易记录」兜底必须按 ledger_id 收敛。

    旧代码按 (symbol, account_name) 匹配：两个『支付宝』账户下同名持仓的交易会
    互相串出来。修复后只返回本账户（本持仓）的交易。
    """
    _ledger_a, _ledger_b, pos_a, _pos_b, txn_a, txn_b = _seed_same_name_accounts_with_positions(
        db, make_position, make_transaction
    )

    resp = client.get(f'/api/positions/{pos_a.id}/transactions/')
    assert resp.status_code == 200
    ids = {t['id'] for t in resp.get_json()['data']}
    assert txn_a.id in ids
    assert txn_b.id not in ids  # 重名账户 B 的交易不得串入


def test_delete_position_fallback_scoped_by_ledger_id(client, db, make_position, make_transaction):
    """删持仓的兜底删除按 ledger_id 收敛——重名账户下不得误删别人的流水。

    旧代码按 (symbol, account_name) 删：会把另一个『支付宝』账户的同代码交易
    一并删掉（不可恢复）。构造 position_id 悬空的孤儿流水强制走兜底分支。
    """
    ledger_a = _make_ledger(db, '支付宝')
    ledger_b = _make_ledger(db, '支付宝')
    pos_a = make_position(
        symbol='000502',
        name='待删持仓',
        ledger_id=ledger_a,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    # 两条 position_id 悬空的孤儿流水（symbol 相同、account_name 相同、ledger_id 不同）
    txn_a = make_transaction(
        position_id=None,
        ledger_id=ledger_a,
        symbol='000502',
        account_name='支付宝',
        quantity=100,
        price=1.0,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    txn_b = make_transaction(
        position_id=None,
        ledger_id=ledger_b,
        symbol='000502',
        account_name='支付宝',
        quantity=200,
        price=1.0,
        confirm_date=TODAY,
        trade_date=TODAY,
    )
    db.commit()
    txn_a_id, txn_b_id = txn_a.id, txn_b.id  # 删除后实例已失效，先存 ID

    from sqlalchemy import exists as _exists

    resp = client.delete(f'/api/positions/{pos_a.id}/?delete_transactions=true')
    assert resp.status_code == 200

    # exists() 查询绕过夹具会话缓存（同 test_positions.py 的删除验证模式）
    assert not db.query(_exists().where(Transaction.id == txn_a_id)).scalar()  # 本账户孤儿流水被删
    assert db.query(_exists().where(Transaction.id == txn_b_id)).scalar()  # 重名账户的流水必须保留（旧代码会误删）


# ── D 孤儿/导入链路：身份键 (ledger_id, symbol) 匹配 ─────────────────────────


def test_find_position_by_identity_prefers_ledger_id(db, make_position):
    """重名账户：身份键按 ledger_id 精确定位，绝不按 account_name 跨账户猜。"""
    ledger_a = _make_ledger(db, '支付宝')
    ledger_b = _make_ledger(db, '支付宝')
    pos_a = make_position(
        symbol='000601',
        name='基金A',
        ledger_id=ledger_a,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    pos_b = make_position(
        symbol='000601',
        name='基金B',
        ledger_id=ledger_b,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )

    hit = _find_position_by_identity(db, {'family_id': 1, 'ledger_id': ledger_b}, symbol='000601')
    assert hit is not None and hit.id == pos_b.id

    # ledger_id 为空 → 只匹配未归档持仓，不得回退到按账户名猜
    assert _find_position_by_identity(db, {'family_id': 1}, symbol='000601') is None
    assert pos_a.id != pos_b.id


def test_find_position_by_identity_unfiled_only(db, make_position):
    """未归档数据（ledger_id 为空）只在未归档持仓里匹配。"""
    ledger_id = _make_ledger(db, '已归档账户')
    filed = make_position(
        symbol='000602',
        name='已归档持仓',
        ledger_id=ledger_id,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    unfiled = make_position(
        symbol='000602',
        name='未归档持仓',
        ledger_id=None,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    db.commit()

    hit = _find_position_by_identity(db, {'family_id': 1}, symbol='000602')
    assert hit is not None and hit.id == unfiled.id
    assert hit.id != filed.id


def test_find_position_by_identity_name_fallback_within_ledger(db, make_position):
    """无 symbol（交割单场景，库里存空串）时按 (ledger_id, name) 兜底——账户内才准。"""
    ledger_a = _make_ledger(db, '券商A')
    ledger_b = _make_ledger(db, '券商B')
    pos_b = make_position(
        symbol='',
        name='某某证券',
        ledger_id=ledger_b,
        asset_type='stock',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    db.commit()

    hit = _find_position_by_identity(db, {'family_id': 1, 'ledger_id': ledger_b}, name='某某证券')
    assert hit is not None and hit.id == pos_b.id
    # 换个账户 ID 同样的名字不得命中（旧代码按 account_name 匹配会串）
    assert _find_position_by_identity(db, {'family_id': 1, 'ledger_id': ledger_a}, name='某某证券') is None


def test_orphan_sell_lands_on_ledger_matched_position(db, make_position):
    """孤儿卖出按 ledger_id 落到正确账户的持仓，重名账户另一个的份额不变。"""
    ledger_a = _make_ledger(db, '支付宝')
    ledger_b = _make_ledger(db, '支付宝')
    pos_a = make_position(
        symbol='000603',
        name='基金A',
        ledger_id=ledger_a,
        asset_type='fund',
        quantity=1000,
        avg_price=1.0,
        current_price=1.0,
    )
    pos_b = make_position(
        symbol='000603',
        name='基金B',
        ledger_id=ledger_b,
        asset_type='fund',
        quantity=1000,
        avg_price=1.0,
        current_price=1.0,
    )
    db.commit()

    PositionService.process_orphan_sell_or_withdraw(
        db,
        {
            'symbol': '000603',
            'op_type': 'sell',
            'asset_type': 'fund',
            'quantity': 100,
            'avg_price': 1.2,
            'fee': 0,
            'trade_date': TODAY,
            'confirm_date': TODAY,
            'ledger_id': ledger_b,  # 明确属于账户 B
            'account_name': '支付宝',  # 可编辑快照：与 A 同名，旧代码会按它猜中 A
            'family_id': 1,
        },
    )
    db.refresh(pos_a)
    db.refresh(pos_b)

    assert Money.min_unit_to_shares(pos_b.quantity) == 900  # B 被正确扣减
    assert Money.min_unit_to_shares(pos_a.quantity) == 1000  # A 一个份都没动


# ── E 同步任务：分红/送股逐持仓行带 ledger_id，去重键含账户 ──────────────────


def _make_dividend_job(db):
    from app.services.sync.jobs.dividend_split_job import DividendSplitSyncJob

    return DividendSplitSyncJob(_FakeAdapter(), db)


def test_dividend_event_records_per_position_with_ledger_id(db, make_position):
    """一个分红事件 → 按持仓行逐户发记录，各带自己的 ledger_id。

    旧代码发家庭汇总单条记录且 account_name=''，导入侧按 (symbol, account_name='')
    只能命中空名持仓——正常持仓全变孤儿；同名账户下 .first() 还会记错账户。
    """
    ledger_a = _make_ledger(db, '天天基金')
    ledger_b = _make_ledger(db, '天天基金')
    make_position(
        symbol='SH600000',
        name='浦发银行A',
        account_name='天天基金',
        ledger_id=ledger_a,
        asset_type='stock',
        quantity=1000,
        avg_price=10.0,
        current_price=10.0,
    )
    make_position(
        symbol='SH600000',
        name='浦发银行B',
        account_name='天天基金',
        ledger_id=ledger_b,
        asset_type='stock',
        quantity=2000,
        avg_price=10.0,
        current_price=10.0,
    )
    ledger_c = _make_ledger(db, '天天基金')
    make_position(  # 0 份额行：不得产生记录（uq_positions_ledger_symbol：另开账户放）
        symbol='SH600000',
        name='浦发银行C',
        account_name='天天基金',
        ledger_id=ledger_c,
        asset_type='stock',
        quantity=0,
        avg_price=10.0,
        current_price=10.0,
    )
    db.commit()

    job = _make_dividend_job(db)
    records = job._events_to_records(
        {
            'symbol': 'SH600000',
            'ex_date': RECENT,
            'bonus_ratio': 0.0,
            'transfer_ratio': 0.0,
            'cash_ratio': 2.0,
            'desc': '10派2',
        }
    )

    assert len(records) == 2  # 逐持仓行，0 份额行跳过
    by_ledger = {r.ledger_id: r for r in records}
    assert set(by_ledger) == {ledger_a, ledger_b}
    assert by_ledger[ledger_a].amount == Decimal('200')  # 1000 × 2 / 10
    assert by_ledger[ledger_b].amount == Decimal('400')  # 2000 × 2 / 10
    assert by_ledger[ledger_a].account_name == '天天基金'
    # 同一事件跨账户的 import_hash 相同（hash 口径不含账户）——靠去重键区分
    assert by_ledger[ledger_a].import_hash == by_ledger[ledger_b].import_hash


def test_dividend_deduplicate_keeps_same_hash_across_ledgers(db):
    """去重键 (ledger_id, import_hash)：跨账户同 hash 是两笔，不是重复。

    旧代码只按 import_hash 去重：第二个账户的分红会被当重复整条丢掉——
    用户那个账户永远收不到这笔分红（且不会报错，静默丢失）。
    """
    from app.services.import_records import StandardTransactionRecord, compute_record_hash

    job = _make_dividend_job(db)

    def _rec(ledger_id):
        r = StandardTransactionRecord(
            confirm_date=date(2024, 6, 1),
            asset_type='stock',
            symbol='SH600000',
            name='浦发银行',
            business_type='dividend',
            amount=Decimal('200'),
            shares=Decimal('0'),
            nav=Decimal('0'),
            account_name='天天基金',
            ledger_id=ledger_id,
            source='akshare_dividend',
        )
        r.import_hash = compute_record_hash(r.source, r)
        return r

    ra, rb = _rec(11), _rec(22)
    assert ra.import_hash == rb.import_hash  # 前提：hash 口径确实不含账户

    unique = job._deduplicate([ra, ra, rb])
    assert len(unique) == 2  # 同账户重复只留一；跨账户同 hash 都必须留
    assert {r.ledger_id for r in unique} == {11, 22}


def test_dividend_holding_query_failure_still_skips(db):
    """#1833 不回归：持仓查询失败仍返回空记录列表（不写 0 金额流水）。"""
    job = _make_dividend_job(db)

    class _Boom:
        def query(self, *_a, **_k):
            raise RuntimeError('db down')

    job.db = _Boom()
    job.stats = {}
    assert job._position_rows('SH600000') is None
    assert any(e.get('stage') == 'holding_query' for e in job.stats['errors'])

    records = job._events_to_records(
        {
            'symbol': 'SH600000',
            'ex_date': RECENT,
            'cash_ratio': 2.0,
            'desc': '10派2',
        }
    )
    assert records == []


def test_dividend_no_positions_yields_no_records(db):
    """查询成功但无持仓（含 0 份额）：不产生记录，也不算错误。"""
    job = _make_dividend_job(db)
    job.stats = {}
    assert job._position_rows('SH600000') == []
    records = job._events_to_records(
        {
            'symbol': 'SH600000',
            'ex_date': RECENT,
            'cash_ratio': 2.0,
            'desc': '10派2',
        }
    )
    assert records == []
    assert job.stats.get('errors', []) == []


# ── F 更新路径：ledger_id 变更同步 account_name 快照 ─────────────────────────


def test_patch_position_ledger_id_syncs_account_name(client, db, make_position):
    """PATCH 持仓换账户：account_name 快照必须同步为新账户名。

    不同步会留下「FK 是新账户、快照是旧名字」的漂移行；账户改名后
    sync_account_name_snapshots 还会把显示名刷回旧账户。
    """
    ledger_a = _make_ledger(db, '旧账户')
    ledger_b = _make_ledger(db, '新账户')
    pos = make_position(
        symbol='000701',
        name='迁移基金',
        account_name='旧账户',  # 夹具只回填 ledger_id，快照需显式给（存量数据同款形态）
        ledger_id=ledger_a,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    assert pos.account_name == '旧账户'
    db.commit()

    resp = client.patch(f'/api/positions/{pos.id}/', json={'ledger_id': ledger_b})
    assert resp.status_code == 200, resp.get_json()

    db.refresh(pos)
    assert pos.ledger_id == ledger_b
    assert pos.account_name == '新账户'


def test_patch_asset_ledger_id_syncs_account_name(client, db, make_asset):
    """PATCH 资产换账户：account_name 快照同步（与持仓同口径）。"""
    ledger_a = _make_ledger(db, '资产旧账户')
    ledger_b = _make_ledger(db, '资产新账户')
    asset = make_asset(major_category='cash', name='储蓄', amount=1000, account_name='资产旧账户', ledger_id=ledger_a)
    assert asset.account_name == '资产旧账户'
    db.commit()

    resp = client.patch(f'/api/assets/{asset.id}/', json={'ledger_id': ledger_b})
    assert resp.status_code == 200, resp.get_json()

    db.refresh(asset)
    assert asset.ledger_id == ledger_b
    assert asset.account_name == '资产新账户'


# ── G 持仓分组：键为 ledger_id 字符串，重名账户不成组 ────────────────────────


def test_positions_grouped_by_ledger_id_keys(client, db, make_position):
    """group_by=account 的键必须是 str(ledger_id)：重名账户各成一组。

    旧代码按 account_name 分组：两个『支付宝』并成一组，前端按名回查整组落空；
    账户改名后分组键随之漂移。未归档持仓归哨兵键 'unfiled'。
    """
    ledger_a = _make_ledger(db, '支付宝')
    ledger_b = _make_ledger(db, '支付宝')
    make_position(
        symbol='000801',
        name='基金A',
        account_name='支付宝',
        ledger_id=ledger_a,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    make_position(
        symbol='000801',
        name='基金B',
        account_name='支付宝',
        ledger_id=ledger_b,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    make_position(
        symbol='000802',
        name='未归档基金',
        ledger_id=None,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    db.commit()

    resp = client.get('/api/positions/', query_string={'group_by': 'account'})
    assert resp.status_code == 200
    groups = resp.get_json()['data']

    assert set(groups.keys()) == {str(ledger_a), str(ledger_b), 'unfiled'}
    # 重名账户的两个持仓分属不同组，没有并组
    a_rows = [r['symbol'] for r in groups[str(ledger_a)]]
    b_rows = [r['symbol'] for r in groups[str(ledger_b)]]
    assert a_rows == ['000801'] and b_rows == ['000801']
    # 行内仍带 account_name 快照供展示
    assert groups[str(ledger_a)][0]['account_name'] == '支付宝'
    assert groups['unfiled'][0]['symbol'] == '000802'


def test_positions_grouped_keys_stable_after_ledger_rename(client, db, make_position):
    """账户改名不改变分组键（快照可编辑，键不可编辑）。

    旧代码键=account_name：改名后分组键从『招商银行』变『招行』，前端缓存/回查
    全部落空。新代码键=ledger_id，改名只影响行内快照——且快照刷新归
    ``sync_account_name_snapshots`` 专职负责，读取路径不借机改库。
    """
    ledger_id = _make_ledger(db, '招商银行')
    make_position(
        symbol='000803',
        name='基金',
        account_name='招商银行',
        ledger_id=ledger_id,
        asset_type='fund',
        quantity=100,
        avg_price=1.0,
        current_price=1.0,
    )
    db.commit()

    # 改账户名（可编辑字段）
    ledger = db.get(Ledger, ledger_id)
    ledger.name = '招行'
    db.commit()

    resp = client.get('/api/positions/', query_string={'group_by': 'account'})
    groups = resp.get_json()['data']
    assert str(ledger_id) in groups  # 键稳定：改名不影响分组
    assert len(groups[str(ledger_id)]) == 1  # 持仓仍在原组，没有因改名掉出/掉组
