# -*- coding: utf-8 -*-
"""#2141 场外基金收盘估值定格 job 测试。

锁定四件事：
1. 校验语义——GSZ 缺失 / PDATE 非法 / 未来日期一律不写行；
2. REPLACE 幂等——同一 (fund_code, est_date) 多时点覆盖，行数不变、值更新；
3. 场内排除——ETF/股票/转债不入表，QDII 等场外基金保留；
4. 空池跳过——targets 为空时不触发 HTTP，整 job 成功。
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.domains.funds.models import FundValuationDaily
from app.services.sync.jobs.fund_valuation_snapshot_job import FundValuationSnapshotJob


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def _gsz_item(code, gsz='1.2345', gztime='2026-10-13 15:00', pdate='2026-10-13', gszzl='0.56'):
    return {
        'FCODE': code,
        'GSZ': gsz,
        'GZTIME': gztime,
        'PDATE': pdate,
        'GSZZL': gszzl,
    }


class TestFundValuationSnapshotJob:
    @pytest.fixture
    def job(self, db):
        adapter = MagicMock()
        adapter.get_name.return_value = 'mock_tiantian'
        return FundValuationSnapshotJob(adapter, db)

    # ── 校验语义 ──

    def test_validate_normal_record(self, job):
        """正常 GSZ 记录通过校验，字段映射正确"""
        raw = [_gsz_item('000001')]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        row = validated[0]
        assert row['fund_code'] == '000001'
        assert row['estimated_nav'] is not None
        assert row['source'] == 'tiantian_gsz'
        assert row['status'] == 'estimated'
        assert row['source_time'] == '2026-10-13 15:00'

    def test_validate_gsz_empty_skipped(self, job):
        """GSZ 为空字符串 → 不写行（缺行即降级信号）"""
        raw = [_gsz_item('000001', gsz=''), _gsz_item('000002', gsz=None)]
        validated = job._validate_data(raw)
        assert validated == []

    def test_validate_pdate_missing_skipped(self, job):
        """PDATE 缺失 → 不写行"""
        raw = [_gsz_item('000001', pdate='')]
        assert job._validate_data(raw) == []

    def test_validate_pdate_invalid_skipped(self, job):
        """PDATE 非法 → 不写行"""
        raw = [_gsz_item('000001', pdate='not-a-date')]
        assert job._validate_data(raw) == []

    def test_validate_future_pdate_skipped(self, job, monkeypatch):
        """未来日期 PDATE → 不写行"""
        # 固定 today 为 2026-10-13，PDATE=2026-10-14 为未来
        monkeypatch.setattr(
            'app.services.sync.jobs.fund_valuation_snapshot_job.date',
            type('D', (date,), {'today': classmethod(lambda cls: date(2026, 10, 13))}),
        )
        raw = [_gsz_item('000001', pdate='2026-10-14')]
        assert job._validate_data(raw) == []

    def test_validate_deduplicates_same_code_in_batch(self, job):
        """同一批次内同一 code 出现两次 → 只保留第一条"""
        raw = [_gsz_item('000001', gsz='1.0'), _gsz_item('000001', gsz='1.1')]
        validated = job._validate_data(raw)
        assert len(validated) == 1
        assert validated[0]['estimated_nav'] is not None

    # ── REPLACE 幂等 ──

    def test_replace_idempotent(self, job, db):
        """同一 (fund_code, est_date) 跑两遍 → 行数不变、值更新"""
        today = date(2026, 10, 13)
        raw1 = [_gsz_item('000001', gsz='1.2000', pdate='2026-10-13')]
        raw2 = [_gsz_item('000001', gsz='1.2500', pdate='2026-10-13')]

        v1 = job._validate_data(raw1)
        job._save_data(v1)
        db.commit()

        v2 = job._validate_data(raw2)
        job._save_data(v2)
        db.commit()

        rows = db.query(FundValuationDaily).filter(FundValuationDaily.est_date == today).all()
        assert len(rows) == 1, f'应恰好 1 行，实际 {len(rows)}'
        assert float(rows[0].estimated_nav) == 1.2500, '后写入的时点应覆盖先写入的'

    # ── 空池跳过 ──

    def test_empty_targets_skips_without_http(self, job):
        """targets 为空 → 不触发 HTTP，整 job 成功"""
        with patch('app.services.sync.jobs.fund_valuation_snapshot_job.requests.get') as mock_get:
            result = job.run(full_sync=False, targets=[])
        assert result['status'] == 'success'
        mock_get.assert_not_called()

    # ── 场内排除 ──

    def test_filter_otc_excludes_exchange_securities(self, job, db, make_position):
        """场内 ETF/股票 → 排除；场外基金 → 保留"""
        # 场内股票（asset_type='stock' → EXCHANGE）
        make_position(
            symbol='600000', name='场内股票', quantity=100, avg_price=10.0, asset_type='stock', account_name='证券账户'
        )
        # 场外基金（asset_type='fund' → OTC）
        make_position(
            symbol='000001', name='场外基金', quantity=1000, avg_price=1.0, asset_type='fund', account_name='基金账户'
        )

        result = job._filter_otc_funds(['600000', '000001'])
        assert '000001' in result, '场外基金应保留'
        assert '600000' not in result, '场内股票应排除'

    # ── 端到端（mock HTTP） ──

    def test_run_integration_mock_http(self, job, db):
        """端到端：mock HTTP 响应 → 正确落库"""
        payload = {
            'data': [
                _gsz_item('000001', gsz='1.2345', pdate='2026-10-13'),
                _gsz_item('000002', gsz='2.0000', pdate='2026-10-13'),
                # GSZ 缺失：不应写行
                _gsz_item('000003', gsz='', pdate='2026-10-13'),
            ]
        }
        with patch(
            'app.services.sync.jobs.fund_valuation_snapshot_job.requests.get',
            return_value=_mock_response(payload),
        ):
            result = job.run(full_sync=False, targets=['000001', '000002', '000003'])
        assert result['status'] == 'success'

        rows = db.query(FundValuationDaily).all()
        assert len(rows) == 2, f'GSZ 缺失的 000003 不应写行；实际 {len(rows)} 行'
        codes = {r.fund_code for r in rows}
        assert codes == {'000001', '000002'}
