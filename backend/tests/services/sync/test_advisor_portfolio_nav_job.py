# -*- coding: utf-8 -*-
"""测试投顾组合净值序列：目标池解析 / 落库幂等 / job 失败语义。

被测对象两处，一起测是因为它们的边界是**同一件事的两半**：

- :mod:`app.services.advisor_nav` —— 「取哪几只」「怎么落库」「怎么读」；
- :class:`AdvisorPortfolioNavSyncJob` —— 「一轮同步里怎么抓、失败怎么隔离」。

测试重点不是「且慢接口长什么样」（那属于适配器），而是三条被既往事故逼出来的语义：

1. **目标池只来自用户触达**（自选 ∪ 持仓），不是库内全量——数据策略准入第 3 问；
2. **空序列 ≠ 故障**：``LONG_WIN`` / ``J7`` / ``WALLET`` 这类计划型 / 钱包型组合
   上游本来就返回 ``[]``，应计 ``skipped`` 而不是把整轮判红（#171 同族）；
3. **没建档的代码要留痕**：``--targets`` 传了一个库里没有的组合时必须进 ``errors``，
   否则「另一台机器上跑同一条命令」会静默变成空跑（空 ≠ 没拿到）。
"""

from datetime import date
from typing import Any, Dict, List, Optional

import pytest

from app.domains.funds.models import AdvisorPortfolio, AdvisorPortfolioNav
from app.domains.watchlist.models import WatchlistItem
from app.services import advisor_nav
from app.services.adapters.advisor_source import AdvisorPortfolioSource
from app.services.mcp.errors import McpTokenMissing, McpUnavailable
from app.services.sync.jobs.advisor_portfolio_nav_job import AdvisorPortfolioNavSyncJob


class _FakeNavSource(AdvisorPortfolioSource):
    """最小假适配器：只关心 ``fetch_nav_history``，其余数据面空实现。

    继承 Port 基类而非 MagicMock——「适配器改了方法名、job 没跟着改」这类破坏
    必须测得出（同 ``test_advisor_portfolio_job._FakeSource`` 的理由）。
    """

    def __init__(
        self,
        platform: str = 'QIEMAN',
        rows: Optional[List[Dict[str, Any]]] = None,
        error: Optional[Exception] = None,
        per_code: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.platform = platform
        self.rows = rows if rows is not None else []
        self.error = error
        #: code → rows / Exception，用于「一只成功一只失败」的隔离用例
        self.per_code = per_code or {}

    def get_name(self) -> str:
        return f'fake_{self.platform.lower()}'

    def get_version(self) -> str:
        return 'v0'

    def fetch_overview(self, code: str) -> dict:
        return {}

    def fetch_holdings(self, code: str) -> dict:
        return {'as_of_date': None, 'funds': []}

    def fetch_industries(self, code: str) -> list:
        return []

    def fetch_rebalances(self, code: str) -> list:
        return []

    def fetch_nav_history(self, code: str) -> List[Dict[str, Any]]:
        override = self.per_code.get(code)
        if isinstance(override, Exception):
            raise override
        if override is not None:
            return override
        if self.error is not None:
            raise self.error
        return self.rows


def _make_job(db, **sources) -> AdvisorPortfolioNavSyncJob:
    """按 ``{platform: 数据源}`` 注入构造任务（生产侧由注册表懒构造）。"""
    return AdvisorPortfolioNavSyncJob(db=db, sources=sources)


def _seed_portfolio(db, code: str = 'ZH012926', platform: str = 'QIEMAN', name: str = '远足') -> AdvisorPortfolio:
    portfolio = AdvisorPortfolio(platform=platform, code=code, name=name)
    db.add(portfolio)
    db.commit()
    return portfolio


# ── 目标池 ──


def test_tracked_codes_union_of_watchlist_and_positions(db, make_position):
    """自选 ∪ 持仓、剥场地前缀、大写去重；非投顾品类不进来。"""
    db.add(WatchlistItem(symbol='NO_VENUE:ZH012926', name='远足', asset_type='portfolio', family_id=1))
    db.add(WatchlistItem(symbol='OTC:zh012926', name='远足(重复)', asset_type='portfolio', family_id=1))
    db.add(WatchlistItem(symbol='110011', name='易方达', asset_type='fund', family_id=1))
    db.commit()
    make_position(symbol='OTC:SI000186', name='稳稳的幸福', asset_type='portfolio', quantity=0)

    # 顺序稳定（升序）便于日志与断言；重复形态归一后只留一条
    assert advisor_nav.tracked_codes(db) == ['SI000186', 'ZH012926']


def test_tracked_portfolios_skips_unregistered_codes(db, make_position):
    """自选里有代码但库内未建档 ⇒ 自然缺席（不猜平台、不伪造实体）。"""
    _seed_portfolio(db, code='ZH012926')
    db.add(WatchlistItem(symbol='NO_VENUE:ZH012926', name='远足', asset_type='portfolio', family_id=1))
    db.add(WatchlistItem(symbol='NO_VENUE:NOT_IN_DB', name='没建档', asset_type='portfolio', family_id=1))
    db.commit()

    rows = advisor_nav.tracked_portfolios(db)
    assert [r.code for r in rows] == ['ZH012926']


def test_tracked_codes_empty_is_legal(db):
    """一个组合都没关注 ⇒ 空列表（合法状态）。job 侧据此走 `_allow_empty_data`。"""
    assert advisor_nav.tracked_codes(db) == []
    assert advisor_nav.tracked_portfolios(db) == []


def test_normalize_code_does_not_guess_platform():
    """只剥场地前缀 + 大写，**不按前缀判平台**（LONG_WIN / J7 也归且慢）。"""
    assert advisor_nav.normalize_code(' NO_VENUE:zh012926 ') == 'ZH012926'
    assert advisor_nav.normalize_code('EXCHANGE:LONG_WIN') == 'LONG_WIN'
    assert advisor_nav.normalize_code(None) == ''


# ── 落库 ──


def test_save_nav_rows_is_idempotent_and_drops_invalid(db):
    """重复写同一日期不新增；非法行进垃圾桶（净值 0 会在图上造假暴跌）。"""
    portfolio = _seed_portfolio(db)
    rows = [
        {'nav_date': '2026-10-28', 'nav': 1.2345},
        {'nav_date': '2026-10-29', 'nav': 1.2400},
    ]
    assert advisor_nav.save_nav_rows(db, portfolio.id, rows, 'qieman') == 2
    # 原样再写一次：既不插入也不更新
    assert advisor_nav.save_nav_rows(db, portfolio.id, rows, 'qieman') == 0
    # 上游修正当日净值 ⇒ 覆盖（否则曲线与组合页「最新净值」对不上）
    assert advisor_nav.save_nav_rows(db, portfolio.id, [{'nav_date': '2026-10-29', 'nav': 1.25}], 'qieman') == 1

    stored = (
        db.query(AdvisorPortfolioNav.nav_date, AdvisorPortfolioNav.nav)
        .filter(AdvisorPortfolioNav.portfolio_id == portfolio.id)
        .order_by(AdvisorPortfolioNav.nav_date)
        .all()
    )
    assert [(str(d), float(n)) for d, n in stored] == [('2026-10-28', 1.2345), ('2026-10-29', 1.25)]


def test_save_nav_rows_drops_unparsable_and_non_positive(db):
    """解析不出日期 / 非数字 / ``nav <= 0`` 一律丢弃（不补 0、不猜）。"""
    portfolio = _seed_portfolio(db)
    rows = [
        {'nav_date': None, 'nav': 1.2},
        {'nav_date': '2026-10-28', 'nav': None},
        {'nav_date': '2026-10-28', 'nav': 0},
        {'nav_date': '2026-10-28', 'nav': -1.0},
        {'nav_date': 'not-a-date', 'nav': 1.1},
        {'nav_date': '2026/10/30', 'nav': '1.3000'},  # 斜杠 + 字符串数字：合法，归一后入库
    ]
    assert advisor_nav.save_nav_rows(db, portfolio.id, rows, 'qieman') == 1
    assert advisor_nav.latest_nav_date(db, portfolio.id) == date(2026, 10, 30)
    # 全非法 ⇒ 一行都不写，且不是异常
    assert advisor_nav.save_nav_rows(db, portfolio.id, [{'nav_date': None, 'nav': 1}], 'qieman') == 0


def test_load_series_filters_by_start_and_orders(db):
    """读路径：``start`` 起、升序、四舍六入到 6 位。"""
    portfolio = _seed_portfolio(db)
    advisor_nav.save_nav_rows(
        db,
        portfolio.id,
        [
            {'nav_date': '2026-09-01', 'nav': 1.1000004},
            {'nav_date': '2026-10-01', 'nav': 1.2000004},
            {'nav_date': '2026-10-29', 'nav': 1.3000004},
        ],
        'qieman',
    )
    series = advisor_nav.load_series(db, portfolio.id, date(2026, 10, 1))
    assert [str(d) for d, _ in series] == ['2026-10-01', '2026-10-29']
    assert series[0][1] == pytest.approx(1.200000)
    assert advisor_nav.series_source_code(db, portfolio.id) == 'qieman'


def test_series_source_code_is_raw_code_not_label(db):
    """来源码原样返回（``qieman``），映射成「且慢」是 product_trend 的事。

    这条钉的是「数据层与展示层各映射一次」的同族问题：映射表以后改了，
    双映射会让一处生效、一处不生效。
    """
    portfolio = _seed_portfolio(db)
    advisor_nav.save_nav_rows(db, portfolio.id, [{'nav_date': '2026-10-29', 'nav': 1.2}], 'qieman')
    assert advisor_nav.series_source_code(db, portfolio.id) == 'qieman'


# ── job ──


def test_job_persists_nav_rows_for_tracked_portfolio(db, make_position):
    """端到端：自选命中 + 抓取返回序列 ⇒ 落库，且状态 success。"""
    portfolio = _seed_portfolio(db)
    db.add(WatchlistItem(symbol='NO_VENUE:ZH012926', name='远足', asset_type='portfolio', family_id=1))
    db.commit()

    job = _make_job(
        db,
        QIEMAN=_FakeNavSource(rows=[{'nav_date': '2026-10-28', 'nav': 1.11}, {'nav_date': '2026-10-29', 'nav': 1.12}]),
    )
    result = job.run(full_sync=True, targets=['__full__'])

    assert result['status'] == 'success'
    assert result['stats']['success'] == 1
    assert result['stats']['errors'] == []
    stored = db.query(AdvisorPortfolioNav).filter_by(portfolio_id=portfolio.id).all()
    assert len(stored) == 2
    assert {s.source for s in stored} == {'qieman'}


def test_job_explicit_targets_use_given_codes(db, make_position):
    """显式 targets 走 code 回查，不需要自选 / 持仓命中（补数据 / 排查单只）。"""
    portfolio = _seed_portfolio(db, code='ZH012926')
    job = _make_job(db, QIEMAN=_FakeNavSource(rows=[{'nav_date': '2026-10-29', 'nav': 1.12}]))
    result = job.run(full_sync=True, targets=['zh012926'])  # 小写也要能命中

    assert result['status'] == 'success'
    assert db.query(AdvisorPortfolioNav).filter_by(portfolio_id=portfolio.id).count() == 1


def test_job_empty_series_is_not_an_error(db):
    """空序列（计划型 / 钱包型组合）⇒ 不进 errors、状态仍 success，且留可见记号。

    ``LONG_WIN`` / ``LONG_WIN_S`` / ``J7`` / ``WALLET`` / ``SI000186`` 实测上游返回 ``[]``。
    把它们判成故障，等于每轮都红、真故障被淹没（#171 同族）。

    同时钉住**不要**把它们记进 ``skipped``：``skipped`` 的语义是「通过校验、被去重剔除」，
    空序列在 ``_validate_data`` 就被剔了，硬记 skipped 会让两个不同原因共用一个数，
    排查时分不清「上游没给」与「库里已有」。
    """
    _seed_portfolio(db, code='LONG_WIN', name='长赢指数投资计划')
    job = _make_job(db, QIEMAN=_FakeNavSource(rows=[]))
    result = job.run(full_sync=True, targets=['LONG_WIN'])

    assert result['status'] == 'success'
    assert result['stats']['errors'] == []
    assert result['stats']['skipped'] == 0
    assert result['stats']['success'] == 0
    assert result['stats']['empty_series'] == ['LONG_WIN']
    assert db.query(AdvisorPortfolioNav).count() == 0


def test_job_partial_failure_isolated_per_portfolio(db):
    """一只失败不拖垮整批：失败的进 errors + degraded，成功的照常落库，状态仍 success。"""
    good = _seed_portfolio(db, code='ZH012926', name='远足')
    bad = _seed_portfolio(db, code='ZH000001', name='另一只')
    job = _make_job(
        db,
        QIEMAN=_FakeNavSource(
            per_code={
                'ZH012926': [{'nav_date': '2026-10-29', 'nav': 1.12}],
                'ZH000001': McpUnavailable('upstream 502'),
            }
        ),
    )
    result = job.run(full_sync=True, targets=['ZH012926', 'ZH000001'])

    assert result['status'] == 'success'
    assert len(result['stats']['errors']) == 1
    assert 'ZH000001' in result['stats']['errors'][0]
    assert result['stats']['degraded'] == 1
    assert db.query(AdvisorPortfolioNav).filter_by(portfolio_id=good.id).count() == 1
    assert db.query(AdvisorPortfolioNav).filter_by(portfolio_id=bad.id).count() == 0


def test_job_all_failed_becomes_failed(db):
    """全部目标都失败且一条没写 ⇒ FAILED（绿色状态是假绿，见 #2495）。"""
    _seed_portfolio(db, code='ZH012926')
    job = _make_job(db, QIEMAN=_FakeNavSource(error=McpUnavailable('upstream down')))
    result = job.run(full_sync=True, targets=['ZH012926'])

    assert result['status'] == 'failed'
    assert result['stats']['success'] == 0
    assert len(result['stats']['errors']) == 1


def test_job_token_missing_counts_as_degraded_not_error(db):
    """未配置 Token = 该平台功能关闭：**不进 errors**（不制造假红灯），但 degraded 可见。"""
    _seed_portfolio(db, code='ZH012926')
    job = _make_job(db, QIEMAN=_FakeNavSource(error=McpTokenMissing()))
    result = job.run(full_sync=True, targets=['ZH012926'])

    # errors 为空 ⇒ errors 不触发失败判定；但 success=0 且 total>0 也不该判红
    # （「功能关闭」不是「跑到一半坏了」）
    assert result['stats']['errors'] == []
    assert result['stats']['degraded'] == 1
    assert result['stats']['success'] == 0


def test_job_unregistered_target_records_error(db):
    """``--targets`` 传了库内没建档的组合 ⇒ 进 errors 并留日志。

    静默跳过会让「换台机器跑同一条命令」变成空跑，而日志一片绿。
    """
    job = _make_job(db, QIEMAN=_FakeNavSource(rows=[{'nav_date': '2026-10-29', 'nav': 1.1}]))
    result = job.run(full_sync=True, targets=['ZH999999'])

    assert result['status'] == 'failed'
    assert len(result['stats']['errors']) == 1
    assert 'ZH999999' in result['stats']['errors'][0]


def test_job_unknown_platform_is_skipped_without_crashing(db):
    """库内存在尚无适配器的平台 ⇒ 跳过该组合，不炸整轮。"""
    _seed_portfolio(db, code='ABC123', platform='HOWBUY_UNKNOWN')
    job = _make_job(db, QIEMAN=_FakeNavSource(rows=[{'nav_date': '2026-10-29', 'nav': 1.1}]))
    result = job.run(full_sync=True, targets=['ABC123'])

    assert result['status'] == 'success'
    assert result['stats']['errors'] == []
    assert db.query(AdvisorPortfolioNav).count() == 0


def test_job_ignores_full_placeholder_and_falls_back_to_tracked(db, make_position):
    """``__full__`` 是「不用外部目标池」而非「全库刷」：仍只取用户触达范围。"""
    tracked = _seed_portfolio(db, code='ZH012926')
    _seed_portfolio(db, code='ZH888888', name='库内其它组合')
    db.add(WatchlistItem(symbol='NO_VENUE:ZH012926', name='远足', asset_type='portfolio', family_id=1))
    db.commit()

    job = _make_job(db, QIEMAN=_FakeNavSource(rows=[{'nav_date': '2026-10-29', 'nav': 1.1}]))
    job.run(full_sync=True, targets=['__full__'])

    assert db.query(AdvisorPortfolioNav).filter_by(portfolio_id=tracked.id).count() == 1
    assert db.query(AdvisorPortfolioNav).count() == 1  # 全库刷的形态会是 2


def test_job_no_tracked_portfolio_is_success_noop(db):
    """一个组合都没关注 ⇒ 空跑且成功（合法状态，不是故障）。"""
    job = _make_job(db, QIEMAN=_FakeNavSource(rows=[{'nav_date': '2026-10-29', 'nav': 1.1}]))
    result = job.run(full_sync=True, targets=None)

    assert result['status'] == 'success'
    assert result['stats']['errors'] == []
    assert db.query(AdvisorPortfolioNav).count() == 0
