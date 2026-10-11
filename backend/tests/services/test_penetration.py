# -*- coding: utf-8 -*-
"""测试基金持仓穿透服务（#870 Step 2）。

覆盖的**硬口径**（每条都对应生产库实测的坑，见 `services/penetration.py` 模块头）：

1. csrc / gics **跨体系隔离** —— 两套语义不重叠，相加会得出「制造业与非必需消费品同级」。
2. **同码多名归并** —— 实测 GICS `45` 既有「信息技术」又有「科技」，聚合键必须是 code。
3. **ratio 不归一化** —— 合计 86%~95% 是常态，归一化会抹掉基金间现金垫差异。
4. **逐基金取自身最新报告期** —— 全局取 max 会让报告期滞后的新基金凭空消失。
5. 三层（已穿透 / 未穿透 / 直持 + 现金等价物）**守恒**。
6. 未穿透逐条带 `reason`，**「真缺口」与「本质无股票敞口」不可混为一谈**。
7. 个股层 `holding_basis` 同期优先 `full`（季报只有前十大）。
8. 空库降级不抛异常。
"""

from datetime import date

import pytest

from app.domains.funds.models import FundHolding, FundIndustryAlloc
from app.services.penetration import (
    REASON_CASH_EQUIVALENT,
    REASON_ETF_HOLDING_MISSING,
    REASON_FUND_ALLOC_MISSING,
    REASON_INDUSTRY_MAP_MISSING,
    build_penetration,
)

REPORT_DATE = date(2026, 6, 30)


# ── 造数工具 ──────────────────────────────────────────────────────────────


def _alloc(db, fund_code, industry_code, industry_name, ratio, *, scheme='csrc', period='2026Q2'):
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


def _holding(db, fund_code, stock_code, stock_name, ratio, *, basis='full', period='2026Q2'):
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


def _find(items, code):
    for item in items:
        if item['code'] == code:
            return item
    return None


# ── 1. 跨体系隔离 ─────────────────────────────────────────────────────────


def test_schemes_are_not_aggregated_across_systems(db, make_position):
    """csrc 与 gics 必须分区求和：主口径结果里不得出现 gics 的行业码。"""
    make_position(symbol='000001', asset_type='fund', name='基金甲', quantity=1000, current_price=2.0)
    _alloc(db, '000001', 'C', '制造业', 50.0)
    _alloc(db, '000001', '25', '非必需消费品', 40.0, scheme='gics')
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    assert [i['code'] for i in result['industries']] == ['C']
    assert _find(result['other_schemes']['gics']['industries'], '25') is not None
    # gics 的 40% 绝不能被并进 csrc 的总量
    assert result['industries'][0]['value_cny'] == pytest.approx(1000.0)


def test_gics_only_fund_contributes_only_to_other_schemes(db, make_position):
    """只有 gics 记录的基金：主口径计入未穿透，但 gics 侧仍能看到它的敞口。"""
    make_position(symbol='000002', asset_type='fund', name='基金乙', quantity=1000, current_price=1.0)
    _alloc(db, '000002', '45', '信息技术', 30.0, scheme='gics')
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    assert result['industries'] == []
    assert result['coverage']['penetrated_cny'] == 0.0
    assert _find(result['other_schemes']['gics']['industries'], '45')['value_cny'] == pytest.approx(300.0)


# ── 2. 同码多名归并 ───────────────────────────────────────────────────────


def test_same_industry_code_with_multiple_names_is_merged(db, make_position):
    """同一 GICS 代码在不同基金下名称不一致（实测 `45`=「信息技术」/「科技」），按 code 归并。

    注意「同码多名」的出现位置：表上唯一键是
    `(fund_code, report_period, industry_code)`，**不含 scheme**，因此同一基金同一
    报告期不可能有两行同 code —— 名称分歧只能发生在**不同基金之间**。
    聚合时按 code 合一，名称取先出现者。
    """
    make_position(symbol='000003', asset_type='fund', name='基金丙', quantity=1000, current_price=1.0)
    make_position(symbol='000013', asset_type='fund', name='基金子', quantity=1000, current_price=1.0)
    _alloc(db, '000003', '45', '信息技术', 20.0, scheme='gics')
    _alloc(db, '000013', '45', '科技', 15.0, scheme='gics')
    db.commit()

    result = build_penetration(db, family_id=1, scheme='gics')

    assert len(result['industries']) == 1
    assert result['industries'][0]['code'] == '45'
    assert result['industries'][0]['value_cny'] == pytest.approx(350.0)
    assert result['industries'][0]['fund_count'] == 2


# ── 3. 不归一化 ───────────────────────────────────────────────────────────


def test_ratio_is_not_normalized_to_hundred(db, make_position):
    """行业合计 90% 的基金：行业敞口算 90%，差额 10% 单列 residual，不摊进行业。"""
    make_position(symbol='000004', asset_type='fund', name='基金丁', quantity=1000, current_price=10.0)
    _alloc(db, '000004', 'C', '制造业', 60.0)
    _alloc(db, '000004', 'I', '信息传输、软件和信息技术服务业', 30.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    assert _find(result['industries'], 'C')['value_cny'] == pytest.approx(6000.0)
    assert _find(result['industries'], 'I')['value_cny'] == pytest.approx(3000.0)
    assert result['industry_non_equity_cny'] == pytest.approx(1000.0)
    assert result['coverage']['penetrated_cny'] == pytest.approx(10000.0)


# ── 4. 逐基金最新报告期 ───────────────────────────────────────────────────


def test_latest_period_is_resolved_per_fund(db, make_position):
    """基金 A 有 Q1/Q2 两期、基金 B 只有 Q1：各自取自身最新，B 不得凭空消失。"""
    make_position(symbol='000005', asset_type='fund', name='基金戊', quantity=1000, current_price=1.0)
    make_position(symbol='000006', asset_type='fund', name='基金己', quantity=1000, current_price=1.0)
    _alloc(db, '000005', 'C', '制造业', 10.0, period='2026Q1')
    _alloc(db, '000005', 'C', '制造业', 50.0, period='2026Q2')
    _alloc(db, '000006', 'J', '金融业', 80.0, period='2026Q1')
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    # 基金戊 只算 Q2 的 50%（不是 10%，也不是两期相加的 60%）
    assert _find(result['industries'], 'C')['value_cny'] == pytest.approx(500.0)
    # 基金己 仍以 Q1 计入，未被全局 max 抹掉
    assert _find(result['industries'], 'J')['value_cny'] == pytest.approx(800.0)
    assert result['report_periods'] == {'2026Q1': 1, '2026Q2': 1}


# ── 5. 三层守恒 ───────────────────────────────────────────────────────────


def test_layers_conserve_total_value(db, make_position):
    """已穿透 + 未穿透 == 总市值（含直持与现金等价物），不得漏算任何一条持仓。"""
    make_position(symbol='000007', asset_type='fund', name='基金庚', quantity=1000, current_price=1.0)
    make_position(symbol='SH600519', asset_type='stock', name='贵州茅台', quantity=100, current_price=10.0)
    make_position(symbol='SZ159857', asset_type='etf', name='光伏ETF', quantity=200, current_price=5.0)
    make_position(symbol='004369', asset_type='money_fund', name='货基甲', quantity=300, current_price=1.0)
    _alloc(db, '000007', 'C', '制造业', 60.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')
    cov = result['coverage']

    assert cov['penetrated_cny'] + cov['unpenetrated_cny'] == pytest.approx(result['total_value_cny'])
    assert result['total_value_cny'] == pytest.approx(1000.0 + 1000.0 + 1000.0 + 300.0)
    assert cov['penetrated_cny'] == pytest.approx(1000.0)


# ── 6. 未穿透原因分类 ─────────────────────────────────────────────────────


def test_unpenetrated_reasons_distinguish_gap_from_no_exposure(db, make_position):
    """四类原因必须分清：货基是「本质无敞口」，其余才是真缺口。"""
    make_position(symbol='000008', asset_type='fund', name='无配置基金', quantity=1000, current_price=1.0)
    make_position(symbol='SZ159857', asset_type='etf', name='光伏ETF', quantity=1000, current_price=1.0)
    make_position(symbol='SH600519', asset_type='stock', name='贵州茅台', quantity=1000, current_price=1.0)
    make_position(symbol='004369', asset_type='money_fund', name='货基甲', quantity=1000, current_price=1.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')
    by_name = {item['name']: item for item in result['unpenetrated']}

    assert by_name['无配置基金']['reason'] == REASON_FUND_ALLOC_MISSING
    assert by_name['光伏ETF']['reason'] == REASON_ETF_HOLDING_MISSING
    assert by_name['贵州茅台']['reason'] == REASON_INDUSTRY_MAP_MISSING
    assert by_name['货基甲']['reason'] == REASON_CASH_EQUIVALENT
    # reason 必须带中文标签，前端不得自己拼
    assert all(item['reason_label'] for item in result['unpenetrated'])


def test_etf_with_holding_data_is_not_a_gap(db, make_position):
    """ETF 一旦补上底层数据即自动进入穿透，无需改代码（B3 生效路径的前置断言）。"""
    make_position(symbol='SZ159857', asset_type='etf', name='光伏ETF', quantity=1000, current_price=1.0)
    _alloc(db, '159857', 'C', '制造业', 90.0, scheme='csrc')
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    assert _find(result['industries'], 'C')['value_cny'] == pytest.approx(900.0)
    assert result['unpenetrated'] == []


# ── 7. 个股层 ─────────────────────────────────────────────────────────────


def test_stock_layer_prefers_full_basis_within_same_period(db, make_position):
    """同一报告期内 full 与 top10 并存时取 full，并据实打标。"""
    make_position(symbol='000009', asset_type='fund', name='基金辛', quantity=1000, current_price=1.0)
    _holding(db, '000009', '600519', '贵州茅台', 30.0, basis='full')
    _holding(db, '000009', '600519', '贵州茅台', 10.0, basis='top10')
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')
    stock = _find(result['stocks'], '600519')

    assert stock['value_cny'] == pytest.approx(300.0)
    assert result['stocks_coverage']['fund_count_by_basis'] == {'full': 1}
    assert result['stocks_coverage']['report_period_by_basis'] == {'full': '2026Q2'}


def test_stock_layer_falls_back_to_top10_and_tags_it(db, make_position):
    """只有季报前十大时照常输出，但 basis 必须是 top10（口径强度不同，不可与行业层混看）。"""
    make_position(symbol='000010', asset_type='fund', name='基金壬', quantity=1000, current_price=1.0)
    _holding(db, '000010', '600519', '贵州茅台', 12.0, basis='top10', period='2026Q2')
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    assert result['stocks_coverage']['fund_count_by_basis'] == {'top10': 1}
    assert _find(result['stocks'], '600519')['value_cny'] == pytest.approx(120.0)


def test_stock_top_n_truncation_keeps_residual_bucket(db, make_position):
    """top_n 截断后其余合并为「其他」一条，金额不得丢失。"""
    make_position(symbol='000011', asset_type='fund', name='基金癸', quantity=1000, current_price=1.0)
    for i, ratio in enumerate((40.0, 30.0, 20.0), start=1):
        _holding(db, '000011', f'60000{i}', f'股{i}', ratio)
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc', top_n=2)

    assert len(result['stocks']) == 3
    assert result['stocks'][-1]['code'] == '__other__'
    assert result['stocks'][-1]['value_cny'] == pytest.approx(200.0)
    total = sum(item['value_cny'] for item in result['stocks'])
    assert total == pytest.approx(900.0)


# ── 8. 空库与降级 ─────────────────────────────────────────────────────────


def test_empty_portfolio_degrades_without_error(db):
    """无任何持仓：返回零值结构、不抛异常（新用户首屏调用路径）。"""
    result = build_penetration(db, family_id=1)

    assert result['total_value_cny'] == 0.0
    assert result['industries'] == []
    assert result['stocks'] == []
    assert result['unpenetrated'] == []
    assert result['coverage']['penetrated_ratio'] == 0.0
    assert result['as_of']


def test_fund_with_zero_total_ratio_is_treated_as_unpenetrated(db, make_position):
    """行业行存在但 ratio 全为 0（脏数据）：按未穿透处理，不得凭空调出 0 值行业。"""
    make_position(symbol='000012', asset_type='fund', name='脏数据基金', quantity=1000, current_price=1.0)
    _alloc(db, '000012', 'C', '制造业', 0.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    assert result['coverage']['penetrated_cny'] == 0.0
    assert result['unpenetrated'][0]['reason'] == REASON_FUND_ALLOC_MISSING


# ── 9. 非主口径的「非完整口径」语义 ───────────────────────────────────────


def test_other_scheme_declares_partial_coverage(db, make_position):
    """gics 不是等价分类而是「港股那一块敞口」，出参必须自带覆盖度与说明。

    实测：44 只有 gics 行的基金，其行业合计只占参与基金市值的个位数百分比
    （residual 高达 90%）——若前端拿它当独立穿透率展示，会得出「港股只占 0.5%」
    这种完全错误的结论。
    """
    make_position(symbol='000014', asset_type='fund', name='基金寅', quantity=1000, current_price=1.0)
    make_position(symbol='000015', asset_type='fund', name='基金卯', quantity=1000, current_price=1.0)
    # A 基金：csrc 95% + gics 5%（只有港股那 5% 走 GICS）
    _alloc(db, '000014', 'C', '制造业', 95.0)
    _alloc(db, '000014', '45', '信息技术', 5.0, scheme='gics')
    # B 基金：只有 csrc，无 gics
    _alloc(db, '000015', 'J', '金融业', 90.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')
    gics = result['other_schemes']['gics']

    assert gics['covered_cny'] == pytest.approx(1000.0)  # 只有 A 参与
    assert gics['covered_ratio_of_fund'] == pytest.approx(0.5)
    assert gics['industry_total_cny'] == pytest.approx(50.0)
    assert gics['industry_ratio_of_covered'] == pytest.approx(0.05)
    assert gics['note']


# ── 10. 报告期统计按基金去重 ──────────────────────────────────────────────


def test_report_periods_count_distinct_funds_not_positions(db, make_position):
    """同一基金在多个账本各有一条持仓：金额累加，但报告期统计只算 1 只基金。"""
    for ledger in ('账本甲', '账本乙'):
        make_position(
            symbol='000016',
            asset_type='fund',
            name='基金辰',
            quantity=1000,
            current_price=1.0,
            account_name=ledger,
        )
    _alloc(db, '000016', 'C', '制造业', 50.0)
    db.commit()

    result = build_penetration(db, family_id=1, scheme='csrc')

    # 两条持仓都参与穿透，金额是两份之和
    assert _find(result['industries'], 'C')['value_cny'] == pytest.approx(1000.0)
    assert _find(result['industries'], 'C')['fund_count'] == 1
    # 报告期统计是「多少只基金用的哪一期」，不是「多少条持仓」
    assert result['report_periods'] == {'2026Q2': 1}


# ── 11. API 端点（路由注册 + 参数校验）────────────────────────────────────


def test_api_penetration_endpoint(client, db, make_position):
    """端点已注册、信封标准、默认口径为 csrc。"""
    make_position(symbol='000017', asset_type='fund', name='基金巳', quantity=1000, current_price=1.0)
    _alloc(db, '000017', 'C', '制造业', 60.0)
    db.commit()

    resp = client.get('/api/summary/penetration/')
    body = resp.get_json()

    assert resp.status_code == 200
    assert body['message'] == 'ok'
    assert body['data']['scheme'] == 'csrc'
    # penetrated = 成功穿透的**基金市值**（不是行业分摊额）
    assert body['data']['coverage']['penetrated_cny'] == pytest.approx(1000.0)
    assert body['data']['industries'][0]['value_cny'] == pytest.approx(600.0)


def test_api_penetration_accepts_scheme_and_top_n(client, db, make_position):
    """query 参数生效：scheme 切到 gics、top_n 截断个股。"""
    make_position(symbol='000018', asset_type='fund', name='基金午', quantity=1000, current_price=1.0)
    _alloc(db, '000018', '45', '信息技术', 80.0, scheme='gics')
    for i, ratio in enumerate((30.0, 20.0, 10.0), start=1):
        _holding(db, '000018', f'60001{i}', f'股{i}', ratio)
    db.commit()

    resp = client.get('/api/summary/penetration/?scheme=gics&top_n=2')
    data = resp.get_json()['data']

    assert resp.status_code == 200
    assert data['scheme'] == 'gics'
    assert len(data['stocks']) == 3  # 2 条 + 「其他」
    assert data['stocks'][-1]['code'] == '__other__'


def test_api_penetration_rejects_unknown_scheme(client):
    """非法 scheme 走 400 + 标准错误信封，不得落到 500。"""
    resp = client.get('/api/summary/penetration/?scheme=sw')

    assert resp.status_code == 400
    assert resp.get_json()['error_code'] == 1001


def test_api_penetration_rejects_bad_top_n(client):
    """top_n 非整数走 400，而不是被 int() 抛成 500。"""
    resp = client.get('/api/summary/penetration/?top_n=abc')

    assert resp.status_code == 400
    assert 'top_n' in resp.get_json()['message']
