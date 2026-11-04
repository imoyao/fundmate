# -*- coding: utf-8 -*-
"""持仓明细的展示层序列化（唯一出口）。

为什么在 services 而不是 `domains/positions/views.py`（#1607 批次 2）：
- 该函数被 **positions 与 ledgers 两个域**的视图共用，此前 `ledgers/views.py` 直接
  `from app.domains.positions.views import enrich_position_dict`——正是决策中明令禁止的
  「跨域引用对方 views」（域视图互引会把 HTTP 层的路由 / 事务 / 鉴权细节卷进另一域的依赖面）；
- 它自身依赖 services 口径（`position_valuation.market_value_cents`）。按
  `core ← domains.{models,schemas} ← services ← domains.{views}` 的方向，
  「多域共用的展示口径」应落 services，两侧视图各自 import 即可。

不变量：字段与数值口径与迁移前**逐字一致**（`PositionOut` + 三个 label + `Money` 单位换算
+ `market_value` / `pnl` 走唯一市值口径），仅模块位置变化。
"""

from app.core.constants import ALLOCATION_LABELS, MARKET_LABELS, TYPE_LABELS
from app.core.money import Money
from app.domains.positions.models import Position
from app.domains.positions.schemas import PositionOut
from app.services.fund_utils import should_exclude_from_investment
from app.services.pnl_settle import is_settled_today
from app.services.position_valuation import market_value_cents


def enrich_position_dict(p: Position) -> dict:
    """把 `Position` 序列化为接口返回字典（含枚举标签与展示单位换算）。

    #2406：market 空值的兜底**只进返回字典，绝不写回 ORM 对象**。旧实现
    `p.market = 'UNKNOWN'` 改的是持久化实体——同一 session 后续任何一次 flush
    都会把这个展示兜底值落进库（本地库实证 position 618：market 列字面值
    'UNKNOWN'，全库唯一一行），此后 MARKET_LABELS 查不到，前端恒显「未知资产」。
    读函数写库是病根：兜底可以有，但必须死在 dict 层。线上 wire 格式不变
    （`d['market']` 仍为 'UNKNOWN'），故 PositionOut.market 相应放宽为可空，
    由本函数在字典层补齐。
    """
    market = p.market or 'UNKNOWN'
    d = PositionOut.model_validate(p).model_dump()
    if not d.get('market'):
        d['market'] = market
    d['type_label'] = TYPE_LABELS.get(p.asset_type, p.asset_type)
    d['market_label'] = MARKET_LABELS.get(market, market)
    d['allocation_label'] = ALLOCATION_LABELS.get(p.allocation, p.allocation or '未分类')
    # 转换内部单位到展示单位
    d['quantity'] = Money.min_unit_to_shares(p.quantity)
    d['avg_price'] = Money.price_units_to_yuan(p.avg_price)
    d['current_price'] = Money.price_units_to_yuan(p.current_price)
    d['market_value_override'] = (
        Money.cents_to_yuan(p.market_value_override) if p.market_value_override is not None else None
    )
    # 市值/盈亏（#1174 收口）：委托唯一口径 position_valuation.market_value_cents。
    # 本币直算——汇率折算仅存在于 summary 聚合口径（total_*_cny）；单条明细与 current_price 保持本币一致。
    d['market_value'] = Money.cents_to_yuan(market_value_cents(p))
    d['pnl'] = (
        Money.cents_to_yuan(Money.multiply_price_quantity(p.current_price - p.avg_price, p.quantity))
        if p.avg_price
        else 0.0
    )

    # ── 当日盈亏（#2007）──
    # 口径：(现价 − 上一确认价) × 数量。与 `pnl` 同为**浮动**性质（不含已实现），
    # 区别只在窗口是一天。基准价由 `sync/jobs/position_price_job` 与 `current_price`
    # **同批**写入——同源同批这个前提不成立时，相减出来的是两段行情之差、不是当日涨跌，
    # 所以这里只负责算，不负责凑。
    d['prev_close'] = Money.price_units_to_yuan(p.prev_close) if p.prev_close is not None else None
    d['price_date'] = p.price_date.isoformat() if p.price_date else None
    # 当日已定型（#2210）：确认口径价格日期是否为今天 ⇒ true 时估值副行冗余，前端隐藏。
    # 判据是数据可用性（price_date 是否今天）而非时钟；比较收口 `pnl_settle`，此处不手写日期比较。
    d['settled_today'] = is_settled_today(p.price_date)
    if p.prev_close:
        d['day_pnl'] = Money.cents_to_yuan(Money.multiply_price_quantity(p.current_price - p.prev_close, p.quantity))
        # 单位与既有 `pnl_rate` 逐字一致：**百分数**（×100，两位小数），前端不再做换算
        d['day_pnl_rate'] = round((p.current_price - p.prev_close) / p.prev_close * 100, 2)
    else:
        # 无基准（未取到上一确认价 / 货基面值无当日涨跌）→ None，前端降级「—」。
        # 给 0 会被读成「今天一分没涨没跌」，那是在编造一个用户会信的结论。
        d['day_pnl'] = None
        d['day_pnl_rate'] = None
    # 是否计入组合（D20 二期开口项 4）：类现金资产（货基 / 逆回购 / cash）会被
    # `should_exclude_from_investment` 从组合持仓里滤掉，但盘点页仍显示这些行，
    # 于是「改派到某组合」成功了、组合页却永远看不到——静默无效比报错更难排查。
    # 判据必须由后端下发（集合的单一真相源在 `core/asset_types`，前端硬编码等于抄
    # 第二份真相源），前端据此把该格渲染成「不进组合」并禁用改派。
    d['in_portfolio'] = not should_exclude_from_investment(p)
    return d
