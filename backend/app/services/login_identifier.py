# -*- coding: utf-8 -*-
"""登录标识解析（D10 / #2764）：把「邮箱 或 用户名」收敛为规范邮箱。

Supabase Auth 原生只支持「邮箱/手机号 + 密码」，用户名登录靠这里先解析成邮箱。
规则放 service 而不是视图：解析口径是业务规则，视图只该做「入参 → 调服务 → 组响应」
（视图厚度基线见 `scripts/check_view_thickness.py`，#1606）。

三个口径缺一个就会让某类用户登不进去：

- **大小写**：邮箱与用户名都按 ``lower()`` 匹配。Supabase 侧邮箱一律小写，本地可能留着
  注册时的原始大小写，按字面量比较会 404（同一份数据两种口径）。
- **歧义不静默**：用户名命中多行 → 409，而不是取 id 最小那条。旧行为把「同一用户名
  指向两个账号」藏了起来，被顶掉的那个人只看到「密码错误」，永远查不到原因。
- **邮箱多行**：同一邮箱无论取哪行，最终登录的都是同一个 Supabase 账号，不存在顶号，
  故按 id 最小解析并打 WARNING（提示清理跨项目幽灵行，见 `scripts/diagnose_ghost_users.py`）。
"""

from loguru import logger
from sqlalchemy import func

from app.core.exceptions import ErrorCode, SBException
from app.domains.users.models import User


def resolve_login_identifier(db, identifier: str) -> str:
    """返回规范邮箱；标识为空 → 400，不存在 → 404，用户名歧义 → 409。"""
    ident = (identifier or '').strip()
    if not ident:
        raise SBException(
            code=ErrorCode.INVALID_PARAMS.code,
            message='登录标识不能为空',
            status_code=ErrorCode.INVALID_PARAMS.http_status,
        )

    is_email = '@' in ident
    column = User.email if is_email else User.username
    users = db.query(User).filter(func.lower(column) == ident.lower()).order_by(User.id.asc()).all()

    if not users:
        raise SBException(
            code=ErrorCode.RESOURCE_NOT_FOUND.code,
            message='未找到该邮箱或用户名，请检查后重试',
            status_code=ErrorCode.RESOURCE_NOT_FOUND.http_status,
        )
    if len(users) > 1 and not is_email:
        logger.warning(
            '登录标识歧义：username={} 命中 {} 行（id={}），拒绝解析（#2764）',
            ident,
            len(users),
            [u.id for u in users],
        )
        raise SBException(
            code=ErrorCode.DUPLICATE_ENTRY.code,
            message='该用户名对应多个账号，请改用邮箱登录',
            status_code=ErrorCode.DUPLICATE_ENTRY.http_status,
        )
    if len(users) > 1:
        logger.warning(
            '同一邮箱命中多行（id={}），按 id 最小解析；建议清理跨项目幽灵行（#2764）',
            [u.id for u in users],
        )
    return users[0].email
