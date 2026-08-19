# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/31 23:31
# File : registry.py
# -*- coding: utf-8 -*-
"""
解析器注册表。

新增平台只需在此注册一行映射，无需修改其他代码。

交易/持仓双轨（#1012）：
- 交易解析器（target='transaction'）：parse 输出 StandardTransactionRecord，落 transactions；
- 持仓解析器（target='holding'）：parse 输出 StandardHoldingRecord，落 positions（不建流水）。
get_parser 返回任意解析器；get_holding_parser 只返回持仓解析器，编排器据此分叉。
"""

from app.core.constants import PositionSource
from app.services.importer.base import BaseHoldingParser, BaseImportParser
from app.services.importer.parsers.alipay_fund import AlipayFundParser
from app.services.importer.parsers.alipay_pdf import AlipayPDFParser
from app.services.importer.parsers.e_account_holding import EAccountHoldingParser
from app.services.importer.parsers.standard import FundStandardParser, StockStandardParser
from app.services.importer.parsers.ths_stock import THSStockParser
from app.services.importer.parsers.tiantian_fund import TiantianFundParser

# source → 解析器实例
PARSER_REGISTRY: dict[str, BaseImportParser] = {}


def register_parser(source: str, parser: BaseImportParser) -> None:
    """注册一个解析器"""
    PARSER_REGISTRY[source] = parser


def get_parser(source: str) -> BaseImportParser | None:
    """根据 source 获取解析器实例"""
    return PARSER_REGISTRY.get(source)


def get_holding_parser(source: str) -> BaseHoldingParser | None:
    """根据 source 获取持仓解析器实例（target='holding'），非持仓解析器返回 None。"""
    parser = PARSER_REGISTRY.get(source)
    if parser is not None and getattr(parser, 'target', 'transaction') == 'holding':
        return parser
    return None


def get_all_sources() -> list[str]:
    """返回所有已注册的 source 列表（供前端动态获取平台列表）"""
    return list(PARSER_REGISTRY.keys())


# 默认注册标准模板解析器
register_parser('standard_fund', FundStandardParser())
register_parser('standard', StockStandardParser())
register_parser('standard_stock', StockStandardParser())
register_parser('ths_stock', THSStockParser())
register_parser('ths', THSStockParser())  # 兼容旧前端参数
register_parser('tiantian_fund', TiantianFundParser())
register_parser('alipay_fund', AlipayFundParser())
register_parser('alipay_pdf', AlipayPDFParser())
# 持仓解析器（#1012）
register_parser(PositionSource.E_ACCOUNT.value, EAccountHoldingParser())
