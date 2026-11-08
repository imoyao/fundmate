# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/6/1 22:55
# File : mappings.py
# -*- coding: utf-8 -*-
"""
导入系统业务类型映射。

BusinessType 枚举只定义业务类型的代码和标签。
各平台的操作类型中文别名作为独立的映射字典存在，新增平台只需添加一个字典即可。
"""

from enum import Enum


class BusinessType(Enum):
    """
    业务类型枚举。

    只定义平台无关的核心属性：
        - code: 内部编码
        - label: 通用中文标签
    """

    BUY = ('buy', '买入')
    SELL = ('sell', '卖出')
    DIVIDEND = ('dividend', '分红')
    DIVIDEND_CASH = ('dividend_cash', '现金分红')
    DIVIDEND_REINVEST = ('dividend_reinvest', '红利再投资')
    DEPOSIT = ('deposit', '存入')
    WITHDRAW = ('withdraw', '取出')
    SPLIT = ('split', '拆分/送股')
    BOND_REDEEM = ('bond_redeem', '债券兑付')
    TAX = ('tax', '扣税')
    OTHER = ('other', '其他')

    def __init__(self, code: str, label: str):
        self.code = code
        self.label = label

    @classmethod
    def get_label(cls, code: str) -> str:
        """根据内部编码获取中文标签"""
        return cls[code.upper()].label


# 通用标签字典（所有平台共用）
OP_TYPE_LABEL = {bt.code: bt.label for bt in BusinessType}

# 所有有效的操作类型编码
VALID_OP_TYPES = set(OP_TYPE_LABEL.keys())

# ── 标准模板别名映射 ──
# 用户在标准模板 CSV 中填写的中文 → 内部编码

FUND_OP_MAP = {
    '申购': BusinessType.BUY.code,
    '赎回': BusinessType.SELL.code,
    '现金分红': BusinessType.DIVIDEND_CASH.code,
    '红利再投资': BusinessType.DIVIDEND_REINVEST.code,
    '转入': BusinessType.DEPOSIT.code,
    '转出': BusinessType.WITHDRAW.code,
    '其他收入': BusinessType.DEPOSIT.code,
    '其他支出': BusinessType.WITHDRAW.code,
}

STOCK_OP_MAP = {
    '买入': BusinessType.BUY.code,
    '卖出': BusinessType.SELL.code,
    '现金分红': BusinessType.DIVIDEND_CASH.code,
    '送股': BusinessType.SPLIT.code,
    '其他收入': BusinessType.DEPOSIT.code,
    '其他支出': BusinessType.WITHDRAW.code,
}

# ── 同花顺平台映射 ──
THS_OP_MAP = {
    '证券买入': BusinessType.BUY.code,
    '证券卖出': BusinessType.SELL.code,
    '基金申购拨出': BusinessType.BUY.code,
    '基金赎回拨入': BusinessType.SELL.code,
    '上证LOF申购': BusinessType.BUY.code,
    '开放基金申购': BusinessType.BUY.code,
    '通用回购逆回': BusinessType.BUY.code,
    '资管计划实时': BusinessType.BUY.code,
    '新股入账': BusinessType.BUY.code,
    '配售缴款': BusinessType.BUY.code,
    '资管T0取现拨': BusinessType.SELL.code,
    '债券转股回售': BusinessType.SELL.code,
    '基金红利拨入': BusinessType.DIVIDEND_CASH.code,
    '债券兑息': BusinessType.DIVIDEND_CASH.code,
    '红利入账': BusinessType.DIVIDEND_CASH.code,
    '利息归本': BusinessType.DIVIDEND_CASH.code,
    '配股退款退息': BusinessType.DIVIDEND_CASH.code,
    '转股零款': BusinessType.DIVIDEND_CASH.code,
    '股份转入': BusinessType.DEPOSIT.code,
    '股份转出': BusinessType.WITHDRAW.code,
    '转股入账': BusinessType.SPLIT.code,
    '债券兑付': BusinessType.BOND_REDEEM.code,
    '股息红利差异': BusinessType.TAX.code,
    '股息红利差异扣税': BusinessType.TAX.code,
    '债券兑息兑付': BusinessType.TAX.code,
    '证券蓝补': BusinessType.OTHER.code,
}

# ── 同花顺「有意忽略」操作名（#2854）──
# 券商交割单里有一类非交易记录，本来就该过滤、不该报错。旧映射表
# （core/constants.THS_OP_TYPE_MAP 的「非交易记录（过滤）」段）把它们标成 None，
# 但**活表** THS_OP_MAP 里没有这些键，于是解析器走到「查不到 → return None」时
# 把它们和「新出现的操作名」用同一种静默方式丢掉。两类语义完全不同：
#   - 列在这里：有意忽略，行数对账里单独计数，不报错；
#   - 不在这里且查不到 THS_OP_MAP：未知操作名，必须报 SBImportError（带行号 + 原文）。
# 只收旧表已明确标注的两个名字；新增名字必须附真实券商样本，勿凭直觉扩充。
THS_IGNORED_OPS = frozenset({'指定交易', '指定登记'})

# ── 债券利息类操作（#2836）──
# 语义：**按票面利率定期支付的债券利息**，个人所得税固定 20%（《个人所得税法》
# 「利息、股息、红利所得」），由兑付机构代扣代缴。
#
# 为什么单独列一个集合（不能只靠 business_type 区分）：
#   债券兑息与 A 股「红利入账」都映射到 `dividend_cash`，但两者税率完全不同——
#   股息红利是**按持股期限的差别化税率**（1 个月内 20% / 1 月~1 年 10% / 1 年以上
#   免征），拿 20% 去校验股票分红会大面积误报。故配对规则里「利息」这一侧必须
#   靠本集合细分，而不是 `dividend_cash` 一刀切。
#
# 只收有真实样本的 `债券兑息`（table1101.xls 丰山 90/−18、龙大 220/−44）。
# `利息归本` 语义上是两融利息，不是债券付息，**不收**；`配股退款退息` / `转股零款`
# 是申购退款产生的利息尾差，无个税，**不收**。没有样本的猜测一律不加。
BOND_INTEREST_OPS = frozenset({'债券兑息'})

# 同花顺「场外」操作集合（#1662）：标的是**场外开放式基金**，代码为证监会分配的 6 位
# 裸码，与交易所代码段无关，落库前**不得**加交易所前缀（否则 `004369` 会被推成
# `SZ004369` → 被当成深市股票/转债）。
#
# 为什么只收这一条（证据链，勿凭直觉扩充）：
#   1) `上证LOF申购` 被**单列**为另一个操作类型 → 说明「开放基金申购」不是场内 LOF，
#      而是场外开放式基金；故 `上证LOF申购` 不在本集合（其 501xxx 码走 SH 前缀）。
#   2) `基金申购拨出` / `基金赎回拨入` / `基金红利拨入` **不在**此列：真实样本里它们对应
#      `970164 银河水星现金添利`，而 970164 属 SH 场内货基段（`^97\d{4}$`）——
#      `tests/services/importer/test_ths_stock_parser.py::test_parse_money_fund` 已把
#      「970164 → SH970164 + money_fund」钉死。当场外处理会剥掉 SH 前缀 → 场内货基误判。
#      ⚠️ `app/core/constants.py` 的注释称 `基金申购拨出` 是「场外基金申购」，与本样本
#      冲突，属**项目内部口径矛盾**（已在 #1662 记录），真实样本裁决前不改行为。
#   3) `资管计划实时` / `资管T0取现拨`：无样本证据，不纳入（不猜）。
THS_OTC_OPS = frozenset({'开放基金申购'})

# ── 无代码收益行的资产类型兜底（#2843）──
# 背景：有些「收益到账」行，券商**原文就不给证券代码和名称**（两列皆空），
# 于是拿不到 `suggested_type`，会掉进 `_parse_row` 的 `else: asset_type = 'stock'`。
# 而「股票」是所有可能里最坏的那个答案：类型标签显示成股票、流水计入投资收益、
# 还会因 symbol 为空被前端判「代码未匹配」而勾不上 —— 既导不进，又算不对。
#
# 判据来源（真实样本 table1101.xls，340 条，owner 已确认）：
#   - `利息归本`：无代码无名称，0.90 元。两融利息归本，没有任何标的 → 现金。
#   - `基金红利拨入`：5 条（2.10 / 1.46 / 10.87 / 19.27 / 7.16 元），每月 20 号一笔。
#     开发库中同源的 12 笔历史流水（2023 全年、每月 20~21 号、1.28~6.79 元）**全部**是
#     `asset_type='money_fund'` + `position_name='银河水星现金添利'` + `symbol=NULL`，
#     即 970164 货币基金的月度收益结转。与上方 THS_OTC_OPS 的证据链一致。
#     为什么不是 `cash`：两者走同一条写入分支（orchestrator_commit 的现金管理类）、
#     都不建持仓，但定 cash 会让同一业务在库里出现两种 asset_type，且丢掉
#     「这是货基收益」这唯一的归属线索 —— 而库里已有 money_fund 的先例。
#
# 生效范围：**仅当拿不到 suggested_type 时**（`_parse_row` 的 elif 链最后一档）。
# 带代码的同类行仍由 normalizer 定类型：970164 推出 money_fund、110022 推出 fund，
# 都不会被本表覆盖 —— 本表只兜「券商没给代码」这一种情况。
#
# 已知缺口（不猜）：`债券兑息` 若也缺代码，仍会兜底成 stock；目前无此类样本。
THS_NO_CODE_INCOME_ASSET_TYPES = {
    '利息归本': 'cash',
    '基金红利拨入': 'money_fund',
}

# ── 天天基金平台映射 ──
TIANTIAN_OP_MAP = {
    '买基金': BusinessType.BUY.code,
    '超级转换-转入': BusinessType.BUY.code,
    '普通转入': BusinessType.BUY.code,
    '充值': BusinessType.BUY.code,
    '活期宝即充即用': BusinessType.BUY.code,
    '超级转换份额调增': BusinessType.BUY.code,
    '卖基金': BusinessType.SELL.code,
    '强赎': BusinessType.SELL.code,
    '超级转换份额调减': BusinessType.SELL.code,
    '超级转换-转出': BusinessType.SELL.code,
    '普通取现': BusinessType.SELL.code,
    '普通转出': BusinessType.SELL.code,
    '现金分红': BusinessType.DIVIDEND_CASH.code,
    '红利再投资': BusinessType.DIVIDEND_REINVEST.code,
    '活动发放': BusinessType.DEPOSIT.code,
    '其他收入': BusinessType.DEPOSIT.code,
    '其他支出': BusinessType.WITHDRAW.code,
}

ALIPAY_PDF_OP_MAP = {
    '用户买入': BusinessType.BUY.code,
    '用户卖出': BusinessType.SELL.code,
    '营销买入': BusinessType.BUY.code,
    '用户跨TA转换': BusinessType.BUY.code,  # 暂归入申购
    '机构分红': BusinessType.DIVIDEND_CASH.code,
}

# ── 支付宝平台映射 ──
# 根据“商品名称”列的关键字匹配交易类型
ALIPAY_OP_MAP = {
    # 基金申购
    '买入': BusinessType.BUY.code,
    '转入': BusinessType.BUY.code,  # 余额宝转入
    '基金申购': BusinessType.BUY.code,
    '转入余额宝': BusinessType.BUY.code,
    # 基金赎回
    '卖出至余额宝': BusinessType.SELL.code,
    '卖出': BusinessType.SELL.code,
    '理财赎回': BusinessType.SELL.code,
    '转出': BusinessType.SELL.code,
    # 分红
    '现金分红至余额宝': BusinessType.DIVIDEND_CASH.code,
    '现金分红': BusinessType.DIVIDEND_CASH.code,
    # 余额宝收益
    '收益发放': BusinessType.DEPOSIT.code,
    # 资金存取
    '转出到银行卡': BusinessType.WITHDRAW.code,
    '银行卡转入': BusinessType.DEPOSIT.code,
    '单次转入': BusinessType.DEPOSIT.code,
    '大额转入': BusinessType.DEPOSIT.code,
    '工资理财': BusinessType.DEPOSIT.code,
    '自动转入': BusinessType.DEPOSIT.code,
    '转账收款到余额宝': BusinessType.DEPOSIT.code,
    # 其他
    '退款': BusinessType.DEPOSIT.code,
    '活动发放': BusinessType.DEPOSIT.code,
    '红包奖励发放': BusinessType.DEPOSIT.code,
    '账户结息': BusinessType.DEPOSIT.code,  # 网商银行计息
    '蚂蚁星愿主动攒入': BusinessType.DEPOSIT.code,
    '蚂蚁星愿自动攒入': BusinessType.DEPOSIT.code,
    '钱管家转入': BusinessType.DEPOSIT.code,
    '笔笔攒': BusinessType.DEPOSIT.code,
    '收益挑战包卖出': BusinessType.SELL.code,
    '收益挑战包买入': BusinessType.BUY.code,
}

# ── 招商证券平台映射（2026-11-07，真实交割单 522 行逐行实证）──
#
# 口径纪律：只收**有真实资金变动、且能落到确定标的**的业务名。其余不是「不认识」，
# 而是「认识但当前不能正确入账」——放进 CMS_IGNORED_OPS 显式忽略并计入行数对账，
# 绝不静默丢行，也绝不为了「看起来导入得多」而编造口径。
CMS_OP_MAP = {
    '证券买入': BusinessType.BUY.code,
    '证券卖出': BusinessType.SELL.code,
    '股息入账': BusinessType.DIVIDEND_CASH.code,
    '利息归本': BusinessType.DIVIDEND_CASH.code,
}

# 银证转账：券商侧现金进出，落 cash + deposit/withdraw，由编排器在银行侧生成反向流水。
# 方向以「发生金额」正负判定（样本：银行转存恒正、银行转取恒负），不按操作名硬编码。
CMS_CASH_TRANSFER_OPS = frozenset({'银行转存', '银行转取'})

# ── 招商证券「申购中签事件」声明（跨券商折叠器 IpoEventPolicy 的实参）──
#
# 打新是**一次建仓事件被拆成 N 行**，不是 N 笔流水：整体忽略会让上市后卖出没有
# 成本来源（实证：6 笔中签对应 6 笔清仓卖出，其中至少 4 笔库内无任何买入/入账
# 记录，只能落孤儿流水）；逐行导入又会把「扣款 −1000 / 回冲 +1000」重复计现金流、
# 并让金额 0 的中签行卡在 validate。故交给 ipo_events.py 折叠成一条标准 buy，
# 本金取组内净现金流、份额取「本金 ÷ 中签价」。
#
# 券商原文用申购代码（072/370/754/783 段），与上市代码（113/123/127/128 段）不同
# 且**文件内无法可靠关联**（同名配对 0 对、流水号不共享、日期间隔不定）。这一层由
# SymbolAliasResolver 承担，候选不唯一时保留申购码 + link_warning 让用户补全。
CMS_IPO_ANCHOR_OPS = frozenset({'市值申购中签'})  # 开新事件，并提供中签价（样本恒 100）
CMS_IPO_CASH_OPS = frozenset(
    {
        '市值申购中签',  # 金额 0
        '市值申购中签扣款',  # −1000
        '市值申购中签扣款回冲',  # +1000（冲正对）
        '新股申购确认缴款',  # −1000
        '托管转出',  # 金额 0
    }
)
CMS_IPO_CREDIT_OPS = frozenset({'新股入账'})  # 携带上市代码，不参与申购码分组
CMS_IPO_MEMBER_OPS = CMS_IPO_ANCHOR_OPS | CMS_IPO_CASH_OPS | CMS_IPO_CREDIT_OPS
CMS_IPO_PRICE_OP = '市值申购中签'
# 可转债上市代码段；用于判定「新股入账」行是否可作上市代码候选。
CMS_IPO_LISTED_CODE_PREFIXES = ('110', '111', '113', '118', '123', '127', '128', '132')

# ── 招商证券「有意忽略」业务名（同 THS_IGNORED_OPS 语义）──
# 列在这里 = 有样本、确认过不能按标准交易入账；不在 CMS_OP_MAP、也不在
# CMS_IPO_MEMBER_OPS 的新业务名一律抛 UnknownOperationError → 带行号与原文的
# SBImportError，绝不静默丢行。
#
# 报价回购（拆出 / 购回卖，共 121 行）忽略，两条硬理由：①标的多为 JXB001（券商现金
# 管理产品编号，非 6 位证券代码），normalizer 无法归一；②「成交价格」是年化收益率
# 而非每份净值（样本：价 1.38 × 数量 20 = 27.6，而发生金额 2000），按 份额×净值
# 入账会把 2000 元记成 27.6 元。它需单独的资产类型与计量口径，不能硬套股票买卖。
CMS_IGNORED_OPS = frozenset(
    {
        '申购配号',  # 新股配号，无资金变动、无持仓变动（样本 90 行），不属于中签事件
        '报价回购拆出',
        '报价购回卖',
    }
)

# 券商原文**不给证券代码/名称**的收益行资产类型兜底（同 THS_NO_CODE_INCOME_ASSET_TYPES）。
# 判据：仅当代码为空时生效；兜成 'stock' 会让它显示成股票、计入投资收益，
# 又因 symbol 为空被前端判「代码未匹配」而永远勾不上。
CMS_NO_CODE_INCOME_ASSET_TYPES = {
    '利息归本': 'cash',  # 资金账户结息，无标的、无持仓
}
