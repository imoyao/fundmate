# -*- coding: utf-8 -*-
"""收益日历物化快照：**等价性** + 三道失效（#1926）。

首要任务是钉住「物化读 ≡ 全量现算」。物化只该省时间，不该改口径——
一旦分叉就是 #1812 那种「静默错数字」的复刻，而且**更隐蔽**：
错的数字躺在缓存里，看上去完全合法，没人会怀疑它。

故所有断言都走 `json` 往返后比较，而不是直接比 dict：
`-0.0` 与 `0.0` 在 Python 里 `==` 成立，但序列化出来一个是 `-0.0` 一个是 `0.0`，
前端会分别显示成 `-0.00%` 和 `0.00%`。这种差异 dict 相等断言永远抓不到。
"""

import datetime as dt
import json

from app.core.money import Money
from app.domains.funds.models import DailyWorth
from app.domains.positions.models import Position
from app.domains.summary.models import PnlDailySnapshot
from app.domains.transactions.models import Transaction
from app.services import pnl_calendar, pnl_snapshot_store
from app.services.pnl_calendar import build_daily_pnl_series

START = dt.date(2026, 1, 5)
END = dt.date(2026, 1, 25)
# 中间故意空掉一天：制造真实的数据断档，让 `partial`（部分断档）也进物化序列。
# 只测连续数据等于只测 happy path，「缺数据不可画成 0」那条红线根本没被碰到。
#
# 日期**刻意选在部分重算的边界上**（前半段读到 01-12，缺口落在 01-13）：缓存
# 覆盖到 01-12、01-13 起现算，正好压中「前段物化 + 后段现算」的拼接点。
# 拼接错位的症状会在这里暴露为「拼接结果 ≠ 一次算到底」，是本文件最重要
# 的一条断言的承重墙。
GAP_DAY = dt.date(2026, 1, 12)
PARTIAL_END = dt.date(2026, 1, 12)
# 第二笔流水的原始生效日——编辑它来验证「按生效日精确失效」
TXN2_DAY = dt.date(2026, 1, 18)


def _add_nav(db, fund_code, date, unit_nav):
    db.add(DailyWorth(fund_code=fund_code, date=date, unit_nav=unit_nav))
    db.commit()


def _seed(db, make_position, make_transaction, start=START, end=END):
    """两只场内基金 + 逐日变动的净值 + 两笔流水（第二笔在 `TXN2_DAY`）。

    必须是**两只**，且**两只都得有流水**：断档判定要求 `day_present_count > 0`
    （有别的标的当天有真报价），而 `held` 看的是 `_as_of_shares` 算出来的份额——
    只有 `positions.quantity` 没有流水的持仓 `shares` 恒为 0，会被整个跳过，
    等于没种进去。单只（或第二只无流水）断档都会走「全体缺席 ⇒ 沿用前值 ⇒
    差分恰为 0」那条分支，`daily_pnl` 是 0 而不是 None——那是设计如此的诚实
    口径，但测不到「不可算」这条红线。

    两只分属不同账户：账户级序列必须是家庭级的真子集，同账户测不出作用域隔离。
    """
    pos = make_position(
        symbol='000001',
        name='测试基金A',
        quantity=1000,
        avg_price=1.0,
        asset_type='fund',
        account_name='甲账户',
    )
    pos_b = make_position(
        symbol='000002',
        name='测试基金B',
        quantity=1000,
        avg_price=1.0,
        asset_type='fund',
        account_name='乙账户',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=start,
        symbol='000001',
    )
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=500,
        price=1.0,
        confirm_date=TXN2_DAY,
        symbol='000001',
    )
    # B 的建仓流水：没有它 `shares=0`，B 在判定循环里被整个跳过（见 docstring）。
    make_transaction(
        position_id=pos_b.id,
        ledger_id=pos_b.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=2.0,
        confirm_date=start,
        symbol='000002',
    )
    day, i = start, 0
    while day <= end:
        # 让净值逐日变动：全 0 收益的序列测不出任何口径差异。
        # `000002` 连续、`000001` 在 GAP_DAY 缺一天 ⇒ 当天部分断档。
        if day != GAP_DAY:
            _add_nav(db, '000001', day, 1.0 + (i % 7) * 0.01)
        _add_nav(db, '000002', day, 2.0 + (i % 5) * 0.01)
        day += dt.timedelta(days=1)
        i += 1
    return pos


def _payload(result):
    """JSON 往返，把 `-0.0` 这类「数值相等但字面不同」的差异暴露出来。"""
    return json.loads(json.dumps(result, ensure_ascii=False))


def _full_recompute(db, start, end, family_id=1, ledger_id=None):
    """清空物化行后从头现算——这是「物化之前那份答案」的参照系。"""
    pnl_snapshot_store.purge_all(db)
    db.commit()
    return _payload(build_daily_pnl_series(db, family_id, start, end, ledger_id=ledger_id))


def _snapshot_count(db, **filters):
    q = db.query(PnlDailySnapshot)
    for k, v in filters.items():
        q = q.filter(getattr(PnlDailySnapshot, k) == v)
    return q.count()


# ────────────────────────────── 等价性 ──────────────────────────────


def test_全命中物化读与全量现算逐位相等(db, make_position, make_transaction):
    """缓存全命中时，输出必须与从头现算**完全一样**（含 -0.0 这种字面差异）。"""
    start, end = '2026-01-05', '2026-01-25'
    _seed(db, make_position, make_transaction)

    reference = _full_recompute(db, start, end)
    assert _snapshot_count(db) > 0, '参照组读完应当已物化，否则后面的「命中」是假的'

    materialized = _payload(build_daily_pnl_series(db, 1, start, end))
    assert materialized == reference


def test_部分重算拼接与全量现算逐位相等(db, make_position, make_transaction):
    """**最关键的一条**：前段用物化行、后段现算，拼起来必须等于一次算到底。

    这条同时压到三处窗口依赖——取价前扩、`no_price_ids` 固定窗口、
    基准日（`first_missing - 1`）的水平值与取数窗口无关。任何一处错位都会
    在这里露出来。

    前半段特意读到 `GAP_DAY`：缓存到 01-12 为止，于是 `first_missing = 01-13`、
    重算从 01-12 起步。基准日的份额/已实现必须与「从 01-04 一路算过来」逐笔
    一致（`_build_per_pos` 先注入 `scan_start` 之前的累计、循环再补
    `[scan_start, A]`，故 `Σ_{d≤A}` 与截断点无关），否则拼接后 01-13 起会拿到
    跨多天的差分当单日值，`merged != reference` 立刻成立。
    """
    _seed(db, make_position, make_transaction)

    # 先只读前半段（末日就是断档日）→ 只有前半段落库
    _full_recompute(db, START.isoformat(), PARTIAL_END.isoformat())
    assert _snapshot_count(db) > 0
    gap_row = db.query(PnlDailySnapshot).filter(PnlDailySnapshot.date == GAP_DAY).one()
    assert gap_row.date == GAP_DAY, '前置条件：断档日已物化，它就是重算的基准日'

    # 再读全段：前半段走缓存、后半段现算后拼接
    merged = _payload(build_daily_pnl_series(db, 1, START.isoformat(), END.isoformat()))

    # 参照：从头一次算到底
    reference = _full_recompute(db, START.isoformat(), END.isoformat())
    assert merged == reference


def test_数据断档日在物化后是部分可算而非零(db, make_position, make_transaction):
    """`GAP_DAY` 只缺 000001 的净值、000002 连续 ⇒ 部分断档。

    #1917 C 方案之后部分断档**照常出数**、`state='partial'` 标明不全——不是旧四态
    里的 `closed → None`。「全断档日必须是 None、绝不画成 0」那条红线由
    `test_净值停更时物化读仍为不可算而非零` 钉住，这里钉的是物化不改这个口径。
    """
    _seed(db, make_position, make_transaction)

    result = _payload(build_daily_pnl_series(db, 1, '2026-01-05', '2026-01-25'))
    gap = next(d for d in result['days'] if d['date'] == GAP_DAY.isoformat())
    assert gap['daily_pnl'] == 10.0, f'部分断档日照常出真值（10.0），绝非 0 / None，实得 {gap["daily_pnl"]}'
    assert gap['state'] == 'partial', f'状态应为 partial，实得 {gap["state"]}'

    # 物化再读一遍，结论不得因缓存而改变
    again = _payload(build_daily_pnl_series(db, 1, '2026-01-05', '2026-01-25'))
    assert next(d for d in again['days'] if d['date'] == GAP_DAY.isoformat()) == gap


def test_家庭级与账户级都物化且互不串味(db, make_position, make_transaction):
    """两个作用域各有自己的行（`ledger_id` NULL / 非 NULL 是不同的唯一键），
    且**各自的物化读都等于各自的全量现算**——账户级最容易漏。"""
    start, end = START.isoformat(), END.isoformat()
    pos = _seed(db, make_position, make_transaction)
    assert pos.ledger_id is not None, '前置条件：两只基金分属两个账户'

    fam = _payload(build_daily_pnl_series(db, 1, start, end))
    led = _payload(build_daily_pnl_series(db, 1, start, end, ledger_id=pos.ledger_id))

    assert led['scope'] == 'ledger' and led['ledger_id'] == pos.ledger_id
    assert _snapshot_count(db, ledger_id=None) > 0
    assert _snapshot_count(db, ledger_id=pos.ledger_id) > 0
    # 甲账户只有 000001，家庭级是 000001+000002 ⇒ 两条序列必然不同。
    # 若完全相同，说明作用域没被算进去（`ledger_id` 被忽略），隔离失效。
    assert led['days'] != fam['days'], '账户级与家庭级序列不该相同'

    # 各自的物化读 == 各自的全量现算（`_full_recompute` 会清表，故先比完再清）
    assert led == _full_recompute(db, start, end, ledger_id=pos.ledger_id)
    assert fam == _full_recompute(db, start, end)


# ────────────────────────────── 失效①口径版本 ──────────────────────────────


def test_口径版本不符时整表作废并回填(db, make_position, make_transaction):
    """`caliber_version` 不符 ⇒ 整表清一次（自愈），随后按新口径回填。"""
    start, end = '2026-01-05', '2026-01-25'
    _seed(db, make_position, make_transaction)
    _full_recompute(db, start, end)
    before = _snapshot_count(db)
    assert before > 0

    db.query(PnlDailySnapshot).update(
        {PnlDailySnapshot.caliber_version: 999},
        synchronize_session=False,
    )
    db.commit()

    result = _payload(build_daily_pnl_series(db, 1, start, end))
    assert _snapshot_count(db, caliber_version=999) == 0, '旧版本行必须被清掉'
    assert _snapshot_count(db) == before, '新口径应把行回填回来'
    # 清完重算的答案必须与清之前的完全一致——口径版本只是作废信号，不该改口径
    assert result == _full_recompute(db, start, end)


# ────────────────────────────── 失效②用户编辑 ──────────────────────────────


def test_编辑流水按生效日精确失效(db, make_position, make_transaction):
    """把 01-18 的流水改到 01-21 ⇒ 只作废 `min(新,旧)=01-18` 起的行，前面的留着。"""
    _seed(db, make_position, make_transaction)
    _full_recompute(db, '2026-01-05', '2026-01-25')
    assert _snapshot_count(db) > 0

    txn = db.query(Transaction).filter(Transaction.confirm_date == TXN2_DAY).one()
    txn.confirm_date = dt.date(2026, 1, 21)
    db.commit()

    remaining = {r.date for r in db.query(PnlDailySnapshot).all()}
    assert remaining, '改的是后段，前段应当完好'
    assert max(remaining) < TXN2_DAY, f'{TXN2_DAY} 起的行必须被作废，实剩最晚 {max(remaining)}'
    # 物化窗口比区间多带一天 `start-1`（range_rate 的分母基准行，见 build docstring）
    assert min(remaining) == START - dt.timedelta(days=1), '基准行仍在，证明不是整族失效'


def test_新增流水自其生效日起失效(db, make_position, make_transaction):
    """新流水只影响生效日之后，之前的日子不该被牵连重算。"""
    _seed(db, make_position, make_transaction)
    _full_recompute(db, '2026-01-05', '2026-01-25')

    # 明确取 A 的建仓流水——`.first()` 会因插入顺序变化而漂到 B 身上
    pos = db.query(Transaction).filter(Transaction.symbol == '000001').order_by(Transaction.id).first()
    make_transaction(
        position_id=pos.position_id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=100,
        price=1.0,
        confirm_date=dt.date(2026, 1, 20),
        symbol='000001',
    )

    remaining = {r.date for r in db.query(PnlDailySnapshot).all()}
    assert max(remaining) < dt.date(2026, 1, 20), f'01-20 起的行应被作废，实剩 {max(remaining)}'
    # 基准行（start-1）早于生效日，不受新流水牵连
    assert min(remaining) == START - dt.timedelta(days=1)


def test_持仓结构变更整族失效(db, make_position, make_transaction):
    """改 `avg_price` ⇒ 家庭级与账户级快照**全部**作废（#1916 决策集全局性）。"""
    _seed(db, make_position, make_transaction)
    _full_recompute(db, '2026-01-05', '2026-01-25')
    assert _snapshot_count(db) > 0

    pos = db.query(Transaction).first()
    p = db.query(Position).filter(Position.id == pos.position_id).one()
    p.avg_price = Money.yuan_to_price_units(2.0)
    db.commit()

    assert _snapshot_count(db) == 0, '持仓结构变化必须让整族失效'


def test_现价回写不触发失效(db, make_position, make_transaction):
    """`position_price` 每天回写 `current_price`，**不是**日历的事实源，不得作废。

    若这条被误判成失效，物化等于每天清空一次，优化就白做了。
    """
    _seed(db, make_position, make_transaction)
    _full_recompute(db, '2026-01-05', '2026-01-25')
    before = _snapshot_count(db)
    assert before > 0

    p = db.query(Position).first()
    p.current_price = Money.yuan_to_price_units(9.99)
    db.commit()

    assert _snapshot_count(db) == before, '现价回写不得作废物化快照'


def test_删除持仓整族失效(db, make_position, make_transaction):
    """删除走 ORM `db.delete()`，`before_flush` 应当抓到。"""
    _seed(db, make_position, make_transaction)
    _full_recompute(db, '2026-01-05', '2026-01-25')
    assert _snapshot_count(db) > 0

    p = db.query(Position).first()
    db.delete(p)
    db.commit()

    assert _snapshot_count(db) == 0, '删持仓必须让整族失效'


# ──────────────────────────── 失效③批量写盲区 ────────────────────────────


def test_孤儿归入与清理的bulk写后显式作废(db, make_position):
    """`Query.update()` / `Query.delete()` 是 **bulk 语句，不进 session 状态**。

    `before_flush` 在它们面前是瞎的（`positions/models.py` 讲同一盲区）。两处漏掉
    显式补钩的症状完全一样：账户归属变了，日历却继续按**旧的**持仓集算，而且
    **不报错**——只会在下一次因别的原因失效时才暴露，事后极难归因到这一步。
    """
    from app.domains.ledgers.models import Ledger
    from app.services import ledger_migration_service as svc

    def _snapshot():
        db.add(
            PnlDailySnapshot(family_id=1, ledger_id=None, date=dt.date(2026, 1, 5), net_worth_cents=100, state='zero')
        )
        db.commit()

    # ① 归入：bulk `Query.update()` 改 `Position.ledger_id`。
    #    顺序是关键——先建孤儿持仓（那笔 flush 自己会作废一次），**再**种快照，
    #    否则断言的是「建仓时的作废」，与本条要守的东西无关。
    target = Ledger(name='目标账户', ledger_type='fund', family_id=1)
    db.add(target)
    db.commit()
    make_position(symbol='510300', name='孤儿ETF', quantity=100, avg_price=1.0, current_price=1.0, asset_type='fund')
    _snapshot()
    assert _snapshot_count(db) > 0, '前置条件：快照已落库'

    svc.migrate_orphan_data(db, target, 1)
    assert _snapshot_count(db) == 0, '归入走 bulk update，事件抓不到，必须显式作废'

    # ② 清理：bulk `Query.delete()` 删 Position/Transaction
    make_position(symbol='510301', name='孤儿ETF2', quantity=100, avg_price=1.0, current_price=1.0, asset_type='fund')
    _snapshot()
    assert _snapshot_count(db) > 0, '前置条件：快照已落库'

    svc.delete_orphan_data(db, 1)
    assert _snapshot_count(db) == 0, '清理走 bulk delete，事件抓不到，必须显式作废'


# ────────────────────────────── 失效④价格数据 ──────────────────────────────


def test_新鲜窗内日期永不物化(db, make_position, make_transaction):
    """`>= 今天 - PRICE_FRESH_DAYS` 的行不落库——日常价格同步因此无需钩子。"""
    from app.core.time_utils import now_shanghai

    today = now_shanghai().date()
    start = today - dt.timedelta(days=20)
    _seed(db, make_position, make_transaction, start=start, end=today)

    build_daily_pnl_series(db, 1, start.isoformat(), today.isoformat())

    cutoff = today - dt.timedelta(days=pnl_calendar.PRICE_FRESH_DAYS)
    fresh = db.query(PnlDailySnapshot).filter(PnlDailySnapshot.date >= cutoff).count()
    persisted = db.query(PnlDailySnapshot).filter(PnlDailySnapshot.date < cutoff).count()
    assert fresh == 0, f'新鲜窗内不该有任何行（cutoff={cutoff}）'
    assert persisted > 0, '窗口外的日期应当正常物化，否则等于没物化'


def test_净值停更后沿用到期_之后正确判为no_price(db, make_position, make_transaction):
    """净值停在窗口**开始之前** 3 天 ⇒ 前 5 天沿用（`zero`），第 6 天起 `no_price`。

    这一个用例同时钉住两处窗口依赖（回退探针实测都能拦下）：

    1. **取价窗口必须前扩 `_STALE_CARRY_DAYS`**。不前扩则 `scan_start` 那天取不到
       价 ⇒ `prev_net_worth` 是 0 ⇒ 首日 `rate` 变 None、`state` 从 `zero` 掉成
       `no_price`。同一笔持仓往前多查几天就能算出来——那正是 #1917 那类
       「结果取决于查询区间」的病根。
    2. **`day_unpriced_count` 必须看 `no_price_ids` 而非 `not series`**。该持仓在
       `[start-1, end]` 里没有任何行（⇒ 在 `no_price_ids` 内），但**前扩窗口**里
       有行（⇒ `series` 非空）。用 `not series` 判会漏掉它，`state` 就从
       `no_price` 退化成 `closed`——两者都表示不可算，但对用户是两种处置。
    """
    buy_day = dt.date(2026, 2, 25)
    nav_day = dt.date(2026, 2, 27)  # 窗口开始前 3 天，停更
    start, end = dt.date(2026, 3, 2), dt.date(2026, 3, 14)

    pos = make_position(symbol='000001', name='停更基金', quantity=1000, avg_price=1.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=1000,
        price=1.0,
        confirm_date=buy_day,
        symbol='000001',
    )
    _add_nav(db, '000001', nav_day, 1.0)

    result = _payload(build_daily_pnl_series(db, 1, start.isoformat(), end.isoformat()))
    state_of = lambda d: next(x['state'] for x in result['days'] if x['date'] == d.isoformat())  # noqa: E731
    pnl_of = lambda d: next(x['daily_pnl'] for x in result['days'] if x['date'] == d.isoformat())  # noqa: E731

    # 沿用窗口：`nav_day` 起 7 天内（2026-02-27 + 7 = 03-06）都取得到价
    assert state_of(dt.date(2026, 3, 2)) == 'zero', '窗口首日应沿用停更前的净值'
    assert pnl_of(dt.date(2026, 3, 2)) == 0.0, '沿用期间价格未变 ⇒ 日盈亏 0（是诚实的 0，不是缺数据）'
    assert state_of(dt.date(2026, 3, 6)) == 'zero', '沿用窗口最后一天仍应出数'
    # 第 8 天起前值已超出 `_STALE_CARRY_DAYS` ⇒ 必须是 no_price，不是 closed、更不是 0
    assert state_of(dt.date(2026, 3, 7)) == 'no_price', '沿用到期后应判 no_price'
    assert pnl_of(dt.date(2026, 3, 7)) is None, '缺数据绝不可画成 0'

    # 物化读与全量现算一致
    assert result == _full_recompute(db, start.isoformat(), end.isoformat())


def test_负收益率在物化读里仍是负零(db, make_position, make_transaction):
    """大额组合的 10 元日亏损 ⇒ `rate` 序列化成 `-0.0`，**不是** `0.0`。

    为什么必须比 JSON 字符串：`-0.0 == 0.0` 在 Python 里为 True，任何 dict 相等
    断言都拦不住；但前端 `toFixed(2)` 会分别显示 `-0.00%` 和 `0.00%`——一个说「跌了
    一点」，一个说「没动」。物化读与现算读在这种天就**不再逐位相等**了。

    数据规模是照着两个触发条件凑的，都卡在**整数精度**上：

    - 收益率的取价精度是 0.0001 元（`_collect_fund_nav` 返回「万分之一元」整数），
      净值 1 元时降一个最小刻度就是 0.01%，`round` 后必是 `-0.01` 而非 `-0.00`——
      所以净值取 3 元，同样一个最小刻度只有 `0.0001/3 ≈ 0.0033%`，才落进
      「四舍五入到 2 位后归零」的窄缝里；
    - 盈亏方向必须为负，否则 `rate_bp == 0` 天然就对应 `0.0`，补不补 `-0.0` 都一样。

    于是 `rate_pct = -10 / 300000 × 100 = -0.0033…`，`round(-0.0033, 2)` 得 `-0.0`，
    取整基点后是 0（符号被吃掉），读回时靠「基点为 0 且当日盈亏为负」补回 `-0.0`。
    """
    navs = [
        (dt.date(2026, 1, 3), '3.000000'),  # 恰好是 scan_start，用来定住首日基准
        (dt.date(2026, 1, 4), '3.000000'),
        (dt.date(2026, 1, 5), '3.000000'),
        (dt.date(2026, 1, 6), '2.999900'),  # 10 万份 × 0.0001 = 10 元日亏损
    ]
    pos = make_position(symbol='000001', name='大额基金', quantity=100000, avg_price=3.0, asset_type='fund')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        txn_type='buy',
        quantity=100000,
        price=3.0,
        confirm_date=dt.date(2026, 1, 2),
        symbol='000001',
    )
    for d, v in navs:
        _add_nav(db, '000001', d, v)

    start, end = '2026-01-04', '2026-01-10'
    reference = _full_recompute(db, start, end)  # 清表 + 现算 + 落库
    materialized = _payload(build_daily_pnl_series(db, 1, start, end))  # 全命中

    day6 = next(x for x in materialized['days'] if x['date'] == '2026-01-06')
    assert day6['daily_pnl'] < 0, '前置条件：这天确实亏了'
    assert day6['daily_pnl'] == -10.0, f'前置条件：10 万份跌 0.0001 元 = 10 元，实得 {day6["daily_pnl"]}'
    assert '"rate": -0.0' in json.dumps(day6), f'应为 -0.0，实得 {day6["rate"]!r}'

    # 逐字面比较——`-0.0` 与 `0.0` 只有在 JSON 里才分得开
    assert json.dumps(materialized, sort_keys=True) == json.dumps(reference, sort_keys=True)


def test_purge_all作废全表(db, make_position, make_transaction):
    """`full_sync` 回填走这条——价格数据不属于任何家庭，最精确的单位就是全表。"""
    _seed(db, make_position, make_transaction)
    _full_recompute(db, '2026-01-05', '2026-01-25')
    assert _snapshot_count(db) > 0

    assert pnl_snapshot_store.purge_all(db) > 0
    db.commit()
    assert _snapshot_count(db) == 0


def test_价格回填白名单只含真正写价格表的job(db):
    """白名单口径：日历只读 `DailyWorth`/`PriceHistory`，写它们的只有这两个 job。

    放进列表型 job 会让每次全市场刷新都白清一遍缓存；漏掉一个则会
    **静默读到回填前的旧值**——后者更危险，故用断言钉死。
    """
    from app.services.sync.orchestrator import PRICE_BACKFILL_JOBS

    assert PRICE_BACKFILL_JOBS == frozenset({'fund_nav', 'price_history'})
    # 列表型 / 资料型 job 不写价格表，不该触发作废
    for job in ('fund_list', 'stock_list', 'fund_manager', 'fund_type', 'temperature'):
        assert job not in PRICE_BACKFILL_JOBS


def test_full_sync回填后整表作废(db):
    """`run_job(full_sync=True)` 命中白名单 ⇒ 必须清表（用桩 job 避开重型注册）。"""
    from app.services.sync.orchestrator import DataSyncOrchestrator

    class _StubJob:
        snapshot_time = None

        def run(self, full_sync, targets=None):
            return {'status': 'success'}

    # 绕过 `__init__`（它会构造 akshare 适配器，与本条无关），只装要用的三个属性
    orch = DataSyncOrchestrator.__new__(DataSyncOrchestrator)
    orch.db = db
    orch.jobs = {'fund_nav': _StubJob(), 'temperature': _StubJob()}
    orch._save_sync_log_with_fallback = lambda *a, **k: None

    db.add(PnlDailySnapshot(family_id=1, ledger_id=None, date=dt.date(2026, 1, 5), net_worth_cents=100, state='zero'))
    db.commit()
    assert _snapshot_count(db) > 0

    orch.run_job('fund_nav', full_sync=True)
    assert _snapshot_count(db) == 0, '价格回填 full_sync 必须整表作废'

    # 非价格 job 的 full_sync 不该动它
    db.add(PnlDailySnapshot(family_id=1, ledger_id=None, date=dt.date(2026, 1, 5), net_worth_cents=100, state='zero'))
    db.commit()
    orch.run_job('temperature', full_sync=True)
    assert _snapshot_count(db) == 1, '非价格 job 不得清表'
