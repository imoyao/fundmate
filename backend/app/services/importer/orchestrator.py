# app/services/importer/orchestrator.py
"""
导入协调器。

统一管理 parse → validate → enrich → commit → trigger_metadata_update 流程。
"""

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from app.core.exceptions import ErrorCode, SBException
from app.domains.funds.models import Fund
from app.domains.securities.models import Security
from app.domains.transactions.models import Transaction
from app.services.async_backfill import trigger_backfill
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

    def __init__(self, db: Session):
        self.db = db
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

    def parse_and_preview(self, file_bytes: bytes, template_key: str, frontend_account: str = '') -> dict:
        """解析文件并返回预览数据，包含去重信息"""
        parser = get_parser(template_key)
        if parser is None:
            raise SBException(ErrorCode.UNSUPPORTED_FILE_FORMAT.code, f'不支持的导入模板: {template_key}')

        records, errors = parser.parse(file_bytes)
        if errors and not records:
            raise SBException(ErrorCode.FILE_PARSE_ERROR.code, errors[0].message)

        # 文件类型校验
        self.validate_file_type(records, template_key)
        # 补全
        self.enrich(records, frontend_account)

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
                    'source': rec.source,  # 新增，前端回传用
                }
            )

        # 去重检查
        hashes = [r['import_hash'] for r in rows if r.get('import_hash')]
        existing_hashes = set()
        if hashes:
            existing_hashes = set(
                h[0] for h in self.db.query(Transaction.import_hash).filter(Transaction.import_hash.in_(hashes)).all()
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
                )
            )

        return self.commit(records)

    # ── 解析 ──

    def parse(self, source: str, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """调用对应解析器解析文件，生成哈希和批次ID"""

        parser = get_parser(source)
        if parser is None:
            raise SBException(
                code=ErrorCode.UNSUPPORTED_FILE_FORMAT.code,
                message=f'不支持的导入来源: {source}',
                status_code=400,
            )

        records, errors = parser.parse(file_bytes)

        # 为每条记录生成 import_hash 和 batch_id
        self.batch_id = str(uuid.uuid4())
        for record in records:
            record.import_hash = parser.compute_import_hash(record)
            record.batch_id = self.batch_id
            record.source = source

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

    # ── 补全 ──

    def enrich(self, records: List[StandardTransactionRecord], frontend_account: str = '') -> None:
        fund_codes = set()
        stock_codes = set()

        # 第一遍：收集所有需要查询的代码，同时补全账户名称
        for r in records:
            if not r.account_name and frontend_account:
                r.account_name = frontend_account
            if not r.name:  # 名称缺失才查询
                if r.asset_type == 'fund':
                    fund_codes.add(r.symbol)
                elif r.asset_type == 'stock':
                    stock_codes.add(r.symbol)
            # 基金 display_type 缺失也需要查询
            if r.asset_type == 'fund' and not r.display_type:
                fund_codes.add(r.symbol)

        # 批量查询基金信息
        fund_name_map = {}
        fund_type_map = {}
        if fund_codes:
            funds = self.db.query(Fund).filter(Fund.fund_code.in_(fund_codes)).all()
            fund_name_map = {f.fund_code: f.name for f in funds}
            for f in funds:
                variety_name = f.variety.name if f.variety else ''
                fund_type_map[f.fund_code] = variety_name

        # 批量查询股票信息
        stock_map = {}
        if stock_codes:
            stock_map = {
                s.symbol: s.name for s in self.db.query(Security).filter(Security.symbol.in_(stock_codes)).all()
            }

        # 第二遍：填充名称和类型
        for r in records:
            if not r.name:
                if r.asset_type == 'fund':
                    r.name = fund_name_map.get(r.symbol, r.symbol)
                else:
                    r.name = stock_map.get(r.symbol, r.symbol)
            if r.asset_type == 'fund' and not r.display_type:
                r.display_type = fund_type_map.get(r.symbol, '')

    # ── 入库 ──

    def commit(self, records: List[StandardTransactionRecord]) -> Dict[str, Any]:
        imported = 0
        skipped = 0
        orphan_count = 0
        commit_errors = []

        for record in records:
            try:
                if record.import_hash:
                    existing = self.db.query(Transaction).filter_by(import_hash=record.import_hash).first()
                    if existing:
                        skipped += 1
                        continue

                if record.asset_type == 'cash':
                    skipped += 1
                    continue

                data = self._build_import_data(record)
                bt = record.business_type

                # 特殊操作：扣税
                if bt == BusinessType.TAX.code:
                    TransactionService.create(
                        db=self.db,
                        position_id=None,
                        txn_type='dividend_tax',
                        trade_date=data['purchase_date'],
                        quantity=0,
                        price=0,
                        fee=0,
                        amount=-abs(data['net_amount']),  # 扣税金额为负
                        status='success',
                        position_name=data.get('name', data['symbol']),
                        account_name=data.get('account_name', ''),
                        notes=data.get('notes') or '股息红利扣税',
                        import_hash=data.get('import_hash'),
                        entry_status='orphan',
                        link_group_id=data.get('link_group_id'),
                    )
                    orphan_count += 1
                    imported += 1
                    continue

                # 特殊操作：债券兑付
                if bt == BusinessType.BOND_REDEEM.code:
                    TransactionService.create(
                        db=self.db,
                        position_id=None,
                        txn_type='bond_redeem',
                        trade_date=data['purchase_date'],
                        quantity=data['quantity'],
                        price=data.get('avg_price', 0),
                        fee=0,
                        amount=data['net_amount'],
                        status='success',
                        position_name=data.get('name', data['symbol']),
                        account_name=data.get('account_name', ''),
                        notes=data.get('notes') or '债券到期兑付',
                        import_hash=data.get('import_hash'),
                        entry_status='orphan',
                        link_group_id=data.get('link_group_id'),
                    )
                    orphan_count += 1
                    imported += 1
                    continue

                # 常规操作
                if bt in (BusinessType.BUY.code, BusinessType.DEPOSIT.code):
                    result = PositionService.process_buy_or_deposit(self.db, data)
                elif bt in (BusinessType.SELL.code, BusinessType.WITHDRAW.code):
                    result = PositionService.process_orphan_sell_or_withdraw(self.db, data)
                elif bt in (BusinessType.DIVIDEND_CASH.code, BusinessType.DIVIDEND_REINVEST.code):
                    result = PositionService.process_orphan_dividend(self.db, data)
                elif bt == BusinessType.SPLIT.code:
                    TransactionService.create(
                        db=self.db,
                        position_id=None,
                        txn_type='split',
                        trade_date=data['purchase_date'],
                        quantity=data['quantity'],
                        price=data.get('avg_price', 0),
                        fee=0,
                        amount=0,
                        status='success',
                        position_name=data.get('name', data['symbol']),
                        account_name=data.get('account_name', ''),
                        notes='转股入账（需手动关联持仓）',
                        import_hash=data.get('import_hash'),
                        entry_status='orphan',
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

    def _build_import_data(self, record: StandardTransactionRecord) -> Dict[str, Any]:
        """将 StandardTransactionRecord 转换为 PositionService 需要的字典格式"""
        trade_date = record.confirm_date
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()

        # 分红类型：用 amount 作为交易金额（同时作为 dividend_amount）
        is_dividend = record.business_type in ('dividend_cash', 'dividend_reinvest')
        avg_price = float(record.amount) if is_dividend else (float(record.nav) if record.nav else 0)

        return {
            'symbol': record.symbol,
            'name': record.name,
            'market': 'CN_A',
            'type': record.asset_type,
            'account_name': record.account_name,
            'quantity': float(record.shares) if record.shares else 0,
            'avg_price': avg_price,
            'currency': 'CNY',
            'purchase_date': trade_date,
            'fee': float(record.fee),
            'notes': '',
            'import_hash': record.import_hash,
            'allocation': 'liquid' if record.asset_type in ('money_fund', 'reverse_repo') else 'longterm',
            'op_type': BusinessType.get_service_code(record.business_type),
            'link_group_id': record.link_group_id,
            'dividend_amount': float(record.amount) if is_dividend else 0,
            'net_amount': float(record.net_amount) if record.net_amount else float(record.amount),
        }

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
            except Exception:
                pass

        for symbol in stock_symbols:
            try:
                trigger_backfill('stock', symbol)
            except Exception:
                pass

        if fund_codes or stock_symbols:
            logger.info(f'已触发元数据更新: 基金={len(fund_codes)}只, 股票={len(stock_symbols)}只')
