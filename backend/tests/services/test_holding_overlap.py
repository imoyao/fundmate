# -*- coding: utf-8 -*-
"""测试组合内基金持仓重叠度分析（#2604）。

覆盖的**硬口径**（每条都对应生产口径的坑，见 `services/holding_overlap.py` 模块头）：

1. **两两配对** —— 只有持仓明细的基金之间才谈得上「重叠」；
2. **两个口径都出** —— ``jaccard``（集合口径）与 ``weighted_overlap``（加权口径，单位
   百分点）同时给出，二者互补、不可互相替代；
3. **``holding_basis`` 不混算** —— 季报前十大（``top10``）与半年报全量（``full``）
   的持仓集合天然不同口径，混算出的重叠度**系统性偏低**，会给用户「我的基金不重叠」
   的**错误安心**。跨口径的对**不计算**，但要如实给出被跳过的对数；
4. **报告期各取各的最新** —— 不强制对齐共同日期（对齐会把报告期落后的基金整体排除）；
5. **同基金多账户先合并** —— 同一只基金在多个账户下不能被当成多只（否则自己跟
   自己算出 100% 的假重叠）；
6. **按 ``stock_code`` 比对** —— ``stock_name`` 只作展示（同一只股票在不同基金里的
   名称写法可能不一致）；
7. **诚实降级** —— 无持仓明细返回空列表，不抛异常、不拿 0 冒充。

造数方式沿用 `tests/services/test_penetration.py`（``FundHolding`` 直写）与
`tests/conftest.py` 的 ``make_position`` 夹具；不另造 fixture 体系。

**跨域说明**：``positions``（持仓）属 user 域、``fund_holdings``（持仓明细）属 market 域，
本模块的取数是「应用层两步法」（先聚合持仓、再查明细），**不做 SQL JOIN**。
测试库里两域由 `tests/conftest.py` 统一重定向，故同会话可见。
"""

from datetime import date

import pytest

from app.domains.funds.models import FundHolding
from app.services.holding_overlap import (
    MIN_OVERLAP_AMOUNT_CENTS,
    WATCH_WEIGHTED_PCT,
    _apply_amount_gate,
    _classify_overlap,
    _empty_result,
    portfolio_holding_overlap,
)

REPORT_DATE = date(2026, 6, 30)

#: 两只基金的示例持仓明细（共同重仓 600519 贵州茅台 + 000858 五粮液）。
#: 故意让两只基金各有一只**不重叠**的股票，才能把 jaccard 算成 2/4 而不是 2/2。
_A_HOLDINGS = [
    ('600519', '贵州茅台', 10.0),
    ('000858', '五粮液', 8.0),
    ('601318', '中国平安', 5.0),
]
_B_HOLDINGS = [
    ('600519', '贵州茅台股份', 6.0),  # 名称写法与 A 不同（口径 6：只按 stock_code 比对）
    ('000858', '五粮液', 4.0),
    ('300750', '宁德时代', 3.0),
]


# ── 造数工具 ──────────────────────────────────────────────────────────────


def _holding(db, fund_code, stock_code, stock_name, ratio, *, basis='full', period='2026Q2'):
    """写入一行基金持仓明细。

    ``ratio`` 传 ``None`` 可造出「占比缺失」的脏行——那是「排除并计数」纪律的输入。
    """
    db.add(
        FundHolding(
            fund_code=fund_code,
            report_period=period,
            report_date=REPORT_DATE,
            holding_basis=basis,
            stock_code=stock_code,
            stock_name=stock_name,
            ratio=ratio,
            source='eastmoney',
        )
    )


def _seed_two_funds(db, make_position, *, period_a='2026Q2', period_b='2026Q2', basis_b='full'):
    """造两只基金（000001 / 000002）的持仓 + 持仓明细，返回两只基金代码。

    ``period_*`` / ``basis_b`` 可调，用于构造「报告期错配」与「口径不同」两种场景。
    """
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    make_position(symbol='000002', asset_type='fund', name='基金乙', quantity=500, current_price=3.0)
    for stock_code, stock_name, ratio in _A_HOLDINGS:
        _holding(db, '000001', stock_code, stock_name, ratio, basis='full', period=period_a)
    for stock_code, stock_name, ratio in _B_HOLDINGS:
        _holding(db, '000002', stock_code, stock_name, ratio, basis=basis_b, period=period_b)
    db.commit()


def _find_pair(pairs, code_a, code_b):
    """从 pairs 里找出（无序）指定的两只基金构成的对；找不到返回 None。"""
    for pair in pairs:
        if {pair['fund_code_a'], pair['fund_code_b']} == {code_a, code_b}:
            return pair
    return None


# ── 1. 两基金重叠度按共同重仓股计算 ────────────────────────────────────────


def test_两基金重叠度按共同重仓股计算(db, make_position):
    """有共同重仓股的一对，重叠度必须 > 0，且共同重仓股明细正确。"""
    _seed_two_funds(db, make_position)

    result = portfolio_holding_overlap(db, family_id=1)

    assert result['fund_count'] == 2
    assert len(result['pairs']) == 1
    pair = result['pairs'][0]
    assert pair['weighted_overlap'] > 0
    # 共同重仓股：600519 与 000858（001318 / 300750 各只在一边）
    assert {item['stock_code'] for item in pair['common_holdings']} == {'600519', '000858'}


# ── 2. 同时输出集合口径与加权口径 ──────────────────────────────────────────


def test_同时输出集合口径与加权口径(db, make_position):
    """jaccard 与 weighted_overlap 都必须给出，且数值符合手算。

    A = {600519:10, 000858:8, 601318:5}，B = {600519:6, 000858:4, 300750:3}
    - jaccard = |A∩B| / |A∪B| = 2 / 4 = 0.5
    - weighted = min(10,6) + min(8,4) = 6 + 4 = 10（百分点）
    """
    _seed_two_funds(db, make_position)

    result = portfolio_holding_overlap(db, family_id=1)

    pair = result['pairs'][0]
    assert pair['jaccard'] == pytest.approx(0.5)
    assert pair['weighted_overlap'] == pytest.approx(10.0)
    # 加权口径的每个分量都要对得上（min(ratio_a, ratio_b)）
    by_code = {item['stock_code']: item for item in pair['common_holdings']}
    assert by_code['600519']['ratio_a'] == pytest.approx(10.0)
    assert by_code['600519']['ratio_b'] == pytest.approx(6.0)
    assert by_code['600519']['min_ratio'] == pytest.approx(6.0)
    assert by_code['000858']['ratio_a'] == pytest.approx(8.0)
    assert by_code['000858']['ratio_b'] == pytest.approx(4.0)
    assert by_code['000858']['min_ratio'] == pytest.approx(4.0)


# ── 3. 全量与前十大不混算 ──────────────────────────────────────────────────


def test_全量与前十大不混算(db, make_position):
    """一只 full 一只 top10 的基金对**不出现在 pairs 里**，且跳过计数正确。

    混算出来的重叠度**系统性偏低**（季报只有前十大，重仓集合天然是全量的子集），
    会给用户「我的基金不重叠」的错误安心——宁可少给一对，不可给一个偏低的数。
    """
    _seed_two_funds(db, make_position, basis_b='top10')

    result = portfolio_holding_overlap(db, family_id=1)

    assert result['pairs'] == []
    assert result['skipped_basis_mismatch'] == 1
    # 两只基金各自的口径仍要如实带出（前端据此解释「为什么没给结论」）
    assert result['fund_count'] == 2


def test_同口径的两只基金不计入跳过数(db, make_position):
    """同为 full 的两只基金正常出结果，跳过计数必须为 0（计数只记「口径不同」）。"""
    _seed_two_funds(db, make_position)

    result = portfolio_holding_overlap(db, family_id=1)

    assert len(result['pairs']) == 1
    assert result['skipped_basis_mismatch'] == 0
    assert result['pairs'][0]['holding_basis'] == 'full'


# ── 4. 报告期错配如实暴露 ──────────────────────────────────────────────────


def test_报告期错配如实暴露(db, make_position):
    """两只基金报告期不同（2026Q2 / 2026Q1）时，各自带自己的报告期，且仍能算出重叠。

    强制对齐共同日期会把报告期落后的基金整体排除（新建仓基金报告期天然滞后），
    反而低估重叠——故报告期**各取各的最新**。
    """
    _seed_two_funds(db, make_position, period_a='2026Q2', period_b='2026Q1')

    result = portfolio_holding_overlap(db, family_id=1)

    assert len(result['pairs']) == 1
    pair = result['pairs'][0]
    assert {pair['report_period_a'], pair['report_period_b']} == {'2026Q2', '2026Q1'}
    # 报告期不同不影响同口径（都是 full）的可比性
    assert pair['holding_basis'] == 'full'
    assert pair['weighted_overlap'] > 0


def test_只取每只基金各自最新的报告期(db, make_position):
    """同一只基金有多期明细时，只用**它自己最新**的那期算重叠。

    造数：000001 有 2026Q1 / 2026Q2 两期，000002 只有 2026Q1。
    期望：000001 取 2026Q2（其最新），000002 取 2026Q1；
    交集按 2026Q2 的 600519(10%) 与 2026Q1 的 600519(6%) 计算。
    """
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    make_position(symbol='000002', asset_type='fund', name='基金乙', quantity=500, current_price=3.0)
    # 000001 的旧报告期（不该被采用）
    _holding(db, '000001', '600519', '贵州茅台', 1.0, period='2026Q1')
    # 000001 的最新报告期
    _holding(db, '000001', '600519', '贵州茅台', 10.0, period='2026Q2')
    _holding(db, '000001', '000858', '五粮液', 8.0, period='2026Q2')
    # 000002 只有 2026Q1
    _holding(db, '000002', '600519', '贵州茅台', 6.0, period='2026Q1')
    _holding(db, '000002', '300750', '宁德时代', 3.0, period='2026Q1')
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    pair = _find_pair(result['pairs'], '000001', '000002')
    assert pair is not None
    assert pair['report_period_a'] == '2026Q2'
    assert pair['report_period_b'] == '2026Q1'
    # 只按 2026Q2 的占比算：min(10, 6) = 6；旧期的 1.0 不参与
    assert pair['weighted_overlap'] == pytest.approx(6.0)
    # 000858 只在 000001 的 2026Q2 里，000002 没有 → 不是共同重仓股
    assert {item['stock_code'] for item in pair['common_holdings']} == {'600519'}


# ── 5. 同基金多账户先合并 ──────────────────────────────────────────────────


def test_同基金多账户先合并(db, make_position):
    """同一只基金在两个账户下各有一条持仓 → 算作**一只**基金，不与自己算 100% 重叠。

    `get_fund_aggregation` 已按 symbol 跨渠道合并；本层再按 6 位业务码二次合并，
    兜住「OTC:004369」与「004369」两种写法——不归一就会自比出 100% 的假重叠。
    """
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    make_position(symbol='OTC:000001', asset_type='fund', name='基金甲', quantity=500, current_price=2.0)
    _holding(db, '000001', '600519', '贵州茅台', 10.0)
    _holding(db, '000001', '000858', '五粮液', 8.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    # 合并后只有一只基金 → 没有可配的对
    assert result['fund_count'] == 1
    assert result['pairs'] == []
    # 两笔市值合并计入总额（1000×2.0 + 500×2.0 = 3000 元 = 300000 分）
    assert result['total_market_value_cents'] == 300000


# ── 6. 返回共同重仓股明细 ──────────────────────────────────────────────────


def test_返回共同重仓股明细(db, make_position):
    """共同重仓股明细要含 stock_code / ratio_a / ratio_b，并按 min_ratio 降序。"""
    _seed_two_funds(db, make_position)

    result = portfolio_holding_overlap(db, family_id=1)

    holdings = result['pairs'][0]['common_holdings']
    assert holdings
    for item in holdings:
        assert 'stock_code' in item
        assert 'ratio_a' in item
        assert 'ratio_b' in item
        assert 'min_ratio' in item
        assert item['min_ratio'] == pytest.approx(min(item['ratio_a'], item['ratio_b']))
    # 排序：重合仓位重的排前面（600519 的 min=6 > 000858 的 min=4）
    assert [item['stock_code'] for item in holdings] == ['600519', '000858']


def test_名称写法不一致仍按股票代码配对(db, make_position):
    """同一只股票在不同基金里名称写法不同（贵州茅台 / 贵州茅台股份）也要配上。

    比对**以 stock_code 为准**——按名字比对会漏配（口径 5）。
    """
    _seed_two_funds(db, make_position)

    result = portfolio_holding_overlap(db, family_id=1)

    codes = {item['stock_code'] for item in result['pairs'][0]['common_holdings']}
    assert '600519' in codes


# ── 7. 无持仓明细时降级为空列表 ────────────────────────────────────────────


def test_无持仓明细时降级为空列表(db, make_position):
    """有持仓但**无持仓明细** → 空 pairs 列表，不抛异常、不返回 500。

    此时覆盖率如实为 0，未覆盖清单如实列出持仓（不拿 0 冒充「重叠 0%」）。
    """
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    make_position(symbol='000002', asset_type='fund', name='基金乙', quantity=500, current_price=3.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    assert result['pairs'] == []
    assert result['fund_count'] == 0
    assert result['coverage_pct'] == 0.0
    # 无明细的持仓要如实列进 uncovered（含货基这类「本质无股票敞口」的标的）
    assert {item['symbol'] for item in result['uncovered']} == {'000001', '000002'}
    # 取数本身没失败 → 不是降级，只是没数据
    assert result['degraded'] is False
    assert result['source'] == 'fund_holdings'


def test_无任何持仓时返回空结构(db):
    """组合里一只基金都没有 → 空结构，不抛异常。"""
    result = portfolio_holding_overlap(db, family_id=1)

    assert result['pairs'] == []
    assert result['fund_count'] == 0
    assert result['total_market_value_cents'] == 0
    assert result['coverage_pct'] == 0.0
    assert result['uncovered'] == []
    assert result['degraded'] is False


def test_可比基金不足两只时不算降级(db, make_position):
    """只有一只基金有明细时：``fund_count == 1``、``pairs`` 空、``degraded`` 仍为 False。

    口径：``degraded`` 的语义严格是「**取数失败**」（与 ``funds/views.py`` 既有用法一致）。
    「可比基金不足 2 只」是**样本不足**、不是取数失败——两者都表现为 ``pairs == []``，
    只能靠 ``degraded`` 与 ``fund_count`` 区分开。若把样本不足也塞进 ``degraded``，
    消费方就分不清「暂时取不到」与「算出来没有」，等于把两个语义搅在一起。
    """
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    _holding(db, '000001', '600519', '贵州茅台', 10.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    assert result['fund_count'] == 1
    assert result['pairs'] == []
    assert result['degraded'] is False
    # 覆盖率是 100（唯一这只基金有明细），缺口清单为空
    assert result['coverage_pct'] == 100.0
    assert result['uncovered'] == []


# ── 8. 占比缺失的行：排除并计数 ────────────────────────────────────────────


def test_占比缺失的行被排除并计数(db, make_position):
    """``ratio`` 为 NULL 的持仓行**排除并计数**，不得当 0 参与计算。

    当 0 参与会系统性低估重叠度（同样是错误安心）；且它会让 jaccard 的集合与
    weighted 的求和跑在**不同**的行集上，两个口径就不可比了。
    """
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    make_position(symbol='000002', asset_type='fund', name='基金乙', quantity=500, current_price=3.0)
    _holding(db, '000001', '600519', '贵州茅台', 10.0)
    _holding(db, '000001', '999999', '占比缺失的票', None)  # 脏行
    _holding(db, '000002', '600519', '贵州茅台', 6.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    assert result['skipped_null_ratio'] == 1
    pair = result['pairs'][0]
    # 缺失行不参与 jaccard 的集合（否则 A 多一只票，交集/并集都被污染）
    assert pair['jaccard'] == pytest.approx(1.0)  # |A∩B|=1, |A∪B|=1
    assert pair['weighted_overlap'] == pytest.approx(6.0)  # min(10, 6)
    assert {item['stock_code'] for item in pair['common_holdings']} == {'600519'}


# ── 9. 取数失败时的诚实降级 ────────────────────────────────────────────────


def test_明细查询失败时降级而不抛异常(db, make_position, monkeypatch):
    """持仓明细查询抛异常 → 降级（degraded=True）+ 明细维度置空，不 500。"""
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    db.commit()

    def _boom(*args, **kwargs):
        raise RuntimeError('模拟明细取数失败')

    monkeypatch.setattr('app.services.holding_overlap._load_holding_map', _boom)

    result = portfolio_holding_overlap(db, family_id=1)

    assert result['degraded'] is True
    assert result['pairs'] == []
    assert result['coverage_pct'] == 0.0
    # 市值已知就如实保留（前端据此说明「不是没有持仓，是明细取不到」）
    assert result['total_market_value_cents'] == 200000
    assert [item['symbol'] for item in result['uncovered']] == ['000001']


# ── 10. 配置重复提示（#866）：双口径阈值分级 ────────────────────────────────


@pytest.mark.parametrize(
    ('jaccard', 'weighted', 'expected'),
    [
        (0.10, 20.00, 'duplicate'),  # 加权口径正好踩线：阈值是 >=，边界必须命中
        (0.50, 0.00, 'duplicate'),  # 只靠集合口径越线（同一指数的两只基金）
        (0.10, 19.99, 'watch'),  # 差 0.01 就降档——档位边界不许含糊
        (0.30, 0.00, 'watch'),  # 只靠集合口径到 watch
        (0.29, 9.99, 'low'),  # 两个口径都没到
        (0.00, 0.00, 'low'),
    ],
)
def test_重叠定级按双口径阈值(jaccard, weighted, expected):
    """任一口径越线即提示，但两档阈值都必须踩准。

    只用单一口径会漏：jaccard 只看「重合几只股票」（同指数的两只基金恒为 1.0），
    weighted 只看「重合多少仓位」（前十大里重合 2 只但都很重也能很高）。
    """
    level, _reason = _classify_overlap(jaccard, weighted, 3)

    assert level == expected


def test_定级理由区分仓位重叠与标的重复():
    """两种越线必须给不同理由，否则用户不知道是「仓位重」还是「股票重」。"""
    _, reason_weighted = _classify_overlap(0.10, 25.0, 6)
    assert '仓位' in reason_weighted
    assert '6' in reason_weighted

    # 仅集合口径越线：必须点明「仓位有差异」，否则用户看到 weighted 很低却被判重复会困惑
    _, reason_jaccard = _classify_overlap(0.60, 2.0, 6)
    assert '重仓股' in reason_jaccard
    assert '仓位有差异' in reason_jaccard

    # low 也要给理由：它现在会出现在弱提醒区里，没有理由用户不知道它为什么在那。
    # 措辞必须点明是「仓位线」而不是金额线——弱提醒里也有金额上万、只是比例低的对。
    level_low, reason_low = _classify_overlap(0.01, 1.0, 1)
    assert level_low == 'low'
    assert '1.0%' in reason_low
    assert f'{WATCH_WEIGHTED_PCT:.0f}% 仓位线' in reason_low


# ── 11. 同一基金不同份额：不是配置重复（#866 的假警报闸门）──────────────────


def test_同一基金的不同份额标记为份额重复而非配置重复(db, make_position):
    """A/C 份额持仓逐行相同 ⇒ ``same-series``，**不进** ``duplicate_count``。

    真实库里就有这种对（161725 / 012414 招商中证白酒 A/C，实测 weighted 86.48）。
    不摘出来，配置重复提示的第一屏就是假警报——用户只买了同一只基金的两个份额。
    """
    make_position(symbol='161725', asset_type='fund', name='招商中证白酒A', quantity=1000, current_price=1.0)
    make_position(symbol='012414', asset_type='fund', name='招商中证白酒C', quantity=1000, current_price=1.0)
    for fund_code in ('161725', '012414'):
        _holding(db, fund_code, '600519', '贵州茅台', 15.0)
        _holding(db, fund_code, '000858', '五粮液', 12.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    pair = _find_pair(result['pairs'], '161725', '012414')
    assert pair is not None
    assert pair['overlap_level'] == 'same-series'
    assert '份额' in pair['overlap_reason']
    assert result['duplicate_count'] == 0
    # 数值本身仍如实给出：用户也该知道这两笔买的是同一只基金
    assert pair['weighted_overlap'] == pytest.approx(27.0)


def test_同指数不同公司不被误判成份额重复(db, make_position):
    """持仓集合相同但占比不同 ⇒ **不是**同一只基金，必须照常走阈值判定。

    参照实测：017513 广发北证50 / 023887 永赢北证50 集合完全相同、占比只差 0.07。
    若用「``jaccard == 1`` 即为同份额」当判据，就会把这种**真重复**藏起来。

    仓位刻意给到各 ¥5,000：金额闸门（¥1,000）之下，这一对本来该被降级成 ``trivial``，
    就测不到「比例定级是否正确」了。闸门与定级是两层，这里测的是定级那一层。
    """
    make_position(symbol='017513', asset_type='fund', name='广发北证50C', quantity=5000, current_price=1.0)
    make_position(symbol='023887', asset_type='fund', name='永赢北证50C', quantity=5000, current_price=1.0)
    _holding(db, '017513', '600519', '贵州茅台', 15.0)
    _holding(db, '017513', '000858', '五粮液', 12.0)
    _holding(db, '023887', '600519', '贵州茅台', 14.93)  # 与 15.0 只差 0.07
    _holding(db, '023887', '000858', '五粮液', 12.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    pair = _find_pair(result['pairs'], '017513', '023887')
    assert pair is not None
    assert pair['overlap_level'] != 'same-series'
    # 同一指数的两只基金确实是重复配置，必须判出来（weighted = 14.93 + 12 = 26.93）
    assert pair['overlap_level'] == 'duplicate'
    # 重复金额 = 5000×14.93% + 5000×12% = 746.5 + 600 = ¥1,346.5
    assert pair['overlap_amount_cents'] == 134650
    assert result['duplicate_count'] == 1


# ── 12. 换手率口径：如实声明，不假装判定 ────────────────────────────────────


def test_口径声明交代换手率局限(db, make_position):
    """卡面 #866 的硬约束：「只对低换手基金有效」必须交代，且不许假装做了基金级判定。

    基金级换手率并未入库（现有 turnover 全是市场/行业拥挤度与用户交易换手），
    所以只能声明局限——**输出「哪只高换手」才是错的**。
    """
    _seed_two_funds(db, make_position)

    result = portfolio_holding_overlap(db, family_id=1)

    text = ' '.join(result['caveats'])
    assert '高换手' in text
    assert '换手率' in text  # 明说没接入，而不是含糊过去
    assert '快照' in text  # 报告期滞后这层也要说
    # 只声明、不判定：出参里不许出现「哪只基金高换手」这类无数据支撑的字段
    assert not any('turnover' in key.lower() for key in result)


def test_空结果的骨架也带口径声明():
    """口径声明描述的是**固有**局限，与取数成败无关——降级时也不能丢。"""
    result = _empty_result()

    assert result['caveats']
    assert result['duplicate_count'] == 0
    assert result['weak_count'] == 0
    # 分档线下发在出参里，前端不必自己再写一个数（两处各写一份迟早不一致）
    assert result['min_overlap_amount_cents'] == MIN_OVERLAP_AMOUNT_CENTS
    assert result['pairs'] == []


# ── 13. 金额分档：几块钱的观察仓降为「弱提醒」（#866 追加）────────────────────


@pytest.mark.parametrize(
    ('level', 'amount_cents', 'expected'),
    [
        ('duplicate', MIN_OVERLAP_AMOUNT_CENTS, 'duplicate'),  # 正好踩线：判据是 >=
        ('duplicate', MIN_OVERLAP_AMOUNT_CENTS - 1, 'trivial'),  # 差 1 分就不过闸
        ('watch', 0, 'trivial'),
        ('low', 0, 'trivial'),
        ('same-series', 0, 'same-series'),  # 份额重复是定性事实，与金额无关
    ],
)
def test_金额闸门只降级不升级(level, amount_cents, expected):
    """闸门只把「比例达标但金额不足」的对降成 ``trivial``，绝不把低比例抬上去。

    边界必须踩准：``MIN_OVERLAP_AMOUNT_CENTS - 1`` 分就得降级——否则「多少钱才算」
    这件事会变成「差一点也行」，门槛等于没有。
    """
    got, _reason = _apply_amount_gate(level, '原理由', 25.0, amount_cents)

    assert got == expected


def test_金额不足时理由保留比例信息():
    """降档不等于「没重叠」：理由里必须说清「比例多高、只是钱太少」。

    只说「金额不足」会让用户以为系统没算出重叠；把 86.5% 摆出来，他才知道
    「确实重叠，只是我在这只基金上只放了 5 毛钱」。措辞必须是「弱提醒」而不是
    「不提示」——这一类在前端是**折叠但可见**的，说成不提示等于骗人。
    """
    level, reason = _apply_amount_gate('duplicate', '共同重仓 3 只、86.5% 仓位重叠', 86.5, 46)

    assert level == 'trivial'
    assert '86.5%' in reason
    assert '0' in reason  # ¥0（46 分四舍五入到元）
    assert '弱提醒' in reason
    assert '不提示' not in reason


def test_重复金额取两侧较小敞口(db, make_position):
    """重复金额 = Σ min(市值A×占比A, 市值B×占比B)，**取小**，不是求和。

    一只投 ¥100、一只投 ¥10,000，同一只股票各占 20%：真实重复的是那 ¥20，
    不是 ¥2,000。这条是「观察仓不该报」的数学基础——不取小就永远截不住。

    两只基金的占比刻意错开 2 个百分点（20.0 vs 18.0）：占比若逐行全等，会被
    ``_is_identical_holdings`` 正确定性成 ``same-series``（口径 8），那测的是同份额
    判据，不是金额口径。
    """
    make_position(symbol='000001', asset_type='fund', name='观察仓', quantity=100, current_price=1.0)
    make_position(symbol='000002', asset_type='fund', name='重仓', quantity=10000, current_price=1.0)
    for fund_code, ratio in (('000001', 20.0), ('000002', 18.0)):
        _holding(db, fund_code, '600519', '贵州茅台', ratio)
        _holding(db, fund_code, '000858', '五粮液', ratio)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    pair = _find_pair(result['pairs'], '000001', '000002')
    assert pair is not None
    # min(100元×20%, 10000元×18%) × 2 只 = 20 + 20 = ¥40 = 4000 分
    # 若误用「求和」会是 (20+1800)+(20+1800)=3640 元，相差 91 倍——取小才挡得住观察仓
    assert pair['overlap_amount_cents'] == 4000
    # 比例照样达标（weighted = min(20,18)×2 = 36、jaccard 1），但金额只有 ¥40 ⇒ 不提示
    assert pair['weighted_overlap'] == pytest.approx(36.0)
    assert pair['overlap_level'] == 'trivial'
    assert result['duplicate_count'] == 0
    assert result['weak_count'] == 1


def test_几块钱的观察仓不报配置重复(db, make_position):
    """真实场景：广发北证50 投 ¥12.57、永赢北证50 投 ¥22,450，持仓几乎一模一样。

    比例上判 duplicate（weighted 26.93、jaccard 1.0），但重复的只有 ¥3 上下——
    这正是用户说的「小实验仓位，重复也没什么意义」。
    """
    make_position(symbol='017513', asset_type='fund', name='广发北证50C', quantity=1257, current_price=0.01)
    make_position(symbol='023887', asset_type='fund', name='永赢北证50C', quantity=2245, current_price=10.0)
    _holding(db, '017513', '600519', '贵州茅台', 15.0)
    _holding(db, '017513', '000858', '五粮液', 12.0)
    _holding(db, '023887', '600519', '贵州茅台', 14.93)
    _holding(db, '023887', '000858', '五粮液', 12.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    pair = _find_pair(result['pairs'], '017513', '023887')
    assert pair is not None
    assert pair['overlap_level'] == 'trivial'
    assert '26.9%' in pair['overlap_reason']  # 比例照样摆出来，只是不提示
    assert result['duplicate_count'] == 0
    assert result['weak_count'] == 1


def test_大仓位重复照常提示(db, make_position):
    """两只各投 ¥20,000、持仓高度重合 ⇒ 必须照常报 duplicate。

    这是分档线存在的意义：不是把弱提醒一关了之，而是把两类分开，
    让「值得管的」浮到第一屏、「只值得看一眼的」收进折叠区。
    """
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=20000, current_price=1.0)
    make_position(symbol='000002', asset_type='fund', name='基金乙', quantity=20000, current_price=1.0)
    _holding(db, '000001', '600519', '贵州茅台', 15.0)
    _holding(db, '000001', '000858', '五粮液', 12.0)
    _holding(db, '000002', '600519', '贵州茅台', 14.93)
    _holding(db, '000002', '000858', '五粮液', 12.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    pair = _find_pair(result['pairs'], '000001', '000002')
    assert pair is not None
    assert pair['overlap_level'] == 'duplicate'
    # 20000×14.93% + 20000×12% = 2986 + 2400 = ¥5,386
    assert pair['overlap_amount_cents'] == 538600
    assert result['duplicate_count'] == 1
    assert result['weak_count'] == 0


def test_弱提醒条数含低比例但金额不小的对(db, make_position):
    """弱提醒 = ``low`` + ``trivial``，不只是金额不足的那些。

    一只基金重仓 20 只股票、和另一只只重 1 只时，比例永远到不了 10%（→ ``low``），
    但两只都投了 ¥100,000 时那只共同持仓仍重复了 ¥5,000。这类**不能**算进
    「配置重复」（比例确实不高），也**不该**从弱提醒里消失（钱是真的）。
    若只数 ``trivial``，前端「弱提醒 N 对」会比折叠区里实际列出的少。
    """
    make_position(symbol='000001', asset_type='fund', name='宽基甲', quantity=100000, current_price=1.0)
    make_position(symbol='000002', asset_type='fund', name='宽基乙', quantity=100000, current_price=1.0)
    # 共同持仓只有 600519（各 5%），其余各不相同 ⇒ jaccard = 1/5 = 0.2、weighted = 5.0
    _holding(db, '000001', '600519', '贵州茅台', 5.0)
    _holding(db, '000001', '000858', '五粮液', 4.0)
    _holding(db, '000001', '000001', '平安银行', 3.0)
    _holding(db, '000002', '600519', '贵州茅台', 5.0)
    _holding(db, '000002', '300750', '宁德时代', 4.0)
    _holding(db, '000002', '300760', '迈瑞医疗', 3.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    pair = _find_pair(result['pairs'], '000001', '000002')
    assert pair is not None
    assert pair['overlap_level'] == 'low'
    # min(100000×5%, 100000×5%) = ¥5,000：金额过线，但比例没到「需留意」
    assert pair['overlap_amount_cents'] == 500000
    assert result['duplicate_count'] == 0
    assert result['weak_count'] == 1


# ── 14. 排序：大仓位重复必须在第一屏 ──────────────────────────────────────


def test_排序按档位优先再按金额降序(db, make_position):
    """``pairs`` 首位必须是「档位最高 + 金额最大」的那对，不能是观察仓。

    旧排序只看 ``weighted_overlap``：一对投了几毛钱、比例 90% 的观察仓会排第 1，
    用户第一眼看到的就是噪音。档位优先、档内金额降序，才对得上「提醒该提醒的」。
    """
    # 大仓位重复：两只各 ¥20,000，持仓高度重合（占比错开 0.07，避免被判成同份额）
    for code, name, ratio in (
        ('000001', '大甲', 15.0),
        ('000002', '大乙', 14.93),
    ):
        make_position(symbol=code, asset_type='fund', name=name, quantity=20000, current_price=1.0)
        _holding(db, code, '600519', '贵州茅台', ratio)
        _holding(db, code, '000858', '五粮液', 12.0)
    # 小仓位观察仓：两只各 ¥5，比例与大仓位那对一样高（weighted 26.93），金额却只有 ¥1.3
    for code, name, ratio in (
        ('000003', '小甲', 15.0),
        ('000004', '小乙', 14.93),
    ):
        make_position(symbol=code, asset_type='fund', name=name, quantity=100, current_price=0.05)
        _holding(db, code, '300750', '宁德时代', ratio)
        _holding(db, code, '002594', '比亚迪', 12.0)
    db.commit()

    result = portfolio_holding_overlap(db, family_id=1)

    levels = [pair['overlap_level'] for pair in result['pairs']]
    assert 'duplicate' in levels and 'trivial' in levels
    assert result['duplicate_count'] == 1
    assert result['weak_count'] == 1
    # 档位优先：第一个 trivial 之后不许再出现 duplicate
    first_trivial = levels.index('trivial')
    assert 'duplicate' not in levels[first_trivial:]
    # 首位是那对大仓位，不是比例同样高但只投了 ¥5 的观察仓
    head = result['pairs'][0]
    assert {head['fund_code_a'], head['fund_code_b']} == {'000001', '000002'}
    assert head['overlap_amount_cents'] == 538600
