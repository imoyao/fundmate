# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/7/4 9:58
# File : fund_service.py
# backend/app/services/fund_service.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.money import Money
from app.domains.funds.models import (
    DailyWorth,
    FeeRatio,
    Fund,
    MoneyFundDailyWorth,
    PurchaseRule,
    RedeemRule,
)
from app.domains.positions.models import Position
from app.domains.transactions.models import Transaction
from app.services.sync.adapters.xalpha_adapter import XalphaAdapter


class FundService:
    """基金领域服务：净值获取、搜索、费率查询、赎回费估算"""

    # ─── 币种推导 ─────────────────────────────────

    # 基金名称/全称中的外币份额特征 → ISO 4217 币种。
    # 东财/同花顺接口均无干净的币种字段（2026-08-10 实证：pingzhongdata / jjfl / f10
    # 基本资料页 / fund_info_ths 均不含），故按基金份额名称特征推导：
    # 境内基金恒为人民币，仅 QDII 等外币份额（如"美元现汇/现钞"）为外币。
    # "人民币"必须排最前：部分 QDII 名称同时含"美元"与"人民币"
    # （如"中银美元债债券(QDII)人民币A"，实为人民币份额），优先匹配人民币。
    _CURRENCY_MARKERS = (
        ('人民币', 'CNY'),
        ('美元', 'USD'),
        ('港币', 'HKD'),
        ('港元', 'HKD'),
        ('日元', 'JPY'),
        ('欧元', 'EUR'),
        ('英镑', 'GBP'),
    )

    @staticmethod
    def infer_fund_currency(full_name: str = '', name: str = '') -> str:
        """根据基金全称/简称推导计费币种，无外币特征时默认 CNY。

        数据源无结构化币种字段，只能按名称特征推导：QDII 外币份额通常以
        "美元现汇/美元现钞/港币"等字样标注；含"人民币"或全无外币字样 → CNY。
        """
        text = f'{full_name} {name}'
        if not text.strip():
            return 'CNY'
        for marker, currency in FundService._CURRENCY_MARKERS:
            if marker in text:
                return currency
        return 'CNY'

    # ─── 净值获取 ─────────────────────────────────

    @staticmethod
    def _fetch_one_nav(fund_code: str, target_date: date) -> Optional[Decimal]:
        adapter = XalphaAdapter()
        result = adapter.fetch_fund_nav_by_date(fund_code, target_date)
        return Decimal(str(result)) if result is not None else None

    @staticmethod
    def _persist_navs(nav_map: Dict[str, Decimal], target_date: date) -> None:
        with SessionLocal() as db:
            try:
                for code, nav_val in nav_map.items():
                    existing = (
                        db.query(DailyWorth)
                        .filter(DailyWorth.fund_code == code, DailyWorth.date == target_date)
                        .first()
                    )
                    if existing:
                        existing.unit_nav = nav_val
                        existing.acc_nav = nav_val
                    else:
                        db.add(DailyWorth(fund_code=code, date=target_date, unit_nav=nav_val, acc_nav=nav_val))
                db.commit()
                logger.info(f'净值持久化成功: {len(nav_map)} 条记录')
            except Exception:
                db.rollback()
                logger.exception('净值持久化失败')
                raise

    @staticmethod
    def get_fund_nav_map(db: Session, symbols: List[str], target_date: date) -> Dict[str, Decimal]:
        """批量获取基金单位净值，优先库内，缺失时实时拉取并持久化"""
        nav_records = (
            db.query(DailyWorth.fund_code, DailyWorth.unit_nav)
            .filter(DailyWorth.fund_code.in_(symbols), DailyWorth.date == target_date)
            .all()
        )
        nav_map: Dict[str, Decimal] = {code: Decimal(str(nav)) for code, nav in nav_records if nav and nav > 0}

        missing = [s for s in symbols if s not in nav_map]
        if not missing:
            return nav_map

        logger.info(f'数据库净值缺失，实时拉取: {missing}')
        fetched: Dict[str, Decimal] = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(FundService._fetch_one_nav, code, target_date): code for code in missing}
            for future in as_completed(futures):
                code = futures[future]
                try:
                    val = future.result()
                    if val and val > 0:
                        fetched[code] = val
                except Exception as e:
                    logger.warning(f'实时拉取 {code} 净值失败: {e}')

        if fetched:
            FundService._persist_navs(fetched, target_date)
        nav_map.update(fetched)
        return nav_map

    # ─── 基金搜索 ─────────────────────────────────

    # 外部基金列表缓存（进程级，基金列表极少变动）：避免每次搜索都打 akshare
    _FUND_NAME_EM_CACHE: dict = {'ts': 0.0, 'data': None}
    _FUND_NAME_EM_TTL = 86400

    # 货基名称兜底词（仅在 fund_type_id 缺失时使用）。
    # 注意：单用「现金」过宽（存在「现金流」等非货基产品），故只收「货币」及
    # 明确的现金管理产品词。
    _CASH_LIKE_NAME_KEYWORDS = ('货币', '现金宝', '现金添利', '现金增利', '现金管家')

    @staticmethod
    def _judge_money_fund(
        fund_type_id: Optional[int],
        name: str,
        has_daily_worth: bool,
    ) -> Optional[bool]:
        """判定基金是否为货币基金，返回**三态** True / False / None（未知）。

        为什么不能只靠 `fund_type_id == 6`：本地库 fund_type_id 标注极不完整
        （23904/26938 为空，占 88.7%），仅按该字段判定会把约 691 条真货基误判为
        非货基——典型如 `026029 银河水星现金添利货币`（券商渠道现金管理产品，
        证券账户「活期+」的真实绑定标的），导致用户搜不到、绑不上。

        判据优先级（强 → 弱）：
          1. fund_type_id == 6                     → True（权威标注）
          2. money_fund_daily_worth 有万份收益记录  → True（有万份收益必为货基，
             且意味着收益计算口径可复用，是最可靠的实测判据）
          3. fund_type_id 非空且 != 6               → False（明确非货基）
          4. 类型缺失 + 名称命中货基词              → True（名称兜底）
          5. 其余                                    → None（未知）

        返回 None 而非 False 的意义：区分「明确不是」与「尚不清楚」，
        使前端「全量展示 + 选择时限制」时不误杀类型缺失的候选。
        """
        if fund_type_id == 6:
            return True
        if has_daily_worth:
            return True
        if fund_type_id is not None:
            return False
        name = name or ''
        if any(k in name for k in FundService._CASH_LIKE_NAME_KEYWORDS):
            return True
        return None

    # 货基渠道分类代码前缀（启发式，akshare/xalpha 无 market/上市字段，见 #1154）。
    # 场内货币ETF（511/519/159）属投资范畴，不纳入现金类；券商渠道现金管理（026/970）
    # 仅证券账户可绑；其余为场外货基，仅基金平台账户可绑。
    EXCHANGE_TRADED_MF_PREFIXES = ('511', '519', '159')
    BROKER_CHANNEL_MF_PREFIXES = ('026', '970')

    @staticmethod
    def _classify_money_fund_channel(fund_code: Optional[str]) -> str:
        """按代码前缀启发式判定货基渠道类别（#1154，方案 B）。

        akshare/xalpha 不提供 market/上市字段，只能靠代码前缀：
          - 'exchange_traded'：场内货币ETF（511/519/159），属投资范畴，不纳入现金类
          - 'broker_channel'：券商渠道现金管理产品（026/970）
          - 'off_exchange'：其余场外货基
        """
        if not fund_code:
            return 'off_exchange'
        prefix = fund_code[:3]
        if prefix in FundService.EXCHANGE_TRADED_MF_PREFIXES:
            return 'exchange_traded'
        if prefix in FundService.BROKER_CHANNEL_MF_PREFIXES:
            return 'broker_channel'
        return 'off_exchange'

    @staticmethod
    def search_funds(db: Session, keyword: str) -> List[Dict[str, Any]]:
        """模糊搜索基金（代码/名称/拼音）。

        本地 Fund 表优先；若本地完全无命中，追加 akshare fund_name_em 外部兜底，
        覆盖本地库尚未同步的基金（如用户持有的货基），使其也能按名称搜到（#交互修复）。
        返回项含 is_money_fund，为**三态** True/False/None，供前端筛选货基
        （判定细节见 FundService._judge_money_fund）。
        """
        keyword = (keyword or '').strip()
        if not keyword:
            return []

        funds = (
            db.query(Fund)
            .filter(
                Fund.fund_code.ilike(f'%{keyword}%')
                | Fund.name.ilike(f'%{keyword}%')
                | Fund.pinyin_abbr.ilike(f'%{keyword}%')
            )
            .limit(20)
            .all()
        )
        results = []
        seen = set()
        # 批量取「有万份收益记录」的基金代码：一次查询，避免逐条 N+1。
        # money_fund_daily_worth 有记录 ⇒ 该基金按货基口径同步 ⇒ 必为货基，
        # 这是比残缺的 fund_type_id 更可靠的实测判据（详见 _judge_money_fund）。
        worth_codes = set()
        if funds:
            worth_codes = {
                row[0]
                for row in db.query(MoneyFundDailyWorth.fund_code)
                .filter(MoneyFundDailyWorth.fund_code.in_([f.fund_code for f in funds]))
                .distinct()
                .all()
            }
        for f in funds:
            # 查询该基金第一条申购费率记录
            rate_record = (
                db.query(FeeRatio).filter(FeeRatio.fund_code == f.fund_code, FeeRatio.fee_type == 'purchase').first()
            )
            default_rate = 0.015
            rate = float(rate_record.rate) if rate_record and rate_record.rate is not None else default_rate
            results.append(
                {
                    'code': f.fund_code,
                    'name': f.name,
                    'type': 'fund',
                    'subscription_rate': rate,
                    # 货基识别字段（2026-08-14 补，2026-08-29 升级为三态）：
                    # 前端无法从代码段识别货基（000198 余额宝等 000 开头会被当普通基金建仓，
                    # 违背统一流水式口径），由后端权威判定。
                    # 三态 True/False/None：None = 类型未知，供前端「全量展示 + 选择时限制」，
                    # 避免 fund_type_id 缺失的货基（如 026029 银河水星现金添利货币）被误杀。
                    'fund_type_id': f.fund_type_id,
                    'is_money_fund': FundService._judge_money_fund(f.fund_type_id, f.name, f.fund_code in worth_codes),
                }
            )
            seen.add(f.fund_code)

        # 外部兜底：本地完全无命中时，用 akshare fund_name_em 补全（覆盖未同步基金）
        if not results:
            try:
                import time

                cache = FundService._FUND_NAME_EM_CACHE
                now = time.time()
                if cache['data'] is None or now - cache['ts'] > FundService._FUND_NAME_EM_TTL:
                    # #1363 修复：此前误拼 AKShareAdapter → ImportError 被下方 except 静默吞掉，
                    # 外部兜底自引入起从未生效。类名以 orchestrator 注册处（AkshareAdapter）为准。
                    from app.services.sync.adapters.akshare_adapter import AkshareAdapter

                    cache['data'] = AkshareAdapter().fetch_fund_list()
                    cache['ts'] = now
                kw = keyword.lower()
                for item in cache['data'] or []:
                    code = item.get('fund_code')
                    if not code or code in seen:
                        continue
                    name = item.get('name') or ''
                    if kw not in (code + name).lower():
                        continue
                    seen.add(code)
                    # 外部兜底同样走三态：fund_type 明确时以其为准，缺失时退到名称兜底
                    # （外部基金尚未同步万份收益，has_daily_worth 传 False）。
                    ext_type = item.get('fund_type')
                    if ext_type == '货币型':
                        ext_is_money_fund: Optional[bool] = True
                    elif ext_type:
                        ext_is_money_fund = False
                    else:
                        ext_is_money_fund = FundService._judge_money_fund(None, name, False)
                    results.append(
                        {
                            'code': code,
                            'name': name,
                            'type': 'fund',
                            'subscription_rate': 0.0,
                            'fund_type_id': None,
                            'is_money_fund': ext_is_money_fund,
                        }
                    )
                    if len(results) >= 20:
                        break
            except Exception as e:  # 外部失败不阻塞本地结果
                logger.warning(f'基金搜索外部兜底失败: {e}')

        return results

    # ─── 基金费率规则查询 ───────────────────────

    @staticmethod
    def get_fund_fee_rates(db: Session, fund_code: str) -> Optional[Dict[str, Any]]:
        """获取指定基金的申购/赎回费率结构"""
        fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
        if not fund:
            return None

        # 申购费率
        purchase_rates = []
        purchase_rows = (
            db.query(FeeRatio, PurchaseRule)
            .join(PurchaseRule, FeeRatio.purchase_rule_id == PurchaseRule.id)
            .filter(FeeRatio.fund_code == fund_code, FeeRatio.fee_type == 'purchase')
            .all()
        )
        for ratio, rule in purchase_rows:
            try:
                rate_val = float(ratio.rate) if ratio.rate is not None else 0.0
            except (ValueError, TypeError):
                rate_val = 0.0
            purchase_rates.append(
                {
                    'start_quota': Money.cents_to_yuan(rule.start_quota),
                    'end_quota': Money.cents_to_yuan(rule.end_quota) if rule.end_quota else None,
                    'rate': rate_val,
                }
            )

        # 赎回费率
        redeem_rates = []
        redeem_rows = (
            db.query(FeeRatio, RedeemRule)
            .join(RedeemRule, FeeRatio.redeem_rule_id == RedeemRule.id)
            .filter(FeeRatio.fund_code == fund_code, FeeRatio.fee_type == 'redeem')
            .all()
        )
        for ratio, rule in redeem_rows:
            try:
                rate_val = float(ratio.rate) if ratio.rate is not None else 0.0
            except (ValueError, TypeError):
                rate_val = 0.0
            redeem_rates.append(
                {
                    'start_day': rule.start_day,
                    'end_day': rule.end_day,
                    'rate': rate_val,
                }
            )

        return {
            'fund_code': fund_code,
            'currency': FundService.infer_fund_currency(full_name=fund.full_name, name=fund.name),
            'purchase': purchase_rates,
            'redeem': redeem_rates,
        }

    # ─── 赎回费估算 ──────────────────────────────

    @staticmethod
    def estimate_redeem_fee(
        db: Session,
        position_id: int,
        sell_date: date,
        sell_shares: Optional[float] = None,
        family_id: int = 1,
    ) -> Dict[str, Any]:
        """
        预估赎回费用及费率分布（FIFO）。
        当 sell_shares 为 None 或 <=0 时，仅返回持有分布，不返回卖出分布。
        """
        position = db.query(Position).filter_by(id=position_id, family_id=family_id).first()
        if not position or position.asset_type != 'fund':
            raise ValueError('无效持仓或非基金')

        fund_code = position.symbol

        # 获取赎回费率规则
        redeem_rules = (
            db.query(RedeemRule.start_day, RedeemRule.end_day, FeeRatio.rate)
            .select_from(FeeRatio)
            .join(RedeemRule, FeeRatio.redeem_rule_id == RedeemRule.id)
            .filter(FeeRatio.fund_code == fund_code, FeeRatio.fee_type == 'redeem')
            .order_by(RedeemRule.start_day.asc())
            .all()
        )
        if not redeem_rules:
            raise ValueError('该基金暂无赎回费率规则')

        # 获取买入记录（FIFO），限本家庭
        buy_txns = (
            db.query(Transaction)
            .filter(
                Transaction.position_id == position_id,
                Transaction.txn_type == 'buy',
                Transaction.family_id == family_id,
            )
            .order_by(Transaction.confirm_date.asc())
            .all()
        )
        if not buy_txns:
            raise ValueError('该持仓无历史买入记录')

        total_hold = Money.min_unit_to_shares(position.quantity)
        total_bought = sum(Money.min_unit_to_shares(t.quantity) for t in buy_txns)

        # 内部函数：按目标份额计算分布和费用
        def _calc(target: float) -> tuple[float, Dict[str, float]]:
            remaining = target
            fee_total = 0.0
            dist: Dict[str, float] = {f'{float(r.rate):.6f}': 0.0 for r in redeem_rules}
            dist.setdefault('0.000000', 0.0)
            for txn in buy_txns:
                if remaining <= 0:
                    break
                shares = Money.min_unit_to_shares(txn.quantity)
                deduct = min(remaining, shares)
                price = Money.price_units_to_yuan(txn.price)
                if not txn.confirm_date:
                    continue
                days = (sell_date - txn.confirm_date).days
                matched = 0.0
                for rule in redeem_rules:
                    if days >= rule.start_day:
                        if rule.end_day is None or days < rule.end_day:
                            matched = float(rule.rate)
                            break
                fee_total += deduct * price * matched
                dist[f'{matched:.6f}'] += deduct
                remaining -= deduct
            if remaining > 1e-8:
                raise ValueError('持仓份额不足，无法卖出指定数量')
            return fee_total, dist

        # 计算全仓持有分布（基于实际买入份额，避免份额不足错误）
        hold_target = min(total_hold, total_bought)  # 取实际可计算的份额
        _, hold_dist = _calc(hold_target)

        hold_details = []
        for rule in redeem_rules:
            key = f'{float(rule.rate):.6f}'
            hold_shares = hold_dist.get(key, 0.0)
            label = f'{rule.start_day}~{rule.end_day}天(不含)' if rule.end_day else f'≥{rule.start_day}天'
            hold_details.append(
                {
                    'range': label,
                    'shares': round(hold_shares, 4),
                    'rate': float(rule.rate),
                }
            )

        # 卖出分布及费用：仅在指定份额时计算
        sell_details = None
        total_fee = 0.0
        if sell_shares is not None and sell_shares > 0:
            if sell_shares > total_hold:
                raise ValueError(f'持仓份额不足：持有 {total_hold} 份，无法卖出 {sell_shares} 份')
            fee, sell_dist = _calc(sell_shares)
            total_fee = round(fee, 2)
            sell_details = []
            for rule in redeem_rules:
                key = f'{float(rule.rate):.6f}'
                shares = sell_dist.get(key, 0.0)
                label = f'{rule.start_day}~{rule.end_day}天(不含)' if rule.end_day else f'≥{rule.start_day}天'
                sell_details.append(
                    {
                        'range': label,
                        'shares': round(shares, 4),
                        'rate': float(rule.rate),
                    }
                )
        else:
            # 没有指定份额，费用不适用，但可以返回全仓费用作为参考
            total_fee = round(_calc(hold_target)[0], 2)

        return {
            'total_fee': total_fee,
            'holdings': hold_details,
            'sell': sell_details,
        }

    @staticmethod
    def sync_fund_fees(db: Session, fund_code: str) -> bool:
        """
        同步单只基金的费率信息（申购+赎回）。
        调用 xalpha 适配器拉取费率并写入 fee_ratios 表。
        返回 True 表示成功，False 表示失败。
        """
        try:
            xalpha = XalphaAdapter()
            fee_info = xalpha.fetch_fund_fee(fund_code)
            if not fee_info:
                return False

            # 费率币种：按基金份额名称特征推导（无结构化币种字段可依赖）
            fund = db.query(Fund).filter(Fund.fund_code == fund_code).first()
            currency = FundService.infer_fund_currency(
                full_name=fund.full_name if fund else '',
                name=fund.name if fund else '',
            )

            # 申购费率
            purchase_rate = fee_info.get('purchase_rate')
            if purchase_rate is not None:
                # 复用规则查找/创建逻辑（避免重复代码，这里直接内联简化版）
                rule = (
                    db.query(PurchaseRule)
                    .filter(PurchaseRule.start_quota == 0, PurchaseRule.end_quota.is_(None))
                    .first()
                )
                if not rule:
                    rule = PurchaseRule(start_quota=0, end_quota=None)
                    db.add(rule)
                    db.flush()
                existing = (
                    db.query(FeeRatio)
                    .filter(
                        FeeRatio.fund_code == fund_code,
                        FeeRatio.fee_type == 'purchase',
                        FeeRatio.purchase_rule_id == rule.id,
                    )
                    .first()
                )
                if not existing:
                    safe_rate = Decimal(str(purchase_rate)) / Decimal('100')
                    db.add(
                        FeeRatio(
                            fund_code=fund_code,
                            fee_type='purchase',
                            rate=safe_rate,
                            purchase_rule_id=rule.id,
                            currency=currency,
                        )
                    )

            # 赎回费率阶梯
            redemption_schedule = fee_info.get('redemption_schedule', [])
            if isinstance(redemption_schedule, list):
                for item in redemption_schedule:
                    if not isinstance(item, dict):
                        continue
                    start_day = item.get('start_day', 0)
                    end_day = item.get('end_day')
                    rule = (
                        db.query(RedeemRule)
                        .filter(RedeemRule.start_day == start_day, RedeemRule.end_day == end_day)
                        .first()
                    )
                    if not rule:
                        rule = RedeemRule(start_day=start_day, end_day=end_day)
                        db.add(rule)
                        db.flush()
                    existing = (
                        db.query(FeeRatio)
                        .filter(
                            FeeRatio.fund_code == fund_code,
                            FeeRatio.fee_type == 'redeem',
                            FeeRatio.redeem_rule_id == rule.id,
                        )
                        .first()
                    )
                    if not existing:
                        safe_rate = Decimal(str(item.get('rate'))) / Decimal('100')
                        db.add(
                            FeeRatio(
                                fund_code=fund_code,
                                fee_type='redeem',
                                rate=safe_rate,
                                redeem_rule_id=rule.id,
                                currency=currency,
                            )
                        )
            db.commit()
            return True
        except Exception:
            db.rollback()
            logger.exception(f'同步基金 {fund_code} 费率失败')
            return False
