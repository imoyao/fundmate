# -*- coding: utf-8 -*-
"""行业映射 job 的取数编排（#2749）：万得优先、巨潮兜底、两套口径各写一行。

不联网：申万全量、万得通道、巨潮通道全部替身。要证明的三件事：
1. 万得覆盖到的标的**不再走巨潮**（省请求，且万得给的是原始门类名）；
2. 万得没覆盖的标的**仍然回退巨潮**（一条通道挂了不该丢整轮）；
3. 写出的行里 ``scheme`` 与 ``source`` 都对得上——``source`` 是「这条谁给的」的唯一线索。
"""

from app.services.security_industry_map_service import IndustryMapRow
from app.services.sync.jobs import security_industry_map_job as job_mod
from app.services.sync.jobs.security_industry_map_job import SecurityIndustryMapSyncJob


def _make_job():
    return SecurityIndustryMapSyncJob(adapter=None, db=None)


def _sw_rows():
    # 用与 targets 不重叠的代码：全量刷的 2 行只是「行业名 → 代码」的字典来源，
    # 若拿 600519 当载体，断言行会被全量行污染（本用例首版即如此）。
    return [
        IndustryMapRow(symbol='000002', industry_code='801120', industry_name='食品饮料'),
        IndustryMapRow(symbol='600000', industry_code='801780', industry_name='银行'),
    ]


def test_wind_covers_targets_and_cninfo_only_gets_leftovers(monkeypatch):
    job = _make_job()
    monkeypatch.setattr(job_mod, 'fetch_sw1_industry_map', _sw_rows)
    monkeypatch.setattr(job_mod.wind_stock, 'is_available', lambda: True)
    monkeypatch.setattr(
        job_mod.wind_stock,
        'fetch_stock_industries',
        lambda codes: {'600519': {'name': '贵州茅台', 'sw1': '食品饮料', 'csrc': '制造业', 'wind_code': '600519.SH'}},
    )
    monkeypatch.setattr(
        job_mod.wind_stock,
        'fetch_bond_industry',
        lambda code: {'sw1': '银行', 'csrc': '金融业', 'name': '浦发银行', 'underlying': '600000.SH'},
    )
    cninfo_calls = []
    monkeypatch.setattr(
        job_mod,
        'fetch_csrc_industry_of',
        lambda code: (
            cninfo_calls.append(code) or IndustryMapRow(symbol=code, industry_code='C', industry_name='制造业')
        ),
    )

    rows = job._fetch_data(False, ['600519', '110059', '000001'])

    # 巨潮只处理万得漏掉的 000001
    assert cninfo_calls == ['000001']

    by_key = {(r['symbol'], r['scheme']): r for r in rows}
    # 股票：两套口径，source=wind
    assert by_key[('600519', 'csrc')]['industry_code'] == 'C'
    assert by_key[('600519', 'csrc')]['source'] == 'wind'
    assert by_key[('600519', 'sw1')]['industry_code'] == '801120'
    # 转债：按**债券代码**落库，指向正股的行业
    assert by_key[('110059', 'csrc')]['industry_code'] == 'J'
    assert by_key[('110059', 'sw1')]['industry_code'] == '801780'
    # 兜底那只：只有 csrc，且 source=cninfo
    assert by_key[('000001', 'csrc')]['source'] == 'cninfo'
    assert ('000001', 'sw1') not in by_key  # 巨潮不给申万，不凭空补


def test_wind_unavailable_falls_back_to_cninfo_for_all(monkeypatch):
    job = _make_job()
    monkeypatch.setattr(job_mod, 'fetch_sw1_industry_map', _sw_rows)
    monkeypatch.setattr(job_mod.wind_stock, 'is_available', lambda: False)
    monkeypatch.setattr(
        job_mod,
        'fetch_csrc_industry_of',
        lambda code: IndustryMapRow(symbol=code, industry_code='C', industry_name='制造业'),
    )

    rows = job._fetch_data(False, ['600519', '000001'])

    csrc_rows = [r for r in rows if r['scheme'] == 'csrc']
    assert {r['symbol'] for r in csrc_rows} == {'600519', '000001'}
    assert all(r['source'] == 'cninfo' for r in csrc_rows)


def test_wind_whole_channel_failure_still_falls_back(monkeypatch):
    """万得整批抛错 ⇒ 全部交给巨潮，而不是当轮丢空。"""
    job = _make_job()
    monkeypatch.setattr(job_mod, 'fetch_sw1_industry_map', _sw_rows)
    monkeypatch.setattr(job_mod.wind_stock, 'is_available', lambda: True)

    def _boom(codes):
        raise RuntimeError('upstream down')

    monkeypatch.setattr(job_mod.wind_stock, 'fetch_stock_industries', _boom)
    monkeypatch.setattr(
        job_mod,
        'fetch_csrc_industry_of',
        lambda code: IndustryMapRow(symbol=code, industry_code='C', industry_name='制造业'),
    )

    rows = job._fetch_data(False, ['600519'])

    csrc = [r for r in rows if r['scheme'] == 'csrc']
    assert len(csrc) == 1 and csrc[0]['source'] == 'cninfo'


def test_unknown_csrc_name_is_not_written(monkeypatch):
    """查不到的证监会门类名不写行（不猜门类），但 sw1 照写。"""
    job = _make_job()
    monkeypatch.setattr(job_mod, 'fetch_sw1_industry_map', _sw_rows)
    monkeypatch.setattr(job_mod.wind_stock, 'is_available', lambda: True)
    monkeypatch.setattr(
        job_mod.wind_stock,
        'fetch_stock_industries',
        lambda codes: {
            '600519': {'name': '某新行业公司', 'sw1': '食品饮料', 'csrc': '外星人业', 'wind_code': '600519.SH'}
        },
    )
    monkeypatch.setattr(job_mod.wind_stock, 'fetch_bond_industry', lambda code: None)
    monkeypatch.setattr(job_mod, 'fetch_csrc_industry_of', lambda code: None)

    rows = job._fetch_data(False, ['600519'])

    keys = {(r['symbol'], r['scheme']) for r in rows}
    assert ('600519', 'csrc') not in keys
    assert ('600519', 'sw1') in keys


def test_sw1_name_without_code_is_skipped(monkeypatch):
    """申万行业名对不上代码表时不写 sw1 行——宁可留缺口，不写一个假代码。"""
    job = _make_job()
    monkeypatch.setattr(job_mod, 'fetch_sw1_industry_map', _sw_rows)  # 只有 食品饮料 / 银行
    monkeypatch.setattr(job_mod.wind_stock, 'is_available', lambda: True)
    monkeypatch.setattr(
        job_mod.wind_stock,
        'fetch_stock_industries',
        lambda codes: {'600519': {'name': 'x', 'sw1': '某个新设一级行业', 'csrc': '制造业', 'wind_code': '600519.SH'}},
    )
    monkeypatch.setattr(job_mod.wind_stock, 'fetch_bond_industry', lambda code: None)

    rows = job._fetch_data(False, ['600519'])

    assert ('600519', 'sw1') not in {(r['symbol'], r['scheme']) for r in rows}
    assert ('600519', 'csrc') in {(r['symbol'], r['scheme']) for r in rows}


def test_dedup_keeps_wind_row_over_cninfo():
    """同一 (symbol, scheme) 两路都给时以先出现者为准，而万得行总是排在前面。"""
    job = _make_job()
    data = [
        {'symbol': '600519', 'scheme': 'csrc', 'source': 'wind', 'industry_code': 'C'},
        {'symbol': '600519', 'scheme': 'csrc', 'source': 'cninfo', 'industry_code': 'C'},
    ]
    out = job._deduplicate(data)
    assert len(out) == 1 and out[0]['source'] == 'wind'
