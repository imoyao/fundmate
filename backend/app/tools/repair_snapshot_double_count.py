# -*- coding: utf-8 -*-
"""存量持仓「快照份额被流水重复累加」的扫描与修复（一次性迁移工具）。

## 问题

`positions.quantity` 曾是快照与流水共用的变量：

- 快照导入（`upsert_from_holding`）SET 绝对值；
- 流水落库（`process_buy_or_deposit`）INCR 累加。

先导持仓快照、后导快照日之前的交易流水时，这部分流水被二次计入。
实测账户 012708：快照 11,083.22 → 加了三笔历史买入 → 22,166.44（精确 2 倍）。

## 为什么不能「全量重算」

修复需要每行一个可信的 `snapshot_quantity`（快照当日份额），而**历史值已经丢了**
——导入时直接写进 `quantity`，随后被流水加权覆盖。同一个 `quantity = 22166.44`：

- 先流水后快照（正确）：`quantity` 就是快照值；
- 先快照后流水（错误）：`quantity = 快照值 + 快照前流水净额`。

盲猜任一方向都会把另一半账户改坏。所以本工具**先出报告**，只在能给出强证据时才建议写入。

## 判定证据（按强度排序）

1. **`import_hash` 反解（强）**——`import_hash = hash(source|ledger|symbol|日期)`，
   日期取自最后一次写入（快照日或某笔交易的确认日）。候选日期重算比对即可反解：
   - 解出的日期 `<= 快照日`：说明最后一次写入的是一笔「本应已包含在快照里」的流水
     ⇒ **确证**重复累加；
   - 解出的日期 `== 快照日`：最后一次写入是快照 ⇒ 份额未被后续流水改动 ⇒ **确证**正确。
2. **比值（弱）**——`quantity / 快照前流水净额 ≈ 2` 提示重复累加，但可能被
   「快照比流水多（分红/漏录）」误触发，故只作提示，需 `--include-likely` 才写。
3. 其余一律 `needs_review`，交给对账工作台人工裁决。

## 用法

    # 只读扫描，输出表格（默认）
    python -m app.tools.repair_snapshot_double_count --report

    # 写入「确证」的行
    python -m app.tools.repair_snapshot_double_count --apply --confirm

    # 连同「疑似」一起写（风险更高，先看报告再决定）
    python -m app.tools.repair_snapshot_double_count --apply --confirm --include-likely

    # 限定单个家庭 / 账户
    python -m app.tools.repair_snapshot_double_count --report --family 1 --ledger 3

    # 只修单个持仓行（人工确认过的那一行）
    python -m app.tools.repair_snapshot_double_count --apply --confirm --position 253

## 判定口径的两个反证（实测踩过）

1. **快照后流水必须先扣掉**：当前值 = 锚点 + 快照前流水(仅重复累加时) + 快照后流水。
   反推锚点写 `current − pre_net` 会让 `recompute` 再把 `post_net` 加一次 ⇒ 凭空多一份。
2. **`import_hash` 反解不足以单独定案**：它只能说明「最后一次写入用的是哪个日期」，
   而快照导入之外的写入路径不刷新 `position.import_hash`。因此在 hash 支持重复累加时，
   还要求 `current − post_net >= 2 × pre_net`——快照日的真实持仓不可能小于该日前的
   净买入。实测 7 行「hash 确证」里 6 行被此条件证伪（把 2.9 万份写成 1.2 万份）。

## 安全边界

- 只处理 `ownership_status='active'` 且 `snapshot_quantity IS NULL` 的持仓；
- 只写 `snapshot_quantity / snapshot_avg_price / snapshot_date / anchor_kind`，
  随后调 `recompute_position_from_transactions` 由锚点派生 `quantity`；
- `--apply` 必须同时给 `--confirm`，避免误触；
- `snapshot_quantity <= 0` 的行一律跳过（份额不可能非正）。
"""

import argparse
import sys
from datetime import date

from app.core.constants import AnchorKind
from app.core.money import Money
from app.services.import_records import compute_position_hash
from app.services.position_service import _txn_effective_date

# 比值判定的容差：实测重复累加是精确 2 倍，留 1% 吸收份额舍入与手续费尾差
_RATIO_TOLERANCE = 0.01


def _net_units(txns) -> int:
    total = 0
    for t in txns:
        if t.txn_type in ('buy', 'deposit', 'split'):
            total += t.quantity or 0
        elif t.txn_type in ('sell', 'withdraw'):
            total -= t.quantity or 0
    return total


def _infer_hash_date(pos, txns, candidates) -> date | None:
    """从 `positions.import_hash` 反解「最后一次写入的日期」。

    hash 只由 `source|ledger_id|symbol|日期` 决定，因此把候选日期逐个重算比对即可。
    候选集 = 快照日 + 所有流水的确认日（写入路径只会用这两类日期）。
    """
    if not pos.import_hash:
        return None
    for d in sorted({c for c in candidates if c is not None}, reverse=True):
        if compute_position_hash(pos.source or '', pos.ledger_id, pos.symbol or '', d) == pos.import_hash:
            return d
    return None


def analyse_position(db, pos) -> dict:
    """单行分析：返回判定结果（不写库）。"""
    from app.domains.transactions.models import Transaction

    txns = (
        db.query(Transaction)
        .filter(Transaction.position_id == pos.id)
        .order_by(Transaction.trade_date, Transaction.id)
        .all()
    )
    result = {
        'position_id': pos.id,
        'ledger_id': pos.ledger_id,
        'symbol': pos.symbol,
        'name': pos.name,
        'snapshot_date': pos.snapshot_date,
        'current_qty': pos.quantity,
        'pre_flow_net': 0,
        'post_flow_net': 0,
        'verdict': 'skipped',
        'implied_qty': None,
        'evidence': '',
    }

    if pos.ownership_status != 'active':
        result['evidence'] = '非 active（影子行）'
        return result
    if pos.snapshot_quantity is not None:
        result['evidence'] = '已有锚点份额'
        return result
    if pos.snapshot_date is None:
        result['evidence'] = '无快照日'
        return result

    # 日期解析必须与派生引擎同源：`_txn_effective_date` 会在 confirm_date 为空时
    # 回落到 trade_date。早期版本只看 confirm_date，把「confirm_date 为空但
    # trade_date 在快照之后」的流水漏掉，导致反推的锚点把一笔已卖出算成持有
    # （实测 012345：快照 5,000、之后卖出 5,000，反推得到 10,000）。
    dated = [(t, _txn_effective_date(t)) for t in txns]
    pre = [t for t, d in dated if d is not None and d <= pos.snapshot_date]
    post = [t for t, d in dated if d is not None and d > pos.snapshot_date]
    undated = [t for t, d in dated if d is None and t.quantity]
    if undated:
        result['verdict'] = 'needs_review'
        result['evidence'] = f'{len(undated)} 条份额流水无法判定归属日（confirm_date/trade_date 皆空）'
        return result
    pre_net = _net_units(pre)
    # 快照后的流水是**合法增量**：当前值里已经含它们，反推锚点时必须先扣掉，
    # 否则锚点会被抬高，`recompute` 再把 post 加一次 = 凭空多出一份。
    post_net = _net_units(post)
    result['pre_flow_net'] = pre_net
    result['post_flow_net'] = post_net

    # 当前值 = 快照锚点 + 快照前流水(仅在重复累加时) + 快照后流水
    #   → 锚点 = current − pre_net(被重复累加时) − post_net
    base = pos.quantity - post_net

    if pre_net == 0:
        # 快照日之前没有流水 → 没有可被重复累加的对象，锚点就是 base
        result['verdict'] = 'safe'
        result['implied_qty'] = base
        result['evidence'] = '快照日前无流水'
        return result
    if pre_net < 0:
        # 净卖出，无法用简单差额反推（快照可能本就小于流水口径）
        result['verdict'] = 'needs_review'
        result['evidence'] = f'快照前流水净额为负({pre_net})'
        return result

    candidates = [pos.snapshot_date] + [t.confirm_date for t in txns if t.confirm_date]
    hash_date = _infer_hash_date(pos, txns, candidates)

    # 可行性反证：若真发生了「全量重复累加」，锚点 = base − pre_net，
    # 而快照日的真实持仓必须**不小于**该日之前的流水净额（份额不会凭空消失），
    # 即要求 base − pre_net >= pre_net ⇔ base >= 2 × pre_net。
    # 违反者说明 import_hash 反解出的「最后一次写入」并非快照写入口径
    # （实测 14 行里 13 行栽在这里），不能据此写锚点。
    # 用相对容差而非精确倍数：份额按 0.0001 份取整，实测 012708 就差 44 个最小单位。
    feasible = base >= 2 * pre_net * (1 - _RATIO_TOLERANCE)

    if hash_date is not None and hash_date <= pos.snapshot_date:
        if not feasible:
            result['verdict'] = 'no_double_count'
            result['implied_qty'] = base
            result['evidence'] = (
                f'反证：推算快照份额 {_fmt_qty(base - pre_net)} < 快照日前流水净额 '
                f'{_fmt_qty(pre_net)}，全量重复累加不可能（当前值已含快照后流水 {_fmt_qty(post_net)}）'
            )
            return result
        implied = base - pre_net
        if implied > 0:
            result['verdict'] = 'double_count_confirmed'
            result['implied_qty'] = implied
            result['evidence'] = f'import_hash 反解出写入日 {hash_date} <= 快照日'
            return result
        result['verdict'] = 'needs_review'
        result['evidence'] = f'反解写入日 {hash_date}，但差额非正({implied})'
        return result

    if hash_date == pos.snapshot_date:
        result['verdict'] = 'safe'
        result['implied_qty'] = base
        result['evidence'] = 'import_hash 反解出写入日 == 快照日'
        return result

    ratio = base / pre_net
    if abs(ratio - 2.0) <= _RATIO_TOLERANCE:
        result['verdict'] = 'double_count_likely'
        result['implied_qty'] = base - pre_net
        result['evidence'] = f'份额/快照前流水 = {ratio:.4f}（疑似 2 倍）'
        return result

    result['verdict'] = 'needs_review'
    result['evidence'] = f'份额/快照前流水 = {ratio:.4f}，无法判定'
    return result


def _implied_avg_price(pos, txns, implied_qty: int) -> int:
    """反推快照成本均价（返回 price_unit，即 0.0001 元）。

    当前 `avg_price` 是加权结果：`(S×P_s + F×P_f) / (S+F)`。
    已知 S（implied_qty）、F（快照前买入份额）、P_f（快照前买入加权价），可解出：

        P_s = (avg × 当前份额 − F × P_f) / S

    **量纲必须统一在「分」上**：`Money.multiply_price_quantity` 的返回值是分，
    而 `avg_price × quantity` 是「price_unit × min_unit」(1e-8 元)，两者相差 1e6。
    早期版本直接相减，快照成本被抹成 0，均价退化成 `avg × 当前份额 / S`
    （012708 实测 1.3234 → 2.6468，凭空翻倍）。

    解出非正值（数据异常）时退回当前均价——宁可成本略偏，也不要写一个负价。
    """
    # 同 `analyse_position`：日期一律走 `_txn_effective_date`，不再单独看 confirm_date
    pre_buys = []
    for t in txns:
        d = _txn_effective_date(t)
        if d is not None and d <= pos.snapshot_date and t.txn_type in ('buy', 'deposit'):
            pre_buys.append(t)
    pre_qty = sum(t.quantity or 0 for t in pre_buys)
    if pre_qty <= 0 or implied_qty <= 0 or not pos.avg_price:
        return pos.avg_price or 0
    pre_cost_cents = sum(Money.multiply_price_quantity(t.price or 0, t.quantity or 0) for t in pre_buys)
    total_cost_cents = Money.multiply_price_quantity(pos.avg_price or 0, pos.quantity or 0)
    implied_cost_cents = total_cost_cents - pre_cost_cents
    if implied_cost_cents <= 0:
        return pos.avg_price or 0
    # 与 `_derive_state_from_txns` 保持同一套换算，避免第二份成本口径
    avg_yuan = Money.cents_to_yuan(implied_cost_cents) / Money.min_unit_to_shares(implied_qty)
    return Money.yuan_to_price_units(round(avg_yuan, 4))


def apply_fix(db, pos, item: dict) -> None:
    """写入锚点并重算份额。"""
    from app.domains.transactions.models import Transaction
    from app.services.position_service import PositionService

    txns = (
        db.query(Transaction)
        .filter(Transaction.position_id == pos.id)
        .order_by(Transaction.trade_date, Transaction.id)
        .all()
    )
    implied = int(item['implied_qty'])
    pos.snapshot_quantity = implied
    pos.snapshot_avg_price = _implied_avg_price(pos, txns, implied)
    pos.snapshot_date = pos.snapshot_date or date.today()
    pos.anchor_kind = AnchorKind.EXTERNAL.value
    db.flush()
    PositionService.recompute_position_from_transactions(db, pos.id)
    db.flush()


def apply_freeze(db, pos, item: dict) -> None:
    """把「当前份额」固化为锚点，**不改变 quantity**。

    用途：给「有快照日、无锚点」的行补上保护。这些行当前值是对的，但
    `compute_anchored_state` 在无锚点时退回全量流水口径，而
    `recompute_position_from_transactions` 在流水为空时**直接删行**——
    实测 105 行里 79 行完全没有流水，任何一次重算都会让持仓整行消失；
    剩下 26 行会被打回全量流水净额（023887：29,551 → 17,086，差 42%）。

    成本口径与 `apply_fix` 不同：这里**不反解**快照成本，直接用当前 `avg_price`。
    理由：本函数的语义是「当前值是权威的，原样冻结」，当前均价本就对应当前份额；
    再走一遍反解会把不属于重复累加的成本减掉（那是 `apply_fix` 的差事）。
    """
    from app.services.position_service import PositionService

    # 锚点 = 当前值 − 快照后流水（快照后流水是合法增量，不属于锚点）
    implied = int(item['implied_qty'])
    pos.snapshot_quantity = implied
    pos.snapshot_avg_price = pos.avg_price or 0
    pos.snapshot_date = pos.snapshot_date or date.today()
    pos.anchor_kind = AnchorKind.EXTERNAL.value
    db.flush()
    # 锚点 == 当前份额时重算没有任何信息增量，只会在 0.0001 元精度上把成本价
    # 舍入一遍（实测 55 行被动了 ±1 个最小单位）。这类纯噪声不该出现在迁移里。
    if implied != pos.quantity:
        PositionService.recompute_position_from_transactions(db, pos.id)
        db.flush()


def _fmt_qty(units) -> str:
    return f'{Money.min_unit_to_shares(units or 0):,.2f}'


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='扫描/修复持仓份额被快照与流水重复累加的行')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--report', action='store_true', help='只读扫描并输出报告（默认）')
    group.add_argument('--apply', action='store_true', help='写入确证的行（需配合 --confirm）')
    parser.add_argument('--confirm', action='store_true', help='确认执行写库')
    parser.add_argument('--include-likely', action='store_true', help='连同「疑似」行一起写入')
    parser.add_argument(
        '--freeze',
        action='store_true',
        help='把当前份额固化为锚点（不改变 quantity）：给「有快照日、无锚点」的行补保护，'
        '防止后续 recompute 删行或打回全量流水口径',
    )
    parser.add_argument('--family', type=int, default=None, help='限定家庭 ID')
    parser.add_argument('--ledger', type=int, default=None, help='限定账户 ID')
    parser.add_argument('--position', type=int, default=None, help='限定持仓行 ID（只写这一行）')
    args = parser.parse_args(argv)

    if args.apply and not args.confirm:
        print('拒绝执行：--apply 必须同时给 --confirm（先跑 --report 看结果）')
        return 2

    # 域模型必须先于 init_db 全量导入：跨模块外键（positions → ledgers/portfolios、
    # position_import_meta → ledgers）缺一张表就会 NoReferencedTableError。
    # 与 app/tools/sync_metadata.py 的初始化顺序保持一致。
    import app.domains.assets.models  # noqa: F401
    import app.domains.families.models  # noqa: F401
    import app.domains.funds.models  # noqa: F401
    import app.domains.indices.models  # noqa: F401
    import app.domains.ledgers.models  # noqa: F401
    import app.domains.market.models  # noqa: F401
    import app.domains.portfolios.models  # noqa: F401
    import app.domains.positions.models  # noqa: F401
    import app.domains.price_history.models  # noqa: F401
    import app.domains.securities.models  # noqa: F401
    import app.domains.strategy.models  # noqa: F401
    import app.domains.summary.models  # noqa: F401
    import app.domains.transactions.models  # noqa: F401
    import app.domains.users.models  # noqa: F401
    import app.domains.watchlist.models  # noqa: F401
    import app.models.sync_log  # noqa: F401
    from app.core.database import get_db, init_db
    from app.domains.positions.models import Position

    init_db()

    with get_db() as db:
        query = db.query(Position)
        if args.family is not None:
            query = query.filter(Position.family_id == args.family)
        if args.ledger is not None:
            query = query.filter(Position.ledger_id == args.ledger)
        if args.position is not None:
            query = query.filter(Position.id == args.position)
        positions = query.all()

        items = [analyse_position(db, p) for p in positions]
        # 报告只展示「有判断价值」的行，避免刷屏
        interesting = [i for i in items if i['verdict'] != 'skipped']

        if not interesting:
            print('没有需要处理的持仓（全部已带锚点，或无快照日）。')
            return 0

        header = f'{"ID":<6}{"ledger":<7}{"symbol":<10}{"snapshot":<12}{"current":>14}{"pre_flow":>14}{"implied":>14}  verdict'
        print(header)
        print('-' * len(header))
        for i in interesting:
            print(
                f'{i["position_id"]:<6}{str(i["ledger_id"]):<7}{i["symbol"]:<10}'
                f'{str(i["snapshot_date"]):<12}{_fmt_qty(i["current_qty"]):>14}'
                f'{_fmt_qty(i["pre_flow_net"]):>14}{_fmt_qty(i["implied_qty"]):>14}  {i["verdict"]}'
            )

        print('\n判定依据：')
        for i in interesting:
            print(f'  · {i["symbol"]}: {i["evidence"]}')

        counts = {}
        for i in interesting:
            counts[i['verdict']] = counts.get(i['verdict'], 0) + 1
        print(f'\n汇总: {counts}')

        if not args.apply:
            print('\n（只读模式。确认无误后加 --apply --confirm 写入）')
            print('  补锚点保护（不改份额）：--apply --confirm --freeze')
            return 0

        writable = {'safe', 'double_count_confirmed'}
        if args.include_likely:
            writable.add('double_count_likely')
        if args.freeze:
            # freeze 的语义是「当前值权威、原样冻结」，故写的是被反证排除重复累加的行；
            # 它不给 needs_review 开口子——那些行连当前值都不可信。
            writable = {'safe', 'no_double_count'}

        applied, skipped = 0, 0
        by_id = {p.id: p for p in positions}
        for i in interesting:
            if i['verdict'] not in writable or not i['implied_qty'] or i['implied_qty'] <= 0:
                skipped += 1
                continue
            if args.freeze and (i.get('post_flow_net') or 0) != 0:
                # 有快照后流水时「当前值 − post」反推出的锚点不可信：当前值可能压根
                # 没把该笔流水算进去（实测 012345 就是这样——快照 5,000 份，之后一笔
                # 卖出 5,000 未被扣减，反推得到 10,000 份）。这类行交给人工，不自动冻。
                print(
                    f'  ! 跳过 {i["symbol"]}（id={i["position_id"]}）：快照后流水净额 '
                    f'{_fmt_qty(i["post_flow_net"])} ≠ 0，锚点无法反推'
                )
                skipped += 1
                continue
            if args.freeze:
                apply_freeze(db, by_id[i['position_id']], i)
            else:
                apply_fix(db, by_id[i['position_id']], i)
            applied += 1
        db.commit()
        print(f'\n已写入 {applied} 行，跳过 {skipped} 行。')
        return 0


if __name__ == '__main__':
    sys.exit(main())
