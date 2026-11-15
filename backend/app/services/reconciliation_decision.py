# -*- coding: utf-8 -*-
"""对账差异的**就地裁决**（#1232 §5.4 / P2；#3125 从 `reconciliation_service` 下沉）。

三种裁决形态，语义各不相同（混用会把「改持仓」和「补流水」写成一件事）：

    increment  补一笔缺失买卖 → 买卖汇点（写 Transaction + 重算 Position）
    set        用户手填份额/成本 → 写人工锚点（`upsert_from_holding`，不建流水）
    anchor     以持仓**当前值**写人工锚点（#3125，免手抄；见 `reconciliation_anchor`）

## 为什么从 service 下沉

`reconciliation_service` 的体积基线已顶格（388 行，只减不增），而 #3125 要新增
`anchor` 分支。按本仓既定做法（`position_service` 的 facade 范式），把裁决链路整体
搬到独立模块、主模块留转发壳——**不是**为了凑行数把注释删掉：裁决与「比对检测」
本来就是两件事（一个写库、一个只读算差异），拆开后各自只有一条职责。

## 下沉时刻意不改的行为

- 审计仍写 `adjustment_logs`，`before_json`/`after_json` 结构逐字不变；
- `set` 分支的 `allow_anchor_rewind=True`、`snapshot_date` 缺省今天等口径原样保留；
- `increment` 分支的 `assert_supplement_is_new` 闸门位置不变（必须在写库之前）。
"""

import json
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.constants import AnchorKind, PositionSource
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy
from app.services.position_service import PositionService
from app.services.position_write_support import _find_existing_position
from app.services.reconciliation_adjustment import recompute_linked_discrepancy
from app.services.reconciliation_anchor import anchor_after_payload, write_anchor_from_position
from app.services.reconciliation_integrity import assert_supplement_is_new


def resolve_sell_position_id(db: Session, family_id: int, data: dict) -> dict:
    """卖出/取出补录缺 `position_id` 时按统一身份键定位持仓并回填，原样返回 data。

    为什么这里要自己定位：对账补录的 payload 只有 `(symbol, ledger_id)`，没有
    「完整记账」UI 的持仓下拉，而卖出汇点 `prepare_sell` 第一行就是
    `data['position_id']` —— 用户实测补一笔卖出直接 500（KeyError: 'position_id'）。
    买入侧无此问题（`position_buy_command` 自己按身份键查/建持仓）。`venue=''`：
    payload 通常不带 asset_type/market，强判场所会把 asset_type 为 NULL 的存量行
    漏掉；`ledger_id` 允许 None（positions.ledger_id 可为 NULL，差异本就由持仓派生）。
    显式传了 `position_id` 时透传不覆盖；找不到时 ValueError → views 层转 400。
    """
    if data.get('position_id') is not None:
        return data
    pos = _find_existing_position(db, data.get('ledger_id'), family_id, data.get('symbol', ''), '')
    if pos is None:
        raise ValueError('找不到这笔持仓：可能已清仓、换了账本，或持仓记录已被删除。若已删除，去「修正数据」按流水重建')
    data['position_id'] = pos.id
    return data


def _normalize_dates(data: dict) -> None:
    """API 传入的是 ISO 字符串，而汇点/模型要求 Python date 对象。

    绕过 PositionCreate schema 的类型转换后必须在此显式处理，否则 SQLite 报
    `Date type only accepts Python date objects`。
    """
    for key in ('confirm_date', 'snapshot_date', 'trade_date'):
        raw = data.get(key)
        if isinstance(raw, str) and raw:
            try:
                data[key] = (
                    datetime.strptime(raw[:10], '%Y-%m-%d').date()
                    if key != 'trade_date'
                    else datetime.strptime(raw[:10], '%Y-%m-%d')
                )
            except ValueError:
                raise ValueError(f'日期格式错误: {key}={raw!r}，应为 YYYY-MM-DD')


def _apply_set(db: Session, data: dict):
    """设定型：写**人工锚点**（不是普通快照导入）。"""
    # - anchor_kind='manual'：同日外部快照不得覆盖它（见 _assert_anchor_accepts）；
    # - allow_anchor_rewind=True：用户显式要求设定持仓，不属于「导入旧快照」，
    #   不受「更旧日期拒绝」约束——这是唯一的合法回退入口；
    # - snapshot_date 缺省取今天：用户是「以此刻的事实」校准，而非补历史快照。
    data.setdefault('anchor_kind', AnchorKind.MANUAL.value)
    data.setdefault('snapshot_date', date.today())
    position = PositionService.upsert_from_holding(db, data, allow_anchor_rewind=True)
    return position, {
        'position_id': position.id,
        'symbol': position.symbol,
        'quantity': position.quantity,
        'avg_price': position.avg_price,
    }


def _apply_increment(db: Session, family_id: int, data: dict):
    """增量型：走交易处理汇点（写 Transaction + 更新 Position）。"""
    op_type = data.get('op_type', 'buy')
    # 补录是「修差异」，不是「记账」：既有的同笔流水、同标的缺归属流水都必须先处置，
    # 否则差异会被重复录入「轧平」成假修复（reconciliation_integrity 模块 docstring）。
    assert_supplement_is_new(db, family_id, data)
    if op_type in ('sell', 'withdraw'):
        position = PositionService.process_sell_or_withdraw(db, resolve_sell_position_id(db, family_id, data))
    else:
        position = PositionService.process_buy_or_deposit(db, data)
    return position, {
        'position_id': position.id if position else None,
        'symbol': data.get('symbol'),
        'op_type': op_type,
        'quantity': data.get('quantity'),
        'avg_price': data.get('avg_price'),
    }


def apply_decision(db: Session, family_id: int, payload: dict) -> dict:
    """就地补充/调整裁决（#1232 §5.4 / P2）：生成调整凭证 + 审计日志。

    不新建调整表：increment → 买卖汇点（Transaction + Position）；
    set → `upsert_from_holding`（SET 语义、不建流水）；anchor → 以持仓现值写锚点。
    审计写 `adjustment_logs`。携带 `discrepancy_id` 时，完成后由
    `recompute_linked_discrepancy` 重算差异：真正轧平才 cleared，差额仍在则保持
    pending，用户可继续补第二笔。payload：kind / op_type / discrepancy_id / reason
    / operator + 汇点字段。
    """
    kind = payload.get('kind', 'increment')
    disc_id = payload.get('discrepancy_id')
    reason = payload.get('reason')
    operator = payload.get('operator')

    disc = None
    if disc_id:
        disc = (
            db.query(ReconciliationDiscrepancy)
            .filter(ReconciliationDiscrepancy.id == disc_id, ReconciliationDiscrepancy.family_id == family_id)
            .first()
        )
        if not disc:
            raise ValueError('差异不存在或无权访问')

    data = {k: v for k, v in payload.items() if k not in ('kind', 'discrepancy_id', 'reason', 'operator')}
    data['family_id'] = family_id
    _normalize_dates(data)
    # 对账补录来源标记（决策 11）。RECONCILIATION_ADJUSTMENT 由 #1238 引入；
    # 当前分支若未合入 #1238 则回退 manual，保证 P2 代码在合入前后均可运行。
    recon_source = getattr(PositionSource, 'RECONCILIATION_ADJUSTMENT', PositionSource.MANUAL).value
    data.setdefault('source', recon_source)

    # 操作前快照（审计）
    before = {
        'discrepancy_id': disc_id,
        'symbol': data.get('symbol'),
        'ledger_id': data.get('ledger_id'),
        'kind': kind,
    }

    if kind == 'anchor':
        # 「以此为准」：份额/成本取持仓现值，actions 不改数值（详见 reconciliation_anchor）。
        position = write_anchor_from_position(db, family_id, disc)
        after = anchor_after_payload(position)
        action = 'anchor'
    elif kind == 'set':
        position, after = _apply_set(db, data)
        action = 'adjust' if disc else 'supplement'
    else:
        position, after = _apply_increment(db, family_id, data)
        action = 'supplement'

    db.flush()

    # 审计日志（用户主动操作，§5.5）
    log = AdjustmentLog(
        family_id=family_id,
        discrepancy_id=disc_id,
        action=action,
        before_json=json.dumps(before, default=str),
        after_json=json.dumps(after, default=str),
        reason=reason,
        operator=operator,
    )
    db.add(log)
    # 先落审计日志拿到 log.id，也让本次补录对重算可见（autoflush=False）
    db.flush()
    result = {'action': action, 'before': before, 'after': after, 'log_id': log.id}
    if disc:
        result['discrepancy'] = recompute_linked_discrepancy(db, family_id, disc)
    db.flush()
    return result
