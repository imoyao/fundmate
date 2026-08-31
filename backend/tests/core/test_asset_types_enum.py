# -*- coding: utf-8 -*-
"""#1172 资产大类枚举（银行理财/投顾/信托/私募/理财型保险）单测。

覆盖：ASSET_CATEGORY_LABELS 含新增键、get_asset_category_label 映射正确、
GET /api/utils/enums/ 下发的 asset_category 含新增大类。
"""

from app.core.asset_types import ASSET_CATEGORY_LABELS, get_asset_category_label

EXPECTED_NEW_CATEGORIES = {
    'bank_wealth': '银行理财',
    'advisory': '投顾',
    'trust': '信托',
    'private_fund': '私募',
    'wealth_insurance': '理财型保险',
}


def test_asset_category_labels_include_new_categories():
    for key, label in EXPECTED_NEW_CATEGORIES.items():
        assert key in ASSET_CATEGORY_LABELS, f'ASSET_CATEGORY_LABELS 缺少新增大类 {key}'
        assert ASSET_CATEGORY_LABELS[key] == label


def test_get_asset_category_label_new():
    for key, label in EXPECTED_NEW_CATEGORIES.items():
        assert get_asset_category_label(key) == label


def test_enums_endpoint_includes_new_categories(client):
    resp = client.get('/api/utils/enums/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert 'asset_category' in data
    for key in EXPECTED_NEW_CATEGORIES:
        assert key in data['asset_category'], f'enums 下发缺少新增大类 {key}'
