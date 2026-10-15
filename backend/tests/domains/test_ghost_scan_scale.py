# -*- coding: utf-8 -*-
"""#2151：扫描分组退回 Python 后的成本探针（**不是性能门禁**，是量级记录）。

WHY 单独一个文件：这次为「身份归一必须发生在分组之前」把 SQL 聚合退回了 Python 分组，
而该改动**部分回退了 B4 的优化**。回退要有代价的数字，否则下一个人只看到注释里的
「有意的取舍」，无从判断它是否已经失控。故用一个**宽松阈值**（真实量级下 < 2s）
把量级钉住：若某天它退化成分钟级，这条会红。
"""

from datetime import date

import pytest

from app.domains.ledgers.models import Ledger
from app.domains.summary.views import scan_cross_ledger_duplicates
from app.domains.transactions.models import Transaction

#: 宽松阈值（秒）。真实家庭量级远低于 2 万笔；这里取「远超真实量级」仍应秒级完成。
#: 不设更紧的阈值：CI 机器性能波动大，紧阈值会制造假红，而假红会让人顺手放宽它。
_BUDGET_SECONDS = 5.0


@pytest.mark.slow
def test_scan_scale_is_seconds_not_minutes(db):
    """2 万笔流水（远超真实家庭量级）的扫描应在秒级完成。"""
    import time

    for i in range(5):
        db.add(Ledger(name=f'L{i}', ledger_type='stock', family_id=1))
    db.flush()
    rows = []
    for i in range(20000):
        rows.append(
            Transaction(
                ledger_id=1 + (i % 5),
                family_id=1,
                # ⚠️ 造数有两条互质要求，否则**一个重复组都造不出来**（本用例首版踩了两轮）：
                #   ① 步长与池大小互质（7 与 301）—— 否则 symbol 只在池内一个子群打转；
                #   ② **池大小与账本数互质**（301 与 5）—— 否则 `(i*7) % 池` 与 `i % 账本数`
                #      仍会锁步（300 能被 5 整除时即如此），同一 symbol 永远落在同一账本。
                # 下面那句 `assert groups` 就是为防这类「判据空转」而写的，不是装饰。
                symbol=f'{(i * 7) % 301:06d}',
                asset_type='stock',
                txn_type='buy',
                quantity=100,
                price=100000,
                amount=100000,
                confirm_date=date(2026, 8, 1),
                status='success',
                import_hash=f'h{i}',
            )
        )
    db.add_all(rows)
    db.commit()

    started = time.time()
    groups = scan_cross_ledger_duplicates(db, 1)
    elapsed = time.time() - started
    assert groups, '2 万笔同内容流水必然检出重复组（判据非空转的自证）'
    assert elapsed < _BUDGET_SECONDS, f'扫描耗时 {elapsed:.2f}s，超过预算 {_BUDGET_SECONDS}s'
