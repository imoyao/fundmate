# app/services/sync/jobs/fund_manager_job.py
"""基金经理同步任务（全量回填 / 按目标筛选）。

目标语义与 `fund_type_job` 一致，二者都遵循 `SyncJob.run` 的既定契约：

- `targets` 非空 → 只处理这几只基金（走 `_execute_batches` 分批）；
- `targets` 为空 → **全量回填**，即遍历库内全部基金。

空列表在本文件里唯一表示「未指定目标」，**不是**「无目标、跳过」。
「无目标跳过」由 `base.run` 在 `targets == []` 分支、于进入分批流程**之前**完成，
因此永远流不到 `_fetch_data`（`run_all_jobs` 传给本 job 的是 `fund_targets` 列表）。
"""

from datetime import date, timedelta
from typing import Dict, List, Optional

from loguru import logger

from app.core.db_utils import bulk_insert_if_not_exists
from app.domains.funds.models import Fund, FundManager, Manager
from app.services.job_base import IN_CHUNK_SIZE, SyncJob
from app.services.sync.company_resolver import get_or_create_fund_company


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
        """遍历目标基金代码，获取关联的基金经理。

        `targets` 为空表示**全量回填**（取库内全部基金），不是「无目标、跳过」——
        完整语义见模块 docstring。
        """
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
                # #1833：记 errors —— 本 job _allow_empty_data=True，全部失败时
                # 基类会记 success，基金经理关联静默不更新而无任何痕迹。
                self.stats.setdefault('errors', []).append(
                    {'fund_code': code, 'stage': 'fetch_manager', 'error': str(e)}
                )
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
        """**只做批内去重，不按库内已有值过滤** —— 与基类默认行为不同，理由见下。

        基类的 :meth:`SyncJob._deduplicate_by_unique_key` 会把「库里**已存在**的
        ``mgr_code``」整批丢掉。对本 job 这恰好把回填路径掐死了：``_save_data``
        需要**存量经理**出现在入参里，才能由 :meth:`_backfill_manager_profile`
        把 #1970 新增的三列（``sum_scale`` / ``best_return`` / ``appointment_date``）
        补到旧行上；被丢掉之后 ``mgr_records`` 只剩新经理，而新经理插入时三列本来
        就带着值，回填分支恒为 ``dirty=False``。

        实测（2026-10-11）：生产库 4267 行存量经理，跑
        ``pdm run sync --job fund_manager --full-sync --targets …`` **报 success**，
        而 ``select count(*) from managers where sum_scale is not null`` 仍是 **0**；
        日志里两条线索固定出现：``新增 0 位经理`` 与 ``回填存量经理档案列: {'updated': 0}``。

        幂等由 :meth:`_save_data` 自己负责（它本就是按幂等写的）：插入走
        ``bulk_insert_if_not_exists``（冲突即跳过）、建关联前先查 ``existing_rels``、
        回填**只补 NULL 不覆盖**已有值。故这里只需按 ``mgr_code`` 去掉**批次内**
        重复（同一经理在多只基金的行里会重复出现）。
        """
        seen: set = set()
        deduped: List[dict] = []
        for item in data:
            code = item.get('mgr_code')
            if not code or code in seen:
                continue
            seen.add(code)
            deduped.append(item)
        return deduped

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """插入新经理并建立基金-经理关联。

        **规模类字段在此写入**（#1970 扩展）：``sum_scale`` / ``best_return`` 来自
        ``fund_manager_em`` 的「现任基金资产总规模 / 现任基金最佳回报」两列 ——
        这两列此前在 ``akshare_adapter._filter_managers`` 就被丢弃，故填充率恒为 0%
        （**是写入侧裁剪，不是数据源缺失**）。

        **必须按 ``mgr_code`` 聚合后再写单行**：这两列是「该经理全部在管基金的合计」，
        实测张坤 3 行（005827/110011/118001）取值完全相同；直接逐行写会让同经理
        重复触发同值写入，并可能在并发下互相覆盖。

        **存量库必须走 UPDATE 回填**：``bulk_insert_if_not_exists`` 只插不更新，
        而生产库 ``managers`` 已有 4267 行 —— 只补插入逻辑的话这三列永远停在0%，
        等于**把旧库上的同一个 bug 原样保留**。故插入后显式回填 NULL 列。

        **``appointment_date`` 存日期而非天数**：见 :meth:`_derive_appointment_date`
        的口径说明 —— 存天数会让起始日每次同步都漂移。
        """
        # 0. 解析基金经理所属公司 → fund_companies.id
        company_names = {item.get('company') for item in new_data if item.get('company')}
        company_map = {}
        if company_names:
            # 唯一写入口（company_resolver）：精确名 → 归一化名 + 业务族 → 才新建。
            # akshare 给的是全称（「招商基金管理有限公司」），库里规范行是简称
            # （「招商基金」），此前只按精确名查会导致同一公司长出第二行
            # （2026-09-10 实测 8 组，招商基金的经理被分裂挂 103 + 9 行）。
            cache: Dict[str, int] = {}
            for name in company_names:
                company_map[name] = get_or_create_fund_company(self.db, name, cache=cache)

        # 1. 插入新经理（带公司关联 + 规模类字段）
        mgr_records = []
        seen_mgr: set = set()
        for item in new_data:
            mgr_code = item['mgr_code']
            # 同一经理在多只基金的行里规模/回报重复，取首个非空即可（口径见方法 docstring）
            if mgr_code in seen_mgr:
                existing = next((r for r in mgr_records if r['mgr_code'] == mgr_code), None)
                if existing is not None:
                    if existing.get('sum_scale') is None:
                        existing['sum_scale'] = item.get('sum_scale')
                    if existing.get('best_return') is None:
                        existing['best_return'] = item.get('best_return')
                    if existing.get('appointment_date') is None:
                        existing['appointment_date'] = self._derive_appointment_date(item)
                    if existing.get('_tenure_days') is None:
                        existing['_tenure_days'] = item.get('tenure_days')
                continue
            seen_mgr.add(mgr_code)
            rec = {'mgr_code': mgr_code, 'name': item['name']}
            cid = company_map.get(item.get('company'))
            if cid:
                rec['company_id'] = cid
            # 缺失键即None，不写入 0（0 会被读成「规模为 0」的假值）
            rec['sum_scale'] = item.get('sum_scale')
            rec['best_return'] = item.get('best_return')
            rec['appointment_date'] = self._derive_appointment_date(item)
            # 溯源原值（供回填路径重建展示档的 raw；**不是模型列，不入库**，
            # 故以下划线前缀区分，防止被 bulk_insert 当成 Manager 字段写进去）
            rec['_tenure_days'] = item.get('tenure_days')
            mgr_records.append(rec)
        # 下划线开头的键是**仅在本方法内流转**的临时数据（溯源原值），
        # 不是 Manager 的模型列 —— 直接透给 bulk_insert 会报「未知列」。
        insertable = [{k: v for k, v in r.items() if not k.startswith('_')} for r in mgr_records]
        inserted = bulk_insert_if_not_exists(self.db, Manager, insertable, 'mgr_code')
        logger.info(
            f'新增 {inserted} 位经理（其中 {sum(1 for r in mgr_records if "company_id" in r)} 位已关联基金公司）'
        )

        # 1b. 回填存量经理的档案列（只补 NULL，不覆盖已有值）
        backfilled = self._backfill_manager_profile(mgr_records)
        if backfilled:
            logger.info(f'回填存量经理档案列: {backfilled}')

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

    # ── 档案字段反推 / 存量回填 ─────────────────────────────

    @staticmethod
    def _derive_appointment_date(item: dict, today: Optional[date] = None) -> Optional[date]:
        """由东财「累计从业时间」（天）反推**首次任职日**。

        ## 为什么存日期而不存天数

        ``累计从业时间`` 是**相对抓取日的滚动值**：今天 5125、明年同一份数据 5190。
        若把天数直接落库、运行时再 ``today - days`` 反推，同一经理在两次同步间会得出
        **不同的起始日**，且无法复核（不知道它是哪天算的）。而「首次任职日」是已发生的
        客观事实，**一次写入即终局**。故落库的是日期。

        ## ⚠️ 精度边界：反推结果有 ±1 天不确定性（实测，非推测）

        基准日取 :func:`date.today`，而东财「累计从业时间」的**统计截止日未知**
        （可能 T 日、也可能 T-1）。两者若差一天，反推结果整体偏一天。

        实测证据：``2026-10-10`` 当天跑，``5125`` → ``2012-09-28``，
        与 F10 实测的 110011 起始日**逐日相同**；但 ``2026-10-11`` 再跑同一份数据，
        结果变成 ``2012-09-29``（跨零点导致，非数据源变化）。

        因此**不能把反推值当作「精确到日的首次任职日」**，只能当作
        「误差 ≤1 天的首次任职日估计」。这也是「从业 N 年」这类展示不受影响的
        原因——1 天远小于年化口径的精度需求。

        真要精确到日，只有两条路（均未做）：
        - 直接抓东财**经理主页**的「上任日期」字段（需每人一请求，成本高）；
        - 用库内该经理的**最早任期起始日**交叉校正（但会漏掉不在库关联的老基金）。
        本期按估计值落库，``basis`` 已标明来源，前端可据此展示口径说明。

        ## 口径：公转私/ 中断不另算，按首次任职起算

        同源校验还揭示了一件事：该字段是**日历跨度**而非「累计在任年数」——
        张坤 001373 于 2021-02-11 卸任、下一只 118001 迟至 2014-04 才接，中间存在
        空档，但反推值仍与F10 起始日一致，**说明空档天数未被扣除**。故：
        「从业第一天」即为从业起算日，**不做公转私/ 断档分段**——分段需要私募任职史，
        公开接口给不出，分段就成了编造。

        Args:
            item: 单行适配器输出，需含 ``tenure_days``。
            today: 基准日（默认今天）；测试可注入以获得确定性结果。

        Returns:
            反推出的 ``date``；``tenure_days`` 缺失/非正/反推出未来日时返回 None。
        """
        raw = item.get('tenure_days')
        if raw is None:
            return None
        try:
            days = int(float(raw))
        except (TypeError, ValueError):
            return None
        if days <= 0:
            return None

        base = today or date.today()
        derived = base - timedelta(days=days)
        # 反推出未来日 = 口径异常（数据源脏行），宁可留空也不写错日期
        if derived > base:
            return None
        return derived

    def _backfill_manager_profile(self, mgr_records: List[dict]) -> Dict[str, int]:
        """把档案列回填到**已存在**的经理行（只补 NULL，不覆盖已有值）。

        为什么必须单独做：:func:`bulk_insert_if_not_exists` 语义是「只插不更新」，
        冲突即跳过。生产库 4267 行存量经理因此永远拿不到这三列 —— 填充率仍是 0%，
        也就是 #1970 的原始 bug 在旧库上原样复现。

        **只补 NULL**：已写入的值不覆盖。理由是这些字段口径可能随数据源修正而变化
        （如东财改统计规则），无条件覆盖会让历史值被新口径静默改写、无法追溯。

        Returns:
            实际更新行数 ``{'updated': n}``；无可更新项时返回空 dict。
        """
        stats = {'updated': 0}
        touched = False
        for rec in mgr_records:
            mgr = self.db.query(Manager).filter(Manager.mgr_code == rec['mgr_code']).first()
            if mgr is None:
                continue
            dirty = False
            if mgr.sum_scale is None and rec.get('sum_scale') is not None:
                mgr.sum_scale = rec['sum_scale']
                dirty = True
            if mgr.best_return is None and rec.get('best_return') is not None:
                mgr.best_return = rec['best_return']
                dirty = True
            if mgr.appointment_date is None and rec.get('appointment_date') is not None:
                mgr.appointment_date = rec['appointment_date']
                dirty = True
            if dirty:
                stats['updated'] += 1
                touched = True
        if touched:
            self.db.flush()
        return stats

    # ── 任期补齐（独立于上述全量回填）────────────────────────────

    def backfill_tenures(self, fund_codes: List[str]) -> Dict[str, int]:
        """按目标基金逐只抓取任期，写入 ``fund_managers.start_date/end_date``。

        **为什么必须独立于 ``_fetch_data``**：任期只存在于天天基金 F10 经理页
        （``fund_manager_em`` 无此维度），即**每只基金一次 HTTP**。若混进
        ``_fetch_data``，全量回填会退化成 26000+ 次请求、且与「一次全量拿经理」
        的既定成本模型冲突。故显式分离，调用方按目标池限量调用。

        **只更新不插入**：关联关系由 ``_save_data`` 建立，本方法仅补两列，
        对库中不存在的 (fund, mgr) 组合**直接跳过**（不凭任期数据造关系，
        关系只由经理全量表决定）。

        Args:
            fund_codes: 目标基金代码列表。

        Returns:
            统计 dict：``{'scanned', 'matched', 'updated', 'failed'}``。
        """
        from app.services.adapters.manager_tenure import fetch_manager_tenures, find_tenure

        stats = {'scanned': 0, 'matched': 0, 'updated': 0, 'failed': 0}

        for code in fund_codes:
            segments = fetch_manager_tenures(code)
            if not segments:
                stats['failed'] += 1
                continue
            stats['scanned'] += 1

            fund = self.db.query(Fund).filter(Fund.fund_code == code).first()
            if fund is None:
                continue

            # 该基金的经理名集合 → 任期分段中能对上的
            rels = (
                self.db.query(Manager.name, FundManager)
                .join(FundManager, FundManager.mgr_id == Manager.id)
                .filter(FundManager.fund_id == fund.id)
                .all()
            )
            for mgr_name, rel in rels:
                tenure = find_tenure(segments, mgr_name)
                if tenure is None:
                    continue
                stats['matched'] += 1
                if rel.start_date == tenure['start_date'] and rel.end_date == tenure['end_date']:
                    continue  # 已是最新，不做无谓写入
                rel.start_date = tenure['start_date']
                rel.end_date = tenure['end_date']
                stats['updated'] += 1

        self.db.commit()
        logger.info(f'任期补齐完成: {stats}')
        return stats
