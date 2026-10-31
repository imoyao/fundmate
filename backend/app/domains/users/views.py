# -*- coding: utf-8 -*-
"""用户 API — 当前家庭成员列表、个人资料更新（D1 家庭共享 / D10 资料编辑）。

鉴权说明：非白名单接口需登录；成员列表按当前用户所属家庭过滤。
个人资料更新仅作用于当前登录用户（`g.current_user`），不跨家庭。
"""

import json
from datetime import date, datetime

from apiflask import APIBlueprint
from flask import abort, g, jsonify
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core import supabase_admin
from app.core.auth import get_family_id
from app.core.database import get_db
from app.core.sensitive_word_guard import contains_sensitive
from app.core.validation import parse_body
from app.domains.transactions.models import Transaction
from app.domains.users.models import ROLE_LABELS, User, UserPreference
from app.domains.users.schemas import PreferenceOut, PreferenceUpsert, ProfileUpdate, UserOut

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


@users_bp.patch('/me/', strict_slashes=False)
def update_me():
    """更新当前登录用户资料（昵称 / 用户名 / 头像）。

    用户名作为登录标识必须全局唯一：与其他用户冲突返回 409；
    用户名只允许修改且不可置空（置空则保持原值）。
    头像仅存生成式 URL（D9：不落盘、不上传，由 DiceBear 之类生成）。

    **写时同步 GoTrue metadata**（#2764 遗留项）：本地改名成功后，把新 `username`
    写回 Supabase `user_metadata`。不这样做的话，注册时写进 metadata 的旧名会一直
    留在 token 里——新设备 / 新库 JIT 建号（`identity.provision` 读 metadata）会拿
    旧名建号，与本地权威值不一致。同步失败**不回滚改名**（本地才是权威，见
    `app/core/supabase_admin.py` 的失败语义说明）。
    """
    data = parse_body(ProfileUpdate)
    renamed_to = None
    with get_db() as db:
        user = db.query(User).filter_by(id=g.current_user.id).first()
        if user is None:
            abort(401, description='未登录')

        if data.username is not None:
            new_username = data.username
            if contains_sensitive(new_username):
                abort(400, description='用户名包含不当词汇，请更换')
            # 判重必须与「登录解析」同口径（大小写不敏感）：resolve 用 lower() 匹配，
            # 这里若按字面量比较，`Devyao` 就能绕过 `devyao` 的占用检查，
            # 落库后两人共用同一个登录标识（#2764）。
            conflict = (
                db.query(User)
                .filter(
                    func.lower(User.username) == new_username.lower(),
                    User.id != user.id,
                )
                .first()
            )
            if conflict is not None:
                abort(409, description='该用户名已被占用，请换一个')
            user.username = new_username
            renamed_to = new_username
        if data.nickname is not None:
            if contains_sensitive(data.nickname):
                abort(400, description='昵称包含不当词汇，请更换')
            user.nickname = data.nickname
        if data.avatar is not None:
            user.avatar = data.avatar

        try:
            db.flush()
        except IntegrityError:
            # 并发改名：两个请求同时通过上面的判重，落库时由 users 的唯一索引
            # `uq_users_username_lower` 兜住。这里必须转成 409 而不是让它冒成 500——
            # 对用户来说「名字被抢了」是可操作的（换一个），500 不是。
            db.rollback()
            abort(409, description='该用户名已被占用，请换一个')
        db.refresh(user)
        payload = _user_to_dict(user)
        # 在会话内取出，避免块外访问 detached 实例（非请求上下文会关会话）
        supabase_id = user.supabase_id
    # 落库成功之后再做外部同步：DB 事务已提交，失败只留日志（见函数 docstring）
    if renamed_to is not None:
        supabase_admin.update_user_metadata(supabase_id, {'username': renamed_to})
    return jsonify({'data': payload, 'message': 'ok'})


@users_bp.get('/record-stats/')
def record_stats():
    """首页欢迎语用：返回用户首笔交易日期与累计记账天数。

    取家庭内最早一笔有效交易的日期作为记账起点（契约：trade_date 缺失时回退
    confirm_date，两者都有时取更早的 trade_date，即 COALESCE 语义；两者皆空的行不参与）。
    record_days 为该起点至今天的自然日差值。无有效交易记录时返回空。
    """
    with get_db() as db:
        first_date = (
            db.query(func.coalesce(Transaction.trade_date, Transaction.confirm_date))
            .filter(
                Transaction.family_id == get_family_id(),
                (Transaction.trade_date.isnot(None)) | (Transaction.confirm_date.isnot(None)),
            )
            .order_by(func.coalesce(Transaction.trade_date, Transaction.confirm_date).asc())
            .first()
        )
        first_txn_date = first_date[0] if first_date else None
        if first_txn_date is None:
            return jsonify({'data': {'first_entry_date': None, 'record_days': 0}, 'message': 'ok'})

        # first_txn_date 来自 coalesce(trade_date, confirm_date)：trade_date 是 DateTime 列、
        # confirm_date 是 Date 列。若最早一笔 trade_date 为 NULL，first_txn_date 已是 date，
        # 再 .date() 会 AttributeError（与 daily_scheduler #1482 同款）。按既有惯例 isinstance 守卫。
        first_entry_date = first_txn_date.date() if isinstance(first_txn_date, datetime) else first_txn_date
        record_days = max((date.today() - first_entry_date).days, 0)
        return jsonify(
            {
                'data': {
                    'first_entry_date': first_entry_date.isoformat(),
                    'record_days': record_days,
                },
                'message': 'ok',
            }
        )


def _pref_to_dict(pref: UserPreference) -> dict:
    """偏好行 → 响应体：value 由 JSON 文本还原为对象，updated_at 供合并策略比较。"""
    return PreferenceOut(
        key=pref.key,
        value=json.loads(pref.value),
        updated_at=pref.updated_at,
    ).model_dump()


@users_bp.get('/preferences/<key>/')
def get_preference(key: str):
    """读取当前用户某偏好键（#1337 方案 B）。无值返回 data=null（非 404，前端按无偏好处理）。"""
    if len(key) > 100:
        abort(400, description='偏好键过长')
    with get_db() as db:
        pref = db.query(UserPreference).filter_by(user_id=g.current_user.id, key=key).first()
        if pref is None:
            return jsonify({'data': None, 'message': 'ok'})
        return jsonify({'data': _pref_to_dict(pref), 'message': 'ok'})


@users_bp.put('/preferences/<key>/')
def upsert_preference(key: str):
    """写入当前用户某偏好键（upsert：同 key 覆盖，updated_at 随之刷新）。

    updated_at 是前端「最近修改时间取胜」合并策略的依据，必须随每次写入刷新，
    不能保留首建时间。
    """
    if len(key) > 100:
        abort(400, description='偏好键过长')
    data = parse_body(PreferenceUpsert)
    with get_db() as db:
        pref = db.query(UserPreference).filter_by(user_id=g.current_user.id, key=key).first()
        payload = json.dumps(data.value, ensure_ascii=False)
        if pref is None:
            pref = UserPreference(user_id=g.current_user.id, key=key, value=payload)
            db.add(pref)
        else:
            pref.value = payload
        db.flush()
        db.refresh(pref)
        return jsonify({'data': _pref_to_dict(pref), 'message': 'ok'})
