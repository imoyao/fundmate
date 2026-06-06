# -*- coding: utf-8 -*-
"""
同花顺股票交割单解析器。

完整迁移旧 TransactionParser 的同花顺逻辑，独立实现 parse() 和 validate()。
"""

import decimal
import io
import math
import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

import pandas as pd
from loguru import logger

from app.core.constants import CASH_SYMBOL
from app.core.symbol_utils import get_normalizer
from app.services.importer.base import BaseImportParser
from app.services.importer.mappings import THS_OP_MAP, VALID_OP_TYPES
from app.services.importer.records import SBImportError, StandardTransactionRecord


class THSStockParser(BaseImportParser):
    """同花顺股票交割单解析器"""

    source = 'ths_stock'

    def __init__(self):
        self.normalizer = get_normalizer()

    # ── 解析 ──

    def parse(self, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """解析同花顺交割单文件"""
        records = []
        errors = []

        # 1. 读取文件为 DataFrame
        df = self._read_file_to_dataframe(file_bytes)
        if df is None:
            errors.append(SBImportError(0, None, '无法自动识别文件编码，请将文件另存为 UTF-8 编码的 CSV 后重新上传'))
            return records, errors

        if df.empty:
            errors.append(SBImportError(0, None, '文件中未找到有效数据'))
            return records, errors

        # 2. 校验必填列
        col_errors = self._validate_required_columns(df)
        if col_errors:
            errors.extend(col_errors)
            return records, errors

        # 3. 预处理 DataFrame（合同编号格式化、费用合并）
        self._preprocess_dataframe(df)

        # 4. 逐行解析
        records, row_errors = self._iterrows_to_records(df)

        records = self._link_bond_interest_and_tax(records)
        errors.extend(row_errors)

        return records, errors

    def _link_bond_interest_and_tax(self, records: List[StandardTransactionRecord]) -> List[StandardTransactionRecord]:
        """识别同日期同代码的债券兑息和债券兑息兑付，生成关联ID"""
        interest_by_key: dict[tuple, StandardTransactionRecord] = {}
        tax_by_key: dict[tuple, StandardTransactionRecord] = {}

        for rec in records:
            key = (rec.symbol, rec.trade_date)
            if rec.raw_op_type == '债券兑息':
                interest_by_key[key] = rec
            elif rec.raw_op_type == '债券兑息兑付':
                tax_by_key[key] = rec

        for key in set(interest_by_key.keys()) & set(tax_by_key.keys()):
            group_id = str(uuid.uuid4())
            interest_by_key[key].link_group_id = group_id
            tax_by_key[key].link_group_id = group_id

        return records

    # ── 文件读取 ──

    def _read_file_to_dataframe(self, file_bytes: bytes) -> Optional[pd.DataFrame]:
        # 1. Excel 优先
        for engine in ['openpyxl', 'xlrd']:
            try:
                df = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
                if df is not None and not df.empty:
                    return df
            except Exception:
                continue

        # 2. 同花顺文件固定为制表符分隔，优先 utf-8-sig，其次 gbk
        for enc in ['utf-8-sig', 'gbk']:
            try:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep='\t',
                    encoding=enc,
                    encoding_errors='ignore',
                    dtype={'证券代码': str, '合同编号': str},
                )
                if df.empty:
                    continue
                df.dropna(how='all', inplace=True)
                df.columns = df.columns.str.strip()
                if any(self._contains_chinese(col) for col in df.columns):
                    return df
            except Exception:
                continue

        # 3. 极少数情况尝试逗号分隔（仅一次）
        try:
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                sep=',',
                encoding='utf-8-sig',
                encoding_errors='ignore',
                dtype={'证券代码': str, '合同编号': str},
            )
            if not df.empty:
                df.dropna(how='all', inplace=True)
                df.columns = df.columns.str.strip()
                if any(self._contains_chinese(col) for col in df.columns):
                    return df
        except Exception:
            pass

        # 4. HTML 兜底
        for enc in ['utf-8', 'gbk']:
            try:
                dfs = pd.read_html(io.BytesIO(file_bytes), encoding=enc)
                if dfs:
                    df = dfs[0]
                    df.columns = df.columns.str.strip()
                    if any(self._contains_chinese(col) for col in df.columns):
                        return df
            except Exception:
                continue

        return None

    @staticmethod
    def _contains_chinese(text: str) -> bool:
        """检测字符串是否包含中文字符"""
        return bool(re.search(r'[\u4e00-\u9fff]', text))

    # ── 列校验与预处理 ──

    def _validate_required_columns(self, df: pd.DataFrame) -> List[SBImportError]:
        """检查必填列是否存在"""
        required = ['证券代码', '操作', '成交数量', '成交均价', '交收日期']
        missing = [c for c in required if c not in df.columns]
        if missing:
            return [SBImportError(0, None, f"缺少必要列: {', '.join(missing)}。请确认上传的是同花顺历史交割单导出文件")]
        return []

    def _preprocess_dataframe(self, df: pd.DataFrame) -> None:
        # 合同编号格式化
        if '合同编号' in df.columns:
            df['合同编号'] = df['合同编号'].apply(self._format_contract_id)
        # 清理证券代码的 Excel 浮点后缀（仅去掉 ".0"，保留末尾零）
        if '证券代码' in df.columns:
            df['证券代码'] = df['证券代码'].apply(lambda x: re.sub(r'\.0$', '', str(x)) if pd.notna(x) else '')
        # 费用合并
        fee_cols = ['佣金', '印花税', '过户费', '其他杂费']
        available_fee = [c for c in fee_cols if c in df.columns]
        if available_fee:
            df['fee'] = df[available_fee].apply(
                lambda row: sum(float(v) for v in row if pd.notna(v) and str(v).strip() not in ('', '0')),
                axis=1,
            )
        else:
            df['fee'] = 0.0

    # ── 逐行解析 ──

    def _iterrows_to_records(self, df: pd.DataFrame) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """遍历 DataFrame 行，调用 _parse_row 解析"""
        records = []
        errors = []
        for idx, raw_dict in enumerate(df.to_dict('records')):
            line_num = idx + 2
            try:
                record = self._parse_row(raw_dict, line_num)
                if record:
                    records.append(record)
            except Exception as e:
                errors.append(SBImportError(line_num, None, f'行解析失败: {str(e)}'))
        return records, errors

    @staticmethod
    def _safe_str(raw: dict, key: str, default: str = '') -> str:
        """安全获取字典值，将 NaN 或字符串 'nan' 统一返回默认值"""
        val = raw.get(key, default)
        if isinstance(val, float) and math.isnan(val):
            return default
        if isinstance(val, str) and val.strip().lower() == 'nan':
            return default
        return str(val).strip()

    @staticmethod
    def _safe_decimal(raw_val: float) -> Decimal:
        """将浮点数安全转为 Decimal，NaN/Inf 转为 0"""
        try:
            if math.isnan(raw_val) or math.isinf(raw_val):
                return Decimal('0')
            return Decimal(str(raw_val))
        except (decimal.InvalidOperation, ValueError):
            return Decimal('0')

    @staticmethod
    def _safe_float(raw: dict, key: str, default: float = 0.0) -> float:
        """安全获取浮点值，NaN 或缺失时返回默认值"""
        val = raw.get(key, default)
        if isinstance(val, float) and math.isnan(val):
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    # ── 行解析 ──

    def _parse_row(self, raw: dict, line_num: int) -> Optional[StandardTransactionRecord]:
        """解析单行同花顺记录"""
        op_type_cn = self._safe_str(raw, '操作')

        # 处理带问号的特殊格式
        otc_match = re.match(r'^(OTC\S+)\?([-]?\d+(?:\.\d+)?)', op_type_cn)
        if otc_match:
            op_type_cn = otc_match.group(1)
        general_match = re.match(r'^([^?]+)\?([-]?\d+(?:\.\d+)?)', op_type_cn)
        if general_match and not op_type_cn.startswith('OTC'):
            op_type_cn = general_match.group(1)

        # 资金划转特殊处理
        if op_type_cn in ('银行转证券', '证券转银行', 'OTC资金划出', 'OTC资金划入', 'OTC现金宝交', 'OTC资管转让'):
            return self._parse_cash_transfer(raw, op_type_cn)

        # 业务类型映射
        business_type = THS_OP_MAP.get(op_type_cn)
        if business_type is None:
            logger.debug(f'无法识别的同花顺操作类型: [{op_type_cn}] (line {line_num})')
            return None

        if business_type not in VALID_OP_TYPES:
            raise ValueError(f'不支持的同花顺操作类型: {op_type_cn}')

        # 代码标准化（同时获取 suggested_type）
        symbol_raw = self._safe_str(raw, '证券代码')
        try:
            normalized, _, suggested_type = self.normalizer.normalize(symbol_raw)
        except Exception:
            normalized, suggested_type = None, None
        symbol = normalized if normalized else symbol_raw

        # 根据 suggested_type 确定资产类型
        if suggested_type:
            asset_type = suggested_type  # 可能为 'money_fund', 'reverse_repo' 等
        elif business_type == 'dividend_cash' and op_type_cn == '利息归本':
            asset_type = 'cash'
        else:
            asset_type = 'stock'

        # 提取字段并构建标准记录
        trade_date = self._parse_ths_date(raw)
        contract_id = self._safe_str(raw, '合同编号')
        quantity = self._safe_float(raw, '成交数量')
        price = self._safe_float(raw, '成交均价')
        fee = self._safe_float(raw, 'fee')
        trade_amount = self._safe_float(raw, '成交金额')
        net_amount_raw = self._safe_float(raw, '发生金额')

        actual_amount = self._compute_actual_amount(business_type, trade_amount, net_amount_raw)
        net_amount_abs = abs(net_amount_raw)

        return StandardTransactionRecord(
            confirm_date=trade_date,
            trade_date=trade_date,
            asset_type=asset_type,
            symbol=symbol,
            name=self._safe_str(raw, '证券名称') or symbol,
            business_type=business_type,
            amount=self._safe_decimal(actual_amount),
            account_name='',  # 前端会覆盖
            shares=self._safe_decimal(quantity),
            nav=self._safe_decimal(price),
            fee=self._safe_decimal(fee),
            transaction_id=contract_id,
            source=self.source,
            raw_op_type=op_type_cn,  # 保留原始中文操作类型
            trade_amount=float(trade_amount),
            net_amount=float(net_amount_abs),
        )

    def _parse_cash_transfer(self, raw: dict, op_type_cn: str) -> StandardTransactionRecord:
        """处理资金划转类型"""
        net_amount_raw = self._safe_float(raw, '发生金额')
        return StandardTransactionRecord(
            confirm_date=self._parse_ths_date(raw),
            asset_type='cash',
            symbol=CASH_SYMBOL,
            name=op_type_cn,  # 使用操作类型作为名称
            business_type='deposit' if net_amount_raw >= 0 else 'withdraw',
            amount=Decimal(str(abs(net_amount_raw))),
            account_name='',
            source=self.source,
        )

    # ── 辅助方法 ──

    def _parse_ths_date(self, raw: dict) -> date:
        """从同花顺行字典中提取交收日期（YYYYMMDD），返回 date 对象"""
        date_str = self._safe_str(raw, '交收日期')
        if not date_str:
            raise ValueError('交收日期为空')
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except ValueError:
            raise ValueError(f'无效的日期格式: {date_str}')

    @staticmethod
    def _compute_actual_amount(business_type: str, trade_amount: float, net_amount_raw: float) -> float:
        if business_type == 'tax':
            # 扣税：取发生金额的绝对值，然后强制为负
            return -abs(net_amount_raw) if net_amount_raw != 0 else -abs(trade_amount)
        elif business_type in ('buy', 'sell'):
            return abs(net_amount_raw) if net_amount_raw != 0 else abs(trade_amount)
        else:
            return abs(net_amount_raw)

    @staticmethod
    def _format_contract_id(x) -> str:
        if x is None or (isinstance(x, float) and math.isnan(x)) or str(x).strip() in ('', 'nan', 'None'):
            return ''
        try:
            return str(int(float(x))).zfill(10)
        except (ValueError, TypeError):
            return str(x).strip()

    # ── 校验 ──

    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        valid_records = []
        errors = []
        for i, record in enumerate(records):
            line_num = i + 2
            if not record.symbol:
                errors.append(SBImportError(line_num, 'symbol', '证券代码不能为空'))
            elif record.amount == Decimal('0'):
                errors.append(SBImportError(line_num, 'amount', '金额不能为0'))
            else:
                valid_records.append(record)
        return valid_records, errors
