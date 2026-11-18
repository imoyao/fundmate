# -*- coding: utf-8 -*-
"""创建资产时的配置目标推导（#3031 / P0-4）。

反向验证锚点：

- ``test_cash_derives_liquid``：把 ``derive_allocation`` 从 ``AssetCreate`` 摘掉 ⇒ 红
  （用户建了现金却落成「长期增值」，活钱永远空态）；
- ``test_derived_value_keeps_default_source``：若推导结果被混入判成 ``user`` ⇒ 红
  （G3 回填从此不敢碰这行，系统默认值被永久伪装成用户配置）；
- ``test_explicit_longterm_stays_longterm``：若推导覆盖显式入参 ⇒ 红（P0-7）。
"""

from app.core.constants import ALLOCATION_LABELS
from app.domains.assets.schemas import AssetCreate


def _create(**kwargs) -> AssetCreate:
    return AssetCreate(name='x', amount=100, **kwargs)


class TestDeriveOnCreate:
    def test_cash_derives_liquid(self):
        model = _create(major_category='cash')
        assert model.allocation == 'liquid'
        assert ALLOCATION_LABELS[model.allocation] == '活钱'

    def test_bank_wealth_is_stable(self):
        assert _create(major_category='bank_wealth').allocation == 'stable'

    def test_insurance_is_security(self):
        assert _create(major_category='insurance').allocation == 'security'
        assert _create(major_category='wealth_insurance').allocation == 'security'

    def test_investment_is_longterm(self):
        assert _create(major_category='investment').allocation == 'longterm'

    def test_explicit_longterm_stays_longterm(self):
        # 用户显式选了长期增值就尊重用户，即使大类是现金
        assert _create(major_category='cash', allocation='longterm').allocation == 'longterm'

    def test_liability_skips_derivation_without_raising(self):
        # derive_allocation 对负债抛 LiabilityAllocationError，那是聚合侧的守卫；
        # 用户建负债不该拿到 400
        assert _create(major_category='liability').allocation == 'longterm'

    def test_non_member_keeps_schema_default(self):
        model = _create(major_category='real_estate')
        assert model.allocation == 'longterm'  # 不推导成任何一笔钱


class TestSourceStampingUnaffected:
    def test_derived_value_keeps_default_source(self):
        data = _create(major_category='cash').model_dump()
        assert data['allocation'] == 'liquid'
        assert 'allocation_source' not in data  # 交给 ORM 列默认 default

    def test_explicit_value_is_user(self):
        data = _create(major_category='cash', allocation='longterm').model_dump()
        assert data['allocation'] == 'longterm'
        assert data['allocation_source'] == 'user'


class TestCreateEndpoint:
    def test_post_cash_asset_returns_liquid(self, client):
        resp = client.post(
            '/api/assets/', json={'major_category': 'cash', 'name': '招行活期', 'amount': 12000, 'currency': 'CNY'}
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['allocation'] == 'liquid'
        assert data['allocation_label'] == '活钱'
        assert data['allocation_source'] == 'default'

    def test_post_liability_asset_does_not_500(self, client):
        resp = client.post(
            '/api/assets/', json={'major_category': 'liability', 'name': '房贷', 'amount': 1760000, 'currency': 'CNY'}
        )
        assert resp.status_code == 200
        assert resp.get_json()['data']['allocation'] == 'longterm'
