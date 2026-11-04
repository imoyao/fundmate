# app/services/importer/parsers/standard.py
import csv
import io
from abc import abstractmethod
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from loguru import logger

from app.core.constants import PositionSource
from app.core.venues import EXCHANGE, OTC
from app.services.import_records import SBImportError, StandardTransactionRecord
from app.services.importer.base import BaseImportParser
from app.services.importer.mappings import (
    FUND_OP_MAP,
    STOCK_OP_MAP,
    VALID_OP_TYPES,
)
from app.services.importer.utils import (
    clean_amount,
    clean_nav,
    clean_shares,
    normalize_fund_code,
    normalize_stock_code,
    parse_date,
)


class StandardTemplateParser(BaseImportParser):
    """标准模板解析器基类"""

    source = PositionSource.BROKER_STD_TEMPLATE.value

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
        cleaned_fieldnames = []
        for name in reader.fieldnames:
            name = name.strip()
            if name.startswith('\ufeff'):
                name = name[1:]
            cleaned_fieldnames.append(name)
        reader.fieldnames = cleaned_fieldnames
        header_set = set(cleaned_fieldnames)

        missing = [col for col in self._required_columns if col not in header_set]
        if missing:
            errors.append(
                SBImportError(
                    line_number=0,
                    field_name=None,
                    message=f'缺少必填列: {", ".join(missing)}',
                )
            )
            return records, errors

        for line_num, raw_row in enumerate(reader, start=2):
            row = {}
            for cn_key, std_key in self._column_map.items():
                val = raw_row.get(cn_key, '').strip()
                row[std_key] = val

            try:
                record = self._parse_row(row, line_num)
                if record:
                    records.append(record)
            except Exception as e:
                records.append(
                    StandardTransactionRecord(
                        confirm_date=date.today(),
                        asset_type=self._asset_type,
                        symbol=row.get('symbol', ''),
                        name=row.get('name', ''),
                        business_type='',
                        amount=Decimal('0'),
                        account_name=row.get('account_name', ''),
                        error=str(e),
                    )
                )

        return records, errors

    # ── 抽象属性 ──
    @property
    @abstractmethod
    def _column_map(self) -> dict: ...

    @property
    @abstractmethod
    def _required_columns(self) -> list: ...

    @abstractmethod
    def _normalize_code(self, raw: str) -> Optional[str]: ...

    @abstractmethod
    def _map_business_type(self, raw: str) -> str: ...

    @property
    @abstractmethod
    def _asset_type(self) -> str: ...

    # ── 行解析 ──
    def _parse_row(self, row: dict, line_num: int) -> Optional[StandardTransactionRecord]:
        if not any(v for v in row.values() if v):
            return None

        symbol_raw = row.get('symbol', '')
        if not symbol_raw:
            raise ValueError('证券代码不能为空')
        symbol = self._normalize_code(symbol_raw)
        if not symbol:
            code_type = '基金代码' if self._asset_type == 'fund' else '证券代码'
            raise ValueError(f'无法识别{code_type}: {symbol_raw}')

        confirm_date = parse_date(row.get('confirm_date', ''))
        if not confirm_date:
            raise ValueError(f'确认日期格式错误: {row.get("confirm_date", "")}')

        trade_date = parse_date(row.get('trade_date', '')) if row.get('trade_date') else None

        raw_type = row.get('business_type', '').strip()
        op_type = self._map_business_type(raw_type)
        if op_type not in VALID_OP_TYPES:
            raise ValueError(f'不支持的业务类型: {raw_type}')

        amount_raw = row.get('amount', '')
        amount = clean_amount(amount_raw) if amount_raw else Decimal('0')
        # 金额：只有现金分红和普通交易必填，红利再投资选填
        if amount is None and op_type not in ('dividend_cash', 'dividend_reinvest', 'deposit', 'withdraw'):
            raise ValueError(f'金额格式错误: {row.get("amount", "")}')

        shares = clean_shares(row.get('shares', ''), '0.00' if self._asset_type == 'fund' else '0')

        # 份额：只有红利再投资必填
        if shares is None and op_type == 'dividend_reinvest':
            raise ValueError('红利再投资必须提供份额')
        nav = clean_nav(row.get('nav', ''))
        # 净值：只有红利再投资必填
        if nav is None and op_type == 'dividend_reinvest':
            raise ValueError('红利再投资必须提供净值')

        fee = clean_amount(row.get('fee', '')) or Decimal('0')
        # #2137 费用拆分（可选列）：模板带明细列才拆分，四列齐全且其和=fee 才认，
        # 否则整体回落 None=未拆分（与模型不变量同口径：缺的类别显式给 0）。
        fee_breakdown = self._parse_fee_breakdown(row)
        name = row.get('name', '')
        account_name = row.get('account_name', '')
        transaction_id = row.get('transaction_id', '') or None

        return StandardTransactionRecord(
            confirm_date=confirm_date,
            trade_date=trade_date,
            asset_type=self._asset_type,
            symbol=symbol,
            name=name,
            business_type=op_type,
            amount=amount,
            account_name=account_name,
            shares=shares,
            nav=nav,
            fee=fee,
            fee_commission=fee_breakdown[0],
            fee_stamp_duty=fee_breakdown[1],
            fee_transfer_fee=fee_breakdown[2],
            fee_other=fee_breakdown[3],
            transaction_id=transaction_id,
            source=self.source,
        )

    # #2137：标准模板费用拆分的可选列（std_key → 中文列名见各子类 _column_map）
    _FEE_BREAKDOWN_KEYS = ('fee_commission', 'fee_stamp_duty', 'fee_transfer_fee', 'fee_other')

    @classmethod
    def _parse_fee_breakdown(cls, row: dict) -> tuple:
        """从映射后的行字典读四列费用明细（#2137），单位元。

        只有**四列全部有值**且**其和等于聚合手续费**才返回拆分（四个 Decimal）；
        缺列 / 无法解析 / 与手续费对不上 → 全 None（未拆分，以聚合 fee 为权威）。
        模板没带明细列时 ``_column_map`` 里没有这些键，``row.get`` 得空串，
        自然落到未拆分。对账回落是为防「只填明细没填手续费」的脏行撞模型的
        拆分不变量（Transaction before_insert 会 fail closed）。
        """
        values = []
        for key in cls._FEE_BREAKDOWN_KEYS:
            raw_val = (row.get(key) or '').strip()
            if not raw_val:
                return (None, None, None, None)
            parsed = clean_amount(raw_val)
            if parsed is None:
                return (None, None, None, None)
            values.append(parsed)
        fee_val = clean_amount(row.get('fee', '')) or Decimal('0')
        if sum(values) != fee_val:
            logger.warning(f'费用拆分四列之和({sum(values)})与手续费({fee_val})不一致，按未拆分入库（#2137）')
            return (None, None, None, None)
        return tuple(values)

    # ── 校验 ──
    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        valid_records = []
        errors = []
        for i, r in enumerate(records):
            line_num = i + 2
            row_errors = []
            if not r.symbol:
                row_errors.append(SBImportError(line_num, 'symbol', '证券代码不能为空'))
            if r.amount <= 0:
                row_errors.append(SBImportError(line_num, 'amount', '确认金额必须大于0'))
            if r.confirm_date > date.today():
                row_errors.append(SBImportError(line_num, 'confirm_date', '确认日期不能晚于今天'))
            if r.business_type not in VALID_OP_TYPES:
                row_errors.append(SBImportError(line_num, 'business_type', f'不支持的业务类型: {r.business_type}'))
            if row_errors:
                errors.extend(row_errors)
            else:
                valid_records.append(r)
        return valid_records, errors


class FundStandardParser(StandardTemplateParser):
    source = PositionSource.BROKER_STD_FUND.value
    # 基金模板 = 场外申赎：代码为证监会分配的 6 位裸码（#1662）
    venue = OTC

    @property
    def _column_map(self) -> dict:
        return {
            '确认日期': 'confirm_date',
            '交易日期': 'trade_date',
            '基金代码': 'symbol',
            '基金名称': 'name',
            '业务类型': 'business_type',
            '份额': 'shares',
            '金额': 'amount',
            '手续费': 'fee',
            # #2137 费用拆分（可选列，缺省即未拆分）：模板带明细列才逐类落库
            '佣金': 'fee_commission',
            '印花税': 'fee_stamp_duty',
            '过户费': 'fee_transfer_fee',
            '其他费用': 'fee_other',
            '净值': 'nav',
            '账户名称': 'account_name',
            '交易流水号': 'transaction_id',
        }

    @property
    def _required_columns(self) -> list:
        return ['确认日期', '基金代码', '业务类型', '金额']

    def _normalize_code(self, raw: str) -> Optional[str]:
        return normalize_fund_code(raw)

    def _map_business_type(self, raw: str) -> str:
        return FUND_OP_MAP.get(raw, raw)

    @property
    def _asset_type(self) -> str:
        return 'fund'


class StockStandardParser(StandardTemplateParser):
    source = PositionSource.BROKER_STD_STOCK.value
    # 股票模板 = 交易所撮合：代码带 SH/SZ/BJ 前缀（#1662）
    venue = EXCHANGE

    @property
    def _column_map(self) -> dict:
        return {
            '确认日期': 'confirm_date',
            '交易日期': 'trade_date',
            '股票代码': 'symbol',
            '股票名称': 'name',
            '业务类型': 'business_type',
            '数量(股)': 'shares',
            '成交均价': 'nav',
            '成交金额': 'amount',
            '手续费': 'fee',
            # #2137 费用拆分（可选列，缺省即未拆分）：模板带明细列才逐类落库
            '佣金': 'fee_commission',
            '印花税': 'fee_stamp_duty',
            '过户费': 'fee_transfer_fee',
            '其他费用': 'fee_other',
            '账户名称': 'account_name',
            '合同编号': 'transaction_id',
        }

    @property
    def _required_columns(self) -> list:
        return ['确认日期', '股票代码', '业务类型', '成交金额']

    def _normalize_code(self, raw: str) -> Optional[str]:
        return normalize_stock_code(raw)

    def _map_business_type(self, raw: str) -> str:
        return STOCK_OP_MAP.get(raw, raw)

    @property
    def _asset_type(self) -> str:
        return 'stock'
