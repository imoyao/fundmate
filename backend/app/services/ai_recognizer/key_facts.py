# -*- coding: utf-8 -*-
"""关键信息卡（key_facts）的单一真源：白名单、合并语义、规则抽取。

本模块收敛同一层的三处缺陷：

1. **早轮无卡**：卡原先只在压缩成功后写入（`turn_count > 6` 且原文 > 8 条），
   短会话这一层恒空。改为每轮由规则从**本轮输入**抽硬槽 → 第 1 轮即有卡，
   不再依赖「压缩有没有触发」。
2. **替换语义自相矛盾**：旧实现「空 dict 保留旧卡 / 半空 dict 整体替换」，
   同一字段空与半空方向相反。现统一为「缺键保留、空值忽略、非空覆盖」。
3. **绕过 state 白名单**：state 有 `ALLOWED_KEYS` + 类型校验，key_facts 却由模型
   自由写库、原样进 prompt。现在写路径（合并）与读路径（装配）都过
   `normalize_key_facts`，脏键与非字符串值到不了模型。

设计边界（刻意的取舍，不是待办）：

- 规则只抽「可枚举、可判定」的硬槽（标的代码 / 时间范围）。规则宁缺勿错——
  错的焦点比空的焦点更坏。
- **账户不进卡**（D124）：卡是「模型可写 + 每轮回灌 + 优先遵守」的持久状态，
  放标识符等于开一条持久化注入通道；而当前 10 个工具**没有一个接受账户参数**，
  这个槽零执行收益。账户信息由工具输出瞬时承担（`get_return_attribution` 的
  `dimension=account` 已返回 `ledger_id + account_name`，且名称解析带 family 过滤）。
  将来若真要「按账户聚焦」，只能存**服务端在 family 作用域内解析后注入**的
  `account_id`，模型写入的该键一律丢弃，渲染时再由服务端 id→name。
- 规则不产出「清除」：卡只增不减，过期靠被新值覆盖 + 会话结束淘汰。显式清除
  要求模型稳定区分「未知」与「清空」，当前做不到，故不做（宁可留旧不误删）。
- 卡只进 prompt 的聚焦段，永不作为工具参数；参数预填只走
  `state.collected_params` + 工具 schema 校验 + `apply_server_context` 覆盖。
"""

import re

# 白名单：与压缩 prompt 的约定、模型注释、前端预期三处保持一致
KEY_FACT_KEYS = ('标的', '时间范围')
FACT_VALUE_CAP = 120

# 标的代码：6 位数字，可带交易所前缀（venue 真相源见 core/venues.py）
_SYMBOL_RE = re.compile(r'(?<![0-9A-Za-z])((?:SH|SZ|BJ)?\d{6})(?![0-9])', re.I)
# 年月形态（202611 / 199912）不是标的
_DATE_SHAPE = re.compile(r'^(?:19|20)\d{4}$')
# 金额 / 数量 / 百分比后缀：命中的 6 位数字是数量，不是代码
_AMOUNT_SUFFIX = re.compile(r'^\s*(?:元|块|万|亿|股|份|手|%|个)')
# 裸 6 位数字要落卡，前文需出现标的类线索（避免流水号 / 金额被当代码）
_SYMBOL_CUES = (
    '基金',
    '股票',
    'ETF',
    'LOF',
    '代码',
    '标的',
    '持仓',
    '净值',
    '走势',
    '看看',
    '分析',
    '买',
    '卖',
    '定投',
)
_CUE_WINDOW = 12  # 线索只看代码前 12 字，避免远处的「买」误点亮整句

_PERIOD_RE = re.compile(
    r'(?:近|最近|过去)\s*(?:\d+|[一二三四五六七八九十两]+)\s*(?:天|日|周|个月|月|年|季度)'
    r'|(?:今年|去年|前年|明年)(?:以来|全年|上半年|下半年)?'
    r'|(?:本|上|下)(?:周|月|季度|半年)'
    r'|\d{4}\s*年(?:\s*\d{1,2}\s*月)?'
    r'|\d{4}-\d{1,2}(?:-\d{1,2})?'
    r'|(?:一|二|三|四|上|下)季度'
    r'|上半年|下半年|年初至今|年初以来'
)


def normalize_key_facts(raw) -> dict:
    """白名单 + 类型 + 长度校验：唯一允许落库 / 进 prompt 的卡形态。

    键序固定为 `KEY_FACT_KEYS`，保证同一份事实序列化结果稳定（prompt 与测试可预期）。
    """
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in KEY_FACT_KEYS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:FACT_VALUE_CAP]
    return out


def merge_key_facts(old, new) -> dict:
    """缺键保留旧值、空值忽略、非空覆盖——三处缺陷 #2 的唯一语义。

    空 dict 与半空 dict 现在走同一条规则，不再出现「空则保留、半空则全丢」。
    """
    merged = normalize_key_facts(old)
    merged.update(normalize_key_facts(new))
    return merged


def _has_symbol_cue(before: str) -> bool:
    window = before[-_CUE_WINDOW:]
    return any(cue in window for cue in _SYMBOL_CUES)


def _extract_symbol(text: str) -> str:
    for match in _SYMBOL_RE.finditer(text):
        code = match.group(1).upper()
        if _DATE_SHAPE.match(code) or _AMOUNT_SUFFIX.match(text[match.end() :]):
            continue
        if len(code) == 6 and not _has_symbol_cue(text[: match.start()]):
            continue
        return code
    return ''


def _extract_period(text: str) -> str:
    match = _PERIOD_RE.search(text)
    return re.sub(r'\s+', '', match.group(0)) if match else ''


def extract_key_facts(text) -> dict:
    """从单条用户输入抽硬槽（标的 / 时间范围）；账户不入卡，见模块 docstring。"""
    if not isinstance(text, str) or not text.strip():
        return {}
    found = {'标的': _extract_symbol(text), '时间范围': _extract_period(text)}
    return normalize_key_facts(found)


def maintain_key_facts(session) -> None:
    """每轮装配前维护焦点卡：规则抽本轮硬槽，与压缩产出的软焦点合并。

    取 `session.messages[-1]['user']` 而不新增入参——本轮原文已由主循环写入
    （两侧截断后），复用它可以不改 `_maybe_compress` 的签名与调用点形态。

    幂等：与库内值一致时不写回。整体重赋新 dict，因为就地改 JSON 列不触发
    SQLAlchemy 脏跟踪（同 `persist` 里 `session.state = dict(state)` 的理由）。
    """
    messages = getattr(session, 'messages', None) or []
    latest = messages[-1].get('user', '') if messages and isinstance(messages[-1], dict) else ''
    current = getattr(session, 'key_facts', None)
    merged = merge_key_facts(current, extract_key_facts(latest))
    if not isinstance(current, dict) or merged != current:
        session.key_facts = merged
