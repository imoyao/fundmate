# -*- coding: utf-8 -*-
"""一次性修复：补挂回历史遗留的孤儿货基/逆回购流水（#1657）。

背景：#863 口径 A 互斥不变式（同 (ledger,symbol) 资金只能以「持仓」或「孤儿净额」之一表达）
要求货基建仓时把同 symbol 孤儿流水挂回持仓（_reattach_orphan_flows）。本机库存在 #863 合入前
已创建、或导入顺序导致持仓先于孤儿流水入库而漏挂的历史行——同一 (ledger,symbol) 既有持仓、
又有 position_id IS NULL 的货基流水，造成总资产双计。

本脚本对全库所有 is_money_fund 持仓**幂等**补挂回其同 (ledger,symbol) 孤儿流水，
复用 _reattach_orphan_flows，与写入层逻辑完全一致。

安全：默认 dry-run（仅打印待改行，rollback）；--apply 才真正写库并提交。
"""
import argparse

from app.core.database import SessionLocal
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.fund_utils import CASH_EQUIVALENT_ASSET_TYPES, normalize_fund_code
from app.services.position_service import _reattach_orphan_flows
from sqlalchemy import or_


def _count_orphans(db, position: Position) -> int:
    return (
        db.query(Transaction)
        .filter(
            Transaction.ledger_id == position.ledger_id,
            Transaction.position_id.is_(None),
            Transaction.family_id == position.family_id,
            Transaction.asset_type.in_(CASH_EQUIVALENT_ASSET_TYPES),
            or_(Transaction.is_income.is_(None), Transaction.is_income.is_(False)),
            Transaction.symbol == position.symbol,
        )
        .count()
    )


def main():
    ap = argparse.ArgumentParser(description='补挂回历史孤儿货基流水（#1657）')
    ap.add_argument('--apply', action='store_true', help='真正写库（默认仅 dry-run 打印）')
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # 取所有孤儿货基/逆回购流水（position_id IS NULL、非收益），反向找同 (ledger,symbol) 持仓。
        # 注意：不能用 is_money_fund 过滤持仓——本机存在 is_money_fund 判定不一致的货基持仓
        # （pos[445]/pos[26] 为货基但 is_money_fund=0），会漏挂回；故从流水侧反查。
        orphans = (
            db.query(Transaction)
            .filter(
                Transaction.position_id.is_(None),
                Transaction.asset_type.in_(CASH_EQUIVALENT_ASSET_TYPES),
                or_(Transaction.is_income.is_(None), Transaction.is_income.is_(False)),
            )
            .all()
        )
        keys = {(t.ledger_id, t.symbol, t.family_id) for t in orphans}
        affected = []
        for lid, sym, fid in keys:
            pos = (
                db.query(Position)
                .filter(Position.ledger_id == lid, Position.family_id == fid, Position.symbol == sym)
                .first()
            )
            if pos is None:
                continue
            before = _count_orphans(db, pos)
            if before == 0:
                continue
            _reattach_orphan_flows(db, lid, sym, pos.id, fid)
            affected.append((pos.id, lid, sym, before))

        if args.apply:
            db.commit()
            print(f'[apply] 已补挂回，涉及 {len(affected)} 个 (ledger,symbol)')
        else:
            db.rollback()
            print('[dry-run] 未改动数据库，以下为将补挂回的目标：')
        for pid, lid, sym, n in affected:
            print(f'  pos_id={pid} ledger={lid} symbol={sym} orphan_flows={n}')
        if not affected:
            print('  无遗留孤儿货基流水，数据库已干净。')
    finally:
        db.close()


if __name__ == '__main__':
    main()
