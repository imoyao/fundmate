# app/services/sync/jobs/amac_institution_job.py
"""AMAC 销售机构 + 公募基金管理人名录同步任务（全量，低频）。

为什么用独立 job 而不是普通适配器：
- AMAC 是 HTTP JSON 接口（GBK 编码），不属于 akshare/xalpha 数据源；
- 本 job 与 TemperatureJob 同模式：NullAdapter 占位 + job 内部抓取。

数据生命周期：
- 权威全称（org_name/house_name）是唯一基准（身份证），幂等 upsert，不删除；
- is_active 标记是否仍在 AMAC 公示名单内——机构下架/倒闭时置 False，
  历史数据保留（保护对账溯源），不物理删除。
- 常用机构策展（#1081）：CURATED_INSTITUTIONS 命中行覆写 is_common/common_sort/
  display_name（代码即 source of truth，保证多环境迁移收敛）；未命中行的
  display_name 维持「仅首次写入」语义，不覆盖。
"""

import time
from typing import List

import requests

from app.domains.positions.models import FundManagementCompany, SalesInstitution
from app.services.sync.jobs.base import SyncJob

AMAC_AGENCY_URL = 'https://www.amac.org.cn//portal/front/infopublic/fsAgencyAnno/findFsAgencyAnnos'
AMAC_HOUSE_URL = 'https://www.amac.org.cn/portal/front/mutualFund/findMutualFundHousePage'

# 常用机构策展（#1081）：权威全称 → (常用别名|None, 常用组内排序)。
# sort 取中基协「基金保有规模」排名（保真来源，允许跳号）；名单成员极稳定，
# 排名会季度性变动——过期无害，更新即改本常量 + 一次提交（设计文档 D4/D5）。
# 应用语义：upsert 时对命中行覆写 is_common/common_sort/display_name——
# 代码即 source of truth，保证本地/生产/灾备重建各环境收敛（设计文档 D6）；
# 未命中行不触碰这三个字段（display_name 维持「仅首次写入」既有语义）。
# 注意：key 必须与 AMAC 名录实际权威全称完全一致（2026-08-24 与库内 394 条逐一核对，
# 含全角括号与「北京雪球」等易错点）；仅销售机构表有策展列，基金管理人（house）勿登记。
CURATED_INSTITUTIONS = {
    '蚂蚁（杭州）基金销售有限公司': ('支付宝', 1),
    '招商银行': (None, 2),
    '上海天天基金销售有限公司': ('天天基金', 3),
    '中国工商银行': (None, 4),
    '中国建设银行': (None, 5),
    '中国银行': (None, 6),
    '交通银行': (None, 7),
    '中信证券': (None, 8),
    '中国人寿保险股份有限公司': ('中国人寿', 9),
    '中国农业银行': (None, 10),
    '腾安基金销售（深圳）有限公司': ('理财通', 13),
    '珠海盈米基金销售有限公司': ('且慢', 26),
    '京东肯特瑞基金销售有限公司': ('京东金融', 32),
    '浙江同花顺基金销售有限公司': ('同花顺', 33),
    '北京雪球基金销售有限公司': ('雪球基金', 36),
}

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    ),
    'Referer': 'https://www.amac.org.cn/',
    'Accept': 'application/json, text/plain, */*',
}

PAGE_SIZE = 500  # AMAC 接口单页上限
REQUEST_INTERVAL = 1.0  # 请求间隔（秒），礼貌抓取


class AmacInstitutionJob(SyncJob):
    @property
    def _allow_empty_data(self) -> bool:
        return False

    def get_name(self) -> str:
        return 'amac_institution'

    # ── 数据获取 ──

    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        """抓取两类名录，统一打 kind 标记后返回。"""
        items: List[dict] = []
        items.extend(self._fetch_paged(AMAC_AGENCY_URL, 'sales', 'orgName'))
        items.extend(self._fetch_paged(AMAC_HOUSE_URL, 'house', 'houseName'))
        return items

    def _fetch_paged(self, url: str, kind: str, name_key: str) -> List[dict]:
        """分页拉取单接口全量数据（礼貌间隔）。

        编码：AMAC 接口响应头为 `application/json;charset=UTF-8`，
        依赖响应头自动解码（requests 默认按 charset 处理），
        **禁止**手动设置 `resp.encoding`——曾因硬编码 gbk 把 UTF-8
        字节解成乱码写入库中，污染数据（2026-08-17 事故复盘）。
        """
        items: List[dict] = []
        page = 1
        while True:
            resp = requests.get(
                url,
                params={'pageNo': page, 'pageSize': PAGE_SIZE},
                headers=HEADERS,
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()['data']['data']
            data_list = payload.get('dataList') or []
            total = payload.get('total') or 0
            for row in data_list:
                row['kind'] = kind
                items.append(row)
            self.logger.info(f'[amac:{kind}] 第 {page} 页拉取 {len(data_list)} 条（累计 {len(items)}/{total}）')
            if page * PAGE_SIZE >= total or not data_list:
                break
            page += 1
            if len(items) < total:  # 仅未拉完时礼貌等待
                time.sleep(REQUEST_INTERVAL)
        return items

    # ── 数据校验 ──

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        """按 kind 校验必填字段（权威全称非空）。

        编码守卫：名称含 U+FFFD 替换符（�）说明解码失败/乱码，
        直接丢弃并告警，**绝不写入库中**（2026-08-17 乱码污染事故后新增）。
        """
        validated = []
        for item in raw_data:
            name = (item.get('orgName') or item.get('houseName') or '').strip()
            if not name:
                continue
            if '\ufffd' in name:
                self.logger.warning(f'[amac] 名称含乱码替换符，丢弃: {name!r}')
                continue
            validated.append(item)
        return validated

    # ── 去重 ──

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        """不过滤——save 层做 upsert（需更新元数据 + is_active，不能跳过已存在记录）。"""
        return data

    # ── 保存 ──

    def _save_data(self, new_data: List[dict]) -> None:
        self._seen_org_names: set = set()
        self._seen_house_names: set = set()

        for item in new_data:
            if item.get('kind') == 'sales':
                self._upsert_sales(item)
            else:
                self._upsert_house(item)
        self.db.commit()

    def _upsert_sales(self, item: dict) -> None:
        org_name = item['orgName'].strip()
        self._seen_org_names.add(org_name)
        curated = CURATED_INSTITUTIONS.get(org_name)
        row = self.db.query(SalesInstitution).filter_by(org_name=org_name).first()
        if row:
            row.reg_addr = item.get('regAddr') or row.reg_addr
            row.org_type = item.get('orgType') or row.org_type
            row.check_time = item.get('checkTime') or row.check_time
            row.is_active = True  # 仍在公示名单 → 恢复/保持 active
            if curated:
                # 策展行覆写三件套：代码即 source of truth，保证多环境收敛（见常量注释）
                row.display_name, row.common_sort = curated
                row.is_common = True
        else:
            self.db.add(
                SalesInstitution(
                    org_name=org_name,
                    reg_addr=item.get('regAddr'),
                    org_type=item.get('orgType'),
                    check_time=item.get('checkTime'),
                    display_name=curated[0] if curated else None,
                    is_common=bool(curated),
                    common_sort=curated[1] if curated else None,
                    is_active=True,
                )
            )
            self.stats['success'] += 1

    def _upsert_house(self, item: dict) -> None:
        house_name = item['houseName'].strip()
        self._seen_house_names.add(house_name)
        row = self.db.query(FundManagementCompany).filter_by(house_name=house_name).first()
        if row:
            row.register_addr = item.get('registerAddr') or row.register_addr
            row.office_addr = item.get('officeAddr') or row.office_addr
            row.website = item.get('website') or row.website
            row.phone = item.get('phone') or row.phone
            row.is_active = True
        else:
            self.db.add(
                FundManagementCompany(
                    house_name=house_name,
                    register_addr=item.get('registerAddr'),
                    office_addr=item.get('officeAddr'),
                    website=item.get('website'),
                    phone=item.get('phone'),
                    is_active=True,
                )
            )
            self.stats['success'] += 1

    # ── 后置：下架/倒闭保护 ──

    def _post_run(self) -> None:
        """把库中 is_active=True 但不在本次 AMAC 名单内的机构标记为失效（保留记录不删除）。"""
        inactive_orgs = (
            self.db.query(SalesInstitution)
            .filter(SalesInstitution.is_active.is_(True), SalesInstitution.org_name.notin_(self._seen_org_names))
            .all()
        )
        for row in inactive_orgs:
            row.is_active = False
            self.logger.warning(f'销售机构已不在 AMAC 公示名单，标记失效: {row.org_name}')

        inactive_houses = (
            self.db.query(FundManagementCompany)
            .filter(
                FundManagementCompany.is_active.is_(True),
                FundManagementCompany.house_name.notin_(self._seen_house_names),
            )
            .all()
        )
        for row in inactive_houses:
            row.is_active = False
            self.logger.warning(f'基金管理人已不在 AMAC 公示名单，标记失效: {row.house_name}')

        if inactive_orgs or inactive_houses:
            self.db.commit()
