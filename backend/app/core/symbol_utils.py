# -*- coding: utf-8 -*-
# Author : imoyao
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
from functools import lru_cache
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
            r'^([56]\d{5})$',
            r'^(11[0-9]\d{3})$',  # 沪市可转债：110xxx 到 119xxx
        ],
        'SZ': [
            r'^SZ(\d{6})$',
            r'^(\d{6})\.SZ$',
            r'^([0-3]\d{5})$',  # 0-3开头
            r'^1[0-2]\d{4}$',  # 深市可转债：10xxxx, 11xxxx? 实际深市转债是 12xxxx 系列，但 10xxxx 是深市基金等，暂时保守，优先保证沪市匹配。
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

    # 特殊代码规则（仅用于补充主模式未覆盖的情况）
    # 规则优先级低于主模式，新增时请先检查是否可以加入主模式
    SPECIAL_CODES = [
        # (正则模式, 市场, 资产类型)
        (r'^110\d{3}$', 'SH', 'bond'),  # 沪市可转债（防御性保留，主模式已覆盖）
        (r'^97\d{4}$', 'SH', 'money_fund'),  # 沪市现金管理产品
        (r'^1318\d{2}$', 'SZ', 'reverse_repo'),  # 深市逆回购
        (r'^204\d{3}$', 'SH', 'reverse_repo'),  # 沪市逆回购
        (r'^11[1-9]\d{3}$', 'SZ', 'money_fund'),  # 深市111-119开头基金（排除110开头的沪市转债）
        (r'^12\d{4}$', 'SZ', 'bond'),  # 深市可转债
    ]

    def __init__(self):
        self.compiled_patterns = {
            market: [re.compile(p, re.IGNORECASE) for p in patterns]
            for market, patterns in self.MARKET_PATTERNS.items()
        }
        self.compiled_special_codes = [
            (re.compile(pattern), market, asset_type) for pattern, market, asset_type in self.SPECIAL_CODES
        ]

    @staticmethod
    def _split_normalized(normalized_code: str) -> Tuple[str, str]:
        """将标准化代码拆分为 (市场, 代码)"""
        if ':' in normalized_code:
            parts = normalized_code.split(':', 1)
            return parts[0], parts[1]
        # 紧凑格式：HK00700 -> HK, 00700
        return normalized_code[:2], normalized_code[2:]

    def _match_special_codes(self, code: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """独立的特殊代码匹配方法，返回 (标准化代码, 市场, 资产类型) 或 (None, None, None)"""
        for pattern, market, asset_type in self.compiled_special_codes:
            if pattern.match(code):
                return self._build_normalized(market, code), market, asset_type
        return None, None, None

    def _get_asset_type(self, normalized_code: str) -> Optional[str]:
        """根据标准化代码推断资产类型"""
        if not normalized_code:
            return None

        market, code = self._split_normalized(normalized_code)

        # 沪市资产类型
        if market == 'SH':
            if code.startswith('11'):
                return 'bond'
            if code.startswith(('51', '56', '58')):
                return 'etf'
            if code.startswith('204'):
                return 'reverse_repo'
            if code.startswith('97'):
                return 'money_fund'

        # 深市资产类型
        elif market == 'SZ':
            if code.startswith('12'):
                return 'bond'
            if code.startswith(('15', '16')):
                return 'etf'
            if code.startswith('1318'):
                return 'reverse_repo'
            if code.startswith(('10', '11')):
                return 'money_fund'

        # 北交所、港股、美股、加密货币默认不推断具体类型
        return None

    def to_sina_code(self, normalized_code: str) -> Optional[str]:
        """将标准化代码转为新浪接口需要的格式（sh600519, sz000001）"""
        if not normalized_code:
            return None
        market, code = self._split_normalized(normalized_code)
        if market == 'SH':
            return f'sh{code}'
        elif market == 'SZ':
            return f'sz{code}'
        elif market == 'BJ':
            return f'b{code}'  # 新浪对北交所可能支持有限，先按此转换
        return None

    @lru_cache(maxsize=512)
    def normalize(
        self, code: str, hint_market: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        标准化证券代码

        Args:
            code: 原始证券代码
            hint_market: 可选的市场提示，优先使用该市场的规则匹配

        Returns:
            Tuple[标准化代码, 市场代码, 资产类型]
            资产类型可选值：bond(债券), reverse_repo(逆回购), money_fund(货币基金), stock(股票),
            fund(基金), None(未知/不适用)
        """
        if not isinstance(code, str) or not (code := code.strip().upper()):
            return None, None, None

        # 1. 加密货币特殊处理（避免被 US 模式捕获）
        if hint_market == 'CRYPTO' and re.match(r'^[A-Z]{2,6}$', code):
            return self._build_normalized('CRYPTO', code), 'CRYPTO', None

        # 2. 优先使用 hint_market 的预定义模式匹配（最高优先级）
        if hint_market and hint_market in self.MARKET_CODES:
            for pattern in self.compiled_patterns.get(hint_market, []):
                m = pattern.match(code)
                if m:
                    number_part = m.group(1).replace(':', '')
                    normalized = self._build_normalized(hint_market, number_part)
                    asset_type = self._get_asset_type(normalized)
                    return normalized, hint_market, asset_type
        # 3. 特殊代码识别（必须在主模式之前）
        special_code, special_market, special_asset = self._match_special_codes(code)
        if special_code:
            return special_code, special_market, special_asset

        # 4. 全市场通用模式匹配
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

        # 5. 主模式匹配成功 → 推断资产类型并返回
        if matched_code:
            # 如果 hint 指定了不同市场，尝试用 hint 强制转换覆盖
            if hint_market and hint_market in self.MARKET_CODES and hint_market != matched_market:
                hint_code, hint_mkt = self._force_normalize(code, hint_market)
                if hint_code:
                    asset_type = self._get_asset_type(hint_code)
                    return hint_code, hint_mkt, asset_type
            asset_type = self._get_asset_type(matched_code)
            return matched_code, matched_market, asset_type

        # 6. 仍未匹配 → 尝试 hint 强制转换
        if hint_market and hint_market in self.MARKET_CODES:
            forced_code, forced_market = self._force_normalize(code, hint_market)
            if forced_code:
                asset_type = self._get_asset_type(forced_code)
                return forced_code, forced_market, asset_type

        return None, None, None

    def _force_normalize(self, code: str, market: str) -> Tuple[Optional[str], Optional[str]]:
        """强制转换：数字补齐、字母归类"""
        numbers = re.findall(r'\d+', code)
        if numbers:
            num = numbers[0]
            if market == 'HK' and len(num) <= 5:
                return self._build_normalized('HK', num.zfill(5)), 'HK'
            if market in ('SH', 'SZ', 'BJ') and len(num) <= 6:
                return self._build_normalized(market, num.zfill(6)), market
            # 新增：纯数字代码也可以强制转换为美股/加密货币
            if market in ('US', 'CRYPTO'):
                return self._build_normalized(market, code), market
        # 允许包含字母、数字、点号的组合代码
        if re.match(r'^[A-Z0-9.]+$', code):
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
    ) -> Dict[str, Tuple[Optional[str], Optional[str], Optional[str]]]:
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


def split_symbol(symbol: str) -> tuple[Optional[str], Optional[str]]:
    """SH/SZ/BJ 前缀代码 → (market, code)；纯 6 位数字按首位推断市场；否则 (None, symbol)。

    例如 'SH510050' → ('SH', '510050')、'159915' → ('SZ', '159915')、'110011' → (None, '110011')。
    供录入阶段按代码前缀推断证券细类（ETF/可转债）时拆分市场与代码。
    """
    s = symbol or ''
    if s[:2] in ('SH', 'SZ', 'BJ'):
        return s[:2], s[2:]
    if len(s) == 6 and s.isdigit():
        if s[0] in '69':
            return 'SH', s
        if s[0] in '023':
            return 'SZ', s
    return None, s


def derive_security_type(code: str, market: str | None = None) -> Optional[str]:
    """A 股 6 位代码 → 资产细类 stock/etf/bond；非 A 股 6 位代码返回 None（不动）。

    统一「代码→品类」口径，供证券元数据同步与持仓 asset_type 回填复用：
    - 可转债 bond：沪市 11xxxx（market='SH'）、深市 12xxxx；
    - ETF：沪市 51xxxx/56xxxx/58xxxx、深市 15xxxx/16xxxx；
    - 其余常规 A 股（60xxxx、000/002/300/003、601/603/605、688…）为股票 stock。
    market 用于消除歧义：11xxxx 在沪市为可转债(bond)、深市为货币基金——此时返回 None（不属证券主分类）。
    边界：511xxx 含场内货币ETF（如华宝添益 511990）按 ETF 计；16xxxx/50xxxx 含少量 LOF，
    个人券商账户极罕见，不影响 股票/ETF/可转债 主分类。
    """
    if not code or len(code) != 6 or not code.isdigit():
        return None
    if code[:2] == '11':
        return 'bond' if market == 'SH' else None
    if code[:2] == '12':
        return 'bond'
    if code[:2] in ('51', '56', '58', '15', '16'):
        return 'etf'
    return 'stock'
