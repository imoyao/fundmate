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
"""

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from flask import has_app_context
from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import (
    ALLOCATION_LABELS,
    MARKET_LABELS,
    TYPE_LABELS,
    AnchorKind,
    OwnershipStatus,
    PositionSource,
    ValuationMode,
)
from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.core.symbol_utils import derive_security_type, normalize_by_venue, split_symbol, strip_exchange_prefix
from app.core.utils import get_confirm_date, paginate
from app.core.venues import asset_types_of_venue, resolve_venue
from app.domains.funds.models import DailyWorth, Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, PositionImportMeta, resolve_sales_institution_id
from app.domains.transactions.models import Transaction
from app.services import async_backfill
from app.services.fund_utils import CASH_EQUIVALENT_ASSET_TYPES, is_money_fund_symbol, normalize_fund_code
from app.services.import_records import compute_position_hash
from app.services.pnl_service import compute_sell_realized_cents
from app.services.position_presenter import enrich_position_dict
from app.services.position_scope import exclude_cleared
from app.services.symbol_scope import build_position_symbol_conditions
from app.services.trading import TransactionService, validate_buy, validate_sell
from app.services.watchlist_service import (
    ensure_watchlist_for_positions,
    reconcile_watchlist_status,
)

# 单用户遗留口径：离线脚本（无请求上下文）且入参也没给 family_id 时的唯一退路。
_LEGACY_SINGLE_FAMILY_ID = 1

# #2137 费用拆分数据键（元）→ Transaction 列名（分）。四键全空 = 未拆分。
_FEE_BREAKDOWN_KEYS = ('fee_commission', 'fee_stamp_duty', 'fee_transfer_fee', 'fee_other')
_FEE_BREAKDOWN_COLUMNS = ('commission', 'stamp_duty', 'transfer_fee', 'other_fee')


def _fee_breakdown_kwargs(data: dict) -> dict:
    """从数据字典提取费用拆分 kwargs（#2137，元 → 分）。

    四键**全空**（缺键 / None / 0 之外的未提供）→ 返回空 dict：Transaction 四列
    留 NULL = 未拆分，聚合 fee 为权威，行为与改造前一致。
    任一键有值 → 四键必须齐全（缺的显式补 0），否则抛 ValueError——
    与 Transaction 的 before_insert 不变量同口径，fail closed 在写入前。
    """
    raw = [data.get(k) for k in _FEE_BREAKDOWN_KEYS]
    if all(v is None or v == '' for v in raw):
        return {}
    if any(v is None or v == '' for v in raw):
        missing = [k for k, v in zip(_FEE_BREAKDOWN_KEYS, raw) if v is None or v == '']
        raise ValueError(f'费用拆分必须四类齐全（缺的类别显式传 0）：未提供 {missing}')
    return {col: Money.yuan_to_cents(v) for col, v in zip(_FEE_BREAKDOWN_COLUMNS, raw)}


def _resolve_family_id(data: dict) -> int:
    """解析本次写入归属的家庭 ID（#1305 #22）。

    WHY 不能继续用「取不到就填 1」的兜底写法：缺字段时会把流水/持仓**静默挂到
    family 1**。多家庭场景下这不是「默认值不好看」，而是**数据越权**——别人家里
    凭空长出一笔资产，而原主人按 family 过滤后反而看不到自己的数据。

    优先级：
    1. 显式入参（视图层 `data['family_id'] = get_family_id()` 已注入，见 positions/views.py）；
    2. 请求上下文 `g.family_id`（鉴权中间件注入）；
    3. 单用户遗留口径 1 —— **仅当没有请求上下文时**。离线脚本（`backend/scripts/*.py`
       直接调本服务）此时 `g` 不可用，`getattr(g, ...)` 会抛 RuntimeError，
       所以必须先用 `has_app_context()` 判一下，不能无条件取上下文。
    """
    fid = data.get('family_id')
    if fid:
        return fid
    if has_app_context():
        # 延迟导入：本模块被离线脚本导入时 Flask 上下文尚未建立
        from app.core.auth import get_family_id

        return get_family_id()
    return _LEGACY_SINGLE_FAMILY_ID


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


def _resolve_fund_name_by_code(db: Session, symbol: Optional[str]) -> Optional[str]:
    """按代码反查基金名称（market 域名录**点查**，非 JOIN）。

    WHY（#2372）：``Position.name`` / ``Transaction.position_name`` 是**冗余快照**，
    多个写入路径（基金转换转入腿、部分导入器）只传 ``ledger_id`` 不传名称，
    快照落 NULL 后交易列表显示「未知资产」、持仓明细退化成 6 位编码
    （真库实测：转换建的持仓 618 ``name=NULL``，流水 3001 两个快照全 NULL）。
    ``symbol``（→ ``funds.fund_code``）才是权威键，快照缺失时按 ID 反查回填，
    不依赖调用方自觉传名称。

    只做单行点查：双库架构下 market / user 分引擎，路由会话按表分发，
    点查安全；查不到返回 None（由调用方兜底），不猜、不建行。
    """
    if not symbol:
        return None
    code = strip_exchange_prefix(str(symbol))
    if not code:
        return None
    fund = db.query(Fund).filter(Fund.fund_code == code).first()
    return fund.name if fund else None


def _resolve_ledger_name_by_id(db: Session, ledger_id: Optional[int]) -> Optional[str]:
    """按账户 ID 反查账户名（user 域 ``ledgers`` 点查）。

    同 ``_resolve_fund_name_by_code``：``account_name`` 是**可编辑字段**的快照，
    快照缺失/漂移时按 ``ledger_id``（真外键）反查——前端据此显示真实账户名而非
    「未知账户」，下游也不得再拿名称当匹配键（真库存在重名账户：#2372）。
    """
    if not ledger_id:
        return None
    ledger = db.get(Ledger, ledger_id)
    return ledger.name if ledger else None


def _find_position_by_identity(
    db: Session,
    data: dict,
    symbol: str = '',
    name: str = '',
    active_only: bool = False,
) -> Optional[Position]:
    """导入 / 孤儿链路按**身份键**查找持仓（#2372：账户 ID 优先，名称不做跨账户键）。

    匹配优先级（#2372 一级键 + #1920 名称兜底的安全重建）：
    1. ``ledger_id`` 有值 → 按 ``(ledger_id, symbol)`` 精确匹配；symbol 缺失时按
       ``(ledger_id, name)`` 兜底（#1920 交割单无代码场景——账户 ID 已把范围收敛到
       单账户，名称只在账户内做键，不再跨账户猜）；
    2. ``ledger_id`` 为空 → 只匹配同属未归档（``ledger_id IS NULL``）的同代码持仓；
    3. 仍未命中且入参带 ``account_name`` → 按 ``(account_name, symbol|name)`` 在
       **全家庭**范围内兜底（#1920 名称回查；覆盖只带账户名、无 ledger_id 的遗留
       导入数据），**唯一命中才关联**。

    为什么名称不能直接做一级键、重名也不许任取一个：``account_name`` 是**可编辑
    字段**的快照，改名即失配；真库存在重名账户（支付宝×2 / 天天基金×2），按名称
    匹配会把卖出 / 分红 / 送股记到**另一个账户**的持仓上，甚至改错别人的份额
    （#2372）。三级兜底命中多个时返回 None 落孤儿（安全降级：孤儿链路有告警，
    串账户则是静默错账，两者不可兼得时选前者）。
    """
    family_id = _resolve_family_id(data)
    if not symbol and not name:
        return None
    key_field = Position.symbol if symbol else Position.name
    key = symbol or name
    query = db.query(Position).filter(Position.family_id == family_id)
    if active_only:
        query = query.filter(Position.ownership_status == OwnershipStatus.ACTIVE.value)
    ledger_id = data.get('ledger_id')
    if ledger_id is not None:
        # 一级：账户 ID 已把范围收敛到单账户，symbol/name 只在账户内做键
        return query.filter(Position.ledger_id == ledger_id, key_field == key).first()
    # 二级：未归档数据优先匹配未归档持仓，不拿账户名跨账户猜
    hit = query.filter(Position.ledger_id.is_(None), key_field == key).first()
    if hit is not None:
        return hit
    # 三级兜底（#1920 名称回查 / 只带 account_name 的遗留导入数据）
    account_name = data.get('account_name')
    if not account_name:
        return None
    rows = query.filter(Position.account_name == account_name, key_field == key).all()
    if len(rows) == 1:
        # 兜底命中必须留痕：数据侧缺 ledger_id 是**待回补**的脏数据，
        # 静默关联会让「快照缺失」隐形（#2372 的教训），日志即回补工单。
        logger.info(
            '身份键按账户名唯一兜底关联（ledger_id 缺失，待回补）: family={} account_name={} {}={} → position_id={}',
            family_id,
            account_name,
            'symbol' if symbol else 'name',
            key,
            rows[0].id,
        )
        return rows[0]
    if rows:
        logger.warning(
            '身份键兜底命中多个重名持仓，拒绝跨账户猜疑（#2372）: family={} account_name={} {}={} n={}',
            family_id,
            account_name,
            'symbol' if symbol else 'name',
            key,
            len(rows),
        )
    return None


def query_transactions_by_identity(db: Session, position: Position):
    """按**身份键**构造流水查询（#2372）：``(ledger_id, symbol)``，未归档持仓只匹配未归档流水。

    ## 为什么不是 ``(symbol, account_name)``

    ``account_name`` 是 ``ledgers.name`` 的**可编辑快照**——账户改名后，改名前落库的
    流水与新名字天然对不上；真库还存在重名账户（支付宝×2 / 天天基金×2），按名称过滤会
    把**另一个账户**的交易一并卷进来。持仓明细页的兜底查询因此必须按 ``ledger_id`` 收敛。

    ``ledger_id`` 为 NULL（未归档持仓 / 探市迁移行）时，只匹配同属未归档的流水——
    宁可少查，也不拿名字去猜（猜错的表现是明细里混入别人账户的交易，且不会报错）。

    ## 为什么放在 service 而不是视图层

    视图层的判据是「只做 HTTP 编排」（``decisions.md`` 2026-09-19），且
    ``scripts/check_view_thickness.py`` 会按行数拦截视图层变厚。同一段兜底过滤在
    ``get_position_transactions`` 与 ``delete_position`` 两处都需要，下沉后一处定义、两处复用。
    """
    query = db.query(Transaction).filter(Transaction.symbol == position.symbol)
    if position.ledger_id is not None:
        return query.filter(Transaction.ledger_id == position.ledger_id)
    return query.filter(Transaction.ledger_id.is_(None))


def resolve_ledger_change(
    db: Session,
    position: Position,
    update_data: dict,
    family_id: int,
) -> Optional[str]:
    """处理持仓的 `ledger_id` 变更：校验目标账户存在，并同步 `account_name` 快照。

    返回 ``None`` 表示通过；返回字符串是**给调用方 abort(404) 的文案**（HTTP 语义留在
    视图层，本方法不 import flask）。原地修改 ``update_data`` 补上快照字段。

    ## 为什么两件事必须一起做

    只校验不同步 ⇒ 归档 / 迁移后留下「外键指向新账户、展示名还是旧账户」的漂移行，
    账户改名时 `sync_account_name_snapshots` 按 `ledger_id` 级联刷新，把用户刚迁走的
    持仓显示名**刷回旧账户**——一次「迁移」在界面上被静默还原（#2372 症状 3 同构）。
    只同步不校验 ⇒ 允许绑定一个不存在的幽灵账本，外键失去意义。

    幂等：`ledger_id` 未变化（含未传）时直接返回，不写任何字段。
    """
    new_id = update_data.get('ledger_id')
    if new_id is None or new_id == position.ledger_id:
        return None
    ledger = db.query(Ledger).filter_by(id=new_id, family_id=family_id).first()
    if not ledger:
        return '目标账户不存在'
    update_data['account_name'] = ledger.name
    return None


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
_SPECIFIC_ASSET_TYPES = {'etf', 'bond', 'fund', 'money_fund', 'reverse_repo', 'cash'}


def _get_asset_type(data: dict, default: str = 'stock') -> str:
    """
    录入阶段确定资产类型：显式具体类型 > 代码前缀推断 > 默认 stock。

    历史债背景：PositionCreate.asset_type 使用 validation_alias='type'，
    model_dump() 输出的是字段名 `asset_type`，而 importer 路径直接构造 `type` key，
    导致不同调用方传入的 key 不一致。此处收敛读取端，保证流水 asset_type 落库正确。

    分类下沉到录入阶段（#1264 / #1266）：仅当显式类型缺失，或显式为泛化默认 'stock' 时，
    才按代码前缀推断（沪 51/56/58、深 15/16 → ETF；11/12 → 可转债），
    以免把已正确标注为 fund/money_fund 的基金（代码前缀可能与股票/可转债重合）误判成股票。
    """
    explicit = data.get('asset_type') or data.get('type')
    if explicit and explicit in _SPECIFIC_ASSET_TYPES:
        return explicit
    symbol = data.get('symbol') or ''
    market, code = split_symbol(symbol)
    derived = derive_security_type(code, market)
    return derived or (explicit or default)


def _resolve_confirm_date(data: dict, asset_type: str):
    """解析本笔交易的**确认日**（锚点判定与流水落库共用同一口径）。

    从 `process_buy_or_deposit` 内联逻辑抽出，原因：锚点判定（这笔交易是否已被快照包含）
    必须发生在合并持仓**之前**，而原实现把确认日计算放在创建流水时（合并之后）。
    两处各算一遍必然分叉——这正是本类 bug 的成因模式（同一语义两份实现）。

    场外基金：前端给了 confirm_date 时按 `get_confirm_date(trade_date, ...)` 重算
    （T+1 确认、15:00 后顺延）；计算失败降级用前端传入值，不阻断记账。
    """
    confirm_date = data.get('confirm_date')
    if asset_type == 'fund' and data.get('confirm_date'):
        try:
            trade_date = data.get('trade_date')
            if isinstance(trade_date, str):
                trade_date = datetime.strptime(trade_date, '%Y-%m-%d').date()
            is_after_15 = data.get('isAfter15', False)
            fund_type = data.get('fund_type', 'domestic')
            confirm_date = get_confirm_date(trade_date, fund_type=fund_type, is_after_15=is_after_15)
        except Exception:
            logger.warning('确认日计算失败，使用前端传入值')
    return confirm_date


def _is_covered_by_anchor(position: Position, effective_date) -> bool:
    """这笔流水是否已包含在持仓快照锚点里（包含则**不得**再驱动 quantity）。

    判定：`归属日 <= 快照日` → 已包含。按 confirm_date 而非 trade_date：
    基金份额在确认日（T+1）才真实变动，快照反映份额登记状态。

    边界：日期无法解析 → 视为「未包含」（保持旧行为，宁可多算也不静默丢流水），
    由对账工作台暴露差异。这与 `compute_anchored_state` 的「排除 + 告警」不同：
    那里是派生（必须唯一），这里是写入（不能吞掉用户刚录的交易）。
    """
    if position is None or position.snapshot_quantity is None or position.snapshot_date is None:
        return False
    if position.ownership_status != 'active':
        return False
    if effective_date is None:
        return False
    if isinstance(effective_date, str):
        # 卖出/导入路径可能直接透传 ISO 字符串（未经 _resolve_confirm_date 归一）
        try:
            day = datetime.strptime(effective_date[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return False
    elif hasattr(effective_date, 'date'):
        day = effective_date.date()
    else:
        day = effective_date
    return day <= position.snapshot_date


def _mark_position_cleared(position: Position, when=None) -> None:
    """把持仓标记为**已清仓**（行保留，issue #2343 第二步）。

    取代过去的 `db.delete(position)`。行保留后三样东西不会随清仓消失：
    - 快照锚点四列（`snapshot_quantity / snapshot_avg_price / snapshot_date / anchor_kind`）
      ——删除卖出流水触发重建时仍走锚点口径，不会退回「全量流水」二次累加；
    - `avg_price`（上一轮的成本基线，「历史曾持有」可追溯）；
    - 名下流水（本来就不级联，但持仓行在，`position_id` 归属不断链）。

    `cleared_at` 记录**何时**清仓，取**清仓流水的确认日**（业务事实，可测试、可回放），
    不是墙钟时间——「系统何时处理的」没有业务意义，且会让「清仓日 < 再买入日」的
    常规时间线在补录场景下倒挂。`when` 接受 str/date/datetime，解析失败退墙钟。

    重新激活时**保留不清**本列——它是「清仓后再买入」新一轮周期的下界，
    「当前是否已清仓」一律看 `ownership_status`。
    """
    position.quantity = 0
    position.ownership_status = OwnershipStatus.CLEARED.value
    if when is None:
        position.cleared_at = datetime.now()
    elif isinstance(when, datetime):
        position.cleared_at = when
    elif isinstance(when, date):
        position.cleared_at = datetime(when.year, when.month, when.day)
    else:
        try:
            position.cleared_at = datetime.strptime(str(when)[:10], '%Y-%m-%d')
        except ValueError:
            position.cleared_at = datetime.now()


def _reactivate_cleared_position(position: Position, first_flow_date) -> None:
    """把已清仓持仓重新激活为**新一轮周期**（#2343）。

    同账户同标的受 `uq_positions_ledger_symbol(_norm)` 双唯一约束，清仓行保留后
    再次买入**必然**复用同一行——「新建一行」在数据库层面不可行（2026-10-18 实测
    INSERT 直接撞约束）。

    复用的关键动作是**重置锚点**，而不是只把状态改回 active：

        锚点 = (0 份, 0 成本额, 清仓日, manual)

    不重置的后果（同日实测）：旧锚点的成本额按卖出比例核销后仍有残留，新一轮
    3000 份 @1.60 会被派生成 **1.4375**（虚低 10.2% ⇒ 浮盈虚高）——上一轮的利润
    悄悄漏进这一轮的成本里。重置后 quantity = 0 + Σ(归属日 > 清仓日)，只认本轮流水。

    锚点日直接取**清仓日**（`cleared_at.date()`）：
    - 常规（买入在清仓之后）：清仓卖出 `== 锚点日` 被 `> anchor` 规则排除，本笔买入计入 ✓；
    - `cleared_at` 为 NULL（历史清仓行无清仓时间）：退「本笔归属日前一天」，
      保证本笔自身不被锚点吞掉；
    - **清仓当天又买入**（confirm_date == 清仓日）：买入同样被 `>` 排除 → 0 份。
      已知边界，日粒度数据无法区分同日先卖后买；刻意**不**退到前一日——那会把
      清仓卖出也计入，净额变负（比 0 份更糟）。0 份由对账工作台暴露，宁可不算不算错。

    `cleared_at` 保留不清空（周期下界），`confirm_date` 同样不动——持有天数
    口径是「首次建仓确认日」（#862 历史口径），改口径需要产品决策，本次不做。
    """
    if position.cleared_at is not None:
        anchor_date = position.cleared_at.date() if isinstance(position.cleared_at, datetime) else position.cleared_at
    elif first_flow_date is None:
        anchor_date = date.today()
    else:
        if isinstance(first_flow_date, datetime):
            day = first_flow_date.date()
        elif isinstance(first_flow_date, date):
            day = first_flow_date
        else:
            day = datetime.strptime(str(first_flow_date)[:10], '%Y-%m-%d').date()
        anchor_date = day - timedelta(days=1)

    position.ownership_status = OwnershipStatus.ACTIVE.value
    position.snapshot_quantity = 0
    position.snapshot_avg_price = 0
    position.snapshot_date = anchor_date
    position.anchor_kind = AnchorKind.MANUAL.value


def _get_default_notes(op_type: str, is_new: bool) -> str:
    """生成默认的交易备注."""
    mapping = {
        (False, 'buy'): '追加买入',
        (False, 'deposit'): '追加存入',
        (True, 'buy'): '初始买入',
    }
    return mapping.get((is_new, op_type), '存入')


def _lookup_unit_nav(db: Session, symbol: str, nav_date, *, exact: bool):
    """库内查单位净值（净值缺失先记账的定价依据）。

    exact=True 按 nav_date 精确查（官方值一次到位）；exact=False 取 ≤ nav_date
    最近一条（占位价）。nav_date 允许 date/datetime/str（str 按前 10 位解析
    YYYY-MM-DD）；解析失败、无命中或净值非正都返回 None——调用方自行兜底 1.0。
    """
    if not symbol or not nav_date:
        return None
    if isinstance(nav_date, datetime):
        d = nav_date.date()
    elif isinstance(nav_date, date):
        d = nav_date
    else:
        try:
            d = datetime.strptime(str(nav_date)[:10], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return None
    # daily_worth.fund_code 存裸 6 位码（#1662）；流水 symbol 可能带场所前缀，先剥掉
    q = db.query(DailyWorth.unit_nav).filter(DailyWorth.fund_code == strip_exchange_prefix(symbol))
    if exact:
        q = q.filter(DailyWorth.date == d)
    else:
        q = q.filter(DailyWorth.date <= d).order_by(DailyWorth.date.desc())
    row = q.first()
    if row and row[0] is not None and row[0] > 0:
        return row[0]
    return None


def _create_cash_transfer_transaction(db: Session, data: dict, txn_type: str) -> None:
    """
    为现金管理产品（货币基金/逆回购）创建孤立交易流水。
    金额转换为分后存储。
    """
    net_amount = abs(data.get('net_amount', 0) or 0)
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=data.get('symbol', ''),
        txn_type=txn_type,
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=_get_asset_type(data),
        ledger_id=data.get('ledger_id'),
        quantity=0,
        price=0,
        fee=0,
        amount=Money.yuan_to_cents(net_amount),
        status='success',
        position_name=data.get('name', ''),
        account_name=data.get('account_name', ''),
        notes=data.get('notes') or ('现金管理产品申赎' if txn_type == 'buy' else '现金管理产品赎回'),
        import_hash=data.get('import_hash'),
        entry_status='orphan',
        family_id=_resolve_family_id(data),
        # #1232 决策 11：孤儿/现金转移流水来源透传
        source=data.get('source'),
    )
    db.flush()


def _create_orphan_transaction(
    db: Session,
    data: dict,
    txn_type: str,
    quantity: float,
    price: float,
    amount: float,
    notes: str,
) -> None:
    """
    创建孤立交易流水（无法匹配到持仓时使用）。
    所有金额和数量转换为内部单位后存储。
    """
    qty_units = Money.shares_to_min_unit(quantity)
    price_units = Money.yuan_to_price_units(price)
    amount_cents = Money.yuan_to_cents(amount) if amount else Money.multiply_price_quantity(price_units, qty_units)
    fee_cents = Money.yuan_to_cents(data.get('fee', 0) or 0)
    # #2137 费用拆分：data 带明细才落四列，否则四列留 NULL（未拆分）
    fee_breakdown = _fee_breakdown_kwargs(data)

    TransactionService.create(
        db=db,
        position_id=None,
        symbol=data.get('symbol', ''),
        txn_type=txn_type,
        trade_date=data.get('trade_date'),
        confirm_date=data.get('confirm_date'),
        asset_type=_get_asset_type(data),
        quantity=qty_units,
        price=price_units,
        fee=fee_cents,
        **fee_breakdown,
        amount=amount_cents,
        ledger_id=data.get('ledger_id'),
        status='success',
        position_name=data.get('name', ''),
        account_name=data.get('account_name', ''),
        notes=notes,
        import_hash=data.get('import_hash'),
        entry_status='orphan',
        family_id=_resolve_family_id(data),
        # #1232 决策 11：孤儿流水来源透传
        source=data.get('source'),
    )
    db.flush()


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


def _txn_effective_date(txn: Transaction):
    """流水的「归属日」：优先 confirm_date，缺失降级 trade_date 的日期部分。

    WHY 需要降级：锚点判定必须给每条流水一个可比较的日期。`confirm_date` 为 NULL 的
    份额类流水（部分导入格式 / 手工补录）若直接跳过，会在锚点重算里**静默丢掉份额**；
    若无条件计入，又会与快照重复。用 trade_date 兜底是两者之间唯一可解释的选择。
    两者都没有 → 返回 None，由调用方决定（当前口径：排除并告警，宁可少算不重复计）。
    """
    if txn.confirm_date is not None:
        return txn.confirm_date
    if txn.trade_date is not None:
        return txn.trade_date.date() if hasattr(txn.trade_date, 'date') else txn.trade_date
    return None


def _derive_state_from_txns(txns, base_qty: int, base_cost_cents: int) -> tuple[int, int]:
    """纯函数：给定基线份额/成本额，叠加流水推导 (净份额, 成本均价)。

    抽成纯函数是为了让「持仓行已被删除、需要从流水重建」的分支复用同一套加减口径，
    避免重算引擎出现第二份实现（两份实现必然分叉，正是本 bug 的成因之一）。
    """
    buy_qty = 0
    buy_cost = 0
    sell_qty = 0
    for t in txns:
        if t.txn_type in ('buy', 'deposit'):
            buy_qty += t.quantity
            buy_cost += Money.multiply_price_quantity(t.price, t.quantity)
        elif t.txn_type == 'split':
            # 送股/拆分：份额增加、成本不变（仅稀释均价）
            buy_qty += t.quantity
        elif t.txn_type in ('sell', 'withdraw'):
            sell_qty += t.quantity

    net_qty = base_qty + buy_qty - sell_qty
    base_and_buy_qty = base_qty + buy_qty
    avg_price = 0
    if base_and_buy_qty > 0:
        avg_price = Money.yuan_to_price_units(
            round(Money.cents_to_yuan(base_cost_cents + buy_cost) / Money.min_unit_to_shares(base_and_buy_qty), 4)
        )
    return net_qty, avg_price


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
        txns = query.order_by(Transaction.trade_date, Transaction.id).all()
        return _derive_state_from_txns(txns, 0, 0)

    base_qty = int(position.snapshot_quantity)
    # 快照成本额（分）：份额 × 快照均价。snapshot_avg_price 必须与份额同批落库，
    # 否则拿 avg_price 顶替会得到「被流水加权过」的价，成本永久偏。
    base_cost = Money.multiply_price_quantity(int(position.snapshot_avg_price or 0), base_qty)
    included = []
    for t in query.order_by(Transaction.trade_date, Transaction.id).all():
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
    return _derive_state_from_txns(included, base_qty, base_cost)


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


def _find_existing_position(
    db: Session,
    ledger_id,
    family_id: int,
    symbol: str,
    venue: str,
    *,
    active_only: bool = False,
) -> Optional[Position]:
    """按「venue 感知的归一身份」定位既有持仓（#1662）—— 写入层查重的唯一入口。

    为什么不能只用 `filter_by(symbol=...)`：`positions` 的唯一约束是**字面量**
    `UNIQUE(ledger_id, symbol)`，历史上同一只基金可能并存两种写法（`SZ004369` 与
    `004369`）→ 同一只基金两行（#1662 本机实测 2 组）。本函数把候选按 6 位码展开成
    各前缀写法，再按 **venue** 约束过滤（`asset_type → venue`），只允许**同一交易场所**
    的行被复用：

    - 场外（OTC，裸码约定）→ 只匹配 `fund` / `money_fund` 行；
    - 场内（EXCHANGE）→ 只匹配 `stock` / `etf` / `bond` / `reverse_repo` 行。

    `asset_type` 为 NULL 的历史行一并纳入：无法判场所时宁可复用，也不要再生成重复行
    （审计脚本 `scripts/audit_symbol_venue_conformance.py` 会把这类行暴露出来人工确认）。
    venue 为空（判定不出场所）时不做场所过滤，退回「同归一码即同标的」。
    """
    code = normalize_fund_code(symbol)
    forms = {symbol} if not code else {symbol, code, *(f'{m}{code}' for m in ('SH', 'SZ', 'BJ'))}
    query = db.query(Position).filter(
        Position.ledger_id == ledger_id,
        Position.family_id == family_id,
        Position.symbol.in_(forms),
    )
    # 只有明确判定出场所时才按场所过滤；venue 为空（判不出）→ 退回「同归一码即同标的」。
    # 不能直接写 asset_types_of_venue(venue)：它对空串返回的是「无场所实体」集合
    # (manager/portfolio/index)，非空 → 会误触发下方过滤，把真实持仓全滤掉。
    allowed = asset_types_of_venue(venue) if venue else ()
    if allowed:
        query = query.filter(or_(Position.asset_type.in_(allowed), Position.asset_type.is_(None)))
    if active_only:
        query = query.filter(Position.ownership_status == 'active')
    # 取最新一条（id 降序），确保命中最近建仓的持仓
    return query.order_by(Position.id.desc()).first()


def find_orphan_cash_flows(db: Session, ledger_id, symbol: str, family_id: int) -> list[Transaction]:
    """#863 口径 A：同 (ledger_id, family_id, symbol) 的**未挂回**货基 / 逆回购流水（非收益行）。

    匹配口径的**唯一入口**——写入层挂回（`_reattach_orphan_flows`）与一次性修复脚本
    （`scripts/fix_orphan_money_fund_reattach.py`）都必须经本函数，避免两处口径漂移。
    #1657 复审即栽在这：脚本曾用 `symbol` 精确相等，`SZ001937` ↔ `001937` 这类跨形态
    组合被静默漏挂，而本机 3 个成功案例恰好都是裸码对裸码，把缺陷掩盖了。

    口径说明：`normalize_fund_code` 会剥掉 `SZ/SH/BJ` 前缀与分隔符，故原候选集
    `{code, 'SZ'+code, 'SH'+code}` 恒等价于 `{code}`——判定即两侧归一化后相等。

    `symbol` 归一化不出 6 位数字时（非标准基金代码，如测试里的 `MF001`、手工建的
    非基金标的）**退回精确相等**：原实现此时退化为候选集 `{''}`，会让「同样归一化
    失败的流水」互相匹配、把不相干的孤儿流水一并吸走；但直接短路成空又会破坏
    非标准代码的正常挂回（`MF001` ↔ `MF001` 应当命中）。
    """
    # #1305 #17：`or_` 已在模块顶部导入，函数内不再重复 import（原为每次调用重复导入）
    code = normalize_fund_code(symbol)

    rows = (
        db.query(Transaction)
        .filter(
            Transaction.ledger_id == ledger_id,
            Transaction.position_id.is_(None),
            Transaction.family_id == family_id,
            Transaction.asset_type.in_(CASH_EQUIVALENT_ASSET_TYPES),
            or_(Transaction.is_income.is_(None), Transaction.is_income.is_(False)),
        )
        .all()
    )
    if code:
        return [t for t in rows if t.symbol and normalize_fund_code(t.symbol) == code]
    return [t for t in rows if t.symbol == symbol]


def _reattach_orphan_flows(db: Session, ledger_id, symbol: str, position_id: int, family_id: int) -> None:
    """#863 口径 A 写入层互斥：把同 (ledger_id, symbol) 的孤儿货基流水挂回持仓。

    互斥语义：同一资金同一 (ledger_id, symbol) 只能有一种表达——持仓 或 孤儿净额。
    建仓后把历史孤儿流水（position_id IS NULL、非收益行）置 position_id，使其不再
    计入孤儿净额桶；金额由持仓市值承接（净值恒 1，市值≈本金），不双计、不漏计。
    is_income 收益行不挂回（收益桶独立于本金，见 #863 D1）。

    筛选范围由 `find_orphan_cash_flows` 收口（只认现金等价物类型 + 同 ledger/family +
    归一化符号相等）。**调用方不要再拿 `position.is_money_fund` 当闸门**：该列存在历史
    未回填 / 快照判定不一致（本机 pos[445]/pos[26] 为货基却为 0），以它为准会漏挂回
    导致资金双计（#1657）；对非现金等价物持仓本函数天然无操作（幂等）。
    """
    matched = find_orphan_cash_flows(db, ledger_id, symbol, family_id)
    if matched:
        for txn in matched:
            txn.position_id = position_id
        logger.info(f'货基建仓挂回孤儿流水 {len(matched)} 条（ledger={ledger_id}, symbol={symbol}）')


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
        """
        执行买入或存入操作，返回更新或新建的持仓实例。

        force_create_position（#1233 决策 5「货基/逆回购保持建持仓」）：
        - 默认 False（交易导入）：money_fund / reverse_repo 只记孤儿资金流水、不建持仓（既有行为，
          市值由 `orphan_money_fund_totals_by_ledger` 按流水净额计入总资产）；
        - True（记一笔手动记账）：跳过现金转移分支，照常建持仓，流水关联持仓（position_id 非空），
          不再计入孤儿净额口径（与 summary 不重复计数，见 test_summary_money_fund 的持仓用例）。
        """
        symbol = data.get('symbol', '')
        qty = data.get('quantity', 0)
        price = data.get('avg_price', 0)
        op_type = data.get('op_type', 'buy')
        asset_type = _get_asset_type(data)

        # ── symbol 按 venue 归一（#1662，落库前唯一形态入口）──
        # 场内 → {MARKET}{CODE}（如 SZ159915）、场外 → 裸 6 位码（如 004369）。
        # 归一放在函数入口：持仓落库、流水落库、现金划转分支全部共享同一形态，
        # 避免「持仓带前缀 / 流水裸码」这类不一致再次出现。
        # venue 由调用方显式传入（建仓 API / 导入解析器本就知道场内/场外），
        # 缺失时按 asset_type 推断（兼容缺省，见 core/venues.venue_of_asset_type）。
        venue = resolve_venue(data.get('venue'), asset_type)
        if venue:
            symbol, _symbol_market, _ = normalize_by_venue(symbol, venue)
            data['symbol'] = symbol  # 下游（流水 / 划转）统一取 data，必须同步回写

        # 现金管理类产品：只记录流水，不创建持仓（交易导入既有行为；
        # 记一笔 force_create_position=True 时跳过此分支，走正常建仓逻辑）
        if asset_type in ('money_fund', 'reverse_repo') and not force_create_position:
            # #863 口径 A 写入层互斥：若该 (ledger, symbol) 已有 active 持仓，本笔买入并入
            # 持仓表达（走下方正常建仓合并），不产生孤儿流水——同一资金不得双表达双计。
            _lid = data.get('ledger_id')
            _family_id = _resolve_family_id(data)
            existing_pos = None
            if _lid:
                # venue 感知查重（#1662）：原实现手拼 {code, SZ+code, SH+code} 候选集，
                # 只覆盖「前缀变体」且不区分场所；改用统一辅助函数。active_only 保持
                # 原语义（仅匹配 active 持仓，避免复用已平仓 / NULL 状态旧持仓）。
                existing_pos = _find_existing_position(
                    db,
                    ledger_id=_lid,
                    family_id=_family_id,
                    symbol=symbol,
                    venue=venue,
                    active_only=True,
                )
            if existing_pos is not None:
                force_create_position = True  # 复用下方正常建仓逻辑（含孤儿流水挂回）
            else:
                _create_cash_transfer_transaction(db, data, 'buy')
                return None

        # symbol 已在函数入口按 venue 归一（#1662）。原实现按 asset_type 白名单
        # 「跳过归一化」（fund / money_fund / reverse_repo / bond 一律不归一），导致场外基金
        # 一旦带了误前缀就永远清不掉（`SZ004369` 与 `004369` 长期并存）。
        # 现在形态由 venue 决定，不再按品种打补丁。
        search_symbol = symbol

        # 查找现有持仓（家庭维度）——统一身份键 (symbol, ledger_id, family_id)（#911 M3）。
        # 历史实现还按 (symbol, account_name) 二次匹配，与 ledger 键可能指向不同记录，
        # 存在「同一标的建出重复持仓」隐患；且标准化后 search_symbol 恒等于 symbol，该分支为死代码。
        ledger_id = data.get('ledger_id')
        family_id = _resolve_family_id(data)
        same = _find_existing_position(db, ledger_id=ledger_id, family_id=family_id, symbol=search_symbol, venue=venue)
        final_symbol = search_symbol

        # ── 计价模式（#1174 / 决策 D2）──
        # nav：份额 × 净值（要求 quantity + avg_price）；balance：直接余额（只要求 amount）。
        # 用显式模式分支，而不是靠「有没有传净值」隐式推断。
        mode = data.get('valuation_mode') or ValuationMode.NAV.value
        is_balance = mode == ValuationMode.BALANCE.value
        amount = data.get('amount', 0) or 0

        # 校验数量/价格
        qty = data.get('quantity', 0) or 0
        price = data.get('avg_price', 0) or 0
        # #1233 货基/逆回购手动建仓：净值恒为 1.0，缺失时兜底，
        # 避免净值接口不可用时用户无法记货基（买入金额 + 份额已足以建仓）。
        if force_create_position and asset_type in ('money_fund', 'reverse_repo') and not is_balance and price <= 0:
            price = 1.0
            data['avg_price'] = 1.0

        # ── 净值缺失先记账（nav_pending）──
        # 当日净值未发布 / 前后端拉取失败时，不把用户挡在记账之外：
        # - 库内已有 nav_date 当日官方净值（提交前恰好发布）→ 直接用官方值，一次到位不标 pending；
        # - 否则用 ≤ nav_date 的最近净值占位（新发基金无历史 → 1.0），份额按 (买入金额−手续费)/占位价
        #   暂算，流水标 entry_status='pending_nav'，nav_backfill job 在官方净值落库后重算份额/成本
        #   （份额手动填写时只校正净值与成本，不覆盖份额；编辑手改份额则清标记，手动优先）。
        nav_pending = bool(data.get('nav_pending')) and not is_balance and asset_type in ('fund', 'money_fund', 'etf')
        shares_manual = bool(data.get('shares_manual')) and qty > 0
        nav_date_extra = str(data.get('nav_date') or data.get('trade_date') or '')[:10]
        if nav_pending:
            if asset_type == 'money_fund':
                # 货基净值恒为 1.0（#1233）：不存在"待发布"，直接定值、无需回填
                price = 1.0
                nav_pending = False
            else:
                official = _lookup_unit_nav(db, symbol, data.get('nav_date') or data.get('trade_date'), exact=True)
                if official:
                    price = float(official)
                    nav_pending = False  # 官方值已在库：无需回填，走正常路径
                else:
                    placeholder = _lookup_unit_nav(
                        db, symbol, data.get('nav_date') or data.get('trade_date'), exact=False
                    )
                    price = float(placeholder) if placeholder else 1.0
            data['avg_price'] = price
            if not shares_manual or qty <= 0:
                net_yuan = float(amount or 0) - float(data.get('fee', 0) or 0)
                if net_yuan <= 0:
                    raise ValueError('买入金额需大于手续费，净值缺失时才能暂算份额')
                qty = round(net_yuan / price, 4)
                data['quantity'] = qty

        if is_balance:
            # balance 模式没有份额/净值概念，只校验金额——市值即由金额累加而来
            if amount <= 0:
                raise ValueError('balance 模式必须提供大于 0 的金额（amount）')
        else:
            if qty <= 0:
                raise ValueError('数量必须大于 0')
            if price <= 0:
                raise ValueError('价格必须大于 0')

            # lot check：买入仅校验本次数量合法（起买单位/步长），与当前持有量无关。
            # #541 豁免：配股缴款不是**申报**买入，数量由配股比例算出（11 股这种非整手
            # 结果完全正常），拿「一手起买」去卡它会把真实配股判成非法交易。
            if data.get('skip_lot_check'):
                pass
            else:
                valid, err_msg = validate_buy(symbol, data.get('market', ''), asset_type, qty)
                if not valid:
                    raise ValueError(err_msg)

            if price <= 0:
                raise SBException(
                    code=ErrorCode.INVALID_PARAMS.code,
                    message=ErrorCode.INVALID_PARAMS.msg,
                    status_code=400,
                    detail={'field': 'avg_price', 'value': price},
                )

        # 转换为内部存储单位（balance 模式份额/价格恒为 0，金额单独转分）
        qty_units = 0 if is_balance else Money.shares_to_min_unit(qty)
        price_units = 0 if is_balance else Money.yuan_to_price_units(price)
        amount_cents = Money.yuan_to_cents(amount) if is_balance else 0

        # 锚点判定必须在合并**之前**：确认日决定这笔流水是否已被快照包含。
        # 提前算一次并复用到下方创建流水，避免「合并处用一套日期、流水用另一套」。
        effective_confirm_date = _resolve_confirm_date(data, asset_type)

        # 清仓后再次买入（#2343）：同账户同标的受 `uq_positions_ledger_symbol(_norm)`
        # 双唯一约束，「新建一行」物理不可行，只能复用清仓保留的同一行。
        # 复用的核心动作是**重置锚点**为新一轮起点（0 份 / 0 成本额 / 清仓日 / manual），
        # 否则上一轮的成本额残留会把本轮成本派生错（实测 1.60 → 1.4375，虚低 10.2%，
        # 上一轮利润漏进本轮成本，浮盈虚高且用户无从察觉）。
        # 重置后本笔归属日 > 清仓日 → 必然「未被锚点包含」，走下方正常合并逻辑。
        if same is not None and same.ownership_status == OwnershipStatus.CLEARED.value:
            _reactivate_cleared_position(same, effective_confirm_date)
            logger.info(
                '已清仓持仓重新激活（新一轮周期）: position={} symbol={} 新锚点日={}',
                same.id,
                same.symbol,
                same.snapshot_date,
            )

        covered_by_anchor = _is_covered_by_anchor(same, effective_confirm_date)

        try:
            if same:
                # 自愈回填（#2372）：存量持仓行可能因上游漏写快照而 name/account_name
                # 为 NULL（实测基金转换转入腿建的持仓两个快照全空）。按 ID 反查补上，
                # 否则交易列表显示「未知资产/未知账户」、持仓明细退化成 6 位编码。
                # 仅在缺失时写，已有快照不动（快照是展示冗余，ID 才是权威）。
                if not same.name:
                    same.name = _resolve_fund_name_by_code(db, same.symbol)
                if not same.account_name and same.ledger_id:
                    same.account_name = _resolve_ledger_name_by_id(db, same.ledger_id)
                if is_balance:
                    # balance 合并：份额/均价无意义（quantity 恒为 0，直接除会 ZeroDivisionError），
                    # 只累加可写市值并刷新覆写时间
                    same.market_value_override = (same.market_value_override or 0) + amount_cents
                    same.value_override_at = datetime.now()
                elif covered_by_anchor:
                    # 这笔交易已包含在快照里（confirm_date <= 锚点日）：**只写流水，不动份额**。
                    # 快照本身已经反映了它，再加一次就是本次修复要解决的重复累加。
                    # 不更新 import_hash：持仓的「最后写入」仍是那张快照，锚点溯源不能被
                    # 一条历史流水改写成交易日期。
                    logger.debug(
                        '交易已含在快照锚点内，仅落流水: position={} symbol={} confirm={} anchor={}',
                        same.id,
                        final_symbol,
                        effective_confirm_date,
                        same.snapshot_date,
                    )
                else:
                    # 合并持仓
                    total_qty_units = same.quantity + qty_units
                    old_cost = Money.multiply_price_quantity(same.avg_price, same.quantity)
                    new_cost = old_cost + Money.multiply_price_quantity(price_units, qty_units)
                    # 用 Decimal 计算均价以避免精度损失
                    total_qty = Money.min_unit_to_shares(total_qty_units)
                    total_cost = Money.cents_to_yuan(old_cost) + Money.cents_to_yuan(
                        Money.multiply_price_quantity(price_units, qty_units)
                    )
                    new_avg_price = Money.yuan_to_price_units(round(total_cost / total_qty, 4))
                    same.avg_price = new_avg_price
                    same.quantity = total_qty_units
                # issue #928: 合并时同步溯源字段（交割单覆盖手动录），并刷新 import_hash
                if 'source' in data:
                    same.source = data['source']
                if 'source_broker' in data:
                    same.source_broker = data['source_broker']
                if not covered_by_anchor:
                    raw_snap = data.get('confirm_date') or date.today()
                    snap = raw_snap if isinstance(raw_snap, date) else datetime.fromisoformat(raw_snap).date()
                    same.import_hash = compute_position_hash(
                        source=same.source, ledger_id=ledger_id, symbol=final_symbol, snapshot_date=snap
                    )
                db.flush()
                position = same
                is_new = False
            else:
                # 新建持仓
                position_data = {k: v for k, v in data.items() if k in _ALLOWED_POSITION_FIELDS}
                position_data['asset_type'] = asset_type
                position_data['avg_price'] = price_units
                position_data['quantity'] = qty_units
                position_data['current_price'] = price_units
                position_data['symbol'] = final_symbol
                position_data['ledger_id'] = ledger_id
                position_data['family_id'] = family_id
                # 快照回填（#2372）：调用方（如基金转换转入腿）只传 ledger_id 不传
                # 名称时，按 ID 反查补 name/account_name——它们是展示快照不是查询键，
                # 但空快照会让交易列表出「未知资产/未知账户」、持仓明细只剩 6 位编码。
                if not position_data.get('name'):
                    position_data['name'] = _resolve_fund_name_by_code(db, final_symbol)
                if not position_data.get('account_name'):
                    position_data['account_name'] = _resolve_ledger_name_by_id(db, ledger_id)
                # #1174 双态计价：显式落计价模式；balance 模式把金额直接写成可写市值
                position_data['valuation_mode'] = mode
                if is_balance:
                    position_data['market_value_override'] = amount_cents
                    position_data['value_override_at'] = datetime.now()
                # issue #928: 生成持仓去重哈希（source|ledger_id|symbol|snapshot_date）
                src = data.get('source', PositionSource.MANUAL.value)
                # 快照日：优先 confirm_date；缺失降级为落库当日（规范 §3.3，保证同日同产品汇总一条）
                raw_snap = data.get('confirm_date') or date.today()
                snapshot_date = raw_snap
                if isinstance(raw_snap, str):
                    snapshot_date = datetime.fromisoformat(raw_snap).date()
                position_data['source'] = src
                position_data['import_hash'] = compute_position_hash(
                    source=src, ledger_id=ledger_id, symbol=final_symbol, snapshot_date=snapshot_date
                )
                try:
                    position = Position(**position_data)
                    db.add(position)
                    db.flush()
                except IntegrityError:
                    # 撞 uq_positions_import_hash：同内容持仓已存在（如手动录后又交割单导入），
                    # 转 upsert 语义——合并数量/成本，溯源跟随末次写入（交割单优先级高于手动录）。
                    db.rollback()
                    logger.info('持仓 import_hash 撞 key，转 upsert 更新既有记录')
                    existing = db.query(Position).filter(Position.import_hash == position_data['import_hash']).first()
                    if existing is None:
                        raise
                    if is_balance:
                        # 同 B1：balance 模式只累加可写市值，不碰份额/均价
                        existing.market_value_override = (existing.market_value_override or 0) + amount_cents
                        existing.value_override_at = datetime.now()
                    elif covered_by_anchor or _is_covered_by_anchor(existing, effective_confirm_date):
                        # 撞 key 撞到的持仓若已有锚点、且本笔已被快照包含 → 同样只写流水。
                        # 这里必须再判一次：`existing` 是撞 key 后**重新查出**的行，可能
                        # 不是入口处的 `same`（two rows same import_hash 的历史数据）。
                        logger.debug(
                            '撞 key 转 upsert：交易已含在锚点内，仅落流水: position={} symbol={}',
                            existing.id,
                            final_symbol,
                        )
                    else:
                        total_qty_units = existing.quantity + qty_units
                        old_cost = Money.multiply_price_quantity(existing.avg_price, existing.quantity)
                        new_cost = old_cost + Money.multiply_price_quantity(price_units, qty_units)
                        total_qty = Money.min_unit_to_shares(total_qty_units)
                        existing.avg_price = Money.yuan_to_price_units(
                            round(
                                (
                                    Money.cents_to_yuan(old_cost)
                                    + Money.cents_to_yuan(Money.multiply_price_quantity(price_units, qty_units))
                                )
                                / total_qty,
                                4,
                            )
                        )
                        existing.quantity = total_qty_units
                    # 溯源字段跟随末次导入来源（交割单覆盖手动录）
                    existing.source = src
                    existing.source_broker = data.get('source_broker')
                    db.flush()
                    position = existing
                is_new = True

            # #863 口径 A + #1657 修复：写路径货基冗余判定 + 互斥挂回（孤儿流水并入持仓表达，
            # 使同 (ledger, symbol) 资金只以持仓市值计入总资产，不双计、不漏计）。
            # 无论 is_money_fund 判定如何都尝试挂回（幂等），避免判定不一致时漏挂回。
            position.is_money_fund = _resolve_money_fund_flag(symbol, asset_type, data.get('is_money_fund'))
            db.flush()  # 确保新建持仓已落库拿到 id，避免挂回孤儿流水时 position_id 为 None
            _reattach_orphan_flows(db, ledger_id, symbol, position.id, family_id)

            # 创建交易流水
            txn_type = op_type if op_type in ('buy', 'deposit') else 'buy'
            notes = data.get('notes') or _get_default_notes(op_type, is_new)

            # 复用入口处已算好的确认日（与锚点判定同一口径，不重算第二遍）
            confirm_date = effective_confirm_date

            TransactionService.create(
                db=db,
                position_id=position.id,
                txn_type=txn_type,
                symbol=symbol,
                trade_date=data.get('trade_date'),
                confirm_date=confirm_date,
                asset_type=_get_asset_type(data),
                link_group_id=data.get('link_group_id'),
                quantity=qty_units,
                price=price_units,
                fee=Money.yuan_to_cents(data.get('fee', 0) or 0),
                # #2137 费用拆分：data 带明细才落四列，否则四列留 NULL（未拆分）
                **_fee_breakdown_kwargs(data),
                # balance 模式没有 price×qty 可算，流水金额直接取用户录入的金额
                amount=amount_cents if is_balance else Money.multiply_price_quantity(price_units, qty_units),
                status='success',
                # #2372：快照缺失时按 ID 兜底反查（position 行刚回填也可能失败，
                # 如 market 名录缺该代码）——绝不留 NULL 让前端显示「未知资产/未知账户」。
                # `or` 短路：快照已在时零额外查询。
                position_name=position.name or _resolve_fund_name_by_code(db, symbol),
                account_name=position.account_name or _resolve_ledger_name_by_id(db, ledger_id),
                notes=notes,
                ledger_id=ledger_id,
                import_hash=data.get('import_hash'),
                family_id=family_id,
                # #1232 决策 11：流水来源与持仓同源（记一笔默认 manual，交易导入/对账补录按 data.source）
                source=data.get('source') or PositionSource.MANUAL.value,
                # 净值缺失先记账：pending 标记 + 元数据（nav_date/shares_manual）供 nav_backfill 消费；
                # 非 pending 场景透传调用方 extra（如基金转换的 extra.conversion，§3.2）
                entry_status='pending_nav' if nav_pending else None,
                extra=(
                    json.dumps(
                        {'nav_pending': True, 'nav_date': nav_date_extra, 'shares_manual': shares_manual},
                        ensure_ascii=False,
                    )
                    if nav_pending
                    else data.get('extra')
                ),
            )

            db.flush()
            db.refresh(position)
            try:
                async_backfill.trigger_backfill(asset_type, symbol)
            except Exception:
                pass
            # #1458 后续：买入即入自选（静默，失败不影响主链路）
            _silent_ensure_watchlist(db, _resolve_family_id(data), symbol)
            return position

        except Exception:
            logger.exception('买入/存入操作失败')
            raise

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
        covered_by_anchor = _is_covered_by_anchor(existing, data.get('confirm_date'))

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
                    _mark_position_cleared(existing, data.get('confirm_date') or data.get('trade_date'))
            else:
                logger.debug(
                    '卖出已含在快照锚点内，仅落流水: position={} symbol={} confirm={} anchor={}',
                    existing.id,
                    existing.symbol,
                    data.get('confirm_date'),
                    existing.snapshot_date,
                )
            db.flush()

            TransactionService.create(
                db=db,
                position_id=position_id,
                symbol=data.get('symbol'),
                txn_type=op_type,
                trade_date=data.get('trade_date'),
                confirm_date=data.get('confirm_date'),
                asset_type=_get_asset_type(data),
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
            if auto_purchase and _get_asset_type(data) not in ('money_fund', 'reverse_repo'):
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

        **净份额归零不再删行**（#2343 第二步，2026-10-18）：改为 `_mark_position_cleared`
        （`quantity=0` + `ownership_status='cleared'` + `cleared_at`），锚点原样留存。
        反向对称：`cleared` 行派生出正份额（典型：删除了那笔清仓卖出流水）时自动
        重新激活回 `active`——持仓「复活」，锚点与流水全程无断链。
        例外：`not txns and not has_anchor` 的空壳行仍删行——那不是清仓历史，
        是无任何数据支撑的孤儿行，标记成 cleared 反而会伪造一段「曾持有」。
        """
        txns = (
            db.query(Transaction)
            .filter(Transaction.position_id == position_id)
            .order_by(Transaction.trade_date, Transaction.id)
            .all()
        )
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
            net_qty, avg_price_units = _derive_state_from_txns(txns, 0, 0)

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
                _mark_position_cleared(pos)
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
                symbol=data.get('symbol'),
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
        """
        处理卖出/取出记录，优先尝试关联持仓；找不到持仓则创建孤立流水。
        """
        asset_type = _get_asset_type(data)
        if asset_type in ('money_fund', 'reverse_repo'):
            _create_cash_transfer_transaction(db, data, 'sell')
            return None

        symbol = data.get('symbol', '')
        qty = data.get('quantity', 0)
        price = data.get('avg_price', 0)
        name = (data.get('name') or data.get('position_name') or '').strip()

        # 尝试查找现有持仓（家庭维度）——身份键 (ledger_id, symbol)，无代码时才按
        # (ledger_id, name) 兜底（#1920 + #2372：账户 ID 收敛范围，名称不做跨账户键）
        existing = None
        if symbol:
            existing = _find_position_by_identity(db, data, symbol=symbol)
        if existing is None and name:
            # **symbol 缺失时的兜底关联**（#1920）
            # 券商交割单里「证券名称」常有而「证券代码」为空（实测真实库 1348/2051 笔
            # 无 symbol）。此前只按 symbol 匹配 ⇒ 必然查不到持仓 ⇒ 卖出退化成孤儿流水
            # ⇒ `realized_pnl` 无从计算而**静默丢 0**（真实库 649 笔卖出如此）。
            # 名称 + 账户 ID 在单个账户内足以唯一定位持仓，退化风险远低于丢成本基准。
            existing = _find_position_by_identity(db, data, name=name, active_only=True)
            if existing is not None:
                logger.info(
                    '卖出/取出按名称兜底关联到持仓：symbol=%r name=%r ledger_id=%r → position_id=%s',
                    symbol,
                    name,
                    data.get('ledger_id'),
                    existing.id,
                )

        if existing:
            try:
                return PositionService.process_sell_or_withdraw(
                    db,
                    {
                        'position_id': existing.id,
                        'quantity': qty,
                        'avg_price': price,
                        'trade_date': data.get('trade_date'),
                        'confirm_date': data.get('confirm_date'),
                        'op_type': data.get('op_type', 'sell'),
                        'fee': data.get('fee', 0.0),
                        'notes': data.get('notes', ''),
                        'import_hash': data.get('import_hash'),
                        'family_id': _resolve_family_id(data),
                    },
                    skip_lot_check=True,
                )
            except ValueError as e:
                if '持仓数量不足' not in str(e):
                    raise
                logger.warning(f'持仓 {existing.symbol} 数量不足，转为孤儿交易')

        # 无持仓或数量不足，统一创建孤儿流水
        _create_orphan_transaction(
            db,
            data,
            txn_type=data.get('op_type', 'sell'),
            quantity=qty,
            price=price,
            amount=0,  # 自动计算
            notes=data.get('notes') or ('卖出' if data.get('op_type') == 'sell' else '取出'),
        )
        return None

    @staticmethod
    def process_orphan_dividend(db: Session, data: dict) -> Optional[Position]:
        """
        处理分红记录，优先尝试关联持仓；找不到持仓则创建孤立流水。

        红利再投资（dividend_reinvest）走单独分支——分红入账 ＋ 按净值申购，
        使持仓份额真正增加；此前它与现金分红合并进同一分支，份额恒为 0，语义丢失。
        数据不全（缺份额或净值）时降级为现金分红，不阻断整批导入。
        """
        symbol = data.get('symbol', '')
        dividend_amount = data.get('dividend_amount', data.get('avg_price', 0))
        is_reinvest = _is_reinvest(data)

        # #2372：按身份键 (ledger_id, symbol) 匹配，不再拿可编辑的 account_name 跨账户猜
        existing = _find_position_by_identity(db, data, symbol=symbol)

        common = {
            'dividend_amount': dividend_amount,
            'confirm_date': data.get('confirm_date'),
            'trade_date': data.get('trade_date'),
            'notes': data.get('notes', ''),
            'import_hash': data.get('import_hash'),
            'link_group_id': data.get('link_group_id'),
            'family_id': _resolve_family_id(data),
        }

        if existing:
            if is_reinvest:
                return PositionService.process_orphan_dividend_reinvest(db, data)
            return PositionService.process_dividend(db, {**common, 'position_id': existing.id})
        else:
            _create_orphan_transaction(
                db,
                data,
                txn_type='dividend',
                quantity=0,
                price=0,
                amount=dividend_amount,
                notes=data.get('notes') or ('红利再投资（待关联持仓）' if is_reinvest else '现金分红'),
            )
            return None

    @staticmethod
    def process_orphan_dividend_reinvest(db: Session, data: dict) -> Optional[Position]:
        """导入路径：红利再投资，优先关联既有持仓；找不到持仓或缺少份额则降级。

        - 有持仓且具备再投份额：分红现金 + 按净值申购双流水（_reinvest_dual_flow）。
        - 有持仓但缺份额：降级为现金分红（单笔），不阻断整批导入。
        - 无关联持仓：记孤儿现金分红流水（notes 标明红利再投资），返回 None。
        """
        family_id = _resolve_family_id(data)
        symbol = data.get('symbol', '')
        # #2372：按身份键 (ledger_id, symbol) 匹配，不再拿可编辑的 account_name 跨账户猜
        existing = _find_position_by_identity(db, data, symbol=symbol)
        link_group_id = data.get('link_group_id') or uuid.uuid4().hex
        if not existing:
            # 无关联持仓：红利再投资无法落地，记孤儿现金分红流水（notes 标明）
            _create_dividend_cash_txn(db, data, None, link_group_id)
            return None
        if not _is_reinvest(data):
            # 缺份额：降级为现金分红，份额不变，不阻断整批导入
            _create_dividend_cash_txn(db, data, existing, link_group_id, entry_status='success')
            return existing
        _reinvest_dual_flow(db, data, existing, link_group_id)
        return existing

    @staticmethod
    def process_orphan_split(db: Session, data: dict) -> Optional[Position]:
        """送股/拆分：优先关联既有持仓并把份额计入；找不到持仓或缺少份额则记孤儿流水。

        送股/拆分本质是「零成本的份额增加」：持仓份额 +quantity、总成本不变，均价由
        recompute_position_from_transactions 自动稀释（与买入/卖出回滚同一口径，避免再添分支）。
        手动记账传 position_id 直接定位；导入路径按身份键 (ledger_id, symbol) 匹配
        （#2372：不再按可编辑的 account_name 跨账户匹配）。
        """
        family_id = _resolve_family_id(data)
        qty = data.get('quantity') or 0

        if qty <= 0:
            # 缺份额：无法计入，记孤儿流水（notes 标明），不阻断整批导入
            _create_orphan_transaction(
                db,
                data,
                txn_type='split',
                quantity=0,
                price=0,
                amount=0,
                notes=data.get('notes') or '送股/拆分（缺份额，需手动关联持仓）',
            )
            return None

        qty_units = Money.shares_to_min_unit(qty)
        position_id = data.get('position_id')
        if position_id:
            existing = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
        else:
            # #2372：身份键 (ledger_id, symbol)；ledger_id 为空时只匹配未归档持仓
            existing = _find_position_by_identity(db, data, symbol=data.get('symbol', ''))

        if not existing:
            # 无关联持仓：送股/拆分无法落地，记孤儿流水（notes 标明），返回 None
            _create_orphan_transaction(
                db,
                data,
                txn_type='split',
                quantity=qty,
                price=0,
                amount=0,
                notes=data.get('notes') or '送股/拆分入账（需手动关联持仓）',
            )
            return None

        # 有关联持仓：记成功流水 + 重算份额（split 作为零成本份额增加，均价自动稀释）
        TransactionService.create(
            db=db,
            position_id=existing.id,
            symbol=data.get('symbol'),
            txn_type='split',
            trade_date=data.get('trade_date'),
            confirm_date=data.get('confirm_date'),
            asset_type=_get_asset_type(data),
            quantity=qty_units,
            price=0,
            fee=Money.yuan_to_cents(data.get('fee', 0) or 0),
            amount=0,
            status='success',
            entry_status='success',
            # #2372：快照缺失时按 ID 兜底反查，不留 NULL 前端显示「未知资产/未知账户」
            position_name=existing.name or _resolve_fund_name_by_code(db, existing.symbol),
            ledger_id=existing.ledger_id,
            account_name=(
                existing.account_name
                or _resolve_ledger_name_by_id(db, existing.ledger_id)
                or data.get('account_name', '')
            ),
            notes=data.get('notes') or '送股/拆分入账',
            import_hash=data.get('import_hash'),
            link_group_id=data.get('link_group_id'),
            family_id=family_id,
            # #1232 决策 11：流水来源透传（记一笔默认 manual）
            source=data.get('source') or PositionSource.MANUAL.value,
        )
        db.flush()
        return PositionService.recompute_position_from_transactions(db, existing.id)

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
    ) -> dict:
        """list_positions 的核心：过滤 + 按账户分组 / 分页组装（#1642 B 块，从 views 下沉）。

        与下沉前逐字段一致：``ledger_id='null'`` 仅取未归档持仓；``group_by='account'`` 按
        **ledger_id** 分组（#2372：可编辑的 account_name 不做分组键；None 归 'unfiled'）并补
        首次买入确认日（优先交易流水，回退 position.confirm_date）；否则分页
        + enrich_position_dict。返回原 jsonify 的「内层 data 字典」（视图负责补 message）。

        ``symbol`` / ``market``（#1966）：产品维度过滤，供详情页「我的持仓」区块用。
        **下推到 SQL**——取全表后内存筛违反数据策略硬约束 §6。
        """
        query = db.query(Position).filter(Position.family_id == family_id)
        # 已清仓行保留在表里（锚点/成本基线不灭），但不属于「当前持仓」视图。
        # 库里还没有 cleared 行时这是恒等变换，见 services/position_scope.py。
        query = exclude_cleared(query)
        # 未归档过滤：ledger_id 显式传 'null' 时仅返回未绑定账户的持仓
        if ledger_id_raw == 'null':
            query = query.filter(Position.ledger_id.is_(None))
        elif ledger_id_raw:
            query = query.filter(Position.ledger_id == int(ledger_id_raw))
        if symbol:
            # symbol 同时匹配「展示形态」与 #1662 的「归一身份键」，取并集：存量行
            # symbol_norm 可能为空、只有新写入行保证有值，只用其一都会漏命中。
            # 判定收口在 `services/symbol_scope.py`（三种 venue 归一候选的详细理由见其模块注释），
            # 与产品级 XIRR（#1972 `scope=symbol`）**共用同一份口径**——两边各写一份，
            # 迟早漂移成「列表里有三行、年化只算了两行」的自相矛盾详情页。
            query = query.filter(or_(*build_position_symbol_conditions(symbol)))
        if market:
            query = query.filter(Position.market == market)
        query = query.order_by(Position.updated_at.desc())

        if group_by == 'account':
            positions = query.all()
            result: dict = {}

            # 一次性查询所有持仓的首次买入确认日（性能优化）
            pos_ids = [p.id for p in positions]
            first_buy_dates: dict = {}
            if pos_ids:
                buy_dates_query = (
                    db.query(Transaction.position_id, func.min(Transaction.confirm_date).label('confirm_date'))
                    .filter(
                        Transaction.position_id.in_(pos_ids),
                        Transaction.txn_type.in_(['buy', 'deposit']),
                    )
                    .group_by(Transaction.position_id)
                    .all()
                )
                first_buy_dates = {row.position_id: row.confirm_date for row in buy_dates_query}

            for p in positions:
                # #2372：分组键用 ledger_id（真外键）而非 account_name（可编辑快照）——
                # 重名账户按名称会并成一组（真库：支付宝×2 / 天天基金×2），账户改名后
                # 前端按名回查整组落空。None（未归档持仓）归哨兵键 'unfiled'。
                # 行内仍带 ledger_id + account_name 快照供展示，键才是关联依据。
                #
                # 与 #2404 的 `p.account_name or '未指定账户'` 兜底同源同目的（避开
                # jsonify sort_keys 对 None 键的 TypeError），但用哨兵键把它**结构性
                # 消除**：None 根本不会成为键，无需靠文案兜底；且键与账户一一对应，
                # 不再受改名 / 重名影响——故保留本实现，移除 #2404 兜底。
                key = str(p.ledger_id) if p.ledger_id is not None else 'unfiled'
                if key not in result:
                    result[key] = []

                # 获取首次买入确认日
                buy_confirm = first_buy_dates.get(p.id)
                if buy_confirm is None:
                    buy_confirm = p.confirm_date  # 兼容无交易记录的回退

                result[key].append(
                    {
                        'id': p.id,
                        'symbol': p.symbol,
                        'name': p.name,
                        'type': p.asset_type,
                        'type_label': TYPE_LABELS.get(p.asset_type, p.asset_type),
                        'market': p.market,
                        'market_label': MARKET_LABELS.get(p.market, p.market),
                        'allocation': p.allocation,
                        'allocation_label': ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类'),
                        'quantity': Money.min_unit_to_shares(p.quantity),
                        'avg_price': Money.price_units_to_yuan(p.avg_price),
                        'currency': p.currency,
                        'current_price': Money.price_units_to_yuan(p.current_price),
                        'confirm_date': buy_confirm.isoformat() if buy_confirm else None,
                        'ledger_id': p.ledger_id,
                        'account_name': p.account_name,
                    }
                )
            return {'data': result}

        # 分页模式保持不变
        items, total = paginate(query, page=page, per_page=per_page)
        data = [enrich_position_dict(p) for p in items]
        return {'data': data, 'total': total, 'page': page, 'per_page': per_page}

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
