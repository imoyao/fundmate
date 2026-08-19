# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/8 19:44
# File : alipay_fund.py
# app/services/importer/parsers/alipay_fund.py
"""
支付宝交易记录解析器。

支付宝导出账单为制表符分隔的文本文件，包含：
- 文件头（4行）：账号、时间范围
- 数据行：交易记录
- 文件尾（统计信息和"----"分隔行）

解析器需要：
1. 跳过文件头和文件尾
2. 处理引号和制表符
3. 过滤非成功交易
4. 从“商品名称”中解析交易类型和基金名称
5. 将余额宝相关交易标记为现金出入
6. 基金交易由后续的 enrich 匹配代码
"""

import csv
import io
import re
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from loguru import logger

from app.core.constants import PositionSource
from app.services.importer.base import BaseImportParser
from app.services.importer.mappings import ALIPAY_OP_MAP
from app.services.importer.records import SBImportError, StandardTransactionRecord
from app.services.importer.utils import clean_amount, parse_date

# 预编译正则（性能优化）
HYPHEN_PATTERN = re.compile(r'[-—]')
YUEBAO_PATTERN = re.compile(r'余额宝')
FUND_TRADE_PATTERN = re.compile(r'蚂蚁财富[-—](.+?)[-—](.+)')
YUEBAO_INCOME_PATTERN = re.compile(r'余额宝[-—](\d{4}\.\d{2}\.\d{2})?[-—]?收益发放')


class AlipayFundParser(BaseImportParser):
    source = PositionSource.BROKER_ALIPAY.value

    def parse(self, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        records = []
        errors = []

        # 1. 编码检测（只检测前1KB）
        encoding = self._detect_encoding(file_bytes)
        if not encoding:
            errors.append(SBImportError(line_number=0, field_name=None, message='无法识别文件编码'))
            return records, errors

        # 2. 解码文件
        try:
            raw_content = file_bytes.decode(encoding)
        except UnicodeDecodeError:
            errors.append(SBImportError(line_number=0, field_name=None, message='文件解码失败'))
            return records, errors
        if raw_content.startswith('\ufeff'):
            raw_content = raw_content[1:]

        lines = raw_content.splitlines()

        # 3. 寻找表头行
        header_idx = -1
        header_parts = []
        for i, line in enumerate(lines):
            # 直接检查是否包含关键列名
            if '交易号' in line and '商家订单号' in line and '交易创建时间' in line:
                header_idx = i
                # 用 csv.reader 正确解析表头（处理引号）
                reader_header = csv.reader(io.StringIO(line), delimiter=',')
                header_parts = next(reader_header, [])
                header_parts = [col.strip().strip('"') for col in header_parts if col.strip()]
                break

        if header_idx == -1 or not header_parts:
            errors.append(SBImportError(line_number=0, field_name=None, message='未找到有效的数据表头'))
            return records, errors

        # 4. 提取数据行（跳过表头前和尾部统计行）
        data_lines = []
        for line in lines[header_idx + 1 :]:
            stripped = line.strip()
            if (
                stripped.startswith('---')
                or stripped.startswith('共')
                or stripped.startswith('已收入')
                or stripped.startswith('导出时间')
            ):
                break
            if stripped:
                data_lines.append(line)

        if not data_lines:
            errors.append(SBImportError(line_number=0, field_name=None, message='无有效数据行'))
            return records, errors

        # 5. 一次性用 csv.reader 解析所有数据行（关键：分隔符为逗号，quotechar 默认双引号）
        reader = csv.reader(io.StringIO('\n'.join(data_lines)), delimiter=',')
        for line_num, parts in enumerate(reader, start=header_idx + 2):
            # 补齐或截断
            if len(parts) < len(header_parts):
                parts.extend([''] * (len(header_parts) - len(parts)))
            elif len(parts) > len(header_parts):
                parts = parts[: len(header_parts)]

            raw_dict = dict(zip(header_parts, parts))
            for k, v in raw_dict.items():
                if isinstance(v, str):
                    raw_dict[k] = v.strip().strip('"')

            if raw_dict.get('交易状态') != '交易成功':
                continue

            try:
                record = self._parse_row(raw_dict, line_num)
                if record:
                    records.append(record)
            except ValueError as e:
                errors.append(SBImportError(line_num, None, str(e)))
            except Exception as e:
                logger.warning(f'行 {line_num} 解析异常: {e}')
                errors.append(SBImportError(line_num, None, f'行解析失败: {str(e)}'))

        logger.info(f'解析完成: 成功 {len(records)} 条, 错误 {len(errors)} 条')
        return records, errors

    def _detect_encoding(self, file_bytes: bytes) -> Optional[str]:
        """只读取前 1024 字节检测编码"""
        sample = file_bytes[:1024]
        for enc in ['gb18030', 'gbk', 'utf-8-sig', 'utf-8']:
            try:
                decoded = sample.decode(enc)
                if '交易号' in decoded and '商家订单号' in decoded:
                    return enc
            except UnicodeDecodeError:
                continue
        return None

    def _parse_row(self, row: dict, line_num: int) -> Optional[StandardTransactionRecord]:
        product_name = row.get('商品名称', '').strip()
        amount_str = row.get('金额（元）', '0').strip()
        amount = clean_amount(amount_str) or Decimal('0')
        fee = clean_amount(row.get('服务费（元）', '0').strip()) or Decimal('0')
        transaction_id = row.get('交易号', '').strip() or None

        create_time = row.get('交易创建时间', '').strip()
        confirm_date = parse_date(create_time) if create_time else date.today()
        if not confirm_date:
            raise ValueError(f'无效的交易时间: {create_time}')

        # 统一解析产品信息
        op_type, asset_type, symbol, name = self._parse_product_info(product_name)
        if not op_type or not asset_type:
            raise ValueError(f'无法识别的交易类型: {product_name}')

        return StandardTransactionRecord(
            confirm_date=confirm_date,
            asset_type=asset_type,
            symbol=symbol,
            name=name,
            business_type=op_type,
            amount=amount,
            account_name='',
            fee=fee,
            transaction_id=transaction_id,
            source=self.source,
            raw_op_type=product_name,
        )

    def _parse_product_info(self, product_name: str) -> Tuple[Optional[str], Optional[str], str, str]:
        """返回 (操作类型, 资产类型, 代码, 名称)"""
        # 蚂蚁财富基金交易
        fund_match = FUND_TRADE_PATTERN.match(product_name)
        if fund_match:
            fund_name = fund_match.group(1).strip()
            action = fund_match.group(2).strip()
            op_type = self._map_op_type(action)
            return op_type, 'fund', '', fund_name

        # 余额宝收益
        if YUEBAO_INCOME_PATTERN.match(product_name):
            return 'deposit', 'cash', '__CASH__', '余额宝'

        # 其他余额宝交易
        if YUEBAO_PATTERN.search(product_name):
            if '转出到银行卡' in product_name or '提现' in product_name:
                return 'withdraw', 'cash', '__CASH__', '余额宝'
            if '转入' in product_name:
                return 'deposit', 'cash', '__CASH__', '余额宝'
            return 'deposit', 'cash', '__CASH__', '余额宝'

        return None, None, '', ''

    def _map_op_type(self, action: str) -> Optional[str]:
        """映射操作类型"""
        if action in ALIPAY_OP_MAP:
            return ALIPAY_OP_MAP[action]
        for key, code in ALIPAY_OP_MAP.items():
            if key in action:
                return code
        return None

    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        valid, errors = [], []
        for i, rec in enumerate(records):
            line_num = i + 2
            if rec.amount == 0:
                errors.append(SBImportError(line_num, 'amount', '金额为0'))
            elif rec.confirm_date > date.today():
                errors.append(SBImportError(line_num, 'confirm_date', '交易日期不能晚于今天'))
            else:
                valid.append(rec)
        return valid, errors
