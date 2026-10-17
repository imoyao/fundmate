# -*- coding: utf-8 -*-
"""基金转换（conversion）试算与落库服务。

设计依据：``docs/working-notes/fund-conversion-design-2026-10-17.md``。
- §4.1 两个端点：``estimate``（只读试算）与 ``submit``（落库），本文件分别是
  ``estimate_conversion`` 与 ``submit_conversion``；
- §4.2 费用算法（唯一实现，禁止前端另算）：赎回费 FIFO 复用
  ``FundService.estimate_redeem_fee``；补差费 = MAX(0, 转入申购费(净额) −
  转出申购费(净额)) × 申购费折扣；净额 = 转出金额 − 赎回费 − 补差费；
- §3.1 一条转换 = 同一 ``link_group_id`` 下的 2~3 条流水（OUT sell / IN buy /
  REFUND），费用只记 OUT 腿，IN 腿金额为净额；
- §3.5 / §4.4：单事务落库、幂等键（组号 + leg 角色派生 import_hash）、
  退款腿显式关闭卖出链路的自动申购（回款不得记两次）。

精度约定（§5.2 / §4.2 注 4）：全部中间值 ``Decimal``；费用到分、份额到 2 位
（用户面）；**入库份额 4 位**——预估份额是系统算值（类比「全部转出」传持仓
精确值），4 位可把「净值 × 份额」与净额的误差压到半分钱以内，避免每笔转换
都漏/涨几分钱；展示仍 2 位。
"""

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import CASH_SYMBOL, PositionSource
from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.core.symbol_utils import strip_exchange_prefix
from app.core.utils import get_confirm_date
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.fund_service import FundService
from app.services.fund_utils import is_money_fund_symbol
from app.services.pnl_service import compute_sell_realized_cents

# 同一 services 层内复用：净值查询是「净值缺失先记账」链路的既定入口，
# 转换试算与它必须同源（同一函数、同一兜底语义），不另写一份查询。
from app.services.position_service import PositionService, _lookup_unit_nav
from app.services.trading import TransactionService

# 申购费折扣缺省值（账户 fee_config 未配置时）：1 折
_DEFAULT_SUBSCRIPTION_DISCOUNT = Decimal('0.1')

# 份额展示/录入精度（§5.2：申购/赎回/转换统一 2 位）
_SHARE_QUANT = Decimal('0.01')
# 份额入库精度（存储 0.0001 不变，§5.2）
_SHARE_STORE_QUANT = Decimal('0.0001')

_CENT_QUANT = Decimal('0.01')
_ZERO = Decimal('0')

_REFUND_MODE_MONEY_FUND = 'money_fund'
_REFUND_MODE_ACCOUNT_CASH = 'account_cash'


class ConversionService:
    """基金转换试算与落库。全部为静态方法，无状态。"""

    # ── 对外：试算（只读） ──────────────────────────

    @staticmethod
    def estimate_conversion(
        db: Session,
        *,
        out_position_id: int,
        in_symbol: str,
        family_id: int,
        ledger_id: Optional[int] = None,
        out_quantity: Optional[float] = None,
        in_amount: Optional[float] = None,
        trade_date: Optional[date] = None,
    ) -> dict:
        """试算一笔基金转换（不落库）。返回结构见设计文档 §4.1（单位：元）。

        业务校验失败抛 ``ValueError``（视图转 400/1001）；费率缺失等**不阻断**
        的信息进 ``warnings``（D9）。
        """
        c = ConversionService._compute_conversion(
            db,
            out_position_id=out_position_id,
            in_symbol=in_symbol,
            family_id=family_id,
            ledger_id=ledger_id,
            out_quantity=out_quantity,
            in_amount=in_amount,
            trade_date=trade_date,
        )
        return {
            'out': {
                'symbol': c['out_symbol'],
                'name': c['out_name'],
                'quantity': float(c['qty']),
                'nav': float(c['out_nav']),
                'amount': float(c['out_amount']),
                'fee': float(c['total_fee']),
                'fee_breakdown': {
                    'redeem': float(c['redeem_fee']),
                    'compensate': float(c['compensate']),
                },
                'realized_pnl_estimate': Money.cents_to_yuan(c['realized_cents']),
            },
            'in': {
                'symbol': c['in_code'],
                'name': c['in_name'],
                'nav': float(c['in_nav']),
                'amount': float(c['in_amount_used']),
                # 展示 2 位（§5.2）；入库为 4 位，见 submit_conversion
                'quantity': float(c['in_quantity'].quantize(_SHARE_QUANT, rounding=ROUND_HALF_UP)),
            },
            'net_amount': float(c['net_amount']),
            'refund': {'amount': float(c['refund_amount']), 'options': c['refund_options']},
            'supplement': {
                'amount': float(c['supplement_amount']),
                'required': c['supplement_amount'] > 0,
            },
            'trade_date': c['trade_date'].isoformat(),
            'warnings': c['warnings'],
        }

    # ── 对外：落库 ──────────────────────────────────

    @staticmethod
    def submit_conversion(
        db: Session,
        *,
        out_position_id: int,
        in_symbol: str,
        idempotency_key: str,
        family_id: int,
        ledger_id: Optional[int] = None,
        out_quantity: Optional[float] = None,
        in_amount: Optional[float] = None,
        refund_mode: Optional[str] = None,
        trade_date: Optional[date] = None,
    ) -> dict:
        """提交一笔基金转换（落库）。

        单事务内依次：OUT 卖出腿（``auto_purchase=False``）→ IN 买入腿 →
        REFUND 退款腿（可选）。任一步失败整体回滚（请求级事务由 ``get_db``
        teardown 统一提交/回滚，§3.5 注 1）。

        幂等：同 ``idempotency_key`` 重复提交时，任一流水的 import_hash 撞唯一
        约束 → IntegrityError 上传导（视图转 409「已记录，请勿重复提交」）。
        """
        # 幂等预检（先于任何持仓查询/校验）：全部转出会删持仓行且 rowid 可能被
        # 复用，不预检会让重试请求拿着已失效的 position_id 走进错位的校验分支。
        dup = db.query(Transaction).filter_by(import_hash=f'{idempotency_key}#conv-out', family_id=family_id).first()
        if dup:
            group_id = dup.link_group_id or str(idempotency_key)
            raise SBException(
                code=ErrorCode.DUPLICATE_ENTRY.code,
                message=f'该笔转换已记录（组 {group_id}），请勿重复提交',
                status_code=409,
                detail={'link_group_id': group_id, 'duplicated': True},
            )

        c = ConversionService._compute_conversion(
            db,
            out_position_id=out_position_id,
            in_symbol=in_symbol,
            family_id=family_id,
            ledger_id=ledger_id,
            out_quantity=out_quantity,
            in_amount=in_amount,
            trade_date=trade_date,
        )
        if c['supplement_amount'] > 0:
            raise ValueError(
                f'转入金额超过可用净额 {float(c["supplement_amount"]):.2f} 元，暂不支持垫资；'
                '请将转入金额改为不超过净额，或单独记一笔充值'
            )
        refund_amount = c['refund_amount']
        mode = (refund_mode or '').strip()
        if refund_amount > 0:
            if mode not in (_REFUND_MODE_MONEY_FUND, _REFUND_MODE_ACCOUNT_CASH):
                raise ValueError('存在退款金额，必须选择退款去向（类现金产品或账户现金）')
            if mode == _REFUND_MODE_MONEY_FUND and not c['linked_money_fund']:
                raise ValueError('该账户未绑定类现金产品，退款只能退回账户现金')

        position: Position = c['position']
        ledger: Ledger = c['ledger']
        trade_d = c['trade_date']
        link_group_id = str(idempotency_key)
        group_no = f'C{trade_d.strftime("%Y%m%d")}{link_group_id[:6].upper()}'
        confirm_d = get_confirm_date(trade_d, fund_type='domestic', is_after_15=False)

        # ── OUT 腿：卖出（显式关闭自动申购，退款由 REFUND 腿显式落账） ──
        # 并发竞态兜底：两个相同幂等键的请求同时穿过预检时，任一流水的 import_hash
        # 撞唯一约束即在此收敛为 409（与预检同一信封），避免冒到全局 500。
        try:
            extra_out = json.dumps(
                {
                    'conversion': {
                        'v': 1,
                        'group_no': group_no,
                        'role': 'out',
                        'status': 'pending',
                        'nav_date': trade_d.isoformat(),
                        'counter_symbol': c['in_code'],
                        'fee_breakdown': {
                            'redeem': float(c['redeem_fee']),
                            'compensate': float(c['compensate']),
                        },
                        'refund_mode': mode or None,
                        'estimated': True,
                    }
                },
                ensure_ascii=False,
            )
            out_data = {
                'position_id': position.id,
                'op_type': 'sell',
                'symbol': position.symbol,
                'asset_type': 'fund',
                'quantity': float(c['qty']),
                'avg_price': float(c['out_nav']),
                'fee': float(c['total_fee']),
                'trade_date': trade_d,
                'confirm_date': confirm_d,
                'link_group_id': link_group_id,
                'import_hash': f'{link_group_id}#conv-out',
                'notes': '基金转换-转出',
                'ledger_id': position.ledger_id,
                'family_id': family_id,
                'extra': extra_out,
                'source': PositionSource.MANUAL.value,
            }
            PositionService.process_sell_or_withdraw(db, out_data, auto_purchase=False)

            # ── IN 腿：买入（份额 4 位入库，保证 净值×份额 ≈ 净额） ──
            extra_in = json.dumps(
                {
                    'conversion': {
                        'v': 1,
                        'group_no': group_no,
                        'role': 'in',
                        'status': 'pending',
                        'nav_date': trade_d.isoformat(),
                        'counter_symbol': c['out_symbol'],
                        'estimated': True,
                    }
                },
                ensure_ascii=False,
            )
            in_data = {
                'symbol': c['in_code'],
                'op_type': 'buy',
                'asset_type': 'fund',
                'quantity': float(c['in_quantity']),
                'avg_price': float(c['in_nav']),
                'fee': 0.0,
                'trade_date': trade_d,
                'confirm_date': confirm_d,
                'link_group_id': link_group_id,
                'import_hash': f'{link_group_id}#conv-in',
                'notes': '基金转换-转入',
                'ledger_id': position.ledger_id,
                'family_id': family_id,
                'venue': 'OTC',
                'extra': extra_in,
                'source': PositionSource.MANUAL.value,
            }
            in_position = PositionService.process_buy_or_deposit(db, in_data, force_create_position=True)

            # ── REFUND 腿（可选）：真实流水，金额唯一真相在流水不在 extra（§3.1） ──
            refund_txn_id = None
            if refund_amount > 0:
                extra_refund = json.dumps(
                    {
                        'conversion': {
                            'v': 1,
                            'group_no': group_no,
                            'role': 'refund',
                            'refund_mode': mode,
                            'estimated': True,
                        }
                    },
                    ensure_ascii=False,
                )
                if mode == _REFUND_MODE_MONEY_FUND:
                    linked: Fund = c['linked_money_fund']
                    txn = TransactionService.create(
                        db=db,
                        position_id=None,
                        symbol=linked.fund_code,
                        txn_type='buy',
                        trade_date=trade_d,
                        confirm_date=confirm_d,
                        asset_type='money_fund',
                        quantity=0,
                        price=0,
                        fee=0,
                        amount=Money.yuan_to_cents(refund_amount),
                        status='success',
                        position_name=linked.name,
                        ledger_id=ledger.id,
                        account_name=ledger.name,
                        notes='基金转换退款-转入类现金产品',
                        link_group_id=link_group_id,
                        import_hash=f'{link_group_id}#conv-refund',
                        entry_status='orphan',
                        extra=extra_refund,
                        family_id=family_id,
                        source=PositionSource.MANUAL.value,
                    )
                else:
                    txn = TransactionService.create(
                        db=db,
                        position_id=None,
                        symbol=CASH_SYMBOL,
                        txn_type='deposit',
                        trade_date=trade_d,
                        confirm_date=confirm_d,
                        asset_type='cash',
                        quantity=0,
                        price=0,
                        fee=0,
                        amount=Money.yuan_to_cents(refund_amount),
                        status='success',
                        position_name='账户现金',
                        ledger_id=ledger.id,
                        account_name=ledger.name,
                        notes='基金转换退款-退回账户现金',
                        link_group_id=link_group_id,
                        import_hash=f'{link_group_id}#conv-refund',
                        entry_status='orphan',
                        extra=extra_refund,
                        family_id=family_id,
                        source=PositionSource.MANUAL.value,
                    )
                db.flush()
                refund_txn_id = txn.id

        except IntegrityError as e:
            logger.warning('转换落库唯一约束冲突（疑似同键并发重复提交）: %s', e)
            raise SBException(
                code=ErrorCode.DUPLICATE_ENTRY.code,
                message='该笔转换已记录，请勿重复提交',
                status_code=409,
                detail={'link_group_id': link_group_id, 'duplicated': True},
            ) from e

        db.flush()
        return {
            'link_group_id': link_group_id,
            'group_no': group_no,
            'status': 'pending',
            'trade_date': trade_d.isoformat(),
            'confirm_date': confirm_d.isoformat(),
            'out': {
                'symbol': c['out_symbol'],
                'name': c['out_name'],
                'quantity': float(c['qty']),
                'nav': float(c['out_nav']),
                'amount': float(c['out_amount']),
                'fee': float(c['total_fee']),
                'fee_breakdown': {
                    'redeem': float(c['redeem_fee']),
                    'compensate': float(c['compensate']),
                },
                'realized_pnl_estimate': Money.cents_to_yuan(c['realized_cents']),
            },
            'in': {
                'symbol': c['in_code'],
                'name': c['in_name'],
                'nav': float(c['in_nav']),
                'amount': float(c['in_amount_used']),
                'quantity': float(c['in_quantity']),
                'position_id': in_position.id if in_position else None,
            },
            'refund': {'amount': float(refund_amount), 'mode': mode or None, 'txn_id': refund_txn_id},
            'warnings': c['warnings'],
        }

    # ── 内部：试算/落库共用的精确计算 ────────────────

    @staticmethod
    def _compute_conversion(
        db: Session,
        *,
        out_position_id: int,
        in_symbol: str,
        family_id: int,
        ledger_id: Optional[int] = None,
        out_quantity: Optional[float] = None,
        in_amount: Optional[float] = None,
        trade_date: Optional[date] = None,
    ) -> dict:
        """校验 + 费用/份额/净额的 Decimal 精确计算（试算与落库的唯一入口）。"""
        warnings: list[str] = []

        # ── 1. 转出持仓与账户校验（§4.4） ──
        position = db.query(Position).filter_by(id=out_position_id, family_id=family_id).first()
        if not position:
            raise ValueError('转出持仓不存在')
        if position.asset_type != 'fund':
            raise ValueError('只有基金持仓可以转换')
        if ledger_id is not None and position.ledger_id != ledger_id:
            raise ValueError('转出持仓不属于所选账户')

        ledger = db.get(Ledger, position.ledger_id) if position.ledger_id else None
        if not ledger:
            raise ValueError('转出持仓所属账户不存在')
        if ledger.ledger_type not in ('fund', 'bank'):
            raise ValueError('只有基金/银行账户可进行转换')

        out_symbol = position.symbol or ''
        available = Decimal(str(Money.min_unit_to_shares(position.quantity)))
        if out_quantity is None or float(out_quantity) <= 0:
            qty = available  # 「全部转出」：传持仓精确值（4 位），不受录入 2 位限制（D8/§5.2）
        else:
            qty = Decimal(str(out_quantity))
            if qty != qty.quantize(_SHARE_QUANT, rounding=ROUND_HALF_UP):
                raise ValueError('转出份额最多 2 位小数；全部转出请留空，将按持仓精确值处理')
        if qty <= 0:
            raise ValueError('转出份额必须大于 0')
        if qty > available:
            raise ValueError(f'转出份额超过可用份额（持有 {float(available)} 份）')

        # ── 2. 转入基金校验（§4.4） ──
        in_code = strip_exchange_prefix(str(in_symbol or '').strip())
        if not in_code:
            raise ValueError('缺少转入基金代码')
        if in_code == strip_exchange_prefix(out_symbol):
            raise ValueError('转入基金不能与转出基金相同')
        in_fund = db.query(Fund).filter(Fund.fund_code == in_code).first()
        if not in_fund:
            raise ValueError('转入基金不存在')
        # 转入不允许货基：货基无申购费率阶梯、转换语义不成立（货基请直接记一笔申购）。
        # 判定走写入链路同款函数（名录优先、代码段兜底），不猜 Fund 行的类型关系。
        if is_money_fund_symbol(in_code):
            raise ValueError('不能转换至货币基金（货币基金请直接记一笔申购）')

        # ── 3. 净值（T 日缺失不给占位价：占位价算出的预估份额会误导用户） ──
        d = trade_date or date.today()
        out_nav_raw = _lookup_unit_nav(db, out_symbol, d, exact=False)
        in_nav_raw = _lookup_unit_nav(db, in_code, d, exact=False)
        if not out_nav_raw:
            raise ValueError(f'转出基金 {out_symbol} 在 {d} 之前无净值，暂无法试算')
        if not in_nav_raw:
            raise ValueError(f'转入基金 {in_code} 在 {d} 之前无净值，暂无法试算')
        out_nav = Money.parse_nav(out_nav_raw)
        in_nav = Money.parse_nav(in_nav_raw)

        # ── 4. 赎回费（FIFO，§4.2 注 1：复用唯一实现） ──
        try:
            redeem_result = FundService.estimate_redeem_fee(
                db=db,
                position_id=position.id,
                sell_date=d,
                sell_shares=float(qty),
                family_id=family_id,
            )
            redeem_fee = Decimal(str(redeem_result['total_fee']))
        except ValueError as e:
            # D9：费率缺失允许提交，但必须显式告警，不静默按 0
            redeem_fee = _ZERO
            warnings.append(f'转出基金赎回费率缺失，赎回费按 0 预估（{e}）')

        # ── 5. 补差费（§4.2 公式） ──
        out_amount = (out_nav * qty).quantize(_CENT_QUANT, rounding=ROUND_HALF_UP)
        net_before_compensate = out_amount - redeem_fee
        if net_before_compensate <= 0:
            raise ValueError('转出金额不足以覆盖赎回费，无法转换')

        discount = ConversionService._subscription_discount(ledger)
        out_rates = FundService.get_fund_fee_rates(db, strip_exchange_prefix(out_symbol)) or {}
        in_rates = FundService.get_fund_fee_rates(db, in_code) or {}
        # 申购费一律以「元」的 Decimal 返回（避免分/元混算——补差费公式要求
        # 两只基金同口径相减后再乘折扣）
        fee_out, _hit_out = ConversionService._purchase_fee_yuan(out_rates.get('purchase') or [], net_before_compensate)
        fee_in, hit_in = ConversionService._purchase_fee_yuan(in_rates.get('purchase') or [], net_before_compensate)
        if hit_in is None:
            warnings.append(f'转入基金 {in_code} 申购费率数据缺失，补差费按 0 预估，请以确认单为准')
        compensate = (max(fee_in - fee_out, _ZERO) * discount).quantize(_CENT_QUANT, rounding=ROUND_HALF_UP)

        total_fee = redeem_fee + compensate
        net_amount = out_amount - total_fee

        # ── 6. 转入金额 / 退款 / 补差（§4.3） ──
        refund_amount = _ZERO
        in_amount_used = net_amount
        supplement_amount = _ZERO
        if in_amount is not None and float(in_amount) > 0:
            requested = Decimal(str(in_amount)).quantize(_CENT_QUANT, rounding=ROUND_HALF_UP)
            if requested > net_amount:
                # D6：v1 不允许垫资——estimate 照常返回差额，submit 拦截
                supplement_amount = requested - net_amount
            elif requested < net_amount:
                refund_amount = net_amount - requested
                in_amount_used = requested
        in_quantity = (in_amount_used / in_nav).quantize(_SHARE_STORE_QUANT, rounding=ROUND_HALF_UP)

        # ── 7. 已实现盈亏预估（与卖出落库同公式，保证试算=落库） ──
        realized_cents = compute_sell_realized_cents(
            price_units=Money.yuan_to_price_units(out_nav),
            avg_price_units=position.avg_price or 0,
            qty_units=Money.shares_to_min_unit(float(qty)),
            fee_cents=Money.yuan_to_cents(total_fee),
        )

        # ── 8. 退款去向选项（D7：优先账户绑定的类现金产品） ──
        linked_money_fund = None
        if ledger.linked_money_fund_id:
            linked_money_fund = db.get(Fund, ledger.linked_money_fund_id)
        refund_options: list[dict] = []
        if linked_money_fund:
            refund_options.append(
                {'type': _REFUND_MODE_MONEY_FUND, 'symbol': linked_money_fund.fund_code, 'name': linked_money_fund.name}
            )
        refund_options.append({'type': _REFUND_MODE_ACCOUNT_CASH, 'symbol': None, 'name': '退回账户现金'})

        return {
            'position': position,
            'ledger': ledger,
            'linked_money_fund': linked_money_fund,
            'out_symbol': out_symbol,
            'out_name': position.name,
            'in_code': in_code,
            'in_name': in_fund.name,
            'trade_date': d,
            'qty': qty,
            'out_nav': out_nav,
            'in_nav': in_nav,
            'out_amount': out_amount,
            'redeem_fee': redeem_fee,
            'compensate': compensate,
            'total_fee': total_fee,
            'net_amount': net_amount,
            'in_amount_used': in_amount_used,
            'in_quantity': in_quantity,
            'refund_amount': refund_amount,
            'supplement_amount': supplement_amount,
            'refund_options': refund_options,
            'realized_cents': realized_cents,
            'warnings': warnings,
        }

    # ── 内部工具 ────────────────────────────────────

    @staticmethod
    def _subscription_discount(ledger: Ledger) -> Decimal:
        """账户申购费折扣（fee_config.subscription_discount，缺省 0.1）。"""
        if not ledger or not ledger.fee_config:
            return _DEFAULT_SUBSCRIPTION_DISCOUNT
        try:
            cfg = json.loads(ledger.fee_config)
            raw = cfg.get('subscription_discount')
            if raw is None:
                return _DEFAULT_SUBSCRIPTION_DISCOUNT
            value = Decimal(str(raw))
            # 折扣须在 (0, 1]：0 或 >1 视为脏配置，回落缺省而不是静默算出 0 费用
            if _ZERO < value <= Decimal('1'):
                return value
        except (ValueError, TypeError, AttributeError):
            pass
        return _DEFAULT_SUBSCRIPTION_DISCOUNT

    @staticmethod
    def _purchase_fee_yuan(tiers: list, amount_yuan: Decimal) -> tuple[Decimal, Optional[str]]:
        """按申购费率阶梯计算申购费（元，Decimal）。

        tiers 来自 ``FundService.get_fund_fee_rates()['purchase']``：
        ``{start_quota, end_quota, rate, fee_amount}``（金额单位为元）。
        命中固定金额档（fee_amount）时返回固定值，否则按比例计算。
        无阶梯数据返回 ``(0, None)``——由调用方记 warning（D9），不静默按 0。
        """
        if not tiers:
            return _ZERO, None
        for tier in tiers:
            start = Decimal(str(tier.get('start_quota') or 0))
            end = tier.get('end_quota')
            if amount_yuan >= start and (end is None or amount_yuan < Decimal(str(end))):
                fixed = tier.get('fee_amount')
                if fixed:
                    return Decimal(str(fixed)), f'固定 {fixed} 元'
                rate = Decimal(str(tier.get('rate') or 0))
                fee = (amount_yuan * rate).quantize(_CENT_QUANT, rounding=ROUND_HALF_UP)
                return fee, f'{rate:.6f}'
        return _ZERO, None
