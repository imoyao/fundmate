# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/1
# File : test_manual_holding_confirm.py
"""导入页「手动录入」分段的确认路径（#1788）。

前端手动分段把预览行 POST 到 `/api/importers/holdings/confirm/`，与文件 / AI 两条分段
共用 `commit_holdings → PositionService.upsert_from_holding` 汇点，只是 `source='manual'`
（文件是 `e_account_holding`、AI 是 `ai_holding`）。

本文件钉住该路径的硬契约：

- 落 `positions`——首次新增、二次 SET 语义更新，均不产生重复行；
- **`transactions` 零新增**：手动录的是「某日的持仓结果快照」，不是「交易过程」。
  误建流水会污染情绪 / 五维 / 雷达分析，这与 #1018 修的是同一族隐患
  （AI 持仓截图误经交易管线建流水）；
- 溯源 `source='manual'`，使这批持仓在对账工作台与文件导入可区分。
"""

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction

CONFIRM_URL = '/api/importers/holdings/confirm/'
LEDGER_NAME = '手动录入测试账户'


def _make_ledger(db) -> int:
    """建一个基金账户并返回 id。

    手动录入要求用户先选定归属账户（面板级选择），故测试也要有一个真实账户。
    末尾 `db.commit()` 不可省：它同时结束本会话事务，POST 之后本会话新开事务才能
    看到接口侧的提交（SQLite 读事务持有快照，跨提交读会拿到旧镜像）。
    """
    ledger = db.query(Ledger).filter_by(name=LEDGER_NAME, family_id=1).first()
    if ledger is None:
        ledger = Ledger(name=LEDGER_NAME, ledger_type='fund', family_id=1)
        db.add(ledger)
    db.commit()
    return ledger.id


def _counts(db) -> tuple[int, int]:
    """读 positions / transactions 行数。

    先 `commit()` 是必须的：若本会话还挂着 POST 之前的读事务，查出来的就是提交前的
    快照，「零新增流水」的断言会基于错误基线得出结论。
    """
    db.commit()
    return db.query(Position).count(), db.query(Transaction).count()


def _manual_row(symbol: str, name: str, ledger_id: int, quantity: float, price: float) -> dict:
    """与前端 `useEaccountImport.generateManualPreview()` 产出的 `OcrHoldingRow` 同构。

    `import_hash` 留空：由后端按 (source, ledger_id, symbol, snapshot_date) 补算，
    前端既算不了也不该重复实现该算法。
    """
    return {
        'symbol': symbol,
        'name': name,
        'type': 'fund',
        'quantity': quantity,
        'price': price,
        'amount': round(quantity * price, 2),  # 派生市值，与前端只读列口径一致
        'snapshot_date': '2026-09-30',
        'account_name': LEDGER_NAME,
        'ledger_id': ledger_id,
        'source': 'manual',
        'import_hash': '',
    }


def test_manual_confirm_adds_positions_without_transactions(client, db):
    """首次录入：新增两条持仓，transactions 零新增，source 溯源为 manual。"""
    ledger_id = _make_ledger(db)
    pos_before, txn_before = _counts(db)
    assert (pos_before, txn_before) == (0, 0)

    rows = [
        _manual_row('110011', '易方达中小盘', ledger_id, 4526.51, 1.1024),
        _manual_row('003095', '易方达中证海外中国互联50A', ledger_id, 1200.0, 2.5),
    ]

    resp = client.post(CONFIRM_URL, json=rows)
    assert resp.status_code == 200

    payload = resp.get_json()
    assert payload['message'] == 'ok'
    result = payload['data']
    assert result['imported'] == 2
    assert result['errors'] == []

    pos_after, txn_after = _counts(db)
    assert pos_after == 2
    assert txn_after == txn_before  # 核心契约：手动录持仓不建任何交易流水
    assert txn_after == 0

    by_symbol = {p.symbol: p for p in db.query(Position).all()}
    assert set(by_symbol) == {'110011', '003095'}
    for p in by_symbol.values():
        assert p.source == 'manual'
        assert p.ledger_id == ledger_id
        assert p.asset_type == 'fund'

    assert by_symbol['110011'].quantity == Money.shares_to_min_unit(4526.51)
    assert by_symbol['110011'].avg_price == Money.yuan_to_price_units(1.1024)


def test_manual_confirm_updates_position_without_new_row_or_transaction(client, db, make_position):
    """再次录入同 (账户, 代码)：SET 语义更新既有行，既不增行也不建流水。"""
    seed = make_position(
        symbol='110011',
        name='易方达中小盘',
        account_name=LEDGER_NAME,
        quantity=1000,
        avg_price=1.0,
        current_price=1.0,
    )
    ledger_id = seed.ledger_id
    seed_symbol = seed.symbol

    pos_before, txn_before = _counts(db)
    assert pos_before == 1

    resp = client.post(
        CONFIRM_URL,
        json=[_manual_row(seed_symbol, '易方达中小盘', ledger_id, 2000.0, 3.5)],
    )
    assert resp.status_code == 200
    assert resp.get_json()['data']['imported'] == 1

    pos_after, txn_after = _counts(db)
    assert pos_after == 1  # 更新而非新增：唯一约束 (ledger_id, symbol) 挡住第二行
    assert txn_after == txn_before  # 更新同样不产生交易流水

    updated = db.query(Position).filter_by(symbol=seed_symbol).first()
    assert updated is not None
    assert updated.quantity == Money.shares_to_min_unit(2000.0)
    assert updated.avg_price == Money.yuan_to_price_units(3.5)
    assert updated.source == 'manual'
