# -*- coding: utf-8 -*-
"""BiasJob._convert_to_records 的 stale 透传单测。"""

from datetime import date

from app.services.bias.job import BiasJob
from app.services.bias.schemas import BiasResult


def _make_result(stale: bool) -> BiasResult:
    return BiasResult(
        item_type='index',
        item_code='000300',
        item_name='沪深300',
        close=4000.0,
        bias=10.0,
        ema20=3900.0,
        label='高位区(绿卖)',
        position=70.0,
        position_label='高位区(绿卖)',
        data_date=date.today(),
        stale=stale,
    )


def test_convert_propagates_stale_true():
    rec = BiasJob._convert_to_records(None, [_make_result(stale=True)])[0]
    assert rec['stale'] is True


def test_convert_propagates_stale_false():
    rec = BiasJob._convert_to_records(None, [_make_result(stale=False)])[0]
    assert rec['stale'] is False
