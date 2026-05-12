# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 22:01
# File : symbol_utils.py
"""
证券代码标准化工具
支持的输入格式：
  - 港股: HK00700, 00700.HK, 00700, 700, hk700
  - A股沪市: SH600519, 600519.SH, 600519, 510050 (ETF)
  - A股深市: SZ000001, 000001.SZ, 000001, 300750 (创业板)
  - 北交所: BJ920185, 920185.BJ, 920185
  - 美股: AAPL, AAPL.US, US:AAPL, BRK.B, BRK.B.US
  - 加密货币: BTC (需要 market_hint='CRYPTO')
数据库存储统一格式: {MARKET}{CODE} 或 {MARKET}:{CODE}
"""

import re
from typing import Dict, Optional, Tuple


class StockCodeNormalizer:
    """中国及全球证券代码标准化器"""

    MARKET_CODES = {
        'HK': '港股',
        'SH': '上交所',
        'SZ': '深交所',
        'BJ': '北交所',
        'US': '美股',
        'CRYPTO': '加密货币',
    }

    MARKET_PATTERNS = {
        'HK': [r'^HK(\d{1,5})$', r'^(\d{1,5})\.HK$', r'^(\d{1,5})$'],
        'SH': [
            r'^SH(\d{6})$',
            r'^(\d{6})\.SH$',
            r'^(\d{6})\.SS$',
            r'^([56]\d{5})$',  # 5或6开头的6位纯数字
        ],
        'SZ': [
            r'^SZ(\d{6})$',
            r'^(\d{6})\.SZ$',
            r'^([0-3]\d{5})$',  # 0-3开头的6位纯数字
        ],
        'BJ': [
            r'^BJ(\d{6})$',
            r'^(\d{6})\.BJ$',
            r'^([89]\d{5})$',  # 8或9开头的6位纯数字
        ],
        'US': [
            r'^US:(\S+)$',
            r'^([A-Z]{1,10})(?:\.(?:US|NYSE|NASDAQ|AMEX|OTC))$',  # 带交易所后缀
            r'^([A-Z]{1,10}(?:\.[A-Z]{1,10})?)$',  # 无后缀，允许代码内含点号（如BRK.B）
        ],
        'CRYPTO': [
            r'^CRYPTO:(\S+)$',  # 已标准化的格式
        ],
    }

    def __init__(self):
        self.compiled_patterns = {
            market: [re.compile(p, re.IGNORECASE) for p in patterns]
            for market, patterns in self.MARKET_PATTERNS.items()
        }

    @staticmethod
    def _split_normalized(normalized_code: str) -> Tuple[str, str]:
        """将标准化代码拆分为 (市场, 代码)"""
        if ':' in normalized_code:
            parts = normalized_code.split(':', 1)
            return parts[0], parts[1]
        # 紧凑格式：HK00700 -> HK, 00700
        return normalized_code[:2], normalized_code[2:]

    def normalize(self, code: str, hint_market: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        if not isinstance(code, str) or not (code := code.strip().upper()):
            return None, None

        # 0. 加密货币特殊处理（避免被 US 模式捕获）
        if hint_market == 'CRYPTO' and re.match(r'^[A-Z]{2,6}$', code):
            return self._build_normalized('CRYPTO', code), 'CRYPTO'

        # 1. 优先使用 hint_market 的预定义模式匹配
        if hint_market and hint_market in self.MARKET_CODES:
            for pattern in self.compiled_patterns.get(hint_market, []):
                m = pattern.match(code)
                if m:
                    number_part = m.group(1).replace(':', '')
                    return self._build_normalized(hint_market, number_part), hint_market

        # 2. 常规匹配
        matched_market = None
        matched_code = None
        for market, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                m = pattern.match(code)
                if m:
                    number_part = m.group(1).replace(':', '')
                    matched_code = self._build_normalized(market, number_part)
                    matched_market = market
                    break
            if matched_code:
                break

        # 3. 如果 hint 指定了不同市场，尝试用 hint 强制转换覆盖
        if matched_code and hint_market and hint_market in self.MARKET_CODES and hint_market != matched_market:
            hint_code, hint_mkt = self._force_normalize(code, hint_market)
            if hint_code:
                return hint_code, hint_mkt
        elif matched_code:
            return matched_code, matched_market

        # 4. 未匹配任何模式，尝试 hint 强制转换
        if hint_market and hint_market in self.MARKET_CODES:
            forced_code, forced_market = self._force_normalize(code, hint_market)
            if forced_code:
                return forced_code, forced_market

        return None, None

    def _force_normalize(self, code: str, market: str) -> Tuple[Optional[str], Optional[str]]:
        """强制转换：数字补齐、字母归类"""
        numbers = re.findall(r'\d+', code)
        if numbers:
            num = numbers[0]
            if market == 'HK' and len(num) <= 5:
                return self._build_normalized('HK', num.zfill(5)), 'HK'
            if market in ('SH', 'SZ', 'BJ') and len(num) <= 6:
                return self._build_normalized(market, num.zfill(6)), market
        if re.match(r'^[A-Z]+$', code):
            if market in ('US', 'CRYPTO'):
                return self._build_normalized(market, code), market
        return None, None

    def _build_normalized(self, market: str, code: str) -> str:
        """根据市场构建标准化字符串"""
        if market in ('US', 'CRYPTO'):
            return f'{market}:{code}'
        if market == 'HK':
            return f'HK{code.zfill(5)}'
        else:  # SH, SZ, BJ
            return f'{market}{code.zfill(6)}'

    def normalize_batch(
        self, codes: list, hint_market: Optional[str] = None
    ) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        return {code: self.normalize(code, hint_market) for code in codes}

    def to_xalpha_code(self, normalized_code: str) -> Optional[str]:
        if not normalized_code:
            return None
        market, code = self._split_normalized(normalized_code)
        if market == 'HK':
            return f'HK{code}'
        if market in ('SH', 'SZ', 'BJ'):
            return f'{market}{code}'
        # 美股、加密货币直接用代码
        return code

    def to_display_code(self, normalized_code: str) -> Optional[str]:
        """友好的展示格式"""
        if not normalized_code:
            return None
        market, code = self._split_normalized(normalized_code)
        if market == 'HK':
            return f'{code}.HK'
        if market in ('SH', 'SZ', 'BJ'):
            return code
        return code  # US, CRYPTO

    def to_akshare_code(self, normalized_code: str) -> Optional[str]:
        """AKShare 的输入格式（纯数字或原始代码）"""
        if not normalized_code:
            return None
        _, code = self._split_normalized(normalized_code)
        return code

    def get_market_name(self, market_code: str) -> Optional[str]:
        return self.MARKET_CODES.get(market_code)


# 全局单例
_normalizer = StockCodeNormalizer()


def get_normalizer() -> StockCodeNormalizer:
    return _normalizer
