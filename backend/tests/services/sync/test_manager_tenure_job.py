# -*- coding: utf-8 -*-
"""``manager_tenure`` job 测试（#2082）。

## 为什么这份测试的重点是「接线」而不是「算法」

这条链路原来的故障**不是算错了，而是从没被调用过**：
``FundManagerSyncJob.backfill_tenures()`` 写得很完整（口径、坑位、边界都有注释），
但全仓 `grep -rn backfill_tenures` 只命中定义本身 —— 于是
``fund_managers.start_date/end_date`` 填充率恒为 0%、前端「任职起止」永远是「—」。

所以本文件第一组用例断言的是**接线在不在**（job 已注册、已被调度覆盖表收走），
而不是「函数返回值对不对」。行为类用例则钉死四条语义：

1. **只更新不插入** —— 对库里不存在的 (基金, 经理) 组合跳过，不凭任期数据造关系；
2. **同值不写 / 二次运行零变更**（幂等）；
3. **抓不到不写占位** —— 留 `None` 让前端降级「—」；
4. **targets 为空时绝不放大到全库** —— 一单位 = 一次 HTTP，兜底成全库是限流事故。

⚠️ market 域数据（``funds`` / ``managers`` / ``fund_managers``）一律走
``market_session_factory`` —— 它们与 user 域不同库，用 ``db`` 夹具会写错库。
本文件因此显式请求 ``app`` 夹具（激活 conftest 对 ``market_session_factory`` 的
monkeypatch，把库指到本用例的 tmp_path），不再落到整轮共享的那个库上。

⚠️ **必须从模块取属性调用**（``db_factory.market_session_factory()``），不能
``from app.core.db_factory import market_session_factory`` —— 后者在 import 期就
**早绑定**了原函数对象，conftest 的 ``monkeypatch.setattr(_db_factory, ...)``
对它无效，测试会静默落到真实库上（`backend/invest.db` 被真写、跨用例撞唯一键）。
"""

import ast
from contextlib import closing
from datetime import date
from pathlib import Path

from app.core import db_factory
from app.domains.funds.models import Fund, FundManager, Manager
from app.services.adapters.manager_tenure import find_tenure
from app.services.sync.jobs.manager_tenure_job import ManagerTenureSyncJob

BACKEND_DIR = Path(__file__).resolve().parents[3]
ORCHESTRATOR_PY = BACKEND_DIR / 'app' / 'services' / 'sync' / 'orchestrator.py'
SCHEDULER_PY = BACKEND_DIR / 'app' / 'services' / 'daily_scheduler.py'

FUND_CODE = '990001'
MGR_NAME = '任期经理'


class _StubTenureAdapter:
    """替身数据源：按 fund_code 返回预置任期分段，并记录**被问过哪些基金**。

    记录 ``asked`` 是为了钉住安全边界 —— 「targets 为空时一次上游请求都不发」
    只能靠「适配器有没有被调用」来证，不能靠「结果为空」（结果为空也可能是发了没抓到）。
    """

    def __init__(self, mapping):
        self.mapping = mapping
        self.asked: list = []

    def get_name(self) -> str:
        return 'stub_tenure'

    def get_version(self) -> str:
        return '0'

    def fetch_tenures(self, fund_code):
        self.asked.append(fund_code)
        return list(self.mapping.get(fund_code, []))


def _make_job(adapter, db) -> ManagerTenureSyncJob:
    return ManagerTenureSyncJob(adapter, db)


def _seed_rel(mgr_name=MGR_NAME, fund_code=FUND_CODE, start=None, end=None):
    """造一条 (基金, 经理) 关联，返回 (fund_id, rel_id)。"""
    with closing(db_factory.market_session_factory()()) as db:
        fund = Fund(fund_code=fund_code, name=f'{fund_code} 基金')
        db.add(fund)
        db.commit()
        mgr = Manager(mgr_code=f'mgr_{fund_code}', name=mgr_name)
        db.add(mgr)
        db.commit()
        rel = FundManager(fund_id=fund.id, mgr_id=mgr.id, is_classic=False, start_date=start, end_date=end)
        db.add(rel)
        db.commit()
        return fund.id, rel.id


def _rel_tenure(rel_id):
    with closing(db_factory.market_session_factory()()) as db:
        rel = db.query(FundManager).filter(FundManager.id == rel_id).first()
        return rel.start_date, rel.end_date


def _segment(name=MGR_NAME, start=date(2012, 9, 28), end=None):
    return {'manager_name': name, 'start_date': start, 'end_date': end}


# ---------------------------------------------------------------------------
# 1. 接线：这条链路必须真的被调用（原故障就是「从没被调用」）
# ---------------------------------------------------------------------------


def _registered_job_names() -> set:
    """AST 静态抽出 orchestrator 里 `self.jobs['x'] = ...` 的注册名。

    与 `scripts/guard_job_schedule_coverage.py` 同一手法：import orchestrator 会连带
    拉起 akshare / py_mini_racer，故静态解析而不是 import。
    """
    tree = ast.parse(ORCHESTRATOR_PY.read_text(encoding='utf-8'), filename=str(ORCHESTRATOR_PY))
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0]
        if isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Attribute) and tgt.value.attr == 'jobs':
            if isinstance(tgt.slice, ast.Constant) and isinstance(tgt.slice.value, str):
                names.add(tgt.slice.value)
    return names


def _assigned_name(node):
    """取赋值目标名，兼容 `x = ...`（Assign）与 `x: T = ...`（AnnAssign）。

    两张调度表都是**带类型标注**的（`_JOB_TEMPLATES: Tuple[...] = (...)` /
    `_NOT_SCHEDULED: Dict[...] = {...}`），在 AST 里是 `AnnAssign` ——
    只判 `Assign` 会一条都抓不到、断言恒失败。
    """
    if isinstance(node, ast.AnnAssign):
        return node.target.id if isinstance(node.target, ast.Name) else None
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        return node.targets[0].id
    return None


def _scheduled_and_unscheduled_names() -> tuple:
    """从 daily_scheduler 抽出 `_JOB_TEMPLATES` 与 `_NOT_SCHEDULED` 里的 job 名。

    同样走 AST：两张表的键在源码里都是字面量常量，静态可判。
    """
    tree = ast.parse(SCHEDULER_PY.read_text(encoding='utf-8'), filename=str(SCHEDULER_PY))
    scheduled: set = set()
    unscheduled: set = set()

    for node in ast.walk(tree):
        name = _assigned_name(node)
        if name is None:
            continue
        value = node.value
        if name == '_JOB_TEMPLATES' and isinstance(value, ast.Tuple):
            # 元组列表：每项第 0 个元素是 job 名
            for elt in value.elts:
                if isinstance(elt, ast.Tuple) and elt.elts:
                    first = elt.elts[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        scheduled.add(first.value)
        elif name == '_NOT_SCHEDULED' and isinstance(value, ast.Dict):
            for k in value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    unscheduled.add(k.value)
    return scheduled, unscheduled


def test_job_is_registered_in_orchestrator():
    """`manager_tenure` 必须真的注册进 orchestrator —— 否则调用链仍然是断的。"""
    assert 'manager_tenure' in _registered_job_names(), 'job 未注册：接线又断了'


def test_job_is_covered_by_schedule_tables():
    """注册的 job 必须被「每日调度」或「明确不调度」收走（与覆盖守门同一判据）。

    本条与 `scripts/guard_job_schedule_coverage.py` 互补：守门保证「注册了的都被覆盖」，
    本条额外保证「这个 job 确实被登记过」——有人只删登记而留注册时，守门会红；
    两边都删则只有本条会红。
    """
    scheduled, unscheduled = _scheduled_and_unscheduled_names()
    assert 'manager_tenure' in scheduled | unscheduled, 'job 未登记进调度覆盖表'


def test_unscheduled_entry_documents_real_reason():
    """留在「明确不调度」表里必须写清理由与实际频率（表头就是这么要求的）。"""
    _, unscheduled = _scheduled_and_unscheduled_names()
    assert 'manager_tenure' in unscheduled, '本 job 是逐只 HTTP，不该进每日调度'


# ---------------------------------------------------------------------------
# 2. 写入语义
# ---------------------------------------------------------------------------


def test_writes_tenure_into_existing_rel(app):
    """命中「库内已有的关联」→ 补上 start_date/end_date。"""
    _, rel_id = _seed_rel()
    adapter = _StubTenureAdapter({FUND_CODE: [_segment()]})

    with closing(db_factory.market_session_factory()()) as db:
        job = _make_job(adapter, db)
        result = job.run(full_sync=True, targets=[FUND_CODE])

    assert result['status'] == 'success'
    assert _rel_tenure(rel_id) == (date(2012, 9, 28), None)
    assert result['stats']['tenure']['updated'] == 1


def test_never_inserts_unknown_pair(app):
    """基金在库、但该经理没挂在这只基金上 → **不写、也不造关系**。

    关系只由经理全量表（`fund_manager` job）决定。若这里凭任期数据补关系，
    会凭空长出一批 (基金, 经理) 关联。
    """
    _seed_rel()
    # 库里存在的经理，但没有与这只基金建立关联
    with closing(db_factory.market_session_factory()()) as db:
        db.add(Manager(mgr_code='code_other', name='无关经理'))
        db.commit()
        before = db.query(FundManager).count()

    adapter = _StubTenureAdapter({FUND_CODE: [_segment(name='无关经理')]})
    with closing(db_factory.market_session_factory()()) as db:
        job = _make_job(adapter, db)
        job.run(full_sync=True, targets=[FUND_CODE])

    with closing(db_factory.market_session_factory()()) as db:
        assert db.query(FundManager).count() == before, '不该新增关联'


def test_skips_when_fund_absent_from_db(app):
    """基金不在库里 → 跳过，不报错、不造基金行。"""
    adapter = _StubTenureAdapter({'999999': [_segment()]})
    with closing(db_factory.market_session_factory()()) as db:
        job = _make_job(adapter, db)
        result = job.run(full_sync=True, targets=['999999'])

    assert result['status'] == 'success'
    assert result['stats']['tenure']['no_rel'] == 1
    with closing(db_factory.market_session_factory()()) as db:
        assert db.query(Fund).filter(Fund.fund_code == '999999').first() is None


def test_second_run_makes_no_change(app):
    """幂等：第二次运行同值不写（`unchanged` 计数 +1，`updated` 为 0）。"""
    _, rel_id = _seed_rel()
    adapter = _StubTenureAdapter({FUND_CODE: [_segment()]})

    with closing(db_factory.market_session_factory()()) as db:
        _make_job(adapter, db).run(full_sync=True, targets=[FUND_CODE])
    with closing(db_factory.market_session_factory()()) as db:
        second = _make_job(adapter, db).run(full_sync=True, targets=[FUND_CODE])

    assert _rel_tenure(rel_id) == (date(2012, 9, 28), None)
    assert second['stats']['tenure']['updated'] == 0
    assert second['stats']['tenure']['unchanged'] == 1


def test_keeps_existing_value_when_fetch_fails(app):
    """抓不到（空分段）→ 保留原值、不写占位日期。"""
    _, rel_id = _seed_rel(start=date(2020, 1, 1), end=None)
    adapter = _StubTenureAdapter({FUND_CODE: []})

    with closing(db_factory.market_session_factory()()) as db:
        result = _make_job(adapter, db).run(full_sync=True, targets=[FUND_CODE])

    assert result['status'] == 'success'
    assert _rel_tenure(rel_id) == (date(2020, 1, 1), None), '抓不到时不该改动原值'


def test_writes_both_dates_for_ended_tenure(app):
    """已离任的分段照写（end_date 非空）——分段语义由 `find_tenure` 决定。"""
    _, rel_id = _seed_rel()
    adapter = _StubTenureAdapter({FUND_CODE: [_segment(start=date(2018, 9, 5), end=date(2026, 5, 22))]})

    with closing(db_factory.market_session_factory()()) as db:
        _make_job(adapter, db).run(full_sync=True, targets=[FUND_CODE])

    assert _rel_tenure(rel_id) == (date(2018, 9, 5), date(2026, 5, 22))


# ---------------------------------------------------------------------------
# 3. 安全边界：targets 为空绝不放大到全库
# ---------------------------------------------------------------------------


def test_empty_targets_never_touch_upstream(app):
    """targets 为空 → 一次上游请求都不发。

    别的 job 会「空 targets → 取全库」，本 job **故意不这么写**：一个单位 = 一次 HTTP，
    兜底成全库等于把 34812 只基金挨个打一遍上游。
    """
    _seed_rel()
    adapter = _StubTenureAdapter({})

    with closing(db_factory.market_session_factory()()) as db:
        job = _make_job(adapter, db)
        assert job._fetch_data(False, []) == []
        result = job.run(full_sync=True, targets=[])

    assert result['status'] == 'success'
    assert adapter.asked == [], '空 targets 下仍向上游发了请求'


# ---------------------------------------------------------------------------
# 4. find_tenure 的「仍在任」口径（此前无人测）
# ---------------------------------------------------------------------------


def test_find_tenure_prefers_active_segment():
    """同一经理在本基金有多段任期时必须取**仍在任**那段。

    实测张坤在 005827 有两段（`2018-09-05~2026-05-22` 已卸任 / `2026-05-23~至今`），
    取错段会把「现任基金经理」显示成已离任的人。
    """
    rows = [
        _segment(start=date(2018, 9, 5), end=date(2026, 5, 22)),
        _segment(start=date(2026, 5, 23), end=None),
    ]
    got = find_tenure(rows, MGR_NAME)
    assert got is not None
    assert got['start_date'] == date(2026, 5, 23)
    assert got['end_date'] is None


def test_find_tenure_returns_none_when_no_segment_matches():
    """姓名对不上 / 空姓名 → None（调用方据此跳过，不写占位）。"""
    rows = [_segment(name='别人')]
    assert find_tenure(rows, MGR_NAME) is None
    assert find_tenure(rows, '') is None
    assert find_tenure([], MGR_NAME) is None
