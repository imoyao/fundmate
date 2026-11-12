# -*- coding: utf-8 -*-
"""逆回购到期回款（#3087，决策 D114）。

## 为什么需要它

逆回购在本仓**不建持仓**，以孤儿流水记账（`position_id IS NULL`，口径见
`summary_service.orphan_money_fund_totals_by_ledger`）：买入记 `buy`（资金出借 ⇒
在途本金 +），到期回款记 `sell`（资金归还 ⇒ 在途本金 −）。

但导入链路只会给到「买入」那一半：真库 4 笔逆回购**全是 `buy`、没有任何一笔回款**
（`backend/invest.db` 实测，合计 202,000.84 元在途）。于是

- 账户页的「类现金」把早已回到现金账户的钱算成**还在逆回购里**（只增不减）；
- 总资产把这笔钱算了两遍：一遍在途本金、一遍它回到的现金余额;
- 而且没有任何入口能补上——本仓**没有**通用「手工新建流水」接口
  （`app/domains/transactions/views.py` 只有查/删，写入只走导入与申购赎回）。

## 口径

- **只整笔结清**：逆回购到期是一次性还本付息，没有「部分回款」。故回款金额恒等于
  当前在途本金，不让用户填——填一个更小的数会让剩下那部分永远悬着。
- **利息单独成行**（`dividend`，`is_income=True`）：它是收益（同 #863 D1「渠道发放的
  收益不是本金」），与本金混在一行会让「累计收益」少算这笔钱。
- **不允许批量回填 `trade_date`**：那批流水的 `trade_date` 是空的（162/163），补它等于
  替用户猜交易日，且会改变按日回放的所有口径。回款只写**回款日**，不动历史行。
- **幂等靠净额归零**：结清后在途本金为 0，再点一次会被拒（「没有在途本金」）；
  不引入额外的「已结清」标记列——那会多出一份可以与流水漂移的状态。
"""

from datetime import datetime
from typing import Any, Dict

from loguru import logger

from app.core.money import Money
from app.domains.transactions.models import Transaction
from app.services.summary_service import ORPHAN_BUCKET_NET, orphan_flow_delta

#: 逆回购的资产类型（`core/asset_types.py`）。只对这一类开放回款：
#: 货基没有「到期」，它的赎回本来就该由申购/赎回流水表达。
REVERSE_REPO_ASSET_TYPE = 'reverse_repo'

#: 回款流水的备注：删掉这条流水就能撤销回款，备注要让用户认得出它是什么。
SETTLE_NOTE = '逆回购到期回款'


class SettleError(Exception):
    """回款被拒（业务错，不是系统错）。`status_code` 直接给到 HTTP 层。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def outstanding_cents(db, family_id: int, ledger_id: int, symbol: str) -> int:
    """该账户该标的的**在途本金**（分）：孤儿逆回购流水的本金净额。

    只走 `orphan_flow_delta` 判据（本金桶），不自己写 elif 链——收益桶不属于本金，
    混进来会让「回款把收益也还了」。
    """
    rows = (
        db.query(Transaction.txn_type, Transaction.amount, Transaction.is_income)
        .filter(
            Transaction.family_id == family_id,
            Transaction.ledger_id == ledger_id,
            Transaction.asset_type == REVERSE_REPO_ASSET_TYPE,
            Transaction.symbol == symbol,
            Transaction.position_id.is_(None),
        )
        .all()
    )
    net = 0
    for txn_type, amount, is_income in rows:
        moved = orphan_flow_delta(txn_type, amount, is_income)
        if moved and moved[0] == ORPHAN_BUCKET_NET:
            net += moved[1]
    return net


def settle_reverse_repo(
    db,
    *,
    family_id: int,
    ledger_id: int,
    symbol: str,
    settle_date,
    interest_cents: int = 0,
) -> Dict[str, Any]:
    """整笔结清一笔逆回购：写一条 `sell`（本金）+ 可选一条 `dividend`（利息）。

    返回 `{settled_amount, interest_amount, transaction_ids}`（金额为元）。

    拒绝的三种情况都对应真实误操作：标的不是逆回购（货基没有到期）、没有在途本金
    （重复点/已回款）、利息为负。**不拒绝「回款日早于买入日」**：导入数据的
    买入日大面积为空（真库 162/163），拿它做校验只会把正常操作挡在门外。
    """
    if not symbol:
        raise SettleError('缺少标的代码，无法确定回款哪一笔逆回购')

    net_cents = outstanding_cents(db, family_id, ledger_id, symbol)
    if net_cents <= 0:
        raise SettleError('该逆回购当前没有在途本金（可能已回款），无需重复结清')
    if interest_cents < 0:
        raise SettleError('利息不能为负')

    # 名称取自已存在的流水：回款行要落在同一个「账户 + 产品」分组里，否则
    # `orphan_cash_like_breakdown` 会把它拆成新的一行。
    name = (
        db.query(Transaction.position_name)
        .filter(
            Transaction.family_id == family_id,
            Transaction.ledger_id == ledger_id,
            Transaction.asset_type == REVERSE_REPO_ASSET_TYPE,
            Transaction.symbol == symbol,
        )
        .order_by(Transaction.id.desc())
        .limit(1)
        .scalar()
    )

    common = {
        'family_id': family_id,
        'ledger_id': ledger_id,
        'position_id': None,
        'symbol': symbol,
        'position_name': name,
        'asset_type': REVERSE_REPO_ASSET_TYPE,
        'trade_date': settle_date,
        'status': 'success',
        'source': 'manual',
        'quantity': 0,
        'price': 0,
    }
    principal = Transaction(txn_type='sell', amount=net_cents, notes=f'{SETTLE_NOTE}（本金）', **common)
    db.add(principal)
    created = [principal]
    if interest_cents:
        interest = Transaction(
            txn_type='dividend',
            amount=interest_cents,
            is_income=True,
            notes=f'{SETTLE_NOTE}（利息）',
            **common,
        )
        db.add(interest)
        created.append(interest)
    db.flush()

    logger.info(f'逆回购到期回款：ledger={ledger_id} symbol={symbol} 本金={net_cents} 分 利息={interest_cents} 分')
    return {
        'settled_amount': Money.cents_to_yuan(net_cents),
        'interest_amount': Money.cents_to_yuan(interest_cents),
        'transaction_ids': [txn.id for txn in created],
    }


def parse_settle_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """把 HTTP 入参（字符串日期 / 元为单位的利息）翻成服务层参数。

    校验放在这里而不是视图里：视图只做「取值 → 调服务 → 组信封」（#1606 视图层厚度），
    而且这些规则（日期格式、利息非负）本身是业务约束，换个入口（CLI / 批量任务）
    也该一致。任何不合法都抛 `SettleError(400)`，由视图统一转信封。
    """
    symbol = str((data or {}).get('symbol') or '').strip()
    if not symbol:
        raise SettleError('缺少标的代码，无法确定回款哪一笔逆回购')
    raw_date = str((data or {}).get('settle_date') or '').strip()
    try:
        settle_date = datetime.strptime(raw_date, '%Y-%m-%d')
    except ValueError:
        raise SettleError('回款日格式应为 YYYY-MM-DD') from None
    try:
        interest_cents = Money.yuan_to_cents((data or {}).get('interest') or 0)
    except (TypeError, ValueError):
        raise SettleError('利息必须是数字') from None
    if interest_cents < 0:
        raise SettleError('利息不能为负')
    return {'symbol': symbol, 'settle_date': settle_date, 'interest_cents': interest_cents}


def settle_message(result: Dict[str, Any]) -> str:
    """回款成功后的提示语（含本金与利息，给用户一个可核对的数）。"""
    text = f'已登记回款：本金 ¥{result["settled_amount"]:.2f}'
    if result.get('interest_amount'):
        text += f'，利息 ¥{result["interest_amount"]:.2f}'
    return text
