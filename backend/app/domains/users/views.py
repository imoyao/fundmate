# -*- coding: utf-8 -*-
"""用户 API — 当前家庭成员列表、个人资料更新（D1 家庭共享 / D10 资料编辑）。

鉴权说明：非白名单接口需登录；成员列表按当前用户所属家庭过滤。
个人资料更新仅作用于当前登录用户（`g.current_user`），不跨家庭。
"""

from datetime import date

from apiflask import APIBlueprint
from flask import abort, g, jsonify

from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.validation import parse_body
from app.domains.transactions.models import Transaction
from app.domains.users.models import ROLE_LABELS, User
from app.domains.users.schemas import ProfileUpdate, UserOut

users_bp = APIBlueprint('users', __name__, url_prefix='/api/users')


def _user_to_dict(user: User) -> dict:
    data = UserOut.model_validate(user).model_dump()
    data['role_label'] = ROLE_LABELS.get(user.role, user.role)
    return data


@users_bp.get('/')
def list_family_members():
    """获取当前用户所属家庭的成员列表。"""
    with get_db() as db:
        members = db.query(User).filter(User.family_id == get_family_id()).order_by(User.created_at.asc()).all()
        return jsonify({'data': [_user_to_dict(m) for m in members], 'message': 'ok'})


@users_bp.patch('/me')
def update_me():
    """更新当前登录用户资料（昵称 / 用户名 / 头像）。

    用户名作为登录标识必须全局唯一：与其他用户冲突返回 409；
    用户名只允许修改且不可置空（置空则保持原值）。
    头像仅存生成式 URL（D9：不落盘、不上传，由 DiceBear 之类生成）。
    """
    data = parse_body(ProfileUpdate)
    with get_db() as db:
        user = db.query(User).filter_by(id=g.current_user.id).first()
        if user is None:
            abort(401, description='未登录')

        if data.username is not None:
            new_username = data.username
            conflict = (
                db.query(User)
                .filter(
                    User.username == new_username,
                    User.id != user.id,
                )
                .first()
            )
            if conflict is not None:
                abort(409, description='该用户名已被占用，请换一个')
            user.username = new_username
        if data.nickname is not None:
            user.nickname = data.nickname
        if data.avatar is not None:
            user.avatar = data.avatar

        db.commit()
        db.refresh(user)
        return jsonify({'data': _user_to_dict(user), 'message': 'ok'})


@users_bp.get('/record-stats/')
def record_stats():
    """首页欢迎语用：返回用户首笔交易日期与累计记账天数。

    取家庭内最早一笔交易的 trade_date（交易发起日，T日）作为记账起点；
    record_days 为该起点至今天的自然日差值。无交易记录时返回空。
    """
    with get_db() as db:
        first_txn = (
            db.query(Transaction)
            .filter(Transaction.family_id == get_family_id())
            .order_by(Transaction.trade_date.asc())
            .first()
        )
        if first_txn is None or first_txn.trade_date is None:
            return jsonify({'data': {'first_entry_date': None, 'record_days': 0}, 'message': 'ok'})

        first_entry_date = first_txn.trade_date.date()
        record_days = (date.today() - first_entry_date).days
        return jsonify(
            {
                'data': {
                    'first_entry_date': first_entry_date.isoformat(),
                    'record_days': record_days,
                },
                'message': 'ok',
            }
        )
