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

from sqlalchemy import and_, exists, or_, select
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


#: 归置域（#3089）专属的账外类现金类型：``orphan_coverage_service`` 只收这两类，
#: 无归属清单必须排除它们，否则同一行会被两个端点同时报出、用户拿到两套「修法」。
UNOWNED_EXCLUDED_ASSET_TYPES = ('money_fund', 'reverse_repo')


def unowned_condition(family_id: int):
    """「无持仓承接」流水（#3126 新类）的检出条件，返回可直接喂给 ``filter()`` 的表达式。

    逐条理由（每条都在与一类既有脏数据划界，勿合并、勿删）：

    - ``family_id`` 匹配：多家庭隔离，与 ``dangling_condition`` 同口径。
    - ``position_id IS NULL``：与域 F（``dangling_condition`` 要求 ``position_id IS NOT
      NULL`` 且引用悬空）互斥——同一行绝不进两个清单，主扫描的契约（NULL 孤儿不进
      域 F）不被破坏。
    - ``covered_position_id IS NULL``：已被「归置」（#3089）标记「已由某持仓体现」的
      行有了承接，不再是无归属。
    - ``ledger_id IS NOT NULL``：与域 G（``orphan_ledger_service._orphan_condition``
      要求 ``ledger_id IS NULL``）互斥——缺账本走那条修法，不在这里双报。
    - ``quantity != 0``：真库 254 条界外流水里，146 条货基买卖与 77 条分红/红利税
      实测全为 0——它们不改变持仓份额、没有「卖出消失」的风险，报出来只是噪声。
      ``quantity`` 存的是最小单位（份×10000），比较用整数，绝不经 float。
    - ``asset_type`` 排除 ``money_fund`` / ``reverse_repo``：这两类归「归置」域收，
      排除避免双报（见 ``UNOWNED_EXCLUDED_ASSET_TYPES``）。

    **刻意不看 ``symbol``**：补全标的（``/dangling-refs/enrich/``）之后，该行必须仍
    留在本清单里——夜间回填会按「同账本同标的」把它自动挂回持仓；谓词若看 symbol，
    补全动作会让它再次凭空消失。

    ⚠️ ``asset_type`` 可能为 NULL：SQL 里 ``NOT IN`` 遇 NULL 结果是 NULL（被当成
    false 而**漏掉整行**），故必须写成 ``or_(is_(None), ~in_(...))`` 的显式形式。
    真库那 10 条的 ``asset_type`` 恰好全是 NULL——写成 ``NOT IN`` 一条都检不出，
    且语法检查、类型检查全绿，只有测试能咬住（见 test_dangling_ref_unowned_service）。
    """
    return and_(
        Transaction.family_id == family_id,
        Transaction.position_id.is_(None),
        Transaction.covered_position_id.is_(None),
        Transaction.ledger_id.isnot(None),
        Transaction.quantity != 0,
        or_(
            Transaction.asset_type.is_(None),
            ~Transaction.asset_type.in_(UNOWNED_EXCLUDED_ASSET_TYPES),
        ),
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


def names_include(index: dict[str, set[str]], txns, symbol) -> bool:
    """组内每个标的名是否都把 ``symbol`` 列为候选（名字歧义可由显式代码收敛）。

    「旅游ETF」同时对应 ``SH562510`` / ``SZ159766`` 两只 —— 这类名字让组内标的数算成 2，
    但它不是「混了标的」，而是「一个名字有多个候选码」。用户显式指定其中一个时应当放行，
    否则这类组永远无法补全（连单条也判 2 个标的）。名字反查不到、或候选里没有该代码 →
    不放行，仍按混标的拒绝。
    """
    names = {(t.position_name or '').strip() for t in txns if (t.position_name or '').strip()}
    if not names:
        return False
    return all(symbol in (index.get(name) or set()) for name in names)


def matches_target(
    t: Transaction,
    symbol: str,
    asset_type,
    name_index: dict[str, set[str]],
    group_names: set[str] | None = None,
) -> bool:
    """这条流水是否属于给定标的：有码走身份归一，缺码走「同名」再退回标的名反查。

    缺码这一支正是 #3127 的成因：08-29 导入时同一标的的买腿带 ``SZ128101``、四条卖腿
    ``symbol`` 为空，重建按 ``(ledger, symbol)`` 分组把卖腿分到了另一组（且被 ``no_symbol``
    挡住）⇒ 只拿买入腿建出 270 张；卖腿随后补码回补，份额却不再重算。判「缺口」必须能
    看见「缺码但同名」的那些流水，否则这类幽灵持仓会被判成「份额偏小」而放过。

    ``group_names``（组内已有的标的名）必须参与，因为 ``name_symbol_index`` **刻意不索引
    悬空流水**——而待重建的那批流水按定义全是悬空的，靠索引反查等于查不到自己这一组。
    「同账本 + 同名」在本域足够可靠：同账本内同名不同标的没有出现过，且已按账本过滤。
    """
    if not symbol:
        return False
    if (t.symbol or '').strip():
        return same_identity(t.symbol, t.asset_type, symbol, asset_type)
    name = (t.position_name or '').strip()
    if not name:
        return False
    venue_t = venue_of_asset_type(t.asset_type)
    venue_g = venue_of_asset_type(asset_type)
    if venue_t and venue_g and venue_t != venue_g:
        return False
    if name in (group_names or set()):
        return True
    mapped = name_index.get(name) or set()
    return any(same_identity(s, t.asset_type, symbol, asset_type) for s in mapped)


def unclaimed_flows(
    db: Session,
    family_id: int,
    ledger_id,
    group: list[Transaction],
    *,
    symbol: str | None = None,
    asset_type=None,
    name_index: dict[str, set[str]] | None = None,
) -> list[Transaction]:
    """同账本、同一标的、**未被任何存活持仓承接**、又不在 ``group`` 里的流水。

    这是「重建 / 改挂只用了一部分流水」这条风险的单一真相源。旧判据（``_sibling_gap_warning``
    / ``_sibling_count``）各写一份，且都是 ``Transaction.symbol == symbol`` 字面量比 + 只扫悬空，
    于是漏掉两类：① 缺码或补码后再也不「悬空」的卖出腿（#3127 真库 95 例）；② 裸码与带前缀
    两种写法（``127078`` vs ``SZ127078``）。

    「未被承接」是后半个判据的关键：同账本同标的还可以有**另一条正常持仓**，它名下的流水
    本来就不该算进本组缺口，否则每组合法重建都会被误报。``position_id is NULL`` 的流水算缺口
    ——它们同样会改变真实份额，只是还没人认领。

    参数取整组 ``group`` 而不只是 ``exclude_ids``：缺码流水要靠「与组内同名」才能认出来
    （``name_symbol_index`` 刻意不索引悬空流水），拆成两个参数调用方一定会漏传后者。
    """
    if not group:
        return []
    symbol = symbol if symbol is not None else (group[0].symbol or '')
    asset_type = asset_type if asset_type is not None else group[0].asset_type
    skip = {t.id for t in group}
    group_names = {(t.position_name or '').strip() for t in group} - {''}
    live_ids = {pid for (pid,) in db.query(Position.id).filter(Position.family_id == family_id)}
    index = name_index if name_index is not None else name_symbol_index(db, family_id)
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.family_id == family_id,
            Transaction.ledger_id == ledger_id,
            Transaction.quantity != 0,
        )
        .all()
    )
    return [
        t
        for t in rows
        if t.id not in skip
        and not (t.position_id is not None and t.position_id in live_ids)
        and matches_target(t, symbol, asset_type, index, group_names)
    ]


def require_single_identity(db: Session, family_id: int, txns, action: str, symbol=None) -> None:
    """写路径的统一闸门：一批流水分属多个标的时拒绝，并说明为什么不能一起做。

    三条写路径（补全 / 回补 / 重建）都要它。``symbol`` 一致不足以放行——真库
    2026-11-15 有 293 条分属 114 个标的的流水被同一次补全写成了同一个 symbol，
    只校验 symbol 会把 114 个标的的历史并成一只债。

    ``symbol`` 传 None 表示这次写入不改标的（例如只补 trade_date），没有可冲突的对象。
    名字本身歧义（一码多名）且每个名字都把 ``symbol`` 列为候选时放行（``names_include``）：
    那是「候选码不止一个」，不是「混了好几个标的」。
    """
    if symbol is None:
        return
    index = name_symbol_index(db, family_id)
    identity = identity_count(txns, index)
    if identity <= 1 or names_include(index, txns, symbol):
        return
    raise ValueError(f'选中的流水混了 {identity} 个不同标的，不能一起{action}；请按标的分别处理')
