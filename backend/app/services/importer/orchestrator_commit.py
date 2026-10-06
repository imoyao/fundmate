# -*- coding: utf-8 -*-
"""导入协调器·交易落库 Mixin（#1370 拆分）。

职责：预览行 → 记录重建 → commit（SAVEPOINT 单条事务、现金/转账/常规分支）→
元数据回填触发。与解析（orchestrator_parse.ParsingMixin）、持仓对账
（orchestrator_holdings.HoldingsMixin）经 ImportOrchestrator 组合复用；
方法体自原 orchestrator.py 逐字搬运，逻辑零改动。
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from app.core.money import Money
from app.domains.ledgers.models import Ledger
from app.domains.transactions.models import Transaction
from app.services import async_backfill
from app.services.import_records import StandardTransactionRecord
from app.services.importer.mappings import BusinessType
from app.services.position_service import PositionService
from app.services.trading import TransactionService

# #1882 决策 (a)：勾选保留行绕开 (ledger_id, import_hash) 复合唯一约束的确定性后缀。
# 确定性（不带随机数）即自幂等——同一行再次「勾选保留」导入时命中已存在的 suffixed hash，
# 走去重拦截计数，不会叠出第三份记录。
KEEP_HASH_SUFFIX = ':keep'


class CommitMixin:
    """交易落库：commit_from_preview → commit → trigger_metadata_update。"""

    def commit_from_preview(self, raw_rows: list) -> dict:
        """
        接收前端提交的原始行，过滤并转换为记录，然后提交。
        返回与原有 commit 一致的统计字典；#1010 起额外携带 cash_transfers_created
        （银证转账在关联现金账户侧生成的反向记录数，独立计数，不混入 imported/skipped 口径）；
        #1882 起携带 kept_duplicates / kept_duplicates_blocked（勾选保留行的入库 /
        去重拦截计数，回执据此如实展示，杜绝「前端放后端拦」的静默丢弃）。
        """
        cash_transfers_created = 0

        # 行分流：错误行一律跳过；疑似重复行仅在用户勾选保留（keep_duplicate）时放行
        # （#1882 决策 (a)，见 issue 评论留痕）；转账行走 #1010 闭环分支；其余为投资交易行
        invest_rows = []
        transfer_rows = []
        for r in raw_rows:
            keep = bool(r.get('keep_duplicate')) and bool(r.get('is_duplicate'))
            if r.get('error') or (r.get('is_duplicate') and not keep):
                continue
            if r.get('is_cash_transfer'):
                transfer_rows.append(r)
            else:
                invest_rows.append(r)
        filter_skipped = len(raw_rows) - len(invest_rows) - len(transfer_rows)

        # ---- 银证转账闭环（#1010）：已关联现金账户时生成反向现金侧记录 ----
        for row in transfer_rows:
            if self._commit_cash_transfer_row(row):
                cash_transfers_created += 1
            else:
                # 未关联 / 绑定无效 / 方向未知 / 重复：维持旧行为计入 skipped
                filter_skipped += 1

        if not invest_rows:
            # 纯转账批次也要落库：commit() 的收尾提交只在有投资行时才会走到
            self._safe_commit()
            return {
                'imported': 0,
                'skipped': filter_skipped,
                'orphan_count': 0,
                'errors': [],
                'cash_transfers_created': cash_transfers_created,
                # #1882：无投资行批次同样回执这两个键，前端契约恒定
                'kept_duplicates': 0,
                'kept_duplicates_blocked': 0,
            }

        # 转换为 StandardTransactionRecord
        records = list()
        for row in invest_rows:
            records.append(
                StandardTransactionRecord(
                    confirm_date=self._parse_row_date(row),
                    asset_type=row.get('type', 'fund'),
                    symbol=row['symbol'],
                    name=row.get('name', ''),
                    business_type=row.get('op_type', 'buy'),
                    # B5 修复：row 值可能为 None（前端缺字段），str(None) 会让 Decimal 抛异常，
                    # 统一 or 0 兜底后再转 Decimal
                    amount=Decimal(str(row.get('amount') or 0)),
                    account_name=row.get('account_name', ''),
                    shares=Decimal(str(row.get('quantity') or 0)) if row.get('quantity') else None,
                    nav=Decimal(str(row.get('price') or 0)) if row.get('price') else None,
                    fee=Decimal(str(row.get('fee') or 0)),
                    transaction_id=row.get('contract_id', ''),
                    import_hash=row.get('import_hash'),
                    source=row.get('source', ''),
                    ledger_id=row.get('ledger_id'),
                    # B2 修复：透传净发生金额（同花顺专用），现金/扣税/兑付分支按净额入账；
                    # 前端 row 为 JSON 浮点，经 str 桥接收口为 Decimal（#1375 阶段二）
                    net_amount=Decimal(str(row.get('net_amount') or 0)),
                    # #1882：疑似重复且勾选保留的行标记真插入（commit 内换 :keep 后缀）
                    keep_duplicate=bool(row.get('keep_duplicate')) and bool(row.get('is_duplicate')),
                )
            )

        result = self.commit(records)
        result['skipped'] += filter_skipped
        result['cash_transfers_created'] = cash_transfers_created
        return result

    @staticmethod
    def _parse_row_date(row: dict) -> date:
        """预览行的 trade_date 字符串 → date，解析失败兜底今天（原 commit_from_preview 内联逻辑收敛）。"""
        try:
            return datetime.strptime(row.get('trade_date', ''), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return date.today()

    def _safe_commit(self) -> None:
        """会话收尾提交：失败回滚并抛出（与 commit() 尾部语义一致，供多分支复用）。"""
        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f'入库提交失败: {e}')
            raise

    def _resolve_linked_cash_ledger(self, target_ledger: Optional[Ledger]) -> Optional[Ledger]:
        """解析目标账本绑定的有效现金账户：须存在且 ledger_type='bank'（同 family），否则 None。

        #1067 与 #1010 共用口径：未绑定或绑定目标非 bank 均视为「未有效绑定」。
        """
        if not target_ledger or not target_ledger.linked_cash_ledger_id:
            return None
        cash_ledger = (
            self.db.query(Ledger).filter_by(id=target_ledger.linked_cash_ledger_id, family_id=self.family_id).first()
        )
        if cash_ledger and cash_ledger.ledger_type != 'bank':
            return None  # 绑定目标非 bank，视为未有效绑定
        return cash_ledger

    def _commit_cash_transfer_row(self, row: dict) -> bool:
        """#1010 银证转账落现金账户：在关联现金账本生成一条「反向」现金流水。

        方向反转语义（用户决策 2026-08-24）：交割单转账行描述的是证券侧资金变动，
        银行侧记相反方向两本账才净额守恒——证券侧 deposit（银行转证券）⇄ 银行侧 withdraw，
        证券侧 withdraw（证券转银行）⇄ 银行侧 deposit。
        未关联/绑定无效/方向未知/重复导入时返回 False，由调用方计入 skipped（维持旧行为）。
        """
        ledger_id = row.get('ledger_id')
        target_ledger = (
            self.db.query(Ledger).filter_by(id=ledger_id, family_id=self.family_id).first() if ledger_id else None
        )
        cash_ledger = self._resolve_linked_cash_ledger(target_ledger)
        if cash_ledger is None:
            return False

        # 方向反转：证券侧视角 → 银行侧视角
        inversion = {'deposit': 'withdraw', 'withdraw': 'deposit'}
        txn_type = inversion.get(str(row.get('op_type') or '').lower())
        if txn_type is None:
            logger.warning(f'银证转账行方向未知，跳过现金侧落账: op_type={row.get("op_type")}')
            return False

        import_hash = row.get('import_hash')
        if import_hash:
            # 与投资交易同口径去重：(现金账本, import_hash)，同一份交割单重导不翻倍
            existing = (
                self.db.query(Transaction)
                .filter_by(import_hash=import_hash, ledger_id=cash_ledger.id, family_id=self.family_id)
                .first()
            )
            if existing:
                return False

        confirm_date = self._parse_row_date(row)
        # 净额优先（THS 口径），**仅当字段缺失（None）时**退化用发生金额；
        # 不能用 `or`——净额恰为 0 会被误判为缺失并取发生额（#1491 评审）。
        # 金额一律整数分（#1375：Decimal 收口）
        raw_net_amount = row.get('net_amount')
        amount = raw_net_amount if raw_net_amount is not None else (row.get('amount') or 0)
        amount_yuan = abs(Decimal(str(amount)))
        TransactionService.create(
            db=self.db,
            symbol=row.get('symbol', ''),
            txn_type=txn_type,
            trade_date=confirm_date,
            confirm_date=confirm_date,
            asset_type='cash',
            quantity=0,
            price=0,
            fee=0,
            amount=Money.yuan_to_cents(amount_yuan),
            status='success',
            entry_status=None,
            position_name=row.get('name', ''),
            ledger_id=cash_ledger.id,
            account_name=cash_ledger.name,
            notes=row.get('notes') or row.get('name') or '',
            import_hash=import_hash,
            link_group_id=row.get('link_group_id'),
            family_id=self.family_id,
        )
        return True

    def commit(self, records: List[StandardTransactionRecord]) -> Dict[str, Any]:
        imported = 0
        skipped = 0
        orphan_count = 0
        commit_errors = []
        # #1882 回执口径：勾选保留行的入库 / 规则拦截独立计数，不混入 imported/skipped
        kept_duplicates = 0
        kept_duplicates_blocked = 0

        for record in records:
            try:
                # B3 修复（2026-08-17）：单条记录包在 SAVEPOINT 内——普通异常回滚该条
                # 已 flush 的部分写入后继续（与 E6 对账侧口径一致）；SQLAlchemyError 仍保持
                # 整体失败语义（数据库级错误，回滚全部并 raise，见下方 except 分支）。
                with self.db.begin_nested():
                    if record.keep_duplicate and record.import_hash:
                        # #1882 决策 (a) 真插入：原件仍在 → 换确定性后缀绕开复合唯一约束；
                        # 原件已被删 → 它已非重复，保持原 hash 走正常去重（保持再导入语义）。
                        original_exists = (
                            self.db.query(Transaction)
                            .filter_by(
                                import_hash=record.import_hash,
                                ledger_id=record.ledger_id,
                                family_id=self.family_id,
                            )
                            .first()
                        )
                        if original_exists:
                            record.import_hash = record.import_hash + KEEP_HASH_SUFFIX
                    if record.import_hash:
                        existing = (
                            self.db.query(Transaction)
                            .filter_by(
                                import_hash=record.import_hash,
                                ledger_id=record.ledger_id,
                                family_id=self.family_id,
                            )
                            .first()
                        )
                        if existing:
                            if record.keep_duplicate:
                                # 保留行命中去重 = 此前已勾选保留过（后缀自幂等，不叠第三份）
                                kept_duplicates_blocked += 1
                            else:
                                skipped += 1
                            continue

                    # ---- 现金管理类产品 ----
                    if record.asset_type in ('cash', 'money_fund'):
                        data = self._build_import_data(record)
                        entry_status = None
                        if not data.get('ledger_id'):
                            logger.warning('现金管理产品缺少 ledger_id，跳过')
                            skipped += 1  # B4 修复：缺 ledger_id 跳过时计入 skipped（原漏计数）
                            continue
                        ledger_id = data['ledger_id']
                        target_ledger = self.db.query(Ledger).filter_by(id=ledger_id, family_id=self.family_id).first()
                        if not target_ledger:
                            # 目标账本完全不存在时才置 pending_cash（record.ledger_id 已校验，几乎不发生）
                            entry_status = 'pending_cash'
                            data['account_name'] = data.get('account_name', '')
                        else:
                            # #1067 现金归属口径（2026-08-29 修正，见 issue #1137）：
                            # 卖出/赎回/分红/货基等回款一律「留在投资账本本身」，不再改写 ledger_id 到
                            # 绑定的现金账户。银证转账是用户**显式**操作，系统自动搬账等价于凭空生成
                            # 一笔银证转账，会扭曲真实资金流。
                            # 仅 #1010 的显式转账行（is_cash_transfer）才在银行侧生成反向流水。
                            # 跨账本重导场景由 #1065 的 (ledger_id, import_hash) 复合约束自然去重。
                            data['account_name'] = target_ledger.name
                        # net_amount 转换为分
                        amount_cents = Money.yuan_to_cents(abs(data['net_amount']))
                        TransactionService.create(
                            db=self.db,
                            txn_type=data['op_type'],
                            trade_date=data.get('trade_date'),
                            confirm_date=data.get('confirm_date'),
                            asset_type=data.get('type'),
                            quantity=0,
                            price=0,
                            fee=0,
                            amount=amount_cents,
                            status='success',
                            position_name=data.get('name', ''),
                            ledger_id=data['ledger_id'],
                            account_name=data.get('account_name', ''),
                            notes=data.get('notes', ''),
                            import_hash=data.get('import_hash'),
                            entry_status=entry_status,
                            family_id=self.family_id,
                        )
                        imported += 1
                        if record.keep_duplicate:  # #1882：勾选保留行入库单独计数
                            kept_duplicates += 1
                        orphan_count += 1
                        continue

                    # ---- 常规投资品种 ----
                    data = self._build_import_data(record)
                    bt = record.business_type

                    # 基本校验
                    if bt in (
                        BusinessType.BUY.code,
                        BusinessType.DEPOSIT.code,
                        BusinessType.SELL.code,
                        BusinessType.WITHDRAW.code,
                    ):
                        if data.get('quantity', 0) <= 0:
                            commit_errors.append(
                                {'symbol': record.symbol, 'name': record.name, 'error': '数量必须大于 0'}
                            )
                            continue
                        if bt in (BusinessType.BUY.code, BusinessType.DEPOSIT.code) and data.get('avg_price', 0) <= 0:
                            commit_errors.append(
                                {'symbol': record.symbol, 'name': record.name, 'error': '价格必须大于 0'}
                            )
                            continue

                    # 特殊操作：扣税
                    if bt == BusinessType.TAX.code:
                        # net_amount 是元，转为分，扣税为负值
                        tax_cents = -Money.yuan_to_cents(abs(data['net_amount']))
                        TransactionService.create(
                            db=self.db,
                            position_id=None,
                            txn_type='dividend_tax',
                            trade_date=data.get('trade_date'),
                            confirm_date=data.get('confirm_date'),
                            asset_type=data.get('type'),
                            quantity=0,
                            price=0,
                            fee=0,
                            amount=tax_cents,
                            status='success',
                            position_name=data.get('name', data['symbol']),
                            account_name=data.get('account_name', ''),
                            notes=data.get('notes') or '股息红利扣税',
                            import_hash=data.get('import_hash'),
                            entry_status='orphan',
                            link_group_id=data.get('link_group_id'),
                            family_id=self.family_id,
                        )
                        orphan_count += 1
                        imported += 1
                        if record.keep_duplicate:  # #1882：勾选保留行入库单独计数
                            kept_duplicates += 1
                        continue

                    # 特殊操作：债券兑付
                    if bt == BusinessType.BOND_REDEEM.code:
                        # 数量和金额都需要转换
                        qty_units = Money.shares_to_min_unit(data['quantity'])
                        price_units = Money.yuan_to_price_units(data.get('avg_price', 0))
                        amount_cents = Money.yuan_to_cents(data['net_amount'])
                        TransactionService.create(
                            db=self.db,
                            position_id=None,
                            txn_type='bond_redeem',
                            trade_date=data.get('trade_date'),
                            confirm_date=data.get('confirm_date'),
                            asset_type=data.get('type'),
                            quantity=qty_units,
                            price=price_units,
                            fee=0,
                            amount=amount_cents,
                            status='success',
                            position_name=data.get('name', data['symbol']),
                            account_name=data.get('account_name', ''),
                            notes=data.get('notes') or '债券到期兑付',
                            import_hash=data.get('import_hash'),
                            entry_status='orphan',
                            link_group_id=data.get('link_group_id'),
                            family_id=self.family_id,
                        )
                        orphan_count += 1
                        imported += 1
                        if record.keep_duplicate:  # #1882：勾选保留行入库单独计数
                            kept_duplicates += 1
                        continue

                    # 常规操作 (BUY/DEPOSIT, SELL/WITHDRAW, DIVIDEND)
                    if bt in (BusinessType.BUY.code, BusinessType.DEPOSIT.code):
                        result = PositionService.process_buy_or_deposit(self.db, data)
                    elif bt in (BusinessType.SELL.code, BusinessType.WITHDRAW.code):
                        result = PositionService.process_orphan_sell_or_withdraw(self.db, data)
                    elif bt == BusinessType.DIVIDEND_CASH.code:
                        result = PositionService.process_orphan_dividend(self.db, data)
                    elif bt == BusinessType.DIVIDEND_REINVEST.code:
                        result = PositionService.process_orphan_dividend_reinvest(self.db, data)
                    elif bt == BusinessType.SPLIT.code:
                        result = PositionService.process_orphan_split(self.db, data)
                    else:
                        skipped += 1
                        continue

                    if result is None:
                        orphan_count += 1
                    imported += 1
                    if record.keep_duplicate:  # #1882：勾选保留行入库单独计数
                        kept_duplicates += 1

            except SQLAlchemyError as e:
                # 数据库级错误：保持整体失败语义（savepoint 已随 with 退出回滚，此处再全量回滚兜底）
                self.db.rollback()
                logger.exception(f'数据库操作失败: symbol={record.symbol}, error={e}')
                raise
            except Exception as e:
                # 普通异常：savepoint 已回滚该条部分写入，仅记错误继续（B3 修复，2026-08-17）
                logger.exception(f'入库单条记录失败: symbol={record.symbol}, business_type={record.business_type}')
                commit_errors.append({'symbol': record.symbol, 'name': record.name, 'error': str(e)})

        self._safe_commit()

        logger.info(
            f'入库完成: 导入={imported}, 跳过={skipped}, 孤立={orphan_count}, '
            f'错误={len(commit_errors)}, 保留入库={kept_duplicates}, 保留拦截={kept_duplicates_blocked}'
        )
        return {
            'imported': imported,
            'skipped': skipped,
            'orphan_count': orphan_count,
            'errors': commit_errors,
            'kept_duplicates': kept_duplicates,
            'kept_duplicates_blocked': kept_duplicates_blocked,
        }

    # ── 元数据更新 ──

    def trigger_metadata_update(self, records: List[StandardTransactionRecord]) -> None:
        """导入成功后，异步触发元数据补充"""

        fund_codes = set()
        stock_symbols = set()

        for record in records:
            if record.asset_type == 'fund':
                fund_codes.add(record.symbol)
            elif record.asset_type in ('stock', 'etf', 'bond'):
                stock_symbols.add(record.symbol)

        for code in fund_codes:
            try:
                async_backfill.trigger_backfill('fund', code)
            except Exception as e:
                logger.warning(f'元数据更新触发失败: fund {code}, error={e}')

        for symbol in stock_symbols:
            try:
                async_backfill.trigger_backfill('stock', symbol)
            except Exception as e:
                logger.warning(f'元数据更新触发失败: stock {symbol}, error={e}')

        if fund_codes or stock_symbols:
            logger.info(f'已触发元数据更新: 基金={len(fund_codes)}只, 股票={len(stock_symbols)}只')
