# -*- coding: utf-8 -*-
"""交易流水展示名称的 **ID 回解析**（#2372）。

WHY
    ``transactions.position_name`` / ``transactions.account_name`` 是**冗余快照**，
    真外键是 ``position_id`` / ``ledger_id``。历史数据与多个写入路径（基金转换
    转入腿等）会漏写快照，快照落 NULL 后各列表直接显示「未知资产 / 未知账户」
    （真库实测：48 笔 ``position_name`` 为空、转换流水两个快照全 NULL）。
    名称只是展示、且账户名是**可编辑字段**，ID 才是权威——快照缺失时必须按 ID
    回解析，而不是把「快照没写」当成「数据未知」展示给用户。

口径
    - 批量两步查（``IN`` + 映射），**不做跨域 JOIN**（双库硬规则：market / user
      分引擎，路由会话按表分发，点查/批查安全）；
    - 三级回解析 ``position_name``：快照 → ``position_id`` 点查持仓 → ``position_id``
      悬空（真库实测 621 笔指向不存在的持仓）时按 ``symbol`` 点查 market 名录；
      ``account_name``：快照 → ``ledger_id`` 点查账户；
    - 只解析「快照缺失」的行；快照已在的行不进映射（调用方优先用快照，行为零变化）；
    - 纯读：不写库、不改快照——写入侧的自愈回填在 ``position_service``
      （#2372），两处分工明确，不重复实现。
"""

from typing import Dict, Iterable, Tuple

from sqlalchemy.orm import Session

from app.core.asset_types import get_asset_type_label
from app.core.constants import OwnershipStatus
from app.core.symbol_utils import strip_exchange_prefix
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction

# 账户级流水（存入 / 取出）：本来就没有持仓行，不属于「已清仓」
ACCOUNT_LEVEL_TXN_TYPES = ('deposit', 'withdraw')

# 收益类流水：券商原文常常只给金额、不给标的（同花顺「基金红利拨入」「红利入账」
# 的证券代码 / 名称两列本来就是空的，table1101.xls 实测 33 笔）。
# 值是兜底名的词尾——「红利税」与「分红」必须分开：把代扣税叫成「分红」会让人
# 以为那笔钱是到账收益（实际是流出）。
INCOME_TXN_SUFFIX: dict[str, str] = {
    'dividend': '分红',
    'dividend_cash': '分红',
    'dividend_tax': '红利税',
}


def display_asset_name(
    *,
    position_name: str | None,
    asset_type: str | None,
    txn_type: str | None,
) -> str:
    """流水行的**展示名称**：快照 → 按「资产类型 + 收益种类」兜底 → 「未知资产」。

    WHY（#2844）：券商原文不给标的的收益行，快照、持仓、名录三处都查不到名称，
    列表里就只剩「未知资产」四个字。用户看到一笔 2.10 元的「分红 / 未知资产」，
    既不知道钱从哪来，也判断不出这是数据缺失还是账目错乱——而这批行恰恰是
    **每月都有的货基收益**，只是原文没写产品。

    兜底文案只说**能确认的那部分**：类型是库里存的、收益种类是 txn_type 给的，
    都不猜具体产品（猜错比「未知」更坏：用户会拿它去对账）。
    不落库：`position_name` 仍是快照，写死一个派生名会让搜索、分组、去重一起失准。

    只对**收益类**兜底。买入 / 卖出缺名称是另一类问题（说明标的真的丢了），
    那时「未知资产」是诚实的，换成「股票买入」反而掩盖了数据缺口。
    """
    if position_name:
        return position_name
    # 代码位由前端单独渲染（`# 600000`），这里不拿它顶名称，否则同一格出现两次。
    # 大小写两套口径都要吃：`transactions.txn_type` 是小写，导入记录里的
    # `business_type` 是大写枚举（`DIVIDEND_CASH`），归一前先比会静默漏判。
    suffix = INCOME_TXN_SUFFIX.get((txn_type or '').lower())
    if suffix:
        label = get_asset_type_label(asset_type)
        return f'{label}{suffix}' if label else suffix
    return '未知资产'


# 流水行的持仓状态（设计口径，见 docs/design/transaction-flow-redesign.md §三）
POSITION_STATE_HELD = 'held'
POSITION_STATE_CLEARED = 'cleared'
POSITION_STATE_ACCOUNT = 'account'


def resolve_transaction_display_names(
    db: Session, txns: Iterable[Transaction]
) -> Tuple[Dict[int, str], Dict[int, str]]:
    """批解析流水行的展示名称。

    Args:
        db: 路由会话（按表分发到 market / user 引擎）。
        txns: 本页/本批的 Transaction ORM 行（通常已按家庭过滤）。

    Returns:
        ``(position_name_by_txn_id, account_name_by_txn_id)``——仅含**回解析出的**
        键；调用方写法 ``t.position_name or pos.get(t.id) or '未知资产'``。
    """
    txn_list = list(txns)
    pos_by_txn: Dict[int, str] = {}
    ledger_by_txn: Dict[int, str] = {}
    if not txn_list:
        return pos_by_txn, ledger_by_txn

    # ── position_name：快照缺失的行才解析 ──
    missing_pos = [t for t in txn_list if not t.position_name]
    pos_ids = {t.position_id for t in missing_pos if t.position_id}
    if pos_ids:
        id_to_name = {
            pid: pname
            for pid, pname in db.query(Position.id, Position.name).filter(Position.id.in_(pos_ids)).all()
            if pname
        }
        for t in missing_pos:
            name = id_to_name.get(t.position_id) if t.position_id else None
            if name:
                pos_by_txn[t.id] = name

    # position_id 悬空/无持仓行时，按 symbol 点查 market 名录兜底（代码比名称稳）。
    dangling = [t for t in missing_pos if t.id not in pos_by_txn and t.symbol]
    if dangling:
        codes = {strip_exchange_prefix(str(t.symbol)) for t in dangling}
        codes.discard('')
        if codes:
            code_to_name = {
                code: name
                for code, name in db.query(Fund.fund_code, Fund.name).filter(Fund.fund_code.in_(codes)).all()
                if name
            }
            for t in dangling:
                name = code_to_name.get(strip_exchange_prefix(str(t.symbol)))
                if name:
                    pos_by_txn[t.id] = name

    # ── account_name：快照缺失且 ledger_id 有值的行按 ID 点查账户 ──
    missing_ledger = [t for t in txn_list if not t.account_name and t.ledger_id]
    if missing_ledger:
        ledger_ids = {t.ledger_id for t in missing_ledger}
        id_to_name = {
            lid: lname
            for lid, lname in db.query(Ledger.id, Ledger.name).filter(Ledger.id.in_(ledger_ids)).all()
            if lname
        }
        for t in missing_ledger:
            name = id_to_name.get(t.ledger_id)
            if name:
                ledger_by_txn[t.id] = name

    return pos_by_txn, ledger_by_txn


def resolve_transaction_asset_types(db: Session, txns: Iterable[Transaction]) -> Dict[int, str]:
    """回解析流水行的**资产类型**（#2712）——快照为 NULL 时价格精度无从判断。

    WHY：``transactions.asset_type`` 与 ``position_name`` 一样是**冗余快照**
    （``Column(String(20), nullable=True, default=None)``），历史导入 / 基金转换流水
    常漏写。前端价格列走 ``pricePrecision(asset_type)``：基金 4 位、其余 2 位，
    **缺失时按证券口径 2 位**（``utils/pricePrecision.ts`` 的刻意取舍）。于是基金申购
    净值 ``1.2200`` 在「类型快照为空」的流水上显示成 ``1.22``——用户报的是
    「申购价格只有 2 位小数」，根因是类型缺失，不是格式化写错。

    口径与名称回解析一致：只处理缺失行，``position_id`` 点查持仓，悬空时按 ``symbol``
    查基金名录（命中即为 ``fund``）。纯读，不写库。

    Returns:
        ``{txn_id: asset_type}``——仅含回解析出的键；调用方写法
        ``t.asset_type or resolved.get(t.id)``。
    """
    txn_list = [t for t in txns if not t.asset_type]
    if not txn_list:
        return {}

    resolved: Dict[int, str] = {}
    pos_ids = {t.position_id for t in txn_list if t.position_id}
    if pos_ids:
        id_to_type = {
            pid: ptype
            for pid, ptype in db.query(Position.id, Position.asset_type).filter(Position.id.in_(pos_ids)).all()
            if ptype
        }
        for t in txn_list:
            ptype = id_to_type.get(t.position_id) if t.position_id else None
            if ptype:
                resolved[t.id] = ptype

    # 持仓已删（position_id 悬空）：按代码查基金名录，命中即 fund。
    dangling = [t for t in txn_list if t.id not in resolved and t.symbol]
    if dangling:
        codes = {strip_exchange_prefix(str(t.symbol)) for t in dangling}
        codes.discard('')
        if codes:
            known = {code for (code,) in db.query(Fund.fund_code).filter(Fund.fund_code.in_(codes)).all()}
            for t in dangling:
                if strip_exchange_prefix(str(t.symbol)) in known:
                    resolved[t.id] = 'fund'

    return resolved


def resolve_transaction_position_states(db: Session, txns: Iterable[Transaction]) -> Dict[int, str]:
    """流水行的持仓状态：``held`` / ``cleared`` / ``account``（单一判据出处）。

    ## 为什么不是「`position_id` 是不是 null」

    设计 v1.0 初稿按 ``position_id === null`` 判「已清仓」，这在今天的库上是**错的**：
    #2343 起清仓**不再删行**（``ownership_status='cleared'``，锚点四列原样留存），
    所以「已清仓」的流水 ``position_id`` 依然有值。只看 null 会让「已清仓」胶囊
    几乎永不出现——而它比不显示更糟：用户会以为这个标记坏了，进而怀疑整列数据。

    反过来的假阳性也在：``position_id`` 非空但持仓行确实已被删（#2343 之前的
    历史数据，真库实测 621 笔悬空 id），那些流水**就是**已清仓，判成 held 会让
    「持仓还在、只是这笔流水看着怪」的错觉长期留存。

    ## 判据（顺序即优先级）

    1. 有 ``position_id`` → 查持仓 ``ownership_status``：``cleared`` → ``cleared``；
       ``active`` / ``shadow`` → ``held``；**id 悬空**（行已删）→ ``cleared``；
    2. 无 ``position_id`` 且 ``txn_type ∈ (deposit, withdraw)`` → ``account``
       （资金流水本来没有持仓行，不是「被删了」）；
    3. 无 ``position_id`` 其余 → ``cleared``（历史「清仓即删行」时期的孤儿流水）。

    ## 为什么必须服务端下发

    判据依赖 ``ownership_status`` 与「行是否存在」两件事，前端只有 ``position_id``。
    让前端按 null 猜，就是把「清仓不删行」这条后端决策抄成第二份真相源——它已经在
    #2343 变过一次口径，前端那份必然滞后。

    Returns:
        ``{txn_id: 'held' | 'cleared' | 'account'}``——**每行都有一项**（含无持仓的），
        调用方直接 ``states[t.id]``，不要再用 ``.get()`` 兜底猜默认值。
    """
    txn_list = list(txns)
    if not txn_list:
        return {}

    pos_ids = {t.position_id for t in txn_list if t.position_id}
    status_by_position: Dict[int, str] = {}
    if pos_ids:
        # 批量一次 IN：与命名解析同法（双库规则下不做跨域 JOIN，点查/批查安全）
        status_by_position = {
            pid: (status or OwnershipStatus.ACTIVE.value)
            for pid, status in db.query(Position.id, Position.ownership_status).filter(Position.id.in_(pos_ids)).all()
        }

    states: Dict[int, str] = {}
    for t in txn_list:
        if t.position_id:
            status = status_by_position.get(t.position_id)
            # status is None = 持仓行不存在（悬空 id）：历史删行的清仓，归 cleared
            states[t.id] = (
                POSITION_STATE_CLEARED if status in (None, OwnershipStatus.CLEARED.value) else POSITION_STATE_HELD
            )
        elif t.txn_type in ACCOUNT_LEVEL_TXN_TYPES:
            states[t.id] = POSITION_STATE_ACCOUNT
        else:
            states[t.id] = POSITION_STATE_CLEARED
    return states
