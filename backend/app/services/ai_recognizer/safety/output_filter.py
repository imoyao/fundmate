# -*- coding: utf-8 -*-
"""L3 输出侧词法过滤器（设计 §7——最硬、不可绕过的最后一道防线）。

模型生成的**最终回复文本**在返回用户前经本模块扫描：即便 L1 prompt 失效、
模型不听指令，这里仍兜底拦截越界内容。

设计原则（照 §7.1，不是我发挥的）：
1. **宁可误伤、不可漏放**——但误伤必须用白名单豁免修正，而不是把规则放宽到形同虚设；
2. **命中替换、不整篇拒答**（§7.3）——命中句换成对应类别的免责声明，其余合规内容保留；
   E 类（未调工具却谈市场判断）例外：整段替换，因为它没有事实基础可保留；
3. **纯函数**：`filter_output(text, used_tools=...) -> OutputVerdict`，无状态、不接模型，
   可确定性单测；命中留痕（规则号）供日志与评估集回填。

域内规则 R1~R10 + E1（见设计 §7.2 表）。白名单/豁免是关键难点：性能类句子里的
「年化 54.6%」是**已发生事实**（XIRR 计算结果），必须放行，否则每次算收益都会被自我误伤
——所以 R5b 只在缺少事实标记词时才命中。
"""

import re
from dataclasses import dataclass

# ── 免责声明模板（按类别；命中后替换该句时使用）──
DISCLAIMER_TEMPLATE = {
    'prediction': '（我无法预测涨跌，以下只陈述已发生的数据，不构成对未来走势的任何判断。）',
    'advice': '（我不提供买卖建议或操作时点，是否交易由你自行决定。）',
    'recommend': '（我不荐股、不给出评级，也不点评基金经理，以下是事实数据。）',
    'promise': '（我不能承诺任何收益；历史数据不代表未来表现。）',
    'subjective': '（我不对标的或人做主观褒贬，以下只是数据对比。）',
    'market_judgment': '（未调用任何数据工具时不提供市场判断，以下是已知信息的复述。）',
}

# 事实标记词：出现即说明该句在陈述**已发生**数据（白名单豁免用）
_FACT_MARKERS = re.compile(r'(历史|过去|实际|截至|回测|已|近(一|半|三|六|12)个?月|近一年|今年以来|去年)')

# ── 规则表 ────────────────────────────────────────────────────────────────
# Rule = (规则号, 类别, 正则, 是否启用事实标记豁免)
# 第 4 位为 True 时：句中含 _FACT_MARKERS 则本条豁免（历史/实际数据放行）。
_RULES = (
    (
        'R1',
        'prediction',
        re.compile(
            r'(会涨|会跌|将涨|将跌|即将(上涨|下跌)|必涨|必跌|见顶|触底|反弹在即|'
            r'还会(涨|跌)|后市(看涨|看跌)|明天(涨|跌)|下(周月年)(涨|跌)|'
            r'(大概率|很可能).{0,6}(涨|跌)|目标价|看到\s*\d)'
        ),
        False,
    ),
    (
        'R2',
        'advice',
        re.compile(
            r'(建议(你)?(现在|立刻|立即)?(买入|卖出|加仓|减仓|清仓|割肉|换|持有|上车|下车)|'
            r'赶紧(买|卖|跑|加|减)|别(再)?(买|卖|拿着|拿了)|'
            r'(现在|此时).{0,6}(是|为)(最佳|最好|最后).{0,4}(时机|机会|时候)|'
            r'该(如何|怎么)(操作|处理)|什么时候(买|卖|入场|离场)|买(入)?(时|点)|卖(出)?(时|点))'
        ),
        False,
    ),
    (
        'R3',
        'advice',
        re.compile(r'(我建议你|你应该(考虑)?|你(最好|不妨|可以考虑)(卖|买|清|减|加|换|走|撤))'),
        False,
    ),
    (
        'R4',
        'recommend',
        re.compile(
            r'(强烈推荐|首推|必买|金牛|五星基金|十倍股|妖股|白马股(之王|首选)|'
            r'(值得|放心)(买入|购买|上车)|这(只|款|个)(基金|标的)?.{0,6}(适合|值得)你)'
        ),
        False,
    ),
    (
        'R5a',
        'promise',
        re.compile(
            r'(保证(年化|收益|不亏|稳赚)|稳赚(不赔)?|稳赢|保本|不会亏(钱|损)?|肯定(赚|赢|涨)|'
            r'(躺|睡)着(赚|收益)|无风险.{0,4}收益|年化\s*\d+(\.\d+)?%\s*(以上|保底))'
        ),
        False,
    ),
    (
        # R5b：裸「年化 X%」——带事实标记（历史/实际/近一年/截至…）则豁免，
        # 否则视为收益承诺式表述。白名单豁免是 §7.1「误伤用白名单修正」的落地。
        'R5b',
        'promise',
        re.compile(r'年化\s*\d+(\.\d+)?%'),
        True,
    ),
    (
        'R6',
        'advice',
        re.compile(r'(跌\s*\d+(\.\d+)?%\s*(就|便|马上)?(卖|清|止损|减)|涨\s*\d+(\.\d+)?%\s*(就|便|马上)?(卖|清|落袋))'),
        False,
    ),
    (
        'R7',
        'subjective',
        re.compile(
            r'(这(只|款|个)?(基金|经理|标的|产品)[一-龥]{0,6}(很差|很差劲|优秀|很优秀|最?(好|棒|牛)|烂|垃圾|不行)|'
            r'(差劲|不靠谱|不靠谱的)(基金经理|产品|标的)|'
            r'(任泽平|葛兰|张坤|刘彦春|朱少醒|谢治宇)(牛|神|差|菜)|'
            r'这(只|款|个)?(基金|标的)值得(你)?(投|买))'
        ),
        False,
    ),
    (
        'R8',
        'recommend',
        re.compile(
            r'(买入评级|增持(评级)?|卖出评级|强烈(看好|看空)|'
            r'我(看好|看空)(这只|这个)|未来.{0,4}(翻倍|十倍)|上(的目标价|看到))'
        ),
        False,
    ),
    (
        'R9',
        'advice',
        re.compile(r'(什么时候(买|卖)|(买|卖)(的)?最佳时机|该(何时|啥时候)(入手|出手|走))'),
        False,
    ),
    (
        'R10',
        'promise',
        re.compile(r'(你(一定|肯定|必须)能赚|这辈?子.{0,6}(财务自由|稳了)|闭眼(买|入)|抄作业(必|稳)赚)'),
        False,
    ),
)

# E1（§6 五类的输出侧辅助）：未调任何数据工具，却谈「当前市场判断 / 具体标的该不该动」
_MARKET_JUDGMENT = re.compile(
    r'(当前市场.{0,6}(判断|趋势|方向|机会)|现在(是|算)(不是)?(底|顶|时机)|'
    r'(这只|这个)(标的|基金|股票).{0,6}该不该|(A股|美股|大盘|黄金|原油)接下来)'
)


@dataclass(frozen=True)
class OutputVerdict:
    """输出侧裁决。

    - `blocked`：是否发生过干预（用于调用方记日志 / 统计，不等于拒答）；
    - `hit_rules`：命中的规则号列表，留痕给日志与评估集；
    - `sanitized`：应展示给用户的文本（已做替换），调用方**必须**用它覆盖原文。
    """

    blocked: bool
    hit_rules: tuple
    sanitized: str

    def __bool__(self) -> bool:
        """真值 = 有干预，便于 `if verdict:` 短路。"""
        return self.blocked


def _split_sentences(text: str) -> list:
    """按中文句末标点切句，保留分隔符（还原时原样拼回，不丢原排版）。"""
    return re.split(r'(?<=[。！？；!?;\n])', text)


# 全角 → 半角映射：数字 / 句点 / 百分号 / 全角空格。
# 只处理「含数字规则会用到的」字符，避免把中文标点也改了（改了会破坏切句）。
_FULLWIDTH_TRANS = str.maketrans({**{chr(0xFF10 + i): str(i) for i in range(10)}, '％': '%', '．': '.', '　': ' '})


def _normalize(text: str) -> str:
    """全角数字/标点转半角，使 R5b/R6 这类含数字的规则不因全角而漏检。

    案例：「年化８．５％」若不转，`\\d+(\\.\\d+)?%` 匹配不到 `8．5%`
    （`．` 不是 `.`），收益承诺就从全角这条缝里漏过去了。
    """
    return text.translate(_FULLWIDTH_TRANS)


def filter_output(text: str, *, used_tools: bool = True) -> OutputVerdict:
    """扫描最终回复文本，命中句替换为免责声明（§7.2/§7.3）。

    :param text: 模型产出的最终回复（叙事轮正文 / 追问内容）。
    :param used_tools: 本回合是否真调用过数据工具——False 时才启用 E1 判定，
        因为「没查数却谈市场判断」是用训练知识补用户数据的信号。
    """
    if not text or not isinstance(text, str):
        return OutputVerdict(blocked=False, hit_rules=(), sanitized=text or '')

    # E1：未调工具却谈市场判断 → 整段替换（没有事实基础可保留）
    if not used_tools and _MARKET_JUDGMENT.search(text):
        return OutputVerdict(
            blocked=True,
            hit_rules=('E1',),
            sanitized=DISCLAIMER_TEMPLATE['market_judgment'],
        )

    normalized = _normalize(text)
    sentences = _split_sentences(text)
    # 归一化句与原文句等长切分（_normalize 只换字符不增删），按位置对应
    norm_sentences = _split_sentences(normalized)
    if len(norm_sentences) != len(sentences):
        norm_sentences = sentences  # 兜底：切分不一致时退回原文逐句判定

    hit_rules = []
    out_parts = []
    for idx, sentence in enumerate(sentences):
        norm = norm_sentences[idx]
        replacement = None
        for rule_id, category, pattern, exempt_facts in _RULES:
            if exempt_facts and _FACT_MARKERS.search(norm):
                continue  # 历史/实际数据白名单豁免
            if pattern.search(norm):
                hit_rules.append(rule_id)
                replacement = DISCLAIMER_TEMPLATE[category]
                break  # 一句只替换一次，命中即止（同类多规则不重复替换）
        out_parts.append(replacement if replacement is not None else sentence)

    if not hit_rules:
        return OutputVerdict(blocked=False, hit_rules=(), sanitized=text)
    return OutputVerdict(blocked=True, hit_rules=tuple(hit_rules), sanitized=''.join(out_parts))
