# -*- coding: utf-8 -*-
"""导入协调器·解析/校验/补全 Mixin（#1370 拆分）。

职责：文件解析 → 记录校验 → enrich 补全（账户/名称/净值份额）→ 预览行构建。
与落库（orchestrator_commit.CommitMixin）、持仓对账（orchestrator_holdings.HoldingsMixin）
经 ImportOrchestrator 组合复用；方法体自原 orchestrator.py 逐字搬运，逻辑零改动。
"""

import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from app.core.constants import PositionSource
from app.core.exceptions import ErrorCode, SBException
from app.core.utils import show_time
from app.domains.funds.models import Fund, FundVariety
from app.domains.positions.models import Position
from app.domains.securities.models import Security
from app.domains.transactions.models import Transaction
from app.domains.watchlist.models import WatchlistItem
from app.services.fund_service import FundService
from app.services.importer.mappings import OP_TYPE_LABEL
from app.services.importer.records import (
    SBImportError,
    StandardTransactionRecord,
    compute_record_hash,
)
from app.services.importer.registry import get_parser


class ParsingMixin:
    """解析与预览：parse → validate → enrich → preview。"""

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
        return self._rows_from_records(records, parser, frontend_account, ledger_id)

    def preview_records(
        self,
        records: List[StandardTransactionRecord],
        frontend_account: str = '',
        ledger_id: Optional[int] = None,
        source: str = 'ai_txn',
    ) -> dict:
        """外部候选记录（如 AI 识别）→ 与 parse_and_preview 相同的预览行。

        供 AI 持仓识别导入共用既有管线：enrich（账户/名称/净值份额补全）→
        import_hash（去重哈希，source 默认 ai_txn）→ 行转换 + 数据库去重标记。
        提交仍走 commit_from_preview（/api/importers/confirm），完全复用既有入库链路。
        """
        return self._rows_from_records(records, None, frontend_account, ledger_id, source=source)

    def _rows_from_records(
        self,
        records: List[StandardTransactionRecord],
        parser,
        frontend_account: str,
        ledger_id: Optional[int],
        source: str = PositionSource.AI_TXN.value,
    ) -> dict:
        """记录 → 前端预览行（enrich + 哈希补全 + 行转换 + 去重标记）。

        parse_and_preview（parser 非空，用平台解析器哈希）与 preview_records
        （parser 为空，用 source 哈希；AI 识别默认 ai_txn）共用，保证两条链路去重口径一致。
        """
        # 补全
        self.enrich(records, frontend_account, ledger_id)

        # 生成 import_hash（如果缺失）
        for rec in records:
            if not rec.import_hash:
                rec.import_hash = parser.compute_import_hash(rec) if parser else compute_record_hash(source, rec)

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
                    'ledger_id': rec.ledger_id,  # 回传 confirm 用：缺了它落库不挂账户且去重失效
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

        # 去重检查（#1020 / #1065：去重作用域降为 ledger 级，查询补 ledger_id 维度）
        # 与复合唯一约束 (ledger_id, import_hash) 对齐：DB 端先按 hash 子集缩小，
        # Python 端再按 (ledger_id, import_hash) 精确判定，避免跨账本误判重复。
        hashes = [r['import_hash'] for r in rows if r.get('import_hash')]
        existing_pairs = set()
        if hashes:
            for t in (
                self.db.query(Transaction.ledger_id, Transaction.import_hash)
                .filter(Transaction.family_id == self.family_id, Transaction.import_hash.in_(hashes))
                .all()
            ):
                existing_pairs.add((t.ledger_id, t.import_hash))
        for row in rows:
            if row.get('import_hash') and (row.get('ledger_id'), row['import_hash']) in existing_pairs:
                row['is_duplicate'] = True

        error_count = sum(1 for r in rows if r.get('error'))
        duplicate_count = sum(1 for r in rows if r.get('is_duplicate'))

        return {
            'rows': rows,
            'total': len(rows),
            'error_count': error_count,
            'duplicate_count': duplicate_count,
        }

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
        stock_codes = {r.symbol for r in records if r.asset_type in ('stock', 'etf', 'bond') and r.symbol}

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
                elif r.asset_type in ('stock', 'etf', 'bond'):
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
                            # 份额精度修复（2026-08-17）：0.00 → 0.0000，与项目份额最小单位
                            # min_unit（份×10000）对齐；预估份额（is_calculated=True）精度提升低风险
                            r.shares = (r.amount / r.nav).quantize(Decimal('0.0000'))
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
        # 相似度算法粗糙（仅长度差），改进需先评估对既有导入行为的影响：
        # 本函数无测试覆盖，SequenceMatcher 比率会改变既有匹配结果（用户已习惯的
        # 导入行为），2026-08-17 评估后暂缓，保持现状。
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

    def _build_import_data(self, record: StandardTransactionRecord) -> Dict[str, Any]:
        """将标准记录转换为业务字典，所有值保持原始单位（元/份），不进行分/最小单位转换。"""
        confirm_date = record.confirm_date
        if isinstance(confirm_date, datetime):
            confirm_date = confirm_date.date()

        trade_date = record.trade_date
        if isinstance(trade_date, datetime):
            trade_date = trade_date.date()

        is_dividend = record.business_type in ('dividend_cash', 'dividend_reinvest')
        # 金融口径收口（#1375）：record 字段本身是 Decimal（仅 net_amount 为 float，经 str 桥接），
        # 数据字典全程 Decimal 直传，禁止塌缩到 float 域中转；Money 各入口原生接受 Decimal
        avg_price = record.amount if is_dividend else (record.nav if record.nav else Decimal('0'))
        qty = record.shares if record.shares else Decimal('0')
        fee_val = record.fee
        net_amount_val = Decimal(str(record.net_amount)) if record.net_amount else record.amount

        return {
            'symbol': record.symbol,
            'name': record.name,
            'market': 'CN_A',
            'type': record.asset_type,
            'ledger_id': record.ledger_id,
            'account_name': record.account_name,
            'quantity': qty,  # 原始份额
            'avg_price': avg_price,  # 原始元
            # 净值须单列：is_dividend 时 avg_price 已被改写为分红金额（见上方赋值），
            # 而红利再投资要按净值申购份额，拿不到净值就无法加仓。
            'nav': record.nav if record.nav else Decimal('0'),  # 原始净值元
            'currency': 'CNY',
            'confirm_date': confirm_date,
            'trade_date': trade_date,
            'fee': fee_val,  # 原始元
            'notes': '',
            'import_hash': record.import_hash,
            'allocation': 'liquid' if record.asset_type in ('money_fund', 'reverse_repo') else 'longterm',
            'op_type': record.business_type,
            'link_group_id': record.link_group_id,
            'dividend_amount': record.amount if is_dividend else Decimal('0'),  # 原始元
            'net_amount': net_amount_val,  # 原始元
            'family_id': self.family_id,
        }
