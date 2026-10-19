# -*- coding: utf-8 -*-
"""`account_name` 冗余快照的不变式：`ledger_id` 有值 ⇒ `account_name` 由 ledger 补齐。

## 为什么要这条守门

2026-10-18 实测：基金转换「转入腿」只传了 `ledger_id`、漏传 `account_name`，
`positions.account_name` 与对应流水一起落成 NULL（position 618 / transaction 3001）。
一旦它成为「按账户分组」的字典键，`flask.jsonify(sort_keys=True)` 在比较 `str` 与
`None` 时抛 `TypeError`，整个持仓列表 500。

根因不是排序，而是数据违反了「有账户就该有账户名」。真正的账户标识是 `ledger_id`，
`account_name` 只是它的冗余快照（改名由 `sync_account_name_snapshots` 级联刷新）。
本文件钉住模型层 mapper 事件兜底后的四条语义。
"""

from sqlalchemy import text

from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position


def _make_ledger(db, name):
    ledger = Ledger(name=name, ledger_type='fund', family_id=1)
    db.add(ledger)
    db.commit()
    return ledger


def _make_position(db, **kwargs):
    defaults = {
        'symbol': '519771',
        'name': '测试基金',
        'asset_type': 'fund',
        'family_id': 1,
        'quantity': 100,
        'source': 'manual',
    }
    defaults.update(kwargs)
    position = Position(**defaults)
    db.add(position)
    db.commit()
    return position


def test_insert_fills_account_name_from_ledger(db):
    """只给 ledger_id 时，落库由 mapper 事件补出 account_name（不再落 NULL）。"""
    ledger = _make_ledger(db, '浙江同花顺基金销售')

    position = _make_position(db, ledger_id=ledger.id)

    db.refresh(position)
    assert position.account_name == '浙江同花顺基金销售'


def test_update_heals_existing_empty_account_name(db):
    """存量空值行被再次写入时自愈（事件同时挂在 before_update）。

    模拟修复前的历史行：绕过 ORM 直接写回 NULL，再触发一次普通更新。
    """
    ledger = _make_ledger(db, '自愈账户')
    position = _make_position(db, ledger_id=ledger.id)
    db.execute(
        text('UPDATE positions SET account_name = NULL WHERE id = :pid'),
        {'pid': position.id},
    )
    db.commit()
    db.expire_all()
    assert db.get(Position, position.id).account_name is None

    stale = db.get(Position, position.id)
    stale.notes = '触发一次更新'
    db.commit()
    db.expire_all()
    assert db.get(Position, position.id).account_name == '自愈账户'


def test_explicit_account_name_is_not_overwritten(db):
    """显式传入的名字保持原样——导入解析出的机构展示名可能与 ledger 名不同，那是有意的。"""
    ledger = _make_ledger(db, '账户本名')

    position = _make_position(db, ledger_id=ledger.id, account_name='展示名')

    db.refresh(position)
    assert position.account_name == '展示名'


def test_unassigned_position_keeps_empty_account_name(db):
    """ledger_id 为空（未归档 / 导入影子行）时无从补齐，保持 None。

    这类行确实没有账户，展示层兜底为「未指定账户」是对它们的正确处理，
    不应被 mapper 事件伪造成某个真实账户名。
    """
    position = _make_position(db, ledger_id=None)

    db.refresh(position)
    assert position.account_name is None
