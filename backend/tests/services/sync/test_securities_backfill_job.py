# -*- coding: utf-8 -*-
"""名录定向补录 job（离线，用假 adapter，不真联网）。

覆盖：补上的写进 securities、查不到的进 stats['failed'] 并保留缺口、
缺口为空时正常结束、已存在的记录走 upsert 更新而不是重复插入。
"""

from app.domains.securities.models import Security
from app.services.sync.jobs.securities_backfill_job import SecuritiesBackfillJob


class _FakeLookupAdapter:
    """假数据源：按 symbol 回放固定记录，其余视为「查不到」。"""

    def __init__(self, mapping):
        self.mapping = mapping
        self.asked = []

    def get_name(self):
        return 'fake_lookup'

    def get_version(self):
        return 'fake-v1'

    def fetch_security_by_symbol(self, symbol):
        self.asked.append(symbol)
        return self.mapping.get(symbol)


def _make_job(db, mapping):
    return SecuritiesBackfillJob(_FakeLookupAdapter(mapping), db)


class TestBackfillJob:
    def test_name(self, db):
        assert _make_job(db, {}).get_name() == 'securities_backfill'

    def test_writes_found_symbols(self, db):
        job = _make_job(
            db,
            {
                'SH600519': {
                    'symbol': 'SH600519',
                    'name': '贵州茅台',
                    'market': 'CN_A',
                    'type': 'stock',
                    'currency': 'CNY',
                }
            },
        )

        job.run(full_sync=False, targets=['SH600519', 'SH999999'])

        assert db.query(Security).filter_by(symbol='SH600519').count() == 1
        # 查不到的不写库
        assert db.query(Security).filter_by(symbol='SH999999').count() == 0

    def test_unresolved_kept_visible_as_failed(self, db):
        """补上的 1 个 + 查不到的 1 个：分母必须是 2，不能显示成 1/1 全成功。"""
        job = _make_job(
            db,
            {
                'SH600519': {
                    'symbol': 'SH600519',
                    'name': '贵州茅台',
                    'market': 'CN_A',
                    'type': 'stock',
                    'currency': 'CNY',
                }
            },
        )

        result = job.run(full_sync=False, targets=['SH600519', 'SH999999'])

        stats = result['stats']
        assert stats['total'] == 2
        assert stats['success'] == 1
        assert stats['failed'] == 1
        assert stats['errors'][0]['symbol'] == 'SH999999'

    def test_empty_targets_is_not_an_error(self, db):
        """缺口为空是正常态（名录已齐），不是故障。"""
        job = _make_job(db, {})
        result = job.run(full_sync=False, targets=[])
        assert result['stats']['success'] == 0

    def test_existing_record_updated_not_duplicated(self, db):
        """upsert 语义（继承自 StockListSyncJob）：名称/品类变化要更新，不能插第二行。"""
        db.add(Security(symbol='SH600519', name='旧名', market='CN_A', type='stock'))
        db.commit()

        job = _make_job(
            db,
            {
                'SH600519': {
                    'symbol': 'SH600519',
                    'name': '贵州茅台',
                    'market': 'CN_A',
                    'type': 'etf',  # 故意改成 etf，验证 type 也会被纠正
                    'currency': 'CNY',
                }
            },
        )
        job.run(full_sync=False, targets=['SH600519'])

        rows = db.query(Security).filter_by(symbol='SH600519').all()
        assert len(rows) == 1
        assert rows[0].name == '贵州茅台'
        assert rows[0].type == 'etf'
