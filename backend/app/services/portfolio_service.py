# -*- coding: utf-8 -*-
"""投资组合域的查询 / 展示行组装 + 账户关联维护服务（#1642 B 块从 views 下沉，承 #1606；
#981 追加关联原子替换）。

WHY 下沉
    `get_portfolio_holdings` 长在视图里（104 行），含组合校验、关联账户推导、持仓/资产
    联合查询、类现金排除与逐行市值/盈亏组装——属纯读组装，却只能挂在 HTTP 栈下测。
    本模块把这部分收口，视图只做归属校验 + 调服务 + 组响应信封。

边界
    - 不碰 ``g`` / ``request``：family_id 由调用方显式传入，可脱离请求上下文单测；
    - 查询组装为只读；关联维护（``replace_portfolio_ledger_links``）只做批量 UPDATE、
      不 commit——提交权在调用方会话；
    - 对外 API 契约零变更（``conventions.md`` §2.4）：返回字段名、嵌套结构与下沉前逐字一致
      （此后按需**只增不改**追加行级字段——#2210 的 ``price_date`` / ``settled_today``）；
"""

from sqlalchemy import and_, or_, update

from app.core.constants import ASSET_CATEGORY_LABELS, TYPE_LABELS
from app.core.money import Money
from app.domains.assets.models import Asset
from app.domains.ledgers.models import Ledger
from app.domains.portfolios.models import Portfolio
from app.domains.positions.models import Position
from app.services.fund_utils import should_exclude_from_investment
from app.services.pnl_settle import is_settled_today


def portfolio_ledger_ids(db, family_id: int, portfolio_id: int) -> list[int]:
    """组合的关联账户集合（``ledgers.portfolio_id`` 指向本组合的账户）。

    注意：这套集合**不再决定组合是否可见**——组合可以只靠``positions.portfolio_id``
    显式指派持仓而存在（A0）。它只用于两件事：持仓的**继承**路径、账户级资产（现金）归属。
    """
    return [
        row[0]
        for row in db.query(Ledger.id).filter(Ledger.portfolio_id == portfolio_id, Ledger.family_id == family_id).all()
    ]


def portfolio_position_conditions(portfolio_id: int, ledger_ids: list[int]) -> list:
    """组合持仓的归属条件（**唯一口径**，持仓视图与组合收益共用）。

    - 主路径：``positions.portfolio_id == portfolio_id``（显式指派，永远优先）
    - 继承路径：仅当持仓未显式指定组合时，继承其账户(ledger)的默认组合

    显式指派必须压过继承，否则改派后的持仓会同时出现在「账户默认组合」里
    （D20 一期回归测试 ``test_position_explicit_portfolio_id_takes_precedence``）。
    `ledger_ids` 为空时只保留显式条件——这正是「组合不绑任何账户、纯靠持仓归属可见」的场景。

    **等价实现**：``services/scope.filter_positions_by_scope`` 是同一语义的内存版
    （对已取出的持仓列表过滤，供穿透 / 收益日历 / 策略视图复用）。两者必须同步修改，
    改任一处前先看另一处的注释。
    """
    conds = [Position.portfolio_id == portfolio_id]
    if ledger_ids:
        conds.append(and_(Position.portfolio_id.is_(None), Position.ledger_id.in_(ledger_ids)))
    return conds


def build_portfolio_holdings(db, family_id: int, portfolio_id: int) -> list[dict]:
    """组合下所有关联账户的持仓/资产明细（#1642 B 块，从视图层下沉）。

    与下沉前逐字段一致：
    - 组合不存在 / 已删除 / 非本家庭 → 抛 ``ValueError('投资组合不存在')``，由视图转 404；
    - 主路径 ``positions.portfolio_id == portfolio_id``；继承路径仅当持仓未显式指定组合时
      继承其账户(ledger)的默认组合（显式 portfolio_id 必须覆盖 ledger 继承）；
    - **组合可以不关联任何账户**（A0）：此时仍返回显式指派的持仓，只是没有继承路径与账户级资产。
      历史实现以 ``if not ledger_ids: return []`` 提前返回，等于要求组合必须先绑账户，
      与 D20「组合成员是持仓」的定义冲突——A 账户默认组合是固收+时，成长组合绑不上该账户，
      结果整个组合为空；
    - 类现金由 ``should_exclude_from_investment`` 排除（尊重 count_as_investment 覆盖）；
    - 账户级资产（现金，非负债）并入同一 holdings 列表，以 ``asset.id + 100000`` 区分；
    - holdings 行为 **dict 直出**（无视图 Out schema），#2210 起持仓行增发
      ``price_date`` / ``settled_today``，D20 二期 UI 起增发 ``portfolio_id``
      （只增不改，原字段逐字不变）；资产行**不含** ``portfolio_id``——现金沿用账户归属，
      没有持仓级组合概念，前端不得把它当成「继承态」渲染。
    """
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.is_deleted.is_(False),
            Portfolio.family_id == family_id,
        )
        .first()
    )
    if not portfolio:
        raise ValueError('投资组合不存在')

    # 关联账户 ID 列表（组合 = 默认组合指向本组合的账户集合）
    # 允许为空：组合可以只靠显式持仓归属存在，不要求先绑账户（A0）。
    ledger_ids = portfolio_ledger_ids(db, family_id, portfolio_id)

    # 查询持仓（仅用 portfolio_id / ledger_id 关联，杜绝 account_name 字符串匹配）
    positions = (
        db.query(Position)
        .filter(
            or_(*portfolio_position_conditions(portfolio_id, ledger_ids)),
            Position.quantity > 0,
        )
        .all()
    )
    # 类现金排除改由统一函数判定（决策 #7：尊重 count_as_investment 覆盖 + 逆回购到期自动转现金）
    positions = [p for p in positions if not should_exclude_from_investment(p)]

    # 账户级资产仍按 ledger_id 关联（现金不进持仓级组合，沿用账户归属）
    # 无关联账户时自然没有账户级资产可并入，跳过查询（空 in_ 会生成无意义 SQL）
    assets = (
        db.query(Asset)
        .filter(
            Asset.ledger_id.in_(ledger_ids),
            # 排除负债
            Asset.major_category != 'liability',
        )
        .all()
        if ledger_ids
        else []
    )

    # 构造持仓列表（包含市值和盈亏）
    holdings = []
    for pos in positions:
        market_value = Money.multiply_price_quantity(pos.current_price, pos.quantity)
        pnl = Money.multiply_price_quantity(pos.current_price - pos.avg_price, pos.quantity) if pos.avg_price else 0

        holdings.append(
            {
                'id': pos.id,
                'symbol': pos.symbol,
                'name': pos.name,
                'type': pos.asset_type,
                'type_label': TYPE_LABELS.get(pos.asset_type, pos.asset_type),
                'account_name': pos.account_name,
                'quantity': Money.min_unit_to_shares(pos.quantity),
                'current_price': Money.price_units_to_yuan(pos.current_price),
                'avg_price': Money.price_units_to_yuan(pos.avg_price),
                'market_value': Money.cents_to_yuan(market_value),
                'pnl': Money.cents_to_yuan(pnl),
                'pnl_rate': round((pos.current_price - pos.avg_price) / pos.avg_price * 100, 2)
                if pos.avg_price
                else 0.0,
                # 价格时点 + 当日已定型（#2210，与持仓明细 #2140 同名同义）：组合页持仓行同样
                # 要能隐藏估值副行——判据是 price_date 是否今天，比较收口 `pnl_settle`。
                # 本查询是全量 ORM 实体（db.query(Position)），price_date 未被 select 裁剪，可直接取。
                'price_date': pos.price_date.isoformat() if pos.price_date else None,
                'settled_today': is_settled_today(pos.price_date),
                # 归属方式原样透出（D20 二期 UI）：``None`` = 本行是被账户继承路径带进来的
                # （``ledger.portfolio_id`` 默认组合），非 ``None`` = 用户显式指派到本组合。
                # 前端据此区分「随账户」与「本组合独有」——两种状态在库里语义不同，
                # 展示层若都渲染成组合名，用户无法判断改派是否真的生效。
                'portfolio_id': pos.portfolio_id,
            }
        )

    for asset in assets:
        holdings.append(
            {
                'id': asset.id + 100000,
                'symbol': asset.major_category or 'asset',
                'name': asset.name or asset.major_category,  # 使用 name 字段
                'type': asset.major_category,
                'type_label': ASSET_CATEGORY_LABELS.get(asset.major_category, asset.major_category or '其他'),
                'account_name': asset.account_name,
                'ledger_id': asset.ledger_id,
                'quantity': 1,
                'current_price': Money.cents_to_yuan(asset.amount),
                'avg_price': Money.cents_to_yuan(asset.amount),
                'market_value': Money.cents_to_yuan(asset.amount),
                'pnl': 0.0,
                'pnl_rate': 0.0,
                # 静态资产无价格日期概念（不随行情定型，也没有估值副行）→ 两字段恒 None（#2210）
                'price_date': None,
                'settled_today': None,
            }
        )

    return holdings


def replace_portfolio_ledger_links(db, portfolio_id: int, family_id: int, new_ids: list[int]) -> None:
    """原子替换组合的关联账户集合（#981，从 PATCH 视图下沉）。

    WHY 下沉
        原「账户关联 diff」长在 PATCH 视图里（归属校验 + 集合差 + 逐对批量写），
        触发视图层厚度守卫（单函数 ≤ 60 行、lines 基线只减不增，#1606）；且它与
        holdings 组装同属「组合-账户关联」概念，收口服务层后可被未来其它入口
        （如账户列表页改归属）复用。

    语义（与原前端 diff 逐位对齐）
        - ``new_ids`` 视为完整目标集合：集合外的现挂账户解绑（portfolio_id=None）；
        - 集合内的未挂账户绑定到本组合（含从其它组合迁入 = 原「直接置值」语义）；
        - ``[]`` = 全部解绑；调用方不传 ledger_ids 时不应进入本函数；
        - 目标账户必须属于 ``family_id``：任一不存在/越权 → 抛 ``ValueError``
          （由视图转 404），校验发生在任何写之前，保证零部分更新。

    边界：只做批量 UPDATE、不 commit（提交权在调用方会话）。
    """
    new_ids = list(dict.fromkeys(new_ids))
    if new_ids:
        owned_count = db.query(Ledger.id).filter(Ledger.id.in_(new_ids), Ledger.family_id == family_id).count()
        if owned_count != len(new_ids):
            raise ValueError('关联账户不存在或无权访问')
    current_ids = {
        row[0]
        for row in db.query(Ledger.id).filter(
            Ledger.portfolio_id == portfolio_id,
            Ledger.family_id == family_id,
        )
    }
    to_unlink = current_ids - set(new_ids)
    to_link = set(new_ids) - current_ids
    if to_unlink:
        db.execute(
            update(Ledger).where(Ledger.id.in_(to_unlink), Ledger.family_id == family_id).values(portfolio_id=None)
        )
    if to_link:
        db.execute(
            update(Ledger)
            .where(Ledger.id.in_(to_link), Ledger.family_id == family_id)
            .values(portfolio_id=portfolio_id)
        )
