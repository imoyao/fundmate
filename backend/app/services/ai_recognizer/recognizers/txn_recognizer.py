# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : txn_recognizer.py
"""持仓/交易场景识别器：持仓/交易截图、粘贴文本 → 交易候选行。

字段集比自选场景多：code、name、business_type（买入/卖出/申购/赎回）、
trade_date（申请日）、confirm_date（确认日）、amount、shares、nav、fee。

分层策略（ai-recognizer-architecture-2026-08-13.md §4.2）：
- 正则层：提取「代码 + 买卖词 + 金额」简单排版（代码段可靠，其余字段留给人工核对）；
- LLM 层：复杂文本（自然语言夹杂、名称在代码前等）全字段提取，便宜模型兜底；
- 反查：catalog.enrich 同自选场景（识别标的是基金还是股票 → 决定份额/净值精度）。

约束：日期/金额/份额 AI 可能识别错，前端确认弹窗必须逐行人工核对，不自动入库。
"""

import re
from typing import List, Optional

from app.services.ai_recognizer.base import BaseRecognizer, extract_json_array, is_valid_code
from app.services.ai_recognizer.schemas import TransactionCandidateDict

_SYSTEM_PROMPT = (
    '你是一个基金/股票交易记录识别助手。请从用户提供的持仓或交易截图/文本中，'
    '提取所有交易记录。只输出 JSON 数组，数组元素为对象：'
    '{"code": "6位数字代码", "name": "名称", "business_type": "买入|卖出|申购|赎回|现金分红|红利再投资", '
    '"trade_date": "申请日 YYYY-MM-DD", "confirm_date": "确认日 YYYY-MM-DD（可空）", '
    '"amount": 金额（元，数字）, "shares": 份额/股数（数字）, "nav": 净值/单价（元，数字）, "fee": 手续费（元，数字）}。'
    '识别不出的字段用 null 或空字符串。若无有效交易记录，输出 []。'
    '不要输出任何其他文字或解释。'
)

# 中文交易词 → importer 内部编码（与 mappings.BusinessType 对齐）
_OP_SYNONYMS = {
    '买入': 'buy',
    '买': 'buy',
    '申购': 'buy',
    '认购': 'buy',
    '买入(申购)': 'buy',
    '买入（申购）': 'buy',
    '卖出': 'sell',
    '卖': 'sell',
    '赎回': 'sell',
    '赎回(卖出)': 'sell',
    '赎回（卖出）': 'sell',
    '现金分红': 'dividend_cash',
    '红利再投资': 'dividend_reinvest',
}
_VALID_OP_CODES = {'buy', 'sell', 'dividend_cash', 'dividend_reinvest'}

# 简单排版：代码 → 可选名称 → 买卖词 → 金额
# 覆盖「110011 易方达中小盘 买入 10000」「600519 贵州茅台 卖出 100股」这类行；
# 名称在代码前 / 夹杂自然语言时正则不匹配，自然落入 LLM 兜底。
_REGEX_TXN_RE = re.compile(
    r'(?P<code>\d{6})'
    r'(?:[^\d]{1,40}?(?P<name>[\u4e00-\u9fa5A-Za-z]{2,12}))?'
    r'[^\d]{0,20}?(?P<action>买入|卖出|申购|赎回|认购)'
    r'[^\d]{0,40}?(?P<amount>\d+(?:\.\d+)?)'
)
_DATE_RE = re.compile(r'(\d{4})-(\d{1,2})-(\d{1,2})')


def _salvage_date(value: str, field: str, warnings: list) -> str:
    """从 LLM 输出中抢救日期（YYYY-MM-DD，容忍 / 或 年月日 混排），非法则清空。"""
    if not value:
        return ''
    text = str(value).strip()
    m = _DATE_RE.search(text)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f'{year:04d}-{month:02d}-{day:02d}'
    text_slash = text.replace('/', '-')
    m = _DATE_RE.search(text_slash)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return f'{year:04d}-{month:02d}-{day:02d}'
    warnings.append(f'{field} 无法识别为日期，已清空，请人工补填')
    return ''


def _to_positive_float(value, field: str, warnings: list) -> Optional[float]:
    """数值化（元/份原始单位），非法/非正数返回 None（不得篡改为 0）。"""
    if value is None or value == '':
        return None
    try:
        num = float(str(value).replace(',', '').replace('，', ''))
    except (TypeError, ValueError):
        warnings.append(f'{field} 无法识别为数字，已清空，请人工补填')
        return None
    if num <= 0:
        warnings.append(f'{field} 需为正数，已清空，请人工补填')
        return None
    return round(num, 6)


class TxnRecognizer(BaseRecognizer):
    key = 'txn_import'
    feature = 'txn_import'
    max_items = 30
    system_prompt = _SYSTEM_PROMPT

    # ── 正则层（零成本）──

    def regex_extract(self, text: str) -> List[TransactionCandidateDict]:
        """简单排版（「代码 名称? 买卖 金额」）直接出候选行，不调 LLM。

        注意：正则行只保证代码/买卖/金额三个字段可靠；日期与份额需人工核对，
        且「名称在代码前」等复杂排版自然落入 LLM 兜底。
        """
        items = []
        for m in _REGEX_TXN_RE.finditer(text):
            code = m.group('code')
            if not is_valid_code(code):
                continue
            action = m.group('action')
            op_code = _OP_SYNONYMS.get(action, 'buy')
            items.append(
                {
                    'code': code,
                    'name': (m.group('name') or '').strip(),
                    'business_type': op_code,
                    'trade_date': '',
                    'confirm_date': '',
                    'amount': float(m.group('amount')),
                    'shares': None,
                    'nav': None,
                    'fee': 0.0,
                }
            )
        return items

    # ── LLM 层 ──

    def extract(self, raw: str) -> List[TransactionCandidateDict]:
        """LLM 输出 → 结构化行：中文买卖词归一为内部编码、数值/日期容错。"""
        rows = extract_json_array(raw)
        items = []
        for it in rows:
            code = str(it.get('code', '') or '').strip()
            name = str(it.get('name', '') or '').strip()
            raw_op = str(it.get('business_type', '') or '').strip()
            op_code = _OP_SYNONYMS.get(raw_op, _OP_SYNONYMS.get(raw_op.replace(' ', ''), '')) or ''
            warnings = []
            trade_date = _salvage_date(it.get('trade_date'), '申请日', warnings)
            confirm_date = _salvage_date(it.get('confirm_date'), '确认日', warnings)
            items.append(
                {
                    'code': code,
                    'name': name,
                    'business_type': op_code,
                    'trade_date': trade_date,
                    'confirm_date': confirm_date,
                    'amount': _to_positive_float(it.get('amount'), '金额', warnings),
                    'shares': _to_positive_float(it.get('shares'), '份额', warnings),
                    'nav': _to_positive_float(it.get('nav'), '净值', warnings),
                    'fee': _to_positive_float(it.get('fee'), '手续费', warnings) or 0.0,
                    'warnings': warnings,
                }
            )
        return items

    def validate(self, items: List[dict]) -> List[TransactionCandidateDict]:
        """清洗校验候选行。

        保留规则：代码 6 位 + 买卖类型在枚举内 + 至少金额或份额其一有效；
        日期缺省允许（前端预览表格人工补填，见「必须人工确认」约束）。
        """
        cleaned = []
        for it in items:
            code = str(it.get('code', '') or '').strip()
            if not is_valid_code(code):
                continue
            op_code = str(it.get('business_type', '') or '').strip()
            if op_code not in _VALID_OP_CODES:
                op_code = ''
            if not op_code:
                continue
            amount = it.get('amount')
            shares = it.get('shares')
            # 至少金额或份额其一有效（否则不是一笔可入账交易）
            if (not amount or amount <= 0) and (not shares or shares <= 0):
                continue
            cleaned.append(
                {
                    'code': code,
                    'name': str(it.get('name', '') or '').strip(),
                    'business_type': op_code,
                    'trade_date': it.get('trade_date', '') or '',
                    'confirm_date': it.get('confirm_date', '') or '',
                    'amount': amount,
                    'shares': shares,
                    'nav': it.get('nav'),
                    'fee': float(it.get('fee') or 0),
                    'warnings': it.get('warnings') or [],
                }
            )
        return cleaned
