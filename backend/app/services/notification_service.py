# -*- coding: utf-8 -*-
"""站内通知服务：唯一写入口 + 读取口径（user 域 notifications 表）。

设计要点
--------
1. **幂等写入**：`emit_many` 先批量查已有 dedup_key，只插入缺失项。
   之所以「先查后插」而不是靠唯一约束抛异常兜底——本服务常在请求路径上被
   调用（见下第 2 点），`IntegrityError` 后的 `rollback()` 会把同一事务里
   其它未提交的改动一起回滚掉，代价远大于一次 `IN` 查询。

2. **懒生成（lazy refresh）**：站内消息只有在用户在线时才可能被消费，
   因此不需要后台定时任务——在读取前顺带跑一次生成即可，天然等价且省掉
   调度器。真正的定时任务要等站外推送（#508）才需要，那时消息必须在用户
   离线时也能产出。

3. **分级与节流**：level=P0/P1/P2 决定展示位置（首页横栏 / 消息盒）。
   dedup_key 含日期，故「同标的同规则一天至多一条」由唯一约束保证，
   落实需求文档 §9.3 的节流铁律（宁可漏报，不可滥报）。

4. **合规**：title/body 由调用方产出，本层不做措辞加工，但约定全链路
   只陈述「某条规则被触发了」这一客观事实，禁止「建议买入 / 建议卖出」。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Sequence

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.notification.models import Notification

# 单页返回上限：防止前端传超大 limit 拖垮请求（AGENTS.md「请求路径禁止全表扫描」）。
MAX_LIMIT = 200
DEFAULT_LIMIT = 50

# 分级顺序：P0 最强。banner 取当前最高优先级的 1 条未读。
_LEVEL_ORDER = {'P0': 0, 'P1': 1, 'P2': 2}


def build_dedup_key(source_type: str, source_key: str, day: Optional[date] = None) -> str:
    """构造去重键：`来源类型:业务键:日期`。

    日期是节流粒度：同一天同一来源同一业务键只产生一条。调用方不要自行拼字符串，
    避免各处粒度不一致（有的按天、有的按小时）导致去重失效。
    """
    return f'{source_type}:{source_key}:{(day or date.today()).isoformat()}'


def emit_many(db: Session, family_id: int, candidates: Sequence[dict[str, Any]]) -> int:
    """批量幂等写入通知，返回**新建**条数（已存在的键静默跳过）。

    candidates 每项需含：level / category / title / dedup_key / source_type，
    可选 body / source_key。
    """
    if not candidates:
        return 0
    keys = [c['dedup_key'] for c in candidates]
    existing = {
        key
        for (key,) in db.query(Notification.dedup_key).filter(
            Notification.family_id == family_id,
            Notification.dedup_key.in_(keys),
        )
    }
    fresh = [c for c in candidates if c['dedup_key'] not in existing]
    if not fresh:
        return 0
    db.add_all([Notification(family_id=family_id, **item) for item in fresh])
    db.flush()
    return len(fresh)


def list_notifications(
    db: Session,
    family_id: int,
    *,
    unread_only: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> list[Notification]:
    """通知列表（未读优先、新的在前）。"""
    safe_limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    query = db.query(Notification).filter(Notification.family_id == family_id)
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    return query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(safe_limit).all()


def unread_count(db: Session, family_id: int) -> int:
    """未读条数。"""
    return (
        db.query(func.count(Notification.id))
        .filter(Notification.family_id == family_id, Notification.is_read.is_(False))
        .scalar()
        or 0
    )


def total_count(db: Session, family_id: int) -> int:
    """本家庭通知总条数（列表分页用）。"""
    return db.query(func.count(Notification.id)).filter(Notification.family_id == family_id).scalar() or 0


def banner_notification(db: Session, family_id: int) -> Optional[Notification]:
    """首页横栏候选：最高优先级的 1 条未读（P0 > P1 > P2，同级取最新）。

    只取 1 条是刻意的——横栏一旦堆多条就成了噪音，弱提醒一律回落到消息盒。
    """
    rows = (
        db.query(Notification)
        .filter(Notification.family_id == family_id, Notification.is_read.is_(False))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(MAX_LIMIT)
        .all()
    )
    if not rows:
        return None
    return min(rows, key=lambda r: (_LEVEL_ORDER.get(r.level, 9), -r.id))


def mark_read(db: Session, family_id: int, notification_id: int) -> bool:
    """标记单条已读；返回是否命中（False = 不存在或不属于本家庭）。

    family_id 必须参与过滤：否则任何登录用户都能改别人的已读状态。
    """
    row = db.query(Notification).filter(Notification.id == notification_id, Notification.family_id == family_id).first()
    if row is None:
        return False
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.now()
    db.flush()
    return True


def mark_all_read(db: Session, family_id: int) -> int:
    """全部标记已读，返回本次被标记条数。"""
    count = (
        db.query(Notification)
        .filter(Notification.family_id == family_id, Notification.is_read.is_(False))
        .update({'is_read': True, 'read_at': datetime.now()}, synchronize_session=False)
    )
    return int(count or 0)


def to_dict(row: Notification) -> dict[str, Any]:
    """序列化（时间统一转 ISO 字符串，避免前端处理 naive datetime）。"""
    return {
        'id': row.id,
        'level': row.level,
        'category': row.category,
        'title': row.title,
        'body': row.body,
        'source_type': row.source_type,
        'source_key': row.source_key,
        'is_read': bool(row.is_read),
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'read_at': row.read_at.isoformat() if row.read_at else None,
    }
