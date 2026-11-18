# -*- coding: utf-8 -*-
"""对账差异的**就地裁决**（#1232 §5.4 / P2；#3125 从 `reconciliation_service` 下沉）。

四种裁决形态，语义各不相同（混用会把「改持仓」和「补流水」写成一件事）：

    increment  补一笔缺失买卖 → 买卖汇点（写 Transaction + 重算 Position）
    set        用户手填份额/成本 → 写人工锚点（`upsert_from_holding`，不建流水）；
               份额填 **0** = 按账单清仓（唯一合法的清仓入口，见 `_clear_position_by_bill`）
    anchor     以持仓**当前值**写人工锚点（#3125，免手抄；见 `reconciliation_anchor`）
    recompute  按流水派生结果覆写持仓份额（#3134，见 `reconciliation_recompute`）；
               派生额 ≤ 0 时拒绝，不会清仓（2026-11-16，见 `assert_recompute_keeps_position`）

> **未知 kind 一律拒绝**（`ADJUSTMENT_KINDS`）。原先 `if/elif` 的 `else` 兜底把没见过的
> kind 静默当成 `increment`（补录买入）：2026-11-16 真机实测，`--no-reload` 起的旧后端
> （早于 #3134）收到新前端的 `kind='recompute'` 就落到那次兜底，用户点「按流水重算份额」
> 得到的提示是「数量必须大于 0」——与操作毫无关系；更糟的是 payload 若带 quantity，
> 它会**真的写进一笔买入**。未知动作没有默认语义，只能拒绝并说清原因。

> `increment` 对 `quantity` 类差异是**无效动作**：它同时写流水与持仓，而差额是两者之差，
> 恒等于操作前的值。这条留在这里，是因为前端判据（`utils/discAction.ts`）把 `quantity`
> 指向 `recompute` / `set`，而 `increment` 只服务 `cost` / `cash` 那几类。

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
from app.core.money import Money
from app.domains.positions.state import mark_position_cleared
from app.domains.reconciliation.models import AdjustmentLog, ReconciliationDiscrepancy
from app.services.position_service import PositionService
from app.services.position_write_support import _find_existing_position
from app.services.reconciliation_adjustment import recompute_linked_discrepancy
from app.services.reconciliation_anchor import anchor_after_payload, write_anchor_from_position
from app.services.reconciliation_integrity import assert_supplement_is_new
from app.services.reconciliation_recompute import recompute_discrepancy_shares

#: 「就地裁决」唯一合法动作集，与前端 `reconcile-workbench/utils/discAction.ts` 的 4 个动作
#: 一一对应。为什么是白名单而不是 if/elif 的兜底：兜底会把未识别的 kind 静默当成
#: `increment`（见模块 docstring 里 2026-11-16 的真机事故），未知动作必须拒绝。
ADJUSTMENT_KINDS = ('increment', 'set', 'anchor', 'recompute')
_KINDS_LABEL = ' / '.join(ADJUSTMENT_KINDS)


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


def _apply_set(db: Session, family_id: int, data: dict):
    """设定型：写**人工锚点**（不是普通快照导入）。"""
    # 账单说「这只已经没有了」：份额 0 不是快照能表达的（``upsert_from_holding`` 要求 > 0），
    # 但它是唯一合法的清仓入口——按流水重算已被闸门挡住（见 ``position_recompute_entry``）。
    if data.get('quantity') is not None and float(data['quantity'] or 0) == 0:
        return _clear_position_by_bill(db, family_id, data)
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


def _clear_position_by_bill(db: Session, family_id: int, data: dict):
    """「改成账单份额 = 0」：按**账单**清仓（行保留 + 锚点重置为当日 0 份）。

    为什么不是直接用 ``mark_position_cleared`` 收工：清仓行仍走锚点派生
    （``compute_anchored_state`` 对 cleared 不豁免），旧锚点还写着 60 份时，
    下一次净值回填会把这条持仓**复活**成 60。故锚点必须一起改成
    「0 份 / 0 成本额 / 账单日 / manual」——与 #2343 再买入时的
    ``reactivate_cleared_position`` 同一套写法，只是方向相反。

    清仓是**人**的结论（账单上没有这只了），不是流水派生出来的结论：
    2026-11-16 用户定调「只应该把错的改对，不应该把对的改错」，
    所以这条路径只认显式填 0，不再由任何「按流水重算」触发。
    """
    position = _find_existing_position(db, data.get('ledger_id'), family_id, data.get('symbol') or '', '')
    if position is None:
        raise ValueError('找不到要清仓的持仓：可能已删除或归到了别的账本，请先刷新对账队列')
    cleared_on = data.get('snapshot_date') or date.today()
    mark_position_cleared(position, cleared_on)
    position.snapshot_quantity = 0
    position.snapshot_avg_price = 0
    position.snapshot_date = cleared_on
    position.anchor_kind = AnchorKind.MANUAL.value
    db.flush()
    return position, {
        'position_id': position.id,
        'symbol': position.symbol,
        'quantity': 0,
        'avg_price': Money.price_units_to_yuan(position.avg_price or 0),
        'cleared': True,
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
    set → `upsert_from_holding`（SET 语义、不建流水）；anchor → 以持仓现值写锚点；
    recompute → 按流水派生结果覆写持仓份额（不建流水、不写锚点）。
    审计写 `adjustment_logs`。携带 `discrepancy_id` 时，完成后由
    `recompute_linked_discrepancy` 重算差异：真正轧平才 cleared，差额仍在则保持
    pending，用户可继续补第二笔。payload：kind / op_type / discrepancy_id / reason
    / operator + 汇点字段。
    """
    kind = payload.get('kind', 'increment')
    if kind not in ADJUSTMENT_KINDS:
        # 未知动作不得有默认语义（见模块 docstring）：拒绝并说清「后端不认识它」，
        # 前端比后端新时用户看到的第一句话就是「重启后端」，而不是一句报错的买入口径。
        raise ValueError(
            f'未知的裁决类型 kind={kind!r}：后端只支持 {_KINDS_LABEL}。'
            '前端可能比后端新，请重启后端后再试（开发模式下 --debug 会自动重载）；本次未写入任何数据'
        )
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

    if kind == 'recompute':
        # 「按流水重算份额」（#3134）：写的是**持仓**（以流水派生结果为准），既不建流水也不
        # 写锚点。差额两端只有持仓这一侧会动，所以它是 quantity 差异唯一有效的补录之外的动作。
        # 审计由 `recompute_with_audit` 记（带 discrepancy_id），这里提前返回、不重复记一条。
        return recompute_discrepancy_shares(db, family_id, disc, reason=reason, operator=operator)

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
        position, after = _apply_set(db, family_id, data)
        # 清仓与「改份额」在审计里必须是两件事：复盘时一眼能看出这次动作把持仓归零了。
        action = 'clear' if after.get('cleared') else ('adjust' if disc else 'supplement')
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
