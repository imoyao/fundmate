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
- 买入/存入命令 → `position_buy_command`（`process_buy_or_deposit` 在此仅为 facade）；
- 快照导入命令 → `position_snapshot_command`（`upsert_from_holding` 在此仅为 facade）；
- 卖出/取出命令 → `position_sell_command`（`process_sell_or_withdraw` 在此仅为 facade）；
- 债券兑付命令 → `position_bond_command`（`process_bond_redeem` 在此仅为 facade）；
- 份额重算 → `position_recompute`（`recompute_position_from_transactions` 在此仅为 facade）。
"""

import uuid
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import (
    AnchorKind,
    OwnershipStatus,
    PositionSource,
)
from app.core.money import Money
from app.core.venues import resolve_venue
from app.domains.positions.models import Position
from app.domains.positions.state import (
    derive_state_from_txns,
)
from app.domains.transactions.dates import order_by_effective_day
from app.domains.transactions.models import Transaction

# #2873 第三抽：孤儿流水簇已下沉到 position_orphan_flows，此处 re-export 保 facade ——
# 内部调用点（买入的现金转移、建仓/卖出的孤儿挂回）与外部导入
# （scripts/fix_orphan_money_fund_reattach、sync/jobs/orphan_backfill_job、测试）一行不改。
from app.services import position_orphan_flows
from app.services.fund_utils import is_money_fund_symbol

# #2873 第五抽：快照导入命令已下沉到 position_snapshot_command，类方法只留 facade。
# #2873 第六抽：卖出/取出命令已下沉到 position_sell_command，类方法只留 facade。
# #2873 第七抽：债券兑付命令已下沉到 position_bond_command，类方法只留 facade。
from app.services.position_bond_command import run_bond_redeem

# issue #2873 安全首抽：读/展示簇已下沉到 position_display，此处仅 re-export 保 facade。
from app.services.position_buy_command import (  # noqa: F401
    _ALLOWED_POSITION_FIELDS,
    _BALANCE_ONLY_ASSET_TYPES,
    _get_default_notes,
    run_buy_or_deposit,
)
from app.services.position_display import (  # noqa: F401
    build_position_list_impl,
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

# #2873 第八抽：份额重算已下沉到 position_recompute，类方法只留 facade。
from app.services.position_recompute import recompute_from_transactions
from app.services.position_sell_command import (
    auto_purchase_money_fund,  # noqa: F401  re-export 保 facade，供外部脚本沿用旧导入路径
    run_sell_or_withdraw,
)
from app.services.position_sell_import import process_sell_or_withdraw_import
from app.services.position_snapshot_command import (
    finalize_snapshot,
    resolve_snapshot_intent,
    upsert_anchor_position,
    upsert_import_meta,
)
from app.services.position_txn_read import list_position_transactions, query_transactions_by_identity  # noqa: F401

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
from app.services.trading import TransactionService
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

        #2873 第五抽：实现已下沉到 `position_snapshot_command`（解析校验 → 锚点 SET/新建 →
        溯源 meta → 挂孤儿 + 锚点派生 → 自选静默同步），此处只保留 facade，签名与行为逐字不变。

        与 `process_buy_or_deposit` 的本质区别：快照是某日点位的**绝对值**（整条替换、不累加），
        `quantity` 是锚点派生结果而非快照值本身，且**绝不调用 TransactionService.create** ——
        导入持仓不产生交易流水。锚点时间轴规则（时间不可倒流 / 同日 manual 优先）、
        影子行不落 positions 锚点、负份额钳 0 并保留快照成本价等口径，见该模块 docstring。
        """
        intent = resolve_snapshot_intent(
            data,
            ownership_status=ownership_status,
            allow_anchor_rewind=allow_anchor_rewind,
        )
        position = upsert_anchor_position(db, intent, data)
        upsert_import_meta(db, position, intent, data)
        return finalize_snapshot(db, position, intent)

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
        """执行卖出或取出操作。

        #2873 第六抽：实现已下沉到 `position_sell_command`（解析校验 → 扣减/清仓 →
        落流水 + 回款自动申购 + 自选对齐），此处只保留 facade，签名与行为逐字不变。

        清仓（份额减至 0）时**行保留**（#2343：`ownership_status='cleared'` + `cleared_at`，
        锚点与成本基线原样留存），但本方法仍返回 None——与既有调用方「None = 已清仓」的
        契约保持一致。`auto_purchase`（#1137）与 `skip_lot_check` 的语义见该模块 docstring。
        """
        return run_sell_or_withdraw(
            db,
            data,
            skip_lot_check=skip_lot_check,
            auto_purchase=auto_purchase,
        )

    @staticmethod
    def recompute_position_from_transactions(db: Session, position_id: int):
        """删除 / 编辑交易后，依据该持仓剩余流水重算份额与成本均价（#948 后续回滚）。

        #2873 第八抽：实现已下沉到 `position_recompute`（取流水 → 锚点派生 → 清仓 / 复活 /
        重建 → 自选对齐），此处只保留 facade，签名与行为逐字不变。

        三条判据都在该模块 docstring 里：份额一律委托 `compute_anchored_state`（不允许第二份
        派生实现）、「无流水即删行」以无锚点为前提（纯快照持仓零流水不能被删）、净份额归零
        改为 `mark_position_cleared` 而非删行（#2343，锚点留存；派生出正份额即复活）。
        """
        return recompute_from_transactions(db, position_id)

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
        """孤儿流水路径：实现见 :mod:`app.services.position_sell_import`（#3004 下沉）。"""
        return process_sell_or_withdraw_import(db, data).position

    # ── 债券兑付（#2832）──

    # ── 债券兑付（#2832）──

    @staticmethod
    def process_bond_redeem(db: Session, data: dict) -> Optional[Position]:
        """债券兑付（到期还本付息 / 强赎 / 回售）：扣份额 + 结转到账额的已实现盈亏。

        #2873 第七抽：实现已下沉到 `position_bond_command`（解析校验 → 扣减/清仓 →
        落流水 + 自选对齐），此处只保留 facade，签名与行为逐字不变。

        调用前必须已确定 `data['position_id']`（手动记账直传，导入路径先经
        `process_orphan_bond_redeem` 按身份键定位）。与卖出路径的三处刻意不同
        （到账净额口径 / 已实现盈亏不再减 fee / 份额不足直接报错不降级孤儿），
        以及清仓沿用 #2343 口径（行保留 + 返回 None）的细节，见该模块 docstring。
        """
        return run_bond_redeem(db, data)

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
