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

#: `bond_id=110060`（2026-10-26 全市场实测原样）：**已生效行 + 合并行同表**。
#: 这是首版解析器「整响应抛错」导致成功记录被一起丢掉的真实样本。
REAL_HTML_110060 = (
    '<table class="tablesorter" style="width:440px;"><thead><tr><th>转债名称</th>'
    '<th>股东大会日</th><th>下修前<br>转股价</th><th>下修后<br>转股价</th>'
    '<th>新转股价<br>生效日期</th><th>下修底价</th></tr></thead><tbody>'
    '<tr><td>天路转债</td><td>2022-08-12</td><td>6.990</td><td>5.420</td><td>2022-08-16</td><td>5.420</td></tr>'
    '<tr><td>天路转债</td><td>2022-05-31</td><td colspan="4" style="text-align:center">股东大会未通过</td></tr>'
    '</tbody></table>'
)

#: `bond_id=110095`（2026-10-26 实测原样）：**未生效预估行 + 已生效行同表**。
#: 预估行的下修后转股价与底价带灰色斜体，生效日是 `-`（股东大会日在未来）。
REAL_HTML_110095 = (
    '<table class="tablesorter" style="width:440px;"><thead><tr><th>转债名称</th>'
    '<th>股东大会日</th><th>下修前<br>转股价</th><th>下修后<br>转股价</th>'
    '<th>新转股价<br>生效日期</th><th>下修底价</th></tr></thead><tbody>'
    '<tr><td>双良转债</td><td>2026-11-10</td><td>6.180</td>'
    '<td style="color:#999;font-style:italic;">3.96</td><td>-</td>'
    '<td style="color:#999;font-style:italic;">3.96</td></tr>'
    '<tr><td>双良转债</td><td>2025-03-25</td><td>7.200</td><td>6.180</td><td>2025-03-27</td><td>5.950</td></tr>'
    '<tr><td>双良转债</td><td>2024-10-25</td><td>11.810</td><td>7.200</td><td>2024-10-29</td><td>4.510</td></tr>'
    '</tbody></table>'
)

#: `bond_id=123099`（2026-10-26 实测原样）：1 条合并行（均退市）+ 5 条已生效。
#: 首版会因合并行抛错，把这 5 条真实下修全部丢掉。
REAL_HTML_123099 = (
    '<table class="tablesorter" style="width:440px;"><thead><tr><th>转债名称</th>'
    '<th>股东大会日</th><th>下修前<br>转股价</th><th>下修后<br>转股价</th>'
    '<th>新转股价<br>生效日期</th><th>下修底价</th></tr></thead><tbody>'
    '<tr><td>普利转退</td><td>2025-05-22</td><td colspan="4" style="text-align:center">正股转债均退市</td></tr>'
    '<tr><td>普利转债</td><td>2025-03-10</td><td>4.890</td><td>3.000</td><td>2025-03-11</td><td>3.000</td></tr>'
    '<tr><td>普利转债</td><td>2025-01-22</td><td>11.220</td><td>4.890</td><td>2025-01-23</td><td>4.890</td></tr>'
    '<tr><td>普利转债</td><td>2024-11-19</td><td>19.760</td><td>11.220</td><td>2024-11-20</td><td>11.220</td></tr>'
    '<tr><td>普利转债</td><td>2023-06-02</td><td>27.100</td><td>19.850</td><td>2023-06-05</td><td>19.840</td></tr>'
    '<tr><td>普利转债</td><td>2022-12-26</td><td>45.870</td><td>27.100</td><td>2022-12-27</td><td>27.090</td></tr>'
    '</tbody></table>'
)

#: 只有合并行的响应（取 `110060` 真实响应的合并行，去掉已生效行）——
#: 用来钉住「有行但无已生效下修 ⇒ no_adjust」这条分桶。
REAL_HTML_NOT_PASSED_ONLY = (
    '<table class="tablesorter" style="width:440px;"><thead><tr><th>转债名称</th>'
    '<th>股东大会日</th><th>下修前<br>转股价</th><th>下修后<br>转股价</th>'
    '<th>新转股价<br>生效日期</th><th>下修底价</th></tr></thead><tbody>'
    '<tr><td>天路转债</td><td>2022-05-31</td><td colspan="4" style="text-align:center">股东大会未通过</td></tr>'
    '</tbody></table>'
)

#: 无下修记录的唯一合法空态（12 字节，无 <table>）
EMPTY_BODY = '暂无数据'


# ── 解析器 ──


def test_parse_adjust_logs_real_sample():
    rows = parse_adjust_logs(REAL_HTML_128013)

    assert len(rows) == 3
    # 三行都是**已生效**下修（生效日期可解析）——只有这种才允许落库
    assert {r['kind'] for r in rows} == {'adjusted'}
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


def test_parse_adjust_logs_missing_prices_are_none():
    """**非唯一键**的空单元格保留为 None（不是 0，也不抛错）。

    下修前转股价 / 下修底价在源侧偶尔留空；把它们当结构异常会让整只债抓取失败。
    生效日期可解析 ⇒ 仍是 ``adjusted``（已生效），只是个别列缺值。
    """
    html = (
        '<table><thead><tr><th>股东大会日</th></tr></thead><tbody>'
        '<tr><td>洪涛转债</td><td>2021-02-23</td><td></td><td>2.320</td>'
        '<td>2021-02-24</td><td>--</td></tr>'
        '</tbody></table>'
    )
    rows = parse_adjust_logs(html)
    assert len(rows) == 1
    assert rows[0]['kind'] == 'adjusted'
    assert rows[0]['convert_price_before'] is None
    assert rows[0]['effective_date'] == date(2021, 2, 24)
    assert rows[0]['adjust_floor_price'] is None


def test_parse_adjust_logs_pending_when_effective_missing():
    """生效日期是 ``-`` ⇒ ``pending``（源侧预估值，股东大会日在未来）。

    判据是**有没有生效日**，不是「数值看起来像不像」：预估值被否掉就不会生效，
    计入「下修次数」等于把未发生的事写成事实。
    """
    rows = parse_adjust_logs(REAL_HTML_110095)

    assert [r['kind'] for r in rows] == ['pending', 'adjusted', 'adjusted']
    pending = rows[0]
    assert pending['shareholder_meeting_date'] == date(2026, 11, 10)
    assert pending['effective_date'] is None
    # 预估值本身仍被解析出来（保留原值，供排查「源侧到底报了什么」）
    assert pending['convert_price_after'] == Decimal('3.96')


def test_parse_adjust_logs_colspan_row_is_not_passed():
    """``<td colspan="4">股东大会未通过</td>`` ⇒ ``not_passed``，且**不丢同表的已生效行**。

    实测 110060 天路转债：2022-08-12 已生效 + 2022-05-31 未通过。首版把合并行
    当「单元格数 3 != 6」整响应抛错，成功记录一起丢掉（列表显示 `—`，
    与「从未下修」无法区分）。
    """
    rows = parse_adjust_logs(REAL_HTML_110060)

    assert [r['kind'] for r in rows] == ['adjusted', 'not_passed']
    assert rows[0]['shareholder_meeting_date'] == date(2022, 8, 12)
    assert rows[0]['adjust_floor_price'] == Decimal('5.420')
    assert rows[1]['shareholder_meeting_date'] == date(2022, 5, 31)
    assert rows[1]['status_text'] == '股东大会未通过'


def test_parse_adjust_logs_not_passed_text_is_not_enumerated():
    """结论文本**不作为判据**：源侧至少 5 种写法（未通过/不通过/取消/无需调整/均退市）。

    判据是结构（末格 colspan >= 2）。拿文本枚举当判据，源侧多一种写法就漏。
    """
    for text in ('股东大会未通过', '股东大会不通过', '股价上涨，股东大会取消', '无需调整', '正股转债均退市'):
        html = (
            '<table><thead><tr><th>股东大会日</th></tr></thead><tbody>'
            f'<tr><td>某转债</td><td>2025-01-02</td><td colspan="4">{text}</td></tr>'
            '</tbody></table>'
        )
        rows = parse_adjust_logs(html)
        assert len(rows) == 1
        assert rows[0]['kind'] == 'not_passed'
        assert rows[0]['status_text'] == text


def test_parse_adjust_logs_123099_keeps_five_adjusted_rows():
    """真实样本 123099：1 条「均退市」合并行 + **5 条已生效**下修，一条都不许丢。"""
    rows = parse_adjust_logs(REAL_HTML_123099)

    assert len(rows) == 6
    kinds = [r['kind'] for r in rows]
    assert kinds.count('adjusted') == 5
    assert kinds.count('not_passed') == 1
    assert [r['adjust_floor_price'] for r in rows if r['kind'] == 'adjusted'] == [
        Decimal('3.000'),
        Decimal('4.890'),
        Decimal('11.220'),
        Decimal('19.840'),
        Decimal('27.090'),
    ]


def test_parse_adjust_logs_not_passed_only():
    """只有合并行 ⇒ 有行但无已生效下修（job 侧计 ``no_adjust``，不是「暂无数据」）。"""
    rows = parse_adjust_logs(REAL_HTML_NOT_PASSED_ONLY)

    assert len(rows) == 1
    assert rows[0]['kind'] == 'not_passed'
    assert rows[0]['status_text'] == '股东大会未通过'


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
    assert stats['no_adjust'] == 0
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


def test_bond_adjust_log_job_only_stores_effective_rows(db):
    """预估（未生效）行**不落库**，但条数进 ``pending_rows``（不静默）。

    实测 110095 双良转债：1 条预估（2026-11-10，生效日 `-`）+ 2 条已生效。
    """
    job = BondAdjustLogSyncJob(_FakeAdapter({'110095': REAL_HTML_110095}), db)
    result = job.run(targets=['SH110095'])

    rows = db.query(ConvertibleBondAdjustLog).order_by(ConvertibleBondAdjustLog.shareholder_meeting_date).all()
    assert len(rows) == 2
    assert [r.shareholder_meeting_date for r in rows] == [date(2024, 10, 25), date(2025, 3, 25)]

    stats = result['stats']
    assert stats['with_records'] == 1
    assert stats['pending_rows'] == 1
    assert stats['success'] == 2
    assert stats['bucket_sum'] == stats['total'] == 1


def test_bond_adjust_log_job_no_adjust_bucket(db):
    """源侧有行但无已生效下修 ⇒ ``no_adjust``（不是 ``no_records``，也不是 ``with_records``）。

    混进 ``no_records`` 会让人以为源侧没数据；混进 ``with_records`` 会让
    「下修次数」把未通过/取消/退市算成下修。
    """
    job = BondAdjustLogSyncJob(_FakeAdapter({'110060': REAL_HTML_NOT_PASSED_ONLY}), db)
    result = job.run(targets=['SH110060'])

    assert db.query(ConvertibleBondAdjustLog).count() == 0
    stats = result['stats']
    assert result['status'] == 'success'
    assert stats['no_adjust'] == 1
    assert stats['no_records'] == 0
    assert stats['with_records'] == 0
    assert stats['failed'] == 0
    assert stats['bucket_sum'] == stats['total'] == 1


def test_bond_adjust_log_job_keeps_adjusted_row_next_to_not_passed(db):
    """合并行与已生效行同表 ⇒ 已生效那条**必须落库**（首版会整响应丢掉的真实样本）。"""
    job = BondAdjustLogSyncJob(_FakeAdapter({'110060': REAL_HTML_110060}), db)
    result = job.run(targets=['SH110060'])

    rows = db.query(ConvertibleBondAdjustLog).all()
    assert len(rows) == 1
    assert rows[0].shareholder_meeting_date == date(2022, 8, 12)
    assert rows[0].convert_price_before == Decimal('6.990')
    assert rows[0].convert_price_after == Decimal('5.420')
    assert rows[0].adjust_floor_price == Decimal('5.420')

    stats = result['stats']
    assert stats['with_records'] == 1
    assert stats['no_adjust'] == 0
    assert stats['success'] == 1


def test_bond_adjust_log_job_skips_non_bond_targets(db):
    """目标池混着股票/ETF：跳过但不计入失败（那不是本 job 的活）。"""
    adapter = _FakeAdapter(_sample_rows())
    job = BondAdjustLogSyncJob(adapter, db)
    result = job.run(targets=['SH600519', 'SZ159915', 'SZ128013'])

    assert result['status'] == 'success'
    assert adapter.calls == ['128013']  # 只在真转债上发请求
    assert result['stats']['not_bond'] == 2
    assert result['stats']['with_records'] == 1
    assert result['stats']['no_adjust'] == 0
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
