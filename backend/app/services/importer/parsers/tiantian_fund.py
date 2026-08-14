# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/7 15:02
# File : tiantian_fund.py
# -*- coding: utf-8 -*-
"""
天天基金交易记录解析器。

用户从天天基金网页复制交易明细并粘贴到 CSV 中，
选择“天天基金”格式上传。解析器自动跳过复制混入的多余表头、
过滤失败记录、映射天天基金的中文业务类型。
"""

import csv
import io
from typing import List, Optional, Tuple

from app.services.importer.mappings import TIANTIAN_OP_MAP
from app.services.importer.parsers.standard import FundStandardParser
from app.services.importer.records import SBImportError, StandardTransactionRecord
from app.services.importer.utils import normalize_fund_code


class TiantianFundParser(FundStandardParser):
    """天天基金交易记录解析器"""

    source = 'tiantian_fund'

    @property
    def _column_map(self) -> dict:
        return {
            '确认日期': 'confirm_date',
            '基金代码': 'symbol',
            '基金简称': 'name',
            '业务类型': 'business_type',
            '确认状态': 'status',
            '确认份额': 'shares',
            '确认金额': 'amount',
            '手续费': 'fee',
            '确认净值': 'nav',
            '关联银行卡': 'bank_info',
        }

    @property
    def _required_columns(self) -> list:
        return ['确认日期', '基金代码', '业务类型', '确认金额']

    def _map_business_type(self, raw: str) -> str:
        return TIANTIAN_OP_MAP.get(raw, raw)

    def _normalize_code(self, raw: str) -> Optional[str]:
        return normalize_fund_code(raw)

    # parse 方法保持不变（已在上次提供）

    def parse(self, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        records = []
        errors = []

        raw_content = self._decode_bytes(file_bytes)
        if raw_content is None:
            errors.append(SBImportError(line_number=0, field_name=None, message='无法识别文件编码'))
            return records, errors

        if raw_content.startswith('\ufeff'):
            raw_content = raw_content[1:]

        reader = csv.DictReader(io.StringIO(raw_content))
        if reader.fieldnames is None:
            errors.append(SBImportError(line_number=0, field_name=None, message='无法读取 CSV 表头'))
            return records, errors

        # 清洗列名
        cleaned_fieldnames = [name.strip().lstrip('\ufeff') for name in reader.fieldnames]
        reader.fieldnames = cleaned_fieldnames
        header_set = set(cleaned_fieldnames)

        missing = [col for col in self._required_columns if col not in header_set]
        if missing:
            errors.append(
                SBImportError(
                    line_number=0,
                    field_name=None,
                    message=f'缺少必填列: {", ".join(missing)}。请确认复制了完整的表格数据。',
                )
            )
            return records, errors

        for line_num, raw_row in enumerate(reader, start=2):
            # 清洗行数据
            cleaned_row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw_row.items()}

            # 跳过多次复制混入的表头行
            if cleaned_row.get('确认日期', '') == '确认日期':
                continue

            # 过滤非成功记录
            status = cleaned_row.get('确认状态', '')
            if status and status != '成功':
                continue

            # 构造父类 _parse_row 需要的标准字段（去除额外字段，保持兼容）
            standard_row = {k: v for k, v in cleaned_row.items() if k in self._column_map}
            # 但父类 _parse_row 接收的是映射后的英文字段，我们需要先映射
            mapped_row = {}
            for cn_key, std_key in self._column_map.items():
                val = cleaned_row.get(cn_key, '').strip()
                mapped_row[std_key] = val

            try:
                # 调用父类的行解析逻辑（使用标准映射后的字典）
                record = self._parse_row(mapped_row, line_num)
                if record:
                    # 补充银行名解析到 account_name（如果为空）
                    bank_info = cleaned_row.get('关联银行卡', '')
                    if bank_info and not record.account_name:
                        record.account_name = self._parse_bank_name(bank_info)
                    records.append(record)
            except Exception as e:
                errors.append(SBImportError(line_num, None, str(e)))

        return records, errors

    @staticmethod
    def _parse_bank_name(bank_info: str) -> str:
        """从“银行名 | 尾号”中提取银行名"""
        if not bank_info:
            return ''
        parts = bank_info.split('|', 1)
        return parts[0].strip()
