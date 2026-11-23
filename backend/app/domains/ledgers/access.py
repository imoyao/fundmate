# -*- coding: utf-8 -*-
"""账户可见性的请求上下文适配层（#3246 第二段）.

``visibility.py`` 是纯判定（不依赖 Flask、可单测）；本模块只做两件事：

1. 把「当前请求是谁」翻译成判定所需参数（``current_user_id``）；
2. 把「按 id 取账户」收敛成单一入口（``get_visible_ledger_or_404``）。

**为什么 404 而不是 403**：403 等于告诉调用方「这个 id 真实存在」，是信息泄露；
与 ``session_store.get_owned`` 的口径保持一致。

**为什么不用 ``visible_ledger_ids`` 做单行判定**：那是集合查询（一次 ``IN`` 全表扫
可见集），单行取数用 ``can_view`` 纯判定即可，少一次查询，且语义与集合过滤共用同一份
规则——两处不会漂移。
"""

from flask import abort, g

from app.core.auth import get_family_id
from app.domains.ledgers.models import Ledger
from app.domains.ledgers.visibility import (
    VISIBILITIES,
    VISIBILITY_PRIVATE,
    VISIBILITY_SHARED,
    can_view,
    visible_ledger_ids,
)


def current_user_id():
    """当前登录用户 id；未启用鉴权（本地模式）时为 None."""
    user = getattr(g, 'current_user', None)
    return getattr(user, 'id', None)


def resolve_ledger_scope(data, user_id):
    """解析新账户的可见性，返回 ``(visibility, owner_user_id, error)``.

    三条规则，都有明确理由：

    1. 缺省 ``private``——产品口径是「默认独有」，不是「默认共享」；
    2. 非法取值返回错误，不静默降级成 private（静默降级会让「共享」请求变成
       「别人看不见」，比 400 更难排查）；
    3. **无身份上下文时降级为 shared**：本地未启用鉴权（``g.current_user`` 不存在）
       时没有可判定的主体，若仍写 private，账户会对所有人（含自己）不可见——
       那不是安全，是数据丢失。这类部署本来就是单人使用，shared 与「全可见」等价。
    """
    raw = data.get('visibility') or VISIBILITY_PRIVATE
    if not isinstance(raw, str):
        return None, None, '可见性取值无效'
    value = raw.strip()
    if value not in VISIBILITIES:
        return None, None, '可见性取值无效'
    if value == VISIBILITY_PRIVATE and user_id is None:
        return VISIBILITY_SHARED, None, None
    return value, (user_id if value == VISIBILITY_PRIVATE else None), None


def visible_ledger_id_set(db) -> set:
    """当前用户可见账户 id 集合（列表查询直接 ``Ledger.id.in_(...)``）."""
    return visible_ledger_ids(db, get_family_id(), current_user_id())


def get_visible_ledger_or_404(db, ledger_id: int) -> Ledger:
    """按 id 取当前用户**可见**的账户；不存在或不可见一律 404（不区分，防探测）."""
    ledger = db.query(Ledger).filter(Ledger.id == ledger_id, Ledger.family_id == get_family_id()).first()
    if ledger is None or not can_view(ledger.visibility, ledger.owner_user_id, current_user_id()):
        abort(404)
    return ledger
