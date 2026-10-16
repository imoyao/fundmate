# -*- coding: utf-8 -*-
"""站内通知服务回归（#2228）。

覆盖的判据（都是产品口径，改实现前先看 `services/notification_service.py` 的模块 docstring）：

1. **幂等**：同一 dedup_key 重复写入只留一条（唯一约束 + 先查后插双保险）；
2. **家庭隔离**：A 家庭的消息 B 家庭读不到，也改不了已读状态；
3. **去重键含日期**：换一天就是新的一条——这是「一天至多一条」节流的实现依据；
4. **banner 取最高优先级的 1 条**：P0 优先于 P1，同级取最新；
5. mark_read 幂等，且不泄漏「存在但不属于你」（返回 False 而非抛错）。
"""

from datetime import date

from app.services import notification_service as ns


def _candidate(source_key='000300', level='P1', day=None):
    return {
        'level': level,
        'category': 'strategy',
        'title': '配比偏离：沪深300',
        'body': '当前占比 46.2%，目标 40.0%，偏离 6.2 个百分点',
        'dedup_key': ns.build_dedup_key('allocation_deviation', source_key, day),
        'source_type': 'allocation_deviation',
        'source_key': source_key,
    }


def test_build_dedup_key_contains_day():
    """去重键含日期：同一天同键只有一条，跨天则是新的一条（节流粒度 = 天）。"""
    assert ns.build_dedup_key('trend', '000300', date(2026, 10, 16)) == 'trend:000300:2026-10-16'
    # 不传 day 时按当天，两次调用同日内结果一致
    assert ns.build_dedup_key('trend', '000300') == ns.build_dedup_key('trend', '000300')


def test_emit_many_idempotent(db):
    """重复 emit 同一键：只有第一次真正新建，后续静默跳过。"""
    assert ns.emit_many(db, 1, [_candidate()]) == 1
    assert ns.emit_many(db, 1, [_candidate()]) == 0
    assert ns.total_count(db, 1) == 1


def test_emit_many_empty_returns_zero(db):
    assert ns.emit_many(db, 1, []) == 0
    assert ns.total_count(db, 1) == 0


def test_emit_many_batch_mixed(db):
    """批量里已有键被跳过、新键被写入，返回的是**新建**条数。"""
    ns.emit_many(db, 1, [_candidate('000300')])
    created = ns.emit_many(db, 1, [_candidate('000300'), _candidate('110020')])
    assert created == 1
    assert ns.total_count(db, 1) == 2


def test_family_isolation(db):
    """家庭隔离：B 家庭读不到 A 的消息，也改不动 A 的已读状态。"""
    ns.emit_many(db, 1, [_candidate()])
    assert ns.total_count(db, 2) == 0
    row = ns.list_notifications(db, 1)[0]
    assert ns.mark_read(db, 2, row.id) is False
    assert ns.unread_count(db, 1) == 1


def test_unread_count_and_mark_read(db):
    ns.emit_many(db, 1, [_candidate('000300'), _candidate('110020')])
    assert ns.unread_count(db, 1) == 2

    first = ns.list_notifications(db, 1)[0]
    assert ns.mark_read(db, 1, first.id) is True
    assert ns.unread_count(db, 1) == 1
    # 幂等：重复标记仍返回 True，但不再重复计数
    assert ns.mark_read(db, 1, first.id) is True
    assert ns.unread_count(db, 1) == 1
    # 不存在的 id
    assert ns.mark_read(db, 1, 999999) is False


def test_mark_all_read_returns_marked_count(db):
    ns.emit_many(db, 1, [_candidate('000300'), _candidate('110020')])
    assert ns.mark_all_read(db, 1) == 2
    assert ns.mark_all_read(db, 1) == 0  # 已无未读
    assert ns.unread_count(db, 1) == 0


def test_banner_prefers_highest_level(db):
    """banner 取最高优先级的 1 条：P1 先写入（更早），P0 后写入，仍应选 P0。"""
    ns.emit_many(db, 1, [_candidate('110020', level='P1')])
    ns.emit_many(db, 1, [_candidate('000300', level='P0')])
    banner = ns.banner_notification(db, 1)
    assert banner is not None
    assert banner.level == 'P0'
    assert banner.source_key == '000300'


def test_banner_none_when_no_unread(db):
    ns.emit_many(db, 1, [_candidate()])
    ns.mark_all_read(db, 1)
    assert ns.banner_notification(db, 1) is None


def test_list_unread_only_and_limit(db):
    ns.emit_many(db, 1, [_candidate('000300'), _candidate('110020')])
    ns.mark_read(db, 1, ns.list_notifications(db, 1)[0].id)
    assert len(ns.list_notifications(db, 1)) == 2
    assert len(ns.list_notifications(db, 1, unread_only=True)) == 1
    assert len(ns.list_notifications(db, 1, limit=1)) == 1
    # limit 被夹在 1~MAX_LIMIT，异常值不得退化成全表扫描
    assert len(ns.list_notifications(db, 1, limit=99999)) == 2


def test_to_dict_isoformat(db):
    ns.emit_many(db, 1, [_candidate()])
    payload = ns.to_dict(ns.list_notifications(db, 1)[0])
    assert payload['is_read'] is False
    assert payload['read_at'] is None
    assert isinstance(payload['created_at'], str)  # ISO 串，而非让前端处理 naive datetime
