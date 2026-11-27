# -*- coding: utf-8 -*-
"""清仓周期账户回填（analytics/cleared_cycle_ledgers.py）测试。

覆盖三件事：
1. 同名账户去重（两个都叫「华泰证券」不该显示成 +1）；
2. 空周期 / 无 id 不查库、不崩；
3. 名称查询限定家庭——ledger 归属别家时回填空列表，而不是把别家的账户名带出来。
"""

from app.domains.ledgers.models import Ledger
from app.services.analytics.cleared_cycle_ledgers import _distinct, attach_ledger_names


def _cycle(ledger_ids=None):
    """最小周期 dict：回填只读写 `ledger_ids`，其余字段无关。"""
    return {'symbol': '110022', 'ledger_ids': list(ledger_ids or [])}


class TestDistinct:
    def test_keeps_order_and_drops_duplicates(self):
        assert _distinct(['账户B', '账户A', '账户B']) == ['账户B', '账户A']

    def test_drops_empty_names(self):
        assert _distinct([None, '', '账户A']) == ['账户A']


class TestAttachLedgerNames:
    def test_no_cycles_is_noop(self, db):
        """空列表不查库：接口在无清仓周期时不该多一次 ledgers 查询。"""
        attach_ledger_names(db, [], family_id=1)

    def test_empty_ledger_ids_yields_empty_list(self, db):
        """没有流水的周期（理论不会出现）也不崩：pop 缺失键走默认空。"""
        cycles = [{'symbol': '110022'}]
        attach_ledger_names(db, cycles, family_id=1)
        assert cycles[0]['ledger_names'] == []

    def test_names_resolved_and_ids_dropped(self, db):
        ledger = Ledger(name='华泰证券', ledger_type='stock', family_id=1)
        db.add(ledger)
        db.commit()
        cycles = [_cycle([ledger.id])]
        attach_ledger_names(db, cycles, family_id=1)
        assert cycles[0]['ledger_names'] == ['华泰证券']
        assert 'ledger_ids' not in cycles[0]

    def test_other_family_ledger_not_exposed(self, db):
        """跨家庭 id 不解析：拿到别家 id 也不该把别家账户名带出来。"""
        other = Ledger(name='别家账户', ledger_type='stock', family_id=2)
        db.add(other)
        db.commit()
        cycles = [_cycle([other.id])]
        attach_ledger_names(db, cycles, family_id=1)
        assert cycles[0]['ledger_names'] == []
