# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : ocr_service.py
"""OCR 截图导入 / AI 批量导入服务（火山方舟 doubao 全模态）。

技术决策（见 explore-watchlist-enhancement-2026-08-12.md §6）：
- OCR 引擎走火山方舟 OpenAI 兼容端点，纯 HTTP 调用，零本地依赖（否决前端 tesseract / 本地 PaddleOCR）。
- 一次调用同时完成「图像理解 + 结构化 JSON 提取」，前端只传图 + 展示结果。
- 用量经 `user_usage` 表按 (user_id, feature, period_date) 限次（免费 5 次/天）。

调用示例：
    https://ark.cn-beijing.volces.com/api/v3/chat/completions
    Authorization: Bearer <ARK_API_KEY>
"""

import base64
import json
import os
import re
import time
from datetime import date
from typing import List, Optional

import requests
from dotenv import load_dotenv
from loguru import logger

from app.core.database import SessionLocal
from app.core.exceptions import ErrorCode, SBException
from app.domains.usage.models import UserUsage

load_dotenv()  # 独立脚本直接 import 时也能读到 .env（main.py 已 load 则幂等）

# ── 环境配置 ──
ARK_ENDPOINT = 'https://ark.cn-beijing.volces.com/api/v3/chat/completions'
ARK_API_KEY = os.getenv('ARK_API_KEY', '')
ARK_MODEL = os.getenv('ARK_MODEL', 'doubao-seed-2-1-pro-260628')
OCR_DAILY_QUOTA = int(os.getenv('OCR_DAILY_QUOTA', '5'))
OCR_MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 图片上限 5MB
# LLM 单次请求超时（秒）：图片/长文本识别较慢，30s 在数据量大时易 ReadTimeout → 503
ARK_TIMEOUT = int(os.getenv('ARK_TIMEOUT', '60'))
# 网络异常/超时/5xx 时的重试次数（0 = 不重试）；重试间隔 1.5s
ARK_RETRIES = int(os.getenv('ARK_RETRIES', '1'))

_SYSTEM_PROMPT = (
    '你是一个基金/股票代码提取助手。请从用户提供的持仓截图或文本中，'
    '提取所有基金/股票的代码与名称。'
    '只输出 JSON 数组，数组元素为对象：{"code": "6位数字代码", "name": "名称"}。'
    '识别不出名称时 name 可为空字符串。若无有效内容，输出 []。'
    '不要输出任何其他文字或解释。'
)


# ── 用量（user_usage）──
def _get_usage(db, user_id: int, feature: str, period: date) -> UserUsage:
    """取当日用量行，不存在则创建（带默认 quota）。"""
    row = (
        db.query(UserUsage)
        .filter(UserUsage.user_id == user_id, UserUsage.feature == feature, UserUsage.period_date == period)
        .first()
    )
    if row is None:
        row = UserUsage(user_id=user_id, feature=feature, period_date=period, count=0, quota=OCR_DAILY_QUOTA)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def check_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> dict:
    """查询某用户某功能当日用量，返回 {used, quota, remaining, period_date}。"""
    period = period or date.today()
    with SessionLocal() as db:
        row = _get_usage(db, user_id, feature, period)
        return {
            'used': row.count,
            'quota': row.quota,
            'remaining': max(0, row.quota - row.count),
            'period_date': period.isoformat(),
        }


def consume_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> dict:
    """消费一次用量；超限抛 SBException（429 语义，错误码 3004）。"""
    period = period or date.today()
    with SessionLocal() as db:
        row = _get_usage(db, user_id, feature, period)
        if row.count >= row.quota:
            raise SBException(
                code=ErrorCode.USAGE_LIMIT_EXCEEDED.code,
                message=f'今日 {feature} 识别次数已用完（{row.quota} 次/天），请明日再试',
                status_code=ErrorCode.USAGE_LIMIT_EXCEEDED.http_status,
            )
        row.count += 1
        db.commit()
        db.refresh(row)
        return {
            'used': row.count,
            'quota': row.quota,
            'remaining': max(0, row.quota - row.count),
            'period_date': period.isoformat(),
        }


def refund_usage(user_id: int, feature: str = 'ocr_import', period: Optional[date] = None) -> None:
    """识别失败后返还本次已消耗的配额（count 减 1，下限 0）。

    策略：先消费再识别（防刷免费额度），但识别因服务不可用/超时失败时不应惩罚用户，
    否则测试期一次超时即白耗 1 次额度，5 次很快耗尽（见用户反馈）。
    """
    period = period or date.today()
    with SessionLocal() as db:
        row = _get_usage(db, user_id, feature, period)
        if row.count > 0:
            row.count -= 1
            db.commit()


# ── LLM 调用 ──
def _call_ark(content: List[dict], temperature: float = 0.1, timeout: int = None) -> str:
    """调用火山方舟 OpenAI 兼容端点，返回 choices[0].message.content。

    兜底设计（用户反馈 503 直报问题）：
    - 超时放宽到 ARK_TIMEOUT（默认 60s，图片/长文本识别慢，30s 易 ReadTimeout）；
    - 网络异常/超时/5xx 自动重试 ARK_RETRIES 次（默认 1 次，间隔 1.5s）；
    - 重试耗尽才抛 503（OCR_SERVICE_UNAVAILABLE），由 views 层返还配额。
    """
    if not ARK_API_KEY:
        raise SBException(
            code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
            message='服务端未配置 ARK_API_KEY，OCR 功能暂不可用',
            status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
        )
    timeout = timeout or ARK_TIMEOUT
    payload = {
        'model': ARK_MODEL,
        'messages': [
            {'role': 'system', 'content': _SYSTEM_PROMPT},
            {'role': 'user', 'content': content},
        ],
        'temperature': temperature,
    }

    last_err: Optional[Exception] = None
    for attempt in range(ARK_RETRIES + 1):
        try:
            resp = requests.post(
                ARK_ENDPOINT,
                headers={'Authorization': f'Bearer {ARK_API_KEY}', 'Content-Type': 'application/json'},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data['choices'][0]['message']['content']
        except (requests.RequestException, KeyError, ValueError) as e:
            last_err = e
            logger.warning('火山方舟调用失败（第 {} 次）: {}', attempt + 1, e)
            if attempt < ARK_RETRIES:
                time.sleep(1.5)
    logger.error('火山方舟调用重试 {} 次后仍失败: {}', ARK_RETRIES, last_err)
    raise SBException(
        code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
        message='OCR 识别服务暂时不可用，请稍后重试',
        status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
    )


def _extract_json(text: str) -> List[dict]:
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
        logger.warning('OCR 输出 JSON 解析失败: {}; 原文: {}', e, text[:200])
        return []
    return []


def _validate_items(items: List[dict]) -> List[dict]:
    """清洗识别结果：只保留 6 位数字代码，name 取字符串。"""
    cleaned = []
    for it in items:
        code = str(it.get('code', '') or '').strip()
        name = str(it.get('name', '') or '').strip()
        if re.fullmatch(r'\d{6}', code):
            cleaned.append({'code': code, 'name': name})
    return cleaned


def _is_listed_fund_code(code: str) -> bool:
    """6 位数字代码是否符合「场内基金」模式（无需查表即可判定）。

    - 5 开头：沪市 ETF/LOF/Reits/货币（510xxx-589xxx）
    - 159 开头：深市 ETF
    - 16x 开头：深市 LOF（160xxx-169xxx）

    场外开放式基金（110011、005827、270xxx 等）不落入上述区段。
    """
    return code.startswith('5') or code.startswith('159') or code.startswith('16')


def _enrich_items(items: List[dict]) -> List[dict]:
    """为识别结果补充资产类型/市场/场所（Securities 表 → 场内代码规则 → Funds 表 → 兜底）。

    OCR 只输出 6 位数字代码，前端无法据此区分股票/ETF/场外基金。若按代码前缀
    猜测（如 startsWith('5') → etf），股票（600519）被误判为场外基金、深市 ETF
    （159915）被漏判——type/venue/symbol 全错，与持仓表断裂、自选页类型错误，
    即「AI 批量导入后资产不对」的根因。此处按优先级反查：

    1. Securities 表命中（normalizer 标准化后精确匹配）→ 场内品种（股票/ETF/可转债）：
       type/market 取表值、symbol 标准化，venue=EXCHANGE。
    2. 未命中但符合场内基金代码模式（5/159/16x）→ 场内 ETF/LOF：venue=EXCHANGE，
       symbol 标准化（本地 Securities 表可能未收录 ETF/LOF，仅 Funds 表有）。
    3. Funds 表命中（fund_code 精确匹配）→ 场外基金：venue=OTC，symbol=裸代码。
    4. 兜底 → 默认场外基金。
    """
    from app.core.database import SessionLocal
    from app.core.symbol_utils import get_normalizer
    from app.domains.funds.models import Fund
    from app.domains.securities.models import Security

    normalizer = get_normalizer()
    enriched: List[dict] = []
    with SessionLocal() as db:
        for it in items:
            code = it['code']
            info = {'code': code, 'name': it.get('name', '')}
            # 1) 场内品种：normalizer 标准化后精确匹配 Securities
            normalized = None
            market = None
            try:
                normalized, market, _ = normalizer.normalize(code)
            except Exception:
                pass
            if normalized:
                sec = db.query(Security).filter_by(symbol=normalized).first()
                if sec:
                    info.update(
                        {
                            'symbol': sec.symbol,
                            'name': sec.name or info['name'],
                            'type': sec.type,
                            'market': sec.market,
                            'venue': 'EXCHANGE',
                        }
                    )
                    enriched.append(info)
                    continue
            # 2) 场内基金（ETF/LOF）：Securities 未收录但代码符合场内模式
            if _is_listed_fund_code(code):
                fund = db.query(Fund).filter_by(fund_code=code).first()
                fund_type = 'etf' if (code.startswith('5') or code.startswith('159')) else 'fund'
                info.update(
                    {
                        'symbol': normalized or code,
                        'name': fund.name if fund else info['name'],
                        'type': fund_type,
                        'market': market or 'CN_A',
                        'venue': 'EXCHANGE',
                    }
                )
                enriched.append(info)
                continue
            # 3) 场外基金：fund_code 精确匹配
            fund = db.query(Fund).filter_by(fund_code=code).first()
            if fund:
                info.update(
                    {
                        'symbol': code,
                        'name': fund.name or info['name'],
                        'type': 'fund',
                        'market': 'CN_A',
                        'venue': 'OTC',
                    }
                )
                enriched.append(info)
                continue
            # 4) 兜底：默认场外基金
            info.update({'symbol': code, 'type': 'fund', 'market': 'CN_A', 'venue': 'OTC'})
            enriched.append(info)
    return enriched


# ── 对外接口 ──
def recognize(image_bytes: bytes) -> List[dict]:
    """图片 → 火山方舟 vision → 基金/股票代码列表。"""
    if not image_bytes:
        raise SBException(code=ErrorCode.INVALID_PARAMS.code, message='图片内容为空', status_code=400)
    if len(image_bytes) > OCR_MAX_IMAGE_BYTES:
        raise SBException(
            code=ErrorCode.INVALID_PARAMS.code, message='图片超过 5MB 上限，请压缩后重试', status_code=400
        )
    b64 = base64.b64encode(image_bytes).decode('ascii')
    content = [
        {'type': 'text', 'text': '请识别图片中的所有基金/股票代码与名称。'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
    ]
    raw = _call_ark(content)
    return _enrich_items(_validate_items(_extract_json(raw)))


def parse_text(text: str) -> List[dict]:
    """纯文本 → LLM → 基金/股票代码列表（AI 批量导入，无需图片）。"""
    if not text or not text.strip():
        raise SBException(code=ErrorCode.INVALID_PARAMS.code, message='文本内容为空', status_code=400)
    content = [{'type': 'text', 'text': f'请从以下文本中提取基金/股票代码与名称：\n\n{text[:8000]}'}]
    raw = _call_ark(content)
    return _enrich_items(_validate_items(_extract_json(raw)))
