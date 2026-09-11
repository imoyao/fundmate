# -*- coding: utf-8 -*-
"""测试跨渠道关联（#1285 §3.8 / #1413）：名称归一、最长核心名匹配、两层落库、保护人工关联。

配对的「错配回归」用例取自 2026-09-11 实测样本——旧白名单实现把它们记到母指数名下。
"""

from app.domains.funds.models import ChannelLink, Fund, FundCompany
from app.domains.indices.models import IndexCatalog
from app.services.sync.jobs.channel_link_job import ChannelLinkSyncJob
from app.services.sync.name_match import ChannelNameMatcher, normalize, pick_manager

COMPANIES = ['易方达基金', '嘉实基金', '华泰柏瑞基金管理有限公司', '国泰基金']
INDEXES = [
    ('000300', '沪深300'),
    ('000919', '沪深300价值'),
    ('000905', '中证500'),
    ('000852', '中证1000'),
    ('000903', '中证100'),
    ('931160', '通信设备'),
    ('000015', '红利指数'),  # 泛词「红利」——必须被黑名单挡住
    ('399606', '创业板R'),  # 泛词「创业板」——同上
    ('932143', '航空航天'),
    ('399967', '中证军工'),  # 与「军工龙头」核心名同长 4 字，且**故意排在前面**
    ('931066', '军工龙头'),  # ——若只按长度排序，「中证军工」会抢先（回归用例）
]


def _matcher() -> ChannelNameMatcher:
    return ChannelNameMatcher(COMPANIES, INDEXES)


# ── 归一化 ──


def test_normalize_strips_company_noise_and_share_class():
    tokens = _matcher().company_tokens
    assert normalize('国泰中证全指通信设备ETF', tokens) == '中证全指通信设备'
    assert normalize('通信ETF国泰', tokens) == '通信'  # 东财简称：指数名已丢，这是覆盖率差异的根因
    assert normalize('华夏沪深300ETF联接A', tokens) == '沪深300'
    # 尾部字母只在噪声词清完后剥：否则「货币ETF」的 F 会被当份额类别切掉
    assert normalize('易方达货币ETF', tokens) == '货币'


def test_pick_manager_from_name_prefix():
    tokens = _matcher().company_tokens
    assert pick_manager('嘉实中证500ETF联接A', tokens) == '嘉实'
    assert pick_manager('华泰柏瑞沪深300ETF联接A', tokens) == '华泰柏瑞'
    assert pick_manager('某某ETF联接A', tokens) is None


# ── 匹配 ──


def test_match_longest_core_wins():
    """「中证100」不得吞掉「中证1000」——取最长核心名。"""
    m = _matcher()
    assert m.match_index('中证1000ETF').index_code == '000852'
    assert m.match_index('中证100ETF').index_code == '000903'


def test_match_theme_index_beats_parent_index():
    """旧实现把「沪深300价值ETF」记到母指数「沪深300」——最长核心名修正之。"""
    m = _matcher()
    hit = m.match_index('沪深300价值ETF申万菱信')
    assert hit.index_code == '000919'
    assert hit.core == '沪深300价值'


def test_match_full_name_from_ths_is_what_unlocks_coverage():
    """东财简称「通信ETF国泰」匹不到；同花顺全称「国泰中证全指通信设备ETF」能匹到。"""
    m = _matcher()
    assert m.match_index('通信ETF国泰') is None
    assert m.match_index('国泰中证全指通信设备ETF').index_code == '931160'


def test_generic_core_blocked_otherwise_mismatched():
    """泛词黑名单：否则「红利」「创业板」这类 2~3 字泛名会吞掉更长语义。"""
    m = _matcher()
    assert m.match_index('广发标普港股通低波红利ETF') is None
    assert m.match_index('国泰创业板软件ETF') is None
    assert m.match_index('某某主题ETF') is None


def test_long_core_still_matchable():
    assert _matcher().match_index('航空航天ETF南方').index_code == '932143'


def test_match_same_length_prefers_suffix_aligned():
    """同长度核心名取位置最靠后者——否则命中谁取决于名录行序（2026-09-11 实测错配）。

    「广发中证军工龙头ETF」归一为「中证军工龙头」，`中证军工`(399967) 与
    `军工龙头`(931066) 核心名同为 4 字；仅按长度排序时前者按行序抢先 → 错配。
    """
    m = _matcher()
    hit = m.match_index('广发中证军工龙头ETF')
    assert hit.index_code == '931066'
    assert hit.core == '军工龙头'


# ── Job ──


class _FakeAdapter:
    def __init__(self, em=None, ths=None):
        self._em = em if em is not None else []
        self._ths = ths if ths is not None else []

    def fetch_etf_list(self):
        return self._em

    def fetch_etf_list_ths(self):
        return self._ths


def _seed(db):
    for i, name in enumerate(COMPANIES):
        db.add(FundCompany(code=f'C{i}', name=name))
    for code, name in INDEXES:
        db.add(IndexCatalog(index_code=code, name=name, exchange='CSI', source='csindex'))
    db.commit()


def test_channel_link_job_builds_both_layers(db):
    _seed(db)
    db.add(Fund(fund_code='000051', name='华夏沪深300ETF联接A'))
    db.add(Fund(fund_code='000008', name='嘉实中证500ETF联接A'))
    db.commit()

    adapter = _FakeAdapter(
        em=[
            {'code': '510300', 'name': '沪深300ETF华泰柏瑞'},
            {'code': '159915', 'name': '创业板ETF'},  # 泛词 → 不入库
            {'code': '512999', 'name': '某某主题ETF'},  # 无命中 → 不入库
        ],
        ths=[
            {'code': '510300', 'name': '华泰柏瑞沪深300ETF'},
            {'code': '515880', 'name': '国泰中证全指通信设备ETF'},
        ],
    )
    result = ChannelLinkSyncJob(adapter, db).run()
    assert result['status'] == 'success'

    index_etf = db.query(ChannelLink).filter_by(link_type='index_etf').all()
    assert {(r.from_symbol, r.to_symbol) for r in index_etf} == {('000300', '510300'), ('931160', '515880')}
    assert next(r for r in index_etf if r.to_symbol == '510300').match_type == 'name_longest_core'

    feeders = db.query(ChannelLink).filter_by(link_type='etf_feeder').all()
    assert {(r.from_symbol, r.to_symbol) for r in feeders} == {('510300', '000051')}


def test_feeder_ambiguity_resolved_by_same_manager(db):
    """同核心多只 ETF 时用管理人消歧；消歧不唯一则放弃（宁可留 `—` 也不错配）。"""
    _seed(db)
    db.add(Fund(fund_code='000051', name='华夏沪深300ETF联接A'))
    db.add(Fund(fund_code='000052', name='某某沪深300ETF联接A'))  # 管理人不在候选名单 → 放弃
    db.commit()

    adapter = _FakeAdapter(
        ths=[
            {'code': '510300', 'name': '华泰柏瑞沪深300ETF'},
            {'code': '510301', 'name': '嘉实沪深300ETF'},
        ]
    )
    ChannelLinkSyncJob(adapter, db).run()
    feeders = db.query(ChannelLink).filter_by(link_type='etf_feeder').all()
    # 华夏：候选里无「华夏」→ 放弃；某某：非管理人前缀 → 放弃
    assert feeders == []


def test_channel_link_job_preserves_manual_links(db):
    """覆盖式重建只能清 auto 行——人工维护的关联不能被任务抹掉。"""
    _seed(db)
    db.add(
        ChannelLink(
            link_type='index_etf',
            from_symbol='000300',
            to_symbol='999999',
            match_type='manual',
            source='manual',
        )
    )
    db.commit()

    adapter = _FakeAdapter(ths=[{'code': '510300', 'name': '华泰柏瑞沪深300ETF'}])
    ChannelLinkSyncJob(adapter, db).run()

    manual = db.query(ChannelLink).filter_by(source='manual').all()
    assert len(manual) == 1
    assert db.query(ChannelLink).filter_by(source='auto').count() == 1


def test_empty_etf_list_is_allowed(db):
    """ETF 名录拉取失败（网络/接口变更）不应让任务失败，只跳过本轮。"""
    _seed(db)
    result = ChannelLinkSyncJob(_FakeAdapter(), db).run()
    assert result['status'] == 'success'
    assert db.query(ChannelLink).count() == 0
