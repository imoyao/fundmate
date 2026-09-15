# -*- coding: utf-8 -*-
"""#1172 资产大类枚举（银行理财/投顾/信托/私募/理财型保险）单测。

覆盖：ASSET_CATEGORY_LABELS 含新增键、get_asset_category_label 映射正确、
GET /api/utils/enums/ 下发的 asset_category 含新增大类。
"""

from app.core.asset_types import (
    ASSET_CATEGORY_LABELS,
    ASSET_TYPE_VALUES,
    get_asset_category_label,
    is_valid_asset_type,
    validate_asset_type,
)

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


# ───────────────────────────── #1527 asset_type 强约束 ─────────────────────────────
def test_asset_type_values_derived_from_labels():
    # 合法值集合必须与标签映射同源，禁止手抄第二份
    from app.core.asset_types import ASSET_TYPE_LABELS

    assert set(ASSET_TYPE_VALUES) == set(ASSET_TYPE_LABELS.keys())
    assert 'stock' in ASSET_TYPE_VALUES
    assert 'manager' in ASSET_TYPE_VALUES


def test_is_valid_asset_type():
    assert is_valid_asset_type('stock') is True
    assert is_valid_asset_type('manager') is True
    assert is_valid_asset_type('not_a_type') is False
    assert is_valid_asset_type('') is False
    assert is_valid_asset_type(None) is False


def test_validate_asset_type_passes_known_and_empty():
    assert validate_asset_type('stock') == 'stock'
    assert validate_asset_type('') == ''  # 空值放行，兼容存量/可选
    assert validate_asset_type(None) is None


def test_validate_asset_type_rejects_unknown():
    import pytest

    with pytest.raises(ValueError):
        validate_asset_type('not_a_type')


def test_enums_endpoint_exposes_asset_type_values(client):
    resp = client.get('/api/utils/enums/')
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert 'asset_type_values' in data
    assert set(data['asset_type_values']) == set(ASSET_TYPE_VALUES)
