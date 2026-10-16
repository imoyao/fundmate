# -*- coding: utf-8 -*-
"""风险收益指标日快照 job（#167）单元测试。

重点不在「能不能跑」，而在三条容易静默走错的**语义**：

1. **空池必须跳过，绝不退化全库** —— `targets or 全库` 是 #1403 的形态；
2. **本轮回撤与最大回撤同时落库**（#167 用户的明确要求），且 0.0 不被当成「没值」丢掉；
3. **跳变样本标 `basis=distorted` 但仍落库** —— 剔除是读路径的决定，不是写路径的；
   写路径丢行会让「为什么这只基金查不到」无从解释。
"""

from datetime import date, timedelta

from app.services.sync.jobs.fund_risk_metrics_job import (
    CALIBER_VERSION,
    FULL_TARGET,
    FundRiskMetricsSyncJob,
    _NavRow,
)


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def distinct(self):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self  # 假库已按查询方向排好序，见 _FakeDb.query 的 nav 分支

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


def _series(values, start=date(2023, 1, 2)):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


class _FakeDb:
    """极简假 Session：只回答本 job 用到的几次查询（按实体名分派）。"""

    def __init__(self, position_symbols=(), watchlist_symbols=(), nav=None, funds=None):
        self._position = [(s,) for s in position_symbols]
        self._watchlist = [(s,) for s in watchlist_symbols]
        self._nav = nav or {}
        self._funds = funds or {}
        self.committed = 0
        self.added = []

    def query(self, *entities):
        # 列表达式是 InstrumentedAttribute：类名要用 `class_`（`__name__` 取不到），
        # 列名用 `.key`。按「(实体类名, 列名)」分派，而不是按 `__name__`——后者对列恒为空串。
        names = tuple((getattr(getattr(e, 'class_', None), '__name__', ''), getattr(e, 'key', '')) for e in entities)
        if names == (('Position', 'symbol'),):
            return _FakeQuery(self._position)
        if names == (('WatchlistItem', 'symbol'),):
            return _FakeQuery(self._watchlist)
        if names == (('Fund', 'fund_code'), ('Fund', 'fund_type_id')):
            return _FakeQuery([(c, self._funds.get(c)) for c in self._funds])
        if names == (
            ('DailyWorth', 'fund_code'),
            ('DailyWorth', 'date'),
            ('DailyWorth', 'unit_nav'),
            ('DailyWorth', 'acc_nav'),
        ):
            rows = []
            for code, pts in self._nav.items():
                for d, v in reversed(pts):  # 查询按 date desc 返回
                    rows.append((code, d, v, None))
            return _FakeQuery(rows)
        if names == (('DailyWorth', 'fund_code'),):  # 显式全库：库内有净值的基金
            return _FakeQuery([(c,) for c in self._nav])
        if names == (('FundRiskMetrics', 'fund_code'), ('FundRiskMetrics', 'as_of')):
            return _FakeQuery([])  # 总是「库里还没有这一行」→ 走 add 分支
        return _FakeQuery([])

    def add(self, obj):
        self.added.append(obj)

    @property
    def last_added(self):
        return self.added[-1] if self.added else None

    def commit(self):
        self.committed += 1


def _job(db):
    job = FundRiskMetricsSyncJob.__new__(FundRiskMetricsSyncJob)
    from app.services.adapters.null_adapter import NullAdapter

    FundRiskMetricsSyncJob.__init__(job, db)
    assert isinstance(job.adapter, NullAdapter)
    return job


# ── 目标池语义 ───────────────────────────────────────────────────────────────


def test_empty_pool_skips_and_never_falls_back_to_all():
    """无持仓无自选 → 跳过。这是 #1403 的形态：`targets if targets else 全库`。"""
    db = _FakeDb()
    job = _job(db)
    result = job.run(full_sync=False, targets=None)
    assert result['status'] == 'success'
    assert result['stats']['total'] == 0
    assert db.committed == 0


def test_user_scope_merges_positions_and_watchlist():
    db = _FakeDb(position_symbols=['110020'], watchlist_symbols=['000001'])
    job = _job(db)
    assert job._codes_from_user_scope() == ['000001', '110020']


def test_full_target_expands_to_funds_with_nav():
    db = _FakeDb(nav={'110020': _series([1.0, 1.1])})
    job = _job(db)
    assert job._resolve_codes([FULL_TARGET]) == ['110020']


def test_explicit_targets_win_over_user_scope():
    db = _FakeDb(position_symbols=['110020'])
    job = _job(db)
    assert job._resolve_codes(['519674']) == ['519674']


# ── 落库字段（两条回撤都要有） ────────────────────────────────────────────────


def test_writes_both_drawdowns():
    """#167 的核心要求：最大回撤 **与** 本轮回撤都要能看到。"""
    values = [1.0 + i * 0.01 for i in range(40)]
    values += [values[-1] * 0.7, values[-1] * 0.72, values[-1] * 0.68]  # 深跌后未修复
    db = _FakeDb(position_symbols=['110020'], nav={'110020': _series(values)}, funds={'110020': 3})
    job = _job(db)
    result = job.run()
    assert result['status'] == 'success'
    rec = db.last_added
    assert rec.fund_code == '110020'
    assert rec.max_drawdown is not None and rec.max_drawdown < 0
    assert rec.current_drawdown is not None and rec.current_drawdown < 0
    assert rec.drawdown_peak_date is not None
    assert rec.fund_type_id == 3
    assert rec.caliber_version == CALIBER_VERSION
    assert rec.window_label == '近3年'


def test_current_drawdown_zero_is_written_not_dropped():
    """最新一日即新高 → current_drawdown == 0.0，必须落库为 0 而不是被当成 falsy 丢掉。"""
    values = [1.0 + i * 0.01 for i in range(40)]
    db = _FakeDb(position_symbols=['110020'], nav={'110020': _series(values)})
    job = _job(db)
    job.run()
    rec = db.last_added
    assert rec.current_drawdown == 0.0
    assert rec.max_drawdown == 0.0  # 单调上涨：最大回撤 0，同号（负数域里的 0）


def test_distorted_sample_is_still_written_with_basis():
    """跳变样本标 distorted 但仍落库 —— 删行会让「查不到」无从解释。"""
    values = [1.0] * 20 + [1.6] + [1.6] * 20  # +60% 单日跳变
    db = _FakeDb(position_symbols=['110020'], nav={'110020': _series(values)})
    job = _job(db)
    job.run()
    assert db.last_added.basis == 'distorted'


def test_no_nav_fund_is_skipped_not_crashed():
    db = _FakeDb(position_symbols=['110020', '999999'], nav={'110020': _series([1.0, 1.1, 1.2])})
    job = _job(db)
    result = job.run()
    assert result['stats']['success'] == 1
    assert result['stats']['no_nav'] == 1


def test_nav_row_shape_matches_load_nav_points_contract():
    row = _NavRow(date(2024, 1, 2), None, 1.5)
    assert row.acc_nav is None and row.unit_nav == 1.5
    assert row.date == date(2024, 1, 2)
