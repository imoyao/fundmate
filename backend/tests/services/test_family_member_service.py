# -*- coding: utf-8 -*-
"""家庭成员档案与账户归属（#1173）的回归网。

## 锁的是什么

1. **成员档案 CRUD 的业务规则**（`services/family_member_service.py`）：
   称谓非空/限长、角色词表校验、成员必须属同一家庭、删除是软删。
2. **账户归属的写路径**（`services/ledger_write_service.py`）：
   `owner_member_id` 必须在白名单里显式处理——该模块用 `if 'X' in data:` 逐字段
   过滤，**未列出的键被静默忽略**。漏写这个分支的症状是「前端传了成员、
   保存成功、但归属没变」，且**不报任何错**。本文件用「传了就生效」反向钉死。
3. **持仓/汇总按成员筛选**（`position_service` / `summary_service`）：
   成员筛选经账户间接归属，**不下推 SQL 就是内存筛**（数据策略硬约束 §6）。
   这里锁两件事：筛选结果正确 + **成员桶 ≡ 该成员名下账户的子集**
   （不多不少，不串户）。
4. **「唯一累加出口」不被破坏**：`family_totals` 的 docstring 明令禁止别处另写
   `total_assets += ...`（#2154 的教训）。成员切片必须复用同一份实现，
   故断言「成员切片的总资产 == 该成员名下账户的市值之和」。
"""

import pytest

from app.core.money import Money
from app.domains.families.models import (
    MEMBER_ROLE_CHILD,
    MEMBER_ROLE_OTHER,
    MEMBER_ROLE_SPOUSE,
    FamilyMember,
)
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.family_member_service import (
    FamilyMemberError,
    create_member,
    deactivate_member,
    get_member,
    list_members,
    resolve_owner_member,
    update_member,
)
from app.services.ledger_write_service import LedgerWriteError, create_ledger, update_ledger
from app.services.pnl_service import family_realized_pnl_cents, realized_pnl_by_position
from app.services.position_service import PositionService
from app.services.summary_service import family_totals, get_summary_data


@pytest.fixture
def member(db):
    m = FamilyMember(family_id=1, name='老婆', role=MEMBER_ROLE_SPOUSE)
    db.add(m)
    db.flush()
    return m


@pytest.fixture
def other_member(db):
    m = FamilyMember(family_id=1, name='小孩', role=MEMBER_ROLE_CHILD)
    db.add(m)
    db.flush()
    return m


@pytest.fixture
def ledger(db):
    lg = Ledger(name='招行', ledger_type='bank', family_id=1)
    db.add(lg)
    db.flush()
    return lg


def _position(db, ledger, symbol: str, *, quantity: float = 1000.0, avg_price: float = 1.0):
    pos = Position(
        symbol=symbol,
        name=f'测试{symbol}',
        asset_type='fund',
        ledger_id=ledger.id,
        family_id=1,
        quantity=Money.shares_to_min_unit(quantity),
        avg_price=Money.yuan_to_price_units(avg_price),
        current_price=Money.yuan_to_price_units(avg_price),
        ownership_status='active',
        source='manual',
    )
    db.add(pos)
    db.flush()
    return pos


# ── 成员档案业务规则 ─────────────────────────────────────────────────────────


def test_create_member_trims_name(db):
    """称谓去首尾空白（用户手输常有空格）。"""
    result = create_member(db, 1, name='  老婆  ', role=MEMBER_ROLE_SPOUSE)
    assert result['name'] == '老婆'
    assert result['role_label'] == '配偶'


def test_create_member_rejects_blank_name(db):
    """空称谓必须报错，不能建出无名成员。"""
    with pytest.raises(FamilyMemberError) as exc:
        create_member(db, 1, name='   ', role=MEMBER_ROLE_OTHER)
    assert '不能为空' in exc.value.message


def test_create_member_rejects_unknown_role(db):
    """角色必须在词表内——复用 users 的权限角色词表是语义错误（角色一词两义）。"""
    with pytest.raises(FamilyMemberError) as exc:
        create_member(db, 1, name='某某', role='admin')
    assert '角色无效' in exc.value.message


def test_member_roles_are_independent_from_permission_roles(db):
    """家庭内角色词表与 users 权限角色词表**不相交**。

    这是 #1173 的核心设计决定：复用 `users.role` 会让「谁能改账本」与
    「这笔钱是谁的」两件事共用一个词。
    """
    from app.domains.families.models import MEMBER_ROLES
    from app.domains.users.models import ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER

    assert set(MEMBER_ROLES) & {ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER} == set()


def test_list_members_counts_ledgers(db, member, ledger):
    """成员列表带各自名下账户数（用户要靠它判断删成员会不会丢数据）。"""
    ledger.owner_member_id = member.id
    db.flush()
    data = list_members(db, 1)
    assert len(data) == 1
    assert data[0]['ledger_count'] == 1


def test_update_member_changes_name_and_role(db, member):
    result = update_member(db, member, name='媳妇', role=MEMBER_ROLE_SPOUSE)
    assert result['name'] == '媳妇'
    assert result['role'] == MEMBER_ROLE_SPOUSE


def test_deactivate_member_is_soft_delete(db, member, ledger):
    """停用是软删：成员行留着（历史归属可追溯），只是 is_active=False。"""
    ledger.owner_member_id = member.id
    db.flush()
    result = deactivate_member(db, member)
    assert result['is_active'] is False
    # 行还在
    assert get_member(db, 1, member.id) is not None


def test_deactivate_member_keeps_ledger_ownership(db, member, ledger):
    """名下有账户**也能停用**，且账户归属不变（历史可追溯）。

    WHY 这条要钉：硬删会让 ``ledgers.owner_member_id`` 悬空，所以停用被设计成软删。
    前端曾误以为「名下有账户就不能停用」，与后端语义打架——后端是权威，
    这条测试把「可停用 + 归属保留」钉死，前端按它对齐。
    """
    ledger.owner_member_id = member.id
    db.flush()
    result = deactivate_member(db, member)
    assert result['is_active'] is False
    # 账户归属原样保留
    db.refresh(ledger)
    assert ledger.owner_member_id == member.id
    assert result['ledger_count'] == 1


def test_reactivate_member_restores_assignability(db, member, ledger):
    """停用后可在「编辑」里恢复启用（停用可逆，否则软删只是半个软删）。"""
    deactivate_member(db, member)
    assert member.is_active is False
    updated = update_member(db, member, is_active=True)
    assert updated['is_active'] is True
    # 恢复后又能新建归属账户
    create_ledger(db, 1, {'name': '恢复后新建', 'owner_member_id': member.id})


def test_get_member_rejects_cross_family(db, member):
    """跨家庭取成员返回 None（视图据此 404，不泄露存在性）。"""
    assert get_member(db, 999, member.id) is None


# ── 账户归属写路径 ───────────────────────────────────────────────────────────


def test_resolve_owner_member_validates_family(db, member):
    """成员必须属同一家庭——否则能把别家成员挂到自家账户上。"""
    assert resolve_owner_member(db, 1, member.id) == member.id
    with pytest.raises(FamilyMemberError) as exc:
        resolve_owner_member(db, 999, member.id)
    assert '不属于当前家庭' in exc.value.message


def test_resolve_owner_member_accepts_none(db):
    """不归属 = 家庭共有（None 原样返回）。"""
    assert resolve_owner_member(db, 1, None) is None


def test_create_ledger_with_owner_member(db, member):
    """建账时可指定归属成员。"""
    ledger = create_ledger(db, 1, {'name': '老婆的招行', 'owner_member_id': member.id})
    assert ledger.owner_member_id == member.id


def test_create_ledger_rejects_cross_family_owner(db):
    """跨家庭成员不得挂到自家账户（成员属 family 2，账户建在 family 1）。"""
    foreign = FamilyMember(family_id=2, name='别家的人', role=MEMBER_ROLE_OTHER)
    db.add(foreign)
    db.flush()
    with pytest.raises(LedgerWriteError) as exc:
        create_ledger(db, 1, {'name': 'X', 'owner_member_id': foreign.id})
    assert '不存在或不属于当前家庭' in exc.value.message


def test_update_ledger_applies_owner_member(db, ledger, member):
    """⚠️ 白名单回归：``owner_member_id`` 必须在 update_ledger 里显式处理。

    该函数用 `if 'X' in data:` 逐字段过滤，**未列出的键被静默忽略**——
    漏写这个分支的症状是「传了、返回 200、但归属没变」，且不报任何错。
    """
    update_ledger(db, ledger, {'owner_member_id': member.id}, 1)
    assert ledger.owner_member_id == member.id


def test_update_ledger_can_unbind_owner(db, ledger, member):
    """解绑：传 None 应把归属清回「家庭共有」。"""
    ledger.owner_member_id = member.id
    db.flush()
    update_ledger(db, ledger, {'owner_member_id': None}, 1)
    assert ledger.owner_member_id is None


def test_update_ledger_rejects_inactive_member(db, ledger, member):
    """停用成员不可被**改绑**（但已绑账户保留原归属，见下一条）。"""
    deactivate_member(db, member)
    with pytest.raises(LedgerWriteError) as exc:
        update_ledger(db, ledger, {'owner_member_id': member.id}, 1)
    assert '已停用' in exc.value.message


def test_update_ledger_keeps_inactive_member_binding(db, ledger, member):
    """已绑账户在成员停用后**保留原归属**——历史归属不能因为停用就丢。"""
    ledger.owner_member_id = member.id
    db.flush()
    deactivate_member(db, member)
    update_ledger(db, ledger, {'owner_member_id': member.id}, 1)
    assert ledger.owner_member_id == member.id


def test_create_ledger_rejects_inactive_member(db, member):
    """新建账户不得指派停用成员。"""
    deactivate_member(db, member)
    with pytest.raises(LedgerWriteError) as exc:
        create_ledger(db, 1, {'name': 'X', 'owner_member_id': member.id})
    assert '已停用' in exc.value.message


# ── 持仓按成员筛选 ───────────────────────────────────────────────────────────


def test_build_position_list_filters_by_member(db, member, other_member, ledger):
    """按成员筛选：只返回该成员名下账户的持仓。"""
    other_ledger = Ledger(name='招行', ledger_type='bank', family_id=1, owner_member_id=member.id)
    db.add(other_ledger)
    db.flush()
    _position(db, other_ledger, '000001')
    _position(db, ledger, '000002')

    payload = PositionService.build_position_list(db, 1, '', 1, 20, '', '', '', str(member.id))
    symbols = {p['symbol'] for p in payload['data']}
    assert symbols == {'000001'}


def test_build_position_list_member_with_no_ledger_returns_empty(db, member, ledger):
    """成员名下没有账户 → 结果必为空（不能因 `IN ()` 各方言差异而 500）。"""
    _position(db, ledger, '000001')
    payload = PositionService.build_position_list(db, 1, '', 1, 20, '', '', '', str(member.id))
    assert payload['data'] == []


def test_build_position_list_without_member_returns_all(db, member, ledger):
    """不传 member_id → 家庭级全量（既有行为不变）。"""
    _position(db, ledger, '000001')
    payload = PositionService.build_position_list(db, 1, '', 1, 20, '', '', '', '')
    assert len(payload['data']) == 1


# ── 汇总按成员切片：唯一累加出口不被破坏 ─────────────────────────────────────


def test_family_totals_member_slice_matches_ledger_sum(db, member, ledger):
    """成员切片的总资产 == 该成员名下账户市值之和（复用唯一累加实现，不是另写一遍）。

    这是 #2154 的教训对应：另写一套累加就会出现「同一接口两个数」。
    """
    member_ledger = Ledger(name='老婆的招行', ledger_type='bank', family_id=1, owner_member_id=member.id)
    db.add(member_ledger)
    db.flush()
    _position(db, member_ledger, '000001', quantity=1000.0, avg_price=2.0)
    _position(db, ledger, '000002', quantity=1000.0, avg_price=5.0)

    member_totals = family_totals(db, 1, member_id=member.id)
    all_totals = family_totals(db, 1)

    # 成员切片只含自己那笔（1000 份 × 2 元 = 2000 元）
    assert member_totals['total_assets'] == 2000.0
    # 家庭全量两笔都在
    assert all_totals['total_assets'] == 7000.0


def test_family_totals_member_without_ledger_is_zero(db, member, ledger):
    """成员名下无账户 → 成员切片为 0（全量非 0），不能串户。"""
    _position(db, ledger, '000001', quantity=1000.0, avg_price=5.0)
    member_totals = family_totals(db, 1, member_id=member.id)
    assert member_totals['total_assets'] == 0.0


# ── 盈亏按成员切片：持仓与盈亏必须同一份账户集合 ─────────────────────────────


def _sell_txn(db, ledger, position, *, realized_cents: int, amount_cents: int = 0):
    """造一条卖出流水（已实现盈亏的**事实源**是流水，不是持仓）。"""
    txn = Transaction(
        position_id=position.id,
        symbol=position.symbol,
        txn_type='sell',
        amount=amount_cents,
        realized_pnl=realized_cents,
        ledger_id=ledger.id,
        family_id=1,
        status='success',
    )
    db.add(txn)
    db.flush()
    return txn


def test_realized_pnl_by_position_filters_by_member(db, member, ledger):
    """已实现盈亏按成员切片：只认该成员名下账户的流水（不串户）。"""
    member_ledger = Ledger(name='老婆的招行', ledger_type='bank', family_id=1, owner_member_id=member.id)
    db.add(member_ledger)
    db.flush()
    member_pos = _position(db, member_ledger, '000001')
    other_pos = _position(db, ledger, '000002')
    _sell_txn(db, member_ledger, member_pos, realized_cents=100_00)
    _sell_txn(db, ledger, other_pos, realized_cents=500_00)

    assert realized_pnl_by_position(db, 1)[member_pos.id] == 100_00
    # 成员切片只含自己的那笔
    sliced = realized_pnl_by_position(db, 1, [member_ledger.id])
    assert sliced == {member_pos.id: 100_00}


def test_realized_pnl_by_position_empty_ledger_ids_returns_empty(db, member, ledger):
    """账户集合为空 → 返回空表（不是全家庭的值）。"""
    pos = _position(db, ledger, '000001')
    _sell_txn(db, ledger, pos, realized_cents=500_00)
    assert realized_pnl_by_position(db, 1, []) == {}


def test_family_realized_pnl_cents_filters_by_member(db, member, ledger):
    """家庭级已实现盈亏合计同样按成员切片。"""
    member_ledger = Ledger(name='老婆的招行', ledger_type='bank', family_id=1, owner_member_id=member.id)
    db.add(member_ledger)
    db.flush()
    member_pos = _position(db, member_ledger, '000001')
    other_pos = _position(db, ledger, '000002')
    _sell_txn(db, member_ledger, member_pos, realized_cents=100_00)
    _sell_txn(db, ledger, other_pos, realized_cents=500_00)

    assert family_realized_pnl_cents(db, 1) == 600_00
    assert family_realized_pnl_cents(db, 1, [member_ledger.id]) == 100_00
    assert family_realized_pnl_cents(db, 1, []) == 0


def test_summary_data_member_slice_pnl_matches_member_only(db, member, ledger):
    """仪表盘的盈亏与持仓按**同一份账户集合**切片。

    WHY 这条要单独锁：持仓切片与盈亏切片若各算各的（口径分叉），会出现
    「持仓显示的是 A 成员、盈亏算的是全家」——汇总页的数字会自相矛盾。
    """
    member_ledger = Ledger(name='老婆的招行', ledger_type='bank', family_id=1, owner_member_id=member.id)
    db.add(member_ledger)
    db.flush()
    member_pos = _position(db, member_ledger, '000001')
    other_pos = _position(db, ledger, '000002')
    _sell_txn(db, member_ledger, member_pos, realized_cents=100_00)
    _sell_txn(db, ledger, other_pos, realized_cents=500_00)

    member_data = get_summary_data(db, 1, member_id=member.id)
    all_data = get_summary_data(db, 1)

    # 成员切片只含自己的已实现盈亏（100 元）
    assert member_data['realized_pnl_cny'] == 100.0
    # 家庭全量含两笔（600 元）
    assert all_data['realized_pnl_cny'] == 600.0
    # 成员的持仓市值只算自己的（1000 份 × 1 元 = 1000 元）
    assert member_data['total_assets_cny'] == 1000.0


def test_summary_data_member_without_ledger_is_zero(db, member, ledger):
    """成员名下无账户 → 成员切片全零（不能退化成家庭全量）。"""
    pos = _position(db, ledger, '000001')
    _sell_txn(db, ledger, pos, realized_cents=500_00)
    data = get_summary_data(db, 1, member_id=member.id)
    assert data['total_assets_cny'] == 0.0
    assert data['realized_pnl_cny'] == 0.0
    assert data['total_pnl_cny'] == 0.0
