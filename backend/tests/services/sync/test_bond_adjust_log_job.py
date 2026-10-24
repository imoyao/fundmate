# -*- coding: utf-8 -*-
"""可转债下修历史 job / 解析器（#2585）。

解析器用例喂的是**源侧真实响应**（2026-10-24 实测洪涛转债 128013 的 3 次下修），
不是手写简化样本 —— 只有这样，「单元格数 / 表头 / 日期格式」这类结构判据才真的
被验证过（#2543 的教训：拿编造的样本测解析，源改版时一条用例都不会红）。
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domains.securities.models import ConvertibleBondAdjustLog
from app.services.adapters.jsl_bond_adjust_adapter import JslBondAdjustAdapter, parse_adjust_logs
from app.services.sync.jobs.bond_adjust_log_job import BondAdjustLogSyncJob, _bare_bond_code

#: 集思录 `GET /data/cbnew/adj_logs/?bond_id=128013` 的真实响应（2026-10-24，590 字节，UTF-8）
REAL_HTML_128013 = (
    '<table class="tablesorter" style="width:440px;"><thead><tr><th>转债名称</th>'
    '<th>股东大会日</th><th>下修前<br>转股价</th><th>下修后<br>转股价</th>'
    '<th>新转股价<br>生效日期</th><th>下修底价</th></tr></thead><tbody>'
    '<tr><td>洪涛转债</td><td>2021-02-23</td><td>3.100</td><td>2.320</td><td>2021-02-24</td><td>2.320</td></tr>'
    '<tr><td>洪涛转债</td><td>2020-06-29</td><td>8.000</td><td>3.120</td><td>2020-06-30</td><td>3.120</td></tr>'
    '<tr><td>洪涛转债</td><td>2019-11-20</td><td>9.970</td><td>8.000</td><td>2019-11-21</td><td>3.100</td></tr>'
    '</tbody></table>'
)

#: 无下修记录的唯一合法空态（12 字节，无 <table>）
EMPTY_BODY = '暂无数据'


# ── 解析器 ──


def test_parse_adjust_logs_real_sample():
    rows = parse_adjust_logs(REAL_HTML_128013)

    assert len(rows) == 3
    first = rows[0]
    assert first['name'] == '洪涛转债'
    assert first['shareholder_meeting_date'] == date(2021, 2, 23)
    assert first['convert_price_before'] == Decimal('3.100')
    assert first['convert_price_after'] == Decimal('2.320')
    assert first['effective_date'] == date(2021, 2, 24)
    assert first['adjust_floor_price'] == Decimal('2.320')

    # 底价**每次不同**（随每股净资产变化）——正是它必须跟着事件走的原因
    assert [r['adjust_floor_price'] for r in rows] == [Decimal('2.320'), Decimal('3.120'), Decimal('3.100')]
    assert [r['shareholder_meeting_date'] for r in rows] == [
        date(2021, 2, 23),
        date(2020, 6, 29),
        date(2019, 11, 20),
    ]


def test_parse_adjust_logs_empty_marker_is_empty_list():
    assert parse_adjust_logs(EMPTY_BODY) == []
    # 前后空白/换行不影响判据
    assert parse_adjust_logs('\n  暂无数据 \n') == []


@pytest.mark.parametrize(
    'body',
    [
        '',  # 空 body：上游异常，不是「无记录」
        '   ',
        '<html><body>请先登录</body></html>',  # 风控/登录页
        '{"data": []}',  # 接口形态若改成 JSON
    ],
)
def test_parse_adjust_logs_rejects_unrecognised_body(body):
    """空态**只有**「暂无数据」一种；其余一律抛错，不得降级成空列表。"""
    with pytest.raises(ValueError):
        parse_adjust_logs(body)


def test_parse_adjust_logs_rejects_wrong_header():
    """有表格但不是下修表（页面改版挂错 tab）→ 抛错。"""
    html = (
        '<table><thead><tr><th>转债名称</th><th>价格</th></tr></thead>'
        '<tbody><tr><td>洪涛转债</td><td>110.0</td></tr></tbody></table>'
    )
    with pytest.raises(ValueError, match='表头'):
        parse_adjust_logs(html)


def test_parse_adjust_logs_rejects_wrong_cell_count():
    """列数变了 → 抛错（错位解析会把日期当价格，静默写脏数据）。"""
    html = (
        '<table><thead><tr><th>股东大会日</th></tr></thead>'
        '<tbody><tr><td>洪涛转债</td><td>2021-02-23</td><td>3.100</td></tr></tbody></table>'
    )
    with pytest.raises(ValueError, match='单元格数'):
        parse_adjust_logs(html)


def test_parse_adjust_logs_rejects_bad_date():
    html = (
        '<table><thead><tr><th>股东大会日</th></tr></thead><tbody>'
        '<tr><td>洪涛转债</td><td>2021年2月23日</td><td>3.100</td><td>2.320</td>'
        '<td>2021-02-24</td><td>2.320</td></tr></tbody></table>'
    )
    with pytest.raises(ValueError, match='格式非法'):
        parse_adjust_logs(html)


def test_parse_adjust_logs_keeps_missing_prices_as_none():
    """**非唯一键**的空单元格保留为 None（不是 0，也不抛错）。

    生效日期可能尚未公布（决议已过、生效待定），把它当结构异常会让整只债抓取失败。
    """
    html = (
        '<table><thead><tr><th>股东大会日</th></tr></thead><tbody>'
        '<tr><td>洪涛转债</td><td>2021-02-23</td><td></td><td>2.320</td><td></td><td>--</td></tr>'
        '</tbody></table>'
    )
    rows = parse_adjust_logs(html)
    assert len(rows) == 1
    assert rows[0]['convert_price_before'] is None
    assert rows[0]['effective_date'] is None
    assert rows[0]['adjust_floor_price'] is None


def test_adapter_get_name():
    """数据源名与落库 `source` 列分开：前者标识适配器，后者标识来源。"""
    assert JslBondAdjustAdapter().get_name() == 'jisilu_adj_logs'


# ── job ──


class _FakeAdapter:
    """按 bond_code 返回预置的下修记录；`fail` 里的代码抛错（模拟单只失败）。"""

    def __init__(self, rows_by_code=None, fail=()):
        self.rows_by_code = rows_by_code or {}
        self.fail = set(fail)
        self.calls = []

    def fetch_adjust_logs(self, bond_code):
        self.calls.append(bond_code)
        if bond_code in self.fail:
            raise RuntimeError('HTTP 403')
        return parse_adjust_logs(self.rows_by_code.get(bond_code, EMPTY_BODY))


def _sample_rows():
    return {'128013': REAL_HTML_128013}


def test_bond_adjust_log_job_writes_rows(db):
    job = BondAdjustLogSyncJob(_FakeAdapter(_sample_rows()), db)
    result = job.run(targets=['SZ128013'])

    assert result['status'] == 'success'
    rows = db.query(ConvertibleBondAdjustLog).order_by(ConvertibleBondAdjustLog.shareholder_meeting_date).all()
    assert len(rows) == 3
    assert {r.symbol for r in rows} == {'SZ128013'}
    assert {r.bond_code for r in rows} == {'128013'}
    assert rows[0].shareholder_meeting_date == date(2019, 11, 20)
    assert rows[0].convert_price_before == Decimal('9.970')
    assert rows[0].convert_price_after == Decimal('8.000')
    assert rows[0].effective_date == date(2019, 11, 21)
    assert rows[0].adjust_floor_price == Decimal('3.100')
    assert rows[0].source == 'jisilu_adj_logs'

    stats = result['stats']
    assert stats['with_records'] == 1
    assert stats['no_records'] == 0
    assert stats['failed'] == 0
    # success 数的是**落库行数**：3 条下修事件一条都不许丢
    assert stats['success'] == 3
    # 分桶合计必须等于目标数（否则有目标被静默吃掉）
    assert stats['bucket_sum'] == stats['total'] == 1


def test_bond_adjust_log_job_idempotent(db):
    """历史事件重复抓取不长重复行，且第二轮全部计入 skipped（不是 success）。

    每轮都是**新实例**（编排器每次 run 都新建 job），故 stats 不跨轮累加。
    """
    BondAdjustLogSyncJob(_FakeAdapter(_sample_rows()), db).run(targets=['SZ128013'])
    result = BondAdjustLogSyncJob(_FakeAdapter(_sample_rows()), db).run(targets=['SZ128013'])

    assert db.query(ConvertibleBondAdjustLog).count() == 3
    assert result['stats']['success'] == 0
    assert result['stats']['skipped'] == 3


def test_bond_adjust_log_job_updates_changed_effective_date(db):
    """生效日期被公告顺延 → 覆盖旧值（不是「库里有就永久跳过」）。"""
    adapter = _FakeAdapter(_sample_rows())
    BondAdjustLogSyncJob(adapter, db).run(targets=['SZ128013'])

    # 源侧把 2021-02-23 那次的生效日顺延一天
    adapter.rows_by_code['128013'] = REAL_HTML_128013.replace('2021-02-24', '2021-02-25')
    result = BondAdjustLogSyncJob(adapter, db).run(targets=['SZ128013'])

    assert db.query(ConvertibleBondAdjustLog).count() == 3
    assert result['stats']['success'] == 1  # 只有那一行有差异
    assert result['stats']['skipped'] == 2
    row = db.query(ConvertibleBondAdjustLog).filter_by(shareholder_meeting_date=date(2021, 2, 23)).one()
    assert row.effective_date == date(2021, 2, 25)


def test_bond_adjust_log_job_skips_non_bond_targets(db):
    """目标池混着股票/ETF：跳过但不计入失败（那不是本 job 的活）。"""
    adapter = _FakeAdapter(_sample_rows())
    job = BondAdjustLogSyncJob(adapter, db)
    result = job.run(targets=['SH600519', 'SZ159915', 'SZ128013'])

    assert result['status'] == 'success'
    assert adapter.calls == ['128013']  # 只在真转债上发请求
    assert result['stats']['not_bond'] == 2
    assert result['stats']['with_records'] == 1
    assert result['stats']['failed'] == 0
    assert result['stats']['bucket_sum'] == result['stats']['total'] == 3


def test_bond_adjust_log_job_reports_empty_and_failure_separately(db):
    """「暂无数据」与「抓取失败」必须分桶上报（空 ≠ 没拿到）。"""
    adapter = _FakeAdapter(_sample_rows(), fail=('110077',))
    job = BondAdjustLogSyncJob(adapter, db)
    result = job.run(targets=['SZ128013', 'SH110077', 'SH113050'])

    stats = result['stats']
    assert stats['with_records'] == 1
    assert stats['no_records'] == 1  # 113050 源侧「暂无数据」
    assert stats['failed'] == 1  # 110077 抛错
    assert len(stats['errors']) == 1
    assert '110077' in stats['errors'][0]
    assert stats['bucket_sum'] == stats['total'] == 3


def test_bond_adjust_log_job_all_failed_is_failed(db):
    """唯一的转债目标就失败 ⇒ FAILED（不能报绿：绿了等于「这只债没下修过」）。"""
    adapter = _FakeAdapter(_sample_rows(), fail=('128013',))
    result = BondAdjustLogSyncJob(adapter, db).run(targets=['SZ128013'])
    assert result['status'] == 'failed'


def test_bond_adjust_log_job_empty_targets_is_success(db):
    """空目标池 = 显式跳过，不是故障。"""
    result = BondAdjustLogSyncJob(_FakeAdapter(_sample_rows()), db).run(targets=[])
    assert result['status'] == 'success'
    assert db.query(ConvertibleBondAdjustLog).count() == 0


# ── 目标归一 ──


@pytest.mark.parametrize(
    'raw, expected',
    [
        ('SH110077', '110077'),
        ('SZ128013', '128013'),
        ('128013', '128013'),
        ('128013.SZ', '128013'),
        ('sh128013', '128013'),
        ('SH600519', None),  # 股票
        ('SZ159915', None),  # ETF
        ('', None),
        (None, None),
    ],
)
def test_bare_bond_code(raw, expected):
    assert _bare_bond_code(raw) == expected
