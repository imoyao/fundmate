# backend/tests/services/sync/test_dividend_split_job.py
"""#1179 / #541 回归：分红、送转、配股抓取 Job 的转换、幂等与降级。

#541 修的是「链路在跑、数据静默丢」的三段，因此用例的重点不在「跑通」，而在
**每段丢失路径都有一条红灯用例**：
- 基金分红必须带每份金额（否则整批被导入校验剔除）；
- 股票混合方案必须拆成现金 + 送转两条；
- 配股必须能按比例 + 配股价算出缴款与份额；
- 幂等键不得随持有份额漂移。
"""

from datetime import date, timedelta
from decimal import Decimal

from app.services.sync.jobs.dividend_split_job import DividendSplitSyncJob

TODAY = date.today()
RECENT = TODAY - timedelta(days=30)


class _FakeAdapter:
    def fetch_stock_dividend(self, symbol):
        return [
            {
                'symbol': symbol,
                'ex_date': RECENT,
                'bonus_ratio': 0.0,
                'transfer_ratio': 0.0,
                'cash_ratio': 2.0,
                'desc': '10派2元',
            }
        ]

    def fetch_fund_dividend(self, symbol):
        return [{'symbol': symbol, 'ex_date': RECENT, 'per_share': 0.01, 'desc': '每10份派现金0.1元'}]

    def fetch_fund_split(self, symbol):
        return []

    def fetch_stock_rights_issue(self, symbols):
        return []


def _make_job(db, held='1000', reinvest=False):
    job = DividendSplitSyncJob(_FakeAdapter(), db)
    job.stats = {'total': 0, 'success': 0, 'skipped': 0, 'failed': 0, 'errors': []}
    # 桩打在 _position_context 上（生产代码取份额/账户的唯一入口），
    # 桩在 _holding_shares 上会绕不过去——那正是本文件第一次跑红的原因。
    job._position_context = lambda s: {
        'shares': Decimal(held),
        'ledger_id': 1,
    }
    job._is_reinvest = lambda s: reinvest
    return job


# ── ① 股票混合方案必须拆两条（#541 第 2 段） ─────────────────────────────


def test_mixed_stock_plan_yields_cash_and_split(db):
    """「10送3股派0.6元」→ 现金分红 + 送转股票 两条。

    修复前 `business_type = 'split' if is_split else 'dividend'` 只留送股，
    那 0.6 元派息被整笔吞掉——「股票分红记不全」的根因。
    """
    job = _make_job(db)
    recs = job._events_to_records(
        {
            'symbol': 'SH600000',
            'ex_date': RECENT,
            'bonus_ratio': 3.0,
            'transfer_ratio': 0.0,
            'cash_ratio': 0.6,
            'desc': '10送3股派0.6元',
        }
    )
    kinds = sorted(r.business_type for r in recs)
    assert kinds == ['dividend_cash', 'split'], f'混合方案必须拆两条，实际 {kinds}'

    cash = next(r for r in recs if r.business_type == 'dividend_cash')
    split = next(r for r in recs if r.business_type == 'split')
    assert cash.amount == Decimal('60.00')  # 1000 / 10 × 0.6
    assert cash.shares == Decimal('0')
    assert split.shares == Decimal('300')  # 1000 / 10 × 3
    assert split.amount == Decimal('0')


def test_pure_cash_plan_yields_single_dividend(db):
    job = _make_job(db)
    recs = job._events_to_records({'symbol': 'SH600000', 'ex_date': RECENT, 'cash_ratio': 2.0, 'desc': '10派2元'})
    assert [r.business_type for r in recs] == ['dividend_cash']
    assert recs[0].amount == Decimal('200')


def test_pure_split_plan_yields_single_split(db):
    job = _make_job(db)
    recs = job._events_to_records(
        {'symbol': 'SH600000', 'ex_date': RECENT, 'transfer_ratio': 10.0, 'desc': '10转增10股'}
    )
    assert [r.business_type for r in recs] == ['split']
    assert recs[0].shares == Decimal('1000')


# ── ② 基金分红必须带每份金额（#541 第 1 段） ─────────────────────────────


def test_fund_dividend_amount_is_computed_from_per_share(db):
    """基金分红要算出真实金额；修复前只拿到公告日 → amount=0 → 被导入校验整批剔除。"""
    job = _make_job(db)
    recs = job._events_to_records({'symbol': '000001', 'ex_date': RECENT, 'per_share': 0.01})
    assert len(recs) == 1
    rec = recs[0]
    assert rec.business_type == 'dividend_cash'
    assert rec.amount == Decimal('10.00')  # 1000 份 × 0.01
    assert job._validate_data([{'symbol': '000001', 'ex_date': RECENT, 'per_share': 0.01}]), '不得被校验剔除'


def test_fund_dividend_follows_position_preference(db):
    """分红方式取持仓的 dividend_preference，命中则落 dividend_reinvest。"""
    job = _make_job(db, reinvest=True)
    recs = job._events_to_records({'symbol': '000001', 'ex_date': RECENT, 'per_share': 0.01})
    assert recs[0].business_type == 'dividend_reinvest'


def test_fund_dividend_without_per_share_is_bad_event_not_zero(db):
    """拿不到每份分红时**跳过**，绝不落 0 金额流水（0 会被当成「不分红」静默吞掉）。"""
    job = _make_job(db)
    assert job._events_to_records({'symbol': '000001', 'ex_date': RECENT}) == []
    assert job._validate_data([{'symbol': '000001', 'ex_date': RECENT}]) == []


def test_fund_split_adds_shares_without_cost(db):
    job = _make_job(db, held='1000')
    recs = job._events_to_records({'symbol': '000001', 'ex_date': RECENT, 'split_ratio': 2.0})
    assert len(recs) == 1
    assert recs[0].business_type == 'split'
    assert recs[0].shares == Decimal('1000.0000')  # 1:2 → 多出一倍份额
    assert recs[0].amount == Decimal('0')


# ── ③ 配股（#541 第 3 段，用户拍板「能自动抓就直接抓」） ────────────────


def test_rights_issue_creates_payment_with_shares_and_cost(db):
    """配股 → 一条「缴款买入」：份额按比例增加、金额按配股价算出。"""
    job = _make_job(db, held='1000')
    recs = job._events_to_records(
        {
            'symbol': 'SH600000',
            'ex_date': RECENT - timedelta(days=5),
            'rights_ratio': 3.0,
            'rights_price': 5.0,
            'pay_start': RECENT - timedelta(days=4),
            'pay_end': RECENT - timedelta(days=2),
            'desc': '10配3，配股价5元',
        }
    )
    assert len(recs) == 1
    rec = recs[0]
    assert rec.business_type == 'buy'
    assert rec.shares == Decimal('300.0000')  # 1000 / 10 × 3
    assert rec.amount == Decimal('1500.00')  # 300 × 5
    assert rec.nav == Decimal('5')
    # 缴款日优先取缴款截止日：钱是那天划走的
    assert rec.confirm_date == RECENT - timedelta(days=2)
    assert rec.raw_op_type == '配股缴款'


def test_rights_issue_without_price_is_skipped_not_guessed(db):
    """缺配股价 → 不记（宁可漏记，也不写猜出来的金额）。"""
    job = _make_job(db)
    assert (
        job._events_to_records({'symbol': 'SH600000', 'ex_date': RECENT, 'rights_ratio': 3.0, 'rights_price': 0}) == []
    )


# ── ④ 幂等键不得随持有份额漂移（#541 的关键设计） ────────────────────────


def test_import_hash_stable_across_position_changes(db):
    """同一事件在「加仓前后」必须算出同一个 import_hash。

    `compute_record_hash` 默认把 shares/nav 算进 key；分红金额恰恰由持有份额决定，
    用户加仓就会算出新 hash → **同一笔分红被记第二遍**。故本 job 把幂等键钉在事件上。

    ⚠️ 单看这一条**测不出关键点**：现金分红事件的 shares/nav 本就是 0，
    默认哈希恰好不含份额。真正咬住幂等键的是下方送转/配股两条用例。
    """
    event = {'symbol': 'SH600000', 'ex_date': RECENT, 'cash_ratio': 2.0, 'desc': '10派2元'}
    before = _make_job(db, held='1000')._events_to_records(event)[0]
    after = _make_job(db, held='9000')._events_to_records(event)[0]
    assert before.amount != after.amount  # 金额确实随份额变
    assert before.import_hash == after.import_hash, '幂等键不得随持有份额漂移'

    other_day = dict(event, ex_date=RECENT - timedelta(days=1))
    assert _make_job(db)._events_to_records(other_day)[0].import_hash != before.import_hash, '不同事件必须不同键'


def test_deduplicate_within_batch(db):
    job = _make_job(db)
    recs = job._events_to_records({'symbol': 'SH600000', 'ex_date': RECENT, 'cash_ratio': 2.0})
    assert len(job._deduplicate(recs * 2)) == 1


# ── ⑤ 持仓查询失败不得写成 0 金额流水（#1833 既有约束） ──────────────────


def test_holding_query_failure_skips_event_instead_of_zero_amount(db):
    """持仓查询失败 → 跳过该事件，**不落库**。

    早先实现是 `except: return Decimal('0')`，于是持仓一查不到就写出 amount=0 的
    分红流水；而幂等去重之后会把这条脏记录当重复跳过 —— **永久不可自愈**。
    """

    class _Boom:
        def query(self, *_a, **_k):
            raise RuntimeError('db down')

        def add(self, *_a, **_k):
            pass

    job = DividendSplitSyncJob(_FakeAdapter(), db)
    job.db = _Boom()
    job.stats = {'errors': []}
    assert job._holding_shares('SH600000') is None
    assert any(e.get('stage') == 'holding_query' for e in job.stats['errors'])
    assert job._events_to_records({'symbol': 'SH600000', 'ex_date': RECENT, 'cash_ratio': 2.0}) == []


def test_future_and_stale_events_are_ignored(db):
    job = _make_job(db)
    future = {'symbol': 'SH600000', 'ex_date': TODAY + timedelta(days=30), 'cash_ratio': 2.0}
    stale = {'symbol': 'SH600000', 'ex_date': TODAY - timedelta(days=800), 'cash_ratio': 2.0}
    assert job._events_to_records(future) == []
    assert job._events_to_records(stale) == []


# ── ⑥ 上游 NaN 不得让事件静默消失（#541 实测踩坑） ──────────────────────


def test_nan_ratio_does_not_swallow_event(db):
    """上游缺失值是 NaN（pandas 常态：送股比例为空）。

    `float('nan')` 是真值，`str(nan)` → 'nan'，`Decimal('nan')` 参与比较**不抛错也不为真**
    （NaN 的一切比较都是 False）——于是整条事件被静默跳过，「有分红但一条没记」。
    """
    job = _make_job(db)
    recs = job._events_to_records(
        {
            'symbol': 'SH600000',
            'ex_date': RECENT,
            'bonus_ratio': float('nan'),
            'transfer_ratio': float('nan'),
            'cash_ratio': 2.0,
            'desc': '10派2元',
        }
    )
    assert len(recs) == 1, 'NaN 送股比例不得把现金分红一起吞掉'
    assert recs[0].business_type == 'dividend_cash'
    assert recs[0].amount == Decimal('200')


def test_num_helper_treats_nan_and_garbage_as_zero(db):
    job = _make_job(db)
    assert job._num(float('nan')) == Decimal('0')
    assert job._num(None) == Decimal('0')
    assert job._num('--') == Decimal('0')
    assert job._num('2.5') == Decimal('2.5')


# ── ⑦ 抓取分流按持仓类型，不按代码段（#541 实测撞上） ─────────────────────


class _AssetType:
    def __init__(self, asset_type):
        self.asset_type = asset_type


def test_fetch_branch_follows_position_asset_type_not_code(db):
    """`000001` 既是平安银行也是华夏成长混合——分流必须听持仓的，不能听代码段。

    修复前按代码段推断，手里是华夏成长却去抓了平安银行的历年股票分红，
    抓到的事件全部因「每 10 股」口径算成 0 元被剔除：一条不落库，也没有任何报错。
    """
    assert DividendSplitSyncJob._fetch_as_stock('000001', [_AssetType('fund')]) is False
    assert DividendSplitSyncJob._fetch_as_stock('000001', [_AssetType('stock')]) is True
    assert DividendSplitSyncJob._fetch_as_stock('SZ000001', [_AssetType('fund')]) is False
    # 无持仓 → 退回代码段推断（000001 在 A 股代码空间里是深市主板股票）
    assert DividendSplitSyncJob._fetch_as_stock('SZ000001', []) is True


def test_fetch_branch_refuses_to_guess_on_conflicting_asset_types(db):
    """同一代码在库内有多种 asset_type（脏数据）→ 不抓，别猜。"""
    assert DividendSplitSyncJob._fetch_as_stock('000001', [_AssetType('fund'), _AssetType('stock')]) is False


def test_split_import_hash_stable_across_position_changes(db):
    """送转的幂等键同样不得随份额漂移。

    **这条是上一版用例的补丁**：现金分红事件的 shares/nav 本来就是 0，默认哈希
    `source|日期|代码|类型|shares|nav` 恰好不含份额，于是一条「现金分红幂等键稳定」
    的用例在删掉 transaction_id 之后**仍然全绿**（探针 MISSED，测了个寂寞）。
    真正会漂移的是带份额的事件：送转、配股。
    """
    event = {'symbol': 'SH600000', 'ex_date': RECENT, 'bonus_ratio': 3.0, 'desc': '10送3股'}
    before = _make_job(db, held='1000')._events_to_records(event)[0]
    after = _make_job(db, held='2000')._events_to_records(event)[0]
    assert before.shares != after.shares  # 份额确实随持有量变
    assert before.import_hash == after.import_hash, '送转的幂等键不得随持有份额漂移'


def test_rights_import_hash_stable_across_position_changes(db):
    event = {
        'symbol': 'SH600000',
        'ex_date': RECENT,
        'rights_ratio': 3.0,
        'rights_price': 5.0,
        'desc': '10配3',
    }
    before = _make_job(db, held='1000')._events_to_records(event)[0]
    after = _make_job(db, held='2000')._events_to_records(event)[0]
    assert before.shares != after.shares
    assert before.import_hash == after.import_hash, '配股的幂等键不得随持有份额漂移'
