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
数据库存储约定（按 venue 分述，唯一权威定义见 core/venues.py，禁止各模块自行拼/剥前缀）：
  - 场内 EXCHANGE: {MARKET}{CODE}（如 SH600519）或 {MARKET}:{CODE}（如美股 US:AAPL）；
  - 场外基金 OTC : 裸 6 位码（如 004369），**不带交易所前缀**（#1662）。
    场外基金代码与交易所代码段共用同一数字空间，带前缀即误判市场。
"""

import re
from functools import lru_cache
from typing import Dict, Optional, Tuple

from loguru import logger

# 交易场所唯一权威定义（#1662）：归一化器不得猜 venue，必须由调用方显式传入。
from app.core.venues import NO_VENUE, OTC, normalize_venue, venue_of_row


def strip_exchange_prefix(symbol: str) -> str:
    """剥掉**已存在**的交易所前缀 / 后缀（`SZ004369` → `004369`、`510300.SH` → `510300`）。

    只做「去前缀」，**不做任何交易所推断**（那是 `market_of_cn_a_code` 的职责）。
    场外（OTC）的存储约定是裸码，故 OTC 归一化必须调用它 —— 否则已经带前缀的脏输入
    （如历史库里误存的 `SZ004369`）会被原样写回去，永远清不掉。
    """
    s = (symbol or '').strip().upper()
    if len(s) > 6 and s[:2] in ('SH', 'SZ', 'BJ'):
        s = s[2:]
    elif len(s) > 7 and s[-3] == '.':
        s = s[:-3]
    # 分隔符表达：SH.004369 / SH:004369 / 004369.SH
    return s.strip('.:')


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
    #
    # ⚠️ 裸 6 位数字不许在此按「基金段」归类（#1661 已删除 `^11[1-9]\d{3}$ → SZ/money_fund`）：
    # 11xxxx 在沪市是**可转债**、在深市才是货币基金，`market_of_cn_a_code()` 已把它判为 SH；
    # 那条规则抢在主模式之前把 111xxx/113xxx/118xxx 沪市转债发成 `SZ…` + `money_fund`
    # （实测 10 只沪市转债样本误判 7 只），并与同文件的 `derive_security_type()` 自相矛盾。
    # 深市 111xxx 基金请走带前缀的 `SZ111xxx`（主模式已覆盖）。
    SPECIAL_CODES = [
        # (正则模式, 市场, 资产类型)
        (r'^110\d{3}$', 'SH', 'bond'),  # 沪市可转债（防御性保留，主模式已覆盖）
        (r'^97\d{4}$', 'SH', 'money_fund'),  # 沪市现金管理产品
        (r'^1318\d{2}$', 'SZ', 'reverse_repo'),  # 深市逆回购
        (r'^204\d{3}$', 'SH', 'reverse_repo'),  # 沪市逆回购
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
        self, code: str, hint_market: Optional[str] = None, venue: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        标准化证券代码

        Args:
            code: 原始证券代码
            hint_market: 可选的市场提示，优先使用该市场的规则匹配
            venue: 可选交易场所（`core/venues.EXCHANGE` / `OTC`）。**#1662 显式化**：
                传 `OTC` 时**不做任何交易所推断**，只去空白 / 转大写 / 剥掉可能已存在的
                交易所前缀（场外约定为裸码），返回结果与输入是否带前缀无关（幂等）；
                场外基金代码与交易所代码段共用同一数字空间（`004369` 会被推成
                `SZ004369` → 深市股票、`121011` → 深市可转债），推断必然误判。
                只有 `EXCHANGE` 才走下方的市场推断。

        Returns:
            Tuple[标准化代码, 市场代码, 资产类型]
            资产类型可选值：bond(债券), reverse_repo(逆回购), money_fund(货币基金), stock(股票),
            fund(基金), None(未知/不适用)
        """
        if not isinstance(code, str) or not (code := code.strip().upper()):
            return None, None, None

        # 0. 场外（OTC）：原样返回，**禁止**推断交易所（#1662）。
        #    此处短路在全部模式匹配之前 —— 一旦落到下方主模式，`004369` 会被
        #    `^([0-3]\d{5})$` 判成 SZ、`121011` 会被 SPECIAL_CODES 判成深市可转债。
        #    market 固定 "CN_A"（场外基金有市场归属、无交易所归属，与 watchlist 同口径）。
        if venue == OTC:
            return strip_exchange_prefix(code), 'CN_A', None

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
        self, codes: list, hint_market: Optional[str] = None, venue: Optional[str] = None
    ) -> Dict[str, Tuple[Optional[str], Optional[str], Optional[str]]]:
        return {code: self.normalize(code, hint_market, venue) for code in codes}

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


def normalize_by_venue(symbol: str, venue: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """按**交易场所**归一 symbol —— 落库前唯一应走的入口（#1662）。

    - `EXCHANGE`：交给归一化器推断交易所并加前缀（`600519` → `SH600519`、`159915` → `SZ159915`）；
    - `OTC`     ：剥掉可能已存在的交易所前缀后返回（场外约定为裸码，故 `SZ004369` 与
      `004369` 归一到同一个 `004369`），**绝不推断交易所**（见 `core/venues` 的说明）；
    - 推断失败（EXCHANGE 下无法解析）时不猜也不丢：保留原值 + 告警，
      由 `scripts/audit_symbol_venue_conformance.py` 暴露出来人工确认。

    返回 `(归一后的 symbol, market, asset_type)`；空输入返回 `('', None, None)`。
    venue 非法时抛 `ValueError`（宁可报错，也不要落一个错形态的 symbol）。
    """
    s = (symbol or '').strip()
    if not s:
        return '', None, None
    resolved = normalize_venue(venue)
    if resolved == OTC:
        return strip_exchange_prefix(s), 'CN_A', None
    normalized, market, asset_type = _normalizer.normalize(s, venue=resolved)
    if not normalized:
        logger.warning(f'EXCHANGE 归一失败，保留原值待人工确认: {s!r}')
        return s.upper(), None, None
    return normalized, market, asset_type


def symbol_identity(symbol: str, asset_type: str | None = None, venue: str | None = None) -> str:
    """归一**身份键**（落 `positions.symbol_norm`）：`{VENUE}:{venue 规范形态的代码}`（#1662 后续）。

    为什么要有它：`positions` 的唯一约束过去是**字面量** `UNIQUE(ledger_id, symbol)`，
    挡不住「同一标的的写法变体」—— `SZ004369` / `sz004369` / ` SZ004369 ` / `SH.004369`
    在 SQLite 里是四个不同字符串，同一只基金就能长出四行（#1662 本机实测 2 组）。
    本函数把一行数据映射到它的**身份**，唯一约束改挂身份而非字面量。

    形态：

        EXCHANGE → `EXCHANGE:SZ159915`（场内，规范化后的 {MARKET}{CODE}）
        OTC      → `OTC:004369`（场外，裸 6 位码）
        NO_VENUE → `NO_VENUE:MGR_xxx`（无交易场所实体：经理 / 投顾组合 / 指数）

    venue 来源（优先级，与 `scripts/audit_symbol_venue_conformance.py` 同口径，
    两者共用 `core.venues.venue_of_row`）：显式 `venue` 参数 > `asset_type` 推断
    （含场内货基 `SH97xxxx` 特例）。**这里不做任何市场推断**，`EXCHANGE` 下的
    `{MARKET}` 前缀由 `normalize_by_venue` 负责（那是它的职责，见 core/venues）。

    `asset_type` 是必需的第二入参而不是可选项：`SH970164`（场内货基）与 `970164`
    （场外货基）**代码段相同、场所不同**，只看 symbol 无法区分 —— 而 #1665 起
    写入侧已强制按 venue 落形态，故库内形态与 asset_type 的组合能唯一确定身份。

    空 symbol 返回空串（不落 `NO_VENUE:`，避免一堆空行撞唯一约束）。
    """
    s = (symbol or '').strip().upper()
    if not s:
        return ''
    resolved = venue_of_row(s, asset_type, venue)
    code = strip_exchange_prefix(s) if resolved == OTC else s
    if resolved == OTC:
        # 场外形态即裸码，剥前缀后无需再过归一化器（OTC 下 market 恒 CN_A）
        return f'{OTC}:{code}'
    if resolved == NO_VENUE:
        return f'NO_VENUE:{code}'
    # 场内：走一次归一化拿到规范 {MARKET}{CODE}（`600519` → `SH600519`、`sh600519` → `SH600519`），
    # 失败则保留原值（与 normalize_by_venue 的「不猜也不丢」同策略）
    normalized, _market, _asset_type = normalize_by_venue(s, resolved)
    return f'{resolved}:{normalized or code}'


def split_symbol(symbol: str) -> tuple[Optional[str], Optional[str]]:
    """SH/SZ/BJ 前缀代码 → (market, code)；纯 6 位数字按「A 股代码段」推断市场；否则 (None, symbol)。

    例如 'SH510050' → ('SH', '510050')、'159915' → ('SZ', '159915')、'110011' → ('SH', '110011')。
    供录入阶段按代码前缀推断证券细类（ETF/可转债）时拆分市场与代码。

    纯数字部分统一走 `market_of_cn_a_code`（与 securities 名录同步同一口径）——
    原先只认「6/9 → SH、0/2/3 → SZ」，导致 5xxxxx（沪 ETF）、15xxxx/16xxxx（深 ETF）、
    11xxxx（沪转债）一律判不出市场，进而 `derive_security_type` 也定不了类（#1104）。
    """
    s = symbol or ''
    if s[:2] in ('SH', 'SZ', 'BJ'):
        return s[:2], s[2:]
    if len(s) == 6 and s.isdigit():
        return market_of_cn_a_code(s), s
    return None, s


def market_of_cn_a_code(code: str) -> Optional[str]:
    """A 股 6 位代码 → 交易所（SH / SZ / BJ）；非 A 股 6 位代码返回 None。

    为什么必须单独有它（#1104）：品种细类的判定离不开市场——11xxxx 在沪市是**可转债**、
    在深市是**货币基金**，只看代码前缀无从区分（见 `derive_security_type` 的 market 参数）。
    securities 名录补齐时，ETF（5xxxxx / 15xxxx / 16xxxx）与可转债（11xxxx / 12xxxx）
    全靠本函数先定市场，否则持仓/自选里的 `SZ159857` 永远对不上证券名录，
    price_history 任务会在 `_get_security_map` 一步静默跳过。
    """
    if not code or len(code) != 6 or not code.isdigit():
        return None
    if code[:2] == '11':  # 沪市可转债 110xxx~119xxx
        return 'SH'
    if code[:2] == '12':  # 深市可转债 123xxx/127xxx/128xxx
        return 'SZ'
    if code[:2] in ('15', '16'):  # 深市 ETF / LOF
        return 'SZ'
    if code[0] == '5':  # 沪市 ETF / LOF：51xxxx / 56xxxx / 58xxxx
        return 'SH'
    if code[:3] == '920':  # 北交所新号段（920xxx），须先于「9 开头 → 沪市」判定
        return 'BJ'
    if code[0] in '69':
        return 'SH'
    if code[0] in '023':
        return 'SZ'
    if code[0] == '8':
        return 'BJ'
    return None


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
