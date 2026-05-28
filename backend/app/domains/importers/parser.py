# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/17 10:55
# File : parser.py
"""交易文件解析器 — 支持标准模板和同花顺交割单"""

import hashlib
import io
import re
import uuid
from datetime import date, datetime
from pathlib import PurePath
from typing import Optional

import pandas as pd
from loguru import logger
from sqlalchemy.orm import Session

from app.core.constants import (
    CASH_SYMBOL,
    DEFAULT_MARKET_CN,
    DEFAULT_THS_ACCOUNT,
    DEFAULT_TYPE_CASH,
    DEFAULT_TYPE_STOCK,
    OP_TYPE_LABEL,
    THS_OP_TYPE_MAP,
)
from app.core.symbol_utils import get_normalizer
from app.domains.importers.templates import STANDARD_TEMPLATE, ImportTemplate
from app.domains.transactions.models import Transaction


class TransactionParser:
    """交易记录解析器"""

    def __init__(self, template: ImportTemplate = STANDARD_TEMPLATE):
        self.template = template
        self.normalizer = get_normalizer()
        self._is_ths = template.name == '同花顺交割单'
        self._sep = '\t' if self._is_ths else ','

    def _contains_chinese(self, text: str) -> bool:
        """检测字符串是否包含中文字符"""
        return bool(re.search(r'[\u4e00-\u9fff]', text))

    def _link_bond_interest_and_tax(self, rows: list[dict]) -> list[dict]:
        """
        识别同日期同代码的"债券兑息"和"债券兑息兑付"，
        为它们生成相同的 link_group_id，不做数据合并。
        """

        # 收集所有配对候选项
        interest_by_key: dict[tuple, dict] = {}
        tax_by_key: dict[tuple, dict] = {}

        for row in rows:
            key = (row['symbol'], row['trade_date'])

            if row.get('op_type') == 'dividend' and row.get('notes') == '债券兑息':
                interest_by_key[key] = row
            elif row.get('op_type') == 'tax' and row.get('notes') == '债券兑息兑付':
                tax_by_key[key] = row

        # 为配对的记录添加相同的 link_group_id
        for key in set(interest_by_key.keys()) & set(tax_by_key.keys()):
            group_id = str(uuid.uuid4())
            interest_by_key[key]['link_group_id'] = group_id
            tax_by_key[key]['link_group_id'] = group_id

        return rows

    def parse(self, file_bytes: bytes, filename: str = '', encoding: str = 'utf-8') -> list[dict]:
        ext = PurePath(filename).suffix.lstrip('.').lower() if filename else 'csv'
        df = None

        # 1. 尝试真正的 Excel
        if ext in ('xls', 'xlsx'):
            for engine in ['openpyxl', 'xlrd']:
                try:
                    df = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
                    break
                except Exception:
                    continue

        # 2. 智能编码检测文本解析
        if df is None:
            encodings_to_try = ['utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'big5']
            read_kwargs = dict(sep=self._sep)
            if self._is_ths:
                read_kwargs['dtype'] = {'合同编号': str}

            success = False
            for enc in encodings_to_try:
                try:
                    tmp_df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc, encoding_errors='ignore', **read_kwargs)
                    tmp_df.dropna(how='all', inplace=True)
                    tmp_df.columns = tmp_df.columns.str.strip()
                    if any(self._contains_chinese(col) for col in tmp_df.columns):
                        df = tmp_df
                        logger.info(f'成功以文本解析，编码: {enc}')
                        success = True
                        break
                except Exception as e:
                    logger.debug(f'编码 {enc} 尝试失败: {e}')
                    continue

            if not success:
                # HTML 解析（兜底）
                for enc in ['utf-8', 'gbk', 'gb18030']:
                    try:
                        dfs = pd.read_html(io.BytesIO(file_bytes), encoding=enc)
                        if dfs:
                            df = dfs[0]
                            df.columns = df.columns.str.strip()
                            if any(self._contains_chinese(col) for col in df.columns):
                                logger.info(f'成功以 HTML 表格解析，编码: {enc}')
                                success = True
                                break
                    except Exception:
                        continue

            if not success:
                raise ValueError('无法自动识别文件编码，请将文件另存为 UTF-8 编码的 CSV 后重新上传')

        if df.empty:
            raise ValueError('文件中未找到有效数据')
        # 合同编号格式化
        if self._is_ths and '合同编号' in df.columns:

            def fmt_contract(x):
                if pd.isna(x) or str(x).strip() in ('', 'nan', 'None'):
                    return ''
                try:
                    return str(int(float(x))).zfill(10)
                except (ValueError, TypeError):
                    return str(x).strip()

            df['合同编号'] = df['合同编号'].apply(fmt_contract)

        # 列校验
        valid, missing = self.template.validate_columns(set(df.columns))
        if not valid:
            available = ', '.join(df.columns)
            missing_str = ', '.join(missing)
            raise ValueError(
                f'文件缺少必要列: {missing_str}\n'
                f'当前文件包含的列: {available}\n'
                '请确认上传的是同花顺历史交割单导出文件，并确保使用制表符分隔。'
            )

        # 选择列并重命名
        cols_to_keep = [c for c in self.template.column_map.keys() if c in df.columns]

        # 同花顺费用处理
        if self._is_ths:
            fee_cols = ['佣金', '印花税', '过户费', '其他杂费']
            available_fee = [c for c in fee_cols if c in df.columns]
            if available_fee:
                df['fee'] = df[available_fee].apply(
                    lambda row: sum(float(v) for v in row if pd.notna(v) and str(v).strip() not in ('', '0')), axis=1
                )
            else:
                df['fee'] = 0.0
            cols_to_keep = [c for c in cols_to_keep if c not in fee_cols]
            if 'fee' not in cols_to_keep:
                cols_to_keep.append('fee')

        df = df[cols_to_keep].rename(columns=self.template.column_map)
        df = df.loc[:, ~df.columns.duplicated()]

        # 去除 symbol 列末尾的 .0
        if 'symbol' in df.columns:
            df['symbol'] = df['symbol'].apply(lambda x: str(x).rstrip('.0') if pd.notna(x) else '')

        rows = []
        for _, raw in df.iterrows():
            row = self._parse_row(raw)
            if row:
                rows.append(row)
        return rows

    def _parse_row(self, raw: pd.Series) -> Optional[dict]:
        if self._is_ths:
            return self._parse_ths_row(raw)
        return self._parse_standard_row(raw)

    def _parse_standard_row(self, raw: pd.Series) -> Optional[dict]:
        try:
            symbol_raw = str(raw.get('symbol', '')).strip()
            if not symbol_raw:
                return None

            normalized, market, suggested_type = self.normalizer.normalize(symbol_raw)
            symbol = normalized if normalized else symbol_raw

            # 重命名后的列名是 'purchase_date'
            trade_date_str = str(raw.get('purchase_date', '')).strip()
            trade_date = datetime.strptime(trade_date_str, '%Y-%m-%d').date() if trade_date_str else date.today()

            op_type = str(raw.get('op_type', 'buy')).strip()

            return {
                'symbol': symbol,
                'name': str(raw.get('name', '')).strip() or symbol,
                'market': market or str(raw.get('market', 'UNKNOWN')).strip(),
                'type': str(raw.get('type', 'stock')).strip(),
                'account_name': str(raw.get('account_name', '默认账户')).strip(),
                'op_type': op_type,
                'op_type_label': OP_TYPE_LABEL.get(op_type, op_type),
                'quantity': float(raw.get('quantity', 0)),
                'price': float(raw.get('avg_price', 0)),
                'amount': float(raw.get('amount', 0) or 0),
                'currency': str(raw.get('currency', 'CNY')).strip(),
                'trade_date': trade_date_str,  # 前端使用 trade_date
                'fee': float(raw.get('fee', 0)),
                'notes': str(raw.get('notes', '')).strip(),
                'contract_id': str(raw.get('contract_id', '')),
                'is_cash_transfer': False,
            }
        except Exception as e:
            return {'symbol': str(raw.get('symbol', '')), 'error': f'解析失败: {str(e)}', 'is_cash_transfer': False}

    def _parse_ths_row(self, raw: pd.Series) -> Optional[dict]:
        op_type_cn = str(raw.get('op_type', '')).strip()

        # 处理带问号的特殊格式（如 OTC现金宝交?0）
        otc_match = re.match(r'^(OTC\S+)\?([-]?\d+(?:\.\d+)?)', op_type_cn)
        if otc_match:
            op_type_cn = otc_match.group(1)
            raw['notes_extra'] = f'OTC变动数量:{otc_match.group(2)}'
        general_match = re.match(r'^([^?]+)\?([-]?\d+(?:\.\d+)?)', op_type_cn)
        if general_match and not op_type_cn.startswith('OTC'):
            op_type_cn = general_match.group(1)

        # ===== 先处理资金划转，不依赖 mapped_op =====
        if op_type_cn in ('银行转证券', '证券转银行', 'OTC资金划出', 'OTC资金划入', 'OTC现金宝交', 'OTC资管转让'):
            net_amount_raw = float(raw.get('net_amount', 0) or 0)
            op_type = 'deposit' if net_amount_raw >= 0 else 'withdraw'
            return {
                'symbol': CASH_SYMBOL,
                'name': op_type_cn,
                'op_type': op_type,
                'op_type_label': OP_TYPE_LABEL.get(op_type, op_type_cn),
                'amount': abs(net_amount_raw),
                'trade_date': self._parse_ths_date(raw),
                'account_name': DEFAULT_THS_ACCOUNT,
                'is_cash_transfer': True,
                'transfer_desc': op_type_cn,
                'market': DEFAULT_MARKET_CN,
                'type': DEFAULT_TYPE_CASH,
                'quantity': 0,
                'price': 0,
                'fee': 0,
                'currency': str(raw.get('currency', 'CNY')).strip(),
                'notes': op_type_cn,
                'error': None,
                'contract_id': '',
                'trade_amount': 0,
                'net_amount': abs(net_amount_raw),
            }

        # ===== 非资金划转，通过映射表获取操作码 =====
        mapped_op = THS_OP_TYPE_MAP.get(op_type_cn)
        if mapped_op is None:
            return None  # 明确需要过滤的记录（如指定交易）

        symbol_raw = str(raw.get('symbol', '')).strip()
        normalized, market, suggested_type = self.normalizer.normalize(symbol_raw)
        symbol = normalized if normalized else symbol_raw
        market = market or DEFAULT_MARKET_CN

        # 确定产品类型
        if suggested_type:
            row_type = suggested_type
        elif mapped_op == 'dividend' and op_type_cn == '利息归本':
            row_type = 'cash'  # 利息归本视为现金
        else:
            row_type = DEFAULT_TYPE_STOCK

        # 对于现金管理类，自动设置配置目标为活钱
        allocation = 'liquid' if row_type in ('money_fund', 'reverse_repo') else None

        if not symbol_raw:
            # 无代码但未过滤的记录，保留为“其他”
            return {
                'symbol': 'UNKNOWN',
                'name': op_type_cn,
                'market': market,
                'type': row_type,
                'allocation': allocation,  # 如果为 None，前端会使用账户默认值
                'op_type': 'other',
                'op_type_label': '其他',
                'amount': abs(float(raw.get('net_amount', 0) or 0)),
                'trade_date': self._parse_ths_date(raw),
                'account_name': DEFAULT_THS_ACCOUNT,
                'is_cash_transfer': False,
                'quantity': 0,
                'price': 0,
                'fee': 0,
                'currency': str(raw.get('currency', 'CNY')).strip(),
                'notes': op_type_cn,
                'contract_id': '',
                'trade_amount': 0,
                'net_amount': abs(float(raw.get('net_amount', 0) or 0)),
            }

        symbol = normalized if normalized else symbol_raw

        trade_date_str = self._parse_ths_date(raw)
        quantity = float(raw.get('quantity', 0) or 0)
        price = float(raw.get('avg_price', 0) or 0)
        fee = float(raw.get('fee', 0) or 0)
        contract_id = str(raw.get('contract_id', '')).strip()

        trade_amount = float(raw.get('amount', 0) or 0)
        net_amount_raw = float(raw.get('net_amount', 0) or 0)
        net_amount_abs = abs(net_amount_raw)
        actual_amount = trade_amount if trade_amount > 0 else net_amount_abs

        # 如果是扣税，金额应为负（支出）
        if mapped_op == 'tax':
            actual_amount = -net_amount_abs if net_amount_raw < 0 else -abs(trade_amount)
        if suggested_type:
            row_type = suggested_type
        else:
            row_type = DEFAULT_TYPE_STOCK

            # 现金管理类产品自动归入“活钱”
        allocation = 'liquid' if row_type in ('money_fund', 'reverse_repo') else None

        return {
            'symbol': symbol,
            'name': str(raw.get('name', '')).strip() or symbol,
            'market': market or DEFAULT_MARKET_CN,
            'type': row_type,
            'allocation': allocation,
            'account_name': DEFAULT_THS_ACCOUNT,
            'op_type': mapped_op,
            'op_type_label': OP_TYPE_LABEL.get(mapped_op, op_type_cn),
            'quantity': quantity,
            'price': price,
            'amount': actual_amount,
            'trade_amount': trade_amount,
            'net_amount': net_amount_abs,
            'currency': str(raw.get('currency', 'CNY')).strip(),
            'trade_date': trade_date_str,
            'fee': fee,
            'notes': op_type_cn,
            'contract_id': contract_id,
            'is_cash_transfer': False,
        }

    def _parse_ths_date(self, raw: pd.Series) -> str:
        # 重命名后的列名是 'purchase_date'，因为模板中 '交收日期' -> 'purchase_date'
        date_str = str(raw.get('purchase_date', '')).strip()
        try:
            parsed = datetime.strptime(date_str, '%Y%m%d').date()
            return parsed.isoformat()
        except ValueError:
            return date.today().isoformat()

    def compute_hashes(self, rows: list[dict]) -> list[dict]:
        for row in rows:
            if row.get('error') or row.get('is_cash_transfer'):
                continue
            contract = row.get('contract_id', '')
            if contract:
                raw = f"{row['symbol']}|{contract}|{row['op_type']}"
            else:
                raw = f"{row['symbol']}|{row['trade_date']}|{row['op_type']}|{row['quantity']}|{row['price']}"
            row['import_hash'] = hashlib.md5(raw.encode()).hexdigest()
        rows = self._link_bond_interest_and_tax(rows)
        return rows

    def check_duplicates(self, db: Session, rows: list[dict]) -> list[dict]:
        hashes = [r['import_hash'] for r in rows if r.get('import_hash')]
        if not hashes:
            return rows
        existing_hashes = set(
            h[0] for h in db.query(Transaction.import_hash).filter(Transaction.import_hash.in_(hashes)).all()
        )
        for row in rows:
            if row.get('import_hash') and row['import_hash'] in existing_hashes:
                row['is_duplicate'] = True
            else:
                row['is_duplicate'] = False
        return rows
