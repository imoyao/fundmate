# -*- coding: utf-8 -*-
"""后端分层依赖方向测试（#1607）。

分层规则（`docs/spec/decisions.md` 2026-09-19 行 D24、`architecture.md` §6）：

    core ← domains.{models,schemas} ← services ← domains.{views}

本文件把四条**非法边**（R1~R4）钉进 pytest，与 `scripts/guard_layer_direction.py`
共用同一份判定逻辑（按路径加载脚本，不重复实现）——本地跑 `pytest` 即可发现回潮，
不必等 CI 守卫。

参数化用例覆盖「每条规则都能报错」的**灵敏度**（防「永远返回空」的假绿），
以及三条**合法边**的反向保护（防守卫收得过紧把正常写法判红）。
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
    # ── 合法边（反向保护）：以下写法必须放行 ──
    ('domains/ledgers/views.py', 'from app.services.position_presenter import enrich_position_dict\n', None),
    ('domains/positions/views.py', 'from app.domains.positions.schemas import PositionOut\n', None),
    ('services/probe_src.py', 'from app.domains.positions.models import Position\n', None),
    ('domains/positions/models.py', 'from app.core.database import Base\n', None),
    ('domains/assets/views.py', 'from app.domains.ledgers.models import Ledger\n', None),
    ('core/probe_src.py', 'from app.core.money import Money\n', None),
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
