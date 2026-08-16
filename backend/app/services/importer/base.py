# -*- coding: utf-8 -*-
"""
导入解析器抽象基类。

- FileParsingMixin：文件读取工具（交易/持仓解析器共享）。
- BaseImportParser：交易流水解析器基类（target='transaction'）。
- BaseHoldingParser：持仓快照解析器基类（target='holding'，#1012）。

所有平台解析器必须继承对应基类并实现 parse() 和 validate()。
"""

import hashlib
import io
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import pandas as pd

from app.services.importer.records import (
    SBImportError,
    StandardHoldingRecord,
    StandardTransactionRecord,
    compute_position_hash,
    compute_record_hash,
)


class FileParsingMixin:
    """文件读取工具 mixin：交易解析器与持仓解析器共享，避免「一个基类扛两种契约」。"""

    # 通用常量
    FAST_ENCODINGS: list = ['utf-8-sig', 'gbk']  # 快速尝试
    FALLBACK_ENCODINGS: list = ['utf-8', 'gb18030']  # 仅在有明确需要时使用
    EXCEL_ENGINES: list = ['openpyxl', 'xlrd']

    def _read_excel(self, file_bytes: bytes, header=0) -> Optional[pd.DataFrame]:
        """尝试将字节流读取为 Excel DataFrame，失败返回 None。

        header 参数透传 pd.read_excel：默认 0（首行为列名，交易解析器用）；
        持仓解析器传 header=None 读取原始行，自行定位表头（E账户文件头部
        可能含标题/个人信息行，表头不固定在第 1 行）。
        """
        for engine in self.EXCEL_ENGINES:
            try:
                df = pd.read_excel(io.BytesIO(file_bytes), engine=engine, header=header)
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


class BaseImportParser(FileParsingMixin, ABC):
    """
    交易流水解析器的抽象基类。

    子类必须实现：
        parse(file_bytes: bytes) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]
        validate(records: List[StandardTransactionRecord]) -> Tuple[List[StandardTransactionRecord], List[SBImportError]]

    子类可选覆盖：
        source: str — 数据来源标识，用于注册表和哈希生成
    """

    source: str = 'unknown'
    target: str = 'transaction'  # 注册表判别：交易解析器

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

    # ── 通用哈希工具 ──

    def compute_import_hash(self, record: StandardTransactionRecord) -> str:
        """为单条交易记录生成去重哈希（委托 records.compute_record_hash，口径统一）。"""
        return compute_record_hash(self.source, record)

    def compute_batch_hash(self, records: List[StandardTransactionRecord]) -> str:
        """
        为整个批次的交易记录生成内容哈希（用于文件级去重）。
        计算所有有效记录的 import_hash 排序拼接后的 MD5。
        """
        valid_hashes = sorted([r.import_hash for r in records if r.import_hash])
        return hashlib.md5('|'.join(valid_hashes).encode()).hexdigest()


class BaseHoldingParser(FileParsingMixin, ABC):
    """
    持仓快照解析器的抽象基类（#1012）。

    与 BaseImportParser（交易）完全并行：parse() 返回 List[StandardHoldingRecord]，
    落库走 PositionService.upsert_from_holding（写持仓、绝不建交易流水）。

    子类必须实现：
        parse(file_bytes: bytes) -> Tuple[List[StandardHoldingRecord], List[SBImportError]]
        validate(records: List[StandardHoldingRecord]) -> Tuple[List[StandardHoldingRecord], List[SBImportError]]

    子类可选覆盖：
        source: str — 数据来源标识（如 'e_account_holding'）
    """

    source: str = 'unknown'
    target: str = 'holding'  # 注册表判别：持仓解析器

    # ── 子类必须实现 ──

    @abstractmethod
    def parse(self, file_bytes: bytes) -> Tuple[List[StandardHoldingRecord], List[SBImportError]]:
        """
        将上传文件的字节内容解析为标准持仓记录列表。

        与交易解析器相同：尽力解析所有行，错误收集到 errors 中返回，不中断解析。
        """

    @abstractmethod
    def validate(self, records: List[StandardHoldingRecord]) -> Tuple[List[StandardHoldingRecord], List[SBImportError]]:
        """
        校验记录列表，过滤不合法数据。

        Args:
            records: parse() 返回的记录列表

        Returns:
            (valid_records, errors)：通过校验的记录和校验失败的错误列表。
        """

    # ── 持仓哈希工具 ──

    def compute_holding_hash(self, record: StandardHoldingRecord) -> str:
        """为单条持仓记录生成去重哈希（委托 records.compute_position_hash，口径统一）。

        注意：ledger_id 在解析阶段可能尚未确定（前端选择目标账户），
        编排器在 enrich 阶段回填 ledger_id 后再调用本方法生成哈希。
        """
        return compute_position_hash(
            source=self.source,
            ledger_id=record.ledger_id or 0,
            symbol=record.symbol,
            snapshot_date=record.snapshot_date,
        )
