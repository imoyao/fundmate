# -*- coding: utf-8 -*-
"""身份读写注入与默认身份种子的回归测试（#1607 批次 1）。

批次 1 把 core 反向依赖切断后，两条契约必须由测试守住（原合并在
`test_core_layer_boundary.py`，批次 2 按主题拆出本文件）：

1. **注入契约**：`create_app()` 必须注入身份实现；未注入时鉴权链路**报错**而非静默降级
   （鉴权链路上的静默降级等于安全缺口）；
2. **种子幂等**：默认家庭 1 / 默认用户 1 重复播种不产生重复行（种子从 core 移到
   `domains/users/seed.py` 后行为不变）。
"""

import pytest


def test_create_app_injects_identity_provider(app):
    """组合根必须注入身份实现（漏注入会让鉴权中间件在首个请求上抛错）。"""
    from app.core import auth as auth_mod
    from app.domains.users.identity import UserIdentity

    assert auth_mod._user_identity is UserIdentity


def test_auth_fails_loud_without_injected_identity(app, monkeypatch):
    """未注入身份实现 → 显式报错，不静默降级。"""
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
    """默认家庭 1 / 默认用户 1 重复播种不产生重复行。"""
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
