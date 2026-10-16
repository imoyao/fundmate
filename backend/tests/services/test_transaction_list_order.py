# -*- coding: utf-8 -*-
"""交易流水列表排序（#2171 反馈修正）。

缺陷背景（真机实测，见 #2171 评论）：旧口径 `order_by(created_at.desc())` 里的
`created_at` 是**写入时间**不是交易时间，批量导入的历史流水会让列表退化成「导入批次顺序」:

    SZ000638 的 24 笔按 created_at 排出来是
    2023-02-03 → 2023-02-15 → 2023-02-07 → 2023-03-16 → 2023-03-13 → 2023-03-20

同一批 `created_at` 挤在毫秒内、并列区间顺序未定义，用户在详情页看到的就是这个顺序
（表现为「按时间正序」）。

现口径：**有效交易日倒序 + id 倒序兜底**，有效交易日 = `trade_date` 优先、`confirm_date`
兜底 —— 与展示层 `components/TransactionTable.formatDate` 同源（排序键必须与屏上印的
那个日期一致），也让翻页有确定顺序。
"""

from datetime import date, datetime

from app.services.transaction_service import build_transaction_list

# 同一批导入的行会共享 created_at（旧口径下并列区间顺序未定义，正是乱序的来源）
BATCH_CREATED_AT = datetime(2026, 8, 29, 16, 59, 44)


def _list(db, **filters):
    payload = build_transaction_list(db, family_id=1, page=1, per_page=50, filters=filters)
    return payload['data']


def test_orders_by_trade_date_desc_not_insert_order(db, make_position, make_transaction):
    """按**交易日期**倒序 —— 不是按写入顺序（旧口径的回归锚点）。

    三笔按**升序插入**且 `created_at` 完全相同（模拟一次批量导入历史流水）。
    旧实现会原样吐出插入顺序（看起来就是正序），新实现必须给出日期倒序。
    """
    pos = make_position(symbol='SZ000638', quantity=100, avg_price=10, account_name='测试账户')
    for day in (date(2023, 2, 3), date(2023, 3, 16), date(2023, 2, 15)):
        make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='SZ000638',
            txn_type='buy',
            quantity=10,
            price=10,
            trade_date=datetime(day.year, day.month, day.day, 10, 0, 0),
            created_at=BATCH_CREATED_AT,
        )

    rows = _list(db, symbol='SZ000638')

    assert [r['trade_date'] for r in rows] == ['2023-03-16', '2023-02-15', '2023-02-03']


def test_null_trade_date_falls_back_to_confirm_date(db, make_position, make_transaction):
    """`trade_date` 缺失时用 `confirm_date` 定位（真机 1,921 笔里有 1,211 笔是这种）。

    只按 `trade_date` 排会把它们整批沉到列表末尾，而屏上显示的却是确认日 ——
    排序键与展示键必须同源（`TransactionTable.formatDate`：交易日优先、确认日兜底）。
    """
    pos = make_position(symbol='000891', quantity=100, avg_price=10, account_name='测试账户')
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        symbol='000891',
        txn_type='buy',
        quantity=10,
        price=10,
        trade_date=datetime(2025, 1, 10, 10, 0, 0),
        created_at=BATCH_CREATED_AT,
    )
    # 无交易日、只有确认日，且日期**晚于**上面那笔 → 它应排在前面
    make_transaction(
        position_id=pos.id,
        ledger_id=pos.ledger_id,
        symbol='000891',
        txn_type='deposit',
        quantity=10,
        price=10,
        allow_null_trade_date=True,
        confirm_date=date(2025, 6, 20),
        created_at=BATCH_CREATED_AT,
    )

    rows = _list(db, symbol='000891')

    assert [r['confirm_date'] for r in rows] == ['2025-06-20', '2025-01-10']


def test_same_day_ordered_by_id_desc(db, make_position, make_transaction):
    """同日多笔按 id 倒序 —— 给分页一个**确定**顺序。

    批量导入的行 created_at 常精确到同一微秒：旧口径在并列区间内不保证顺序，
    翻页时同一行可能重复出现、另一行被跳过。
    """
    pos = make_position(symbol='SH600383', quantity=100, avg_price=10, account_name='测试账户')
    ids = []
    for _ in range(3):
        txn = make_transaction(
            position_id=pos.id,
            ledger_id=pos.ledger_id,
            symbol='SH600383',
            txn_type='buy',
            quantity=10,
            price=10,
            trade_date=datetime(2026, 4, 3, 10, 0, 0),
            created_at=BATCH_CREATED_AT,
        )
        ids.append(txn.id)

    rows = _list(db, symbol='SH600383')

    assert [r['id'] for r in rows] == sorted(ids, reverse=True)
