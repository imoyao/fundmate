# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/10 21:46
# File : position_service.py

"""
持仓业务逻辑服务层。

职责：
- 处理买入/存入的持仓合并与创建
- 处理卖出/取出的数量扣减与清空
- 处理分红流水记录
- 所有方法接收 SQLAlchemy Session 与原始数据字典
- 业务异常通过 ValueError 抛出，由视图层捕获并转为 HTTP 异常

#2873 拆分进度（god module 逐簇下沉，主模块保留核心命令与 facade）：
- 读/展示簇 → `position_display`；写侧共用原语 → `position_write_support`；
- 孤儿流水簇 → `position_orphan_flows`（`process_orphan_*` 在此仅为薄壳）；
- 买入/存入命令 → `position_buy_command`（`process_buy_or_deposit` 在此仅为 facade）。
"""

import uuid
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import (
    AnchorKind,
    OwnershipStatus,
    PositionSource,
)
from app.core.money import Money
from app.core.symbol_utils import normalize_by_venue
from app.core.venues import resolve_venue
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta
from app.domains.positions.state import (
    derive_state_from_txns,
    is_covered_by_anchor,
    mark_position_cleared,
)
from app.domains.transactions.dates import order_by_effective_day
from app.domains.transactions.models import Transaction

# #2873 第三抽：孤儿流水簇已下沉到 position_orphan_flows，此处 re-export 保 facade ——
# 内部调用点（买入的现金转移、建仓/卖出的孤儿挂回）与外部导入
# （scripts/fix_orphan_money_fund_reattach、sync/jobs/orphan_backfill_job、测试）一行不改。
from app.services import async_backfill, position_orphan_flows
from app.services.fund_utils import is_money_fund_symbol
from app.services.import_records import compute_position_hash
from app.services.institution_resolver import resolve_sales_institution_id
from app.services.pnl_service import compute_redeem_realized_cents, compute_sell_realized_cents

# issue #2873 安全首抽：读/展示簇已下沉到 position_display，此处仅 re-export 保 facade。
from app.services.position_buy_command import (  # noqa: F401
    _ALLOWED_POSITION_FIELDS,
    _BALANCE_ONLY_ASSET_TYPES,
    _get_default_notes,
    run_buy_or_deposit,
)
from app.services.position_display import (  # noqa: F401
    build_position_list_impl,
    list_position_transactions,
    query_transactions_by_identity,
    resolve_ledger_change,
    resolve_portfolio_change,
    serialize_position_transaction,
)
from app.services.position_orphan_flows import (  # noqa: F401
    BondRedeemOutcome,
    _create_cash_transfer_transaction,
    _create_orphan_transaction,
    _reattach_orphan_flows,
    find_orphan_cash_flows,
)

# #2873 第二抽：写侧共用原语已下沉到 position_write_support，此处 re-export 保 facade，
# 调用点与外部导入（conversion_service / repair_snapshot_double_count 等）一行不改。
from app.services.position_write_support import (  # noqa: F401
    _FEE_BREAKDOWN_COLUMNS,
    _FEE_BREAKDOWN_KEYS,
    _LEGACY_SINGLE_FAMILY_ID,
    _SPECIFIC_ASSET_TYPES,
    _fee_breakdown_kwargs,
    _find_existing_position,
    _find_position_by_identity,
    _get_asset_type,
    _lookup_unit_nav,
    _resolve_confirm_date,
    _resolve_family_id,
    _resolve_fund_name_by_code,
    _resolve_ledger_name_by_id,
    _txn_effective_date,
)
from app.services.trading import TransactionService, validate_sell
from app.services.watchlist_service import (
    ensure_watchlist_for_positions,
    reconcile_watchlist_status,
)


def _silent_ensure_watchlist(db: Session, family_id: int, symbol: str) -> None:
    """买入/持仓快照后：静默补齐 HOLDING 自选记录（#1458 后续：持仓即自选）。

    后台静默失败——绝不影响主交易链路，也不向用户暴露错误。
    """
    try:
        ensure_watchlist_for_positions(db, family_id, [symbol])
    except Exception:
        # loguru 只认 {}：用 %s 会导致参数被静默丢弃，日志里看不到 family/symbol（#1491 评审）
        logger.warning('持仓自动入自选失败（已静默）: family={} symbol={}', family_id, symbol)


def _silent_reconcile_watchlist(db: Session, family_id: int, symbol: str) -> None:
    """卖出/重算后：静默对齐自选状态（有持仓→HOLDING，无持仓→WATCHING）。

    后台静默失败——绝不影响主交易链路，也不向用户暴露错误。
    """
    try:
        reconcile_watchlist_status(db, family_id, [symbol])
    except Exception:
        # 同 _silent_ensure_watchlist：loguru 用 {} 占位（#1491 评审）
        logger.warning('持仓状态对齐自选失败（已静默）: family={} symbol={}', family_id, symbol)


def auto_purchase_money_fund(
    db: Session,
    ledger_id: Optional[int],
    amount_cents: int,
    trade_date=None,
    confirm_date=None,
    family_id: Optional[int] = None,
) -> None:
    """#1137 卖出/赎回回款自动申购账户绑定的类现金产品（「余额宝」）。

    仅在账户显式开启 `auto_purchase_money_fund` 且绑定了有效货基时执行——
    遵循「用户不操作，系统不代劳」，开关由用户在账户设置里自行开启。

    - 回款净额 <= 0 时不申购；
    - 生成**孤儿流水**（asset_type='money_fund'）：货基不建持仓，与导入器、
      `money_fund_income` 的既有口径一致（货基市值按流水净额计入总资产）；
    - 调用方须自行排除货基 / 逆回购自身的卖出，避免「赎回 → 自动申购」死循环
      （货基卖出在 `process_orphan_sell_or_withdraw` 里走现金转移分支，不进入本函数）。

    失败（绑定产品缺失等）仅告警不抛出：自动申购是增值行为，不应阻断卖出主流程。
    """
    # #1305 #22：缺省不再硬编码 1，走与写入链路一致的解析（入参 → 上下文 → 遗留口径）
    family_id = family_id or _resolve_family_id({})
    if not ledger_id or amount_cents <= 0:
        return
    ledger = db.query(Ledger).filter_by(id=ledger_id, family_id=family_id).first()
    if not ledger or not ledger.auto_purchase_money_fund or not ledger.linked_money_fund_id:
        return
    fund = db.get(Fund, ledger.linked_money_fund_id)
    if not fund:
        logger.warning(f'账户 {ledger_id} 绑定的类现金产品 {ledger.linked_money_fund_id} 不存在，跳过自动申购')
        return
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=fund.fund_code,
        txn_type='buy',
        trade_date=trade_date,
        confirm_date=confirm_date,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=amount_cents,
        status='success',
        position_name=fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='卖出回款自动申购类现金产品',
        entry_status='orphan',
        family_id=family_id,
    )


# 录入阶段已显式给出的具体类型，直接信任，不再做代码推断（避免误伤基金等）
# bank_wealth 必须在这里：银行理财没有可推断的代码段，漏了它显式传入的 asset_type 会被


def _is_reinvest(data: dict) -> bool:
    """
    是否为「可执行」的红利再投资：类型命中 dividend_reinvest，且具备申购所需的份额与价格。

    份额必填；净值缺失时允许用 金额/份额 反推（由 process_dividend_reinvest 执行）。
    数据不全时返回 False，调用方降级按现金分红处理，避免一条脏数据阻断整批导入。
    """
    if data.get('op_type') != 'dividend_reinvest':
        return False

    shares = data.get('quantity') or 0
    nav = data.get('nav') or 0
    amount = data.get('dividend_amount') or 0

    if shares <= 0:
        logger.warning('红利再投资缺少份额，降级按现金分红处理')
        return False
    if nav <= 0 and amount <= 0:
        logger.warning('红利再投资缺少净值且无法由金额反推，降级按现金分红处理')
        return False
    return True


def _create_dividend_cash_txn(
    db: Session, data: dict, position: Optional[Position], link_group_id: str, entry_status: str = 'orphan'
) -> None:
    """红利再投资的第一条流水：分红现金（txn_type='dividend'，份额为 0，link_group_id 与申购流水配对）。

    position 为 None 时记孤儿流水（无关联持仓）。entry_status 默认 orphan，
    双流水场景由调用方传 'success'。
    """
    base_hash = data.get('import_hash')
    dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
    TransactionService.create(
        db=db,
        position_id=position.id if position else None,
        txn_type='dividend',
        symbol=position.symbol if position else data.get('symbol'),
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=_get_asset_type(data),
        link_group_id=link_group_id,
        quantity=0,
        price=0,
        fee=0,
        amount=Money.yuan_to_cents(dividend_amount),
        # 红利再投资的分红入账同样计入已实现盈亏（#1183）：与随后的申购流水（记投入、
        # 抬高成本基数）一进一出，对总盈亏净额为 0，与 XIRR「reinvest 记流出」自洽
        realized_pnl=Money.yuan_to_cents(dividend_amount),
        status='success',
        position_name=position.name if position else data.get('name', ''),
        account_name=position.account_name if position else data.get('account_name', ''),
        ledger_id=position.ledger_id if position else data.get('ledger_id'),
        notes=data.get('notes') or '红利再投资（分红入账）',
        import_hash=base_hash,
        entry_status=entry_status,
        family_id=_resolve_family_id(data),
        # #1232 决策 11：红利再投资分红流水来源透传
        source=data.get('source'),
    )
    db.flush()


def _build_reinvest_buy_data(data: dict, position: Optional[Position], link_group_id: str) -> dict:
    """构造红利再投资第二条流水（申购）的业务字典：price=净值，quantity=再投份额。"""
    nav = data.get('nav', data.get('avg_price', 0))
    dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
    shares = data.get('quantity') or (dividend_amount / nav if nav else 0)
    base_hash = data.get('import_hash')
    # 申购流水使用独立幂等键，避免与分红流水撞 UNIQUE(ledger_id, import_hash)；
    # 分红流水保留原始 import_hash 承担记录级去重（导入路径同键重导整体跳过）。
    buy_hash = None if not base_hash else f'{base_hash}#reinvest'
    # 资产类型 / 场所**必须取自目标持仓**（#1662 修正）：本笔是「对既有持仓的红利再投资」，
    # 品种与场所由持仓决定。原实现取 _get_asset_type(data)，而再投资请求体里没有 symbol /
    # type，推断结果恒为默认 'stock' —— 于是这笔申购被当场内标的归一到 EXCHANGE，
    # 与持仓（场外基金，OTC）场所不符 → _find_existing_position 查不到既有持仓 →
    # 另建一条重复持仓，份额也不再增加。
    asset_type = position.asset_type if position and position.asset_type else _get_asset_type(data)
    return {
        'symbol': position.symbol if position else data.get('symbol'),
        'name': position.name if position else data.get('name'),
        'market': data.get('market', 'CN_A'),
        'asset_type': asset_type,
        'venue': resolve_venue(None, asset_type),  # 持仓场所即本笔场所（#1662）
        'account_name': position.account_name if position else data.get('account_name', ''),
        'ledger_id': position.ledger_id if position else data.get('ledger_id'),
        'quantity': shares,
        'avg_price': nav,
        'currency': data.get('currency', 'CNY'),
        'trade_date': data.get('trade_date'),
        'confirm_date': data.get('confirm_date'),
        'fee': data.get('fee', 0),
        'notes': data.get('notes') or '红利再投资（申购）',
        'op_type': 'buy',
        'link_group_id': link_group_id,
        'import_hash': buy_hash,
        'family_id': _resolve_family_id(data),
        'position_id': position.id if position else None,
        # #1232 决策 11：红利再投资申购流水来源透传（走 process_buy_or_deposit 落库）。
        # 缺失时兜底 manual——Position.source 非空校验拒绝 None，而流水 source 缺省可空。
        'source': data.get('source') or PositionSource.MANUAL.value,
    }


def _resolve_money_fund_flag(symbol: str, asset_type: str | None, hint=None) -> bool:
    """写路径货基判定（#863 / #1661）：显式 hint > money_fund > 显式非基金类型 > 名录/代码段。

    reverse_repo 不是货基（即使与货基同属现金等价物聚合桶），不落 is_money_fund。

    **#1661**：显式 `stock` / `etf` / `bond` 等非基金类型一律 **False**，绝不落回
    名录/代码段解析。原因是场内证券与场外基金**共用同一 6 位数字空间**：
    `000651` 既是格力电器（深市股票）也是某只货基、`000725` 京东方Ａ 与大成添利宝
    货币B 同号、`110081` 既是闻泰转债也在 `1[01]xxxx` 段内。原实现把 `asset_type`
    丢掉后交给「只看数字」的 `is_money_fund_symbol`，等于让基金段反推证券品种，
    于是股票/可转债持仓被标记为货基 → `sync/jobs/position_price_job.py:293` 见到该
    标记即按面值 1.0000 回写 `current_price`，**持仓市值塌成「份额数」**。
    """
    if hint is not None:
        return bool(hint)
    if asset_type == 'money_fund':
        return True
    if asset_type == 'reverse_repo':
        return False
    if asset_type and asset_type != 'fund':
        # 显式非基金类型：名录/代码段只对「基金」有意义
        return False
    return is_money_fund_symbol(symbol)


def compute_anchored_state(db: Session, position: Position) -> tuple[int, int]:
    """按锚点推导持仓份额与成本均价（**唯一**的份额派生入口）。

    口径：
        有锚点 → quantity = snapshot_quantity + Σ(归属日 > snapshot_date 的流水净额)
        无锚点 → quantity = Σ(全部流水净额)          # 旧口径，保持向后兼容

    成本：`快照成本额 + 锚点后买入成本额`，除以 `快照份额 + 锚点后买入份额`。
    卖出/取出不改成本额（移动加权，与 `process_buy_or_deposit` 一致）。

    ## 为什么必须是「唯一入口」

    份额有三条写路径（快照导入 SET / 买卖 INCR / 净值回填后重算），只要有一条不认锚点，
    它就会把另外两条的结果覆盖掉。`nav_backfill_job` 就是活例子：它调
    `recompute_position_from_transactions`，若那里走旧口径，用户修好的份额会在下一次
    官方净值回填时被静默打回「全量流水」——修复当场失效且无报错。

    ## 锚点的边界（刻意保守）

    - 归属日 `<= snapshot_date` 的流水视为「已被快照包含」，不再计入。按 `confirm_date`
      而非 `trade_date` 切分：基金份额在确认日（T+1）才真实变动，快照反映的是份额登记
      状态，用下单日会把 T+1 确认的交易误判为「未包含」而重复加一次。
    - 归属日无法判定的流水：排除 + WARNING。宁可少算（可由对账工作台兜底），
      也不要重复计（用户看不出来）。
    - `ownership_status == 'shadow'`（E账户影子行）**不走锚点**：影子记录只写
      `position_import_meta`，没有 positions 层锚点，走锚点会把对账链路搅乱。
      `cleared`（已清仓保留行，#2343）**要走锚点**——锚点是它唯一残存的份额事实源，
      排除它等于清仓后删行旧病复发。

    返回 (净份额 min_unit, 成本均价 price_unit)。净份额可为 0 或负（由调用方决定删行）。
    """
    has_anchor = (
        position.ownership_status != OwnershipStatus.SHADOW.value
        and position.snapshot_quantity is not None
        and position.snapshot_date is not None
    )
    query = db.query(Transaction).filter(Transaction.position_id == position.id)
    if not has_anchor:
        txns = order_by_effective_day(query, descending=False).all()
        return derive_state_from_txns(txns, 0, 0)

    base_qty = int(position.snapshot_quantity)
    # 快照成本额（分）：份额 × 快照均价。snapshot_avg_price 必须与份额同批落库，
    # 否则拿 avg_price 顶替会得到「被流水加权过」的价，成本永久偏。
    base_cost = Money.multiply_price_quantity(int(position.snapshot_avg_price or 0), base_qty)
    included = []
    for t in order_by_effective_day(query, descending=False).all():
        d = _txn_effective_date(t)
        if d is None:
            if t.quantity:
                logger.warning(
                    '锚点重算忽略无日期的份额流水: position={} txn={} type={} qty={}',
                    position.id,
                    t.id,
                    t.txn_type,
                    t.quantity,
                )
            continue
        if d > position.snapshot_date:
            included.append(t)
    return derive_state_from_txns(included, base_qty, base_cost)


def _assert_anchor_accepts(
    existing: Position,
    snapshot_date,
    incoming_kind: str,
    *,
    allow_rewind: bool = False,
) -> None:
    """锚点时间轴守卫：**时间不可倒流**，同日人工值不被同日外部数据覆盖。

    规则来源（2026-10-18 讨论定稿）：
    - `<` 更旧的快照一律拒绝 —— 允许回退会让当前准确的锚点被历史数据打回旧值，
      中间这段流水差异会变成无从归因的噪声；
    - `==` 同日：external 可覆盖（用户发现导错了重导一次），但 **manual 优先**——
      用户当天已显式校准过，同日的外部数据不更权威，否则「手工校正」会被
      下一次同日导入静默抹掉；
    - `>` 更新：正常推进锚点。

    `allow_rewind=True` 仅供对账工作台 `kind='set'` 使用：那是用户显式要求设定持仓，
    语义是「人工校准」而非「导入旧快照」，不属于本条守卫的管辖范围。
    """
    if allow_rewind or existing.snapshot_date is None:
        return
    # 已清仓行（#2343）的旧锚点只是上一轮的历史残留，对新一轮周期没有「当前值」
    # 意义（quantity 已为 0）。重新导入快照 = 开启新一轮，不参与时间轴比较——
    # 否则用户无法为新周期导入比上一轮更早的快照（如清仓后导一份 7 月的补录快照）。
    # active 行不受影响，时间不可倒流的守卫照常生效。
    if existing.ownership_status == OwnershipStatus.CLEARED.value:
        return
    if snapshot_date < existing.snapshot_date:
        raise ValueError(
            f'快照日 {snapshot_date} 早于该持仓当前锚点 {existing.snapshot_date}，拒绝用更旧的数据覆盖。'
            '如需按历史快照重算，请先清空/重置该账户后再导入。'
        )
    if (
        snapshot_date == existing.snapshot_date
        and existing.anchor_kind == AnchorKind.MANUAL.value
        and incoming_kind != AnchorKind.MANUAL.value
    ):
        raise ValueError(
            f'该持仓在 {snapshot_date} 已有「人工校准」锚点，同日的外部快照不会覆盖人工值。'
            '如需以外部数据为准，请导入更新日期的快照。'
        )


def _reinvest_dual_flow(db: Session, data: dict, position: Position, link_group_id: str) -> None:
    """已知持仓上的红利再投资双流水：分红现金 + 按净值申购（合并入持仓，份额增加）。"""
    nav = data.get('nav', data.get('avg_price', 0))
    dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
    shares = data.get('quantity') or 0
    # 双向兜底：只给净值→按「金额/净值」算份额；只给份额→按「金额/份额」反推净值
    if shares <= 0 and nav > 0 and dividend_amount > 0:
        shares = dividend_amount / nav
    if nav <= 0 and shares > 0 and dividend_amount > 0:
        nav = dividend_amount / shares
    if nav <= 0 or shares <= 0:
        raise ValueError('红利再投资净值(nav)或再投份额无效')
    # 反推结果写回 data，确保下方 _build_reinvest_buy_data 取到一致的净值/份额
    data['nav'] = nav
    data['quantity'] = shares
    _create_dividend_cash_txn(db, data, position, link_group_id, entry_status='success')
    db.flush()
    PositionService.process_buy_or_deposit(db, _build_reinvest_buy_data(data, position, link_group_id))


class PositionService:
    # ── 公开方法 ──────────────────────────────────────────

    @staticmethod
    def upsert_from_holding(
        db: Session,
        data: dict,
        ownership_status: str = 'active',
        allow_anchor_rewind: bool = False,
    ) -> Position:
        """持仓快照 upsert（#1012）：以 (ledger_id, symbol) 为业务键写**锚点**，不直接写份额。

        与 process_buy_or_deposit 的本质区别（持仓 vs 交易流水）：
        - 快照是某日点位的绝对值：`snapshot_quantity / snapshot_avg_price / snapshot_date`
          按快照**整条替换**，不累加；
        - `quantity` 不再是「快照值」本身，而是 `compute_anchored_state` 派生出来的结果
          （快照 + 快照日之后的流水）。这正是修复「份额被快照与流水重复累加」的关键：
          快照值只作为基线存在，不再与流水共享同一个变量；
        - **绝不调用 TransactionService.create** —— 导入持仓不产生交易流水；
        - 溯源元数据（基金管理人/平台账号/分红方式/市值等）写入 position_import_meta（1:1 upsert）。

        ## 锚点时间轴规则（时间不可倒流）

        | 新快照日 vs 现有锚点 | external 来源 | manual 来源 |
        |---|---|---|
        | `<`（更旧） | **拒绝**（除非 allow_anchor_rewind） | 同左 |
        | `==`（同日） | 允许覆盖 | **拒绝**（同日人工值优先于同日外部数据） |
        | `>`（更新） | 接纳并推进锚点 | 接纳并推进锚点 |

        开放 `allow_anchor_rewind` 的唯一场景是对账工作台的 `kind='set'`：用户显式要求把
        持仓设成某个值，这属于「人工校准」，不是「导入旧快照」。

        ownership_status 参数（E账户对账扩展，#1021）：
        - 'active'（默认）：参与总资产，渠道正常持仓；
        - 'shadow'：仅对账不参与总资产（影子记录走专用 upsert，不调用本方法）。

        data 关键字段：
            symbol / name / asset_type / ledger_id / account_name / quantity(份) /
            avg_price(元,缺失降级为 current_price 近似) / current_price(元) /
            snapshot_date(date,缺失降级为落库当日) / anchor_kind(external|manual) /
            currency / source / source_broker / source_import_id / family_id /
            meta(dict: fund_manager/share_class/fund_account/trade_account/
            dividend_preference/market_value)
        """
        symbol = data.get('symbol', '')
        ledger_id = data.get('ledger_id')
        family_id = _resolve_family_id(data)
        if not symbol or not ledger_id:
            raise ValueError('持仓快照导入必须提供 symbol 与 ledger_id')

        # venue（#1662）：显式入参优先，缺失按 asset_type 推断（持仓快照本无场所维度，只能兜底）。
        # 落库前把 symbol 收敛到该场所的唯一形态，避免同一标的并存 `SZ004369` / `004369`
        # 两种写法——positions 的唯一约束是字面量 UNIQUE(ledger_id, symbol)，拦不住。
        venue = resolve_venue(data.get('venue'), data.get('asset_type'))
        if venue:
            symbol, _venue_market, _ = normalize_by_venue(symbol, venue)
            data['symbol'] = symbol

        qty = data.get('quantity', 0) or 0
        if qty <= 0:
            raise ValueError('数量必须大于 0')

        # 成本均价：优先显式 avg_price，缺失降级为当前净值近似（用户已确认）
        price_yuan = data.get('avg_price') or data.get('current_price') or 0
        if price_yuan <= 0:
            raise ValueError('成本均价与当前净值均缺失，无法确定价格')

        qty_units = Money.shares_to_min_unit(qty)
        price_units = Money.yuan_to_price_units(price_yuan)

        # 快照日：优先 snapshot_date，缺失降级为落库当日（规范 §3.3）
        raw_snap = data.get('snapshot_date') or date.today()
        snapshot_date = raw_snap if isinstance(raw_snap, date) else datetime.fromisoformat(str(raw_snap)).date()

        incoming_kind = data.get('anchor_kind') or AnchorKind.EXTERNAL.value
        if isinstance(incoming_kind, AnchorKind):
            incoming_kind = incoming_kind.value

        src = data.get('source', PositionSource.E_ACCOUNT.value)
        import_hash = data.get('import_hash') or compute_position_hash(src, ledger_id, symbol, snapshot_date)

        # 查找现有持仓（venue 感知归一去重，SET 语义定位；#1662）
        existing = _find_existing_position(db, ledger_id=ledger_id, family_id=family_id, symbol=symbol, venue=venue)

        if existing:
            _assert_anchor_accepts(
                existing,
                snapshot_date,
                incoming_kind,
                allow_rewind=allow_anchor_rewind,
            )
            # 锚点 SET：份额/成本价/日期三者必须同批写入（缺 snapshot_avg_price 会让
            # 重算拿不到快照原价，成本被永久稀释）。
            existing.snapshot_quantity = qty_units
            existing.snapshot_avg_price = price_units
            existing.snapshot_date = snapshot_date
            existing.anchor_kind = incoming_kind
            # quantity 先按快照值占位；下方 reattach 孤儿流水后用锚点重算覆盖。
            existing.quantity = qty_units
            existing.avg_price = price_units
            existing.current_price = price_units
            existing.confirm_date = snapshot_date
            existing.name = data.get('name') or existing.name
            existing.account_name = data.get('account_name') or existing.account_name
            existing.currency = data.get('currency') or existing.currency
            existing.import_hash = import_hash
            existing.source = src
            existing.source_broker = data.get('source_broker')
            # 对账扩展：调用方显式传 shadow 时同步更新（防渠道记录被误标为影子）
            if existing.ownership_status != ownership_status:
                existing.ownership_status = ownership_status
            position = existing
        else:
            # 影子行（ownership_status != active）不落锚点：它只在 position_import_meta 层
            # 有日期，若写 positions 层锚点，重算会把对账影子链路搅进派生逻辑。
            write_anchor = ownership_status == 'active'
            position = Position(
                symbol=symbol,
                name=data.get('name') or symbol,
                market=data.get('market', 'CN_A'),
                asset_type=data.get('asset_type', 'fund'),
                ledger_id=ledger_id,
                account_name=data.get('account_name', ''),
                quantity=qty_units,
                avg_price=price_units,
                current_price=price_units,
                currency=data.get('currency', 'CNY'),
                confirm_date=snapshot_date,
                allocation=data.get('allocation', 'longterm'),
                import_hash=import_hash,
                source=src,
                source_broker=data.get('source_broker'),
                ownership_status=ownership_status,
                family_id=family_id,
                snapshot_quantity=qty_units if write_anchor else None,
                snapshot_avg_price=price_units if write_anchor else None,
                snapshot_date=snapshot_date if write_anchor else None,
                anchor_kind=incoming_kind if write_anchor else None,
            )
            db.add(position)

        db.flush()

        # #863 口径 A：快照持仓也落货基冗余判定（SET 覆盖，聚合分类归「现金」桶）
        position.is_money_fund = _resolve_money_fund_flag(symbol, position.asset_type, data.get('is_money_fund'))

        # 溯源元数据 1:1 upsert（position_import_meta，保留末次快照的溯源信息）
        meta = data.get('meta') or {}
        meta_row = db.query(PositionImportMeta).filter_by(position_id=position.id).first()
        if meta_row is None:
            meta_row = PositionImportMeta(position_id=position.id, family_id=family_id)
            db.add(meta_row)
        meta_row.symbol = symbol
        meta_row.ledger_id = ledger_id
        meta_row.snapshot_date = snapshot_date
        meta_row.source = src
        meta_row.source_import_id = data.get('source_import_id')
        meta_row.source_broker = data.get('source_broker')
        meta_row.fund_manager = meta.get('fund_manager')
        meta_row.share_class = meta.get('share_class')
        meta_row.fund_account = meta.get('fund_account')
        meta_row.trade_account = meta.get('trade_account')
        meta_row.dividend_preference = meta.get('dividend_preference')
        meta_row.market_value = (
            Money.yuan_to_cents(meta['market_value']) if meta.get('market_value') is not None else None
        )
        meta_row.sales_institution_id = resolve_sales_institution_id(db, data.get('source_broker'))
        db.flush()

        # #863 口径 A 写入层互斥 + #1657 修复：无论 is_money_fund 快照判定如何，都尝试挂回
        # 同 (ledger, symbol) 孤儿货基/逆回购流水（幂等；非货基持仓无对应孤儿流水则无操作），
        # 避免快照 is_money_fund 判定不一致时漏挂回导致资金双计。
        _reattach_orphan_flows(db, ledger_id, symbol, position.id, family_id)

        # 锚点派生：quantity 不再等于快照值，而是「快照 + 快照日之后的流水」。
        # 必须在 _reattach_orphan_flows **之后**：刚挂回的孤儿流水也要参与派生，
        # 否则它们在下一轮重算时才会被计入，中间这一段时间市值偏小。
        if position.snapshot_quantity is not None:
            net_qty, derived_avg = compute_anchored_state(db, position)
            if net_qty < 0:
                # 语义矛盾：快照说还有份额，但快照日之后的流水已把它卖成负数。
                # 导入路径不做「删行」这种激进动作（那是卖出路径的职责），钳到 0 并告警，
                # 由对账工作台暴露给用户。
                logger.warning(
                    '快照锚点派生出负份额，已钳为 0: position={} symbol={} net={} anchor={} date={}',
                    position.id,
                    symbol,
                    Money.min_unit_to_shares(net_qty),
                    Money.min_unit_to_shares(position.snapshot_quantity),
                    position.snapshot_date,
                )
                net_qty = 0
            position.quantity = net_qty
            # 成本只在能派生出正份额时采用；0 份额保留快照成本价，避免 avg_price 被清成 0
            # 后前端显示「成本 0 元」。
            if net_qty > 0:
                position.avg_price = derived_avg
            db.flush()

        try:
            async_backfill.trigger_backfill('fund', symbol)
        except Exception:
            pass

        # #1458 后续：持仓快照导入即入自选（静默，失败不影响主链路）
        _silent_ensure_watchlist(db, family_id, symbol)
        return position

    @staticmethod
    def process_buy_or_deposit(db: Session, data: dict, force_create_position: bool = False) -> Optional[Position]:
        """执行买入或存入操作，返回更新或新建的持仓实例。

        #2873 第四抽：实现已下沉到 `position_buy_command`（解析 → 落持仓 → 落流水三段），
        此处只保留 facade，签名与行为逐字不变。`force_create_position`（#1233 决策 5）
        的语义（货基/逆回购在导入路径只记流水、记一笔时照常建仓）见该模块 docstring。
        """
        return run_buy_or_deposit(db, data, force_create_position=force_create_position)

    @staticmethod
    def process_sell_or_withdraw(
        db: Session, data: dict, skip_lot_check: bool = False, auto_purchase: bool = True
    ) -> Optional[Position]:
        """
        执行卖出或取出操作。
        成功返回更新后的持仓；清仓（份额减至 0）时**行保留**（#2343：改为
        `ownership_status='cleared'` + `cleared_at`，锚点与成本基线原样留存），
        但本方法仍返回 None——与既有调用方「None = 已清仓」的契约保持一致，
        调用方零改动。行已不在「当前持仓」视图（`exclude_cleared` 过滤）。

        auto_purchase（#1137 的显式开关，默认 True 保持既有行为）：
        - True：普通卖出走「回款自动申购账户绑定的类现金产品」；
        - False：**基金转换**专用——转换的退款去向由 conversion_service 自行落
          第三条腿（类现金或账户现金，用户显式选择），若此处再自动申购一笔，
          同一笔回款会被记两次（资产虚增）。关掉的是「代劳副作用」，不是任何
          校验（validate_sell 照跑）。
        """
        position_id = data['position_id']
        op_type = data['op_type']
        qty_shares = data['quantity']
        price_yuan = data['avg_price']

        qty_units = Money.shares_to_min_unit(qty_shares)
        price_units = Money.yuan_to_price_units(price_yuan)

        existing = db.query(Position).filter_by(id=position_id, family_id=_resolve_family_id(data)).first()
        if not existing:
            raise ValueError('指定的持仓不存在')
        if qty_units <= 0:
            raise ValueError('操作数量必须大于 0')

        # 锚点判定：这笔卖出若已包含在快照里（confirm_date <= 锚点日），快照份额已经
        # 反映了它，**不再扣减** quantity，否则会把快照值减成「快照 - 已含卖出」。
        # 同时跳过数量校验：被包含的卖出不该受当前派生份额约束（它已经发生过了）。
        covered_by_anchor = is_covered_by_anchor(existing, data.get('confirm_date'))

        if not covered_by_anchor:
            if existing.quantity < qty_units:
                raise ValueError(
                    f'持仓数量不足：当前持有 {Money.min_unit_to_shares(existing.quantity)}，拟操作 {qty_shares}'
                )

            if not skip_lot_check:
                symbol = existing.symbol or ''
                valid, err_msg = validate_sell(
                    symbol,
                    existing.market or '',
                    existing.asset_type or 'stock',
                    Money.min_unit_to_shares(existing.quantity),  # 转回份
                    Money.min_unit_to_shares(qty_units),
                )
                if not valid:
                    raise ValueError(err_msg)

        try:
            # 自愈回填（#2372）：存量持仓快照缺失时按 ID 反查补上（与买入路径同口径），
            # 修复上游漏写导致的「未知资产/未知账户」。仅在缺失时写。
            if not existing.name:
                existing.name = _resolve_fund_name_by_code(db, existing.symbol)
            if not existing.account_name and existing.ledger_id:
                existing.account_name = _resolve_ledger_name_by_id(db, existing.ledger_id)
            # #2372：快照仍缺失（如 market 名录无该代码）时按 ID 兜底反查，
            # 绝不留 NULL 让前端显示「未知资产/未知账户」。
            position_name = existing.name or _resolve_fund_name_by_code(db, existing.symbol)
            account_name = existing.account_name or _resolve_ledger_name_by_id(db, existing.ledger_id)
            # 清仓不再删行（#2343），ledger_id 提前取出保留（#1137 自动申购要用）——
            # 防御性写法：即使行保留，也避免依赖「事后仍可读 existing」的顺序耦合。
            ledger_id = existing.ledger_id

            # ── 已实现盈亏结转（#1183）──
            # 必须在份额扣减前取成本均价：移动加权下卖出本不改均价，但显式提前取值
            # 可避免后续重构引入顺序依赖。结果落在流水的 realized_pnl 上而不是持仓上，
            # 因为清仓时持仓行会被 delete，记在持仓上会随持仓一起丢失。
            fee_cents = Money.yuan_to_cents(data.get('fee', 0) or 0)
            realized_cents = compute_sell_realized_cents(
                price_units=price_units,
                avg_price_units=existing.avg_price or 0,
                qty_units=qty_units,
                fee_cents=fee_cents,
            )

            is_cleared = False
            if not covered_by_anchor:
                existing.quantity -= qty_units
                is_cleared = existing.quantity == 0
                if is_cleared:
                    # 清仓不再删行（#2343）：行保留 = 锚点不灭 + 成本基线可追溯。
                    # 过去的 `db.delete(existing)` 是「锚点随行消失 → 删卖出流水后
                    # 重建退回全量口径 → 二次累加复发」这条链的源头。
                    # cleared_at 取清仓流水的确认日（业务事实），不是墙钟时间。
                    mark_position_cleared(existing, data.get('confirm_date') or data.get('trade_date'))
            else:
                logger.debug(
                    '卖出已含在快照锚点内，仅落流水: position={} symbol={} confirm={} anchor={}',
                    existing.id,
                    existing.symbol,
                    data.get('confirm_date'),
                    existing.snapshot_date,
                )
            db.flush()

            # 品种以**持仓**为准（理由见 `_get_asset_type` 的 `fallback` 说明）：
            # 卖出请求不带 type 时若兜底成 'stock'，场外基金的卖出流水会与买入
            # 分属两个身份键，清仓周期永远闭合不上。
            sell_asset_type = _get_asset_type(data, fallback=existing.asset_type)
            TransactionService.create(
                db=db,
                position_id=position_id,
                # symbol 同理以持仓为准（#2855）：卖出请求漏带 symbol 时若落 NULL，
                # 产品详情「交易记录」（按 symbol 身份匹配）与清仓周期（按 symbol 分组）
                # 都看不见这笔卖出——已清仓产品于是「有买无卖」。与下方 bond_redeem
                # 路径的 `data.get('symbol') or existing.symbol` 同一条纪律。
                symbol=data.get('symbol') or existing.symbol,
                txn_type=op_type,
                trade_date=data.get('trade_date'),
                confirm_date=data.get('confirm_date'),
                asset_type=sell_asset_type,
                link_group_id=data.get('link_group_id'),
                quantity=qty_units,
                price=price_units,
                fee=fee_cents,
                # #2137 费用拆分：data 带明细才落四列，否则四列留 NULL（未拆分）
                **_fee_breakdown_kwargs(data),
                amount=Money.multiply_price_quantity(price_units, qty_units),
                realized_pnl=realized_cents,
                status='success',
                position_name=position_name,
                ledger_id=ledger_id,
                account_name=account_name,
                notes=data.get('notes') or ('卖出' if op_type == 'sell' else '取出'),
                import_hash=data.get('import_hash'),
                family_id=_resolve_family_id(data),
                # #1232 决策 11：流水来源透传（记一笔默认 manual）
                source=data.get('source') or PositionSource.MANUAL.value,
                # 转换等成组交易经 data 透传 extra.conversion 元数据（§3.2）
                extra=data.get('extra'),
            )

            # #1137 卖出回款自动申购账户绑定的类现金产品（余额宝）。
            # 净额 = 成交额 - 手续费；货基/逆回购自身的卖出不触发，避免「赎回 → 自动申购」死循环。
            # 基金转换传 auto_purchase=False：退款腿由转换服务按用户选择显式落账（见 docstring）。
            # #1137 卖出回款自动申购账户绑定的类现金产品（余额宝）。
            # 净额 = 成交额 - 手续费；货基/逆回购自身的卖出不触发，避免「赎回 → 自动申购」死循环。
            # 判据用 `sell_asset_type`（持仓品种）而非 `_get_asset_type(data)`：请求体没带 type 时
            # 后者会把货基赎回判成股票卖出去自动申购，正是它要防的那个死循环。
            if auto_purchase and sell_asset_type not in ('money_fund', 'reverse_repo'):
                gross_cents = Money.multiply_price_quantity(price_units, qty_units)
                auto_purchase_money_fund(
                    db,
                    ledger_id=ledger_id,
                    amount_cents=gross_cents - fee_cents,
                    trade_date=data.get('trade_date'),
                    confirm_date=data.get('confirm_date'),
                    family_id=_resolve_family_id(data),
                )

            db.flush()
            # #1458 后续：卖出/清仓后对齐自选状态（静默，失败不影响主链路）
            _silent_reconcile_watchlist(db, _resolve_family_id(data), existing.symbol)
            if is_cleared:
                return None
            db.refresh(existing)
            return existing

        except Exception:
            logger.exception('卖出/取出操作失败')
            raise

    @staticmethod
    def recompute_position_from_transactions(db: Session, position_id: int):
        """删除/编辑交易后，依据该持仓剩余流水重算份额与成本均价（#948 后续回滚）。

        卖出/取出使持仓份额减少；删除该类流水必须把份额加回，否则账面份额丢失。
        采用「从流水重算」而非只做反向加减：
        - 能正确处理部分卖出（剩余流水仍有买入，净份额>0，更新现有持仓）；
        - 也能在「整笔卖出清空持仓」后删除该卖出流水时（持仓行已被 process_sell 删掉）
          依据剩余买入流水重建持仓，避免份额彻底丢失。

        **份额与成本一律委托 `compute_anchored_state`**（锚点感知）：本函数历史上自己
        实现了一套「全量流水净额」循环，与快照导入的 SET 语义并存，正是份额被重复
        累加的成因。现在只保留一个派生入口，避免第二份实现再次分叉。

        **「无流水即删行」必须以无锚点为前提**（2026-10-18）：纯快照导入的持仓本来就没有
        明细流水，早退删行会让它们在任意一次重算中消失（真实库实测 79 行）。
        有锚点时走正常派生：`snapshot_quantity` 即基线份额。

        **净份额归零不再删行**（#2343 第二步，2026-10-18）：改为 `mark_position_cleared`
        （`quantity=0` + `ownership_status='cleared'` + `cleared_at`），锚点原样留存。
        反向对称：`cleared` 行派生出正份额（典型：删除了那笔清仓卖出流水）时自动
        重新激活回 `active`——持仓「复活」，锚点与流水全程无断链。
        例外：`not txns and not has_anchor` 的空壳行仍删行——那不是清仓历史，
        是无任何数据支撑的孤儿行，标记成 cleared 反而会伪造一段「曾持有」。
        """
        txns = order_by_effective_day(
            db.query(Transaction).filter(Transaction.position_id == position_id), descending=False
        ).all()
        pos = db.query(Position).filter_by(id=position_id).first()

        # 「无流水即删行」只能在**无锚点**时成立。有锚点的持仓其份额来自快照，
        # 流水本来就可以为空（纯快照导入的账户，绝大多数持仓没有明细流水）。
        # 2026-10-18 实测：真实库 105 行「有快照日、无流水」的持仓里 79 行零流水，
        # 该早退分支会让它们在任何一次重算中整行消失——锚点模型对这类持仓完全失效。
        has_anchor = pos is not None and pos.snapshot_quantity is not None and pos.snapshot_date is not None
        if not txns and not has_anchor:
            if pos:
                db.delete(pos)
                db.flush()
            return None

        if pos is not None:
            net_qty, avg_price_units = compute_anchored_state(db, pos)
        else:
            # 持仓行已被清空删除：无锚点可用，退回全量流水口径（见 docstring 已知边界）
            net_qty, avg_price_units = derive_state_from_txns(txns, 0, 0)

        if net_qty <= 0:
            if pos:
                # 归零不再删行（#2343）：标记清仓、锚点留存。负份额钳为 0
                # （负数是脏数据，真实份额不可能为负，保留负值会让市值算出负数）。
                if net_qty < 0:
                    logger.warning(
                        '[Recompute] 派生份额为负，钳为 0 并标记清仓: position={} symbol={} net={}',
                        pos.id,
                        pos.symbol,
                        Money.min_unit_to_shares(net_qty),
                    )
                mark_position_cleared(pos)
                db.flush()
            return None

        if pos:
            # 清仓行派生出正份额 → 持仓复活（典型：删除了那笔清仓卖出流水）。
            # 锚点与 cleared_at 原样保留：锚点仍是上一轮快照口径（删除卖出后全量流水
            # 恰好等于锚点+流入，两者自洽），cleared_at 是历史周期下界，不是当前状态。
            if pos.ownership_status == OwnershipStatus.CLEARED.value:
                pos.ownership_status = OwnershipStatus.ACTIVE.value
                logger.info(
                    '[Recompute] 已清仓持仓复活: position={} symbol={} qty={}',
                    pos.id,
                    pos.symbol,
                    Money.min_unit_to_shares(net_qty),
                )
            # 锚点重算的可观测性（2026-10-18 评审）：重算覆盖是本类 bug 最隐蔽的复发形态
            # ——净值回填/删流水都会静默改写 quantity。只记日志不抛错：重算本来就会正常
            # 变化（补录/修正历史流水），抛错会打断 nav_backfill 的任务链。
            if pos.quantity != net_qty and pos.snapshot_quantity is not None:
                logger.warning(
                    '[Recompute] 锚点持仓份额变更: position={} symbol={} {} -> {} (anchor={} date={} kind={})',
                    pos.id,
                    pos.symbol,
                    Money.min_unit_to_shares(pos.quantity),
                    Money.min_unit_to_shares(net_qty),
                    Money.min_unit_to_shares(pos.snapshot_quantity),
                    pos.snapshot_date,
                    pos.anchor_kind,
                )
            pos.quantity = net_qty
            pos.avg_price = avg_price_units
            if pos.current_price in (None, 0):
                pos.current_price = avg_price_units
            db.flush()
            # #1458 后续：重算后对齐自选状态（静默）
            _silent_reconcile_watchlist(db, pos.family_id, pos.symbol)
            return pos

        # 持仓行已被整笔卖出清空删除：依据剩余买入流水重建
        # （Transaction 不携带 market/currency，缺失时取默认值）
        first = txns[0]
        new_pos = Position(
            ledger_id=first.ledger_id,
            family_id=first.family_id,
            symbol=first.symbol or '',
            name=first.position_name or first.symbol or '',
            asset_type=first.asset_type,
            market='CN_A',
            currency='CNY',
            quantity=net_qty,
            avg_price=avg_price_units,
            current_price=avg_price_units,
            confirm_date=first.confirm_date,
            account_name=first.account_name,
            allocation='longterm',
            notes='',
        )
        db.add(new_pos)
        db.flush()
        for t in txns:
            t.position_id = new_pos.id
        db.flush()
        # #1458 后续：重算后对齐自选状态（静默）
        _silent_reconcile_watchlist(db, new_pos.family_id, new_pos.symbol)
        return new_pos

    @staticmethod
    def process_dividend(db: Session, data: dict) -> Position:
        """处理分红记录，不改变持仓数量。"""
        position_id = data['position_id']
        dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))

        existing = db.query(Position).filter_by(id=position_id, family_id=_resolve_family_id(data)).first()
        if not existing:
            logger.error(f'持仓不存在: position_id={position_id}')
            raise ValueError('指定的持仓不存在')

        try:
            TransactionService.create(
                db=db,
                position_id=position_id,
                txn_type='dividend',
                # 分红挂在持仓上，symbol 缺失时以持仓为准（#2855，与卖出路径同因同法）：
                # 落 NULL 会让该笔分红在按 symbol 匹配的读侧（产品详情交易记录 /
                # 清仓周期分红窗口）里消失。
                symbol=data.get('symbol') or existing.symbol,
                trade_date=data.get('trade_date'),
                confirm_date=data.get('confirm_date'),
                asset_type=_get_asset_type(data),
                link_group_id=data.get('link_group_id'),
                quantity=0,
                price=0,
                fee=0,
                amount=Money.yuan_to_cents(dividend_amount),
                # 现金分红全额计入已实现盈亏（#1183）：与 XIRR 的 dividend_cash 正现金流同口径，
                # 修复「汇总排除 dividend、XIRR 却计入」的口径分叉
                realized_pnl=Money.yuan_to_cents(dividend_amount),
                status='success',
                position_name=existing.name,
                account_name=existing.account_name,
                ledger_id=existing.ledger_id,
                notes=data.get('notes') or '现金分红',
                import_hash=data.get('import_hash'),
                family_id=_resolve_family_id(data),
                # #1232 决策 11：流水来源透传（记一笔默认 manual）
                source=data.get('source') or PositionSource.MANUAL.value,
            )

            db.flush()
            return existing

        except Exception:
            logger.exception('分红操作失败')
            raise

    @staticmethod
    def process_dividend_reinvest(db: Session, data: dict) -> Optional[Position]:
        """
        处理红利再投资：分红到账（现金流入）＋ 按当日净值申购份额（份额增加）。

        WHY 拆成两笔流水，而不是记一笔 `dividend_reinvest`：
        1. 语义真实——先分红入账、再用这笔钱按净值申购，本就是两件事；
        2. XIRR 自洽——`services/performance/xirr_engine.py` 按类型分流现金流方向：
           dividend_cash 记流入、buy/dividend_reinvest 记流出。两笔金额相等、一进一出，
           净额为 0，与「红利再投资不产生实际现金进出」相符；若只记一笔流出，
           会虚增投入、低估年化。（流水的 amount 字段恒为正，方向由 txn_type 决定，此处不取负）
        3. 两笔以 link_group_id 配对，便于前端折叠展示为一条「红利再投资」。

        去重：分红流水沿用原始 import_hash（重导时命中即跳过整条记录，见 orchestrator.commit），
        申购流水用派生 hash `{原 hash}#reinvest`，避开 uq_txn_import_hash 唯一约束。
        """
        position_id = data.get('position_id')
        if not position_id:
            raise ValueError('红利再投资必须指定关联持仓（position_id）')
        family_id = _resolve_family_id(data)
        existing = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
        if not existing:
            raise ValueError('指定的持仓不存在')
        link_group_id = data.get('link_group_id') or uuid.uuid4().hex
        _reinvest_dual_flow(db, data, existing, link_group_id)
        return existing

    @staticmethod
    def process_orphan_sell_or_withdraw(db: Session, data: dict) -> Optional[Position]:
        """孤儿流水路径：实现见 :mod:`app.services.position_orphan_flows`（#2873 第三抽）。"""
        return position_orphan_flows.process_orphan_sell_or_withdraw(db, data)

    # ── 债券兑付（#2832）──

    @staticmethod
    def process_bond_redeem(db: Session, data: dict) -> Optional[Position]:
        """债券兑付（到期还本付息 / 强赎 / 回售）：扣份额 + 结转到账额的已实现盈亏。

        调用前必须已确定 ``data['position_id']``（手动记账直传，导入路径先经
        :meth:`process_orphan_bond_redeem` 按身份键定位）。

        ## 与 :meth:`process_sell_or_withdraw` 的三处刻意不同

        1. **金额口径是「到账净额」而不是「价格 × 数量」**。交割单兑付行的
           「发生金额」= 面值 + 应计利息 − 代扣费，而 ``price`` 只是券商给的成交均价
           （通常等于面值 100）。付息 / 强赎溢价时两者本来不等，若照卖出路径用
           ``price × qty`` 记金额，利息会被静默丢掉——用户看到「到账 1035，账面 1000」。
           详见 :func:`pnl_service.compute_redeem_realized_cents`。
        2. **已实现盈亏不再减 fee**：``amount`` 已经是扣费后的净额（同花顺 / 东财的
           「发生金额」口径一致），再减一次是双扣。卖出路径的 amount 是毛额，所以那边
           必须减，两个口径不能互相套用。
        3. **份额不足直接报错，不降级成孤儿**：兑付量 > 持仓量只可能是买入流水缺失
           （或上次只导了兑付没导买入），静默记孤儿会把差额藏起来——用户看到的是
           「钱到账了，持仓还在」。让这一行进 ``commit_errors`` / 400 让人看见，
           比记一笔谁也不会去核的孤儿流水有用。卖出路径的降级是历史遗留（真实库
           649 笔卖出无 symbol 可匹配），兑付没有那个包袱。

        清仓沿 #2343 口径：行保留 + ``ownership_status='cleared'``，返回 None
        （调用方「None = 已清仓」的契约不变）。
        """
        position_id = data.get('position_id')
        existing = db.query(Position).filter_by(id=position_id, family_id=_resolve_family_id(data)).first()
        if not existing:
            raise ValueError('指定的持仓不存在')

        qty_shares = data.get('quantity') or 0
        qty_units = Money.shares_to_min_unit(qty_shares)
        if qty_units <= 0:
            raise ValueError('兑付数量必须大于 0')

        # 金额：net_amount（交割单发生金额）优先 → amount（手动记账实收）→ 价格×数量
        raw_amount = data.get('net_amount')
        if raw_amount is None:
            raw_amount = data.get('amount')
        price_units = Money.yuan_to_price_units(data.get('avg_price') or 0)
        if raw_amount is None:
            amount_cents = Money.multiply_price_quantity(price_units, qty_units)
        else:
            amount_cents = Money.yuan_to_cents(abs(raw_amount))

        # 均价缺失（兑付行常常只给发生金额、不给成交均价）：按到账额 ÷ 份数反算，
        # 让「金额 / 单价 / 数量」三者自洽，前端在金额列旁展开时才不会显示 0 单价。
        # 换算一律走 Money 的既有链路，不手推「分 × 份额最小单位 × 价格单位」的系数
        # ——那三个 10_000 / 100 混乘极易差两个数量级且测试里也看不出来。
        if price_units <= 0 and qty_units > 0:
            per_share_yuan = Money.cents_to_yuan(amount_cents) / Money.min_unit_to_shares(qty_units)
            price_units = Money.yuan_to_price_units(per_share_yuan)

        fee_cents = Money.yuan_to_cents(data.get('fee') or 0)

        # 锚点判定与卖出同口径：若这笔记兑付已含在快照里（confirm_date <= 锚点日），
        # 快照份额已反映它，不再扣减；流水照落（它确实是发生过的业务事实）。
        covered_by_anchor = is_covered_by_anchor(existing, data.get('confirm_date'))
        if not covered_by_anchor and existing.quantity < qty_units:
            raise ValueError(
                f'兑付数量超过持仓：当前持有 {Money.min_unit_to_shares(existing.quantity)}，'
                f'本次兑付 {qty_shares}。请检查买入流水是否已完整导入'
            )

        realized_cents = compute_redeem_realized_cents(
            amount_cents=amount_cents,
            avg_price_units=existing.avg_price or 0,
            qty_units=qty_units,
        )

        try:
            # 自愈回填（与卖出路径同口径）：快照缺名称/账户时按 ID 反查，绝不留 NULL
            if not existing.name:
                existing.name = _resolve_fund_name_by_code(db, existing.symbol)
            if not existing.account_name and existing.ledger_id:
                existing.account_name = _resolve_ledger_name_by_id(db, existing.ledger_id)
            position_name = existing.name or _resolve_fund_name_by_code(db, existing.symbol)
            account_name = existing.account_name or _resolve_ledger_name_by_id(db, existing.ledger_id)
            ledger_id = existing.ledger_id

            is_cleared = False
            if not covered_by_anchor:
                existing.quantity -= qty_units
                is_cleared = existing.quantity == 0
                if is_cleared:
                    # 清仓不清行（#2343）：锚点与成本基线原样留存，二次累加才不会复发
                    mark_position_cleared(existing, data.get('confirm_date') or data.get('trade_date'))
            db.flush()

            # 品种以持仓为准（同卖出路径）：请求体不带 type 时若兜底成 stock，
            # 兑付流水会与买入分属两个身份键，清仓周期永远闭合不上。
            redeem_asset_type = _get_asset_type(data, fallback=existing.asset_type)
            TransactionService.create(
                db=db,
                position_id=position_id,
                symbol=data.get('symbol') or existing.symbol,
                txn_type='bond_redeem',
                trade_date=data.get('trade_date'),
                confirm_date=data.get('confirm_date'),
                asset_type=redeem_asset_type,
                link_group_id=data.get('link_group_id'),
                quantity=qty_units,
                price=price_units,
                fee=fee_cents,
                # #2137 费用拆分：data 带明细才落四列，否则四列留 NULL（未拆分）
                **_fee_breakdown_kwargs(data),
                amount=amount_cents,
                realized_pnl=realized_cents,
                status='success',
                position_name=position_name,
                ledger_id=ledger_id,
                account_name=account_name,
                notes=data.get('notes') or '债券到期兑付',
                import_hash=data.get('import_hash'),
                family_id=_resolve_family_id(data),
                # #1232 决策 11：流水来源透传（记一笔默认 manual）
                source=data.get('source') or PositionSource.MANUAL.value,
            )
            db.flush()
            # 兑付即退出持仓，与卖出/清仓后同样对齐自选状态（静默，失败不影响主链路）
            _silent_reconcile_watchlist(db, _resolve_family_id(data), existing.symbol)
            if is_cleared:
                return None
            db.refresh(existing)
            return existing
        except Exception:
            logger.exception('债券兑付操作失败')
            raise

    @staticmethod
    def process_orphan_bond_redeem(db: Session, data: dict) -> BondRedeemOutcome:
        """孤儿流水路径：实现见 :mod:`app.services.position_orphan_flows`（#2873 第三抽）。"""
        return position_orphan_flows.process_orphan_bond_redeem(db, data)

    @staticmethod
    def process_orphan_dividend(db: Session, data: dict) -> Optional[Position]:
        """孤儿流水路径：实现见 :mod:`app.services.position_orphan_flows`（#2873 第三抽）。"""
        return position_orphan_flows.process_orphan_dividend(db, data)

    @staticmethod
    def process_orphan_dividend_reinvest(db: Session, data: dict) -> Optional[Position]:
        """孤儿流水路径：实现见 :mod:`app.services.position_orphan_flows`（#2873 第三抽）。"""
        return position_orphan_flows.process_orphan_dividend_reinvest(db, data)

    @staticmethod
    def process_orphan_split(db: Session, data: dict) -> Optional[Position]:
        """孤儿流水路径：实现见 :mod:`app.services.position_orphan_flows`（#2873 第三抽）。"""
        return position_orphan_flows.process_orphan_split(db, data)

    @staticmethod
    def build_position_list(
        db,
        family_id: int,
        group_by: str,
        page: int,
        per_page: int,
        ledger_id_raw: str,
        symbol: str = '',
        market: str = '',
        member_id_raw: str = '',
    ) -> dict:
        return build_position_list_impl(
            db, family_id, group_by, page, per_page, ledger_id_raw, symbol, market, member_id_raw
        )

    @staticmethod
    def dispatch_position_op(db, data: dict, op_type: str) -> Optional['Position']:
        """create_position 的操作分派（#1642 B 块，从 views 下沉）。

        与下沉前逐字段一致：sell/withdraw → process_sell_or_withdraw；dividend → process_dividend；
        dividend_reinvest → process_dividend_reinvest；split → process_orphan_split；buy/deposit →
        process_buy_or_deposit(force_create_position=True)。返回持仓或 None（已清空）。业务校验失败
        透传 ValueError（视图转 400/1001）；唯一约束冲突透传 IntegrityError（视图转 409 幂等拦截）。
        不支持的操作类型由视图在调本方法前 abort(400)，此处不兜底。
        """
        if op_type in ('sell', 'withdraw'):
            return PositionService.process_sell_or_withdraw(db, data)
        if op_type == 'bond_redeem':
            # 债券兑付（#2832）：带 position_id 直接定位；只带代码/名称时按身份键找持仓
            if data.get('position_id'):
                return PositionService.process_bond_redeem(db, data)
            outcome = PositionService.process_orphan_bond_redeem(db, data)
            return outcome.position
        if op_type == 'dividend':
            data['dividend_amount'] = data.get('avg_price', 0)
            return PositionService.process_dividend(db, data)
        if op_type == 'dividend_reinvest':
            data['dividend_amount'] = data.get('dividend_amount', data.get('amount', data.get('avg_price', 0)))
            data['nav'] = data.get('nav', data.get('avg_price', 0))
            return PositionService.process_dividend_reinvest(db, data)
        if op_type == 'split':
            return PositionService.process_orphan_split(db, data)
        if op_type in ('buy', 'deposit'):
            return PositionService.process_buy_or_deposit(db, data, force_create_position=True)
        raise ValueError(f'不支持的操作类型: {op_type}')
