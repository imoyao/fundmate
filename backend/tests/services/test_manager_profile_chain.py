# -*- coding: utf-8 -*-
"""写入→ 读取全链路（#1970 扩展 · **用东财真实字段值**跑，禁mock）。

与 ``test_fund_manager_job_profile.py``（单元级，用构造数据）的分工：
那一层验证「反推函数对不对」，本文件验证**链路接不接得上**——
适配器透传的三个字段，能不能一路走到前端最终看到的展示文本。

## 为什么必须有这一层

单测全绿也可能是**每一环各自正确、接起来断掉**。三个真实断点：

1. ``akshare_adapter`` 透传的键名与 ``_save_data`` 读取的键名不一致；
2. 写入侧填了，但 ``manager_profile`` 取的是另一个字段；
3. 原始值落了，但展示档忘了附``basis``（前端无从判断口径）。

真实数据（取自 ``ak.fund_manager_em()`` 的实际返回形态）能把这三处照出来。

## 口径锚点与精度边界

张坤 ``tenure_days=5125``。以 ``2026-10-10`` 为基准反推得 ``2012-09-28``，
与天天基金 F10 实测的 110011「任职起始日 2012-09-28」**逐日相同**。

⚠️ **但这是±1 天的估计值，不是精确到日的首次任职日**：基准日取 ``date.today()``，
而东财该字段的统计截止日未知（T 日或 T-1）。实测跨零点重跑（``2026-10-11``）
同一份数据会得到 ``2012-09-29``。故本文件断言的是**不变量**而非硬编码日期——
见 ``test_derived_start_is_within_one_day_of_f10_anchor``：反推值必须落在
F10 锚点 ±1 天内。硬编码某个日期会让测试在跨零点那天假红（已踩过一次）。
"""

from contextlib import closing
from datetime import date

import pytest

from app.core.db_factory import market_session_factory
from app.domains.funds.models import Manager
from app.services.manager_profile import build_manager_profile
from app.services.sync.jobs import fund_manager_job as fm_job
from app.services.sync.jobs.fund_manager_job import FundManagerSyncJob

AS_OF = date(2026, 10, 10)
ZHANGKUN_TENURE_DAYS = 5125.0
#: F10 实测锚点：张坤在 110011 的任职起始日（用于 ±1 天容差断言）
ZHANGKUN_F10_START = date(2012, 9, 28)


@pytest.fixture
def fixed_today(monkeypatch):
    """把 ``fund_manager_job`` 的 ``date.today()`` 钉在 :data:`AS_OF`。

    ## 为什么必须钉

    本文件里有两个**基准日**，它们必须同源，否则断言随运行日期整体漂移：

    - 写入侧 ``_derive_appointment_date`` 用 ``date.today()`` 反推起始日；
    - 展示档断言用固定 ``AS_OF`` 反算 ``raw = (AS_OF - appointment_date).days``。

    两者不同源时 ``raw = AS_OF - (today - tenure_days)``：today 与 AS_OF 同日时偏差 0，
    晚一天偏 1（仍在 ±1 容差内），**晚两天起就红**。

    ⚠️ 这颗雷已引爆：2026-10-12 起本文件在**干净库**上稳定失败（``raw=5123`` vs
    ``5125``，差 2）。本机开发库之所以一直绿，是旧记录走了 ``_save_data`` 的
    「非 NULL 就不覆盖」分支、保留了两天前写入的起始日，恰好把漂移藏住了——
    **脏数据掩盖了时间炸弹**，CI 干净库当天就照了出来。

    故凡断言「起始日 / raw / 展示年限」的用例都挂这个夹具；只关心链路是否接得上的
    场景则不需要。
    """

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return cls(AS_OF.year, AS_OF.month, AS_OF.day)

    monkeypatch.setattr(fm_job, 'date', _FixedDate)
    return AS_OF


def _make_job(db):
    job = FundManagerSyncJob.__new__(FundManagerSyncJob)
    job.db = db
    job.stats = {}
    return job


def _em_row(name, company, fund_code, scale, best_return, tenure_days):
    """构造一行**东财真实形态**的适配器输出（键名与 `_filter_managers` 一致）。"""
    return {
        'fund_code': fund_code,
        'name': name,
        'company': company,
        'sum_scale': scale,
        'best_return': best_return,
        'tenure_days': tenure_days,
    }


def test_derived_start_is_within_one_day_of_f10_anchor():
    """反推的首次任职日必须落在 F10 锚点 ±1 天内。

    **为什么是±1 天而不是精确相等**：反推基准日取 ``date.today()``，东财该字段的
    统计截止日未知（T 日或 T-1）。实测跨零点重跑会让结果整体偏移一天，
    故硬编码日期会在特定日期假红 —— 那是测试写错，不是代码错。
    """
    for base in (date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 9)):
        got = FundManagerSyncJob._derive_appointment_date({'tenure_days': ZHANGKUN_TENURE_DAYS}, today=base)
        assert got is not None
        assert abs((got - ZHANGKUN_F10_START).days) <= 1, f'基准日 {base} 反推得 {got}，超出 ±1 天'


def test_full_chain_from_em_row_to_display_text(fixed_today):
    """东财一行 → 落库 → 展示文本，端到端打通。"""
    rows = [
        _em_row('张坤', '易方达基金管理有限公司', '005827', 307.94, 297.54, ZHANGKUN_TENURE_DAYS),
        _em_row('张坤', '易方达基金管理有限公司', '110011', 307.94, 297.54, ZHANGKUN_TENURE_DAYS),
    ]

    with closing(market_session_factory()()) as db:
        job = _make_job(db)
        job._save_data(job._validate_data(rows))

    with closing(market_session_factory()()) as db:
        p = build_manager_profile(db, _mgr_code_of(db, '张坤'), as_of=AS_OF)

    # 原始档：东财值原样落库
    assert p['sum_scale'] == 307.94
    assert p['best_return'] == 297.54
    # 起始日 = **抓取日** − tenure_days。抓取日已由 `fixed_today` 钉在 AS_OF，
    # 于是反推值应**逐日等于** F10 实测锚点 —— 不再需要 ±1 天容差。那层容差原本是
    # 为容忍「写入侧 today 与断言侧 AS_OF 不同源」造成的整段漂移（见 `fixed_today`
    # 的 docstring），基准同源后漂移本身不存在了，留着只会把真偏移放过。
    stored = date.fromisoformat(p['appointment_date'])
    assert stored == ZHANGKUN_F10_START, f'反推起始日 {stored} ≠ F10 锚点 {ZHANGKUN_F10_START}'

    # 展示档：换算 + 口径元数据齐备
    td = p['tenure_display']
    assert td is not None
    # 展示文本与 F10 口径对齐（同样按 ±1 天容差断言，避免跨零点假红）
    assert td['text'].startswith('14 年')
    assert td['basis'] == 'em_days_derived'
    # 溯源值可重建（由起始日反算回天数），误差在 ±1 天内 —— 见模块 docstring 精度边界
    assert td['raw'] is not None
    assert abs(td['raw'] - ZHANGKUN_TENURE_DAYS) <= 1, f'raw={td["raw"]} 与原始天数 {ZHANGKUN_TENURE_DAYS} 偏差过大'

    assert p['scale_display']['text'] == '307.94 亿元'
    assert p['best_return_display']['text'] == '+297.54%'
    for d in (p['scale_display'], p['best_return_display'], td):
        assert 'basis' in d and d['basis']


def test_tenure_grows_but_start_date_frozen():
    """不变量：起始日**冻结**，而展示年限随基准日增长。

    这正是「存日期不存天数」的核心收益 —— 若存天数，``start_date`` 会每次同步都变。
    """
    rows = [_em_row('冻结经理', '某某基金管理有限公司', '005827', 10.0, 20.0, 3650.0)]
    with closing(market_session_factory()()) as db:
        job = _make_job(db)
        job._save_data(job._validate_data(rows))

    with closing(market_session_factory()()) as db:
        code = _mgr_code_of(db, '冻结经理')
        early = build_manager_profile(db, code, as_of=date(2026, 10, 10))
        late = build_manager_profile(db, code, as_of=date(2027, 10, 10))

    assert early['appointment_date'] == late['appointment_date']  # 事实冻结
    assert early['tenure_display']['years'] < late['tenure_display']['years']  # 解读增长


def test_multi_row_same_manager_deduped_to_single_record():
    """同一经理多行（005827/110011）只落一行，规模不翻倍。

    东财这两行的规模/回报完全相同，若不去重会把307.94 写成两行或相加。
    """
    rows = [
        _em_row('去重经理', '某某基金管理有限公司', '005827', 100.5, 50.25, 2000.0),
        _em_row('去重经理', '某某基金管理有限公司', '110011', 100.5, 50.25, 2000.0),
    ]
    with closing(market_session_factory()()) as db:
        job = _make_job(db)
        job._save_data(job._validate_data(rows))

    with closing(market_session_factory()()) as db:
        code = _mgr_code_of(db, '去重经理')
        assert db.query(Manager).filter(Manager.mgr_code == code).count() == 1
        p = build_manager_profile(db, code, as_of=AS_OF)

    assert p['sum_scale'] == 100.5  # 不是 201.0
    assert p['scale_display']['text'] == '100.50 亿元'


def test_negative_best_return_carries_sign():
    """负回报必须带负号（前端靠符号选跌色，去掉符号就会显示成涨）。"""
    rows = [_em_row('负回报经理', '某某基金管理有限公司', '005827', 50.0, -18.52, 900.0)]
    with closing(market_session_factory()()) as db:
        job = _make_job(db)
        job._save_data(job._validate_data(rows))

    with closing(market_session_factory()()) as db:
        p = build_manager_profile(db, _mgr_code_of(db, '负回报经理'), as_of=AS_OF)

    assert p['best_return_display']['text'] == '-18.52%'
    assert p['best_return_display']['value'] < 0


def test_chain_survives_missing_optional_columns():
    """东财给 None 的列（实测有值但仍可能缺）→ 一致降级，不产出假数据。"""
    rows = [_em_row('缺列经理', '某某基金管理有限公司', '005827', None, None, None)]
    with closing(market_session_factory()()) as db:
        job = _make_job(db)
        job._save_data(job._validate_data(rows))

    with closing(market_session_factory()()) as db:
        code = _mgr_code_of(db, '缺列经理')
        p = build_manager_profile(db, code, as_of=AS_OF)

    assert p['sum_scale'] is None
    assert p['appointment_date'] is None
    # 三档展示全部 None —— 前端统一降级「—」
    assert p['scale_display'] is None
    assert p['best_return_display'] is None
    assert p['tenure_display'] is None


def test_dedup_keeps_existing_manager_so_profile_can_be_backfilled():
    """存量经理行必须能沿流水线被回填 —— 这是 #1970 扩展的原始诉求。

    ⚠️ 走的是**真实流水线三步**（`_validate_data` → `_deduplicate` → `_save_data`），
    不是直接调 `_save_data`：bug 恰好出在 `_deduplicate` 那一步，
    只测 `_save_data` 是测不到的 —— 这正是它上线时漏网的原因。

    实测 bug（2026-10-11）：基类 `_deduplicate_by_unique_key` 把「库里**已存在**的
    `mgr_code`」整批丢掉 → `_save_data` 拿不到存量经理 →
    `_backfill_manager_profile` 空转 → 生产库 4267 行三列永远是 NULL。
    现象：`pdm run sync --job fund_manager --full-sync --targets …` 报 success，
    而 `select count(*) from managers where sum_scale is not null` 仍是 **0**。

    ⚠️ 种子姓名必须是本文件独有的合成值（`回填经理`）——本文件的测试不走 `app`
    夹具，写入落在**整轮测试共享的那个库**上，用真名（如「张坤」）会串到别的用例。
    """
    rows = [_em_row('回填经理', '回填基金管理有限公司', '005827', 123.45, 67.89, 3650.0)]

    with closing(market_session_factory()()) as db:
        job = _make_job(db)
        validated = job._validate_data(rows)
        code = validated[0]['mgr_code']
        # 先造一行「已存在但档案全空」的经理 —— 模拟生产库的存量行
        db.add(Manager(mgr_code=code, name='回填经理'))
        db.commit()

        # 真实流水线的第 3、4 步
        job._save_data(job._deduplicate(validated))

    with closing(market_session_factory()()) as db:
        p = build_manager_profile(db, code, as_of=AS_OF)

    assert p['sum_scale'] == 123.45, '存量经理的规模没被回填（_deduplicate 把它丢了？）'
    assert p['best_return'] == 67.89
    assert p['appointment_date'] is not None


def _mgr_code_of(db, name):
    """按姓名取 mgr_code（仅测试用；生产代码严禁按姓名检索，库内 119 组重名）。"""
    m = db.query(Manager).filter(Manager.name == name).first()
    assert m is not None, f'库中未找到 {name}'
    return m.mgr_code
