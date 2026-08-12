# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : base.py
"""AI 识别域抽象基类（对称模板导入 BaseImportParser 的分层设计）。

模板方法（子类一般不覆盖）：
    recognize_text  文本识别：正则层（零成本）→ LLM 层（便宜模型兜底）→ validate → enrich；
    recognize_image 图片识别：LLM vision → extract → validate → enrich；
    enrich          类型/名称反查（catalog.py），证券/基金表消歧，回填权威名称。

子类必须实现（场景差异点）：
    key / feature / max_items / system_prompt
    regex_extract（正则层；不启用返回 []）
    extract / validate（LLM 输出解析 + 清洗校验，字段集由场景定）

设计原则（ai-recognizer-architecture-2026-08-13.md §3.2）：
AI 识别域只产出候选行，不碰业务表；提交由各业务域负责（自选 → watchlist 域；
持仓 → importer/orchestrator 既有入库管线）。
"""

import json
import re
from abc import ABC, abstractmethod
from typing import List

from loguru import logger

from app.core.exceptions import ErrorCode, SBException
from app.services.ai_recognizer import catalog, llm

CODE6_RE = re.compile(r'\d{6}')
# 图片上限 5MB（识别图片/长文本较慢，超大图会显著拉长耗时与 token 消耗）
OCR_MAX_IMAGE_BYTES = 5 * 1024 * 1024


def extract_json_array(text: str) -> List[dict]:
    """从模型输出中稳健提取 JSON 数组（去掉 markdown 围栏/解释文字）。"""
    if not text:
        return []
    # 去掉 ```json ... ``` 围栏
    fence = re.search(r'```(?:json)?\s*(.*?)```', text, re.S)
    if fence:
        text = fence.group(1)
    # 找到第一个 [ 到最后一个 ] 的片段
    start, end = text.find('['), text.rfind(']')
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning('AI 识别输出 JSON 解析失败: {}; 原文: {}', e, text[:200])
        return []
    return []


def is_valid_code(code: str) -> bool:
    """是否 6 位数字基金/股票代码。"""
    return bool(re.fullmatch(r'\d{6}', str(code or '').strip()))


class BaseRecognizer(ABC):
    """AI 识别器抽象基类。"""

    key: str = 'unknown'  # 注册标识：watchlist_import / txn_import
    feature: str = 'ocr_import'  # 用量表 feature：按场景独立限次
    max_items: int = 30  # 单次最多返回条数（防单次调用爆量）
    system_prompt: str = ''  # 场景化系统指令（约束输出 JSON schema）
    # 识别为空文本/空图片时是否允许走 LLM（子类可按场景收紧）
    allow_empty_text: bool = False
    MAX_TEXT_LEN = 8000  # 文本输入截断长度（防超长 payload）

    # ── 子类必须实现 ──

    @abstractmethod
    def extract(self, raw: str) -> List[dict]:
        """LLM 输出 → 结构化行（JSON 解析 + 字段映射/默认值补齐）。"""

    @abstractmethod
    def validate(self, items: List[dict]) -> List[dict]:
        """清洗校验候选行（代码位数/枚举字段/数值与日期合法性），返回合法行。"""

    # ── 子类可覆盖 ──

    def regex_extract(self, text: str) -> List[dict]:
        """正则层（零成本）：简单排版直接提取，返回 []; 未启用场景直接走 LLM。"""
        return []

    # ── 模板方法（子类不覆盖，通用流程）──

    def recognize_text(self, text: str) -> List[dict]:
        """文本识别：正则层（零成本）→ LLM 层（便宜模型兜底）→ validate → enrich。

        分层策略（用户建议「正则优先，便宜模型兜底」，2026-08-13）：
        1. 正则层：简单排版（「代码 名称」/「代码 名称 买卖 金额」）直接提取，零成本、零延迟；
        2. LLM 层：复杂文本（自然语言夹杂、名称在代码前等）才调便宜模型（默认 mini）。
        """
        if not text or not text.strip():
            raise SBException(code=ErrorCode.INVALID_PARAMS.code, message='文本内容为空', status_code=400)
        # 第 1 层：正则优先（零成本）
        regex_items = self.regex_extract(text)
        if regex_items:
            return self.enrich(regex_items)
        # 第 2 层：便宜模型兜底（复杂排版）
        content = [{'type': 'text', 'text': f'请从以下文本中提取结构化记录：\n\n{text[: self.MAX_TEXT_LEN]}'}]
        raw = llm.call_llm(content, self.system_prompt)
        items = self.validate(self.extract(raw))
        return self.enrich(items)

    def recognize_image(self, image_bytes: bytes, mime: str = 'image/jpeg') -> List[dict]:
        """图片识别：LLM vision（便宜模型）→ extract → validate → enrich。"""
        import base64

        if not image_bytes:
            raise SBException(code=ErrorCode.INVALID_PARAMS.code, message='图片内容为空', status_code=400)
        if len(image_bytes) > OCR_MAX_IMAGE_BYTES:
            raise SBException(
                code=ErrorCode.INVALID_PARAMS.code, message='图片超过 5MB 上限，请压缩后重试', status_code=400
            )
        b64 = base64.b64encode(image_bytes).decode('ascii')
        content = [
            {'type': 'text', 'text': '请识别图片中的所有基金/股票信息。'},
            {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{b64}'}},
        ]
        raw = llm.call_llm(content, self.system_prompt)
        items = self.validate(self.extract(raw))
        return self.enrich(items)

    def enrich(self, items: List[dict]) -> List[dict]:
        """类型/名称反查（catalog.py）：证券/基金表消歧，回填权威名称/type/venue/symbol。"""
        return catalog.enrich(items)
