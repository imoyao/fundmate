# app/services/importer/orchestrator.py
"""
导入协调器。

统一管理 parse → validate → enrich → commit → trigger_metadata_update 流程。
"""

import re
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import ErrorCode, SBException
from app.core.money import Money
from app.core.utils import show_time
from app.domains.funds.models import Fund, FundVariety
from app.domains.ledgers.models import Ledger
from app.domains.positions.models import Position
from app.domains.securities.models import Security
from app.domains.transactions.models import Transaction
from app.domains.watchlist.models import WatchlistItem
from app.services.async_backfill import trigger_backfill
from app.services.fund_service import FundService
from app.services.importer.mappings import OP_TYPE_LABEL, BusinessType
from app.services.importer.records import SBImportError, StandardTransactionRecord
from app.services.importer.registry import get_parser
from app.services.position_service import PositionService
from app.services.transaction_service import TransactionService


class ImportOrchestrator:
    """
    导入流程协调器。

    用法:
        orch = ImportOrchestrator(db)
        records, errors = orch.parse(source, file_bytes)
        valid, validation_errors = orch.validate(records)
        orch.enrich(valid, frontend_account)
        result = orch.commit(valid)
        orch.trigger_metadata_update(valid)
    """

    def __init__(self, db: Session, family_id: int = 1):
        self.db = db
        self.family_id = family_id
        self.batch_id = ''

    def validate_file_type(self, records: List[StandardTransactionRecord], expected_source: str) -> None:
        """
        根据解析后的证券代码特征校验文件类型是否匹配预期模板。
        如果不匹配，直接抛出 SBException。
        """
        if not records:
            return

        symbols = [r.symbol for r in records if r.symbol]
        total = len(symbols)
        if total == 0:
            return

        # 基金代码特征：纯6位数字
        fund_count = sum(1 for s in symbols if re.match(r'^\d{6}$', s))
        # 股票代码特征：SH/SZ/BJ 开头
        stock_count = sum(1 for s in symbols if re.match(r'^(SH|SZ|BJ)\d{6}$', s))

        if expected_source in ('standard_fund',):
            if stock_count > total * 0.5:
                raise SBException(
                    code=ErrorCode.FILE_PARSE_ERROR.code,
                    message='文件内容与所选账户不匹配：多数记录为股票代码，请选择股票账户后重新上传。',
                )
        elif expected_source in ('standard_stock', 'ths_stock'):
            if fund_count > total * 0.5:
                raise SBException(
                    code=ErrorCode.FILE_PARSE_ERROR.code,
                    message='文件内容与所选账户不匹配：多数记录为基金代码，请选择基金账户后重新上传。',
                )

    def parse_and_preview(
        self, file_bytes: bytes, template_key: str, frontend_account: str = '', ledger_id: int | None = None
    ) -> dict:
        """解析文件并返回预览数据，包含去重信息"""
        parser = get_parser(template_key)
        records, errors = self._parse_internal(template_key, file_bytes)
        if errors and not records:
            raise SBException(ErrorCode.FILE_PARSE_ERROR.code, errors[0].message)

        # 文件类型校验
        self.validate_file_type(records, template_key)
        # 补全
        self.enrich(records, frontend_account, ledger_id)

        # 生成 import_hash（如果缺失）
        for rec in records:
            if not rec.import_hash:
                rec.import_hash = parser.compute_import_hash(rec)

        # 转换为前端格式
        rows = []
        for rec in records:
            rows.append(
                {
                    'symbol': rec.symbol,
                    'name': rec.name,
                    'type': rec.asset_type,
                    'display_type': rec.display_type,
                    'op_type': rec.business_type.lower() if not rec.error else '',
                    'op_type_label': OP_TYPE_LABEL.get(rec.business_type, '') if not rec.error else '',
                    'quantity': float(rec.shares) if rec.shares and not rec.error else 0,
                    'price': float(rec.nav) if rec.nav and not rec.error else 0,
                    'amount': float(rec.amount),
                    'fee': float(rec.fee),
                    'trade_date': rec.confirm_date.isoformat() if rec.confirm_date else '',
                    'account_name': rec.account_name,
                    'contract_id': rec.transaction_id or '',
                    'is_cash_transfer': rec.asset_type == 'cash',
                    'error': rec.error or None,
                    'import_hash': rec.import_hash,
                    'is_duplicate': False,
                    'allocation': 'liquid' if rec.asset_type in ('money_fund', 'reverse_repo', 'cash') else None,
                    'link_group_id': rec.link_group_id,
                    'trade_amount': rec.trade_amount,
                    'net_amount': rec.net_amount,
                    'notes': rec.raw_op_type or '',
                    'source': rec.source,  # 前端回传用
                    'is_calculated': rec.is_calculated,
                }
            )

        # 去重检查
        hashes = [r['import_hash'] for r in rows if r.get('import_hash')]
        existing_hashes = set()
        if hashes:
            existing_hashes = set(
                h[0]
                for h in self.db.query(Transaction.import_hash)
                .filter(Transaction.import_hash.in_(hashes), Transaction.family_id == self.family_id)
                .all()
            )
        for row in rows:
            if row.get('import_hash') and row['import_hash'] in existing_hashes:
                row['is_duplicate'] = True

        error_count = sum(1 for r in rows if r.get('error'))
        duplicate_count = sum(1 for r in rows if r.get('is_duplicate'))

        return {
            'rows': rows,
            'total': len(rows),
            'error_count': error_count,
            'duplicate_count': duplicate_count,
        }

    def commit_from_preview(self, raw_rows: list) -> dict:
        """
        接收前端提交的原始行，过滤并转换为记录，然后提交。
        返回与原有 commit 一致的统计字典。
        """
        # 过滤有效行（前端已过滤，但后端再防一次）
        valid_rows = [
            r for r in raw_rows if not r.get('is_duplicate') and not r.get('error') and not r.get('is_cash_transfer')
        ]
        filter_skipped = len(raw_rows) - len(valid_rows)

        if not valid_rows:
            return {'imported': 0, 'skipped': len(raw_rows), 'orphan_count': 0, 'errors': []}

        # 转换为 StandardTransactionRecord
        records = list()
        for row in valid_rows:
            trade_date_str = row.get('trade_date', '')
            try:
                confirm_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                confirm_date = date.today()

            records.append(
                StandardTransactionRecord(
                    confirm_date=confirm_date,
                    asset_type=row.get('type', 'fund'),
                    symbol=row['symbol'],
                    name=row.get('name', ''),
                    business_type=row.get('op_type', 'buy'),
                    amount=Decimal(str(row.get('amount', 0))),
                    account_name=row.get('account_name', ''),
                    shares=Decimal(str(row.get('quantity', 0))) if row.get('quantity') else None,
                    nav=Decimal(str(row.get('price', 0))) if row.get('price') else None,
                    fee=Decimal(str(row.get('fee', 0))),
                    transaction_id=row.get('contract_id', ''),
                    import_hash=row.get('import_hash'),
                    source=row.get('source', ''),
                    ledger_id=row.get('ledger_id'),
                )
            )

        result = self.commit(records)
        result['skipped'] += filter_skipped
        return result

    # ── 解析 ──

    def _parse_internal(
        self, source: str, file_bytes: bytes
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        parser = get_parser(source)
        if parser is None:
            raise SBException(ErrorCode.UNSUPPORTED_FILE_FORMAT.code, f'不支持的导入来源: {source}')
        records, errors = parser.parse(file_bytes)
        for record in records:
            record.source = source
            if not record.import_hash:
                record.import_hash = parser.compute_import_hash(record)
        return records, errors

    def parse(self, source: str, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """调用对应解析器解析文件，生成哈希和批次ID"""

        records, errors = self._parse_internal(source, file_bytes)
        self.batch_id = str(uuid.uuid4())
        for record in records:
            record.batch_id = self.batch_id
        logger.info(f'解析完成: source={source}, 记录={len(records)}, 错误={len(errors)}')
        return records, errors

    # ── 校验 ──

    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """校验记录列表，过滤不合法数据"""
        all_valid = []
        all_errors = []

        for idx, record in enumerate(records):
            line_num = idx + 2  # 表头占第1行
            field_errors = self._validate_single_record(record, line_num)
            if field_errors:
                all_errors.extend(field_errors)
            else:
                all_valid.append(record)

        logger.info(f'校验完成: 通过={len(all_valid)}, 错误={len(all_errors)}')
        return all_valid, all_errors

    def _validate_single_record(self, record: StandardTransactionRecord, line_num: int) -> List[SBImportError]:
        errors = []
        if not record.symbol:
            errors.append(SBImportError(line_num, 'symbol', '证券代码不能为空'))
        if record.amount <= 0:
            errors.append(SBImportError(line_num, 'amount', '确认金额必须大于0'))
        if record.confirm_date and record.confirm_date > datetime.now().date():
            errors.append(SBImportError(line_num, 'confirm_date', '确认日期不能晚于今天'))
        return errors

    def enrich(self, records: List[StandardTransactionRecord], frontend_account: str = '', ledger_id=None) -> None:
        start = time.time()
        self._fill_account_and_match_codes(records, frontend_account, ledger_id)
        logger.info(f'enrich 补全账户+名称匹配耗时: {time.time() - start:.3f}s')

        start2 = time.time()
        fund_map, stock_map = self._batch_query_asset_info(records)
        logger.info(f'enrich 批量查询资产信息耗时: {time.time() - start2:.3f}s')

        start3 = time.time()
        self._fill_names_and_types(records, fund_map, stock_map)
        logger.info(f'enrich 填充名称和类型耗时: {time.time() - start3:.3f}s')

        start4 = time.time()
        self._fill_missing_nav_and_shares(records)
        logger.info(f'enrich 填充净值份额耗时: {time.time() - start4:.3f}s')
        logger.info(f'enrich 总耗时: {time.time() - start:.3f}s')

    def _fill_account_and_match_codes(self, records, frontend_account, ledger_id):
        match_cache = {}
        for r in records:
            r.ledger_id = ledger_id
            if not r.account_name and frontend_account:
                r.account_name = frontend_account
            if r.asset_type == 'fund' and not r.symbol and r.name:
                if r.name in match_cache:
                    r.symbol = match_cache[r.name]
                else:
                    matched = self._match_fund_by_name(r.name)
                    if matched:
                        r.symbol = matched
                        match_cache[r.name] = matched

    def _batch_query_asset_info(self, records):
        """批量查询基金和股票的名称、类型"""
        fund_codes = {r.symbol for r in records if r.asset_type == 'fund' and r.symbol}
        stock_codes = {r.symbol for r in records if r.asset_type == 'stock' and r.symbol}

        fund_name_map = {}
        fund_type_map = {}
        if fund_codes:
            funds = (
                self.db.query(Fund.fund_code, Fund.name, FundVariety.name.label('variety_name'))
                .outerjoin(FundVariety, Fund.fund_variety_id == FundVariety.id)
                .filter(Fund.fund_code.in_(fund_codes))
                .all()
            )
            for fund_code, fund_name, variety_name in funds:
                fund_name_map[fund_code] = fund_name or fund_code
                fund_type_map[fund_code] = variety_name or ''

        stock_map = {}
        if stock_codes:
            stock_map = {
                s.symbol: s.name for s in self.db.query(Security).filter(Security.symbol.in_(stock_codes)).all()
            }

        return (fund_name_map, fund_type_map), stock_map

    def _fill_names_and_types(self, records, fund_map, stock_map):
        """填充名称和显示类型，识别货币基金"""
        fund_name_map, fund_type_map = fund_map
        for r in records:
            if not r.name:
                if r.asset_type == 'fund':
                    r.name = fund_name_map.get(r.symbol, r.symbol)
                elif r.asset_type == 'stock':
                    r.name = stock_map.get(r.symbol, r.symbol)

            if r.asset_type == 'fund' and not r.display_type:
                r.display_type = fund_type_map.get(r.symbol, '')
                if '货币' in r.display_type:
                    r.asset_type = 'money_fund'

            # 临时方案：名称关键词兜底（后续依赖元数据同步，届时移除）
            if r.asset_type == 'fund' and r.name:
                name_lower = r.name.lower()
                if any(kw in name_lower for kw in ['货币', '现金', '宝', '增利', '天天益']):
                    r.asset_type = 'money_fund'
                    r.display_type = '货币型'

    def _fill_missing_nav_and_shares(self, records):
        needed = [
            r for r in records if r.asset_type == 'fund' and r.symbol and r.confirm_date and (not r.nav or not r.shares)
        ]
        if not needed:
            return

        # 按日期分组
        date_groups = {}
        for r in needed:
            dt = r.confirm_date
            if dt not in date_groups:
                date_groups[dt] = set()
            date_groups[dt].add(r.symbol)

        for dt, symbols in date_groups.items():
            symbol_list = list(symbols)
            nav_map = FundService.get_fund_nav_map(self.db, symbol_list, dt)
            for r in needed:
                if r.confirm_date == dt and r.symbol in nav_map:
                    nav = nav_map[r.symbol]
                    if nav and nav > 0:
                        r.nav = nav.quantize(Decimal('0.0001'))
                        if r.amount and r.amount > 0:
                            r.shares = (r.amount / r.nav).quantize(Decimal('0.00'))
                        r.is_calculated = True

    @show_time
    def _match_fund_by_name(self, fund_name: str) -> Optional[str]:
        clean_input = self._clean_fund_name(fund_name)
        search_pattern = f'%{clean_input}%'

        # 1. 持仓优先
        pos_fund = (
            self.db.query(Fund.fund_code)
            .join(Position, Position.symbol == Fund.fund_code)
            .filter(Fund.name.ilike(search_pattern))
            .first()
        )
        if pos_fund:
            return pos_fund[0]

        # 2. 自选
        watch_fund = (
            self.db.query(Fund.fund_code)
            .join(WatchlistItem, WatchlistItem.symbol == Fund.fund_code)
            .filter(Fund.name.ilike(search_pattern))
            .first()
        )
        if watch_fund:
            return watch_fund[0]

        # 3. 全库搜索，限制 10 条
        candidates = self.db.query(Fund.fund_code, Fund.name).filter(Fund.name.ilike(search_pattern)).limit(10).all()
        if not candidates:
            return None

        # 相似度选择
        scored = []
        for code, name in candidates:
            clean_name = self._clean_fund_name(name)
            similarity = abs(len(clean_input) - len(clean_name))
            scored.append((similarity, code))
        scored.sort(key=lambda x: x[0])
        if len(scored) > 1 and scored[0][0] == scored[1][0]:
            return None  # 多个最佳匹配，放弃自动匹配
        return scored[0][1]

    def _clean_fund_name(self, name: str) -> str:
        for word in ['LOF', 'ETF', '联接', '发起', '指数']:
            name = name.replace(word, '')
        name = name.replace('（', '(').replace('）', ')')
        return re.sub(r'\s+', '', name)

    # ── 入库 ──
    # app/services/importer/orchestrator.py

    def _build_import_data(self, record: StandardTransactionRecord) -> Dict[str, Any]:
        """将标准记录转换为业务字典，所有值保持原始单位（元/份），不进行分/最小单位转换。"""
        confirm_date = record.confirm_date
        if isinstance(confirm_date, datetime):
            confirm_date = confirm_date.date()

        trade_date = record.trade_date
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()

        is_dividend = record.business_type in ('dividend_cash', 'dividend_reinvest')
        # 使用 Decimal 或安全转换避免 float 精度问题，但 Money 方法内部会通过 Decimal(str(x)) 处理，此处直接传 Decimal 亦可
        avg_price = float(record.amount) if is_dividend else (float(record.nav) if record.nav else 0.0)
        qty = float(record.shares) if record.shares else 0.0
        fee_val = float(record.fee)
        net_amount_val = float(record.net_amount) if record.net_amount else float(record.amount)

        return {
            'symbol': record.symbol,
            'name': record.name,
            'market': 'CN_A',
            'type': record.asset_type,
            'ledger_id': record.ledger_id,
            'account_name': record.account_name,
            'quantity': qty,  # 原始份额
            'avg_price': avg_price,  # 原始元
            'currency': 'CNY',
            'confirm_date': confirm_date,
            'trade_date': trade_date,
            'fee': fee_val,  # 原始元
            'notes': '',
            'import_hash': record.import_hash,
            'allocation': 'liquid' if record.asset_type in ('money_fund', 'reverse_repo') else 'longterm',
            'op_type': record.business_type,
            'link_group_id': record.link_group_id,
            'dividend_amount': float(record.amount) if is_dividend else 0.0,  # 原始元
            'net_amount': net_amount_val,  # 原始元
            'family_id': self.family_id,
        }

    def commit(self, records: List[StandardTransactionRecord]) -> Dict[str, Any]:
        imported = 0
        skipped = 0
        orphan_count = 0
        commit_errors = []

        for record in records:
            try:
                if record.import_hash:
                    existing = (
                        self.db.query(Transaction)
                        .filter_by(import_hash=record.import_hash, family_id=self.family_id)
                        .first()
                    )
                    if existing:
                        skipped += 1
                        continue

                # ---- 现金管理类产品 ----
                if record.asset_type in ('cash', 'money_fund'):
                    data = self._build_import_data(record)
                    entry_status = None
                    if not data.get('ledger_id'):
                        logger.warning('现金管理产品缺少 ledger_id，跳过')
                        continue
                    bank_ledger = self.db.query(Ledger).filter_by(ledger_type='bank', family_id=self.family_id).first()
                    if bank_ledger:
                        data['account_name'] = bank_ledger.name
                        data['ledger_id'] = bank_ledger.id
                    else:
                        entry_status = 'pending_cash'
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
                        commit_errors.append({'symbol': record.symbol, 'name': record.name, 'error': '数量必须大于 0'})
                        continue
                    if bt in (BusinessType.BUY.code, BusinessType.DEPOSIT.code) and data.get('avg_price', 0) <= 0:
                        commit_errors.append({'symbol': record.symbol, 'name': record.name, 'error': '价格必须大于 0'})
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
                    continue

                # 特殊操作：债券兑付
                if bt == BusinessType.BOND_REDEEM.code:
                    # 数量和金额都需要转换
                    qty_units = Money.shares_to_min_unit(data['quantity'])
                    price_cents = Money.yuan_to_cents(data.get('avg_price', 0))
                    amount_cents = Money.yuan_to_cents(data['net_amount'])
                    TransactionService.create(
                        db=self.db,
                        position_id=None,
                        txn_type='bond_redeem',
                        trade_date=data.get('trade_date'),
                        confirm_date=data.get('confirm_date'),
                        asset_type=data.get('type'),
                        quantity=qty_units,
                        price=price_cents,
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
                    continue

                # 常规操作 (BUY/DEPOSIT, SELL/WITHDRAW, DIVIDEND)
                if bt in (BusinessType.BUY.code, BusinessType.DEPOSIT.code):
                    result = PositionService.process_buy_or_deposit(self.db, data, skip_lot_check=True)
                elif bt in (BusinessType.SELL.code, BusinessType.WITHDRAW.code):
                    result = PositionService.process_orphan_sell_or_withdraw(self.db, data)
                elif bt in (BusinessType.DIVIDEND_CASH.code, BusinessType.DIVIDEND_REINVEST.code):
                    result = PositionService.process_orphan_dividend(self.db, data)
                elif bt == BusinessType.SPLIT.code:
                    # 转股：数量需转换，金额为 0
                    qty_units = Money.shares_to_min_unit(data['quantity'])
                    TransactionService.create(
                        db=self.db,
                        position_id=None,
                        txn_type='split',
                        trade_date=data.get('trade_date'),
                        confirm_date=data.get('confirm_date'),
                        asset_type=data.get('type'),
                        quantity=qty_units,
                        price=data.get('avg_price', 0),  # avg_price 可能为 0，转股无价格，保留原值
                        fee=0,
                        amount=0,
                        status='success',
                        position_name=data.get('name', data['symbol']),
                        account_name=data.get('account_name', ''),
                        notes='转股入账（需手动关联持仓）',
                        import_hash=data.get('import_hash'),
                        entry_status='orphan',
                        family_id=self.family_id,
                    )
                    orphan_count += 1
                    imported += 1
                    continue
                else:
                    skipped += 1
                    continue

                if result is None:
                    orphan_count += 1
                imported += 1

            except SQLAlchemyError as e:
                self.db.rollback()
                logger.exception(f'数据库操作失败: symbol={record.symbol}, error={e}')
                raise
            except Exception as e:
                logger.exception(f'入库单条记录失败: symbol={record.symbol}, business_type={record.business_type}')
                commit_errors.append({'symbol': record.symbol, 'name': record.name, 'error': str(e)})

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f'入库提交失败: {e}')
            raise

        logger.info(f'入库完成: 导入={imported}, 跳过={skipped}, 孤立={orphan_count}, 错误={len(commit_errors)}')
        return {'imported': imported, 'skipped': skipped, 'orphan_count': orphan_count, 'errors': commit_errors}

    # ── 元数据更新 ──

    def trigger_metadata_update(self, records: List[StandardTransactionRecord]) -> None:
        """导入成功后，异步触发元数据补充"""

        fund_codes = set()
        stock_symbols = set()

        for record in records:
            if record.asset_type == 'fund':
                fund_codes.add(record.symbol)
            elif record.asset_type == 'stock':
                stock_symbols.add(record.symbol)

        for code in fund_codes:
            try:
                trigger_backfill('fund', code)
            except Exception as e:
                logger.warning(f'元数据更新触发失败: fund {code}, error={e}')

        for symbol in stock_symbols:
            try:
                trigger_backfill('stock', symbol)
            except Exception as e:
                logger.warning(f'元数据更新触发失败: stock {symbol}, error={e}')

        if fund_codes or stock_symbols:
            logger.info(f'已触发元数据更新: 基金={len(fund_codes)}只, 股票={len(stock_symbols)}只')
