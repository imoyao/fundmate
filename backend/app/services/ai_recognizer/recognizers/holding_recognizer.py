# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/23
# File : holding_recognizer.py
"""持仓场景识别器：持仓截图 / 粘贴文本 → 持仓候选（代码/名称/份额/成本/市值/快照日）。

从旧 ocr_service.py 迁入的「自选识别」范式扩展而来，与 txn_import 完全独立：
本识别器只产出「持仓」，绝不产出交易流水。提交阶段由 OCR 端点路由到
ImportOrchestrator.preview_holding_records / commit_holdings，而非
process_buy_or_deposit，从而修复 #1018（AI 持仓识别误经交易管线建流水）。
"""

import re
from datetime import datetime
from typing import List

from app.services.ai_recognizer.base import BaseRecognizer, extract_json_array, is_valid_code
from app.services.ai_recognizer.schemas import HoldingCandidateDict

_SYSTEM_PROMPT = (
    '你是一个基金/股票持仓提取助手。请从用户提供的持仓截图或文本中，'
    '提取每一项持仓。只输出 JSON 数组，数组元素为对象：'
    '{"code": "6 位数字代码", "name": "名称", "shares": 份额或股数(数字), '
    '"avg_cost": 单位成本价(元, 数字), "market_value": 当前市值(元, 数字), '
    '"snapshot_date": "快照日期 YYYY-MM-DD(可选)"}。'
    'shares 与 market_value 至少其一为正数；识别不出名称时 name 可为空字符串；'
    '无快照日时 snapshot_date 可为空字符串。若无有效持仓，输出 []。'
    '不要输出任何其他文字或解释。'
)

# 日期宽松匹配：2026-08-23 / 2026/8/23 / 2026年8月23日
_DATE_RE = re.compile(r'(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})')


def _parse_date(s: str):
    if not s:
        return None
    m = _DATE_RE.search(str(s))
    if not m:
        return None
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
    except ValueError:
        return None


class HoldingRecognizer(BaseRecognizer):
    key = 'holding_import'
    feature = 'holding_import'
    max_items = 50
    system_prompt = _SYSTEM_PROMPT

    # ── 正则层 ──
    # 持仓含份额/成本/市值等多字段，正则无法稳定提取，直接交给 LLM 兜底。

    def regex_extract(self, text: str) -> List[HoldingCandidateDict]:
        return []

    # ── LLM 层 ──

    def extract(self, raw: str) -> List[HoldingCandidateDict]:
        return extract_json_array(raw)

    def validate(self, items: List[HoldingCandidateDict]) -> List[HoldingCandidateDict]:
        """清洗识别结果：仅保留有效代码，且 shares / market_value 至少其一为正。

        保留 enrich 阶段回填的 symbol / asset_type（用于落库与反查）。
        """
        cleaned = []
        for it in items:
            code = str(it.get('code', '') or '').strip()
            if not is_valid_code(code):
                continue
            try:
                shares = float(it.get('shares') or 0)
            except (TypeError, ValueError):
                shares = 0.0
            try:
                avg_cost = float(it.get('avg_cost') or 0)
            except (TypeError, ValueError):
                avg_cost = 0.0
            try:
                market_value = float(it.get('market_value') or 0)
            except (TypeError, ValueError):
                market_value = 0.0
            if shares <= 0 and market_value <= 0:
                continue
            name = str(it.get('name', '') or '').strip()
            snapshot_date = _parse_date(str(it.get('snapshot_date', '') or ''))
            cleaned.append(
                {
                    'code': code,
                    'symbol': it.get('symbol') or code,
                    'asset_type': it.get('asset_type') or '',
                    'name': name,
                    'shares': shares,
                    'avg_cost': avg_cost,
                    'market_value': market_value,
                    'snapshot_date': snapshot_date.isoformat() if snapshot_date else '',
                }
            )
        return cleaned
