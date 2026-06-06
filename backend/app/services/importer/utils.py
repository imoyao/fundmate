# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 23:35
# File : utils.py
# -*- coding: utf-8 -*-
"""
导入系统公共工具函数。

从现有 TransactionParser 中提取的纯函数，供所有解析器子类复用。
不依赖任何特定平台逻辑。
"""

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

from app.core.symbol_utils import get_normalizer

# ── 金额/数值清洗 ──


def clean_amount(raw: str) -> Optional[Decimal]:
    """
    将原始金额字符串转换为 Decimal。

    处理规则：
        - 去除千分位分隔符（,）
        - 去除货币符号（¥、$等）
        - 去除首尾空格
        - 空字符串返回 None
        - 无法解析返回 None（不抛异常，由调用方决定如何处理）
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip().replace(',', '').replace('¥', '').replace('$', '').replace('，', '')
    if not cleaned or cleaned == '-':
        return None

    try:
        return Decimal(cleaned).quantize(Decimal('0.00'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def clean_shares(raw: str, precision: str = '0.00') -> Optional[Decimal]:
    """
    将原始份额字符串转换为 Decimal。

    Args:
        raw: 原始字符串
        precision: 精度，基金份额默认 '0.00'，股票数量默认 '0'

    Returns:
        Decimal 或 None
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip().replace(',', '')
    if not cleaned or cleaned == '-':
        return None

    try:
        return Decimal(cleaned).quantize(Decimal(precision), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def clean_nav(raw: str) -> Optional[Decimal]:
    """
    将原始净值字符串转换为 Decimal。

    精度保留 4 位小数。
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip()
    if not cleaned or cleaned == '-':
        return None

    try:
        return Decimal(cleaned).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


# ── 日期解析 ──


def parse_date(raw: str) -> Optional[date]:
    """
    将原始日期字符串解析为 date 对象。

    支持格式（自动检测）：
        - YYYY-MM-DD
        - YYYY/MM/DD
        - YYYYMMDD
        - YYYY年MM月DD日
        - YYYY.MM.DD
    """
    if not raw or not isinstance(raw, str):
        return None

    cleaned = raw.strip().replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-').replace('.', '-')

    # 纯数字 YYYYMMDD 格式
    if len(cleaned) == 8 and cleaned.isdigit():
        try:
            return datetime.strptime(cleaned, '%Y%m%d').date()
        except ValueError:
            pass

    # 标准格式
    for fmt in ['%Y-%m-%d', '%Y-%m-%d']:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue

    return None


# ── 代码标准化 ──


def normalize_fund_code(raw: str) -> Optional[str]:
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    # 处理 Excel 可能截断的数字结尾 .0
    if cleaned.endswith('.0'):
        cleaned = cleaned[:-2]
    if not cleaned.isdigit():
        return None
    if len(cleaned) > 6:
        return None
    return cleaned.zfill(6)


def normalize_stock_code(raw: str) -> Optional[str]:
    """
    将原始股票代码标准化。

    委托给现有的 StockCodeNormalizer（从 symbol_utils 导入）。
    如果无法识别，返回 None。
    """
    if not raw or not isinstance(raw, str):
        return None

    normalizer = get_normalizer()
    normalized, _, _ = normalizer.normalize(raw.strip())
    return normalized


# ── 中文检测 ──


def contains_chinese(text: str) -> bool:
    """检测字符串是否包含中文字符"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


# ── 业务类型映射辅助 ──


def map_business_type(raw_type: str, mapping: dict) -> Optional[str]:
    """
    根据平台特定的映射字典，将原始业务类型字符串映射为标准枚举。

    Args:
        raw_type: 平台原始类型（如 '买基金'、'活期宝即充即用'）
        mapping: 平台特定映射字典 {原始类型: 标准枚举}

    Returns:
        标准枚举值或 None
    """
    if not raw_type:
        return None
    return mapping.get(raw_type.strip())
