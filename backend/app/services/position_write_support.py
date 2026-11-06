# -*- coding: utf-8 -*-
"""持仓**写侧共用原语**（#2873 第二抽）。

`position_service.py` 的 2337 行里，有一簇函数既不是买/卖命令、也不属于读展示，
却是几乎每条写路径都要用的判定与解析：

| 原语 | 谁在用 | 为什么独立 |
|---|---|---|
| `_resolve_family_id` | 所有写入 | 归属家庭是**数据隔离边界**，解析规则（显式 > 上下文 > 遗留兜底）值得单独一处 |
| `_fee_breakdown_kwargs` | 买入/卖出/分红/兑付 | 费用四列「全空或齐全」的不变量，与 `Transaction.before_insert` 同口径 |
| `_get_asset_type` | 买入/卖出/孤儿 | 品种以显式入参 > 已知持仓 > 代码前缀为准，错判会**分裂身份键** |
| `_resolve_confirm_date` | 买入 | 场外 T+1 确认日的唯一算法，锚点判定与落库必须同源 |
| `_lookup_unit_nav` | 买入（净值缺失先记账） | 库内净值点查，被 `conversion_service` 复用 |
| `_txn_effective_date` | 锚点派生 | 流水归属日口径 |
| `_find_position_by_identity` | 导入 / 孤儿挂回 | 身份键三级匹配（账户 ID > 未归档 > 名称唯一兜底） |
| `_find_existing_position` | 买入/快照合并 | venue 感知的归一身份查重，写侧唯一入口 |

## 为什么搬而不是重写

**逐字搬迁**。这一簇每条都有真实事故史（#1662 同码两行、#2372 跨账户串账、#1920 无代码
交割单），改写等于重开战场。搬完后 `position_service` 顶部 re-export 同样的名字，
所有调用点与外部 `from app.services.position_service import _lookup_unit_nav` 一行不改。

## 与 `_txn_effective_date` 有关的一处**刻意不一致**（勿"顺手统一"）

`domains/transactions/dates.py` 的有效日表达式是 `COALESCE(trade_date, confirm_date)`
（**交易日优先**，用于列表排序 / 区间筛选 / 展示值）；本模块的流水归属日是
`confirm_date` 优先、`trade_date` 兜底——锚点判定问的是「份额哪天真正变动」，
场外基金 T+1 才登记。两者优先级相反是**设计**，不是笔误：统一任何一边都会让另一侧出错
（排序按确认日会把「未确认」的行堆到当天，锚点按交易日会把 T+1 确认的买入重复计入）。
真要收敛，得先定一个二分口径（例如按品种给不同优先级），那是独立决策，不在本次搬迁范围。
"""

from datetime import date, datetime
from typing import Optional

from flask import has_app_context
from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.constants import OwnershipStatus
from app.core.money import Money
from app.core.symbol_utils import derive_security_type, split_symbol, strip_exchange_prefix
from app.core.utils import get_confirm_date
from app.core.venues import asset_types_of_venue
from app.domains.funds.models import DailyWorth, Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.fund_utils import normalize_fund_code

# 单用户遗留口径：离线脚本（无请求上下文）且入参也没给 family_id 时的唯一退路。
_LEGACY_SINGLE_FAMILY_ID = 1

# #2137 费用拆分数据键（元）→ Transaction 列名（分）。四键全空 = 未拆分。
_FEE_BREAKDOWN_KEYS = ('fee_commission', 'fee_stamp_duty', 'fee_transfer_fee', 'fee_other')
_FEE_BREAKDOWN_COLUMNS = ('commission', 'stamp_duty', 'transfer_fee', 'other_fee')

# 显式声明即视为「具体品种」的白名单：只有落在其中的显式值才优先于代码前缀推断。
_SPECIFIC_ASSET_TYPES = {
    'etf',
    'bond',
    'fund',
    'money_fund',
    'reverse_repo',
    'cash',
    'portfolio',
    'bank_wealth',
}


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


def _get_asset_type(data: dict, default: str = 'stock', *, fallback: Optional[str] = None) -> str:
    """
    录入阶段确定资产类型：显式具体类型 > 代码前缀推断 > ``fallback`` > 默认 stock。

    历史债背景：PositionCreate.asset_type 使用 validation_alias='type'，
    model_dump() 输出的是字段名 `asset_type`，而 importer 路径直接构造 `type` key，
    导致不同调用方传入的 key 不一致。此处收敛读取端，保证流水 asset_type 落库正确。

    分类下沉到录入阶段（#1264 / #1266）：仅当显式类型缺失，或显式为泛化默认 'stock' 时，
    才按代码前缀推断（沪 51/56/58、深 15/16 → ETF；11/12 → 可转债），
    以免把已正确标注为 fund/money_fund 的基金（代码前缀可能与股票/可转债重合）误判成股票。

    ``fallback``（#2773 附带修）：**已知持仓**时的品种来源。卖出/取出等「操作的是既有持仓」
    的路径，请求体可以不带 ``type``（导入器、脚本、老客户端都不带），而默认兜底是
    ``'stock'`` —— 于是场外基金的卖出流水落成 ``asset_type='stock'``，身份键从
    ``OTC:004369`` 变成 ``EXCHANGE:SZ004369``，与买入那条**分裂成两个分组**：
    清仓周期永远闭合不上，卖出被记成「无周期可归集」。品种本来就该以持仓为准，
    请求体只是它的冗余副本，故 ``fallback`` 排在代码前缀推断**之前**。
    """
    explicit = data.get('asset_type') or data.get('type')
    if explicit and explicit in _SPECIFIC_ASSET_TYPES:
        return explicit
    # 已知持仓的品种**优先于**代码前缀推断：`derive_security_type` 在缺少场所信息时
    # 对任何 6 位数字码都返回 'stock'（实测 004369 → stock），而它其实是场外基金。
    # 推导不可信时以持仓为准，请求体里的品种只是持仓的冗余副本。
    if fallback:
        return fallback
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
            is_after15 = data.get('isAfter15', False)
            fund_type = data.get('fund_type', 'domestic')
            confirm_date = get_confirm_date(trade_date, fund_type=fund_type, is_after_15=is_after15)
        except Exception:
            logger.warning('确认日计算失败，使用前端传入值')
    return confirm_date


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


def _txn_effective_date(txn: Transaction):
    """流水的「归属日」：优先 confirm_date，缺失降级 trade_date 的日期部分。

    WHY 需要降级：锚点判定必须给每条流水一个可比较的日期。`confirm_date` 为 NULL 的
    份额类流水（部分导入格式 / 手工补录）若直接跳过，会在锚点重算里**静默丢掉份额**；
    若无条件计入，又会与快照重复。用 trade_date 兜底是两者之间唯一可解释的选择。
    两者都没有 → 返回 None，由调用方决定（当前口径：排除并告警，宁可少算不重复计）。

    与 `domains/transactions/dates.py` 的 `COALESCE(trade_date, confirm_date)` **优先级
    相反**，这是刻意的：排序要的是「用户看到的那一天」，锚点问的是「份额哪天变动」。
    详见模块 docstring 最后一节，勿顺手统一。
    """
    if txn.confirm_date is not None:
        return txn.confirm_date
    if txn.trade_date is not None:
        return txn.trade_date.date() if hasattr(txn.trade_date, 'date') else txn.trade_date
    return None


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
