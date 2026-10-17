# -*- coding: utf-8 -*-
"""基金转换（conversion）试算服务。

设计依据：``docs/working-notes/fund-conversion-design-2026-10-17.md``（§4.1 试算端点 /
§4.2 费用算法）。本文件只承载 **P0：只读试算**；落库（P1）与撤销另行追加。

费用口径（与落库同源的唯一实现，禁止前端另算）：

- 赎回费：FIFO 复用 ``FundService.estimate_redeem_fee``（持有天数阶梯）；
- 补差费：``MAX(0, 转入申购费(净额) − 转出申购费(净额)) × 申购费折扣``，
  其中「转出申购费」按**本次转入净额**重新计算，不是用户当初实付费用（§4.2 注 2）；
- 净额 = 转出金额 − 赎回费 − 补差费；全部中间值走 ``Decimal``，费用到分
  （ROUND_HALF_UP），份额到 2 位（§4.2 注 4 / §5.2）。
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.money import Money
from app.core.symbol_utils import strip_exchange_prefix
from app.domains.funds.models import Fund
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.services.fund_service import FundService
from app.services.fund_utils import is_money_fund_symbol
from app.services.pnl_service import compute_sell_realized_cents

# 同一 services 层内复用：净值查询是「净值缺失先记账」链路的既定入口，
# 转换试算与它必须同源（同一函数、同一兜底语义），不另写一份查询。
from app.services.position_service import _lookup_unit_nav

# 申购费折扣缺省值（账户 fee_config 未配置时）：1 折
_DEFAULT_SUBSCRIPTION_DISCOUNT = Decimal('0.1')

# 份额展示/录入精度（§5.2：申购/赎回/转换统一 2 位；存储仍为 0.0001）
_SHARE_QUANT = Decimal('0.01')

_ZERO = Decimal('0')


class ConversionService:
    """基金转换试算。全部为类方法/静态方法，无状态。"""

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
        """试算一笔基金转换（只读，不落库）。

        返回结构见设计文档 §4.1；金额单位为元（float，保留 2 位），净值 4 位，
        预估份额 2 位。业务校验失败抛 ``ValueError``（视图转 400/1001）；
        费率缺失等**不阻断**的信息进 ``warnings``（D9）。
        """
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
        available = Money.min_unit_to_shares(position.quantity)
        qty = available if not out_quantity or out_quantity <= 0 else float(out_quantity)
        if qty <= 0:
            raise ValueError('转出份额必须大于 0')
        if Decimal(str(qty)) > Decimal(str(available)):
            raise ValueError(f'转出份额超过可用份额（持有 {available} 份）')

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
                sell_shares=qty,
                family_id=family_id,
            )
            redeem_fee = Decimal(str(redeem_result['total_fee']))
        except ValueError as e:
            # D9：费率缺失允许提交，但试算必须显式告警，不静默按 0
            redeem_fee = _ZERO
            warnings.append(f'转出基金赎回费率缺失，赎回费按 0 预估（{e}）')

        # ── 5. 补差费（§4.2 公式） ──
        qty_dec = Decimal(str(qty))
        out_amount = (out_nav * qty_dec).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
        net_before_compensate = out_amount - redeem_fee
        if net_before_compensate <= 0:
            raise ValueError('转出金额不足以覆盖赎回费，无法转换')

        discount = ConversionService._subscription_discount(ledger)
        out_rates = FundService.get_fund_fee_rates(db, strip_exchange_prefix(out_symbol)) or {}
        in_rates = FundService.get_fund_fee_rates(db, in_code) or {}
        # 申购费一律以「元」的 Decimal 返回（内部量，避免分/元混算——补差费公式
        # 要求两只基金同口径相减后再乘折扣）
        fee_out, hit_out = ConversionService._purchase_fee_yuan(out_rates.get('purchase') or [], net_before_compensate)
        fee_in, hit_in = ConversionService._purchase_fee_yuan(in_rates.get('purchase') or [], net_before_compensate)
        if hit_in is None:
            warnings.append(f'转入基金 {in_code} 申购费率数据缺失，补差费按 0 预估，请以确认单为准')
        compensate = (max(fee_in - fee_out, _ZERO) * discount).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')

        total_fee = redeem_fee + compensate
        net_amount = out_amount - total_fee

        # ── 6. 转入金额 / 退款 / 补差（§4.3） ──
        refund_amount = _ZERO
        in_amount_used = net_amount
        supplement_required = False
        supplement_amount = _ZERO
        if in_amount is not None and float(in_amount) > 0:
            requested = Decimal(str(in_amount)).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
            if requested > net_amount:
                # D6：v1 不允许垫资——试算照常返回，提交端拦截
                supplement_required = True
                supplement_amount = requested - net_amount
            elif requested < net_amount:
                refund_amount = net_amount - requested
                in_amount_used = requested
        in_quantity = (in_amount_used / in_nav).quantize(_SHARE_QUANT, rounding='ROUND_HALF_UP')

        # ── 7. 已实现盈亏预估（与卖出落库同公式，保证试算=落库） ──
        realized_cents = compute_sell_realized_cents(
            price_units=Money.yuan_to_price_units(out_nav),
            avg_price_units=position.avg_price or 0,
            qty_units=Money.shares_to_min_unit(qty),
            fee_cents=Money.yuan_to_cents(total_fee),
        )

        # ── 8. 退款去向选项（D7：优先账户绑定的类现金产品） ──
        refund_options: list[dict] = []
        if ledger.linked_money_fund_id:
            linked = db.get(Fund, ledger.linked_money_fund_id)
            if linked:
                refund_options.append({'type': 'money_fund', 'symbol': linked.fund_code, 'name': linked.name})
        refund_options.append({'type': 'account_cash', 'symbol': None, 'name': '退回账户现金'})

        return {
            'out': {
                'symbol': out_symbol,
                'name': position.name,
                'quantity': float(qty_dec),
                'nav': float(out_nav),
                'amount': float(out_amount),
                'fee': float(total_fee),
                'fee_breakdown': {
                    'redeem': float(redeem_fee),
                    'compensate': float(compensate),
                },
                'realized_pnl_estimate': Money.cents_to_yuan(realized_cents),
            },
            'in': {
                'symbol': in_code,
                'name': in_fund.name,
                'nav': float(in_nav),
                'amount': float(in_amount_used),
                'quantity': float(in_quantity),
            },
            'net_amount': float(net_amount),
            'refund': {'amount': float(refund_amount), 'options': refund_options},
            'supplement': {'amount': float(supplement_amount), 'required': supplement_required},
            'trade_date': d.isoformat(),
            'warnings': warnings,
        }

    # ── 内部工具 ────────────────────────────────────

    @staticmethod
    def _subscription_discount(ledger: Ledger) -> Decimal:
        """账户申购费折扣（fee_config.subscription_discount，缺省 0.1）。"""
        import json

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
                fee = (amount_yuan * rate).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
                return fee, f'{rate:.6f}'
        return _ZERO, None
