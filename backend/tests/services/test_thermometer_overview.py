# -*- coding: utf-8 -*-
# 本地数据链路验证（离线，确定性）：覆盖 B4 / B1 / B2 后端改动。
# 不依赖真实外部数据源（韭圈儿 / 集思录 / akshare），仅验证：
#   - B4: label_temp 权威阈值与 None 兜底
#   - B1: get_overview 返回 temperature_bands（短/中/长期 + 各自 level）
#   - B2: jisilu_indicator 的 level 字段在 overview 中正确透传
# 说明：B2 的「端到端」（集思录实际抓取写入的 data 是否含 level）依赖重新抓取，
#       此处验证 overview 对含 level 的 data 的透传逻辑正确。
from datetime import date

from app.domains.temperature.models import MarketComposite, MarketSingleValue
from app.services.thermometer.constants import TempLevel, label_temp
from app.services.thermometer.service import TemperatureService


def test_label_temp_authoritative_thresholds():
    # B4: >70 偏高, >40 适中, 其余偏低; None -> 未知
    assert label_temp(None) == '未知'
    assert label_temp(20) == TempLevel.LOW.value
    assert label_temp(40) == TempLevel.LOW.value
    assert label_temp(41) == TempLevel.MID.value
    assert label_temp(70) == TempLevel.MID.value
    assert label_temp(71) == TempLevel.HIGH.value
    # 枚举与字面量一致，避免再次出现「正常」近义词
    assert {TempLevel.LOW.value, TempLevel.MID.value, TempLevel.HIGH.value} == {'偏低', '适中', '偏高'}


def test_overview_temperature_bands(db):
    # B1: 短/中/长期分解 + 各自 level（数据源：韭圈儿恐惧/中长期 + 自算估值分位）
    db.add(
        MarketSingleValue(
            source='jiucaishuo_fear',
            name='韭圈儿短期情绪',
            value=30.8,
            collected_at=date.today(),
        )
    )
    db.add(
        MarketSingleValue(
            source='jiucaishuo_medium',
            name='韭圈儿中长期温度',
            value=49.0,
            collected_at=date.today(),
        )
    )
    db.add(
        MarketComposite(
            source='self_calc',
            collected_at=date.today(),
            data={'pe': 12.3, 'percent': 44.0, 'level': '适中'},
        )
    )
    db.add(
        MarketComposite(
            source='jisilu_indicator',
            collected_at=date.today(),
            data={
                'median_pb': 2.35,
                'median_pb_temperature': 22.75,
                'median_pb_level': '偏低',
                'median_pe': 13.1,
                'median_pe_temperature': 35.0,
                'median_pe_level': '偏低',
            },
        )
    )
    db.commit()

    data = TemperatureService.get_overview()
    composites = data['composites']

    # B1 核心：temperature_bands
    bands = composites.get('temperature_bands')
    assert bands is not None
    assert bands['short'] == {'name': '短期情绪', 'value': 30.8, 'level': '偏低'}
    assert bands['medium'] == {'name': '中期温度', 'value': 49.0, 'level': '适中'}
    # 长期取 self_calc.percent 原值（高=贵=热），不反向
    assert bands['long'] == {'name': '长期估值', 'value': 44.0, 'level': '适中'}

    # B2 核心：jisilu level 字段透传
    jisilu = composites['jisilu_indicator']
    assert jisilu['median_pb_level'] == '偏低'
    assert jisilu['median_pe_level'] == '偏低'


def test_overview_bands_missing_source_yields_unknown(db):
    # 缺源时对应 band 的 value 为 None，level 由 label_temp(None) 给出「未知」，不应崩溃
    db.add(
        MarketComposite(
            source='self_calc',
            collected_at=date.today(),
            data={'pe': 12.3, 'percent': None},
        )
    )
    db.commit()

    data = TemperatureService.get_overview()
    bands = data['composites'].get('temperature_bands')
    assert bands is not None
    assert bands['long']['value'] is None
    assert bands['long']['level'] == '未知'
    assert bands['short']['value'] is None
    assert bands['short']['level'] == '未知'
