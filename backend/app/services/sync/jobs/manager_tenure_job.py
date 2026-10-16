# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/10/11
# File : manager_tenure_job.py
# app/services/sync/jobs/manager_tenure_job.py
"""基金经理任期同步（#2082 / #2239）：把 F10 抓到的任期写进 ``manager_tenures``。

## WHY：这条链路曾经是断的，落点也曾经是错的

``FundManagerSyncJob.backfill_tenures()`` 早就写好了（口径与坑位注释都很完整），
但**全仓没有任何调用点** —— ``grep -rn backfill_tenures`` 只命中定义本身。
于是任职时间连「跑同步能修」都谈不上，真实库实测：

```
fund_managers 总数 = 34812
  start_date   非空      0 / 34812  =  0.0%
  end_date     非空      0 / 34812  =  0.0%
```

前端「任职起止 / 任期」因此永远是「—」。

#2239 又把**落点**改对了：任期不再写 ``fund_managers``（那张表已拆成纯关联 + 唯一约束），
而是写 ``manager_tenures`` —— 一段一行，同一 (基金, 经理) 允许**多段**，
这是原表「一行一格」表达不出来的（张坤在 005827 就有两段）。
本 job 是这张表的**唯一写入方**；「谁在管谁」仍由 ``fund_manager`` job 负责，
两件事不再混在同一条写入路径里。

## 为什么必须独立成 job，而不是塞进 fund_manager

任期只存在于天天基金 F10 经理页（``fund_manager_em`` 无此维度），即
**每只基金一次 HTTP**。若混进 ``fund_manager`` 的 ``_fetch_data``，全量回填会退化成
26000+ 次请求，与「一次全量拿经理」的既定成本模型冲突（原方法 docstring 已写明
「故显式分离，调用方按目标池限量调用」）。独立成 job 后，限量调用就是天然的
``--targets`` 语义。

## ⚠️ 安全边界：targets 为空时**什么都不做**

``_fetch_data`` **不做**「空 targets → 取全库」的兜底（别的 job 常那么写，见
``FundManagerSyncJob._fetch_data``）。本 job 一个单位 = 一次 HTTP，兜底成全库
等于把 34812 只基金挨个打一遍上游，是明确的限流事故。故 targets 为空 → 返回空
→ 由 ``_allow_empty_data`` 静默跳过，绝不自动放大。

调用方式：

    pdm run python -m app.tools.sync_cli job manager_tenure --full-sync --targets 005827,110011

## 口径

- **不造关系**：关联关系由 ``fund_manager`` job 的经理全量表决定；本 job 对库里
  不存在的 (基金, 经理) 组合直接跳过，**不凭任期数据造关系**；
- **取「仍在任」的那一段**（:func:`find_tenure`，实测张坤在 005827 有两段任期，
  取错段会把现任显示成已卸任的人）；
- **幂等键 = (fund_id, mgr_id, start_date)**：同一段反复抓取只落一行；
- **``end_date`` 要能改**：在任段下次抓到时若已带卸任日，必须更新 —— 「任职起止」
  这个字段的全部价值就在这条；只插不改会让卸任永远不生效；
- 抓不到 / 姓名对不上 → 跳过，**不写占位日期**（诚实降级 §6）。
"""

from typing import List

from loguru import logger

from app.domains.funds.models import Fund, FundManager, Manager, ManagerTenure
from app.services.adapters.manager_tenure import find_tenure
from app.services.job_base import SyncJob


class ManagerTenureSyncJob(SyncJob):
    """按目标基金逐只抓 F10 任期，写入 ``manager_tenures``（#2239）。"""

    @property
    def _allow_empty_data(self) -> bool:
        # 目标池为空（或全部抓取失败）时静默跳过，不阻断整体同步。
        # ⚠️ 这里的「空」只可能来自「没给 targets」或「上游抓不到」，
        # 绝不来自「自动放大到全库」——见模块 docstring 的安全边界。
        return True

    def get_name(self) -> str:
        return 'manager_tenure'

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """逐只基金抓任期分段。

        **不做 targets 为空时取全库的兜底**（理由见模块 docstring）。
        """
        codes = [c for c in (targets or []) if c]
        if not codes:
            return []

        out: List[dict] = []
        for code in codes:
            segments = self.adapter.fetch_tenures(code)
            if not segments:
                # 抓不到不算错误（页面缺失 / 上游抖动），记 stats 供审计，继续下一只
                self.stats.setdefault('unavailable', []).append(code)
                continue
            out.append({'fund_code': code, 'segments': segments})
        return out

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [item for item in raw_data if item.get('fund_code') and item.get('segments')]

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """按 ``fund_code`` 去重（同一只基金在一次运行里只处理一次）。

        **不按库内已有值过滤**：本 job 的写入对象恰恰是「库里已有行」，
        按已有值去重会把要更新的行整批丢掉（``fund_manager`` job 踩过同样的坑，
        见 PR #2081）。
        """
        seen: set = set()
        deduped: List[dict] = []
        for item in data:
            code = item['fund_code']
            if code in seen:
                continue
            seen.add(code)
            deduped.append(item)
        return deduped

    # ── 写入 ──

    def _save_data(self, new_data: List[dict]) -> None:
        """把 F10 抓到的任期分段写进 ``manager_tenures``（#2239）。

        对库里没有关联的 (基金, 经理) 组合**直接跳过** —— 关系只由经理全量表决定，
        不凭任期数据反向造关系（否则会凭空长出一批关联）。

        三条写入口径：

        1. **幂等键 = (fund_id, mgr_id, start_date)**（``uq_manager_tenures_fund_mgr_start``）：
           同一段反复抓取只落一行，已有则改、没有则插；
        2. **``end_date`` 允许变**：在任段下次抓到时若已带卸任日，必须更新 ——
           「任职起止」这个字段的全部价值就在这条，只插不改会让卸任永远不生效。
           ``start_date`` 变了则视为**另一段**（真实场景里换了一段任期，就该多一行）；
        3. **``current`` 同批维护**：本段在任（``end_date`` 为空）时，把同 (基金, 经理)
           的其它段翻成 False —— 「当前在任段」最多一条，否则读侧按它筛选代表作
           会跨轮次选错人。

        **同值不写**：三个字段都没变时跳过，避免每次运行把整行标脏
        （``n_changed`` 也因此是「真实变更数」）。
        """
        stats = {
            'scanned': 0,
            'matched': 0,
            'unchanged': 0,
            'inserted': 0,
            'updated': 0,
            'no_rel': 0,
        }

        for item in new_data:
            code = item['fund_code']
            segments = item['segments']

            fund = self.db.query(Fund).filter(Fund.fund_code == code).first()
            if fund is None:
                stats['no_rel'] += 1
                continue
            stats['scanned'] += 1

            rels = (
                self.db.query(Manager.id, Manager.name)
                .join(FundManager, FundManager.mgr_id == Manager.id)
                .filter(FundManager.fund_id == fund.id)
                .all()
            )
            if not rels:
                stats['no_rel'] += 1
                continue

            for mgr_id, mgr_name in rels:
                tenure = find_tenure(segments, mgr_name)
                if tenure is None:
                    continue
                stats['matched'] += 1
                is_current = tenure['end_date'] is None

                row = (
                    self.db.query(ManagerTenure)
                    .filter(
                        ManagerTenure.fund_id == fund.id,
                        ManagerTenure.mgr_id == mgr_id,
                        ManagerTenure.start_date == tenure['start_date'],
                    )
                    .first()
                )
                if row is None:
                    self.db.add(
                        ManagerTenure(
                            fund_id=fund.id,
                            mgr_id=mgr_id,
                            start_date=tenure['start_date'],
                            end_date=tenure['end_date'],
                            current=is_current,
                            source='jjjl_f10',
                        )
                    )
                    stats['inserted'] += 1
                else:
                    dirty = False
                    if row.end_date != tenure['end_date']:
                        row.end_date = tenure['end_date']
                        dirty = True
                    if row.current != is_current:
                        row.current = is_current
                        dirty = True
                    if dirty:
                        stats['updated'] += 1
                    else:
                        stats['unchanged'] += 1

                if is_current:
                    # 其它段让位。查询量有界：只扫本基金下该经理的段（正常 1–2 段）
                    for other in (
                        self.db.query(ManagerTenure)
                        .filter(
                            ManagerTenure.fund_id == fund.id,
                            ManagerTenure.mgr_id == mgr_id,
                            ManagerTenure.start_date != tenure['start_date'],
                            ManagerTenure.current.is_(True),
                        )
                        .all()
                    ):
                        other.current = False

        if stats['inserted'] or stats['updated']:
            self.db.flush()
        self.db.commit()
        # 暴露到 self.stats：`run()` 的返回值与 sync_logs 都读它，便于事后回答
        # 「这轮到底写了几段、有多少只是抓不到」——只写日志答不了。
        self.stats['tenure'] = stats
        logger.info(f'任期写入完成: {stats}')
