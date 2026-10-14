# -*- coding: utf-8 -*-
"""测试基金行业配置 + 持仓明细（#2029 卡 C）。

用mock 的 db Session 验证分支与口径，不依赖真实库。重点钉三条硬口径：

1. **csrc / gics 禁止跨体系相加** —— 两者分区返回，且各取各的最新报告期；
2. **持仓明细同期内 ``full`` 优先**，无 ``full`` 才用 ``top10`` 并据此打标；
3. **截断不改变合计** —— Top N + 「其他」的占比和 = 截断前的总和。
"""

from datetime import date
from unittest.mock import MagicMock

from app.services.fund_holdings_detail import build_fund_holdings_detail


class _FundType:
    def __init__(self, name):
        self.name = name


class _Fund:
    def __init__(self, code='110020', name='易方达消费行业'):
        self.fund_code = code
        self.name = name
        self.fund_type = _FundType('股票型')


class _Alloc:
    """``fund_industry_allocs`` 行。"""

    def __init__(self, period, code, name, scheme, ratio, report_date=None):
        self.report_period = period
        self.report_date = report_date or date(2026, 6, 30)
        self.industry_code = code
        self.industry_name = name
        self.scheme = scheme
        self.ratio = ratio


class _Holding:
    """``fund_holdings`` 行。"""

    def __init__(self, period, basis, stock_code, stock_name, ratio, rank, shares=None, market_value=None):
        self.report_period = period
        self.report_date = date(2026, 6, 30)
        self.holding_basis = basis
        self.stock_code = stock_code
        self.stock_name = stock_name
        self.ratio = ratio
        self.rank = rank
        self.shares = shares
        self.market_value = market_value


def _fake_db(fund, alloc_rows=None, holding_rows=None):
    """mock db。

    ⚠️ `order_by(...desc())` 必须**真排序**：`_load_latest_holdings` 与本模块的
    `_industry_buckets` 都靠「rows[0] 是最新期」这个前提取期次。MagicMock 默认不排，
    于是 rows[0] 变成插入序 —— 断言会以「实现有 bug」的假象红掉（实测踩过：
    `test_holding_only_latest_period` 报['600000'] != ['600001']，而真库是对的）。
    这里按列名还原排序语义：``report_period`` 降序、其余保持插入序。
    """
    db = MagicMock()
    fund_q = MagicMock()
    fund_q.filter.return_value.first.return_value = fund
    alloc_q = MagicMock()
    alloc_q.filter.return_value.order_by.return_value.all.side_effect = lambda: sorted(
        alloc_rows or [], key=lambda r: r.report_period, reverse=True
    )
    hold_q = MagicMock()
    hold_q.filter.return_value.order_by.return_value.all.side_effect = lambda: sorted(
        holding_rows or [], key=lambda r: r.report_period, reverse=True
    )

    def _query(model):
        name = getattr(model, '__name__', '')
        if name == 'Fund':
            return fund_q
        if name == 'FundIndustryAlloc':
            return alloc_q
        if name == 'FundHolding':
            return hold_q
        return MagicMock()

    db.query.side_effect = _query
    return db


def test_not_found():
    assert build_fund_holdings_detail(_fake_db(None), '999999') is None


def test_empty_code_raises():
    import pytest

    with pytest.raises(ValueError):
        build_fund_holdings_detail(_fake_db(_Fund()), '  ')


def test_both_empty_is_applicable_false():
    """基金存在但无任何披露 → applicable False（**不是** 404）。"""
    data = build_fund_holdings_detail(_fake_db(_Fund()), '110020')
    assert data is not None
    assert data['applicable'] is False
    assert data['has_industry'] is False
    assert data['has_holding'] is False
    assert data['industries'] == []
    assert data['industry_chart'] == []
    assert data['holdings']['rows'] == []


# ── 硬口径 1：csrc / gics 分区，禁止跨体系相加 ──────────────────────────────────


def test_schemes_partitioned_and_ordered():
    rows = [
        _Alloc('2026Q2', 'A', '制造业', 'csrc', 30.0),
        _Alloc('2026Q2', 'B', '金融业', 'csrc', 20.0),
        _Alloc('2026Q2', '10', '非必需消费品', 'gics', 12.0),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020')
    assert data['has_industry'] is True
    # 主口径 csrc 必须排第一
    assert [b['scheme'] for b in data['industries']] == ['csrc', 'gics']
    assert data['industries'][0]['is_primary'] is True
    assert data['industries'][1]['is_primary'] is False
    # 两套体系各自独立合计，绝不相加（否则 30+20+12=62 会误导用户）
    assert data['industries'][0]['total_ratio'] == 50.0
    assert data['industries'][1]['total_ratio'] == 12.0
    assert data['industries'][0]['scheme_label'] == '证监会门类'
    assert data['industries'][1]['scheme_label'] == 'GICS 板块'


def test_latest_period_per_scheme_not_global_max():
    """各体系的最新期独立取：csrc 有 2026Q2 而 gics 只到 2025Q4 时，
    不能拿全局 max（2026Q2）当 gics 的报告期去查（查不到 → 该体系整个消失）。"""
    rows = [
        _Alloc('2026Q2', 'A', '制造业', 'csrc', 30.0),
        _Alloc('2025Q4', '10', '非必需消费品', 'gics', 12.0),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020')
    by_scheme = {b['scheme']: b for b in data['industries']}
    assert by_scheme['csrc']['report_period'] == '2026Q2'
    assert by_scheme['gics']['report_period'] == '2025Q4'
    assert len(by_scheme['gics']['items']) == 1


def test_industry_chart_uses_primary_scheme_only():
    """环形图只吃主口径（否则会把两套体系混进一张图，正是硬口径禁止的事）。"""
    rows = [
        _Alloc('2026Q2', 'A', '制造业', 'csrc', 30.0),
        _Alloc('2026Q2', '10', '非必需消费品', 'gics', 12.0),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020')
    names = [d['name'] for d in data['industry_chart']]
    assert names == ['制造业']
    assert all(d['value'] > 0 for d in data['industry_chart'])


def test_industry_chart_drops_zero_and_null_ratio():
    rows = [
        _Alloc('2026Q2', 'A', '制造业', 'csrc', 30.0),
        _Alloc('2026Q2', 'B', '金融业', 'csrc', 0.0),
        _Alloc('2026Q2', 'C', '未知行业', 'csrc', None),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020')
    assert [d['name'] for d in data['industry_chart']] == ['制造业']


# ── 硬口径 2：full 优先 ────────────────────────────────────────────────────────


def test_holding_basis_full_preferred_over_top10():
    """同一报告期内 full 与 top10 并存时选 full（本地库实测 6A0008 就是这种）。"""
    rows = [
        _Holding('2026Q2', 'full', '600000', '浦发银行', 3.0, 1),
        _Holding('2026Q2', 'top10', '600001', '邯郸钢铁', 9.9, 1),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), holding_rows=rows), '110020')
    holdings = data['holdings']
    assert holdings['basis'] == 'full'
    assert [r['stock_code'] for r in holdings['rows']] == ['600000']
    assert '全量' in holdings['basis_label']


def test_holding_basis_top10_when_no_full():
    rows = [_Holding('2026Q2', 'top10', '600001', '邯郸钢铁', 9.9, 1)]
    data = build_fund_holdings_detail(_fake_db(_Fund(), holding_rows=rows), '110020')
    assert data['holdings']['basis'] == 'top10'
    assert '前十大' in data['holdings']['basis_label']


def test_holding_only_latest_period():
    rows = [
        _Holding('2026Q1', 'full', '600000', '旧股', 5.0, 1),
        _Holding('2026Q2', 'full', '600001', '新股', 3.0, 1),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), holding_rows=rows), '110020')
    assert [r['stock_code'] for r in data['holdings']['rows']] == ['600001']
    assert data['holdings']['report_period'] == '2026Q2'


def test_holding_sorted_by_rank_and_null_fields_kept_none():
    rows = [
        _Holding('2026Q2', 'full', '600003', 'C', 1.0, 3),
        _Holding('2026Q2', 'full', '600001', 'A', 5.0, 1, shares=None, market_value=None),
        _Holding('2026Q2', 'full', '600002', 'B', 3.0, 2),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), holding_rows=rows), '110020')
    rows_out = data['holdings']['rows']
    assert [r['rank'] for r in rows_out] == [1, 2, 3]
    # 缺失字段必须是 None（前端降级「—」），**不能**编造 0
    assert rows_out[0]['shares'] is None
    assert rows_out[0]['market_value'] is None
    assert rows_out[0]['ratio'] == 5.0
    assert data['holdings']['shown_total_ratio'] == 9.0


def test_holding_top_n_none_returns_all():
    rows = [_Holding('2026Q2', 'full', f'60000{i}', f'S{i}', 1.0, i) for i in range(1, 16)]
    data = build_fund_holdings_detail(_fake_db(_Fund(), holding_rows=rows), '110020')
    assert len(data['holdings']['rows']) == 15


# ── 硬口径 3：截断不改变合计 ──────────────────────────────────────────────────


def test_industry_truncation_preserves_total():
    rows = [
        _Alloc(
            '2026Q2',
            chr(65 + i),
            f'行业{i}',
            'csrc',
            float(i + 1),
        )
        for i in range(10)
    ]
    full = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020', industry_top_n=0)
    trunc = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020', industry_top_n=3)
    total_all = full['industries'][0]['total_ratio']
    total_trunc = trunc['industries'][0]['total_ratio']
    assert total_all == total_trunc == 55.0  # 1+2+...+10
    items = trunc['industries'][0]['items']
    assert len(items) == 4  # Top3 + 「其他」
    assert [it['ratio'] for it in items[:3]] == [10.0, 9.0, 8.0]
    assert items[-1]['industry_name'] == '其他'
    # 余下 7+6+5+4+3+2+1 = 28（不是 52 —— 52 是「从第 7 项起全部」的错算）
    assert items[-1]['ratio'] == 28.0
    # 扇形图与表格必须一致（都取截断后的 items）
    assert len(trunc['industry_chart']) == 4
    assert sum(d['value'] for d in trunc['industry_chart']) == 55.0


def test_industry_no_truncation_when_top_n_zero():
    rows = [_Alloc('2026Q2', chr(65 + i), f'行业{i}', 'csrc', float(i + 1)) for i in range(10)]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020', industry_top_n=0)
    assert len(data['industries'][0]['items']) == 10


def test_industry_truncation_with_null_tail_ratio_does_not_fabricate_zero():
    """余下项占比全缺 → 不编造「其他 0%」，改标「无占比」。"""
    rows = [
        _Alloc('2026Q2', 'A', '行业1', 'csrc', 10.0),
        _Alloc('2026Q2', 'B', '行业2', 'csrc', 20.0),
        _Alloc('2026Q2', 'C', '行业3', 'csrc', None),
    ]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020', industry_top_n=2)
    items = data['industries'][0]['items']
    assert items[-1]['ratio'] is None
    assert '无占比' in items[-1]['industry_name']


# ── 组合场景 ──────────────────────────────────────────────────────────────────


def test_industry_only_still_reports_has_holding_false():
    """只有行业配置没有个股（未到披露期）→ applicable仍 True，只降级持仓那张卡。"""
    rows = [_Alloc('2026Q2', 'A', '制造业', 'csrc', 30.0)]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020')
    assert data['applicable'] is True
    assert data['has_industry'] is True
    assert data['has_holding'] is False


def test_source_label_is_eastmoney_not_nav_source():
    """来源必须是东财（持仓 f10/ccmx），**不是**天天基金（那是净值链路）——
    标错来源比不标更糟，用户会拿它当溯源依据。"""
    rows = [_Holding('2026Q2', 'full', '600001', 'A', 5.0, 1)]
    data = build_fund_holdings_detail(_fake_db(_Fund(), holding_rows=rows), '110020')
    assert data['source'] == '东方财富'
    assert data['source'] != '天天基金'


def test_eastmoney_source_code_is_mapped():
    """``eastmoney``（东财直连码，非 akshare 封装）必须在映射表里。

    反向样本：未收录的码 ``data_source_label`` 会**原样返回**（这是刻意设计，
    好让排查的人看到线索而不是笼统的「未知」）—— 正因如此，漏登记的后果是
    前端脚注直接显示 ``eastmoney`` 给用户，测试必须钉住这条。
    """
    from app.core.data_sources import data_source_label

    assert data_source_label('eastmoney') == '东方财富'
    # 反向：未知码原样返回（证明上一条不是因为「什么都返回东方财富」而绿）
    assert data_source_label('akshare_zzz_unknown') == 'akshare_zzz_unknown'


def test_as_of_falls_back_to_industry_report_date():
    """只有行业配置时 as_of 取行业报告期（否则脚注日期会是空的）。"""
    rows = [_Alloc('2026Q2', 'A', '制造业', 'csrc', 30.0)]
    data = build_fund_holdings_detail(_fake_db(_Fund(), alloc_rows=rows), '110020')
    assert data['as_of'] == '2026-06-30'
