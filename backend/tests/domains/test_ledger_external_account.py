# -*- coding: utf-8 -*-
"""渠道 Ledger 的粒度与机构关联测试（2026-10-28 修正）。

2026-10-28 之前：查/建键含 ``external_account_code``，而导入侧传进来的是**交易账号**
（同一渠道下每张绑定卡 / 每个基金账号各不同）⇒ 一次导入建出 13 个同名账户
（``珠海盈米基金销售`` ×2、``富国基金`` ×3、``招商银行`` ×3 …）。

现行契约：**一个销售渠道 = 一个渠道账户**，查/建键为
``(family_id, ledger_type='fund', sales_institution_id)``（名录未命中退化为 name）。
交易账号 / 基金账号是持仓级属性，留在 ``position_import_meta``，不参与账户匹配。

本文件钉住三件事：
1. 同一渠道的多个交易账号**只产生一个**账户；
2. 机构名要能被归一化匹配上（简称「珠海盈米基金销售」↔ 全称「…有限公司」），
   命中后 ``sales_institution_id`` 与 ``channel_category`` 都要写入；
3. 匹配必须**宁可漏配不可误配**：歧义 / 名录外一律不关联机构，而不是猜一个。
"""

from app.domains.positions.models import SalesInstitution
from app.services.importer.orchestrator import ImportOrchestrator


def _inst(org_name, display_name=None, org_type='独立基金销售机构', is_active=True):
    return SalesInstitution(
        org_name=org_name,
        display_name=display_name,
        org_type=org_type,
        is_active=is_active,
    )


class TestLedgerExternalAccount:
    def test_create_ledger_defaults_main(self, client, db):
        resp = client.post('/api/ledgers/', json={'name': '招商银行'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['external_account_code'] == 'MAIN'

    def test_multiple_trade_accounts_share_one_ledger(self, db):
        """核心回归：同一渠道的多个交易账号必须复用同一个账户（不得再按账号分裂）。"""
        db.add(_inst('珠海盈米基金销售有限公司', '且慢'))
        db.commit()

        orch = ImportOrchestrator(db, family_id=1)
        opened = [
            orch._get_or_create_channel_ledger('珠海盈米基金销售', external_account_code=code)
            for code in ('07207192', '07207187', '07207192')
        ]

        assert len({led.id for led in opened}) == 1, '同一渠道的不同交易账号不得拆成多个账户'
        # 渠道账户这一层不再承载交易账号
        assert opened[0].external_account_code == 'MAIN'

    def test_alias_suffix_matches_amac_org_name(self, db):
        """简称缺「有限公司」也要命中，并写入机构 + 渠道分类。"""
        inst = _inst('珠海盈米基金销售有限公司', '且慢')
        db.add(inst)
        db.commit()

        orch = ImportOrchestrator(db, family_id=1)
        ledger = orch._get_or_create_channel_ledger('珠海盈米基金销售')

        assert ledger.sales_institution_id == inst.id
        # 展示名用名录别名（用户可读），权威全称只留在后台
        assert ledger.name == '且慢'
        assert ledger.ledger_type == 'fund'
        assert ledger.channel_category == 'fund_platform'

    def test_bank_org_type_maps_to_bank_category(self, db):
        """org_type=商业银行 → channel_category=bank，且 ledger_type 由它派生为 bank。

        2026-10-28 修正（#2713）：原断言是 `ledger_type == 'fund'`，docstring 称「两者正交」。
        正交只是当时实现的写法，与三处权威依据全部冲突：

        1. 模型注释（`Ledger.ledger_type`）：**「ledger_type 由系统维护/派生（创建时据
           channel_category 或销售机构 org_type 推导）」**；
        2. `constants.py` 的 `CHANNEL_CATEGORY_TO_LEDGER_TYPE`：`'bank' → 'bank'`，
           且文件头写明这是「唯一映射源，禁止在别处硬编码」；
        3. 同仓的手工建号路径 `ledger_write_service`：`ledger_type =
           map_channel_category_to_ledger_type(channel_category)`。

        只有导入路径写死 fund，于是同一个微众银行出现两种建号结果 —— 用户手工建的
        「微众银行」是 bank、E账户导入建的「深圳前海微众银行」是 fund，在账户列表里
        并排成两个账户，后者的徽标永远显示「基」（ledger_type 编辑时 409 不可变）。
        这就是 owner 报的那个 bug，故断言改为派生结果，与手工路径同口径。
        """
        db.add(_inst('深圳前海微众银行股份有限公司', '微众银行', org_type='商业银行'))
        db.commit()

        orch = ImportOrchestrator(db, family_id=1)
        ledger = orch._get_or_create_channel_ledger('深圳前海微众银行')

        assert ledger.channel_category == 'bank'
        assert ledger.ledger_type == 'bank', '银行渠道必须派生出 bank 类型，不再写死 fund'

    def test_normalized_name_other_display_name_still_matches(self, db):
        """display_name 精确命中的别名路径不受归一化改动影响。"""
        inst = _inst('某某财富管理股份有限公司', '示例渠道')
        db.add(inst)
        db.commit()

        ledger = ImportOrchestrator(db, family_id=1)._get_or_create_channel_ledger('示例渠道')
        assert ledger.sales_institution_id == inst.id

    def test_manual_alias_bridge_unrelated_brand(self, db):
        """品牌词完全不同（浦发银行 / 上海浦东发展银行）靠手工别名搭桥。"""
        inst = _inst('上海浦东发展银行股份有限公司', '浦发银行', org_type='商业银行')
        db.add(inst)
        db.commit()

        ledger = ImportOrchestrator(db, family_id=1)._get_or_create_channel_ledger('浦发银行')
        assert ledger.sales_institution_id == inst.id

    def test_ambiguous_normalized_name_is_not_matched(self, db):
        """归一化后同键多候选 = 歧义 → 不匹配（错配外键几乎无从发现，宁可漏配）。"""
        db.add(_inst('测试银行有限公司'))
        db.add(_inst('测试银行股份有限公司'))
        db.commit()

        ledger = ImportOrchestrator(db, family_id=1)._get_or_create_channel_ledger('测试银行')

        assert ledger.sales_institution_id is None, '歧义必须留空，不得任选一个'
        assert ledger.name == '测试银行'

    def test_bank_and_securities_same_core_word_are_not_confused(self, db):
        """「招商银行」与「招商证券」归一化同键（招商），必须靠业务族分开。"""
        bank = _inst('招商银行股份有限公司', None, org_type='商业银行')
        sec = _inst('招商证券股份有限公司', None, org_type='证券公司')
        db.add_all([bank, sec])
        db.commit()

        orch = ImportOrchestrator(db, family_id=1)
        assert orch._get_or_create_channel_ledger('招商银行').sales_institution_id == bank.id
        assert orch._get_or_create_channel_ledger('招商证券').sales_institution_id == sec.id

    def test_unlisted_broker_falls_back_then_is_reused(self, db):
        """名录外（基金公司直销：易方达基金）→ 按原文建账户、不关联机构，且同样只建一个。"""
        orch = ImportOrchestrator(db, family_id=1)
        first = orch._get_or_create_channel_ledger('易方达基金', external_account_code='A1')
        second = orch._get_or_create_channel_ledger('易方达基金', external_account_code='A2')

        assert first.id == second.id
        assert first.sales_institution_id is None

    def test_legacy_duplicate_ledgers_are_reused_not_split(self, db):
        """存量重复账户：新导入复用「持仓最多」的那条，不再继续分裂。"""
        from app.domains.positions.models import Position

        inst = _inst('招商银行股份有限公司', None, org_type='商业银行')
        db.add(inst)
        db.commit()

        from app.domains.ledgers.models import Ledger

        empty = Ledger(name='招商银行', ledger_type='fund', family_id=1, sales_institution_id=inst.id)
        used = Ledger(name='招商银行', ledger_type='fund', family_id=1, sales_institution_id=inst.id)
        db.add_all([empty, used])
        db.flush()
        db.add(Position(symbol='000001', name='测试基金', ledger_id=used.id, family_id=1))
        db.commit()

        picked = ImportOrchestrator(db, family_id=1)._get_or_create_channel_ledger('招商银行')
        assert picked.id == used.id, '应复用持仓最多的账户，而不是空壳账户'

    def test_inactive_institution_is_not_matched(self, db):
        db.add(_inst('已下线销售有限公司', None, is_active=False))
        db.commit()

        ledger = ImportOrchestrator(db, family_id=1)._get_or_create_channel_ledger('已下线销售')
        assert ledger.sales_institution_id is None
