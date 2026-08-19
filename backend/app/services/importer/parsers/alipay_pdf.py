# -*- coding: utf-8 -*-
"""
支付宝基金交易确认单 PDF 解析器。

用户从支付宝申请“基金交易明细”PDF，直接上传即可解析。
PDF 为原生文本、表格规整，使用 pdfplumber 提取。
"""

import os
import re
import tempfile
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

import pdfplumber

from app.core.constants import PositionSource
from app.services.importer.base import BaseImportParser
from app.services.importer.mappings import ALIPAY_PDF_OP_MAP, VALID_OP_TYPES
from app.services.importer.records import SBImportError, StandardTransactionRecord


class AlipayPDFParser(BaseImportParser):
    """支付宝基金交易确认单 PDF 解析器"""

    source = PositionSource.BROKER_ALIPAY_PDF.value

    def parse(self, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        records = []
        errors = []

        # 写入临时文件
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            raw_rows = self._extract_rows(tmp_path)
            if not raw_rows:
                errors.append(SBImportError(line_number=0, field_name=None, message='PDF 中未提取到交易数据'))
                return records, errors

            for i, row in enumerate(raw_rows):
                try:
                    record = self._row_to_record(row)
                    if record:
                        records.append(record)
                except Exception as e:
                    errors.append(SBImportError(line_number=i + 2, field_name=None, message=str(e)))

        finally:
            os.unlink(tmp_path)

        return records, errors

    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        valid = []
        errors = []
        for idx, rec in enumerate(records):
            line_num = idx + 2
            if not rec.symbol:
                errors.append(SBImportError(line_num, 'symbol', '基金代码不能为空'))
            elif not rec.amount or rec.amount <= 0:
                errors.append(SBImportError(line_num, 'amount', '确认金额必须大于0'))
            elif rec.confirm_date and rec.confirm_date > date.today():
                errors.append(SBImportError(line_num, 'confirm_date', '确认日期不能晚于今天'))
            elif rec.business_type not in VALID_OP_TYPES:
                errors.append(SBImportError(line_num, 'business_type', f'不支持的业务类型: {rec.business_type}'))
            else:
                valid.append(rec)
        return valid, errors

    @staticmethod
    def _is_valid_date_prefix(s: str) -> bool:
        """判断字符串前8位是否为有效日期（YYYYMMDD）"""
        if len(s) < 8:
            return False
        try:
            y, m, d = int(s[0:4]), int(s[4:6]), int(s[6:8])
            return 2020 <= y <= 2099 and 1 <= m <= 12 and 1 <= d <= 31
        except (ValueError, IndexError):
            return False

    # ── 内部方法 ──

    def _extract_rows(self, pdf_path: str) -> List[List[str]]:
        """提取并标准化所有数据行（12列），合并跨页断裂行"""
        all_standard_rows = []
        header_processed = False

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                table = page.extract_table(
                    {
                        'vertical_strategy': 'lines',
                        'horizontal_strategy': 'lines',
                        'intersection_tolerance': 10,
                    }
                )
                if not table:
                    continue

                cleaned = []
                for row in table:
                    if any(cell and cell.strip() for cell in row):
                        cleaned.append([self._clean_text(cell) for cell in row])
                if not cleaned:
                    continue

                has_header = any('订单号' in str(cell) or '交易时间' in str(cell) for row in cleaned for cell in row)

                if not header_processed and has_header:
                    data_rows = cleaned[1:]  # 跳过表头
                    for row in data_rows:
                        standard_row = [
                            row[0],  # 订单号
                            row[3],  # 交易时间
                            row[6],  # 交易类型
                            row[9],  # 基金名称
                            '',  # 组合基金名称（本PDF无）
                            row[15],  # 基金代码
                            row[18],  # 申请金额
                            row[21],  # 申请份额
                            row[24],  # 确认金额
                            row[27],  # 确认份额
                            row[30],  # 手续费
                            row[33],  # 确认日期
                        ]
                        all_standard_rows.append(standard_row[:12])
                    header_processed = True
                elif header_processed and not has_header:
                    for row in cleaned:
                        all_standard_rows.append(row[:12])

        if not all_standard_rows:
            return []

        # 合并跨页断裂：如果一行的订单号不以8位日期开头，则拼接到上一行
        merged_rows = []
        for row in all_standard_rows:
            first_cell = row[0] if row else ''
            is_new_record = self._is_valid_date_prefix(first_cell)
            if is_new_record:
                merged_rows.append(row[:])
            else:
                if merged_rows:
                    prev = merged_rows[-1]
                    for i in range(12):
                        cur_val = row[i] if i < len(row) else ''
                        if cur_val and cur_val != '0':
                            prev[i] = prev[i] + cur_val
                else:
                    merged_rows.append(row[:])

        return merged_rows

    def _row_to_record(self, row: List[str]) -> Optional[StandardTransactionRecord]:
        """将标准化12列行转换为 StandardTransactionRecord"""
        if len(row) < 12:
            return None

        order_id = row[0]
        trade_time = row[1]
        business_type_raw = row[2]
        fund_name = row[3]
        fund_code = row[5]
        confirm_amount = row[8]
        confirm_shares = row[9]
        fee = row[10]
        confirm_date_raw = row[11]

        if not order_id or not fund_code or not confirm_amount:
            return None

        trade_date = self._parse_date(trade_time[:10])
        confirm_date = self._parse_date(confirm_date_raw[:10])

        if not confirm_date:
            # 确认日期无效须报告错误，而非静默丢弃整行（tech-debt L23）
            raise ValueError(f'确认日期无效: {confirm_date_raw}')

        # 业务类型映射
        business_type = ALIPAY_PDF_OP_MAP.get(business_type_raw, 'buy')

        # 数值解析
        amount = self._parse_decimal(confirm_amount)
        shares = self._parse_decimal(confirm_shares) if confirm_shares and confirm_shares != '/' else None
        fee_val = self._parse_decimal(fee)

        # 净值计算
        nav = None
        if amount and amount > 0 and shares and shares > 0:
            nav = (amount / shares).quantize(Decimal('0.0001'))

        return StandardTransactionRecord(
            confirm_date=confirm_date,
            trade_date=trade_date,
            asset_type='fund',
            symbol=fund_code,
            name=fund_name,
            business_type=business_type,
            amount=amount,
            account_name='',
            shares=shares,
            nav=nav,
            fee=fee_val,
            transaction_id=order_id,
            source=self.source,
        )

    @staticmethod
    def _clean_text(text: str) -> str:
        if not text:
            return ''
        return re.sub(r'\s+', '', str(text))

    @staticmethod
    def _parse_date(date_str: str) -> Optional[date]:
        if not date_str:
            return None
        date_str = date_str.replace('/', '-')[:10]
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        if not value or value in ('/', '—', ''):
            return Decimal('0')
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal('0')
