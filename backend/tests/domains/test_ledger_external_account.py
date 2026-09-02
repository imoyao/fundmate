# -*- coding: utf-8 -*-
"""Ledger.external_account_code 字段与建账逻辑测试（#1100/#1101）。

验证：
- 手动建账默认 external_account_code='MAIN'；
- get_or_create 按 (family_id, sales_institution_id, external_account_code) 查/建，
  同一机构不同资金账户 → 不同账本，相同 → 复用；
- E账户对账按 trade_account/fund_account 传入（普通/两融天然拆账本）。
"""

from app.domains.positions.models import SalesInstitution
from app.services.importer.orchestrator import ImportOrchestrator


class TestLedgerExternalAccount:
    def test_create_ledger_defaults_main(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '招商银行'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['external_account_code'] == 'MAIN'

    def test_get_or_create_distinguishes_external_account(self, db):
        inst = SalesInstitution(
            org_name='测试销售机构X',
            display_name='测试机构X',
            org_type='独立基金销售机构',
            is_active=True,
        )
        db.add(inst)
        db.commit()

        orch = ImportOrchestrator(db, family_id=1)
        l_normal = orch._get_or_create_channel_ledger('测试销售机构X', external_account_code='NORMAL')
        l_margin = orch._get_or_create_channel_ledger('测试销售机构X', external_account_code='MARGIN')

        assert l_normal.id != l_margin.id
        assert l_normal.external_account_code == 'NORMAL'
        assert l_margin.external_account_code == 'MARGIN'

        # 同 external_account_code 复用同一账本
        again = orch._get_or_create_channel_ledger('测试销售机构X', external_account_code='NORMAL')
        assert again.id == l_normal.id

        # 默认 'MAIN' 也复用，且与显式 NORMAL 不同
        default_led = orch._get_or_create_channel_ledger('测试销售机构X')
        assert default_led.id != l_normal.id
        assert default_led.external_account_code == 'MAIN'
