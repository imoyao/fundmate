# -*- coding: utf-8 -*-
"""基金公司按需回填（#2037 方案 A）。

覆盖五件事，每条都对应实现里一个有代价的分支：

1. **已有 `company_id` 时零外部请求** —— 11.5% 已填数据的路径不该再打网络；
2. **空 `company_id` 时按 symbol 单只回填并落库**，二次调用不再请求（缓存生效）；
3. **取数失败 / 查不到 → 降级 None 且进负缓存**，第二次调用不再打网络
   （否则用户每次冷开详情页都白等一个 6s 超时）；
4. **走唯一写入口** —— 公司行经 `get_or_create_fund_company` 建，`code` 拿到东财权威值；
5. **`build_fund_profile` 把回填结果接到 `company` 字段**，且其余字段不受影响。

⚠️ 一律**不触网**：取数口 `fetch_fund_company_of` / 公司名录 `fetch_fund_company_list`
在本文件内被 monkeypatch 替换。`company_resolver` 的模块级缓存是跨用例的进程态，
autouse fixture 一并清掉，避免用例间互相污染（`reset_cache`）。
"""

from contextlib import closing

import pytest

from app.core.db_factory import market_session_factory
from app.domains.funds.models import Fund, FundCompany
from app.services import fund_company_backfill as backfill_module
from app.services import fund_profile as fund_profile_module
from app.services.fund_company_backfill import ensure_fund_company, reset_miss_cache
from app.services.sync import company_resolver as resolver_module

CODE = '004369'


@pytest.fixture(autouse=True)
def _isolated_caches(monkeypatch):
    """清掉两个进程级缓存，并挡住真实网络。

    - `reset_miss_cache`：负缓存是模块级 dict，不清会让上一个用例的失败记录影响下一个；
    - `resolver.reset_cache`：东财名录索引是 `_cache` 兼「已加载」哨兵，不清则第一个
      用例会真去抓 `jjjz_gs.js`（慢且可能因上游波动让本文件变红）；
    - `fetch_fund_company_list` 替换为本地假名录：`get_or_create_fund_company` 建行时会
      经 `resolve_company_identity` 解析权威 code。
    """
    reset_miss_cache()
    resolver_module.reset_cache()
    monkeypatch.setattr(
        resolver_module,
        'fetch_fund_company_list',
        lambda: [{'code': '80000229', 'name': '易方达基金'}],
    )
    yield
    reset_miss_cache()
    resolver_module.reset_cache()


def _market_db():
    return market_session_factory()()


def _seed_fund(code=CODE, name='测试基金', company_id=None):
    """造/更新一只基金，返回其 id（int；commit 后实例属性已过期，不能返回 ORM 对象）。

    每次都**同步** name 与 company_id：测试库的 market 域在用例间未必清干净
    （conftest 的 `clean_db` 只清当前引擎实际存在的表），沿用旧值会让断言读到
    上一个用例留下的数据——本文件曾因此把 `name` 断言打到别的基金的简称上。
    """
    with closing(_market_db()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == code).first()
        if fund is None:
            fund = Fund(fund_code=code, name=name)
            db.add(fund)
        fund.name = name
        fund.company_id = company_id
        db.commit()
        return fund.id


def _seed_company(name='易方达基金', code='80000229'):
    with closing(_market_db()) as db:
        row = db.query(FundCompany).filter_by(code=code).first()
        if row is None:
            row = FundCompany(name=name, code=code)
            db.add(row)
            db.commit()
            return row.id
        return row.id


def _company_of(code=CODE):
    with closing(_market_db()) as db:
        fund = db.query(Fund).filter(Fund.fund_code == code).first()
        return fund.company_id if fund else None


# ── 路径 1：已有 company_id，零外部请求 ────────────────────────────────
def test_existing_company_id_does_not_call_network(monkeypatch):
    """已有归属 → 直接读库返回，**不得**发起任何外部请求。"""
    company_id = _seed_company()
    _seed_fund(company_id=company_id)

    def _boom(*a, **k):
        raise AssertionError('已有 company_id 时不应发起外部请求')

    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', _boom)

    with closing(_market_db()) as db:
        assert ensure_fund_company(db, CODE) == '易方达基金'


# ── 路径 3：空 company_id 时按需回填 ──────────────────────────────────
def test_backfills_and_persists_company(monkeypatch):
    """空 company_id → 取数 → 建公司行 → 写回 funds.company_id 并落库。"""
    _seed_fund()
    calls = []

    def _fake(code, *a, **k):
        calls.append(code)
        return {'name': '易方达基金', 'code': '80000229'}

    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', _fake)

    with closing(_market_db()) as db:
        assert ensure_fund_company(db, CODE) == '易方达基金'

    assert calls == [CODE]
    assert _company_of() is not None, '回填必须落库，否则下次冷开又得重新抓'


def test_second_call_skips_network_after_backfill(monkeypatch):
    """回填成功后第二次调用走 DB 快路径，不再请求外部。"""
    _seed_fund()
    monkeypatch.setattr(
        backfill_module, 'fetch_fund_company_of', lambda *a, **k: {'name': '易方达基金', 'code': '80000229'}
    )
    with closing(_market_db()) as db:
        ensure_fund_company(db, CODE)

    def _boom(*a, **k):
        raise AssertionError('已回填的基金不应再次请求外部')

    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', _boom)
    with closing(_market_db()) as db:
        assert ensure_fund_company(db, CODE) == '易方达基金'


def test_uses_authoritative_company_code(monkeypatch):
    """公司行的 code 取东财权威值，不是「名称占位」。

    `code == name` 的占位行意味着这家公司永远无法与 jjjz_gs.js 名录对齐
    （`backfill_fund_company_codes` 之后还得再修一次）。本用例锁住「唯一写入口
    解析出真 code」这条链路。
    """
    _seed_fund()
    monkeypatch.setattr(
        backfill_module, 'fetch_fund_company_of', lambda *a, **k: {'name': '易方达基金', 'code': '80000229'}
    )

    with closing(_market_db()) as db:
        ensure_fund_company(db, CODE)

    with closing(_market_db()) as db:
        row = db.query(FundCompany).filter(FundCompany.name == '易方达基金').first()
        assert row is not None
        assert row.code == '80000229'
        assert row.code != row.name, 'code==name 即占位行，说明没解析到权威 code'


# ── 负缓存：失败不是每次都重试 ────────────────────────────────────────
@pytest.mark.parametrize(
    'fetch_result',
    [None, {'name': '', 'code': ''}],
    ids=['fetch_returned_none', 'fetch_returned_blank_name'],
)
def test_miss_is_cached_so_repeat_call_skips_network(monkeypatch, fetch_result):
    """查不到 → 降级 None 且**进负缓存**：第二次调用不再打网络。

    没有负缓存的话，一只本就查不到公司的基金会让用户每次冷开详情页都白等一个
    6s 超时——L3 的「可降级」就退化成「每次都卡」。
    """
    _seed_fund()
    calls = []

    def _fake(code, *a, **k):
        calls.append(code)
        return fetch_result

    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', _fake)

    with closing(_market_db()) as db:
        assert ensure_fund_company(db, CODE) is None
    assert len(calls) == 1

    with closing(_market_db()) as db:
        assert ensure_fund_company(db, CODE) is None
    assert len(calls) == 1, '负缓存未生效：第二次仍在打外部请求'


def test_unrecorded_code_is_not_a_miss_cache_hit(monkeypatch):
    """**未记录过**的 code 不得被判为命中负缓存（#2089 CI 6 例红 的真根因）。

    曾经的实现是 ``(time.monotonic() - _MISS_CACHE.get(code, 0.0)) < TTL``，而
    ``time.monotonic()`` 返回的是**进程启动后的秒数**：进程启动后的前 30 分钟内，
    ``0.0 → 现在`` 的差值小于 TTL，于是**从未记录**的 code 也被判成「命中」。

    后果两条，第二条当时没人看见：

    1. 测试只在 CI 上红：GitHub runner 每次全新启动，跑到本文件时 uptime 约
       400s < 1800s；开发机开机已久、uptime 几十万秒，判据看着完全正常。
    2. 生产上更严重：应用每次重启后的前 30 分钟内，L3 懒加载整体失效，
       详情页基金公司恒为「—」，且不发起任何请求。

    用假时钟把三种情形钉住，**不依赖跑测机器的真实 uptime**（否则本地这条测试
    在开机 30 分钟后会恒绿、CI 才红，等于没测）。
    """

    class _FakeClock:
        def __init__(self, now):
            self.now = now

        def monotonic(self):
            return self.now

    monkeypatch.setattr(backfill_module, 'time', _FakeClock(10.0))
    assert backfill_module._in_miss_cache('NEVER-SEEN') is False, '进程刚启动时未记录的 code 不得算命中'

    backfill_module._remember_miss('SEEN')
    assert backfill_module._in_miss_cache('SEEN') is True, '记录过且未过期应命中'

    monkeypatch.setattr(backfill_module, 'time', _FakeClock(10.0 + backfill_module._MISS_TTL_SECONDS + 1))
    assert backfill_module._in_miss_cache('SEEN') is False, '超过 TTL 应失效'


def test_fetch_exception_degrades_to_none(monkeypatch):
    """取数口抛异常 → 降级 None，不把异常抛给详情页（否则整页 500）。"""

    def _boom(*a, **k):
        raise RuntimeError('network down')

    _seed_fund()
    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', _boom)

    with closing(_market_db()) as db:
        assert ensure_fund_company(db, CODE) is None
    assert _company_of() is None, '取数失败不得写库（一次抖动不该固化成永久留白）'


def test_missing_fund_returns_none_without_network(monkeypatch):
    """基金不存在 → None，且不发起外部请求（不能给不存在的东西编公司）。"""

    def _boom(*a, **k):
        raise AssertionError('基金不存在时不应发起外部请求')

    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', _boom)
    with closing(_market_db()) as db:
        assert ensure_fund_company(db, 'NOPE00') is None


def test_blank_code_returns_none():
    with closing(_market_db()) as db:
        assert ensure_fund_company(db, '  ') is None


# ── 事务与副作用边界（两个真实缺陷的回归保护）────────────────────────
def test_write_failure_rolls_back_partial_company_row(monkeypatch):
    """写库中途失败 → 回滚，**不留半成品公司行**。

    `get_or_create_fund_company` 在同事务里 `flush` 了新建的公司行；若回填随后失败
    而不 rollback，那行会留在调用方的会话事务里——调用方之后任何一次 commit 都会把
    「公司建好了、基金没挂上」的行落库。这种残迹比缺字段更难查。
    """
    _seed_fund()
    monkeypatch.setattr(backfill_module, 'fetch_fund_company_of', lambda *a, **k: {'name': '新公司X', 'code': 'X'})

    def _boom(db, name, cache=None):
        db.add(FundCompany(name='新公司X', code='X'))
        db.flush()  # 模拟 resolver 的行为：行已进入事务
        raise RuntimeError('写库炸了')

    monkeypatch.setattr(backfill_module, 'get_or_create_fund_company', _boom)

    with closing(_market_db()) as db:
        assert ensure_fund_company(db, CODE) is None
        # 会话内不得残留未提交的半成品
        assert db.query(FundCompany).filter_by(code='X').first() is None

    # 关会话（closing 会回滚未提交事务）后再查，确认没有落库
    with closing(_market_db()) as db:
        assert db.query(FundCompany).filter_by(code='X').first() is None


def test_does_not_disturb_caller_session_objects(monkeypatch):
    """回填不得让调用方会话里**其它**对象的未提交改动消失。

    这条盯的是 `refresh` vs `expire_all`：后者会把整个会话的实例一并过期，调用方
    在同一会话里改的其它对象会被静默丢弃。实现只 `refresh(fund)`，别的对象不动。
    """
    code = '004371'
    _seed_fund(code=code)
    other = _seed_fund(code='004372', name='不该消失的基金')

    def _fake_ensure(db, target_code):
        db.commit()
        return '易方达基金'

    monkeypatch.setattr(fund_profile_module, 'ensure_fund_company', _fake_ensure)

    with closing(_market_db()) as db:
        # 模拟调用方在同会话改了别的对象
        touched = db.query(Fund).filter(Fund.id == other).one()
        touched.name = '调用方改过的名字'
        assert touched.name == '调用方改过的名字'

        fund_profile_module.build_fund_profile(db, code)

        # 同一会话内、改动应仍在（未被 expire_all 静默丢弃）
        assert db.query(Fund).filter(Fund.id == other).one().name == '调用方改过的名字'
        db.rollback()  # 测试收尾，不留痕


# ── 接入点：build_fund_profile ─────────────────────────────────────────
def test_profile_company_uses_existing_relationship(monkeypatch):
    """已有 company_id → 聚合层直接用它，且不回填（不触网）。"""
    company_id = _seed_company()
    _seed_fund(company_id=company_id)

    def _boom(*a, **k):
        raise AssertionError('已有归属时不应触发回填')

    monkeypatch.setattr(fund_profile_module, 'ensure_fund_company', _boom)

    with closing(_market_db()) as db:
        profile = fund_profile_module.build_fund_profile(db, CODE)
    assert profile['company'] == '易方达基金'


def test_profile_company_falls_back_to_lazy_backfill(monkeypatch):
    """company_id 为空 → 走回填，回填结果出现在 profile['company']。"""
    _seed_fund()
    seen = []

    def _fake_ensure(db, code):
        seen.append(code)
        return '易方达基金'

    monkeypatch.setattr(fund_profile_module, 'ensure_fund_company', _fake_ensure)

    with closing(_market_db()) as db:
        profile = fund_profile_module.build_fund_profile(db, CODE)

    assert seen == [CODE]
    assert profile['company'] == '易方达基金'
    # 回填不得影响其余字段：净值等照常返回（这里没造净值，只断言键在且为 None）
    assert 'unit_nav' in profile and 'managers' in profile


def test_profile_survives_backfill_failure(monkeypatch):
    """回填返回 None → profile['company'] 为 None，其余字段完整。

    前端据此降级为「—」。这是本方案的核心承诺：外部不可用只损失一个字段，
    不让整个详情页失败。
    """
    _seed_fund()
    monkeypatch.setattr(fund_profile_module, 'ensure_fund_company', lambda db, code: None)

    with closing(_market_db()) as db:
        profile = fund_profile_module.build_fund_profile(db, CODE)

    assert profile is not None
    assert profile['company'] is None
    assert profile['source'] == '天天基金'


def test_profile_reads_scalar_fields_after_backfill(monkeypatch):
    """回填会 commit（ORM 实例随之过期），此后读标量字段不得报错或变 None。

    这条锁的是实现里的顺序约定：回填放在资料拼装**之后**。若有人把
    `ensure_fund_company` 挪到拼装之前，`fund.scale` / `fund.name` 就会在过期实例上
    被读，触发逐字段 refresh（慢）甚至 DetachedInstanceError。
    """
    # 用独立 code：本文件的 `_seed_fund` 只在基金不存在时才建，004369 早已被前面的
    # 用例以默认名建过，name 改不动（断言会读到别人的值）。
    code = '004370'
    _seed_fund(code=code, name='易方达蓝筹精选混合')
    with closing(_market_db()) as db:
        db.query(Fund).filter(Fund.fund_code == code).one().scale = 12.5
        db.commit()

    def _fake_ensure(db, code):
        # 模拟真实回填：commit 让会话内实例过期
        db.commit()
        return '易方达基金'

    monkeypatch.setattr(fund_profile_module, 'ensure_fund_company', _fake_ensure)

    with closing(_market_db()) as db:
        profile = fund_profile_module.build_fund_profile(db, code)

    assert profile['company'] == '易方达基金'
    assert profile['name'] == '易方达蓝筹精选混合'
    assert float(profile['scale']) == 12.5
