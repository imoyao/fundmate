# -*- coding: utf-8 -*-
"""持仓「编辑」写入规则：配置目标 / 现价 / 备注 / 到期日 / 产品名称与编码
（#1123 P0 / #931）。

## 为什么在 services 而不在视图

`domains/ledgers/views.py` 有 656 行的冻结基线（`scripts/check_view_thickness.py`，
存量视图「只减不增」）。原实现把「五笔钱白名单」「金额单位换算」直接写在端点里，
本轮要加到期日就必然再长十来行。按 `conventions.md` §2.2（视图只做 HTTP 编排）
下沉到这里：端点只剩「取参 → 调本函数 → 组信封」，各字段的口径也收在一处，
不必在两个端点之间对读。

## 到期日为什么按品类 fail closed

`positions.maturity_date` 只有逆回购（时间建模：到期即不再计入投资）与银行理财
（D121：仅记录，到期仍计入）有语义。基金 / 股票没有到期日，传进来是上游把字段
接错了；静默忽略会让「我明明设了到期日」变成一条查不出原因的 NULL——故报 400。
判据复用买入侧的 `assert_maturity_date_allowed`，同一份口径不写第二遍。

## 为什么只有银行理财能改名称与编码

基金 / 股票 / 指数的 `symbol` 与 `name` 来自行情名录（`funds` / `securities` /
`indices`），是**外部真相源的投影**；让用户改只会让持仓与名录对不上（估值查不到、
分红匹配不到），而名录错则应该修名录。银行理财相反：登记编码没有中心目录可查
（D121），这条记录**是用户手填的**，填错就得能改——首次录入时只有一个输入框，
容易把产品名当编码填进去。

改名不是装扮门面：`symbol` 是持仓身份（`uq_positions_ledger_symbol_norm`）与流水匹配键
（多处 `Transaction.symbol == position.symbol` 字面量等值），故必须连同该持仓的
流水快照一起改，否则成本与回款全部失联。
"""

from datetime import date
from typing import Any

from sqlalchemy import or_

from app.core.allocation_rules import resolve_allocation_source
from app.core.constants import ALLOCATION_LABELS
from app.core.money import Money
from app.core.symbol_utils import symbol_identity
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.position_write_policy import assert_maturity_date_allowed


def apply_position_edit(db: Any, pos: Any, data: dict) -> None:
    """把编辑载荷应用到 `pos`（原地改属性，不 commit）。

    只认六个字段：配置目标 / 现价 / 备注 / 到期日 / 产品名称 / 登记编码。其余静默
    忽略——与本端点此前「字段白名单」口径一致：调用方多传字段不算错，落库前一律过滤。

    校验失败抛 `ValueError`，由视图转成 400（沿用 `abort(400, ...)` 的信封）。
    """
    if 'allocation' in data:
        # 五笔钱白名单（#1123 P0）；None = 清空语义保留
        if data['allocation'] is not None and data['allocation'] not in ALLOCATION_LABELS:
            raise ValueError('非法配置目标')
        pos.allocation = data['allocation']
        # 来源打标（#3115 D2）：本路径不走 AllocationSourceStampMixin（那是
        # AssetCreate/AssetUpdate/PositionUpdate 的 model_dump 出口，本端点是裸
        # dict 直入），不接的话用户行内改的配置目标落到 default——下一次 G3 回填
        # （只放 default）就会把手动选择覆盖掉，正是 P0-7 要防的事。判据与 mixin
        # 一致：「请求体显式带了 allocation」即显式；清空（None）也是用户的显式
        # 动作，同样标 user 受保护。
        pos.allocation_source = resolve_allocation_source(explicit=True, allocation=data['allocation'], path='form')
    if 'current_price' in data:
        pos.current_price = Money.yuan_to_price_units(data['current_price'])
    if 'notes' in data:
        pos.notes = data['notes']
    if 'maturity_date' in data:
        pos.maturity_date = parse_maturity_date(data['maturity_date'], pos.asset_type)
    if 'name' in data or 'symbol' in data:
        apply_identity_edit(db, pos, data)


def apply_identity_edit(db: Any, pos: Any, data: dict) -> None:
    """手工标的的名称 / 编码（仅银行理财，见模块 docstring）。

    两个字段可能只来一个：只改名时编码不动，只编码时名称不动。`symbol` 归一成
    大写去空白——同一个码两种写法会绕过唯一索引长出两行（#1662 的复发形态）。
    """
    if pos.asset_type != 'bank_wealth':
        raise ValueError('仅银行理财可修改产品名称与登记编码')
    if 'name' in data:
        pos.name = clean_name(data['name'])
    if 'symbol' in data:
        rename_symbol(db, pos, data['symbol'])


def clean_name(raw: Any) -> str | None:
    """产品名归一：去空白；空串按「清空」处理（清空后列表回落显示编码）。

    `None` 而非空串：本列可空，空串会变成「有一个长度为 0 的名字」，
    展示层两种空值各判一次迟早漏一处。
    """
    name = str(raw or '').strip()
    return name or None


def rename_symbol(db: Any, pos: Any, raw: Any) -> None:
    """改登记编码：校验同账户唯一 → 落持仓 → 同步该持仓的流水快照。"""
    new = str(raw or '').strip().upper()
    if not new:
        raise ValueError('登记编码不能为空')
    new_norm = symbol_identity(new, pos.asset_type)
    if new_norm == symbol_identity(pos.symbol, pos.asset_type):
        # 只改了大小写 / 空白：身份没变，仍落归一形态（否则库里同时存在两种写法）
        pos.symbol = new
        return
    conflict = (
        db.query(Position.id)
        .filter(
            Position.ledger_id == pos.ledger_id,
            Position.id != pos.id,
            or_(Position.symbol_norm == new_norm, Position.symbol == new),
        )
        .first()
    )
    if conflict:
        # 让它在这里 400，而不是在 commit 时炸唯一索引（那是 500，用户只看到「服务器错误」）
        raise ValueError(f'该账户已有编码 {new} 的持仓，同一产品只应有一条')
    pos.symbol = new
    rename_position_transactions(db, pos.id, new, new_norm)


def rename_position_transactions(db: Any, position_id: int, symbol: str, symbol_norm: str) -> None:
    """把该持仓已落库的流水快照同步成新编码（按 `position_id` 精确定位）。

    读侧有多处 `Transaction.symbol == position.symbol` 的字面量等值匹配
    （`symbol_scope` / `cash_like_settle` / 对账链路）：只改持仓不改流水，那些流水
    就指向一个已不存在的标的——成本、已实现盈亏、回款全部静默失联。
    `symbol_norm` 必须显式给：批量 `update()` 不触发 mapper 事件。
    """
    db.query(Transaction).filter(Transaction.position_id == position_id).update(
        {'symbol': symbol, 'symbol_norm': symbol_norm},
        synchronize_session=False,
    )


def parse_maturity_date(raw: Any, asset_type: str) -> date | None:
    """解析到期日：空值 = 清空（合法，任何品类都允许）；品类不符 / 格式非法 = 400。

    `None` 与空串都按「清空」处理：前端 `el-date-picker` 清空后回传空串，
    若把它当非法格式拒绝，用户就永远撤不掉一个填错的日期。
    """
    if raw is None or raw == '':
        return None
    assert_maturity_date_allowed({'maturity_date': raw}, asset_type)
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        raise ValueError('到期日格式应为 YYYY-MM-DD') from None
