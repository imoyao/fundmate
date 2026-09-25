# -*- coding: utf-8 -*-
"""账户写入类业务规则服务层（#1642 A 块，承接 #1606 视图层收敛）。

WHY 下沉
    `create_ledger` / `update_ledger` / `update_ledger_transaction` 以及活期+ 换绑、
    改名级联快照刷新等，都是**业务规则 + 校验**，不是 HTTP 编排：账户类型变更约束、
    改名级联刷新下游 ``account_name`` 冗余快照、活期+ 绑定/换绑、费用配置、交易金额重算。
    留在 ``domains/ledgers/views.py`` 里时：① 高风险路径没有服务层单测入口（必须起 HTTP 栈）；
    ② 视图持续变厚。

边界
    - 入参是**已通过归属校验的模型对象**（视图负责 ``get_owned_or_404`` 与 404），
      本层不碰 ``g`` / ``request``，故可被非 HTTP 入口复用；
    - 错误一律抛 :class:`LedgerWriteError`，由视图转成统一信封 + 状态码 + error_code——
      **文案 / 状态码 / error_code 与下沉前逐字一致**（`conventions.md` §2.4 对外契约零变更）；
    - 事务由请求级边界持有（``get_db`` 的 teardown 统一提交/回滚），本层只 ``flush()``，
      异常即整体回滚——天然获得「中途异常 → 完全回滚」语义（D30 第 ⑥ 条）。
"""

import json
from datetime import datetime

from loguru import logger
from sqlalchemy import func

from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.funds.models import Fund, MoneyFundDailyWorth
from app.domains.ledgers.constants import (
    map_channel_category_to_ledger_type,
    map_ledger_type_to_channel_category,
    map_org_type_to_channel_category,
)
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position, SalesInstitution
from app.domains.transactions.models import Transaction
from app.services.fund_service import FundService
from app.services.trading import TransactionService


class LedgerWriteError(Exception):
    """账户写入业务错误：视图据此返回统一信封 + 状态码 + error_code。

    ``error_code`` 为 ``None`` 时，视图用 ``abort(status_code, message)``（与下沉前
    ``abort(400, ...)`` 行为一致，响应体不含 ``error_code``）；否则返回
    ``jsonify({'data': None, 'message': ..., 'error_code': ...}), status_code``。
    """

    def __init__(self, message: str, status_code: int = 400, error_code=None):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)


# 外部基金列表缓存（进程级，基金列表极少变动）：用于「本地库无此货基时」补建 Fund 行
_FUND_NAME_EM_CACHE: dict = {'ts': 0.0, 'data': None}
_FUND_NAME_EM_TTL = 86400


def resolve_money_fund(db, fund_code: str):
    """按代码解析类现金产品（货基）对应的 Fund 行（业务规则，原视图辅助函数下沉）。

    本地缺失时，用 akshare fund_name_em 兜底补建（仅填代码/名称/类型等最小字段），
    使「本地库尚未同步的货基」也能被绑定。补建失败（网络/解析异常）返回 None，
    由调用方回退 400。
    """
    fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
    if fund:
        return fund
    try:
        import time

        cache = _FUND_NAME_EM_CACHE
        now = time.time()
        if cache['data'] is None or now - cache['ts'] > _FUND_NAME_EM_TTL:
            from app.services.adapters.akshare_adapter import AKShareAdapter

            cache['data'] = AKShareAdapter().fetch_fund_list()
            cache['ts'] = now
        for item in cache['data'] or []:
            if item.get('fund_code') == fund_code:
                fund = Fund(
                    fund_code=fund_code,
                    name=item.get('name') or fund_code,
                    fund_type_id=6 if item.get('fund_type') == '货币型' else None,
                )
                db.add(fund)
                db.flush()
                return fund
    except Exception as e:  # 外部失败不阻塞，回退 400
        logger.warning(f'补建货基 Fund 行失败({fund_code}): {e}')
    return None


def check_money_fund_bindable(db, fund: Fund, ledger_type: str) -> str | None:
    """校验基金是否可作为「活期+」绑定标的，并按账户渠道约束可绑范围（业务规则下沉）。

    复用 FundService._judge_money_fund 三态判定（与前端 disabled 策略一致）；
    渠道约束（#1154，方案 B）按账户 ledger_type 约束可绑范围。
    返回 None 表示可绑定；返回字符串为 400 拒绝原因。
    """
    has_worth = (
        db.query(MoneyFundDailyWorth.fund_code).filter(MoneyFundDailyWorth.fund_code == fund.fund_code).first()
        is not None
    )
    is_mf = FundService._judge_money_fund(fund.fund_type_id, fund.name, has_worth)
    if is_mf is False:
        return '活期+ 仅支持货币基金类产品'
    if is_mf is None:
        logger.warning(f'绑定活期+ 的基金类型未知（{fund.fund_code} {fund.name}），按前端策略放行')
    # 渠道约束（#1154，方案 B）：按账户类型约束可绑范围，不加 Fund 字段
    channel = FundService._classify_money_fund_channel(fund.fund_code)
    if channel == 'exchange_traded':
        return '场内货币ETF（如华宝添益/银华日利）属投资范畴，不可绑定活期+'
    if channel == 'broker_channel' and ledger_type != 'stock':
        return '证券账户活期+ 仅支持券商渠道现金管理产品（如银河水星现金添利）'
    if channel == 'off_exchange' and ledger_type != 'fund':
        return '基金平台账户活期+ 仅支持场外货币基金'
    return None


def sync_account_name_snapshots(db, ledger_id: int, account_name: str, family_id: int) -> dict[str, int]:
    """把账户新名称刷到所有下游 account_name 冗余快照（#1354，业务规则下沉）。

    账户改名时只改 ledgers.name 会让明细页、按账户分组的分布图继续显示旧名字；
    此处按 ledger_id 命中范围统一刷新；ledger_id 为空/家庭不符的孤儿数据不处理。

    Returns:
        {表名: 受影响行数}，便于接口回执与测试断言。
    """
    return {
        'assets': db.query(Asset)
        .filter(Asset.ledger_id == ledger_id, Asset.family_id == family_id)
        .update({Asset.account_name: account_name}, synchronize_session=False),
        'positions': db.query(Position)
        .filter(Position.ledger_id == ledger_id, Position.family_id == family_id)
        .update({Position.account_name: account_name}, synchronize_session=False),
        'transactions': db.query(Transaction)
        .filter(Transaction.ledger_id == ledger_id, Transaction.family_id == family_id)
        .update({Transaction.account_name: account_name}, synchronize_session=False),
    }


def swap_linked_money_fund(db, ledger: Ledger, old_fund: Fund, new_fund: Fund, family_id: int) -> None:
    """#1137 换绑活期+：将账户内原绑定货基 A 的净额持仓赎回，并申购新绑定货基 B（业务规则下沉）。

    货基以孤儿流水记账（不建持仓），故「持仓」= 该账户下 A 的 money_fund 流水净额。
    净额<=0 表示无实际持仓，跳过（避免凭空造流水）。仅生成两条孤儿流水（赎回 A /
    申购 B），资产中性、不影响其他账户；失败仅记录告警不抛出，避免阻断换绑主流程。
    """
    family_id = family_id
    # 货基以孤儿流水记账（不建持仓），净额口径与 summary_service.orphan_money_fund_totals_by_ledger
    # 一致：buy/deposit 加、sell/withdraw 减，且仅计 position_id IS NULL 的孤儿流水，全程整数分。
    positive = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.ledger_id == ledger.id,
            Transaction.family_id == family_id,
            Transaction.asset_type == 'money_fund',
            Transaction.symbol == old_fund.fund_code,
            Transaction.position_id.is_(None),
            Transaction.txn_type.in_(('buy', 'deposit')),
        )
        .scalar()
        or 0
    )
    negative = (
        db.query(func.coalesce(func.sum(Transaction.amount), 0))
        .filter(
            Transaction.ledger_id == ledger.id,
            Transaction.family_id == family_id,
            Transaction.asset_type == 'money_fund',
            Transaction.symbol == old_fund.fund_code,
            Transaction.position_id.is_(None),
            Transaction.txn_type.in_(('sell', 'withdraw')),
        )
        .scalar()
        or 0
    )
    net_cents = int(positive) - int(negative)
    if net_cents <= 0:
        return
    today = datetime.now().date()
    # 赎回原绑定货基 A
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=old_fund.fund_code,
        txn_type='sell',
        trade_date=today,
        confirm_date=today,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=net_cents,
        status='success',
        position_name=old_fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='更换活期+，赎回原绑定产品',
        entry_status='orphan',
        family_id=family_id,
    )
    # 申购新绑定货基 B（活期+内迁移，保持资产中性）
    TransactionService.create(
        db=db,
        position_id=None,
        symbol=new_fund.fund_code,
        txn_type='buy',
        trade_date=today,
        confirm_date=today,
        asset_type='money_fund',
        quantity=0,
        price=0,
        fee=0,
        amount=net_cents,
        status='success',
        position_name=new_fund.name,
        ledger_id=ledger.id,
        account_name=ledger.name,
        notes='更换活期+，申购新绑定产品',
        entry_status='orphan',
        family_id=family_id,
    )
    logger.info(
        f'账户 {ledger.id} 换绑活期+：{old_fund.fund_code} → {new_fund.fund_code}，'
        f'净额 {net_cents} 分已迁移（赎回 A / 申购 B）'
    )


def create_ledger(db, family_id: int, data: dict) -> Ledger:
    """创建新账户的业务规则（与下沉前视图层行为逐字一致）。

    ``data`` 为已 json 解析的请求体字典。返回新建的 Ledger 实例（已 flush/refresh）。
    校验失败抛 :class:`LedgerWriteError`（视图转信封）。
    """
    name = (data.get('name') or '').strip()
    if not name:
        # 与下沉前 ``abort(400, '账户名称不能为空')`` 一致（响应体不含 error_code）
        raise LedgerWriteError('账户名称不能为空', 400, None)

    ledger_type = data.get('ledger_type', 'bank')
    channel_category = data.get('channel_category')
    linked_cash_id = data.get('linked_cash_ledger_id')
    sales_institution_id = data.get('sales_institution_id')

    # 校验关联的销售机构（可选）：机构是全局 AMAC 名录，无 family 归属
    institution_org_type = None
    if sales_institution_id is not None:
        institution = db.query(SalesInstitution).filter_by(id=sales_institution_id).first()
        if not institution:
            raise LedgerWriteError('关联的销售机构不存在', 400, 1001)
        institution_org_type = institution.org_type

    # 校验关联的现金账户
    if linked_cash_id is not None:
        if ledger_type not in ('stock', 'fund'):
            raise LedgerWriteError('只有证券账户或基金可以关联现金账户', 400, 1001)
        cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='bank').first()
        if not cash_ledger or cash_ledger.family_id != family_id:
            raise LedgerWriteError('关联的现金账户不存在或类型不是现金账户', 400, 1001)

    # 派生 channel_category / ledger_type（#1101 渠道分类重设计）：
    #   - 显式给了 channel_category → 以它为准，并据其反推 ledger_type（手动账本路径）；
    #   - 否则有销售机构 → 以 org_type 映射为准（权威，覆盖 ledger_type 的展示语义）；
    #   - 否则按 ledger_type 反推 channel_category（向后兼容旧调用方）。
    if channel_category:
        ledger_type = map_channel_category_to_ledger_type(channel_category)
    elif institution_org_type:
        channel_category = map_org_type_to_channel_category(institution_org_type)
    elif ledger_type:
        channel_category = map_ledger_type_to_channel_category(ledger_type)

    # 类现金产品绑定（#1137）：入参用基金代码（前端搜索结果即 code），存储 funds.id。
    # 仅证券/基金平台可绑；开关默认关闭，未绑定时不允许开启。
    linked_money_fund_code = (data.get('linked_money_fund_code') or '').strip() or None
    auto_purchase_money_fund = bool(data.get('auto_purchase_money_fund', False))
    linked_money_fund_id = None
    if linked_money_fund_code:
        if ledger_type not in ('stock', 'fund'):
            raise LedgerWriteError('只有证券账户或基金可以绑定活期+', 400, 1001)
        fund = resolve_money_fund(db, linked_money_fund_code)
        if not fund:
            raise LedgerWriteError('绑定的活期+不存在', 400, 1001)
        reject = check_money_fund_bindable(db, fund, ledger_type)
        if reject:
            raise LedgerWriteError(reject, 400, 1001)
        linked_money_fund_id = fund.id
    elif auto_purchase_money_fund:
        raise LedgerWriteError('请先绑定活期+，再开启自动申购', 400, 1001)

    ledger = Ledger(
        name=name,
        ledger_type=ledger_type,
        channel_category=channel_category,
        default_allocation=data.get('default_allocation', 'longterm'),
        notes=data.get('notes', ''),
        portfolio_id=data.get('portfolio_id'),
        linked_cash_ledger_id=linked_cash_id,
        linked_money_fund_id=linked_money_fund_id,
        auto_purchase_money_fund=auto_purchase_money_fund,
        sales_institution_id=sales_institution_id,
        family_id=family_id,
    )

    # 处理 fee_config JSON 字段
    fee_config = data.get('fee_config')
    if fee_config is not None:
        if isinstance(fee_config, dict):
            ledger.fee_config = json.dumps(fee_config, ensure_ascii=False)
        elif isinstance(fee_config, str):
            ledger.fee_config = fee_config  # 信任前端传的 JSON 字符串
        else:
            # 与下沉前 ``abort(400, 'fee_config 格式无效')`` 一致（响应体不含 error_code）
            raise LedgerWriteError('fee_config 格式无效', 400, None)

    db.add(ledger)
    db.flush()
    db.refresh(ledger)
    return ledger


def update_ledger(db, ledger: Ledger, data: dict, family_id: int) -> Ledger:
    """更新账户信息的业务规则（与下沉前视图层行为逐字一致）。

    入参 ``ledger`` 为已通过归属校验（``get_owned_or_404``）的实例；本层只改字段、
    做校验、触发活期+ 换绑/改名级联快照，并 flush（提交/回滚由请求级边界统一决定）。
    """
    name = data.get('name')
    renamed_to: str | None = None
    if name is not None:
        name = name.strip()
        if not name:
            raise LedgerWriteError('账户名称不能为空', 400, 1001)
        if name != ledger.name:
            renamed_to = name
        ledger.name = name

    ledger_type = data.get('ledger_type')
    if ledger_type is not None and ledger_type != ledger.ledger_type:
        # 类型决定计算口径（费率/税费/分红再投资/XIRR 处理不同），已有数据的账户
        # 禁止改类型，否则历史交易的计算口径会瞬间错乱。空白账户（零交易/零持仓/
        # 零资产）允许改类型。
        has_data = (
            db.query(Transaction).filter(Transaction.ledger_id == ledger.id).count() > 0
            or db.query(Position).filter(Position.ledger_id == ledger.id).count() > 0
            or db.query(
                db.query(Asset).filter(Asset.ledger_id == ledger.id, Asset.family_id == family_id).exists()
            ).scalar()
        )
        if has_data:
            raise LedgerWriteError('账户已有交易/持仓/资产数据，类型不可更改；如需调整请先归档后新建', 409, 1003)
        ledger.ledger_type = ledger_type

    # 归档状态：活跃/归档切换。归档仅隐藏于日常视图，保留全部数据并仍参与收益计算。
    if 'is_active' in data:
        is_active = data['is_active']
        if not isinstance(is_active, bool):
            raise LedgerWriteError('is_active 必须为布尔值', 400, 1001)
        ledger.is_active = is_active

    default_allocation = data.get('default_allocation')
    if default_allocation is not None:
        ledger.default_allocation = default_allocation

    notes = data.get('notes')
    if notes is not None:
        ledger.notes = notes

    # 更新 portfolio_id（允许设置为 None）
    if 'portfolio_id' in data:
        ledger.portfolio_id = data['portfolio_id']

    # 更新 linked_cash_ledger_id（允许设置为 None）
    if 'linked_cash_ledger_id' in data:
        linked_cash_id = data['linked_cash_ledger_id']
        # 如果是设置非空值，必须校验
        if linked_cash_id is not None:
            current_type = ledger_type if ledger_type is not None else ledger.ledger_type
            if current_type not in ('stock', 'fund'):
                raise LedgerWriteError('只有证券账户或基金可以关联现金账户', 400, 1001)
            cash_ledger = db.query(Ledger).filter_by(id=linked_cash_id, ledger_type='bank').first()
            if not cash_ledger or cash_ledger.family_id != family_id:
                raise LedgerWriteError('关联的现金账户不存在或类型不是现金账户', 400, 1001)
        # 无论值是否为 None，均更新
        ledger.linked_cash_ledger_id = linked_cash_id

    # 更新类现金产品绑定（#1137，允许设置为 None 解绑）
    # 入参用基金代码，存储 funds.id；未绑定时不允许开启自动申购。
    if 'linked_money_fund_code' in data:
        fund_code = (data.get('linked_money_fund_code') or '').strip() or None
        old_linked_id = ledger.linked_money_fund_id
        if fund_code is None:
            ledger.linked_money_fund_id = None
            # 解绑时自动关闭开关，避免残留一个无法生效的开关
            ledger.auto_purchase_money_fund = False
        else:
            if ledger.ledger_type not in ('stock', 'fund'):
                raise LedgerWriteError('只有证券账户或基金可以绑定活期+', 400, 1001)
            fund = resolve_money_fund(db, fund_code)
            if not fund:
                raise LedgerWriteError('绑定的活期+不存在', 400, 1001)
            reject = check_money_fund_bindable(db, fund, ledger.ledger_type)
            if reject:
                raise LedgerWriteError(reject, 400, 1001)
            ledger.linked_money_fund_id = fund.id
            # #1137 换绑活期+：原绑定货基仍有净额持仓时，赎回 A 并申购 B（资产中性）。
            # 仅当从 A 换到 B（ID 不同）才触发，首次绑定 / 解绑重绑不触发。
            if old_linked_id and old_linked_id != fund.id:
                old_fund = db.get(Fund, old_linked_id)
                if old_fund:
                    swap_linked_money_fund(db, ledger, old_fund, fund, family_id)

    # 更新自动申购开关（#1137）
    if 'auto_purchase_money_fund' in data:
        auto_purchase = data['auto_purchase_money_fund']
        if not isinstance(auto_purchase, bool):
            raise LedgerWriteError('auto_purchase_money_fund 必须为布尔值', 400, 1001)
        if auto_purchase and not ledger.linked_money_fund_id:
            raise LedgerWriteError('请先绑定活期+，再开启自动申购', 400, 1001)
        ledger.auto_purchase_money_fund = auto_purchase

    # 更新 sales_institution_id（允许设置为 None）
    if 'sales_institution_id' in data:
        sales_institution_id = data['sales_institution_id']
        if sales_institution_id is not None:
            institution = db.query(SalesInstitution).filter_by(id=sales_institution_id).first()
            if not institution:
                raise LedgerWriteError('关联的销售机构不存在', 400, 1001)
        # 无论值是否为 None，均更新
        ledger.sales_institution_id = sales_institution_id

    # 更新 channel_category（用户可见分组/类型标签，#1101 重设计）。
    # 不反向改写 ledger_type（计算口径键）。
    if 'channel_category' in data:
        ledger.channel_category = data['channel_category']

    # 更新 fee_config
    if 'fee_config' in data:
        fee_config = data['fee_config']
        if fee_config is None:
            ledger.fee_config = None
        elif isinstance(fee_config, dict):
            ledger.fee_config = json.dumps(fee_config, ensure_ascii=False)
        elif isinstance(fee_config, str):
            ledger.fee_config = fee_config
        else:
            raise LedgerWriteError('fee_config 格式无效', 400, 1001)

    # #1354：改名后级联刷新下游快照，否则明细页仍显示旧账户名
    if renamed_to:
        sync_account_name_snapshots(db, ledger.id, renamed_to, family_id)

    db.flush()
    db.refresh(ledger)
    return ledger


def update_ledger_transaction(db, ledger, txn, data: dict) -> Transaction:
    """编辑账户内交易（金额/数量/价格/日期/备注，见 issue #1112，业务规则下沉）。

    - 允许修改 quantity/price/amount/fee/trade_date/confirm_date/notes；
    - 归属类字段（ledger_id/symbol/account 等）禁止修改（由视图在调用前拦截）；
    - 修改金额类或日期/备注字段后清空 import_hash：手工编辑已破坏"内容哈希去重"
      不变式，后续重新导入需按新内容重新匹配/对账；
    - 未显式给出 amount 时，按 价格×数量 重算毛额以保持一致。
    返回已 flush 的 txn；响应字典（含 Money 反算）由视图组装，保持展示职责在视图。
    """

    def _non_negative(field, value):
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            raise LedgerWriteError(f'{field} 必须为非负数字', 400, None)
        return value

    touched = False
    recompute_amount = False
    if 'quantity' in data:
        txn.quantity = Money.shares_to_min_unit(_non_negative('quantity', data['quantity']))
        touched = True
        recompute_amount = True
    if 'price' in data:
        txn.price = Money.yuan_to_price_units(_non_negative('price', data['price']))
        touched = True
        recompute_amount = True
    if 'fee' in data:
        txn.fee = Money.yuan_to_cents(_non_negative('fee', data['fee']))
        touched = True
    if 'amount' in data:
        txn.amount = Money.yuan_to_cents(_non_negative('amount', data['amount']))
        touched = True
    elif recompute_amount:
        # 改了价格/数量但未显式给金额时，按 价格×数量 重算毛额，保持一致性
        txn.amount = Money.multiply_price_quantity(txn.price, txn.quantity)

    if 'trade_date' in data and data['trade_date'] is not None:
        try:
            txn.trade_date = datetime.strptime(data['trade_date'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            raise LedgerWriteError('trade_date 格式应为 YYYY-MM-DD', 400, None)
        touched = True
    if 'confirm_date' in data:
        if data['confirm_date'] is None:
            txn.confirm_date = None
        else:
            try:
                txn.confirm_date = datetime.strptime(data['confirm_date'], '%Y-%m-%d').date()
            except (ValueError, TypeError):
                raise LedgerWriteError('confirm_date 格式应为 YYYY-MM-DD', 400, None)
            touched = True
    if 'notes' in data:
        txn.notes = data['notes']
        touched = True

    # 手工编辑破坏内容哈希去重不变式，清空以便重新导入按新内容对账
    if touched and txn.import_hash:
        txn.import_hash = None

    db.flush()
    return txn
