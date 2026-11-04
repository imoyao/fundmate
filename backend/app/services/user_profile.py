# -*- coding: utf-8 -*-
"""当前用户资料更新（`PATCH /api/users/me` 的业务规则）。

为什么在 service：敏感词校验、用户名唯一性（大小写口径 + 并发兜底）、GoTrue metadata
同步都是业务规则；视图只该做「取当前用户 → 调这里 → 组响应」（视图厚度基线见
`scripts/check_view_thickness.py`，#1606）。

用户名唯一性为什么必须在这里做三件事：

1. **判重与登录解析同口径**（``lower()``）——否则把名字改成 ``Devyao`` 就能绕过
   ``devyao`` 的占用检查，落库后两人共用同一个登录标识（#2764）；
2. **``flush()`` 捕获 ``IntegrityError`` 转 409** —— 两个请求同时通过上面的判重时，
   由 ``uq_users_username_lower`` 唯一索引兜住。对用户来说「名字被抢了」是可操作的
   （换一个），500 不是；
3. **落库成功后同步 GoTrue ``user_metadata``** —— 否则注册时写进 metadata 的旧名会
   一直留在 token 里，新设备 / 新库 JIT 建号（``identity.provision`` 读 metadata）
   会拿旧名建行，与本地权威值不一致。同步失败**不回滚改名**（本地才是权威，
   见 `app/core/supabase_admin.py` 的失败语义说明）。
"""

from loguru import logger
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core import supabase_admin
from app.core.exceptions import ErrorCode, SBException
from app.core.sensitive_word_guard import contains_sensitive
from app.domains.users.models import User


def _taken() -> SBException:
    """用户名被占用的统一错误（判重命中与并发撞索引共用，保证文案一致）。"""
    return SBException(
        code=ErrorCode.DUPLICATE_ENTRY.code,
        message='该用户名已被占用，请换一个',
        status_code=ErrorCode.DUPLICATE_ENTRY.http_status,
    )


def update_profile(db, user: User, data) -> None:
    """就地更新 ``user``（昵称 / 用户名 / 头像）；冲突 → 409，敏感词 → 400。"""
    renamed_to = None

    if data.username is not None:
        new_username = data.username
        if contains_sensitive(new_username):
            raise SBException(
                code=ErrorCode.INVALID_PARAMS.code,
                message='用户名包含不当词汇，请更换',
                status_code=ErrorCode.INVALID_PARAMS.http_status,
            )
        conflict = (
            db.query(User)
            .filter(
                func.lower(User.username) == new_username.lower(),
                User.id != user.id,
            )
            .first()
        )
        if conflict is not None:
            raise _taken()
        user.username = new_username
        renamed_to = new_username

    if data.nickname is not None:
        if contains_sensitive(data.nickname):
            raise SBException(
                code=ErrorCode.INVALID_PARAMS.code,
                message='昵称包含不当词汇，请更换',
                status_code=ErrorCode.INVALID_PARAMS.http_status,
            )
        user.nickname = data.nickname

    if data.avatar is not None:
        user.avatar = data.avatar

    try:
        db.flush()
    except IntegrityError:
        # 并发改名：两个请求同时通过判重，落库时由唯一索引兜住
        db.rollback()
        raise _taken() from None

    db.refresh(user)

    if renamed_to is not None:
        supabase_admin.update_user_metadata(user.supabase_id, {'username': renamed_to})
        logger.debug('改名已同步 GoTrue metadata：user_id={} username={}', user.id, renamed_to)
