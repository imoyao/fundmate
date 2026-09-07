# app/services/sync/jobs/fund_manager_job.py
"""基金经理同步任务（全量，当前接口不稳定，暂时跳过）"""

from typing import List

from loguru import logger

from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.funds.models import Fund, FundCompany, FundManager, Manager
from app.services.sync.company_resolver import get_company_code_by_name
from app.services.sync.jobs.base import IN_CHUNK_SIZE, SyncJob


def _chunked(values, size: int = IN_CHUNK_SIZE):
    """把可迭代分批为列表块，规避 SQLite in_ 变量上限（#1286 实测 2.6 万基金爆变量数）。"""
    values = list(values)
    for i in range(0, len(values), size):
        yield values[i : i + size]


class FundManagerSyncJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        # 无目标基金（用户无持仓/自选）时静默跳过，不报错阻断整体同步
        return True

    def get_name(self) -> str:
        return 'fund_manager'

    # ── 目标代码获取 ──

    def _get_all_fund_codes(self) -> List[str]:
        """获取所有已存在的基金代码"""
        funds = self.db.query(Fund.fund_code).all()
        return [fund.fund_code for fund in funds]

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """遍历所有基金代码，获取关联的基金经理"""
        codes = targets if targets else self._get_all_fund_codes()
        if not codes:
            return []

        all_managers = list()
        for code in codes:
            try:
                managers = self.adapter.fetch_fund_manager(code)
                for mgr in managers:
                    mgr['fund_code'] = code
                all_managers.extend(managers)
            except Exception as e:
                logger.warning(f'获取基金 {code} 经理信息失败: {e}')
        return all_managers

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """确保必填字段存在，生成唯一 mgr_code"""
        validated = list()
        for item in raw_data:
            if not item.get('fund_code') or not item.get('name'):
                continue
            # 生成唯一经理标识（如果适配器未提供）
            if not item.get('mgr_code'):
                import hashlib

                raw = f'{item.get("name", "")}_{item.get("company", "")}'
                item['mgr_code'] = hashlib.sha256(raw.encode()).hexdigest()[:12]
            validated.append(item)
        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """基于 mgr_code 去重"""
        return self._deduplicate_by_unique_key(data, Manager, 'mgr_code')

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """插入新经理并建立基金-经理关联"""
        # 0. 解析基金经理所属公司 → fund_companies.id
        company_names = {item.get('company') for item in new_data if item.get('company')}
        company_map = {}
        if company_names:
            existing = self.db.query(FundCompany).filter(FundCompany.name.in_(company_names)).all()
            company_map = {c.name: c.id for c in existing}
            # 补建缺失的基金公司，优先用真值 code（#1168）
            for name in company_names:
                if name in company_map:
                    continue
                real_code = get_company_code_by_name(name)
                if not real_code:
                    logger.warning(f'基金公司「{name}」未匹配到权威 code，暂以名称占位')
                    inst = FundCompany(name=name, code=name)
                    self.db.add(inst)
                    self.db.flush()
                    company_map[name] = inst.id
                    continue
                # 权威 code 已被其他名称占用（同机构简称/全称变体）→ 复用既有行，
                # 避免 unique(code) 冲突（#1286 全量回填实测：银华基金 80000235）
                by_code = self.db.query(FundCompany).filter_by(code=real_code).first()
                if by_code is not None:
                    company_map[name] = by_code.id
                    continue
                inst = FundCompany(name=name, code=real_code)
                self.db.add(inst)
                self.db.flush()
                company_map[name] = inst.id

        # 1. 插入新经理（带公司关联）
        mgr_records = []
        for item in new_data:
            rec = {'mgr_code': item['mgr_code'], 'name': item['name']}
            cid = company_map.get(item.get('company'))
            if cid:
                rec['company_id'] = cid
            mgr_records.append(rec)
        inserted = bulk_insert_if_not_exists(self.db, Manager, mgr_records, 'mgr_code')
        logger.info(
            f'新增 {inserted} 位经理（其中 {sum(1 for r in mgr_records if "company_id" in r)} 位已关联基金公司）'
        )

        # 2. 建立基金-经理关联（in_ 均分批查询，全量回填时基金/经理数量远超 SQLite 变量上限）
        mgr_codes = [item['mgr_code'] for item in new_data]
        mgr_map: dict = {}
        for chunk in _chunked(set(mgr_codes)):
            for m in self.db.query(Manager).filter(Manager.mgr_code.in_(chunk)).all():
                mgr_map[m.mgr_code] = m.id
        fund_codes = list({item['fund_code'] for item in new_data})
        fund_map: dict = {}
        for chunk in _chunked(fund_codes):
            for f in self.db.query(Fund.fund_code, Fund.id).filter(Fund.fund_code.in_(chunk)).all():
                fund_map[f.fund_code] = f.id

        rel_records = list()
        for item in new_data:
            fid = fund_map.get(item['fund_code'])
            mid = mgr_map.get(item['mgr_code'])
            if fid and mid:
                rel_records.append({'fund_id': fid, 'mgr_id': mid})

        existing_rels: set = set()
        fund_id_chunks = list(_chunked(fund_map.values()))
        mgr_id_chunks = list(_chunked(mgr_map.values()))
        for fids in fund_id_chunks:
            for mids in mgr_id_chunks:
                rows = (
                    self.db.query(FundManager.fund_id, FundManager.mgr_id)
                    .filter(FundManager.fund_id.in_(fids), FundManager.mgr_id.in_(mids))
                    .all()
                )
                existing_rels.update((r.fund_id, r.mgr_id) for r in rows)
        new_rels = [r for r in rel_records if (r['fund_id'], r['mgr_id']) not in existing_rels]
        if new_rels:
            self.db.bulk_insert_mappings(FundManager, new_rels)
            logger.info(f'新增 {len(new_rels)} 条基金-经理关联')

        self.db.commit()
