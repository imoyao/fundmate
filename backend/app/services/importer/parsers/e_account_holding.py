# -*- coding: utf-8 -*-
"""
基金E账户（公募基金统一账户）导出持仓解析器（#1012）。

文件结构（真实样本 2026-08-12 核实）：
- sheet 名「持有信息」，唯一 sheet；
- 头部可能含标题行（「基金E账户App投资者公募基金持有信息」）与个人信息行
  （姓名/证件类型/证件号码）——用户上传时可能保留（未编辑）或删除（已处理），
  因此解析器必须自动定位真正的表头行，不能假设表头固定在第 1 行；
- 真正的表头行含「基金代码」「持有份额」等关键列；
- 数据行：基金代码(6位数字) / 基金名称 / 持有份额 / 份额日期 / 基金净值 /
  资产市值 / 结算币种 / 销售机构 / 基金管理人 / 份额类别 / 基金账户 / 交易账户 / 分红方式。

容错策略：
1. 表头定位：扫描前 20 行，找同时含「基金代码」+「持有份额」的行作为表头；
2. 列名清洗：去换行/空格后匹配（样本「资产情况\n（结算币种）」含换行）；
3. 数据行校验：基金代码非 6 位数字、份额/日期解析失败 → 收集错误并跳过该行；
4. 空行/合计行自动跳过。
"""

from datetime import date
from typing import List, Optional, Tuple

import pandas as pd

from app.services.importer.base import BaseHoldingParser
from app.services.importer.records import SBImportError, StandardHoldingRecord
from app.services.importer.utils import clean_amount, clean_nav, clean_shares, normalize_fund_code, parse_date

# 表头定位关键列：必须同时出现才认定为真正的表头行
HEADER_KEY_COLUMNS = ('基金代码', '持有份额')

# 表头扫描上限（前 N 行内定位，防止异常文件全表扫描）
HEADER_SCAN_LIMIT = 20

# 样本表头 → 标准字段映射（键为清洗后的列名：去换行/空格）
COLUMN_MAP = {
    '基金代码': 'symbol',
    '基金名称': 'name',
    '持有份额': 'shares',
    '份额日期': 'snapshot_date',
    '基金净值': 'nav',
    '资产情况（结算币种）': 'market_value',
    '结算币种': 'currency',
    '销售机构': 'source_broker',
    '基金管理人': 'fund_manager',
    '份额类别': 'share_class',
    '基金账户': 'fund_account',
    '交易账户': 'trade_account',
    '分红方式': 'dividend_preference',
}

# 币种映射：样本中文 → 标准 ISO 代码
CURRENCY_MAP = {
    '人民币': 'CNY',
    '美元': 'USD',
    '港币': 'HKD',
}


def _clean_col(name) -> str:
    """清洗列名：去换行、去空格（样本「资产情况\\n（结算币种）」需归一）。"""
    return str(name).strip().replace('\n', '').replace(' ', '')


class EAccountHoldingParser(BaseHoldingParser):
    """基金E账户导出持仓解析器：只实现文件列映射，落库走持仓汇点。"""

    source = 'e_account_holding'

    # ── 表头定位 ──

    def _locate_header_row(self, df: pd.DataFrame) -> Optional[int]:
        """在原始 DataFrame 中定位真正的表头行（含关键列的行）。

        返回表头行索引；找不到返回 None（文件格式不匹配）。
        """
        for idx in range(min(len(df), HEADER_SCAN_LIMIT)):
            row = df.iloc[idx]
            cells = {_clean_col(v) for v in row.tolist() if pd.notna(v)}
            if all(k in cells for k in HEADER_KEY_COLUMNS):
                return idx
        return None

    def _build_column_index(self, header_row: pd.Series) -> dict:
        """表头行 → {标准字段: 列索引} 映射（经 COLUMN_MAP 转换）。"""
        index = {}
        for col_idx, raw in enumerate(header_row.tolist()):
            if pd.notna(raw):
                std_key = COLUMN_MAP.get(_clean_col(raw))
                if std_key:
                    index[std_key] = col_idx
        return index

    # ── 解析 ──

    def parse(self, file_bytes: bytes) -> Tuple[List[StandardHoldingRecord], List[SBImportError]]:
        records: List[StandardHoldingRecord] = []
        errors: List[SBImportError] = []

        df = self._read_excel(file_bytes, header=None)
        if df is None:
            errors.append(SBImportError(line_number=0, field_name=None, message='无法读取 Excel 文件'))
            return records, errors

        header_idx = self._locate_header_row(df)
        if header_idx is None:
            errors.append(
                SBImportError(
                    line_number=0,
                    field_name=None,
                    message=f'未找到持仓表头（缺少关键列: {"、".join(HEADER_KEY_COLUMNS)}），请确认是基金E账户导出文件',
                )
            )
            return records, errors

        col_index = self._build_column_index(df.iloc[header_idx])

        # 数据行：表头下一行开始
        for offset, (line_idx, raw_row) in enumerate(df.iloc[header_idx + 1 :].iterrows(), start=1):
            line_num = header_idx + offset + 1  # 1-based 行号（含表头前的内容）
            try:
                record = self._parse_row(raw_row, col_index, line_num)
                if record is None:
                    continue  # 空行/合计行
                records.append(record)
            except ValueError as e:
                errors.append(
                    SBImportError(
                        line_number=line_num,
                        field_name=None,
                        message=str(e),
                        raw_value=str(raw_row.tolist()),
                    )
                )

        return records, errors

    def _parse_row(self, raw_row: pd.Series, col_index: dict, line_num: int) -> Optional[StandardHoldingRecord]:
        """单行 → StandardHoldingRecord；空行返回 None；解析失败抛 ValueError。"""

        def cell(std_key: str) -> str:
            col_idx = col_index.get(std_key)
            if col_idx is None:
                return ''
            val = raw_row.iloc[col_idx]
            return '' if pd.isna(val) else str(val).strip()

        # 空行/合计行跳过：基金代码为空即跳过
        symbol_raw = cell('symbol')
        if not symbol_raw:
            return None

        symbol = normalize_fund_code(symbol_raw)
        if not symbol:
            raise ValueError(f'无法识别基金代码: {symbol_raw}')

        shares = clean_shares(cell('shares'), '0.00')
        if shares is None or shares <= 0:
            raise ValueError(f'持有份额无效: {cell("shares")}')

        snapshot_date = parse_date(cell('snapshot_date'))
        if not snapshot_date:
            raise ValueError(f'份额日期格式错误: {cell("snapshot_date")}')

        nav = clean_nav(cell('nav')) if cell('nav') else None
        market_value = clean_amount(cell('market_value')) if cell('market_value') else None

        currency_raw = cell('currency')
        currency = CURRENCY_MAP.get(currency_raw, currency_raw or 'CNY')

        return StandardHoldingRecord(
            symbol=symbol,
            name=cell('name') or symbol,
            shares=shares,
            snapshot_date=snapshot_date,
            asset_type='fund',
            nav=nav,
            market_value=market_value,
            currency=currency,
            source_broker=cell('source_broker') or None,
            fund_manager=cell('fund_manager') or None,
            share_class=cell('share_class') or None,
            fund_account=cell('fund_account') or None,
            trade_account=cell('trade_account') or None,
            dividend_preference=cell('dividend_preference') or None,
            source=self.source,
        )

    # ── 校验 ──

    def validate(self, records: List[StandardHoldingRecord]) -> Tuple[List[StandardHoldingRecord], List[SBImportError]]:
        valid_records = []
        errors = []
        for i, r in enumerate(records):
            line_num = i + 1
            row_errors = []
            if not r.symbol:
                row_errors.append(SBImportError(line_num, 'symbol', '基金代码不能为空'))
            if not r.shares or r.shares <= 0:
                row_errors.append(SBImportError(line_num, 'shares', '持有份额必须大于0'))
            if not r.snapshot_date:
                row_errors.append(SBImportError(line_num, 'snapshot_date', '快照日期不能为空'))
            if r.snapshot_date and r.snapshot_date > date.today():
                row_errors.append(SBImportError(line_num, 'snapshot_date', '快照日期不能晚于今天'))
            if row_errors:
                errors.extend(row_errors)
            else:
                valid_records.append(r)
        return valid_records, errors
