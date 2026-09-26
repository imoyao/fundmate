# -*- coding: utf-8 -*-
"""输入侧意图护栏（L2 前置；设计 §6「输入侧意图护栏」）。

在**请求进入模型之前**做前置拦截：能在输入侧拦掉的，就不花钱让模型生成再拦
（§6 的「顺序的意义是成本」）。判据全部是正则 / 规则，无状态、不接模型，
因此拦截行为可以确定性单测。

本域的越界定义（比通用「违规内容」更具体，见设计 §6 五类）：
- A 意图分类：数据查询 / 通用知识 / 预测 / 建议 / 情绪施压 —— 预测与建议类直接拦；
- B 模式命中：越界句式正则（含「伪装成分析的建议」的输入形态，不只匹配字面「买/卖」）；
- D 情绪 + 建议复合：**不拦**，但打 `risk_notice` 让调用方在回复里强制带风险提示，
  防模型顺着用户情绪给安慰式建议；
- E（未调工具却谈市场判断）属输出侧，与 `output_filter` 协同，不在本模块。

被拦时**不进模型**，直接回预设标准话术——注意话术给的是安全出口（「我可以帮你查 X」），
不是干巴巴的拒绝，否则用户只会换个问法再来一遍（那会撞上 `repeat_tracker`）。
"""

import re
from dataclasses import dataclass

# ── 意图类别（A）──
CATEGORY_QUERY = 'query'  # 数据查询：正常进模型
CATEGORY_KNOWLEDGE = 'knowledge'  # 通用知识：放行（不含用户数据断言，风险低）
CATEGORY_PREDICTION = 'prediction'  # 预测：拦
CATEGORY_ADVICE = 'advice'  # 建议：拦
CATEGORY_EMOTION = 'emotion'  # 情绪施压：不拦，但插风险提示（D）

# ── 标准话术（给模型安全出口，替代干瘪的「我不能回答」）──
REPLY_PREDICTION = (
    '我无法预测涨跌，也不会对未来走势下任何断言——这不是我不愿意，是这类问题没有可靠答案。'
    '已经发生的数据我可以如实查给你：历史净值走势、近一年涨跌幅、当前市场温度，要看哪个？'
)
REPLY_ADVICE = (
    '我不能替你做决定，也不提供买卖时点、荐股或基金经理点评。'
    '我可以帮你查的是事实：这只标的的历史表现、你的持仓成本与浮亏、当前温度——要看哪个？'
)
REPLY_PROMISE = '我不能给出任何收益承诺（稳赚 / 保本 / 保证年化）。历史收益我可以如实查给你，但历史不代表未来。'
# D：情绪 + 建议复合时，由调用方插到回复前的强制风险提示
RISK_NOTICE = '（市场有波动是常态，下面只是数据梳理，不构成任何投资建议，也不构成对你的操作建议。）'

# ── B 模式命中：越界句式（命中即拦，不进模型）──
# 每条 = (规则号, 意图类别, 正则, 标准话术)。
# 注意用「会涨/会跌/该不该/如果我是你」这类**意图句式**，而非字面「涨/跌」——
# 「温度多少」「近一年涨跌幅」是数据查询，必须放行，故不单独匹配「涨」「跌」。
_BLOCK_RULES = (
    (
        'B1',
        CATEGORY_PREDICTION,
        re.compile(
            r'(会涨|会跌|即将(上涨|下跌)|必涨|必跌|见顶|触底|反弹在即|还会(涨|跌)|'
            r'后市(看涨|看跌)|明天(涨|跌)|能涨(吗|么)|会涨(吗|么)|会跌(吗|么)|'
            r'你觉得.{0,8}(涨|跌)|预测.{0,6}(涨|跌|点位|走势))'
        ),
        REPLY_PREDICTION,
    ),
    (
        'B2',
        CATEGORY_ADVICE,
        re.compile(
            r'(该不该(买|卖|加仓|减仓|清仓|割|换|持有)|要不要(买|卖|加仓|减仓)|'
            r'能不能(买|卖|加|减)|推荐.{0,6}(基金|股票|标的|组合)|买入评级|强烈推荐|'
            r'如果我是你|你(会|应该)怎么做|你觉得我(该|应该)|'
            r'(现在|当下).{0,6}(买|卖|上车|下车|冲|进|出))'
        ),
        REPLY_ADVICE,
    ),
    (
        'B3',
        CATEGORY_ADVICE,
        re.compile(
            r'(哪个(基金|股票|标的)(好|最好)|这只(基金|标的)(怎么样|好不好|行不行)|'
            r'基金经理(怎么样|好不好|牛不牛)|值得(买|投|上车)(吗|么)|'
            r'(值得|可以|还能)(继续)?(持有|拿|留)(吗|么)|'
            r'(能不能|还能不能|可不可以)(拿|持有|留)(住)?|'
            r'(白酒|医药|新能源|半导体|纳指|标普|黄金|原油|大盘|A股|美股).{0,6}(还能|可不可以)(拿|持有))'
        ),
        REPLY_ADVICE,
    ),
    (
        'B4',
        CATEGORY_PREDICTION,
        re.compile(r'(能赚多少|保证(能|会)?(赚|收益|不亏)|稳赚|稳赢|保本|不会亏|低风险高收益|肯定(赚|赢))'),
        REPLY_PROMISE,
    ),
)

# A 意图分类用的越界句式（比 _BLOCK_RULES 略宽，用于归类而不一定拦截）
_PREDICTION_CUE = re.compile(r'(涨|跌|走势|点位|牛市|熊市|抄底|逃顶|反弹|反转).{0,4}(吗|么|呢|会|能|该)')
_ADVICE_CUE = re.compile(r'(该不该|要不要|买不买|卖不卖|换不换|加不加|减不减|值不值得|如何操作|怎么办)')
# D 情绪 + 建议复合（§6-D）：两个条件**都**满足才打 risk_notice，故拆成两个 pattern。
# 合成一个大 pattern 会让「怎么办」（无意图情绪）或「我好焦虑」（无建议意图）
# 任意一侧单独出现就上免责声明——前者是普通求助，后者是情绪倾诉，都不构成
# 「模型顺情绪给安慰式建议」的风险面。
_EMOTION_WORDS = re.compile(r'(焦虑|心慌|慌了|亏惨|睡不着|割肉|害怕|崩溃|扛不住|受不了|还有救|回本|要完|没救)')
_SEEK_ADVICE = re.compile(r'(怎么办|该不该|要不要|怎么操作|如何是好|你说我|你觉得我|帮我想想办法)')
_QUERY_CUE = re.compile(
    r'(多少|几成|几只|温度|持仓|收益|净值|涨幅|跌幅|回撤|浮亏|浮盈|跑赢|跑输|'
    r'历史|近(一|半|三|六|12)年|查(一)?下|看看|帮我(查|看|算)|我的)'
)


@dataclass(frozen=True)
class InputVerdict:
    """输入侧裁决。

    - `blocked`：True 时调用方**不得**调模型，直接回 `reply`；
    - `risk_notice`：D 情绪复合，调用方须把 `RISK_NOTICE` 放进回复；
    - `rule`：命中的规则号（B1~B4）或分类来源，未命中为空串——留痕给日志与测试。
    """

    category: str
    blocked: bool
    risk_notice: bool
    rule: str
    reply: str


def classify(text: str) -> str:
    """A 意图分类：预测 / 建议 / 情绪 / 数据查询 / 通用知识。

    顺序即优先级：越界的判定先于查询——「温度会涨吗」既含「温度」也含「会涨」，
    必须归到预测类，否则会被查询线索放行。
    """
    if not text or not isinstance(text, str):
        return CATEGORY_KNOWLEDGE
    for rule, category, pattern, _reply in _BLOCK_RULES:
        if pattern.search(text):
            return category
    if _PREDICTION_CUE.search(text):
        return CATEGORY_PREDICTION
    # D 复合判定排在普通建议线索之前：情绪倾诉常带「怎么办」，
    # 先按 advice 归类会把 risk_notice 整个吃掉（§6-D 要的是「插提示而非硬拦」）
    if _EMOTION_WORDS.search(text) and _SEEK_ADVICE.search(text):
        return CATEGORY_EMOTION
    if _ADVICE_CUE.search(text):
        return CATEGORY_ADVICE
    if _QUERY_CUE.search(text):
        return CATEGORY_QUERY
    return CATEGORY_KNOWLEDGE


def check_input(text: str) -> InputVerdict:
    """输入侧前置检查（进模型之前调用）。

    命中 B 规则 → `blocked=True` 且带标准话术，零模型成本；
    情绪复合（D）→ `blocked=False` 但 `risk_notice=True`。
    """
    for rule, category, pattern, reply in _BLOCK_RULES:
        if pattern.search(text or ''):
            return InputVerdict(category=category, blocked=True, risk_notice=False, rule=rule, reply=reply)
    category = classify(text)
    if category == CATEGORY_EMOTION:
        return InputVerdict(category=category, blocked=False, risk_notice=True, rule='D', reply='')
    return InputVerdict(category=category, blocked=False, risk_notice=False, rule='', reply='')
