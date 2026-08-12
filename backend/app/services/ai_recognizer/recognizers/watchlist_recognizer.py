# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : watchlist_recognizer.py
"""自选场景识别器：持仓截图 / 粘贴文本 → 基金/股票代码+名称候选。

从旧 `ocr_service.py` 迁入（P2，行为不变）：
- 正则层：`代码 名称` 简单排版零成本提取；
- LLM 层：复杂排版用便宜模型（doubao mini）兜底；
- 反查：catalog.enrich（Securities → 场内代码规则 → Funds → 兜底 + 名称消歧）。
"""

import re
from typing import List

from app.services.ai_recognizer.base import BaseRecognizer, extract_json_array, is_valid_code

_SYSTEM_PROMPT = (
    '你是一个基金/股票代码提取助手。请从用户提供的持仓截图或文本中，'
    '提取所有基金/股票的代码与名称。'
    '只输出 JSON 数组，数组元素为对象：{"code": "6位数字代码", "name": "名称"}。'
    '识别不出名称时 name 可为空字符串。若无有效内容，输出 []。'
    '不要输出任何其他文字或解释。'
)

# 正则提取：6 位数字代码 + 紧随其后的中文/字母名称（2~12 字符）
# 覆盖「代码 名称」的简单排版（如“110011 易方达中小盘”“002910 易方达供给侧改革混合”），
# 名称前有数字（如“买入 xxx 1000元”）时因后跟非中文不匹配，自然落入 LLM 兜底。
_REGEX_ITEM_RE = re.compile(r'(\d{6})\s*([\u4e00-\u9fa5A-Za-z]{2,12})')


class WatchlistRecognizer(BaseRecognizer):
    key = 'watchlist_import'
    feature = 'ocr_import'
    max_items = 30
    system_prompt = _SYSTEM_PROMPT

    # ── 正则层（零成本）──

    def regex_extract(self, text: str) -> List[dict]:
        """简单排版（「代码 名称」）直接出码号+名称，不调 LLM。"""
        items = []
        for m in _REGEX_ITEM_RE.finditer(text):
            code, name = m.group(1), m.group(2)
            if is_valid_code(code):
                items.append({'code': code, 'name': name})
        return items

    # ── LLM 层 ──

    def extract(self, raw: str) -> List[dict]:
        return extract_json_array(raw)

    def validate(self, items: List[dict]) -> List[dict]:
        """清洗识别结果：只保留 6 位数字代码，name 取字符串。"""
        cleaned = []
        for it in items:
            code = str(it.get('code', '') or '').strip()
            name = str(it.get('name', '') or '').strip()
            if is_valid_code(code):
                cleaned.append({'code': code, 'name': name})
        return cleaned
