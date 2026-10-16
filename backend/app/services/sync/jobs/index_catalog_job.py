# -*- coding: utf-8 -*-
"""指数名录同步任务（#1286 数据底座；#1365 三源合并）。

与 index_constituent_job 的分工：名录回答「有哪些指数」（搜索/自选引用），
成分回答「某指数里有哪些股票」。

三源合并（2026-09-09，调研见 docs/working-notes/index-catalog-sources-research-2026-09-08.md）：
- 新浪 index_stock_info：交易所挂牌指数（带 SH/SZ 归属）
- 中证官网 index_csindex_all：中证专属码唯一来源（930950/932000/000510）
- 国证官网 index_all_cni：国证专属码唯一来源（399303/399317）
去重优先级 sina > csindex > cni（sina 带交易所归属信息最全）；
万得系（881001 万得全A 等）三源均无免费权威收录（同调研文档），原先仅以
399317 国证A指 / 000985 中证全指替代——用户搜「万得全A」零命中、加不了自选。
#2217 起以**静态名录**并入（WIND_INDEX_CATALOG_PAIRS，(code, name) 对复制自
sync/jobs/index_daily_job.py 的 WIND_INDEX_TARGETS；该文件被 open PR #2206 占用
只读不改，且名录 job 不该反向依赖点位 job 的运行时模块），随三源同走
重建 / 去重 / 白名单保留流程；仅在三源至少一路有数据时并入（见 _fetch_data 注释）。
"""

from typing import List

from loguru import logger

from app.domains.indices.models import PUBLISHER_BY_SOURCE, IndexCatalog
from app.services.job_base import SyncJob

# 万得系静态名录（#2217）：(index_code, name) 对，index_code 一律**裸码**（不带 .WI 后缀）。
# 为什么是裸码：index_catalog 全表约定即裸码——搜索侧的前缀归一
# （asset_search._search_indices）、自选展示名反查（watchlist_service.bare_code_of）、
# 详情页目录反查（product_identity._infer_asset_type_from_catalog / index_profile
# 的 _bare_index_code）全都按裸码匹配；index_daily 才存数据源原生形态（881001.WI）。
# 若把「881001.WI」写进名录，bare_code_of('881001.WI') → '881001' ≠ 存值，
# 自选列表显示名将永远落空、退化成代码。
# (code, name) 复制自 sync/jobs/index_daily_job.py 的 WIND_INDEX_TARGETS
# （该文件被 open PR #2206 占用，只许读不许改；复制而非 import，故若点位清单
# 增删品种，须记得同步本清单各一行——两份都是 (code, name) 对，逐行对照即可）。
WIND_INDEX_CATALOG_PAIRS: List[tuple] = [
    ('881001', '万得全A'),
    ('881003', '万得全A(除金融、石油石化)'),
    ('881007', '万得300除金融'),
    ('8841425', '万得小市值指数'),
    ('8841431', '万得微盘股指数'),
    ('885000', '万得普通股票型基金指数'),
    ('885001', '万得偏股混合型基金指数'),
    ('885002', '万得平衡混合型基金指数'),
    ('885003', '万得偏债混合型基金指数'),
    ('885005', '万得债券型基金指数'),
    ('885006', '万得混合债券型一级基金指数'),
    ('885007', '万得混合债券型二级基金指数'),
    ('885008', '万得中长期纯债型基金指数'),
    ('889033', '万得可转债等权指数'),
    ('885072', '万得混合型FOF指数'),
    ('885073', '万得偏股混合型FOF指数'),
    ('885074', '万得平衡混合型FOF指数'),
    ('885075', '万得偏债混合型FOF指数'),
]


class IndexCatalogSyncJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        # 三源全空视为接口异常，静默跳过，避免清空既有名录
        return True

    def get_name(self) -> str:
        return 'index_catalog'

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        # 顺序即去重优先级（_deduplicate 保留首次出现）：sina > csindex > cni
        fetchers = [
            ('sina', self.adapter.fetch_index_catalog),
            ('csindex', self.adapter.fetch_index_catalog_csindex),
            ('cni', self.adapter.fetch_index_catalog_cni),
        ]
        out: List[dict] = []
        for name, fetch in fetchers:
            try:
                rows = fetch()
                out.extend(rows)
                logger.info(f'指数名录源 {name} 获取 {len(rows)} 条')
            except Exception as e:
                # 单源失败不阻断其他源（名录覆盖面优先于单源完整性）
                logger.warning(f'指数名录源 {name} 获取失败: {e}')
        # 万得系静态名录并入（#2217）。排在三源之后 append → _deduplicate 保留首现，
        # 万一三源某条目与万得码同码，以三源条目为准。
        #
        # **必须挂在 `if out` 上**：三源全空 = 接口异常，基类靠「raw_data 为空」跳过
        # 整体重建（_allow_empty_data + run() 的空判 + _save_data 的空守卫三道闸）。
        # 静态行无条件并入会把「空」变成「非空（18 条）」，覆盖式重建随即把 ~4100 行
        # 名录抹成只剩万得系十几行——数据不可恢复，这是本改动最危险的一处。
        if out:
            out.extend(
                [
                    {'index_code': idx_code, 'name': idx_name, 'exchange': None, 'source': 'wind', 'publisher': 'WIND'}
                    for idx_code, idx_name in WIND_INDEX_CATALOG_PAIRS
                ]
            )
        return out

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return [r for r in raw_data if r.get('index_code') and r.get('name')]

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        # 按 index_code 去重，保留首次出现（即高优先级源）；表列 unique 约束兜底
        seen = set()
        out = []
        for r in data:
            if r['index_code'] in seen:
                continue
            seen.add(r['index_code'])
            out.append(r)
        return out

    def _save_data(self, new_data: List[dict]) -> None:
        # 空数据直接返回：基类 run() 已用 `if new_data` 守住，此处二次防御——
        # 名录是整体 DELETE 重建，任何旁路调用传入空列表都会抹掉全表（#1362 评审）
        if not new_data:
            return
        # 名录整体覆盖式重建（条目量 ~千级，成本可忽略）。
        # is_core / core_rank 是人工策展字段（seed_core_indices.py 维护），
        # 重建前快照、重建后回填，避免每次同步抹掉白名单标记（#1365）。
        prev_flags = {
            r.index_code: (r.is_core, r.core_rank)
            for r in self.db.query(IndexCatalog.index_code, IndexCatalog.is_core, IndexCatalog.core_rank).all()
        }
        self.db.query(IndexCatalog).delete(synchronize_session=False)
        for r in new_data:
            is_core, core_rank = prev_flags.get(r['index_code'], (False, None))
            source = r.get('source', 'sina')
            self.db.add(
                IndexCatalog(
                    index_code=r['index_code'],
                    name=r['name'],
                    exchange=r.get('exchange'),
                    source=source,
                    # 编制/发布机构（#1425）：三源行按来源回填（csindex→CSI、cni→CNI）；
                    # 万得系静态行（#2217）自带 publisher='WIND'（INDEX_PUBLISHER_LABELS
                    # 已预定义 WIND=万得），经 or 兜底优先取行内值。
                    # sina 为行情转发源无法权威判定 → 留空（NULL），前端不展示该维度。
                    publisher=r.get('publisher') or PUBLISHER_BY_SOURCE.get(source),
                    is_core=is_core,
                    core_rank=core_rank,
                )
            )
        self.db.commit()
        kept = sum(1 for v in prev_flags.values() if v[0])
        logger.info(f'指数名录重建完成，共 {len(new_data)} 条（核心白名单保留 {kept} 条）')
