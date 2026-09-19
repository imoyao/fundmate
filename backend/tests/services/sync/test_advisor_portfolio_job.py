# -*- coding: utf-8 -*-
"""测试 AdvisorPortfolioSyncJob：多平台（Ports & Adapters，#1392）+ 且慢手动导入（#1167）。

重点不是「某个平台能不能抓」，而是**落库语义与平台无关**：

- 概览只覆盖非 None 值、策展字段永不被抓取覆盖；
- 持仓/行业按快照日覆盖、调仓按调仓日覆盖；
- 无官方调仓接口的平台由快照序列推导；
- **新增平台只加适配器**（registry 注入即可，无需改 job）。
"""

import json
import os
from datetime import date
from typing import Any, Dict, List, Optional

import pytest

from app.domains.funds.models import (
    AdvisorAdjustHistory,
    AdvisorHolding,
    AdvisorIndustryAlloc,
    AdvisorPortfolio,
)
from app.services.sync.adapters.advisor_source import (
    _SOURCES,
    AdvisorPortfolioSource,
    AdvisorSourceRegistry,
    UnknownAdvisorPlatform,
    register_advisor_source,
    registered_platforms,
)
from app.services.sync.adapters.qieman_advisor_adapter import QiemanAdvisorAdapter
from app.services.sync.adapters.tiantian_advisor_adapter import TiantianAdvisorAdapter
from app.services.sync.jobs.advisor_portfolio_job import (
    AdvisorPortfolioSyncJob,
    flatten_qieman_composition,
    import_qieman_holdings,
)

FIXTURE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'fixtures', 'qieman_holdings_sample.json')
)


class _FakeSource(AdvisorPortfolioSource):
    """最小假适配器：实现 Port 全部数据面，返回内容由测试注入。

    继承 ``AdvisorPortfolioSource`` 而非 MagicMock——否则「适配器改了方法名但 job 没
    跟着改」这类破坏根本测不出来，而那正是 #1392 要消灭的问题。
    """

    def __init__(
        self,
        platform: str = 'TIANTIAN',
        overview: Optional[Dict[str, Any]] = None,
        holdings: Optional[Dict[str, Any]] = None,
        industries: Optional[List[dict]] = None,
        rebalances: Optional[List[dict]] = None,
        derive_rebalances: bool = False,
        has_official_rebalances: bool = True,
    ) -> None:
        self.platform = platform
        self.has_official_rebalances = has_official_rebalances
        self.derive_rebalances_from_snapshots = derive_rebalances
        self.overview = overview if overview is not None else {}
        self.holdings = holdings if holdings is not None else {'as_of_date': None, 'funds': []}
        self.industries = industries or []
        self.rebalances = rebalances or []

    def get_name(self) -> str:
        return f'fake_{self.platform.lower()}'

    def get_version(self) -> str:
        return 'v0'

    def fetch_overview(self, code: str) -> dict:
        return self.overview

    def fetch_holdings(self, code: str) -> dict:
        return self.holdings

    def fetch_industries(self, code: str) -> list:
        return self.industries

    def fetch_rebalances(self, code: str) -> list:
        return self.rebalances


#: 天天基金 canonical 概览（含一个 canonical 未覆盖的平台特有字段）
TIANTIAN_OVERVIEW = {
    'name': '越海',
    'risk_level': '4',
    'strategy_desc': '均衡风格',
    'estab_date': '2021-07-26',
    'return_1y': 12.34,
    'extra': {'STATUS': '在售', 'TGCODE': 'XCOVSEX'},
}
TIANTIAN_HOLDINGS = {
    'as_of_date': '2026-04-01',
    'funds': [
        {
            'fund_code': '012153',
            'fund_name': '博时研究慧选混合A',
            'pre_ratio': 15.77,
            'after_ratio': 16.0,
            'op_code': 5,
            'op_name': '持平',
        },
        {
            'fund_code': '005827',
            'fund_name': '易方达蓝筹精选混合',
            'pre_ratio': 10.0,
            'after_ratio': 8.0,
            'op_code': 3,
            'op_name': '减仓',
        },
    ],
}
TIANTIAN_INDUSTRIES = [
    {'industry_name': '电子', 'ratio': 9.16},
    {'industry_name': '基础化工', 'ratio': 4.69},
]
TIANTIAN_REBALANCES = [
    {
        'adjust_date': '2026-04-01',
        'reason': '常规调仓',
        'funds': [
            {
                'fund_code': '012153',
                'fund_name': '博时研究慧选混合A',
                'pre_ratio': 15.0,
                'after_ratio': 16.0,
                'op_code': 2,
                'op_name': '加仓',
            },
        ],
    },
]


def _make_job(db, **sources) -> AdvisorPortfolioSyncJob:
    """按 ``{platform: 数据源}`` 注入构造任务（生产侧由注册表懒构造，见 #1392）。"""
    return AdvisorPortfolioSyncJob(db=db, sources=sources)


@pytest.fixture
def job(db):
    return _make_job(
        db,
        TIANTIAN=_FakeSource(
            'TIANTIAN',
            overview=TIANTIAN_OVERVIEW,
            holdings=TIANTIAN_HOLDINGS,
            industries=TIANTIAN_INDUSTRIES,
            rebalances=TIANTIAN_REBALANCES,
        ),
    )


def test_sync_end_to_end(job, db):
    """四类数据面一次落库：组合建档 + 概览/持仓/行业/历史。"""
    result = job.run(full_sync=True, targets=['XCOVSEX'])
    assert result['status'] == 'success'

    p = db.query(AdvisorPortfolio).filter_by(platform='TIANTIAN', code='XCOVSEX').one()
    assert p.name == '越海'
    assert str(p.estab_date) == '2021-07-26'
    assert p.strategy_desc == '均衡风格'
    # canonical 区间收益 + 平台特有字段（extra）+ 来源标记
    assert float(p.return_1y) == pytest.approx(12.34)
    assert p.extra == {'STATUS': '在售', 'TGCODE': 'XCOVSEX'}
    assert p.source == 'tiantian'

    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id).all()
    assert len(hs) == 2
    assert {h.fund_code for h in hs} == {'012153', '005827'}

    ind = db.query(AdvisorIndustryAlloc).filter_by(portfolio_id=p.id).all()
    assert {r.industry_name for r in ind} == {'电子', '基础化工'}

    hist = db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).all()
    assert len(hist) == 1
    assert hist[0].reason == '常规调仓'
    assert hist[0].op_name == '加仓'


def test_holdings_cover_replace(job, db):
    """同一快照日重复同步：持仓整体覆盖而非追加（贴合生产：先 seed 旧行再单次运行）。"""
    p = AdvisorPortfolio(platform='TIANTIAN', code='XCOVSEX', name='越海')
    db.add(p)
    db.flush()
    db.add_all(
        [
            AdvisorHolding(
                portfolio_id=p.id,
                as_of_date=date(2026, 4, 1),
                fund_code='012153',
                fund_name='旧持仓A',
                after_ratio=50.0,
                source='tiantian',
            ),
            AdvisorHolding(
                portfolio_id=p.id,
                as_of_date=date(2026, 4, 1),
                fund_code='011111',
                fund_name='旧持仓B',
                after_ratio=50.0,
                source='tiantian',
            ),
        ]
    )
    db.commit()

    job.run(full_sync=True, targets=['XCOVSEX'])
    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id).all()
    assert {h.fund_code for h in hs} == {'012153', '005827'}
    assert next(h for h in hs if h.fund_code == '012153').fund_name == '博时研究慧选混合A'


def test_validate_skips_empty_payload(job):
    """四类数据面全空的组合（可能已下架）应被校验剔除。"""
    empty = {
        'code': 'X',
        'platform': 'TIANTIAN',
        'overview': {},
        'holdings': {'as_of_date': None, 'funds': []},
        'industries': [],
        'rebalances': [],
    }
    assert job._validate_data([empty]) == []


def test_resolve_targets_from_db(job, db):
    """缺省 targets 时抓库内在售、且**已有适配器**的平台组合（#1392）。"""
    db.add(AdvisorPortfolio(platform='TIANTIAN', code='ABC123', name='t'))
    db.add(AdvisorPortfolio(platform='QIEMAN', code='ZH999999', name='q'))
    db.commit()
    assert set(job._resolve_targets([])) == {('ABC123', 'TIANTIAN'), ('ZH999999', 'QIEMAN')}


def test_resolve_targets_explicit_platform(job, db):
    """显式 targets 的平台解析（#1468）。

    且慢码含 LONG_WIN / J7 / SIxxxx 等非 ZH 命名空间，禁止按代码前缀判平台：
    库内以 platform 为准，库内未建档的再按 advisor_catalog 注册表兜底。
    """
    db.add(AdvisorPortfolio(platform='QIEMAN', code='LONG_WIN', name='长赢指数投资计划-150份'))
    db.commit()

    assert job._resolve_targets(['LONG_WIN']) == [('LONG_WIN', 'QIEMAN')]
    # 库内未建档、但且慢注册表收录 → QIEMAN（前缀兜底会误判为天天基金）
    assert job._resolve_targets(['J7']) == [('J7', 'QIEMAN')]
    # 库内 / 注册表均不命中 → 兜底平台（天天基金）
    assert job._resolve_targets(['UNKNOWN_TG']) == [('UNKNOWN_TG', 'TIANTIAN')]
    # 占位符被过滤
    assert job._resolve_targets(['__full__', 'LONG_WIN']) == [('LONG_WIN', 'QIEMAN')]
    assert job._infer_platform('LONG_WIN_S') == 'QIEMAN'
    assert job._infer_platform('SI000090') == 'QIEMAN'


def test_registry_covers_builtin_platforms():
    """内置适配器已注册：天天 + 且慢；未知平台报错而非静默跳过（#1392）。"""
    assert set(registered_platforms()) >= {'TIANTIAN', 'QIEMAN'}
    assert isinstance(AdvisorSourceRegistry().get('TIANTIAN'), TiantianAdvisorAdapter)
    assert isinstance(AdvisorSourceRegistry().get('QIEMAN'), QiemanAdvisorAdapter)

    with pytest.raises(UnknownAdvisorPlatform):
        AdvisorSourceRegistry().get('NOT_A_PLATFORM')

    # 注册表同时充当 SyncJob 的 adapter 槽位（sync_logs 审计读这两个方法）
    registry = AdvisorSourceRegistry()
    assert registry.get_name()
    assert registry.get_version()


def test_new_platform_only_adds_adapter(job, db):
    """验收核心：新增平台只加适配器，不改 job、不改表（#1392）。

    这里不是靠「注入 sources」取巧，而是真注册一个新平台类（蛋卷），
    由注册表发现它 —— 与日后真正接入蛋卷的路径完全一致。
    """

    @register_advisor_source
    class DanjuanAdvisorAdapter(AdvisorPortfolioSource):
        platform = 'DANJUAN'
        has_official_rebalances = False
        derive_rebalances_from_snapshots = True

        def get_name(self) -> str:
            return 'danjuan_advisor'

        def get_version(self) -> str:
            return 'v1'

        def fetch_overview(self, code: str) -> dict:
            return {'name': '蛋卷安睡全天候', 'risk_level': '中风险'}

        def fetch_holdings(self, code: str) -> dict:
            return {'as_of_date': '2026-09-10', 'funds': [{'fund_code': '000216', 'after_ratio': 100.0}]}

        def fetch_industries(self, code: str) -> list:
            return []

        def fetch_rebalances(self, code: str) -> list:
            return []

    try:
        assert 'DANJUAN' in registered_platforms()
        db.add(AdvisorPortfolio(platform='DANJUAN', code='CSI1033', name='蛋卷安睡全天候'))
        db.commit()

        result = job.run(full_sync=True, targets=['CSI1033'])
        assert result['status'] == 'success'

        p = db.query(AdvisorPortfolio).filter_by(platform='DANJUAN', code='CSI1033').one()
        assert p.name == '蛋卷安睡全天候'
        assert p.source == 'danjuan'
        assert db.query(AdvisorHolding).filter_by(portfolio_id=p.id).count() == 1
    finally:
        _SOURCES.pop('DANJUAN', None)  # 注册是全局的，测完还原，避免污染其他用例


def test_unknown_platform_skips_only_that_portfolio(job, db):
    """库内存在无适配器的平台组合：跳过该组合，不炸整轮同步（其余组合照常落库）。"""
    db.add(AdvisorPortfolio(platform='DANJUAN', code='CSI1033', name='蛋卷安睡全天候'))
    db.commit()

    result = job.run(full_sync=True, targets=['CSI1033', 'XCOVSEX'])
    assert result['status'] == 'success'

    assert db.query(AdvisorPortfolio).filter_by(platform='TIANTIAN', code='XCOVSEX').count() == 1
    # 未知平台连建档都不该发生（不是「建个空组合」）
    p = db.query(AdvisorPortfolio).filter_by(platform='DANJUAN', code='CSI1033').one()
    assert p.source is None


def test_overview_does_not_clear_existing_values(job, db):
    """抓取失败（空概览）时保留库内已有指标与来源标记，不清空。"""
    db.add(
        AdvisorPortfolio(
            platform='TIANTIAN',
            code='XCOVSEX',
            name='越海',
            max_drawdown=18.5,  # 天天 API 不提供回撤：存量值更不能被动掉
            source='tiantian',
        )
    )
    db.commit()

    # 持仓照常返回（否则四类数据面全空会被校验整条剔除，测不到「概览为空」这一支）
    empty_job = _make_job(db, TIANTIAN=_FakeSource('TIANTIAN', overview={}, holdings=TIANTIAN_HOLDINGS))
    empty_job.run(full_sync=True, targets=['XCOVSEX'])

    p = db.query(AdvisorPortfolio).filter_by(platform='TIANTIAN', code='XCOVSEX').one()
    assert float(p.max_drawdown) == pytest.approx(18.5)
    assert p.source == 'tiantian'


def test_curated_fields_never_overwritten_by_fetch(db):
    """策展字段（主理人 / 五笔钱 / 产品类型）由注册表维护，抓取**永不**覆盖（#1468）。"""
    db.add(
        AdvisorPortfolio(
            platform='TIANTIAN',
            code='XCOVSEX',
            name='越海',
            host='基民柠檬',
            allocation='longterm',
            product_type='固收+',
        )
    )
    db.commit()

    # 适配器恶意/错误地返回了策展字段，也必须与概览无关地被忽略
    evil = _FakeSource(
        'TIANTIAN',
        overview={'name': '越海', 'host': '接口给的错名字', 'product_type': '货币', 'allocation': 'liquid'},
        holdings=TIANTIAN_HOLDINGS,
    )
    _make_job(db, TIANTIAN=evil).run(full_sync=True, targets=['XCOVSEX'])

    p = db.query(AdvisorPortfolio).filter_by(platform='TIANTIAN', code='XCOVSEX').one()
    assert p.host == '基民柠檬'
    assert p.allocation == 'longterm'
    assert p.product_type == '固收+'


def test_flatten_qieman_composition():
    data = {
        'ZH012926': {
            '货币基金': {
                '持有成分': [
                    {
                        '基金代码': '000509',
                        '基金名称': '广发钱袋子A',
                        '持仓占比': '1.21%',
                        '最新更新时间': '2026-07-21 00:00:00',
                    }
                ],
                '分类占比': '1.21%',
            },
            '混合基金': {
                '持有成分': [
                    {
                        '基金代码': '006567',
                        '基金名称': '中泰星元灵活配置混合A',
                        '持仓占比': '10.30%',
                        '最新更新时间': '2026-07-21 00:00:00',
                    }
                ],
                '分类占比': '98.79%',
            },
        }
    }
    funds = flatten_qieman_composition(data)
    assert len(funds) == 2
    assert {f['fund_code'] for f in funds} == {'000509', '006567'}
    gqb = next(f for f in funds if f['fund_code'] == '000509')
    assert gqb['after_ratio'] == pytest.approx(1.21)
    assert str(funds[0]['as_of_date']) == '2026-07-21'


def test_qieman_import(db):
    """且慢实测 JSON 导入 fixture → advisor_holdings（source=qieman_manual）。"""
    with open(FIXTURE, encoding='utf-8') as f:
        data = json.load(f)
    db.add(AdvisorPortfolio(platform='QIEMAN', code='ZH012926', name='远足'))
    db.commit()

    n = import_qieman_holdings(db, data, 'ZH012926')
    assert n == 12  # 货基 1 + 混合 11，跨分类无重复

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH012926').one()
    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id, source='qieman_manual').all()
    assert len(hs) == n
    assert all(h.after_ratio is not None for h in hs)
    # 重复导入按同快照日覆盖（覆盖式更新，持仓数保持 n 而非累加）
    assert import_qieman_holdings(db, data, 'ZH012926') == n
    hs_after_second = db.query(AdvisorHolding).filter_by(portfolio_id=p.id, source='qieman_manual').all()
    assert len(hs_after_second) == n

    # 未建档组合应报错而非静默建卡
    with pytest.raises(ValueError):
        import_qieman_holdings(db, {'ZH888888': {}}, 'ZH888888')


def test_qieman_auto_fetch(db):
    """#1392/#1468 且慢自动抓取：canonical 概览 + 持仓 → 组合档案 + advisor_holdings。"""
    # 且慢假源返回的是**适配器已翻译过的 canonical**（适配器内部再调 MCP 归一化）
    src = _FakeSource(
        'QIEMAN',
        has_official_rebalances=False,
        derive_rebalances=True,
        overview={
            'name': '我要稳稳的幸福',
            'org_name': '交银施罗德',
            'risk_level': '中低风险',
            'estab_date': '2017-01-20',
            'strategy_summary': '稳健理财，力争长期稳健增值',
            'strategy_desc': '稳健理财，力争长期稳健增值',  # desc 为空时回退 summary
            'annual_return': 4.8,
            'max_drawdown': 2.79,
            'volatility': 2.36,
            'sharpe_ratio': 1.234,
            'return_1w': 0.1,
            'return_1m': 0.2,
            'return_1y': 3.3,
            'return_since_incep': 40.0,
            'extra': {'verified': True},
        },
        holdings={
            'as_of_date': '2026-09-10 00:00:00',
            'funds': [
                {'fund_code': '110011', 'fund_name': '易方达中小盘', 'after_ratio': 32.5},
                {'fund_code': '161725', 'fund_name': '招商中证白酒', 'after_ratio': 18.0},
            ],
        },
    )
    result = _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH013136'])
    assert result['status'] == 'success'

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH013136').one()
    assert p.name == '我要稳稳的幸福'
    assert p.org_name == '交银施罗德'
    assert p.risk_level == '中低风险'
    assert str(p.estab_date) == '2017-01-20'
    assert p.strategy_desc == '稳健理财，力争长期稳健增值'
    # SafeNumeric 读出为 Decimal，比较前统一转 float
    assert float(p.annual_return) == pytest.approx(4.8)
    assert float(p.max_drawdown) == pytest.approx(2.79)
    assert float(p.volatility) == pytest.approx(2.36)
    assert float(p.sharpe_ratio) == pytest.approx(1.234)
    assert float(p.return_1y) == pytest.approx(3.3)
    assert p.extra == {'verified': True}
    assert p.source == 'qieman'

    hs = db.query(AdvisorHolding).filter_by(portfolio_id=p.id, source='qieman').all()
    assert {h.fund_code for h in hs} == {'110011', '161725'}
    assert next(h for h in hs if h.fund_code == '110011').after_ratio == pytest.approx(32.5)


def test_qieman_overview_empty_keeps_curated_fields(db):
    """概览抓取为空（接口失败/无 key）时不得清空策展字段（#1468）。"""
    db.add(
        AdvisorPortfolio(
            platform='QIEMAN',
            code='ZH013136',
            name='我要稳稳的幸福',
            host='基民柠檬',
            allocation='stable',
            product_type='固收+',
        )
    )
    db.commit()
    # 概览为空但持仓有数据：校验不会整条剔除，「空概览不清空策展字段」才被测到
    src = _FakeSource(
        'QIEMAN',
        overview={},
        derive_rebalances=True,
        holdings={'as_of_date': '2026-09-10', 'funds': [{'fund_code': '110011', 'after_ratio': 32.5}]},
    )

    _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH013136'])

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH013136').one()
    assert p.host == '基民柠檬'
    assert p.allocation == 'stable'
    assert p.product_type == '固收+'


def test_qieman_derive_adjust_from_snapshots(db):
    """#1468 且慢调仓明细：且慢无历史调仓接口，由相邻两次持仓快照推导前后占比与方向。"""
    p = AdvisorPortfolio(platform='QIEMAN', code='ZH999888', name='测试组合')
    db.add(p)
    db.commit()
    # 上一快照（2026-06-30）：A 20% / B 10% / C 5%
    db.bulk_insert_mappings(
        AdvisorHolding,
        [
            {
                'portfolio_id': p.id,
                'as_of_date': date(2026, 6, 30),
                'fund_code': c,
                'fund_name': n,
                'after_ratio': r,
                'source': 'qieman',
            }
            for c, n, r in [('000001', 'A', 20.0), ('000002', 'B', 10.0), ('000003', 'C', 5.0)]
        ],
    )
    db.commit()

    # 本次快照（2026-09-11）：A 加仓至 25% / B 减至 4% / C 清仓 / D 新增 8%
    src = _FakeSource(
        'QIEMAN',
        has_official_rebalances=False,
        derive_rebalances=True,
        holdings={
            'as_of_date': '2026-09-11 00:00:00',
            'funds': [
                {'fund_code': '000001', 'fund_name': 'A', 'after_ratio': 25.0},
                {'fund_code': '000002', 'fund_name': 'B', 'after_ratio': 4.0},
                {'fund_code': '000004', 'fund_name': 'D', 'after_ratio': 8.0},
            ],
        },
    )
    _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH999888'])

    rows = {
        r.fund_code: r
        for r in db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id, adjust_date=date(2026, 9, 11)).all()
    }
    assert set(rows) == {'000001', '000002', '000003', '000004'}
    # 加仓：20 → 25
    assert float(rows['000001'].pre_ratio) == pytest.approx(20.0)
    assert float(rows['000001'].after_ratio) == pytest.approx(25.0)
    assert rows['000001'].op_name == '加仓'
    # 减仓：10 → 4
    assert rows['000002'].op_name == '减仓'
    # 清仓：5 → 0（仍记减仓，after=0）
    assert rows['000003'].op_name == '减仓'
    assert float(rows['000003'].after_ratio) == pytest.approx(0.0)
    # 新增：0 → 8
    assert rows['000004'].op_name == '新增'
    assert float(rows['000004'].pre_ratio) == pytest.approx(0.0)
    assert all(r.source == 'qieman' for r in rows.values())


def test_qieman_first_snapshot_creates_no_adjust(db):
    """首次快照没有前值可对比 → 不编造调仓记录（#1468）。"""
    db.add(AdvisorPortfolio(platform='QIEMAN', code='ZH999777', name='首建组合'))
    db.commit()
    src = _FakeSource(
        'QIEMAN',
        has_official_rebalances=False,
        derive_rebalances=True,
        holdings={
            'as_of_date': '2026-09-11 00:00:00',
            'funds': [{'fund_code': '000001', 'fund_name': 'A', 'after_ratio': 50.0}],
        },
    )

    _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH999777'])

    p = db.query(AdvisorPortfolio).filter_by(platform='QIEMAN', code='ZH999777').one()
    assert db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).count() == 0
    assert db.query(AdvisorHolding).filter_by(portfolio_id=p.id).count() == 1


def _seed_drift_snapshot(db, code: str, as_of: date, ratios: dict) -> AdvisorPortfolio:
    """落一条 QIEMAN 组合 + 一条历史持仓快照（模拟"上次抓取"的结果）。"""
    p = AdvisorPortfolio(platform='QIEMAN', code=code, name='漂移组合')
    db.add(p)
    db.commit()
    db.bulk_insert_mappings(
        AdvisorHolding,
        [
            {
                'portfolio_id': p.id,
                'as_of_date': as_of,
                'fund_code': c,
                'fund_name': c,
                'after_ratio': r,
                'source': 'qieman',
            }
            for c, r in ratios.items()
        ],
    )
    db.commit()
    return p


def _derived_source(as_of: str, ratios: dict) -> _FakeSource:
    return _FakeSource(
        'QIEMAN',
        has_official_rebalances=False,
        derive_rebalances=True,
        holdings={
            'as_of_date': as_of,
            'funds': [{'fund_code': c, 'fund_name': c, 'after_ratio': r} for c, r in ratios.items()],
        },
    )


def test_qieman_net_value_drift_writes_no_adjust(db):
    """#1622 回归：占比是市值口径、每天随净值微漂（实测 p99≈0.23pp）——不得记成调仓。

    原实现的症状：每个交易日都写满一整组「调仓」（没变的写 op=5 持平），
    自选页抽屉里因此每天一条调仓历史。
    """
    p = _seed_drift_snapshot(db, 'ZH0001622', date(2026, 9, 17), {'000001': 10.30, '000002': 5.50, '000003': 3.10})
    src = _derived_source('2026-09-18 00:00:00', {'000001': 10.38, '000002': 5.42, '000003': 3.18})

    _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH0001622'])

    assert db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).count() == 0, '净值漂移被误记为调仓'
    # 快照本身仍照常落库（持仓序列不受影响）
    assert db.query(AdvisorHolding).filter_by(portfolio_id=p.id, as_of_date=date(2026, 9, 18)).count() == 3


def test_qieman_only_real_changes_recorded_no_flat_rows(db):
    """只有超阈值的真实变化入账，且**不写 op=5 持平行**（没变不是调仓）。"""
    p = _seed_drift_snapshot(db, 'ZH0001623', date(2026, 9, 17), {'000001': 10.0, '000002': 5.0, '000003': 3.0})
    # 000001 真实加仓 2.5pp；000002/000003 只有漂移
    src = _derived_source('2026-09-18 00:00:00', {'000001': 12.5, '000002': 5.1, '000003': 2.9})

    _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH0001623'])

    rows = db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).all()
    assert [r.fund_code for r in rows] == ['000001']
    assert rows[0].op_name == '加仓'
    assert float(rows[0].pre_ratio) == pytest.approx(10.0)
    assert float(rows[0].after_ratio) == pytest.approx(12.5)
    assert all(r.op_code != 5 for r in rows), '不得再写「持平」行'


def test_qieman_sub_threshold_change_is_ignored(db):
    """低于阈值的持仓变化**有意不记录**（宁缺勿噪）——阈值语义的显式钉住。"""
    p = _seed_drift_snapshot(db, 'ZH0001624', date(2026, 9, 17), {'000001': 10.0})
    # 新增一只但仓位只有 0.4pp（< 0.5pp 阈值）
    src = _derived_source('2026-09-18 00:00:00', {'000001': 10.2, '000009': 0.4})

    _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH0001624'])

    assert db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).count() == 0


def test_qieman_clear_position_beyond_threshold_is_recorded(db):
    """清仓超过阈值仍要记（回归：过滤逻辑不能把"清仓"这类真实事件也滤掉）。"""
    p = _seed_drift_snapshot(db, 'ZH0001625', date(2026, 9, 17), {'000001': 6.0, '000002': 4.0})
    src = _derived_source('2026-09-18 00:00:00', {'000001': 6.05})

    _make_job(db, QIEMAN=src).run(full_sync=True, targets=['ZH0001625'])

    rows = db.query(AdvisorAdjustHistory).filter_by(portfolio_id=p.id).all()
    assert [r.fund_code for r in rows] == ['000002']
    assert rows[0].op_name == '减仓'
    assert float(rows[0].after_ratio) == pytest.approx(0.0)


def test_job_rejects_single_platform_adapter(db):
    """#1392 起一任务多平台：把单平台适配器塞进 adapter 槽位应报错（否则审计口径会失真）。"""
    with pytest.raises(TypeError):
        AdvisorPortfolioSyncJob(TiantianAdvisorAdapter(), db)
