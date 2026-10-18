# app/services/sync/jobs/fund_detail_enrich_job.py
"""
基金详细信息补充任务。
对传入的目标基金列表，补充分类、公司、费率、拼音等静态信息。

注意：pypinyin 是重型依赖（自带 3.2MB 词典），仅在生成拼音简拼时才需要，
因此刻意不放在模块顶层导入，避免应用启动/无关路径（如批量测试、其他 Job）
加载它导致峰值内存暴涨（曾在本机多进程 pytest-xdist 下触发 OOM）。
这是与 tasks.py 中 `-p no:xdist` 正交的额外防护，不要挪回顶层。
"""

import time
import traceback
from datetime import date
from typing import Any, Dict, List

from loguru import logger
from sqlalchemy.orm import Session

from app.core.time_utils import now_shanghai
from app.domains.funds.models import Fund, FundType
from app.services.fund_service import FundService
from app.services.job_base import BATCH_SIZE_DETAIL_ENRICH, JobStatus, SyncJob
from app.services.sync.company_resolver import get_or_create_fund_company
from app.services.sync.fund_type_resolution import FundTypeResolver


class FundDetailEnrichJob(SyncJob):
    def __init__(self, akshare_adapter, xalpha_adapter, db: Session):
        super().__init__(akshare_adapter, db)
        self.akshare_adapter = akshare_adapter
        self.xalpha_adapter = xalpha_adapter

    def get_name(self) -> str:
        return 'fund_detail_enrich'

    # 以下四个方法是基类抽象方法的占位实现（本 Job 使用自定义 run 流程）
    def _fetch_data(self, full_sync: bool, targets: List[str]) -> List[dict]:
        return []

    def _validate_data(self, raw_data: List[dict]) -> List[dict]:
        return []

    def _deduplicate(self, data: List[dict]) -> List[dict]:
        return []

    def _save_data(self, new_data: List[dict]) -> None:
        pass

    # ── 主流程 ──

    def run(self, full_sync: bool = False, targets: List[str] = None) -> Dict[str, Any]:
        self.snapshot_time = now_shanghai()
        self.status = JobStatus.RUNNING
        self._pre_run()
        self.logger.info('开始补充基金详情')

        self.stats = {'enriched': 0, 'skipped': 0, 'not_found': [], 'fee_refused': [], 'errors': []}

        if not targets:
            self.logger.info('无基金需要补充详情')
            self.status = JobStatus.SUCCESS
            return self._build_result()

        total = len(targets)
        batch_size = getattr(self, 'batch_size', BATCH_SIZE_DETAIL_ENRICH)

        for i in range(0, total, batch_size):
            batch = targets[i : i + batch_size]
            self.logger.info(f'详情进度: {min(i + batch_size, total)}/{total}')

            for code in batch:
                try:
                    fund = self.db.query(Fund).filter_by(fund_code=code).first()
                    if not fund:
                        # 目标代码在库里不存在 → 必须显式记账。旧写法是静默 continue，
                        # 于是「一个都没匹配上」会跑成 enriched 0 / skipped 0 / errors 0
                        # 的假成功（2026-10-18 实测：指向了另一个库时整轮静默空跑）。
                        # 空 ≠ 没拿到：拿不到就得说拿不到。
                        self.stats['not_found'].append(code)
                        continue
                    # 今日已处理则跳过
                    if fund.last_nav_check and fund.last_nav_check.date() == date.today():
                        self.stats['skipped'] += 1
                        continue

                    # 获取详情和费率
                    akshare_detail = self.akshare_adapter.fetch_fund_detail(code)
                    xalpha_fee = self.xalpha_adapter.fetch_fund_fee(code)

                    # 更新基本信息
                    self._update_fund_basics(fund, akshare_detail)
                    # 更新费率
                    try:
                        refused = self._update_fund_fees(code, xalpha_fee)
                    except Exception as e:
                        logger.warning(f'更新基金 {code} 费率失败: {e}\n{traceback.format_exc()}')
                    else:  # ✅ 只有没报错，才执行这行统计和标记
                        if refused == 'fee_refused':
                            # 拒写不是失败（刻意保住了旧数据），但也**不是**成功——
                            # 混进 enriched 就等于把「这只的费率没更新」藏起来
                            self.stats['fee_refused'].append(code)
                        fund.last_nav_check = now_shanghai()
                        self.stats['enriched'] += 1

                except Exception as e:
                    logger.warning(f'补充基金 {code} 详情失败: {e}')
                    self.stats['errors'].append({'fund_code': code, 'error': str(e)})

            # 批次提交
            enriched_before = self.stats['enriched']
            try:
                self.db.commit()
            except Exception as e:
                self.db.rollback()
                logger.error(f'批次提交失败: {e}')
                # #1833：commit 失败意味着这一批的写入**全部丢失**，而逐只累加的
                # enriched 计数不会自动回退。若仍记 SUCCESS，sync_logs 里就留下一条
                # 「enriched=N 但一条都没落库」的假成功，get_last_sync_time 还会拿它
                # 当增量基线，health 也会报「调度正常」。口径照 asset_snapshot_job /
                # position_price_job（有 errors 就 FAILED）。
                self.stats['errors'].append({'stage': 'batch_commit', 'batch_size': len(batch), 'error': str(e)})
                self.stats['enriched'] = enriched_before

            time.sleep(1)  # 避免请求过快

        self._post_run()
        # 目标一个都没匹配上：判 FAILED。「跑完了」不等于「做对了」——旧实现这里静默成功，
        # 而调用方（含 get_last_sync_time 的增量基线）会把假成功当依据。
        all_targets_missing = bool(self.stats['not_found']) and not (
            self.stats['enriched'] or self.stats['skipped']
        )
        if all_targets_missing:
            sample = ', '.join(self.stats['not_found'][:10])
            logger.error(
                f'{len(self.stats["not_found"])} 个目标代码在 funds 表里全部找不到'
                f'（样本: {sample}）——本轮什么也没做。请确认目标是已入库基金，'
                f'且连接的是预期数据库。'
            )
            self.stats['errors'].append(
                {
                    'stage': 'resolve_targets',
                    'error': f'{len(self.stats["not_found"])} 个目标代码在 funds 表里不存在',
                }
            )
        elif self.stats['not_found']:
            logger.warning(
                f'{len(self.stats["not_found"])} 个目标代码在 funds 表里不存在，已跳过'
                f'（样本: {", ".join(self.stats["not_found"][:10])}）'
            )
        if self.stats['fee_refused']:
            # 拒写= 保住旧数据而不是写入新数据，需要被看见：否则费率会停在错误值上，
            # 而日志只显示 enriched=N，看不出其中有多少根本没更新
            logger.warning(
                f'{len(self.stats["fee_refused"])} 只基金的赎回费率阶梯结构非法被拒写'
                f'（既有费率保持不变，需修好上游解析后重跑修复）'
                f'（样本: {", ".join(self.stats["fee_refused"][:10])}）'
            )
        # 有 errors 就判 FAILED：不能一边记录错误一边宣称成功（#1833）
        self.status = JobStatus.FAILED if self.stats.get('errors') else JobStatus.SUCCESS
        self.logger.info(
            f'基金详情补充完成: 新增 {self.stats["enriched"]}, '
            f'跳过 {self.stats["skipped"]}, 未匹配 {len(self.stats["not_found"])}, '
            f'费率拒写 {len(self.stats["fee_refused"])}, 错误 {len(self.stats["errors"])}'
        )
        return self._build_result()

    # ── 基本信息更新 ──

    def _update_fund_basics(self, fund: Fund, detail: Dict[str, Any]) -> None:
        """根据 akshare 详情更新 fund 表的静态字段"""
        if not detail:
            return

        # 基金类型映射（文本 -> canonical ID 下沉到 FundTypeResolver，本 Job 只负责落库）
        raw_type = detail.get('fund_type_raw')
        raw_variety = detail.get('fund_variety_raw')
        if raw_type and not fund.fund_type_id:
            type_id, variety_id = FundTypeResolver(self.db).resolve(raw_type, raw_variety)
            fund.fund_type_id = type_id
            if variety_id and not fund.fund_variety_id:
                fund.fund_variety_id = variety_id

        # 若已有小类但缺大类，单独补全（resolver 回填大类并同步 fund_type 关联）
        if fund.fund_type_id and not fund.fund_variety_id and raw_variety:
            _, variety_id = FundTypeResolver(self.db).resolve(raw_type='', raw_variety=raw_variety)
            if variety_id:
                fund.fund_variety_id = variety_id
                fund_type = self.db.query(FundType).filter_by(id=fund.fund_type_id).first()
                if fund_type and fund_type.variety_id is None:
                    fund_type.variety_id = variety_id
                    self.db.flush()

        # 基金公司
        company_name = detail.get('company_name')
        if company_name and not fund.company_id:
            fund.company_id = self._get_or_create_company(company_name)

        # 全称
        if detail.get('fund_full_name') and not fund.full_name:
            fund.full_name = detail['fund_full_name']

        # 成立日期
        if detail.get('create_time') and not fund.create_time:
            fund.create_time = detail['create_time']

        # 业绩比较基准
        if detail.get('benchmark') and not fund.benchmark:
            fund.benchmark = detail['benchmark']

        if detail.get('risk_level') and not fund.risk_level:
            fund.risk_level = detail['risk_level']

        # 拼音简拼
        if fund.name and not fund.pinyin_abbr:
            fund.pinyin_abbr = self._generate_pinyin_abbr(fund.name)

    @staticmethod
    def _generate_pinyin_abbr(name: str) -> str:
        """
        生成拼音首字母简拼（仿天天基金规则：英文/数字原样保留，特殊符号跳过）。
        示例: "华夏成长混合" -> "HXCZHH"

        实现已抽取到 sync/pinyin_utils.generate_pinyin_abbr（amac_institution_job
        同样需要，#1081），此处保留方法作委托，兼容类内既有调用点。
        """
        from app.services.sync.pinyin_utils import generate_pinyin_abbr

        return generate_pinyin_abbr(name)

    # ── 费率更新 ──

    def _update_fund_fees(self, fund_code: str, fee_info: Dict[str, Any]) -> str:
        """按上游费率信息**镜像**更新 fee_ratios（申购 + 赎回）。

        全部委托 `FundService.apply_purchase_fee` / `apply_redeem_schedule`——结构校验
        （阶梯非法即拒写）、upsert（费率变了要能改回来）、删除上游已不存在的档位，
        三件事都在那一处实现。

        本文件此前**自己抄了一份**写入逻辑，与 `FundService.sync_fund_fees` 各改各的：
        两份实现都只有「查不到才插」，于是解析缺陷写进去的错误费率没有任何路径会
        自愈（2026-10-18 查实：本机 334 只基金的赎回阶梯结构已损坏）。

        返回 ``'fee_refused'`` 表示阶梯结构非法、**被拒写**（库内既有数据保持不动）。
        调用方必须把它单独记账：拒写是刻意保数据，不是「这只处理成功了」——旧实现
        只 warning 不抛异常，于是 `enriched` 把被拒的基金也算成功，日志里
        `enriched=100` 混着 29 只拒写，看日志的人完全看不出来。
        """
        if not fee_info:
            return 'ok'

        # 费率币种：按基金份额名称特征推导（无结构化币种字段可依赖）
        fund = self.db.query(Fund).filter_by(fund_code=fund_code).first()
        currency = FundService.infer_fund_currency(full_name=fund.full_name, name=fund.name) if fund else 'CNY'

        FundService.apply_purchase_fee(self.db, fund_code, fee_info.get('purchase_rate'), currency)

        redemption_schedule = fee_info.get('redemption_schedule', [])
        if isinstance(redemption_schedule, list):
            outcome = FundService.apply_redeem_schedule(
                self.db,
                fund_code,
                [item for item in redemption_schedule if isinstance(item, dict)],
                currency,
            )
            if outcome.get('skipped'):
                logger.warning(
                    f'基金 {fund_code} 赎回费率阶梯结构非法，已拒写（既有数据不动）: ' + '; '.join(outcome['skipped'])
                )
                return 'fee_refused'
        return 'ok'

    def _get_or_create_company(self, company_name: str) -> int:
        # 唯一写入口（company_resolver）：归一化匹配既有行，杜绝为同一主体建第二行
        if getattr(self, '_fund_company_cache', None) is None:
            self._fund_company_cache: Dict[str, int] = {}
        return get_or_create_fund_company(self.db, company_name, cache=self._fund_company_cache)
