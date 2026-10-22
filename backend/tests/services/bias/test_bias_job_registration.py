# -*- coding: utf-8 -*-
"""BiasJob 注册进同步编排器的「接线」测试（#2494）。

## 为什么这份测试的重点是接线

故障形态与 #2082（manager_tenure）同族：**不是算错了，而是「到不了」**。
`BiasJob` 写得很完整（逐标的失败明细、全挂判 FAILED 都有测试钉着），但编排器里
没有 'bias' 这个键 ⇒ `pdm run sync --job bias` 报「未知任务」，乖离率只能靠
`temperature` 内联跑，**无法单独补跑**、也没有自己的 `sync_logs` 行。

所以本文件断言的是「接线在不在」，以及「接线的方式对不对」——后者更要紧。

## 为什么大部分用 AST 静态解析

`import app.services.sync.orchestrator` 会连带拉起 akshare / py_mini_racer，
CI 里跑不动。与 `tests/services/sync/test_manager_tenure_job.py` 同一手法。

## 三条口径防线（按重要性排序）

1. **注册**：`orchestrator.jobs` 含 'bias'；
2. **不调度**：在 `_NOT_SCHEDULED` 里，且 **不在** `_JOB_TEMPLATES`（一天算两遍）；
3. **不吃目标池**：不在 `DB_POOL_JOBS` —— 这条最反直觉，理由见最后一个用例：
   `BiasJob._fetch_data` 完全不读 targets，一旦被注入目标池，基类会按 batch_size
   分批、每批重算全量 37 个标的，在东财限流下就是封禁风险。
"""

import ast
from datetime import date
from pathlib import Path

import pytest

from app.services.adapters.null_adapter import NullAdapter
from app.services.bias.calculator import BiasCalculator
from app.services.bias.job import BiasJob
from app.services.bias.provider import ProductProvider
from app.services.bias.schemas import BiasResult

BACKEND_DIR = Path(__file__).resolve().parents[3]
ORCHESTRATOR_PY = BACKEND_DIR / 'app' / 'services' / 'sync' / 'orchestrator.py'
SCHEDULER_PY = BACKEND_DIR / 'app' / 'services' / 'daily_scheduler.py'
SYNC_METADATA_PY = BACKEND_DIR / 'app' / 'tools' / 'sync_metadata.py'


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding='utf-8'), filename=str(path))


def _registered_job_names() -> set:
    """AST 静态抽出 orchestrator 里 `self.jobs['x'] = ...` 的注册名。"""
    names = set()
    for node in ast.walk(_parse(ORCHESTRATOR_PY)):
        if not isinstance(node, ast.Assign):
            continue
        tgt = node.targets[0]
        if isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Attribute) and tgt.value.attr == 'jobs':
            if isinstance(tgt.slice, ast.Constant) and isinstance(tgt.slice.value, str):
                names.add(tgt.slice.value)
    return names


def _module_value(tree: ast.Module, var_name: str):
    """取模块级变量赋值右值，兼容 Assign 与带注解的 AnnAssign。

    两张调度表都是**带类型标注**的（`_JOB_TEMPLATES: Tuple[...] = (...)` /
    `_NOT_SCHEDULED: Dict[...] = {...}`），在 AST 里是 AnnAssign——
    只认 Assign 会一条都抓不到、断言恒失败。
    """
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == var_name:
                return node.value
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == var_name for t in node.targets):
                return node.value
    return None


def _scheduled_and_unscheduled() -> tuple:
    """从 daily_scheduler 抽出「每日调度」与「明确不调度」两张表的 job 名。"""
    tree = _parse(SCHEDULER_PY)
    scheduled: set = set()
    unscheduled: dict = {}

    templates = _module_value(tree, '_JOB_TEMPLATES')
    if isinstance(templates, ast.Tuple):
        for elt in templates.elts:
            if isinstance(elt, ast.Tuple) and elt.elts:
                first = elt.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    scheduled.add(first.value)

    table = _module_value(tree, '_NOT_SCHEDULED')
    if isinstance(table, ast.Dict):
        for k, v in zip(table.keys, table.values):
            if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
                continue
            # 值是 (理由, 频率) 二元组：理由必须非空，否则「不调度」没有依据
            reason = ''
            if isinstance(v, ast.Tuple) and v.elts:
                first = v.elts[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    reason = first.value
            unscheduled[k.value] = reason
    return scheduled, unscheduled


def _db_pool_jobs() -> set:
    """AST 抽出 `sync_metadata.DB_POOL_JOBS` 的键（CLI 会为这些 job 注入库内目标池）。"""
    tree = _parse(SYNC_METADATA_PY)
    value = _module_value(tree, 'DB_POOL_JOBS')
    names = set()
    if isinstance(value, ast.Dict):
        for k in value.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                names.add(k.value)
    return names


# ── 接线：注册 ──


def test_bias_is_registered_in_orchestrator():
    """`bias` 必须真的注册进 orchestrator —— 否则仍然「未知任务」、无法单独补跑。"""
    assert 'bias' in _registered_job_names(), 'job 未注册：--job bias 仍然不可用'


# ── 口径：只注册、不调度 ──


def test_bias_is_declared_as_not_scheduled():
    """注册了就必须被调度覆盖表收走，且本 job 收在「明确不调度」里（#1934 守门）。

    留在本表还必须写清理由——表头就是这么要求的，理由是「不调度」的依据。
    """
    _, unscheduled = _scheduled_and_unscheduled()
    assert 'bias' in unscheduled, 'job 已注册但没被调度覆盖表收走，守门会红'
    assert unscheduled['bias'].strip(), '「不调度」必须写理由，否则与漏登记同形'


def test_bias_is_not_in_daily_schedule():
    """本 job **不进每日调度**：日常已由 temperature 内联执行。

    进每日调度 ⇒ 同一天算两遍（每遍 37 个标的 × 约 3s 间隔），纯属重复打上游。
    摘掉内联、改由本 job 独立供数属另一方案（探市数据来源切换），另开卡。
    """
    scheduled, _ = _scheduled_and_unscheduled()
    assert 'bias' not in scheduled, 'bias 进了每日调度：与 temperature 内联重复执行'


# ── 口径：不吃目标池 ──


def test_bias_is_not_in_db_pool_jobs():
    """`bias` 不得进 `DB_POOL_JOBS`：CLI 会为其中的 job 注入库内核心池。

    这是本卡设计问题 ①的**真正防线**。注入目标池后 `run()` 走分批分支，
    每批各调一次 `_fetch_data`，而它不读 targets ⇒ 每批都重算全量。
    """
    assert 'bias' not in _db_pool_jobs(), 'bias 被注入目标池：分批会重复全量计算（限流风险）'


# ── 行为：上面那条防线成立的前提 ──


@pytest.fixture
def products():
    return [
        ('000300', 'index', '沪深300'),
        ('000905', 'index', '中证500'),
        ('801010', 'industry', '农林牧渔'),
    ]


def _bias_result(symbol: str, item_type: str, name: str) -> BiasResult:
    return BiasResult(
        item_type=item_type,
        item_code=symbol,
        item_name=name,
        close=4000.0,
        bias=10.0,
        ema20=3900.0,
        label='高位区(绿卖)',
        position=70.0,
        position_label='高位区(绿卖)',
        data_date=date.today(),
        stale=False,
    )


def test_fetch_data_ignores_targets_so_target_pool_must_stay_none(db, monkeypatch, products):
    """`_fetch_data` 不消费 targets ⇒ 目标池只能是 None（job 自取全量）。

    这是「不挂 target_kind / 不进 DB_POOL_JOBS」两条静态断言的**前提**。
    一旦有人让 `_fetch_data` 真的按 targets 过滤，挂目标池就变成正确做法，
    上面两条断言也随之失效——本用例会先转红，逼改的人同步更新口径，
    而不是等它在生产上把 37 个标的按批次数放大成限流事故。

    判据：传 1 个 targets，仍按 provider 的全量清单（3 个标的）计算。
    """
    job = BiasJob(NullAdapter(), db)
    job.request_interval = 0.0
    monkeypatch.setattr(ProductProvider, 'get_default_list', staticmethod(lambda: products))
    monkeypatch.setattr(
        BiasCalculator,
        'calculate_item',
        lambda self, symbol, item_type, name, data_date=None: _bias_result(symbol, item_type, name),
    )

    records = job._fetch_data(False, ['000300'])

    assert len(records) == len(products), 'targets 被消费了：目标池口径需要同步更新'
    assert job.stats['total'] == len(products)
