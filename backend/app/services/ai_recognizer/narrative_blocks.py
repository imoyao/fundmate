# -*- coding: utf-8 -*-
"""结构化叙事分块解析（#1712）。

职责：把叙事轮模型输出（prompt 契约：固定三小节【结论】/【明细】/【风险提示】）
解析为**块结构**，并把工具返回的行级数据（如 list_position_pnl 的 items）组装成
表格块，供前端按块渲染（结论加粗置顶 / 明细表格带涨跌语义色 / 风险提示弱化）。

契约与降级（验收标准 1）：
- 输出结构由我们契约控制，不取决于模型能力；但模型可能漂移——
  解析不到任何小节标记时返回 None，上层把 None 原样透传，
  前端 blocks 缺失即回退纯文本渲染（不 500、不崩、不留半块）。

防御（验收标准 3 / 全站约定）：
- 所有文本剔除 Emoji（AGENTS.md 前端约束在后端的镜像防线，前端渲染层另有 stripEmoji 兜底）；
- 表格只收**扁平标量行**（str/int/float/bool/None），嵌套结构整体放弃成表；
- 行数 / 列数硬上限（MAX_TABLE_ROWS / MAX_TABLE_COLS），超限截断并在块内标注 truncated；
- 前端渲染一律文本插值（Vue 自动转义），无 v-html，raw HTML / script 标签天然不执行——
  解析器不负责转义 HTML，转义是渲染层的职责边界。

盈亏语义色口径（验收标准 2）：**行级**盈亏 / 盈亏率列标 kind='pnl'，前端按正负染
--color-rise-ink / --color-fall-ink（涨红跌绿）；**汇总值 / 中性值不染色**——
解析器只对行级表格列标注 kind，叙事文本与指标 chips 一律 plain。
"""

import re
from typing import Any, List, Optional

# ── 小节标记（prompt 契约，前后端共同遵守的唯一口径） ──
SECTION_MARKERS = ('【结论】', '【明细】', '【风险提示】')
_MARKER_RE = re.compile('|'.join(re.escape(m) for m in SECTION_MARKERS))

# Emoji 剔除（与前端 stripEmoji 同区间；Python re 无 \p{Emoji}，用码段穷举）
_EMOJI_RE = re.compile('[\U0001f000-\U0001faff\u2600-\u27bf\u2b00-\u2bff\ufe0f\u200d]')

# 表格硬上限（验收标准 5：列数 / 行数设上限）
MAX_TABLE_ROWS = 50
MAX_TABLE_COLS = 8

# 行级列契约：key -> (展示列名, 语义 kind)。kind='pnl' 的列前端按正负染涨跌色。
# 顺序即列优先级——超出 MAX_TABLE_COLS 时从尾部丢弃（先保代码/名称/核心数字）。
COLUMN_CONTRACT = [
    ('symbol', '代码', 'plain'),
    ('name', '名称', 'plain'),
    ('quantity', '数量', 'plain'),
    ('avg_price', '成本价', 'plain'),
    ('current_price', '现价', 'plain'),
    ('market_value', '市值', 'plain'),
    ('pnl', '盈亏', 'pnl'),
    ('pnl_rate', '盈亏率(%)', 'pnl'),
    # 以下列仅在未触顶时展示（补充信息）
    ('cost', '成本', 'plain'),
    ('type', '类型', 'plain'),
    ('account_name', '账户', 'plain'),
]

_SCALAR_TYPES = (str, int, float, bool)


def _strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub('', text)


def _is_scalar(v: Any) -> bool:
    return v is None or isinstance(v, _SCALAR_TYPES)


def _extract_table(tool_data: Any) -> Optional[dict]:
    """从工具返回数据提取行级表格块；不是「扁平标量行的数组」则返回 None。

    识别口径：dict 且 items 为行数组（list_position_pnl 契约），或数据本身就是行数组。
    行内嵌套值（dict/list）剥掉不渲染（缺该列即可），**整行不是 dict** 才整体放弃成表
    ——后者说明这根本不是行集合，宁可不渲染表格，也不渲染出 [object Object]。
    """
    if isinstance(tool_data, dict):
        rows = tool_data.get('items')
    elif isinstance(tool_data, list):
        rows = tool_data
    else:
        return None
    if not isinstance(rows, list) or not rows:
        return None

    truncated = len(rows) > MAX_TABLE_ROWS
    flat_rows: List[dict] = []
    for r in rows[:MAX_TABLE_ROWS]:
        if not isinstance(r, dict):
            return None
        flat = {k: v for k, v in r.items() if _is_scalar(v)}
        # 整行没有可渲染的扁平值（全是嵌套结构）→ 放弃成表
        if not flat:
            return None
        flat_rows.append(flat)
    if not flat_rows:
        return None

    # 列序：契约优先（按 COLUMN_CONTRACT 顺序），其余键按首现顺序补尾；列数硬上限
    seen: List[str] = []
    for r in flat_rows:
        for k in r:
            if k not in seen:
                seen.append(k)
    ordered = [k for k, _, _ in COLUMN_CONTRACT if k in seen]
    ordered += [k for k in seen if k not in {c[0] for c in COLUMN_CONTRACT}]
    cols = ordered[:MAX_TABLE_COLS]
    if not cols:
        return None

    kind_by_key = {k: kind for k, _, kind in COLUMN_CONTRACT}
    label_by_key = {k: label for k, label, _ in COLUMN_CONTRACT}
    columns = [{'key': k, 'label': label_by_key.get(k, k), 'kind': kind_by_key.get(k, 'plain')} for k in cols]
    rows_out = []
    for r in flat_rows:
        row = {}
        for k in cols:
            v = r.get(k)
            row[k] = _strip_emoji(v) if isinstance(v, str) else v
        rows_out.append(row)
    return {'type': 'table', 'columns': columns, 'rows': rows_out, 'truncated': truncated}


def parse_narrative_blocks(narrative: Any, tool_data: Any = None) -> Optional[List[dict]]:
    """把叙事文本按小节契约解析为块列表；完全无小节标记时返回 None（降级纯文本）。

    块结构（全部扁平、可直接进 JSON 信封）：
    - {'type': 'summary', 'text': str}   结论（前端加粗置顶）
    - {'type': 'text',    'text': str}   明细叙述（可多段）
    - {'type': 'table',   columns/rows/truncated}  行级数据表（仅当工具数据可成表）
    - {'type': 'risk',    'text': str}   风险提示（前端弱化展示）

    容错：小节缺失跳过该节；标记外的前导/夹缝文本按原序保留为 text 块；
    表格提取失败不影响文本块（各自独立降级）。
    """
    if not isinstance(narrative, str) or not narrative.strip():
        return None

    # 按标记切段：pieces[i] 为 markers[i-1] 之后、markers[i] 之前的文本（pieces[0] 为前导）
    pieces: List[str] = []
    last_end = 0
    for m in _MARKER_RE.finditer(narrative):
        pieces.append(narrative[last_end : m.start()])
        pieces.append(m.group())  # 占位：偶数位为标记前文本，奇数位为标记——改为显式结构更清晰
        last_end = m.end()
    pieces.append(narrative[last_end:])
    if not _MARKER_RE.search(narrative):
        return None

    # 重组为 (当前标记或 None, 文本) 序列
    segments: List[tuple] = []
    current: Optional[str] = None
    buf: List[str] = []
    for p in pieces:
        if p in SECTION_MARKERS:
            if current is not None or ''.join(buf).strip():
                segments.append((current, ''.join(buf)))
            current = p
            buf = []
        else:
            buf.append(p)
    segments.append((current, ''.join(buf)))

    blocks: List[dict] = []
    table = _extract_table(tool_data)
    for marker, text in segments:
        text = _strip_emoji(text).strip()
        if not text:
            continue
        if marker == '【结论】':
            blocks.append({'type': 'summary', 'text': text})
        elif marker == '【风险提示】':
            blocks.append({'type': 'risk', 'text': text})
        else:
            # 明细节文本（或标记外的夹缝文本）→ text 块；明细节之后紧跟表格块
            blocks.append({'type': 'text', 'text': text})
            if marker == '【明细】' and table is not None:
                blocks.append(table)
                table = None  # 表格只挂一次
    if table is not None:
        # 契约漂移（没有【明细】节）但有行级数据：表格兜底追加在文本块之后，不丢数据
        blocks.append(table)
    return blocks or None
