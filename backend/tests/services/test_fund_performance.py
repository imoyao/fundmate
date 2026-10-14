# -*- coding: utf-8 -*-
"""测试基金业绩与风险（#2029 卡 B · 详情页业绩与风险卡）。

纯函数（区间收益 / 年化波动率）用合成序列做精确断言；`build_fund_performance`
用 mock 的 db Session 验证分支（货基 / 场外 / 不存在），不依赖真实库。
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

from app.services.fund_performance import (
    _annualized_volatility,
    _interval_return,
    build_fund_performance,
)

D0 = date(2025, 1, 1)


def _series(values):
    return [(D0 + timedelta(days=i), v) for i, v in enumerate(values)]


def test_interval_return_basic():
    # 起点=首点，终点=末点 → (1.2/1.0 - 1)*100 = 20.0
    assert _interval_return(_series([1.0, 1.1, 1.2]), D0) == 20.0


def test_interval_return_window_clamps_to_first_ge_start():
    pts = _series([1.0, 1.1, 1.2, 1.5])
    # 起点 = D0+2（≥ 该日首点）→ nav_start=1.2，终点=1.5 → 25.0
    assert _interval_return(pts, D0 + timedelta(days=2)) == 25.0


def test_interval_return_too_few():
    assert _interval_return([(D0, 1.0)], D0) is None


def test_annualized_volatility_known():
    # 100 → 110 → 120：日收益 10% / 9.09%，年化 ≈ 10.20%
    pts = [(D0 + timedelta(days=i), v) for i, v in enumerate([100.0, 110.0, 120.0])]
    vol = _annualized_volatility(pts, date(2000, 1, 1))
    assert vol is not None
    assert round(vol, 2) == 10.20


def test_annualized_volatility_insufficient():
    pts = [(D0, 100.0), (D0 + timedelta(days=1), 101.0)]
    assert _annualized_volatility(pts, D0) is None


class _FundType:
    def __init__(self, name):
        self.name = name


class _Fund:
    def __init__(self, name):
        self.fund_type = _FundType(name)


class _DailyWorth:
    def __init__(self, d, acc_nav):
        self.date = d
        self.acc_nav = acc_nav
        self.unit_nav = None


class _MoneyRow:
    def __init__(self):
        self.annual_return_7d = 1.5
        self.nav_per_10k = 0.5
        self.date = date(2026, 10, 9)


def _model_name(expr):
    """取 `db.query(...)` 首个参数的模型名。

    **类与列两种形态都要认**：`db.query(Fund)` 传类；`db.query(IndexDaily.close)` /
    `db.query(FundRiskMetrics.fund_code, ...)` 传的是 Column，它的 `__name__` 是列名
    而不是模型名。只认类会让多列查询静默落到兜底分支，取数返回空 ⇒ 测试跑绿但
    什么也没验（「基准不可用」与「基准取不到」同形）。
    """
    name = getattr(expr, '__name__', '')
    if name:
        return name
    # Column 形态：从 `expr.class_` / `expr.table.name` 反查所属模型
    for attr in ('class_',):
        cls = getattr(expr, attr, None)
        if cls is not None:
            return getattr(cls, '__name__', '')
    table = getattr(expr, 'table', None)
    return getattr(table, 'name', '') if table is not None else ''


def _fake_db(fund, money_row=None, daily_rows=None):
    db = MagicMock()
    fund_q = MagicMock()
    fund_q.filter.return_value.first.return_value = fund
    money_q = MagicMock()
    money_q.filter.return_value.order_by.return_value.first.return_value = money_row
    dw_q = MagicMock()
    dw_q.filter.return_value.order_by.return_value.all.return_value = daily_rows or []

    def _query(model, *rest):
        # `*rest`：多列查询形态（`db.query(Model.a, Model.b)`）的占位。
        # `index_daily` / `fund_risk_metrics` 的取数就是多列形态，只接一个参数会
        # 在测试替身上抛 TypeError —— 那报错指向替身而非被测代码，很费时间。
        name = _model_name(model)
        if name == 'Fund':
            return fund_q
        if name == 'MoneyFundDailyWorth':
            return money_q
        if name == 'DailyWorth':
            return dw_q
        return MagicMock()

    db.query.side_effect = _query
    return db


def test_build_not_found():
    assert build_fund_performance(_fake_db(None), '999999') is None


def test_build_money_fund():
    # 货基：返回万份收益 + 七日年化，不进净值算法（无回撤口径）
    db = _fake_db(_Fund('货币型'), money_row=_MoneyRow())
    result = build_fund_performance(db, '000001')
    assert result is not None
    assert result['fund_kind'] == 'money'
    assert result['applicable'] is True
    assert result['annual_return_7d'] == 1.5
    assert result['nav_per_10k'] == 0.5
    assert result['source'] == '天天基金'


def test_build_open_fund(monkeypatch):
    # 场外基金：构造 48 个月度净值（含一次回撤），验证结构与同源口径。
    # 序列必须**锚定到 today**（末点落在 today 所在月），否则「近1年」窗口内点数
    # 不足 3 → volatility_1y 恒为 None，测不到真实分支。
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    # 从 today 所在月往前推 48 个月，再反转为「最早在前」
    months = []
    y, m = today.year, today.month
    for _ in range(48):
        months.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()
    rows = []
    for i, (y, m) in enumerate(months):
        # 增长率本身要波动：若净利严格单调（如恒定 1.005^i），日收益全同 → 方差 0 → 波动率恒为 0，
        # 测不到真实数值分支。这里用 ±1% 交替偏离做确定性噪声（不引入随机源，保证可复现）。
        growth = 1.005 + (0.01 if i % 2 == 0 else -0.01)
        nav = 1.0 * (growth**i)
        if i == 30:
            nav *= 0.8  # 中途 -20% 回撤（落在近 3 年窗口内）
        rows.append(_DailyWorth(date(y, m, 1), round(nav, 6)))
    db = _fake_db(_Fund('股票型'), daily_rows=rows)
    result = build_fund_performance(db, '110020')
    assert result is not None
    assert result['fund_kind'] == 'fund'
    assert result['applicable'] is True
    assert result['basis'] == 'acc_nav'
    assert len(result['intervals']) == 10
    # 4 年历史覆盖所有窗口（近5年 起点晚于首点 → 退化为首点）→ 区间值均非空
    assert all(iv['value'] is not None for iv in result['intervals'])
    # 含回撤 → 最大回撤为负且非 None，口径 fixed_3y
    assert result['max_drawdown'] is not None
    assert result['max_drawdown'] < 0
    assert result['max_drawdown_basis'] == 'fixed_3y'
    # 近 1 年窗口内 ≥3 个月度点 → 波动率可算（月度间距不代表真实年化，仅验证分支可达）
    assert result['volatility_1y'] is not None
    assert result['volatility_1y'] > 0
    assert result['source'] == '天天基金'


def test_build_open_fund_stale_series_no_volatility(monkeypatch):
    """数据陈旧（末点远早于 today）→ 近1年窗口点数不足，波动率降级为 None 而非报错。

    这条守护的是「序列锚点写错」这类测试自身 bug：实现对陈旧数据必须诚实地返回 None。
    """
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    # 末点 2025-12，距 today 10 个月 → 近1年窗口内只有 1 个点
    rows = [_DailyWorth(date(2025, 11, 1), 1.0), _DailyWorth(date(2025, 12, 1), 1.05)]
    result = build_fund_performance(_fake_db(_Fund('股票型'), daily_rows=rows), '110020')
    assert result['applicable'] is True
    assert result['volatility_1y'] is None
    assert result['max_drawdown'] is None
    assert result['max_drawdown_basis'] == 'insufficient'


# ── #167：风险指标块（本轮回撤 / 夏普族），快照优先 + 现算回退 ────────────────


class _Snap:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _snap_query(snap):
    q = MagicMock()
    q.filter.return_value.order_by.return_value.first.return_value = snap
    return q


def _fake_db_with_snap(fund, snap, daily_rows):
    db = _fake_db(fund, daily_rows=daily_rows)
    base = db.query.side_effect

    def _query(model, *rest):
        if _model_name(model) == 'FundRiskMetrics':
            return _snap_query(snap)
        return base(model, *rest)

    db.query.side_effect = _query
    return db


def _monotonic_rows(today, months=48, drop_at=None):
    """构造锚定 today 的月度净值序列（可选中途一次性回撤）。"""
    rows = []
    for i in range(months):
        y, m = today.year, today.month
        m -= months - 1 - i
        while m <= 0:
            m += 12
            y -= 1
        nav = 1.0 * (1.004**i)
        if drop_at is not None and i >= drop_at:
            nav *= 0.75
        rows.append(_DailyWorth(date(y, m, 1), round(nav, 6)))
    return rows


def test_risk_block_present_for_open_fund(monkeypatch):
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    rows = _monotonic_rows(today, drop_at=30)
    db = _fake_db_with_snap(_Fund('股票型'), None, rows)
    result = build_fund_performance(db, '110020')
    # 快照缺失 → 现算回退
    assert result['risk_source'] == 'computed'
    assert result['current_drawdown'] is not None and result['current_drawdown'] < 0
    assert result['upi'] is not None
    assert result['risk_free_rate'] == 0.015
    assert result['risk_window'] == '近3年'
    assert result['risk_basis'] in ('acc_nav', 'distorted')
    assert result['risk_caveats'], '口径 caveats 必须随值下发'
    assert result['win_rate_period'] == 'month'


def test_risk_block_prefers_fresh_snapshot(monkeypatch):
    """快照 as_of 与净值最新日一致且口径版本对 → 走快照，不回退现算。"""
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    rows = _monotonic_rows(today)
    last = rows[-1].date
    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    snap = _Snap(
        as_of=last,
        caliber_version=CALIBER_VERSION,
        current_drawdown=-3.5,
        drawdown_peak_date=None,
        drawdown_days=12,
        max_drawdown=-9.0,
        max_drawdown_peak_date=None,
        max_drawdown_trough_date=None,
        annual_return=8.0,
        annual_volatility=12.0,
        sharpe=0.54,
        sortino=0.8,
        calmar=0.88,
        ulcer_index=2.0,
        upi=4.0,
        return_drawdown_ratio=7.4,
        win_rate=58.0,
        win_rate_period='month',
        sample_points=len(rows),
        basis='acc_nav',
        window_label='近3年',
    )
    result = build_fund_performance(_fake_db_with_snap(_Fund('股票型'), snap, rows), '110020')
    assert result['risk_source'] == 'snapshot'
    assert result['current_drawdown'] == -3.5
    assert result['max_drawdown'] == -9.0
    assert result['sharpe'] == 0.54


def test_risk_block_falls_back_when_snapshot_stale(monkeypatch):
    """快照落后于最新净值 → 回退现算（否则页面显示的是上一个交易日的口径）。"""
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    rows = _monotonic_rows(today)
    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    snap = _Snap(
        as_of=date(2026, 8, 1),
        caliber_version=CALIBER_VERSION,
        current_drawdown=-99.0,  # 若走快照就会泄漏这个哨兵值
        drawdown_peak_date=None,
        drawdown_days=1,
        max_drawdown=-99.0,
        max_drawdown_peak_date=None,
        max_drawdown_trough_date=None,
        annual_return=None,
        annual_volatility=None,
        sharpe=None,
        sortino=None,
        calmar=None,
        ulcer_index=None,
        upi=None,
        return_drawdown_ratio=None,
        win_rate=None,
        win_rate_period=None,
        sample_points=1,
        basis='acc_nav',
        window_label='近3年',
    )
    result = build_fund_performance(_fake_db_with_snap(_Fund('股票型'), snap, rows), '110020')
    assert result['risk_source'] == 'computed'
    assert result['current_drawdown'] != -99.0


def test_risk_block_falls_back_when_caliber_outdated(monkeypatch):
    """口径版本不符 → 回退现算。旧口径的数与新口径不可比，宁可多算一次。"""
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    rows = _monotonic_rows(today)
    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    snap = _Snap(
        as_of=rows[-1].date,
        caliber_version=CALIBER_VERSION + 1,  # 旧代码写的行
        current_drawdown=-99.0,
        drawdown_peak_date=None,
        drawdown_days=1,
        max_drawdown=-99.0,
        max_drawdown_peak_date=None,
        max_drawdown_trough_date=None,
        annual_return=None,
        annual_volatility=None,
        sharpe=None,
        sortino=None,
        calmar=None,
        ulcer_index=None,
        upi=None,
        return_drawdown_ratio=None,
        win_rate=None,
        win_rate_period=None,
        sample_points=1,
        basis='acc_nav',
        window_label='近3年',
    )
    result = build_fund_performance(_fake_db_with_snap(_Fund('股票型'), snap, rows), '110020')
    assert result['risk_source'] == 'computed'


def test_money_fund_has_no_risk_block():
    """货基没有日净值口径，风险指标块**不出现**（不是显示成「—」，是不该有这个区块）。"""
    db = _fake_db(_Fund('货币型'), money_row=_MoneyRow())
    result = build_fund_performance(db, '000001')
    assert 'current_drawdown' not in result
    assert 'sharpe' not in result


def test_snapshot_and_computed_paths_agree_digit_for_digit(monkeypatch):
    """物化读与现算读**逐位相等** —— 这是物化快照能不能信的判据。

    与 `pnl_snapshot_store` 同款纪律：两条路径不一致就退化回 #1812 那种「静默错数字」，
    而那种错最难发现——页面有值、数字也「像是对的」。

    做法：先用现算跑出一个结果，把它当作快照内容喂回去，要求两条路径输出的
    **同名字段逐个相等**（浮点用精确比较：两条路径调的是同一个纯函数，不该有误差）。
    """
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    rows = _monotonic_rows(today, drop_at=30)
    fund = _Fund('股票型')

    computed = build_fund_performance(_fake_db_with_snap(fund, None, rows), '110020')
    assert computed['risk_source'] == 'computed'

    from app.services.sync.jobs.fund_risk_metrics_job import CALIBER_VERSION

    snap = _Snap(
        as_of=rows[-1].date,
        caliber_version=CALIBER_VERSION,
        current_drawdown=computed['current_drawdown'],
        drawdown_peak_date=None,
        drawdown_days=computed['current_drawdown_days'],
        max_drawdown=computed['max_drawdown'],
        max_drawdown_peak_date=None,
        max_drawdown_trough_date=None,
        annual_return=computed['annual_return'],
        annual_volatility=computed['annual_volatility'],
        sharpe=computed['sharpe'],
        sortino=computed['sortino'],
        calmar=computed['calmar'],
        ulcer_index=computed['ulcer_index'],
        upi=computed['upi'],
        return_drawdown_ratio=computed['return_drawdown_ratio'],
        win_rate=computed['win_rate'],
        win_rate_period=computed['win_rate_period'],
        sample_points=computed['risk_sample_points'],
        basis=computed['risk_basis'],
        window_label=computed['risk_window'],
    )
    from_snap = build_fund_performance(_fake_db_with_snap(fund, snap, rows), '110020')
    assert from_snap['risk_source'] == 'snapshot'

    for key in (
        'current_drawdown',
        'max_drawdown',
        'annual_return',
        'annual_volatility',
        'sharpe',
        'sortino',
        'calmar',
        'ulcer_index',
        'upi',
        'return_drawdown_ratio',
        'win_rate',
        'risk_sample_points',
        'risk_basis',
        'risk_window',
    ):
        assert from_snap[key] == computed[key], f'{key} 在两条路径下不一致'

    # 键集合也必须一致：前端在两条路径下看到的字段不能不同，否则「有时有 sharpe 有时没有」
    assert {k for k in from_snap if k.startswith(('risk_', 'current_', 'max_drawdown'))} == {
        k for k in computed if k.startswith(('risk_', 'current_', 'max_drawdown'))
    }


# ── 基准块与同类分位（#167 追加之二）────────────────────────────────────────


def _bench_points(dates, start=1000.0, step=0.1):
    """基准序列，形态与 `load_index_points` 的返回**逐位一致**：`[(date, close)]` 升序。

    刻意不用「像行对象」的替身：取数函数返回的就是元组，替身形态一旦与它不同，
    这里测的就不是真实契约（`benchmark_diagnostics` 期望元组）。
    """
    return [(d, start + i * step) for i, d in enumerate(dates)]


def _fake_db_with_bench(fund, daily_rows, bench_rows, peer_rows=None):
    """在基础替身上加 `IndexDaily` / `FundRiskMetrics` 多列查询的应答。

    `load_index_points` 走 `db.query(IndexDaily.trade_date, IndexDaily.close)`，
    `peer_percentiles_for` 走 `db.query(FundRiskMetrics....)` —— 都是多列形态。
    """
    db = _fake_db(fund, daily_rows=daily_rows)
    base = db.query.side_effect

    # `load_index_points` 有两条链：给了 limit 走 `.order_by().limit().all()`，
    # 不给走 `.order_by().all()`。两条都要应答——只配一条会让「基准取不到」变成
    # 默认结果，于是「基准块是否真的可用」这个判据永远假绿。
    idx_q = MagicMock()
    idx_q.filter.return_value.order_by.return_value.limit.return_value.all.return_value = bench_rows
    idx_q.filter.return_value.order_by.return_value.all.return_value = bench_rows
    idx_q.filter.return_value.all.return_value = bench_rows

    peer_q = MagicMock()
    peer_q.filter.return_value.all.return_value = peer_rows or []

    def _query(model, *rest):
        name = _model_name(model)
        if name == 'IndexDaily':
            return idx_q
        if name == 'FundRiskMetrics':
            return peer_q
        return base(model, *rest)

    db.query.side_effect = _query
    return db


def test_benchmark_mapped_for_bond_fund(monkeypatch):
    """债基映射到债券族基准，且**不是**沪深300 —— 这是「分类别参照」的核心。

    断言用 `BENCH_BOND_FUND` 常量而非写死代码：映射的具体标的会变
    （2026-10-14 由源侧无序列的 `885005.WI` 换成 `H11001.CSI`），
    不变的是「债基有一个**取得到序列**的债券族基准」这件事本身。
    """
    from app.services.fund_benchmark import BENCH_BOND_FUND

    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    rows = _monotonic_rows(today)
    bench = _bench_points([r.date for r in rows])  # 全覆盖 ⇒ 基准「已同步」

    db = _fake_db_with_bench(_Fund('债券型-长期纯债'), rows, bench)
    out = build_fund_performance(db, '000001')

    assert out['benchmark'] is not None
    b = out['benchmark']
    assert b['code'] == BENCH_BOND_FUND
    assert b['code'] != '000300.SH'
    assert b['matched_by']
    # 原始序列是内部实现，不得下发（前端不该自己算，也不该被 500 个点撑爆响应）
    assert 'points' not in b


def test_benchmark_none_for_index_fund(monkeypatch):
    """指数型不给基准：它该比的是跟踪标的，而源侧无「跟踪标的」字段 ⇒ 不猜。

    关键断言是 `is None` 而不是「有基准」。若实现退回沪深300，本用例会红。
    """
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    db = _fake_db_with_bench(_Fund('指数型-股票'), _monotonic_rows(today), [])
    out = build_fund_performance(db, '000001')
    assert out['benchmark'] is None


def test_benchmark_reports_unavailable_when_series_missing(monkeypatch):
    """映射成立但序列取不到 ⇒ available=False + 原因，**不退回别的指数**。

    构造手法：债基基准（`BENCH_BOND_FUND`）映射成立，但「库里没有它的日线」
    （`_fake_db_with_bench` 传空基准序列）——这正是「尚未跑同步 / 源侧未收录」
    的真实形态。断言用 `BENCH_BOND_FUND` 常量而非写死代码，映射换标的时本用例不失效。
    """
    from app.services.fund_benchmark import BENCH_BOND_FUND

    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    db = _fake_db_with_bench(_Fund('债券型-长期纯债'), _monotonic_rows(today), [])
    out = build_fund_performance(db, '000001')
    b = out['benchmark']
    assert b is not None
    assert b['available'] is False
    assert b['reason']
    assert b['code'] == BENCH_BOND_FUND


def test_benchmark_block_carries_relative_metrics(monkeypatch):
    """基准可用时下发超额 / 信息比率 / 捕获率（两序列按共同交易日对齐后算）。"""
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    rows = _monotonic_rows(today)
    # 基准与基金覆盖同样的日期，但涨得慢 ⇒ 超额为正
    bench = _bench_points([r.date for r in rows], step=0.1)  # 基准涨得比基金慢

    db = _fake_db_with_bench(_Fund('股票型'), rows, bench)
    out = build_fund_performance(db, '000001')
    b = out['benchmark']
    assert b['available'] is True
    # 相对指标键必须齐（缺任何一个前端都会显示成「—」而不知道是没算还是没值）
    for key in ('excess_return', 'information_ratio', 'upside_capture', 'downside_capture'):
        assert key in b, f'基准块缺少 {key}'
    # 基金涨得比基准快 ⇒ 超额为正；这是「算得对」而非「跑通了」的判据
    assert b['excess_return'] is not None and b['excess_return'] > 0
    # 共同交易日数应等于两序列的日期交集
    assert b['sample_points'] == len(rows)


def test_peer_percentiles_absent_when_sample_thin(monkeypatch):
    """同类样本不足 ⇒ 不下发分位（前端降级「—」），而不是给一个 2 只样本的名次。"""
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    db = _fake_db_with_bench(_Fund('股票型'), _monotonic_rows(today), [], peer_rows=[])
    out = build_fund_performance(db, '000001')
    assert out['peer_percentiles'] is None


def test_peer_percentile_failure_does_not_break_the_block(monkeypatch):
    """分位是锦上添花：它失败不该让整个业绩块炸掉（详情页会整块打不开）。"""
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    db = _fake_db_with_bench(_Fund('股票型'), _monotonic_rows(today), [])

    def boom(*a, **k):
        raise RuntimeError('ranking down')

    monkeypatch.setattr('app.services.fund_risk_ranking.peer_percentiles_for', boom)
    out = build_fund_performance(db, '000001')
    assert out is not None
    assert out['peer_percentiles'] is None
    assert out['applicable'] is True


def test_shape_gain2_present_in_payload(monkeypatch):
    """拟涨幅2 随表现卡下发（#167 收尾）；历史不足一年时为 None 而**不是缺席**。

    缺席与 null 的区别：前端拿到 null 才知道「这个位置本该有值、只是没算出来」，
    字段直接不在时它只能猜是「这个品类没有这项」还是「这次没取到」。
    """
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    # 48 个月 ≈ 4 年 ⇒ 有 ≥365 天历史，拟涨幅2 应出值
    rows = _monotonic_rows(today, months=48)
    db = _fake_db_with_bench(_Fund('股票型'), rows, [])
    out = build_fund_performance(db, '000001')
    assert 'shape_gain2' in out
    assert out['shape_gain2'] is not None
    assert 'shape_gain2' in out['shape_gain2']
    assert len(out['shape_gain2']['segments']) == 4


def test_shape_gain2_none_when_short_history(monkeypatch):
    """历史不足一年：key 在、值为 None（不拿别的口径凑）。"""
    today = date(2026, 10, 9)
    monkeypatch.setattr('app.services.fund_performance.today_shanghai', lambda: today)
    # 4 个月 ⇒ 历史不足一年
    rows = _monotonic_rows(today, months=4)
    db = _fake_db_with_bench(_Fund('股票型'), rows, [])
    out = build_fund_performance(db, '000001')
    assert 'shape_gain2' in out
    assert out['shape_gain2'] is None
