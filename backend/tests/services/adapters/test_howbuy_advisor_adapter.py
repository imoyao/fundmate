# -*- coding: utf-8 -*-
"""好买适配器单测（#1910）。

全部走 **mock 响应**，不依赖外网——真实接口回归由 ``#1910`` 的实跑核对覆盖
（持仓 21 条 / 调仓 33 次，与网页版一致）。

这里钉住三类最容易写错、且写错不会报错只会「数据悄悄不对」的地方：

1. **空字符串不是 0**：好买用 ``''`` 表示无数据（持仓的 ``sccczb`` 常见），
   直接 ``float('')`` 会抛、``or 0`` 会变成「占比 0」——两者都会污染落库数据；
2. **指标区间必须是 ``CL``**：``range=1N`` 返回的是「近1年收益」而非年化口径
   （实测 ``-0.41`` 与 ``return_1y`` 相同），用错会让 ``annual_return`` 静默错位；
3. **操作码由占比推导**：好买不给 ``operationInt``（天天给），推错等于调仓方向全反。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.domains.funds.models import (  # noqa: E402
    AdvisorAdjustHistory,
    AdvisorHolding,
    AdvisorIndustryAlloc,
    AdvisorPortfolio,
)
from app.services.adapters.advisor_source import (  # noqa: E402
    get_advisor_source,
    registered_platforms,
)
from app.services.adapters.howbuy_advisor_adapter import (  # noqa: E402
    METRIC_RANGE,
    HowbuyAdvisorAdapter,
    _to_float,
    _to_iso_date,
)
from app.services.sync.jobs.advisor_portfolio_job import (  # noqa: E402
    AdvisorPortfolioSyncJob,
)

# ── 平台注册 ──


def test_platform_registered():
    """挂了装饰器 + 被 _ensure_builtin_sources 导入，才能出现在注册表里。"""
    assert 'HOWBUY' in registered_platforms()
    src = get_advisor_source('HOWBUY')
    assert isinstance(src, HowbuyAdvisorAdapter)
    assert src.platform == 'HOWBUY'
    # 有官方调仓接口 → 不需要快照推导（Port 的能力位）
    assert src.has_official_rebalances is True
    assert src.derive_rebalances_from_snapshots is False


def test_audit_identity_non_empty():
    """orchestrator._save_sync_log 会写这两个值，缺则 AttributeError。"""
    src = HowbuyAdvisorAdapter()
    assert src.get_name() == 'howbuy_advisor'
    assert src.get_version()


# ── _to_float：空字符串语义 ──


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('7.50', 7.5),
        ('', None),  # 好买的无数据表示——必须是 None，不能是 0
        (None, None),
        ('-16.37', -16.37),
        ('abc', None),
    ],
)
def test_to_float(raw, expected):
    assert _to_float(raw) == expected


def test_to_float_empty_is_not_zero():
    """回归：``sccczb=''`` 曾被当成 0，会让「新增」误判成「持平」。"""
    assert _to_float('') is None
    assert _to_float('') != 0


# ── 操作码推导 ──


@pytest.mark.parametrize(
    'pre,after,expected',
    [
        (None, 5.0, 4),  # 上次无、本次有 → 新增
        (0.0, 5.0, 4),  # 同上（0 视同无）
        (5.0, 7.0, 2),  # 加仓
        (5.0, 3.0, 3),  # 减仓
        (5.0, 0.0, 3),  # 清仓 → 归减仓（词表无「清仓」）
        (5.0, 5.0, 5),  # 持平
        (5.0, None, 3),  # 本次缺失、上次有 → 减仓
        (None, None, None),  # 两侧都缺 → 不猜
    ],
)
def test_derive_op_code(pre, after, expected):
    assert HowbuyAdvisorAdapter._derive_op_code(pre, after) == expected


def test_flatten_funds_maps_names():
    """op_name 走共享词表，别在适配器里另写一份中文。"""
    funds = HowbuyAdvisorAdapter._flatten_funds(
        [
            {'jjdm': '002980', 'jjjc': '华夏创新前沿股票A', 'cczb': '7.50', 'sccczb': '5.00'},
            {'jjdm': '', 'jjjc': '缺代码应被跳过', 'cczb': '1.00', 'sccczb': '1.00'},
        ]
    )
    assert len(funds) == 1
    f = funds[0]
    assert f['fund_code'] == '002980'
    assert f['fund_name'] == '华夏创新前沿股票A'
    assert (f['pre_ratio'], f['after_ratio']) == (5.0, 7.5)
    assert f['op_code'] == 2 and f['op_name'] == '加仓'


# ── fetch_overview：映射与口径 ──


DAY_BODY = {
    'syxx': {
        'cjrq': '20170905',
        'zhjz': '1.9816',
        'jzrq': '20260929',
        'hbcl': '98.16',
        'nhhbcl': '7.83',
        'hbdr': '0.37',
    },
    'cpjs': {'recommendReason': '以长期业绩优秀的基金为核心基础配置'},
    'zlr': {'name': '中欧财富投顾'},
    'jdsybx': {
        'dataList': [
            {'rangeName': '近1周', 'zhhb': '-4.90', 'jzhb': '-5.54', 'cehb': '0.64'},
            {'rangeName': '近1年', 'zhhb': '-0.41', 'jzhb': '2.36', 'cehb': '-2.77'},
            {'rangeName': '近3年', 'zhhb': '32.41', 'jzhb': '30.72', 'cehb': '1.69'},
        ]
    },
    # 实测该节点是空的（只有 2 条 zbdm=hb、zbnrValue 全 null）——指标不能从这取
    'frontInfo': {'cpzbList': [{'zbdm': 'hb', 'zbnr': '98.16%', 'zbnrValue': None}]},
}

IND_BODY = {
    'title1': '超级股票全明星',
    'qjzb': {
        'dataList': [
            {'mc': '年化收益率', 'sz1': '7.83', 'sz2': '5.46'},
            {'mc': '年化波动率', 'sz1': '19.25', 'sz2': '20.15'},
            {'mc': '夏普比率', 'sz1': '0.33', 'sz2': '0.20'},
            {'mc': '最大回撤', 'sz1': '-46.91', 'sz2': '-47.17'},
        ]
    },
}


def _adapter_with(monkeypatch, day=None, ind=None, rb=None):
    src = HowbuyAdvisorAdapter()

    def fake_get(url, params):
        if 'clcphbzst' in url:
            return ind
        if 'clcplsgd' in url:
            return rb
        return day

    monkeypatch.setattr(src, '_get_json', fake_get)
    return src


def test_fetch_overview_maps_canonical(monkeypatch):
    src = _adapter_with(monkeypatch, day=DAY_BODY, ind=IND_BODY)
    ov = src.fetch_overview('zozh002')

    assert ov['name'] == '超级股票全明星'  # 名称来自指标端点的 title1
    assert ov['estab_date'] == '2017-09-05'
    assert ov['nav'] == 1.9816
    assert ov['nav_date'] == '2026-09-29'
    assert ov['cum_return'] == 98.16
    assert ov['annual_return'] == 7.83  # 成立以来年化
    assert ov['return_1d'] == 0.37
    assert ov['org_name'] == '中欧财富投顾'
    assert ov['volatility'] == 19.25
    assert ov['sharpe_ratio'] == 0.33
    assert ov['max_drawdown'] == -46.91
    assert ov['source_url'] == 'https://www.howbuy.com/combination/zozh002/'
    # 区间收益
    assert ov['return_1w'] == -4.9
    assert ov['return_1y'] == -0.41
    assert ov['excess_return'] == -2.77  # 取「近1年」那行的超额
    # 无对应列的区间进 extra，不硬塞
    assert ov['extra']['近3年']['zhhb'] == 32.41


def test_metric_range_must_be_cl(monkeypatch):
    """回归：``range=1N`` 时「年化收益率」给的是近1年收益（-0.41），与 return_1y 重复；
    换成 CL 才是 7.83、与概览 nhhbcl 一致。这里钉住请求参数本身。"""
    captured = {}

    def fake_get(url, params):
        if 'clcphbzst' in url:
            captured.update(params)
            return IND_BODY
        return DAY_BODY

    src = HowbuyAdvisorAdapter()
    monkeypatch.setattr(src, '_get_json', fake_get)
    src.fetch_overview('zozh002')

    assert captured.get('range') == METRIC_RANGE == 'CL'


def test_fetch_overview_degrades_on_empty(monkeypatch):
    """概览端点挂了就返回 {}——Port 约定：单面失败不影响其余数据面。"""
    src = _adapter_with(monkeypatch, day=None, ind=None)
    assert src.fetch_overview('zozh002') == {}


def test_fetch_overview_without_indicator_still_returns_day(monkeypatch):
    """指标面失败不该连基本信息一起丢。"""
    src = _adapter_with(monkeypatch, day=DAY_BODY, ind=None)
    ov = src.fetch_overview('zozh002')
    assert ov['estab_date'] == '2017-09-05'
    assert 'name' not in ov  # 名称在指标端点，拿不到就不返回（不编造）


# ── fetch_holdings / fetch_industries / fetch_rebalances ──


def test_fetch_holdings(monkeypatch):
    day = {
        'zxgd': {
            'gdqsrq': '20260918',
            'fundList': [
                {'jjdm': '002980', 'jjjc': '华夏创新前沿股票A', 'cczb': '7.50', 'sccczb': ''},
                {'jjdm': '001892', 'jjjc': '长盛新兴成长混合A', 'cczb': '7.00', 'sccczb': '5.00'},
            ],
        }
    }
    src = _adapter_with(monkeypatch, day=day)
    h = src.fetch_holdings('zozh002')

    assert h['as_of_date'] == '2026-09-18'
    assert len(h['funds']) == 2
    f = h['funds'][0]
    # 快照没有前后对比 → pre/op 一律 None，不猜
    assert f['pre_ratio'] is None
    assert f['op_code'] is None and f['op_name'] is None
    assert f['after_ratio'] == 7.5


def test_fetch_industries(monkeypatch):
    day = {
        'zcfl1List': [
            {'mc': '股票型', 'zb': '0.00'},
            {'mc': '混合型', 'zb': '0.00'},
            {'mc': '', 'zb': '1.00'},  # 无名称跳过
        ]
    }
    src = _adapter_with(monkeypatch, day=day)
    out = src.fetch_industries('zozh002')
    assert [x['industry_name'] for x in out] == ['股票型', '混合型']


def test_fetch_rebalances(monkeypatch):
    rb = {
        'dataList': [
            {
                'gdqsrq': '20260918',
                'ms1': '',
                'fundList': [
                    {'jjdm': '002980', 'jjjc': '华夏创新前沿股票A', 'cczb': '7.50', 'sccczb': '7.50'},
                    {'jjdm': '001892', 'jjjc': '长盛新兴成长混合A', 'cczb': '7.00', 'sccczb': '5.00'},
                ],
            }
        ]
    }
    src = _adapter_with(monkeypatch, rb=rb)
    out = src.fetch_rebalances('zozh002')

    assert len(out) == 1
    node = out[0]
    assert node['adjust_date'] == '2026-09-18'
    assert node['reason'] is None  # 空字符串归一为 None
    ops = {f['fund_code']: f['op_name'] for f in node['funds']}
    assert ops == {'002980': '持平', '001892': '加仓'}


def test_empty_data_surfaces_return_empty_not_raise(monkeypatch):
    """Port 约定：无该数据面时返回空集合，不要抛错（job 对空集合天然无操作）。"""
    src = _adapter_with(monkeypatch, day=None, ind=None, rb=None)
    assert src.fetch_holdings('zozh002') == {'as_of_date': None, 'funds': []}
    assert src.fetch_industries('zozh002') == []
    assert src.fetch_rebalances('zozh002') == []


# ── 日期格式规整（端到端抓到的契约不匹配）──


def test_compact_dates_normalized_to_iso():
    """howbuy 用 ``YYYYMMDD``，而落库层 ``_parse_date`` 只认 ``%Y-%m-%d``。

    不规整的后果是**静默落成 NULL**：端到端用例里 `estab_date` 一开始就是 None，
    单测却全过（因为单测只验适配器返回了字符串，没验落库层能否解析）。
    """
    assert _to_iso_date('20170905') == '2017-09-05'
    assert _to_iso_date('20260929') == '2026-09-29'
    assert _to_iso_date('') is None
    assert _to_iso_date(None) is None
    # 已经是 ISO 的原样返回（幂等，防重复格式化）
    assert _to_iso_date('2017-09-05') == '2017-09-05'


# ── 端到端：经 AdvisorPortfolioSyncJob 全自动入库（#1910 验收项）──
#
# 与上面的单测互补：单测验「适配器自己返回什么」，这里验「job 拿到适配器后落库成什么」。
# 用**真实适配器**（不是 _FakeSource）只 mock 掉 HTTP 层，让 canonical 映射真跑一遍——
# 假数据源只能验证 job 的平台无关性，验证不了「我这个适配器的输出能否被 job 正确消化」。
#
# 样本来自 tests/fixtures/howbuy_zozh002_sample.json（2026-10-06 抓的真实响应），
# 沿用 qieman_holdings_sample.json 的做法：端到端不依赖外网，CI 才稳定。

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'howbuy_zozh002_sample.json'


@pytest.fixture
def howbuy_job(db, monkeypatch):
    """真实适配器 + mock HTTP。db 是 conftest 的临时库 fixture，不碰 invest.db。

    **必须先在建档表里插一条 platform=HOWBUY 的档案**：``AdvisorPortfolioSyncJob._resolve_targets``
    是「按 code 回查库内 platform」，查不到才用 ``_infer_platform`` 兜底，而兜底对
    ``zozh002`` 会给出 ``DEFAULT_ADVISOR_PLATFORM``（TIANTIAN）——于是 job 会去调天天接口、
    与 howbuy 无关。job 文件里也写明了「**禁止按代码前缀判定平台归属**，一律以
    ``AdvisorPortfolio.platform`` 为准」。测试若不铺这条前置，验的就不是本适配器。
    """
    sample = json.loads(FIXTURE.read_text(encoding='utf-8'))
    src = HowbuyAdvisorAdapter()

    def fake_get(url, params):
        if 'clcphbzst' in url:
            return sample['indicator']
        if 'clcplsgd' in url:
            return sample['rebalance']
        return sample['overview']

    monkeypatch.setattr(src, '_get_json', fake_get)

    db.add(AdvisorPortfolio(platform='HOWBUY', code='zozh002', name='zozh002'))
    db.commit()
    return AdvisorPortfolioSyncJob(db=db, sources={'HOWBUY': src})


def test_howbuy_sync_end_to_end(howbuy_job, db):
    """四类数据面一次落库 + source 口径（卡片验收项）。"""
    result = howbuy_job.run(full_sync=True, targets=['zozh002'])
    assert result['status'] == 'success', result

    p = db.query(AdvisorPortfolio).filter_by(platform='HOWBUY', code='zozh002').one()
    # 概览（含从指标端点取的 name 与风险指标）
    assert p.name == '超级股票全明星'
    assert p.org_name == '中欧财富投顾'
    assert str(p.estab_date) == '2017-09-05'
    assert float(p.annual_return) == pytest.approx(7.83)
    assert float(p.max_drawdown) == pytest.approx(-46.91)
    assert float(p.volatility) == pytest.approx(19.25)
    assert float(p.sharpe_ratio) == pytest.approx(0.33)
    # return_1y 取区间收益，与 annual_return 不是同一个口径（前者 -0.41、后者 7.83）
    assert float(p.return_1y) == pytest.approx(-0.41)
    # **source 列与既有口径一致**（天天是 'tiantian'、且慢是 'qieman'，本适配器 'howbuy'）
    assert p.source == 'howbuy'

    # 持仓快照（实测 21 条，与网页版一致）
    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id).all()
    assert len(hs) == 21
    assert '002980' in {h.fund_code for h in hs}

    # 资产类别（好买给的是 zcfl1List，非行业）
    ind = db.query(AdvisorIndustryAlloc).filter_by(portfolio_id=p.id).all()
    assert {r.industry_name for r in ind} == {'股票型', '混合型', '货币型', '指数型'}

    # 调仓明细入库：**这是基金级明细表，不是「每次调仓一行」**——
    # 源数据 33 次调仓，每次含多只基金，落到 543 行（33 次 × 平均约 16 只）。
    # 断言按「不同调仓日期数」表示次数，避免把明细行数误读成次数。
    hist = db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).all()
    assert len(hist) == 543
    assert len({str(h.adjust_date) for h in hist}) == 33
    # **三张明细表的 source 列也要与既有口径一致** —— #1910 验收项点名的就是这半句
    # （「调仓明细入 advisor_adjust_histories」），只验 advisor_portfolios.source 不够。
    # 生产库实测既有口径为 qieman / tiantian / qieman_manual（= platform.lower()），
    # 本适配器经 job 应统一写 'howbuy'。
    assert {h.source for h in hs} == {'howbuy'}
    assert {r.source for r in ind} == {'howbuy'}
    assert {h.source for h in hist} == {'howbuy'}
    # 操作名由占比推导（好买不给 operationInt），四类都该出现
    ops = {h.op_name for h in hist}
    assert {'加仓', '减仓', '新增', '持平'} <= ops


def test_howbuy_rebalance_dates_landed(howbuy_job, db):
    """调仓日期必须落进 adjust_date——它是快照覆盖的键，错一天就会重复插行。"""
    howbuy_job.run(full_sync=True, targets=['zozh002'])
    p = db.query(AdvisorPortfolio).filter_by(platform='HOWBUY', code='zozh002').one()
    hist = db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).all()
    dates = sorted({str(h.adjust_date) for h in hist})
    # 源数据最早那次调仓就在成立日（20170905，建仓），不是第二个日期
    assert dates[0] == '2017-09-05'
    assert dates[-1] == '2026-09-18'
    assert len(dates) == 33
