# -*- coding: utf-8 -*-
"""
实证：乖离率从 BiasJob 记录 -> save_multi_items 落库 -> get_multi_items 读取
的完整链路，验证两点：
  1) 扁平记录能否真正落库（结构对齐性，非想当然）
  2) stale 标记在落库后是否保留（observability 前提）
"""

from app.core.time_utils import now_shanghai
from app.services.bias.constants import SOURCE_BIAS
from app.services.thermometer.service import TemperatureService


def _flat_bias_record(item_code: str, item_name: str, stale: bool) -> dict:
    """模拟 BiasJob._convert_to_records 产出的扁平记录。"""
    return {
        'kind': 'multi',
        'source': SOURCE_BIAS,
        'item_type': 'index',
        'item_code': item_code,
        'item_name': item_name,
        'data': {
            'bias': 10.0,
            'label': '高位区(绿卖)',
            'position': 70.0,
            'position_label': '高位区(绿卖)',
            'close': 4000.0,
            'ema20': 3900.0,
            'data_date': '2026-08-02',
        },
        'collected_at': now_shanghai(),
        'stale': stale,
    }


def test_save_multi_items_persists_flat_bias_records():
    """落库计数应 > 0：若当前结构不匹配（被 continue 跳过），此断言会失败并暴露 bug。"""
    recs = [
        _flat_bias_record('000300', '沪深300', stale=False),
        _flat_bias_record('000905', '中证500', stale=True),
    ]
    count = TemperatureService.save_multi_items(recs)
    # 实证：扁平记录是否真的写进了库
    assert count == 2, f'期望落库 2 条，实际 {count} 条（结构对齐性存疑）'


def test_get_multi_items_returns_and_preserves_stale():
    """读取应返回刚写入的记录，并保留 stale 标记。"""
    recs = [
        _flat_bias_record('000300', '沪深300', stale=False),
        _flat_bias_record('000905', '中证500', stale=True),
    ]
    TemperatureService.save_multi_items(recs)

    resp = TemperatureService.get_multi_items(SOURCE_BIAS)
    items = resp.get('items', [])
    assert len(items) == 2, f'期望读回 2 条，实际 {len(items)} 条'

    by_code = {it['item_code']: it for it in items}
    # stale 标记不得丢失
    assert by_code['000300']['stale'] is False
    assert by_code['000905']['stale'] is True


def test_get_latest_multi_items_returns_stale():
    """overview 聚合使用的读取方法也应返回滞后记录（不应被 stale.is_(False) 滤掉）。"""
    recs = [
        _flat_bias_record('000300', '沪深300', stale=True),
        _flat_bias_record('000905', '中证500', stale=True),
    ]
    TemperatureService.save_multi_items(recs)

    items = TemperatureService.get_latest_multi_items(SOURCE_BIAS)
    assert len(items) == 2, f'期望 overview 读到 2 条，实际 {len(items)} 条'
    assert all(it['stale'] is True for it in items)


def test_save_multi_items_nested_format():
    """兼容嵌套入参（{source, collected_at, items:[...]}），且 stale 透传。"""
    nested = [
        {
            'source': SOURCE_BIAS,
            'collected_at': now_shanghai(),
            'items': [
                {
                    'item_type': 'index',
                    'item_code': '000300',
                    'item_name': '沪深300',
                    'data': {'bias': 5.0},
                    'stale': True,
                }
            ],
        }
    ]
    count = TemperatureService.save_multi_items(nested)
    assert count == 1, f'嵌套入参期望落库 1 条，实际 {count}'

    resp = TemperatureService.get_multi_items(SOURCE_BIAS)
    items = resp.get('items', [])
    assert len(items) == 1
    assert items[0]['stale'] is True
    assert resp['stale'] is True
