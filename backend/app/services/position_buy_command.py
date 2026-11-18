# -*- coding: utf-8 -*-
"""持仓**买入/存入命令**（#2873 第四抽）。

`process_buy_or_deposit` 曾是一个 405 行、圈复杂度 84 的单方法，把四件事塞在同一个
`try` 里：

    解析入参 → 合并/新建持仓 → 挂回孤儿流水 → 落买入流水

这一簇整体下沉到本模块，主模块只留一个转发薄壳（facade 签名不变）。拆分的硬约束来自
`scripts/guard_service_size.py` 的 `NEW_FILE_LIMITS`：单函数 ≤120 行、圈复杂度 ≤20，
所以「按物理行切开」不够——`max_cc` 按 AST 决策点算，必须真的拆开分支。

## 三段与 `BuyIntent`

    resolve_buy_intent      解析 + 校验，产出一个不可变的 `BuyIntent`
    upsert_position_on_buy  拿到 intent 后决定「合并既有 / 新建 / 复活清仓行」
    write_buy_transaction   落流水 + 孤儿挂回 + 自选静默同步

段间原本共享 12 个局部变量。**刻意不为每段单独重算**：

- `effective_confirm_date` 必须锚点判定与流水同源。`_txn_effective_date`（confirm 优先）
  与 `domains/transactions/dates.py::effective_day_expr`（trade 优先）是**刻意相反**的
  两套口径（见 `position_write_support` 顶部说明），多算一次就多一次走错的机会；
- `nav_pending` 的判定要查库（当日官方净值 / 最近净值占位），重算等于重复查询，
  且两次查询之间净值可能刚好发布，导致「份额按占位价算、流水标 pending」自相矛盾。

故显式传一个 `frozen` 的 dataclass：解析完成后任何一段都不得改写。

## 与主模块的依赖方向

`position_service` 在模块级导入本模块（转发薄壳）；本模块只在**函数内**延迟导入
`position_service` 里的四个展示辅助（`_silent_ensure_watchlist` /
`_resolve_fund_name_by_code` / `_resolve_ledger_name_by_id` / `_resolve_money_fund_flag`）。
它们同时服务快照导入与卖出路径，留主模块才不制造双向依赖——函数级导入是本仓既有范式。

## 刻意不做的事

- **不改 `force_create_position` 语义**（#1233 决策 5）：默认 False 时货基/逆回购在导入
  路径只记孤儿流水、不建持仓；True（记一笔）照常建仓。7 个调用点一行不改。
- **不拆基金转换**：`conversion_service` 的买入腿复用本模块是**设计**（转换＝卖 A + 买 B），
  它自己已有编排层，另起 `process_conversion` 只会把两层逻辑再叠一层。
- **不合并 `_txn_effective_date` 与 `effective_day_expr`**：理由见上，属独立决策。
"""

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.asset_types import get_asset_type_label
from app.core.constants import OwnershipStatus, PositionSource, ValuationMode
from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.core.symbol_utils import is_subscription_code, normalize_by_venue
from app.core.venues import resolve_venue
from app.domains.positions.models import Position
from app.domains.positions.state import is_covered_by_anchor, reactivate_cleared_position
from app.services import async_backfill
from app.services.import_records import compute_position_hash
from app.services.position_orphan_flows import _create_cash_transfer_transaction, _reattach_orphan_flows
from app.services.position_write_support import (
    _fee_breakdown_kwargs,
    _find_existing_position,
    _get_asset_type,
    _lookup_unit_nav,
    _resolve_confirm_date,
    _resolve_family_id,
    _resolve_fund_name_by_code,
    _resolve_ledger_name_by_id,
)
from app.services.trading import TransactionService, validate_buy

# 允许写入持仓模型的字段白名单（防止注入无效字段）
_ALLOWED_POSITION_FIELDS = {
    'symbol',
    'name',
    'market',
    'asset_type',
    'account_name',
    'ledger_id',
    'quantity',
    'avg_price',
    'currency',
    'current_price',
    'confirm_date',
    'notes',
    'allocation',
    # issue #928: 去重与溯源字段，允许透传落库
    'import_hash',
    'source',
    'source_import_id',
    'source_broker',
    # #1174 双态计价：balance 模式建仓需透传计价模式与可写市值
    'valuation_mode',
    'market_value_override',
}

# 只允许 balance（直接余额）记账的品类：共同点是**系统拿不到公开净值**，落成 nav 模式
# 不会报错，而是市值恒为 0（`position_price` job 不给它定价），用户看到一张「持仓 0 元」的卡。
# 值是该品类专属的拒绝理由，拼进错误信息用。
_BALANCE_ONLY_ASSET_TYPES: dict[str, str] = {
    'portfolio': '投顾组合没有份额与净值',
    'bank_wealth': '银行理财不在公开基金名录里，系统拿不到它的净值',
}

# 现金管理类：导入路径只记流水、不建持仓（市值由孤儿流水净额口径计入）
_CASH_PRODUCT_ASSET_TYPES = ('money_fund', 'reverse_repo')

# 支持「净值缺失先记账」的品类（场外/场内基金；货基在此只为复用同一段判定）
_NAV_PENDING_ASSET_TYPES = ('fund', 'money_fund', 'etf')


def _get_default_notes(op_type: str, is_new: bool) -> str:
    """生成默认的交易备注."""
    mapping = {
        (False, 'buy'): '追加买入',
        (False, 'deposit'): '追加存入',
        (True, 'buy'): '初始买入',
    }
    return mapping.get((is_new, op_type), '存入')


@dataclass(frozen=True, slots=True)
class BuyIntent:
    """一次买入/存入请求解析后的全部写入参数（见模块 docstring 的「三段与 BuyIntent」）。

    `existing` 是入口处按统一身份键 (symbol, ledger_id, family_id) 查到的持仓行，
    可能为 None（新建）。落持仓阶段会按需把它复活/合并，本对象本身不持有可变状态。
    """

    symbol: str
    asset_type: str
    venue: Optional[str]
    ledger_id: Optional[int]
    family_id: Optional[int]
    op_type: str
    mode: str
    is_balance: bool
    nav_pending: bool
    shares_manual: bool
    nav_date_extra: str
    effective_confirm_date: Optional[date]
    qty_units: int
    price_units: int
    amount_cents: int
    existing: Optional[Position]


def run_buy_or_deposit(db: Session, data: dict, force_create_position: bool = False) -> Optional[Position]:
    """买入/存入的唯一写入入口（主模块 `PositionService.process_buy_or_deposit` 转发到此）。

    `force_create_position`（#1233 决策 5「货基/逆回购保持建持仓」）：
    - 默认 False（交易导入）：money_fund / reverse_repo 只记孤儿资金流水、不建持仓（既有行为，
      市值由 `orphan_money_fund_totals_by_ledger` 按流水净额计入总资产）；
    - True（记一笔手动记账）：跳过现金转移分支，照常建持仓，流水关联持仓（position_id 非空），
      不再计入孤儿净额口径（与 summary 不重复计数，见 test_summary_money_fund 的持仓用例）。
    """
    intent = resolve_buy_intent(db, data, force_create_position=force_create_position)
    if intent is None:
        return None
    try:
        position, is_new = upsert_position_on_buy(db, data, intent)
        return write_buy_transaction(db, data, intent, position, is_new)
    except Exception:
        logger.exception('买入/存入操作失败')
        raise


def resolve_buy_intent(db: Session, data: dict, force_create_position: bool = False) -> Optional[BuyIntent]:
    """解析并校验入参；返回 None 表示这笔现金管理类买入已按流水记完、无需建仓。"""
    asset_type = _get_asset_type(data)
    symbol, venue = _normalize_symbol_by_venue(data, asset_type)

    effective_force = _handle_cash_product(
        db, data, asset_type, symbol, venue, force_create_position=force_create_position
    )
    if effective_force is None:
        return None

    ledger_id = data.get('ledger_id')
    family_id = _resolve_family_id(data)
    # 统一身份键 (symbol, ledger_id, family_id)（#911 M3）。历史实现还按 (symbol, account_name)
    # 二次匹配，与 ledger 键可能指向不同记录，存在「同一标的建出重复持仓」隐患。
    same = _find_existing_position(db, ledger_id=ledger_id, family_id=family_id, symbol=symbol, venue=venue)

    # ── 计价模式（#1174 / 决策 D2）──
    # nav：份额 × 净值（要求 quantity + avg_price）；balance：直接余额（只要求 amount）。
    # 用显式模式分支，而不是靠「有没有传净值」隐式推断。
    mode = data.get('valuation_mode') or ValuationMode.NAV.value
    is_balance = mode == ValuationMode.BALANCE.value
    amount = data.get('amount', 0) or 0
    qty = data.get('quantity', 0) or 0
    price = data.get('avg_price', 0) or 0

    _assert_balance_only_asset_type(asset_type, is_balance, symbol, same)

    price, qty, nav_pending, shares_manual, nav_date_extra = _resolve_pricing(
        db,
        data,
        asset_type,
        symbol,
        qty,
        price,
        amount,
        is_balance=is_balance,
        force_create_position=effective_force,
    )
    _validate_buy_inputs(data, asset_type, symbol, qty, price, amount, is_balance=is_balance)

    return BuyIntent(
        symbol=symbol,
        asset_type=asset_type,
        venue=venue,
        ledger_id=ledger_id,
        family_id=family_id,
        op_type=data.get('op_type', 'buy'),
        mode=mode,
        is_balance=is_balance,
        nav_pending=nav_pending,
        shares_manual=shares_manual,
        nav_date_extra=nav_date_extra,
        # 锚点判定必须在合并**之前**：确认日决定这笔流水是否已被快照包含。
        # 提前算一次并复用到落流水，避免「合并处用一套日期、流水用另一套」。
        effective_confirm_date=_resolve_confirm_date(data, asset_type),
        # 转换为内部存储单位（balance 模式份额/价格恒为 0，金额单独转分）
        qty_units=0 if is_balance else Money.shares_to_min_unit(qty),
        price_units=0 if is_balance else Money.yuan_to_price_units(price),
        amount_cents=Money.yuan_to_cents(amount) if is_balance else 0,
        existing=same,
    )


def _normalize_symbol_by_venue(data: dict, asset_type: str) -> tuple[str, Optional[str]]:
    """symbol 按 venue 归一（#1662，落库前唯一形态入口）。

    场内 → {MARKET}{CODE}（如 SZ159915）、场外 → 裸 6 位码（如 004369）。
    归一放在入口：持仓落库、流水落库、现金划转分支全部共享同一形态，避免
    「持仓带前缀 / 流水裸码」这类不一致。venue 由调用方显式传入（建仓 API /
    导入解析器本就知道场内/场外），缺失时按 asset_type 推断。

    历史实现按 asset_type 白名单「跳过归一化」（fund / money_fund / reverse_repo /
    bond 一律不归一），导致场外基金一旦带了误前缀就永远清不掉（`SZ004369` 与
    `004369` 长期并存）。现在形态由 venue 决定，不再按品种打补丁。
    """
    symbol = data.get('symbol', '')
    venue = resolve_venue(data.get('venue'), asset_type)
    if venue:
        symbol, _market, _ = normalize_by_venue(symbol, venue)
        data['symbol'] = symbol  # 下游（流水 / 划转）统一取 data，必须同步回写
    return symbol, venue


def _handle_cash_product(
    db: Session,
    data: dict,
    asset_type: str,
    symbol: str,
    venue: Optional[str],
    force_create_position: bool = False,
) -> Optional[bool]:
    """现金管理类产品：只记录流水，不创建持仓（交易导入既有行为）。

    返回 None 表示「已记完流水，调用方应直接返回 None」；否则返回生效的
    `force_create_position`（记一笔 force_create_position=True 时跳过本分支，
    走正常建仓逻辑）。

    #863 口径 A 写入层互斥：若该 (ledger, symbol) 已有 active 持仓，本笔买入并入
    持仓表达（走正常建仓合并），不产生孤儿流水——同一资金不得双表达双计。
    """
    if asset_type not in _CASH_PRODUCT_ASSET_TYPES or force_create_position:
        return force_create_position

    ledger_id = data.get('ledger_id')
    family_id = _resolve_family_id(data)
    existing = None
    if ledger_id:
        # venue 感知查重（#1662）：原实现手拼 {code, SZ+code, SH+code} 候选集，
        # 只覆盖「前缀变体」且不区分场所。active_only 保持原语义（仅匹配 active
        # 持仓，避免复用已平仓 / NULL 状态旧持仓）。
        existing = _find_existing_position(
            db, ledger_id=ledger_id, family_id=family_id, symbol=symbol, venue=venue, active_only=True
        )
    if existing is not None:
        return True  # 复用正常建仓逻辑（含孤儿流水挂回）
    _create_cash_transfer_transaction(db, data, 'buy')
    return None


def _assert_balance_only_asset_type(asset_type: str, is_balance: bool, symbol: str, same: Optional[Position]) -> None:
    """无净值品类只允许 balance 记账（D70 / #2740），且不得跨品类合并。

    落成 nav 模式的后果**不是报错而是静默 0 元**：`position_price` job 不会给它定价，
    市值恒为 0，但 has_position 仍为 true，详情页照常渲染一张「持仓 0 元」的卡——
    用户看到的是一个说不通的数字，没有任何提示。历史上这条约束只写在
    `core/asset_types.py` 的注释里，没有任何代码执行它。

    第二条防止「产品名恰好与某只证券同码」时合并进那只证券的行：balance-only 品类的
    venue 是 NO_VENUE，`_find_existing_position` 对空 venue 按设计不做品类过滤，于是
    balance 分支只往 `market_value_override` 上加钱，用户看到「一只股票凭空多了钱」。
    真实组合码是平台原生码（ZHxxxx / tgcode），撞码概率极低，但静默串账比报错贵。
    """
    if asset_type in _BALANCE_ONLY_ASSET_TYPES and not is_balance:
        raise ValueError(
            f'{_BALANCE_ONLY_ASSET_TYPES[asset_type]}，'
            '只能以 balance（直接余额）模式记账，市值靠人工录入金额（valuation_mode 须传 balance）'
        )
    if same is not None and asset_type in _BALANCE_ONLY_ASSET_TYPES and same.asset_type != asset_type:
        raise ValueError(
            f'该账户下 {symbol} 已存在一条 asset_type={same.asset_type} 的持仓，'
            f'不能按{get_asset_type_label(asset_type)}记账；请核对名称或换一个账户'
        )


def _resolve_pricing(
    db: Session,
    data: dict,
    asset_type: str,
    symbol: str,
    qty: float,
    price: float,
    amount: float,
    is_balance: bool = False,
    force_create_position: bool = False,
) -> tuple[float, float, bool, bool, str]:
    """定出最终 (price, qty, nav_pending, shares_manual, nav_date_extra)。

    含两段历史口径：
    - #1233 货基/逆回购手动建仓：净值恒为 1.0，缺失时兜底，避免净值接口不可用时
      用户无法记货基（买入金额 + 份额已足以建仓）；
    - 净值缺失先记账（nav_pending）：当日净值未发布 / 前后端拉取失败时，不把用户挡在
      记账之外。库内已有 nav_date 当日官方净值（提交前恰好发布）→ 直接用官方值，
      一次到位不标 pending；否则用 ≤ nav_date 的最近净值占位（新发基金无历史 → 1.0），
      份额按 (买入金额−手续费)/占位价 暂算，流水标 entry_status='pending_nav'，
      nav_backfill job 在官方净值落库后重算份额/成本（份额手动填写时只校正净值与成本，
      不覆盖份额；编辑手改份额则清标记，手动优先）。
    """
    if force_create_position and asset_type in _CASH_PRODUCT_ASSET_TYPES and not is_balance and price <= 0:
        price = 1.0
        data['avg_price'] = 1.0

    nav_pending = bool(data.get('nav_pending')) and not is_balance and asset_type in _NAV_PENDING_ASSET_TYPES
    shares_manual = bool(data.get('shares_manual')) and qty > 0
    nav_date_extra = str(data.get('nav_date') or data.get('trade_date') or '')[:10]
    if not nav_pending:
        return price, qty, False, shares_manual, nav_date_extra

    price, qty, nav_pending = _apply_nav_pending(
        db, data, asset_type, symbol, qty, price, amount, shares_manual=shares_manual
    )
    return price, qty, nav_pending, shares_manual, nav_date_extra


def _apply_nav_pending(
    db: Session,
    data: dict,
    asset_type: str,
    symbol: str,
    qty: float,
    price: float,
    amount: float,
    shares_manual: bool = False,
) -> tuple[float, float, bool]:
    """净值缺失先记账：定出占位价（或官方价）、暂算份额，并回写 `data`。"""
    if asset_type == 'money_fund':
        # 货基净值恒为 1.0（#1233）：不存在"待发布"，直接定值、无需回填
        price = 1.0
        nav_pending = False
    else:
        nav_date = data.get('nav_date') or data.get('trade_date')
        official = _lookup_unit_nav(db, symbol, nav_date, exact=True)
        if official:
            price = float(official)
            nav_pending = False  # 官方值已在库：无需回填，走正常路径
        else:
            placeholder = _lookup_unit_nav(db, symbol, nav_date, exact=False)
            price = float(placeholder) if placeholder else 1.0
            nav_pending = True
    data['avg_price'] = price
    if not shares_manual or qty <= 0:
        net_yuan = float(amount or 0) - float(data.get('fee', 0) or 0)
        if net_yuan <= 0:
            raise ValueError('买入金额需大于手续费，净值缺失时才能暂算份额')
        qty = round(net_yuan / price, 4)
        data['quantity'] = qty
    return price, qty, nav_pending


def _validate_buy_inputs(
    data: dict,
    asset_type: str,
    symbol: str,
    qty: float,
    price: float,
    amount: float,
    is_balance: bool = False,
) -> None:
    """校验数量/价格/金额，以及买入的整手规则。"""
    if is_balance:
        # balance 模式没有份额/净值概念，只校验金额——市值即由金额累加而来
        if amount <= 0:
            raise ValueError('balance 模式必须提供大于 0 的金额（amount）')
        return

    if qty <= 0:
        raise ValueError('数量必须大于 0')
    if price <= 0:
        raise ValueError('价格必须大于 0')

    # lot check：买入仅校验本次数量合法（起买单位/步长），与当前持有量无关。
    # #541 豁免：配股缴款不是**申报**买入，数量由配股比例算出（11 股这种非整手
    # 结果完全正常），拿「一手起买」去卡它会把真实配股判成非法交易。
    if not data.get('skip_lot_check'):
        valid, err_msg = validate_buy(symbol, data.get('market', ''), asset_type, qty)
        if not valid:
            # 申购段不是可上市证券（D97）：走到这说明打新别名没命中，报真问题，别让用户去改数量
            if is_subscription_code(symbol):
                raise ValueError(
                    f'申购码 {symbol} 未能解析上市代码，无法入账；请在导入预览页把该行标的代码补全为上市代码后重新导入'
                )
            raise ValueError(err_msg)

    if price <= 0:  # pragma: no cover - 上方已拦；保留原实现的兜底错误码
        raise SBException(
            code=ErrorCode.INVALID_PARAMS.code,
            message=ErrorCode.INVALID_PARAMS.msg,
            status_code=400,
            detail={'field': 'avg_price', 'value': price},
        )


def upsert_position_on_buy(db: Session, data: dict, intent: BuyIntent) -> tuple[Position, bool]:
    """合并既有持仓或新建一行；返回 (position, is_new)。"""
    same = intent.existing

    # 清仓后再次买入（#2343）：同账户同标的受 `uq_positions_ledger_symbol(_norm)`
    # 双唯一约束，「新建一行」物理不可行，只能复用清仓保留的同一行。
    # 复用的核心动作是**重置锚点**为新一轮起点（0 份 / 0 成本额 / 清仓日 / manual），
    # 否则上一轮的成本额残留会把本轮成本派生错（实测 1.60 → 1.4375，虚低 10.2%，
    # 上一轮利润漏进本轮成本，浮盈虚高且用户无从察觉）。
    # 重置后本笔归属日 > 清仓日 → 必然「未被锚点包含」，走正常合并逻辑。
    if same is not None and same.ownership_status == OwnershipStatus.CLEARED.value:
        reactivate_cleared_position(same, intent.effective_confirm_date)
        logger.info(
            '已清仓持仓重新激活（新一轮周期）: position={} symbol={} 新锚点日={}',
            same.id,
            same.symbol,
            same.snapshot_date,
        )

    covered_by_anchor = is_covered_by_anchor(same, intent.effective_confirm_date)
    if same is not None:
        _merge_into_existing(db, same, data, intent, covered_by_anchor=covered_by_anchor)
        return same, False
    return _create_position_row(db, data, intent, covered_by_anchor=covered_by_anchor)


def _merge_into_existing(
    db: Session, same: Position, data: dict, intent: BuyIntent, covered_by_anchor: bool = False
) -> None:
    """把本笔买入合并进既有持仓行（份额/成本/溯源/模式自愈）。"""
    # 自愈回填（#2372）：存量持仓行可能因上游漏写快照而 name/account_name
    # 为 NULL（实测基金转换转入腿建的持仓两个快照全空）。按 ID 反查补上，
    # 否则交易列表显示「未知资产/未知账户」、持仓明细退化成 6 位编码。
    # 仅在缺失时写，已有快照不动（快照是展示冗余，ID 才是权威）。
    if not same.name:
        same.name = _resolve_fund_name_by_code(db, same.symbol)
    if not same.account_name and same.ledger_id:
        same.account_name = _resolve_ledger_name_by_id(db, same.ledger_id)

    if intent.is_balance:
        # balance 合并：份额/均价无意义（quantity 恒为 0，直接除会 ZeroDivisionError），
        # 只累加可写市值并刷新覆写时间
        same.market_value_override = (same.market_value_override or 0) + intent.amount_cents
        same.value_override_at = datetime.now()
        # 投顾组合自愈（D70）：存量行可能是在写入约束落地前按 nav 建出来的，
        # 那一行没有净值、市值恒 0。再次买入时顺手把模式纠正过来，让「同一组合
        # 两种计价模式并存」不至于永久留在库里。只对 portfolio 做——其他品类
        # 若被以 balance 入参合并，擅自改模式会把份额口径静默作废。
        if intent.asset_type == 'portfolio':
            same.valuation_mode = ValuationMode.BALANCE.value
    elif covered_by_anchor:
        # 这笔交易已包含在快照里（confirm_date <= 锚点日）：**只写流水，不动份额**。
        # 快照本身已经反映了它，再加一次就是重复累加。
        # 不更新 import_hash：持仓的「最后写入」仍是那张快照，锚点溯源不能被
        # 一条历史流水改写成交易日期。
        logger.debug(
            '交易已含在快照锚点内，仅落流水: position={} symbol={} confirm={} anchor={}',
            same.id,
            intent.symbol,
            intent.effective_confirm_date,
            same.snapshot_date,
        )
    else:
        total_qty_units = same.quantity + intent.qty_units
        old_cost = Money.multiply_price_quantity(same.avg_price, same.quantity)
        # 用 Decimal 计算均价以避免精度损失
        total_qty = Money.min_unit_to_shares(total_qty_units)
        total_cost = Money.cents_to_yuan(old_cost) + Money.cents_to_yuan(
            Money.multiply_price_quantity(intent.price_units, intent.qty_units)
        )
        same.avg_price = Money.yuan_to_price_units(round(total_cost / total_qty, 4))
        same.quantity = total_qty_units

    # issue #928: 合并时同步溯源字段（交割单覆盖手动录），并刷新 import_hash
    if 'source' in data:
        same.source = data['source']
    if 'source_broker' in data:
        same.source_broker = data['source_broker']
    if not covered_by_anchor:
        same.import_hash = compute_position_hash(
            source=same.source,
            ledger_id=intent.ledger_id,
            symbol=intent.symbol,
            snapshot_date=_snapshot_date(data),
        )
    db.flush()


def _create_position_row(
    db: Session, data: dict, intent: BuyIntent, covered_by_anchor: bool = False
) -> tuple[Position, bool]:
    """新建持仓行；撞 `uq_positions_import_hash` 时转 upsert。"""
    position_data = {k: v for k, v in data.items() if k in _ALLOWED_POSITION_FIELDS}
    position_data['asset_type'] = intent.asset_type
    position_data['avg_price'] = intent.price_units
    position_data['quantity'] = intent.qty_units
    position_data['current_price'] = intent.price_units
    position_data['symbol'] = intent.symbol
    position_data['ledger_id'] = intent.ledger_id
    position_data['family_id'] = intent.family_id
    # 快照回填（#2372）：调用方（如基金转换转入腿）只传 ledger_id 不传名称时，
    # 按 ID 反查补 name/account_name——它们是展示快照不是查询键，但空快照会让
    # 交易列表出「未知资产/未知账户」、持仓明细只剩 6 位编码。
    if not position_data.get('name'):
        position_data['name'] = _resolve_fund_name_by_code(db, intent.symbol)
    if not position_data.get('account_name'):
        position_data['account_name'] = _resolve_ledger_name_by_id(db, intent.ledger_id)
    # #1174 双态计价：显式落计价模式；balance 模式把金额直接写成可写市值
    position_data['valuation_mode'] = intent.mode
    if intent.is_balance:
        position_data['market_value_override'] = intent.amount_cents
        position_data['value_override_at'] = datetime.now()
    # issue #928: 生成持仓去重哈希（source|ledger_id|symbol|snapshot_date）
    src = data.get('source', PositionSource.MANUAL.value)
    position_data['source'] = src
    position_data['import_hash'] = compute_position_hash(
        source=src, ledger_id=intent.ledger_id, symbol=intent.symbol, snapshot_date=_snapshot_date(data)
    )

    try:
        position = Position(**position_data)
        db.add(position)
        db.flush()
    except IntegrityError:
        position = _adopt_on_import_hash_conflict(
            db, data, intent, position_data['import_hash'], covered_by_anchor=covered_by_anchor
        )
    return position, True


def _adopt_on_import_hash_conflict(
    db: Session, data: dict, intent: BuyIntent, import_hash: str, covered_by_anchor: bool = False
) -> Position:
    """撞 `uq_positions_import_hash`：同内容持仓已存在（如手动录后又交割单导入）。

    转 upsert 语义——合并数量/成本，溯源跟随末次写入（交割单优先级高于手动录）。
    """
    db.rollback()
    logger.info('持仓 import_hash 撞 key，转 upsert 更新既有记录')
    existing = db.query(Position).filter(Position.import_hash == import_hash).first()
    if existing is None:
        raise

    if intent.is_balance:
        # 同合并分支：balance 模式只累加可写市值，不碰份额/均价
        existing.market_value_override = (existing.market_value_override or 0) + intent.amount_cents
        existing.value_override_at = datetime.now()
    elif covered_by_anchor or is_covered_by_anchor(existing, intent.effective_confirm_date):
        # 撞 key 撞到的持仓若已有锚点、且本笔已被快照包含 → 同样只写流水。
        # 这里必须再判一次：`existing` 是撞 key 后**重新查出**的行，可能
        # 不是入口处的 `same`（two rows same import_hash 的历史数据）。
        logger.debug(
            '撞 key 转 upsert：交易已含在锚点内，仅落流水: position={} symbol={}',
            existing.id,
            intent.symbol,
        )
    else:
        total_qty_units = existing.quantity + intent.qty_units
        old_cost = Money.multiply_price_quantity(existing.avg_price, existing.quantity)
        total_qty = Money.min_unit_to_shares(total_qty_units)
        existing.avg_price = Money.yuan_to_price_units(
            round(
                (
                    Money.cents_to_yuan(old_cost)
                    + Money.cents_to_yuan(Money.multiply_price_quantity(intent.price_units, intent.qty_units))
                )
                / total_qty,
                4,
            )
        )
        existing.quantity = total_qty_units

    # 溯源字段跟随末次导入来源（交割单覆盖手动录）
    existing.source = data.get('source', PositionSource.MANUAL.value)
    existing.source_broker = data.get('source_broker')
    db.flush()
    return existing


def write_buy_transaction(db: Session, data: dict, intent: BuyIntent, position: Position, is_new: bool) -> Position:
    """落买入流水、挂回孤儿、触发净值回填与自选同步。"""
    # 本模块只在函数内导入主模块的名字：`position_service` 在模块级导入本模块，
    # 模块级反向导入会形成加载期循环（本仓既有范式：函数级导入 + noqa）。
    from app.services.position_service import (  # noqa: PLC0415
        _get_default_notes,
        _resolve_money_fund_flag,
        _silent_ensure_watchlist,
    )

    # #863 口径 A + #1657 修复：写路径货基冗余判定 + 互斥挂回（孤儿流水并入持仓表达，
    # 使同 (ledger, symbol) 资金只以持仓市值计入总资产，不双计、不漏计）。
    # 无论 is_money_fund 判定如何都尝试挂回（幂等），避免判定不一致时漏挂回。
    position.is_money_fund = _resolve_money_fund_flag(intent.symbol, intent.asset_type, data.get('is_money_fund'))
    db.flush()  # 确保新建持仓已落库拿到 id，避免挂回孤儿流水时 position_id 为 None
    _reattach_orphan_flows(db, intent.ledger_id, intent.symbol, position.id, intent.family_id)

    txn_type = intent.op_type if intent.op_type in ('buy', 'deposit') else 'buy'
    notes = data.get('notes') or _get_default_notes(intent.op_type, is_new)

    TransactionService.create(
        db=db,
        position_id=position.id,
        txn_type=txn_type,
        symbol=intent.symbol,
        trade_date=data.get('trade_date'),
        # 复用解析阶段已算好的确认日（与锚点判定同一口径，不重算第二遍）
        confirm_date=intent.effective_confirm_date,
        asset_type=intent.asset_type,
        link_group_id=data.get('link_group_id'),
        quantity=intent.qty_units,
        price=intent.price_units,
        fee=Money.yuan_to_cents(data.get('fee', 0) or 0),
        # #2137 费用拆分：data 带明细才落四列，否则四列留 NULL（未拆分）
        **_fee_breakdown_kwargs(data),
        # balance 模式没有 price×qty 可算，流水金额直接取用户录入的金额
        amount=(
            intent.amount_cents
            if intent.is_balance
            else Money.multiply_price_quantity(intent.price_units, intent.qty_units)
        ),
        status='success',
        # #2372：快照缺失时按 ID 兜底反查（position 行刚回填也可能失败，
        # 如 market 名录缺该代码）——绝不留 NULL 让前端显示「未知资产/未知账户」。
        # `or` 短路：快照已在时零额外查询。
        position_name=position.name or _resolve_fund_name_by_code(db, intent.symbol),
        account_name=position.account_name or _resolve_ledger_name_by_id(db, intent.ledger_id),
        notes=notes,
        ledger_id=intent.ledger_id,
        import_hash=data.get('import_hash'),
        family_id=intent.family_id,
        # #1232 决策 11：流水来源与持仓同源（记一笔默认 manual，交易导入/对账补录按 data.source）
        source=data.get('source') or PositionSource.MANUAL.value,
        # 净值缺失先记账：pending 标记 + 元数据（nav_date/shares_manual）供 nav_backfill 消费；
        # 非 pending 场景透传调用方 extra（如基金转换的 extra.conversion，§3.2）
        entry_status='pending_nav' if intent.nav_pending else None,
        extra=(
            json.dumps(
                {
                    'nav_pending': True,
                    'nav_date': intent.nav_date_extra,
                    'shares_manual': intent.shares_manual,
                },
                ensure_ascii=False,
            )
            if intent.nav_pending
            else data.get('extra')
        ),
    )

    db.flush()
    db.refresh(position)
    try:
        async_backfill.trigger_backfill(intent.asset_type, intent.symbol)
    except Exception:
        pass
    # #1458 后续：买入即入自选（静默，失败不影响主链路）
    _silent_ensure_watchlist(db, intent.family_id, intent.symbol)
    return position


def _snapshot_date(data: dict) -> date:
    """快照日：优先 confirm_date；缺失降级为落库当日（规范 §3.3，保证同日同产品汇总一条）。"""
    raw_snap = data.get('confirm_date') or date.today()
    return raw_snap if isinstance(raw_snap, date) else datetime.fromisoformat(raw_snap).date()
