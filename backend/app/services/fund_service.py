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
from app.domains.funds.models import DailyWorth, FeeRatio, Fund, PurchaseRule, RedeemRule
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

    @staticmethod
    def search_funds(db: Session, keyword: str) -> List[Dict[str, Any]]:
        """模糊搜索基金（代码/名称/拼音），返回列表含默认申购费率"""
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
                }
            )
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
                price = Money.cents_to_yuan(txn.price)
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
