# -*- coding: utf-8 -*-
"""悬空流水的「标的身份」判据：一组流水到底涉及几个标的。

## 为什么单独一个模块

「同标的」是域 F 三条写路径（补全 / 回补 / 重建）共同的前提，而它此前被三处各自
实现：回补候选比 ``symbol`` 字面量、重建查重比六位码、补全则完全不比。判据一分为三，
真库里就出现了「回补侧说没候选、重建侧说请去回补」的死锁（2026-11-15）。

本模块只回答一件事：给定一批流水，它们是不是同一个标的。``symbol`` 相同不足以证明
（真库 293 条分属 114 个标的的流水全被同一次补全写成 ``127078``），标的名相同也不
足以证明（同一标的的简称与全称写法不同，如「华商元亨混合C」与它的全称），故用
「标的名 → symbol」反查合并之后再数。

## 为什么悬空条件也在这里

索引必须排除悬空流水：它们正是可能被写坏的那批，拿它们互相证明「同一个标的」等于
让错标自我背书。悬空条件因此与身份判据放在一处，域 F 各服务从这里取，不再各写一遍。
"""

from collections import defaultdict

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from app.core.venues import venue_of_asset_type
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.fund_utils import normalize_fund_code

#: 候选持仓最多返回条数。
MAX_CANDIDATES = 20


def symbol_forms(symbol: str | None) -> set[str]:
    """同一标的的全部代码写法：字面量 + 裸 6 位码 + 三个交易所前缀。

    ``127078`` 与 ``SZ127078`` 是同一只债的两种写法（真库 2026-11-15：券商交割单导入
    写的是裸码，持仓行带 ``SZ`` 前缀）。按字面量比，同一只标的会被当成两只。
    """
    if not symbol or not symbol.strip():
        return set()
    value = symbol.strip().upper()
    code = normalize_fund_code(value)
    if not code:
        return {value}
    return {value, code, f'SH{code}', f'SZ{code}', f'BJ{code}'}


def same_identity(symbol_a, asset_type_a, symbol_b, asset_type_b) -> bool:
    """两个「代码 + 资产类型」是否指向同一标的：场所必须相容、归一码必须有交集。

    只看归一码不够：``000001`` 既是场外基金（华夏成长），也是 ``SZ000001`` 平安银行。
    场所（``asset_type → venue``）两侧都判得出且不同 → 直接判「不是同一标的」；
    任一侧判不出场所时退回「同归一码即同标的」，与 ``_find_existing_position`` 同口径。
    """
    if not symbol_a or not symbol_b:
        return False
    if symbol_a.strip().upper() == symbol_b.strip().upper():
        return True
    venue_a = venue_of_asset_type(asset_type_a)
    venue_b = venue_of_asset_type(asset_type_b)
    if venue_a and venue_b and venue_a != venue_b:
        return False
    return bool(symbol_forms(symbol_a) & symbol_forms(symbol_b))


def matching_positions(positions: list[Position], symbol, asset_type=None) -> list[Position]:
    """按「同一标的」筛持仓（写法归一 + 场所相容），顺序保持不变。"""
    return [p for p in positions if same_identity(p.symbol, p.asset_type, symbol, asset_type)]


def position_candidates(
    ledger_positions: list[Position], symbol: str, asset_type=None
) -> tuple[list[Position], Position | None]:
    """候选只列「同账本且同一标的」的现存持仓；空 symbol 一律不给候选。

    reattach 硬校验标的身份，列出别的标的只会诱导用户挂错。早前一组缺码流水拿到的
    是「同账本任意持仓前 20 条」，等于让用户瞎猜。比对走 ``same_identity``：``127078``
    与 ``SZ127078`` 视为同一只（字面量比较会造出「候选 0 条 / 重建又说请去回补」的死锁）。
    """
    if not symbol:
        return [], None
    same_symbol = matching_positions(ledger_positions, symbol, asset_type)
    return same_symbol[:MAX_CANDIDATES], (same_symbol[0] if same_symbol else None)


def block_reason(symbol: str, cands: list[Position], identity_count: int) -> tuple[bool, str | None]:
    """可否安全回补的单一真相源（前端只显示结果，不自行推导）；文案须指向界面上真有的按钮。"""
    if identity_count > 1:
        return False, (
            f'这组流水混了 {identity_count} 个不同标的，不能整组回补或重建；'
            '请先按标的拆开（每组只留一个标的）再逐个处理'
        )
    if not symbol:
        return False, '这批流水缺标的代码，无法判定归属；需先补全 symbol 才能回补'
    if not cands:
        return False, '同账本没有同标的的现存持仓行，无法挂回；可按流水重建持仓'
    return True, None


def dangling_condition(family_id: int):
    """悬空检出条件（#2866 契约口径），返回可直接喂给 ``filter()`` 的表达式。

    ``Transaction.position_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM positions p
                       WHERE p.id = transactions.position_id
                         AND p.family_id = :family_id)
       AND transactions.family_id = :family_id``

    ``.correlate(Transaction.__table__)`` 把 transactions 从子查询 FROM 里排除、作为外层
    引用：否则 EXISTS 会退化成「全库任意一条流水匹配任意持仓」的非相关子查询，库里只要
    存在一条正常流水 NOT EXISTS 就恒假，检出彻底失效。相关子查询能在「有持仓行 / 无持仓行」
    两种情况下精确区分，是本模块正确性的命门（见测试的变异探针）。
    """
    live = exists(
        select(Position.id)
        .where(Position.id == Transaction.position_id, Position.family_id == family_id)
        .correlate(Transaction.__table__)
    )
    return and_(
        Transaction.family_id == family_id,
        Transaction.position_id.isnot(None),
        ~live,
    )


def name_symbol_index(db: Session, family_id: int) -> dict[str, set[str]]:
    """标的名 → 本家庭出现过的 symbol 集合（判断「一组流水是不是混了多个标的」的依据）。

    真库 2026-11-15 实测：293 条空 symbol 流水并成一组，组内 114 个不同标的
    （优彩转债、精达转债、紫金矿业…），而「补全信息」按组写一个 symbol —— 一次就把
    114 个标的刷成了同一只债。判据必须能在写之前问出「这组到底有几个标的」。

    悬空流水自身不参与建索引（见模块 docstring）：它们可能正是被写坏的那批。
    """
    index: dict[str, set[str]] = defaultdict(set)
    rows = (
        db.query(Transaction.position_name, Transaction.symbol)
        .filter(
            Transaction.family_id == family_id,
            Transaction.position_name.isnot(None),
            Transaction.symbol.isnot(None),
            Transaction.symbol != '',
            ~dangling_condition(family_id),
        )
        .distinct()
    )
    for name, symbol in rows:
        index[(name or '').strip()].add(symbol)
    positions = db.query(Position.name, Position.symbol).filter(
        Position.family_id == family_id,
        Position.name.isnot(None),
        Position.symbol.isnot(None),
        Position.symbol != '',
    )
    for name, symbol in positions:
        index[(name or '').strip()].add(symbol)
    return index


def display_name(first_name, identity_count: int):
    """组名在混标的时点出「等 N 个标的」——只报第一个名字正是 293 条被误读的成因。"""
    if first_name and identity_count > 1:
        return f'{first_name} 等 {identity_count} 个标的'
    return first_name


def identity_count(txns, name_index: dict[str, set[str]]) -> int:
    """这组流水实际涉及几个标的：按标的名反查 symbol 合并；反查不到的名字各算一个。

    名字线索全无时返回 1（无从判冲突，不臆造拒绝）。
    """
    names = {(t.position_name or '').strip() for t in txns if (t.position_name or '').strip()}
    if not names:
        return 1
    symbols: set[str] = set()
    for name in names:
        mapped = name_index.get(name)
        symbols |= mapped if mapped else {f'?{name}'}
    return len(symbols)


def require_single_identity(db: Session, family_id: int, txns, action: str, symbol=None) -> None:
    """写路径的统一闸门：一批流水分属多个标的时拒绝，并说明为什么不能一起做。

    三条写路径（补全 / 回补 / 重建）都要它。``symbol`` 一致不足以放行——真库
    2026-11-15 有 293 条分属 114 个标的的流水被同一次补全写成了同一个 symbol，
    只校验 symbol 会把 114 个标的的历史并成一只债。

    ``symbol`` 传 None 表示这次写入不改标的（例如只补 trade_date），没有可冲突的对象。
    """
    if symbol is None:
        return
    identity = identity_count(txns, name_symbol_index(db, family_id))
    if identity > 1:
        raise ValueError(f'选中的流水混了 {identity} 个不同标的，不能一起{action}；请按标的分别处理')
