# -*- coding: utf-8 -*-
"""core 层依赖边界测试（#1607）。

分层规则（`docs/spec/decisions.md` 2026-09-19 决策行）：

    core ← domains.models ← services ← domains.<域>.views

core 是业务无关的基础设施层，**不得** import `app.domains.*` / `app.models.*`。
本文件把该边界钉进 pytest（与 `scripts/guard_core_imports.py` 同一份判定逻辑，
不重复实现）：本地跑 `pytest` 即可发现回潮，不必等 CI 守卫。

同时覆盖两条配套不变量：
- 身份实现必须由组合根注入，未注入时**报错**而不是静默放行（安全缺口）；
- 默认家庭/用户种子幂等（重复播种不产生重复行）。
"""

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CORE_DIR = _REPO_ROOT / 'backend' / 'app' / 'core'
_GUARD_PATH = _REPO_ROOT / 'scripts' / 'guard_core_imports.py'


def _load_guard():
    """按路径加载仓库根的守卫脚本（复用其判定逻辑，避免两处规则漂移）。"""
    spec = importlib.util.spec_from_file_location('guard_core_imports', _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_core_layer_has_zero_domain_imports():
    """`app/core/**` 除注释外零 `from app.domains` / `from app.models` 引用（#1607 验收项）。"""
    guard = _load_guard()
    violations = guard.scan_core(_CORE_DIR)
    assert violations == [], 'core 反向依赖领域层：\n' + '\n'.join(violations)


def test_guard_detects_violation_in_probe_dir(tmp_path):
    """灵敏度验证：守卫对违规样本必须报错（防「永远返回空」的假绿）。"""
    guard = _load_guard()
    probe = tmp_path / 'core'
    probe.mkdir()
    (probe / 'bad.py').write_text(
        'from app.domains.users.models import User\nimport app.models.sync_log  # noqa: F401\n',
        encoding='utf-8',
    )
    (probe / 'good.py').write_text('from app.core.money import Money\n', encoding='utf-8')

    violations = guard.scan_core(probe)
    assert len(violations) == 2
    assert 'app.domains.users.models' in violations[0]
    assert 'app.models.sync_log' in violations[1]


def test_create_app_injects_identity_provider(app):
    """组合根必须注入身份实现（漏注入会让鉴权中间件在首个请求上抛错）。"""
    from app.core import auth as auth_mod
    from app.domains.users.identity import UserIdentity

    assert auth_mod._user_identity is UserIdentity


def test_auth_fails_loud_without_injected_identity(app, monkeypatch):
    """未注入身份实现 → 显式报错，不静默降级（鉴权链路上的静默降级等于安全缺口）。"""
    from app.core import auth as auth_mod
    from app.core.database import SessionLocal

    monkeypatch.setattr(auth_mod, '_user_identity', None)

    with pytest.raises(RuntimeError, match='register_user_identity'):
        auth_mod._identity()

    # 请求路径上同样必须失败（而不是被当成「未登录」返回 401 或误放行）
    with app.test_request_context('/api/assets/'):
        with pytest.raises(RuntimeError, match='register_user_identity'):
            auth_mod._resolve_user(SessionLocal())


def test_seed_default_identity_is_idempotent(app):
    """默认家庭 1 / 默认用户 1 重复播种不产生重复行（#1607 移交后行为不变）。"""
    from app.core.database import SessionLocal
    from app.domains.families.models import Family
    from app.domains.users.models import User
    from app.domains.users.seed import seed_default_identity

    # app fixture 已由 create_app 播种一次，这里再跑两次验证幂等
    seed_default_identity()
    seed_default_identity()

    with SessionLocal() as session:
        assert session.query(Family).filter_by(id=1).count() == 1
        assert session.query(User).filter_by(id=1).count() == 1
