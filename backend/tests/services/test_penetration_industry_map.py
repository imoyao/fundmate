# -*- coding: utf-8 -*-
"""直持股票 / 可转债的「代码→行业」映射（#1981）。

issue 的三条验收各自对应下面第一个测试，另附双体系隔离与采集侧单测：

1. **命中映射的直持腿转入行业分布**，``industry_map_missing`` 里不再出现它；
2. **反向验证**：没有映射时仍归 ``industry_map_missing``，且**不得凭空调出 0 值行业**
   （这条比第 1 条更重要：错归到「制造业」那种大类，数字仍然守恒、事后无人察觉）；
3. **守恒**：``行业合计 + industry_non_equity_cny == penetrated_cny``。

另锁两条容易被顺手改坏的边界：

- **现金等价物不参与映射**：货基 / 逆回购即使代码撞上某行业也不该被归类，
  那等于把现金算成某个行业的股票敞口；
- **申万一级只进单列**：它只覆盖直持腿（基金侧没有申万口径），与主口径的基金部分
  **互补而非重叠**，混进主口径就会破守恒。
"""

from datetime import date

import pytest

from app.domains.funds.models import FundIndustryAlloc
from app.domains.securities.models import SecurityIndustryMap
from app.services.penetration import (
    REASON_CASH_EQUIVALENT,
    REASON_INDUSTRY_MAP_MISSING,
    build_penetration,
)
from app.services.security_industry_map_service import (
    SCHEME_CSRC,
    SCHEME_SW1,
    SOURCE_CNINFO,
    SOURCE_SWSRESEARCH,
    IndustryMapRow,
    csrc_code_of,
    upsert_industry_map,
)

REPORT_DATE = date(2026, 6, 30)


# ── 造数工具 ──────────────────────────────────────────────────────────────


def _map(db, symbol, industry_code, industry_name, *, scheme=SCHEME_CSRC, source=SOURCE_CNINFO):
    db.add(
        SecurityIndustryMap(
            symbol=symbol,
            scheme=scheme,
            industry_code=industry_code,
            industry_name=industry_name,
            source=source,
        )
    )


def _alloc(db, fund_code, industry_code, industry_name, ratio, *, scheme=SCHEME_CSRC, period='2026Q2'):
    db.add(
        FundIndustryAlloc(
            fund_code=fund_code,
            report_period=period,
            report_date=REPORT_DATE,
            industry_code=industry_code,
            industry_name=industry_name,
            scheme=scheme,
            ratio=ratio,
            source='eastmoney',
        )
    )


def _find(items, code):
    for item in items or []:
        if item['code'] == code:
            return item
    return None


def _industry_total(result):
    return sum(i['value_cny'] for i in result['industries'])


# ── 验收 1：命中映射的直持腿转入行业分布 ──────────────────────────────────


def test_mapped_direct_stock_enters_industry_distribution(db, make_position):
    """直持股票有映射 → 计入 penetrated、不再出现在 unpenetrated。"""
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    _map(db, '600519', 'C', '制造业')
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)

    hit = _find(result['industries'], 'C')
    assert hit is not None, '直持股票映射到制造业，应出现在主口径行业分布里'
    assert hit['value_cny'] == pytest.approx(1000.0)
    assert hit['direct_count'] == 1
    # 不再是缺口
    assert all(u['symbol'] != '600519' for u in result['unpenetrated'])
    assert result['coverage']['penetrated_cny'] == pytest.approx(1000.0)
    assert result['coverage']['mapped_direct_cny'] == pytest.approx(1000.0)
    assert result['coverage']['direct_cny'] == pytest.approx(0.0)


# ── 验收 2：反向验证——无映射仍归缺口，且不补 0 值行业 ──────────────────────


def test_unmapped_direct_stock_stays_missing_without_zero_industry(db, make_position):
    """没有映射 → 仍带 industry_map_missing，且**行业列表不得凭空多出 0 值项**。"""
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)

    assert result['industries'] == [], '无映射时不得凭空调出任何行业'
    missing = [u for u in result['unpenetrated'] if u['reason'] == REASON_INDUSTRY_MAP_MISSING]
    assert len(missing) == 1 and missing[0]['symbol'] == '600519'
    assert result['coverage']['direct_cny'] == pytest.approx(1000.0)
    assert result['coverage']['penetrated_cny'] == pytest.approx(0.0)


def test_cash_equivalent_is_not_mapped_even_if_code_hits(db, make_position):
    """现金等价物不参与映射：代码撞上行业也不能被归类成股票敞口。

    用 ``money_fund`` 而不是「场内货币 ETF」：后者的判定要查 market 域名录
    （``resolve_money_fund_flags_strict``），在纯内存测试库里没有那只 ETF 的数据，
    会走不进现金桶而让本用例测不到真正想锁的那条分支。
    """
    make_position(symbol='511990', asset_type='money_fund', name='银华日利', quantity=1000, current_price=1.0)
    _map(db, '511990', 'C', '制造业')
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)

    assert result['industries'] == []
    assert result['coverage']['cash_equivalent_cny'] == pytest.approx(1000.0)
    reasons = {u['reason'] for u in result['unpenetrated']}
    assert REASON_CASH_EQUIVALENT in reasons


# ── 验收 3：守恒 ──────────────────────────────────────────────────────────


def test_conservation_holds_with_mapped_direct(db, make_position):
    """基金 + 直持（有映射 / 无映射）+ 现金等价物 混在一起时三层守恒成立。"""
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    _alloc(db, '000001', 'C', '制造业', 80.0)  # 80% 摊入C，20% 是债/现金 → residual
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    _map(db, '600519', 'J', '金融业')
    make_position(symbol='000002', asset_type='stock', name='无映射股', quantity=100, current_price=5.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)

    # 验收 3 的原始口径
    assert _industry_total(result) + result['industry_non_equity_cny'] == pytest.approx(
        result['coverage']['penetrated_cny']
    )
    # 三层拆分也自洽：已穿透 + 未穿透 == 总市值
    cov = result['coverage']
    assert cov['penetrated_cny'] + cov['unpenetrated_cny'] == pytest.approx(result['total_value_cny'])
    # 未穿透的两类互斥且合计正确（1000 直持无映射 + 1000 现金等价物）
    assert cov['direct_cny'] + cov['cash_equivalent_cny'] == pytest.approx(cov['unpenetrated_cny'])


def test_mapped_direct_is_not_double_counted_in_direct_cny(db, make_position):
    """命中映射的直持腿只算 penetrated 一次：mapped_direct 是**拆分展示**不是追加。"""
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    _map(db, '600519', 'C', '制造业')
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)
    cov = result['coverage']

    assert cov['direct_cny'] == pytest.approx(0.0), '已映射的直持腿不得再计入 direct_cny（否则同一笔钱算两次）'
    assert cov['penetrated_cny'] == pytest.approx(1000.0)


# ── 双体系：申万一级只进单列 ──────────────────────────────────────────────


def test_sw1_only_in_other_schemes_never_in_primary(db, make_position):
    """申万一级只覆盖直持腿，且**绝不出现在主口径**（混进去会破守恒）。"""
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    # 只给 sw1 映射，不给 csrc → 主口径仍应是缺口
    _map(db, '600519', '801150', '医药生物', scheme=SCHEME_SW1, source=SOURCE_SWSRESEARCH)
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)

    assert result['industries'] == [], 'sw1 不得并入主口径行业分布'
    assert any(u['reason'] == REASON_INDUSTRY_MAP_MISSING for u in result['unpenetrated'])
    sw1 = result['other_schemes'][SCHEME_SW1]
    hit = _find(sw1['direct_industries'], '801150')
    assert hit is not None and hit['value_cny'] == pytest.approx(1000.0)
    # covered_* 仍是纯基金口径，不被直持腿污染
    assert sw1['covered_cny'] == pytest.approx(0.0)
    assert sw1['covered_ratio_of_fund'] == pytest.approx(0.0)
    assert '互补' in sw1['note']


def test_both_schemes_present_primary_merges_and_sw1_side_by_side(db, make_position):
    """两套映射都有：主口径用 csrc，申万在单列里独立给出同一笔钱。"""
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    _map(db, '600519', 'C', '制造业')
    _map(db, '600519', '801150', '医药生物', scheme=SCHEME_SW1, source=SOURCE_SWSRESEARCH)
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)

    assert _find(result['industries'], 'C') is not None
    assert _find(result['other_schemes'][SCHEME_SW1]['direct_industries'], '801150') is not None


def test_sw1_scheme_never_produced_empty_block(db, make_position):
    """没有 sw1 映射时不产出空的 sw1 块（避免前端渲染一个空面板）。"""
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    _map(db, '600519', 'C', '制造业')
    db.commit()

    result = build_penetration(db, family_id=1, scheme=SCHEME_CSRC)

    assert SCHEME_SW1 not in result['other_schemes']
    assert 'gics' not in result['other_schemes']


# ── 采集侧：门类字典 ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    'name,expected',
    [
        ('制造业', 'C'),
        ('金融业', 'J'),
        ('金融业 ', 'J'),  # 来源常带尾随空白
        ('电力、热力、燃气及水生产和供应业', 'D'),  # 带顿号变体
        ('信息传输、软件和信息技术服务业', 'I'),
    ],
)
def test_csrc_code_of_known_names(name, expected):
    assert csrc_code_of(name) == expected


@pytest.mark.parametrize('name', [None, '', '  ', '某某不存在的门类', '制造业与建筑业'])
def test_csrc_code_of_unknown_returns_none(name):
    """认不出一律 None，**绝不猜**——猜错会静默污染行业分布且数字仍然守恒。"""
    assert csrc_code_of(name) is None


# ── 采集侧：幂等 upsert ───────────────────────────────────────────────────


def test_upsert_is_idempotent_and_updates_in_place(db):
    row = IndustryMapRow(symbol='600519', industry_code='C', industry_name='制造业')
    first = upsert_industry_map(db, [row], SCHEME_CSRC, SOURCE_CNINFO)
    assert first['inserted'] == 1

    # 同样内容再刷一次 → 不产生新行
    again = upsert_industry_map(db, [row], SCHEME_CSRC, SOURCE_CNINFO)
    assert again['inserted'] == 0 and again['skipped'] == 1

    # 行业变了 → 就地更新，且行数不变
    changed = IndustryMapRow(symbol='600519', industry_code='J', industry_name='金融业')
    third = upsert_industry_map(db, [changed], SCHEME_CSRC, SOURCE_CNINFO)
    assert third['updated'] == 1
    assert db.query(SecurityIndustryMap).filter_by(symbol='600519', scheme=SCHEME_CSRC).one().industry_code == 'J'

    # 同 code 不同 scheme 是两行（两套体系并存）
    upsert_industry_map(db, [IndustryMapRow(symbol='600519', industry_code='801150')], SCHEME_SW1, SOURCE_SWSRESEARCH)
    assert db.query(SecurityIndustryMap).filter_by(symbol='600519').count() == 2


def test_upsert_skips_rows_without_code_or_symbol(db):
    stats = upsert_industry_map(
        db,
        [IndustryMapRow(symbol='', industry_code='C'), IndustryMapRow(symbol='600519', industry_code='')],
        SCHEME_CSRC,
        SOURCE_CNINFO,
    )
    assert stats == {'inserted': 0, 'updated': 0, 'skipped': 2}
    assert db.query(SecurityIndustryMap).count() == 0


# ── #2617 直接持有口径（图 A）：基金整块不拆底层 ──────────────────────────


def test_direct_view_与穿透后口径对照且守恒(db, make_position):
    """直持行业只含直持腿金额，基金整块单列；两图各项合计都等于持仓总市值。"""
    make_position(symbol='600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)  # 1000
    make_position(symbol='110011', asset_type='fund', name='混合基金', quantity=100, current_price=5.0)  # 500
    _map(db, '600519', 'C', '制造业')
    _alloc(db, '110011', 'C', '制造业', 50.0)  # 基金一半在制造业
    db.commit()

    result = build_penetration(db, family_id=1)
    dv = result['direct_view']

    assert dv['fund_cny'] == pytest.approx(500.0)
    assert dv['total_cny'] == pytest.approx(1500.0)
    # 图 A：制造业只有直持的 1000，不含基金穿透出的 250
    assert _find(dv['industries'], 'C')['value_cny'] == pytest.approx(1000.0)
    # 图 B（穿透后）：制造业 = 1000 + 250
    assert _find(result['industries'], 'C')['value_cny'] == pytest.approx(1250.0)
    # 守恒：直持行业 + 基金整块 + 未映射 + 现金等价物 = 持仓总市值
    assert (
        sum(i['value_cny'] for i in dv['industries']) + dv['fund_cny'] + dv['unmapped_cny'] + dv['cash_equivalent_cny']
    ) == pytest.approx(dv['total_cny'])
    # 本口径下直持映射可用，不该给出「映射缺口」的降级说明
    assert dv['mapping_available'] is True
    assert dv['mapped_cny'] == pytest.approx(1000.0)
    assert dv['unmapped_reason'] is None


def test_direct_view_无映射直持进未映射而非零值行业(db, make_position):
    """无行业映射的直持腿只进 unmapped_cny，行业列表不得凭空多出 0 值项。"""
    make_position(symbol='600519', asset_type='stock', name='无映射股票', quantity=100, current_price=10.0)
    db.commit()

    result = build_penetration(db, family_id=1)
    dv = result['direct_view']

    assert dv['industries'] == []
    assert dv['unmapped_cny'] == pytest.approx(1000.0)
    assert dv['fund_cny'] == pytest.approx(0.0)
    # 整个口径都没有直持映射时，必须显式告知成因，而不是只给空列表
    assert dv['mapping_available'] is False
    assert dv['mapped_cny'] == pytest.approx(0.0)
    assert '映射' in (dv['unmapped_reason'] or '')


def test_direct_view_现金等价物单列不进未映射(db, make_position):
    """货基/逆回购本质无股票敞口，不得混进「未映射」把映射缺口放大。"""
    make_position(symbol='600519', asset_type='stock', name='无映射股票', quantity=100, current_price=10.0)  # 1000
    make_position(
        symbol='511990', asset_type='money_fund', name='华宝现金添益', quantity=200, current_price=5.0
    )  # 1000
    db.commit()

    result = build_penetration(db, family_id=1)
    dv = result['direct_view']

    assert dv['unmapped_cny'] == pytest.approx(1000.0)  # 只有股票的 1000
    assert dv['cash_equivalent_cny'] == pytest.approx(1000.0)
    assert dv['total_cny'] == pytest.approx(2000.0)
