# -*- coding: utf-8 -*-
"""后端分层依赖方向测试（#1607）。

分层规则（`docs/spec/decisions.md` 2026-09-19 行 D24、`architecture.md` §6）：

    core ← domains.{models,schemas} ← services ← domains.{views}

本文件把五条**非法边**（R1~R5）钉进 pytest，与 `scripts/guard_layer_direction.py`
共用同一份判定逻辑（按路径加载脚本，不重复实现）——本地跑 `pytest` 即可发现回潮，
不必等 CI 守卫。

参数化用例覆盖「每条规则都能报错」的**灵敏度**（防「永远返回空」的假绿）、
**合法边**的反向保护（防守卫收得过紧把正常写法判红），以及 R5 冻结基线的边界
（已登记的既有边放行、同源的其它反向边仍须报错）。
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_APP_DIR = _REPO_ROOT / 'backend' / 'app'
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_layer_direction.py'


def _load_guard():
    """按路径加载仓库根的守卫脚本（复用其判定逻辑，避免两处规则漂移）。"""
    spec = importlib.util.spec_from_file_location('guard_layer_direction', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_layer_direction_has_no_violations():
    """真实 app 目录 R1~R4 全绿（跨域 views 互引已于 #1607 批次 2 归零）。"""
    guard = _load_guard()
    violations = guard.scan_app(_APP_DIR)
    assert violations == [], '发现违反分层方向的 import：\n' + '\n'.join(violations)


# (探针相对路径, 源码, 期望命中的规则号或 None=应放行)
_PROBES = [
    # ── R1：core 反向依赖领域层 ──
    ('core/probe_src.py', 'from app.domains.users.models import User\n', 'R1'),
    ('core/probe_src.py', 'import app.models.sync_log\n', 'R1'),
    ('core/probe_src.py', "import importlib\nimportlib.import_module('app.domains.families.models')\n", 'R1'),
    # ── R2：services 依赖 domains.views ──
    (
        'services/probe_src.py',
        'from app.domains.positions.views import enrich_position_dict\n',
        'R2',
    ),
    ('services/probe_src.py', 'import app.domains.importers.e_account_views\n', 'R2'),
    # ── R3：domains 的 models / schemas 反向依赖 services ──
    ('domains/positions/models.py', 'from app.services.position_valuation import market_value_cents\n', 'R3'),
    ('domains/positions/schemas.py', 'import app.services.position_service\n', 'R3'),
    # ── R4：跨域引用对方 views ──
    ('domains/ledgers/views.py', 'from app.domains.positions.views import enrich_position_dict\n', 'R4'),
    ('domains/ledgers/views.py', 'import app.domains.importers.e_account_views\n', 'R4'),
    # ── R5：services 顶层共享件反向依赖家族包（#1607 批次 3 上提后新增） ──
    ('services/adapters/probe.py', 'from app.services.sync.company_resolver import x\n', 'R5'),
    ('services/job_base.py', 'from app.services.thermometer.fetchers import y\n', 'R5'),
    ('services/import_records.py', 'import app.services.importer.orchestrator_parse\n', 'R5'),
    # ── 合法边（反向保护）：以下写法必须放行 ──
    ('domains/ledgers/views.py', 'from app.services.position_presenter import enrich_position_dict\n', None),
    ('domains/positions/views.py', 'from app.domains.positions.schemas import PositionOut\n', None),
    ('services/probe_src.py', 'from app.domains.positions.models import Position\n', None),
    ('domains/positions/models.py', 'from app.core.database import Base\n', None),
    ('domains/assets/views.py', 'from app.domains.ledgers.models import Ledger\n', None),
    ('core/probe_src.py', 'from app.core.money import Money\n', None),
    # 家族包依赖共享件（正确方向）与同包内互引必须放行
    (
        'services/sync/company_resolver.py',
        'from app.services.adapters.eastmoney_adapter import fetch_fund_company_list\n',
        None,
    ),
    ('services/sync/jobs/probe.py', 'from app.services.job_base import SyncJob\n', None),
    ('services/adapters/probe.py', 'from app.services.adapters.base import DataSourceAdapter\n', None),
    ('services/adapters/probe.py', 'from app.domains.funds.models import FundCompany\n', None),
    # 批次 4 后：adapters 反向依赖 thermometer 已消除 → 该写法现在应报 R5（冻结基线已清空）
    (
        'services/adapters/qieman_advisor_adapter.py',
        'from app.services.thermometer.fetchers import QiemanFetcher\n',
        'R5',
    ),
    # 但同一源的**其它**反向边仍须报错（冻结基线不构成"该文件豁免"）
    (
        'services/adapters/qieman_advisor_adapter.py',
        'from app.services.sync.orchestrator import DataSyncOrchestrator\n',
        'R5',
    ),
]


@pytest.mark.parametrize('rel_path, source, expect_rule', _PROBES)
def test_guard_rule_sensitivity(tmp_path, rel_path, source, expect_rule):
    """每条规则都能报错（expect_rule 非空），合法边不被误伤（expect_rule 为空）。"""
    guard = _load_guard()
    app_dir = tmp_path / 'app'
    probe = app_dir / rel_path
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text(source, encoding='utf-8')

    violations = guard.scan_app(app_dir)
    if expect_rule is None:
        assert violations == [], f'合法边被误判：{violations}'
    else:
        assert len(violations) == 1, f'期望命中 1 条 {expect_rule}，实得 {violations}'
        assert expect_rule in violations[0]
