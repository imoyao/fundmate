# -*- coding: utf-8 -*-
"""
导入解析器抽象基类。

所有平台解析器必须继承此类并实现 parse() 和 validate()。
基类提供文件读取工具方法、编码常量等通用能力。
"""

import hashlib
import io
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import pandas as pd

from app.services.importer.records import SBImportError, StandardTransactionRecord


class BaseImportParser(ABC):
    """
    所有导入解析器的抽象基类。

    子类必须实现：
        parse(file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]
        validate(records: List[StandardTransactionRecord]) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]

    子类可选覆盖：
        source: str — 数据来源标识，用于注册表和哈希生成
    """

    source: str = 'unknown'

    # 通用常量
    FAST_ENCODINGS: list = ['utf-8-sig', 'gbk']  # 快速尝试
    FALLBACK_ENCODINGS: list = ['utf-8', 'gb18030']  # 仅在有明确需要时使用
    EXCEL_ENGINES: list = ['openpyxl', 'xlrd']

    # ── 子类必须实现 ──

    @abstractmethod
    def parse(self, file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """
        将上传文件的字节内容解析为标准交易记录列表。

        Args:
            file_bytes: 上传文件的原始字节

        Returns:
            (records, errors)：成功解析的记录和解析失败的错误列表。
            注意：parse 应该尽力解析所有行，即使某些行有错误也要继续，
            将所有错误收集到 errors 中返回，不中断解析。
        """

    @abstractmethod
    def validate(
        self, records: List[StandardTransactionRecord]
    ) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]:
        """
        校验记录列表，过滤不合法数据。

        Args:
            records: parse() 返回的记录列表

        Returns:
            (valid_records, errors)：通过校验的记录和校验失败的错误列表。
        """

    # ── 文件读取工具方法 ──

    def _read_excel(self, file_bytes: bytes) -> Optional[pd.DataFrame]:
        """尝试将字节流读取为 Excel DataFrame，失败返回 None"""
        for engine in self.EXCEL_ENGINES:
            try:
                df = pd.read_excel(io.BytesIO(file_bytes), engine=engine)
                if df is not None and not df.empty:
                    return df
            except Exception:
                continue
        return None

    def _read_csv(
        self, file_bytes: bytes, sep: str = ',', encodings: Optional[List[str]] = None, **kwargs
    ) -> Optional[pd.DataFrame]:
        """
        尝试将字节流读取为 CSV DataFrame，支持多编码尝试。

        Args:
            file_bytes: 文件字节流
            sep: 分隔符
            encodings: 编码尝试列表，默认使用 self.FAST_ENCODINGS
            **kwargs: 传递给 pd.read_csv 的额外参数

        Returns:
            成功读取的 DataFrame，或 None
        """
        if encodings is None:
            encodings = self.FAST_ENCODINGS
        for enc in encodings:
            try:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep=sep,
                    encoding=enc,
                    encoding_errors='ignore',
                    **kwargs,
                )
                if df is not None and not df.empty:
                    df.columns = df.columns.str.strip()
                    return df
            except Exception:
                continue
        return None

    def _decode_bytes(self, file_bytes: bytes) -> Optional[str]:
        """
        尝试将字节流解码为字符串，支持多编码。
        返回成功解码的字符串，或 None。
        """
        for encoding in self.FAST_ENCODINGS:
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return None

    # ── 通用哈希工具 ──

    def compute_import_hash(self, record: StandardTransactionRecord) -> str:
        """
        为单条交易记录生成去重哈希。

        规则：
            - 有平台交易流水号时：f"{source}|{transaction_id}"
            - 无流水号时：f"{source}|{confirm_date}|{symbol}|{business_type}|{quantity}|{price}"

        注意：不包含 amount，因为不同平台对金额的四舍五入处理不同。
        """
        if record.transaction_id:
            raw = f'{self.source}|{record.transaction_id}'
        else:
            shares_str = f'{float(record.shares):.4f}' if record.shares else '0'
            nav_str = f'{float(record.nav):.4f}' if record.nav else '0'
            raw = (
                f'{self.source}|{record.confirm_date.isoformat()}|{record.symbol}|'
                f'{record.business_type}|{shares_str}|{nav_str}'
            )
        return hashlib.md5(raw.encode()).hexdigest()

    def compute_batch_hash(self, records: List[StandardTransactionRecord]) -> str:
        """
        为整个批次的交易记录生成内容哈希（用于文件级去重）。
        计算所有有效记录的 import_hash 排序拼接后的 MD5。
        """
        valid_hashes = sorted([r.import_hash for r in records if r.import_hash])
        return hashlib.md5('|'.join(valid_hashes).encode()).hexdigest()
