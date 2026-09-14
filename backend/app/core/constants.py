# backend/app/core/constants.py
"""项目级常量定义（汇率、标签映射、桑基图节点名称等）

注意：`CURRENT_USER_ID` 已随 v4.7 多用户化退役（见 docs/spec/decisions.md D1），
当前用户一律从 Flask `g` 上下文取（app/core/auth.py），禁止再引入硬编码常量。
"""

from enum import Enum

from app.core.asset_types import ASSET_CATEGORY_LABELS, ASSET_TYPE_LABELS

# 兼容历史 import：core/constants.TYPE_LABELS 曾为资产类型标签的别名，现统一指向 asset_types
TYPE_LABELS = ASSET_TYPE_LABELS

# ── 自选/搜索标的代码命名空间（#1286）──
# 基金经理在 watchlist.symbol（及搜索 code）中统一表示为 'MGR_' + managers.mgr_code，
# 与场内 SH/SZ 码、场外 6 位基金码、投顾组合平台原生码（ZHxxxx/CSIxxxx）隔离命名空间，
# 防不同实体空间的代码碰撞。展示名解析须剥离该前缀回查 managers 表
# （见 services/watchlist_service.lookup_manager / resolve_display_name 唯一实现），
# 否则会把 sha256 派生码直接甩给用户。
MANAGER_SYMBOL_PREFIX = 'MGR_'

# ── 汇率（MVP 阶段硬编码，后续可迁移到数据库）──
EXCHANGE_RATES = {
    'CNY': 1.0,
    'USD': 7.25,
    'HKD': 0.92,
}

# ── 货基万份收益写入来源版本标记（#863 P0-4）──
# fund_nav_job / async_backfill 共用，避免 'v2_recalc' 字符串在多处硬编码漂移。
SOURCE_VERSION_V2_RECALC = 'v2_recalc'

# ── 产品类型标签（交易性资产）──
# 单一权威定义已收口到 app/core/asset_types.ASSET_TYPE_LABELS（本文件顶部已从该处 import，别名 TYPE_LABELS）；
# bond 已澄清为「可转债」。新增 / 修改类型标签请改 asset_types.py，勿在此手写。


LEDGER_TYPE_LABELS = {
    'bank': '银行账户',
    'stock': '证券账户',
    'fund': '基金',
    'e_account': '基金E账户',
    'property': '实物资产',
}

# ── 市场标签 ──
# 兼容两套市场词表：securities 域的 CN_A/CN_HK/US/CRYPTO/COMMODITY 与
# 交易所维度的 SH/SZ/HK/US（自选/前端展示用）。'' 为无市场实体
# （基金经理/投顾组合，#1286）的约定取值。
MARKET_LABELS = {
    'CN_A': 'A股',
    'CN_HK': '港股',
    'US': '美股',
    'CRYPTO': '虚拟币',
    'SH': '沪市',
    'SZ': '深市',
    'HK': '港股',
    'COMMODITY': '大宗商品',
    # 指数名录三源合并（#1365）：中证/国证专属代码的命名空间前缀
    'CSI': '中证',
    'CNI': '国证',
    '': '通用',
}

# ── 五笔钱 / 配置目标标签 ──
ALLOCATION_LABELS = {
    'liquid': '活钱',
    'stable': '稳健底仓',
    'longterm': '长期增值',
    'speculative': '高风险博弈',
    'security': '保险保障',
}

# ── 且慢「四笔钱」→ 五笔钱（ALLOCATION_LABELS）映射（#1468）──
# 且慢组合自带的 活钱/稳钱/长钱 分类，映射到本系统 assets/positions 的 allocation 词表，
# 避免为投顾组合另立一套并行分类。注册表 advisor_catalog 的 bucket 字段经此归一。
QIEMAN_BUCKET_TO_ALLOCATION = {
    '活钱': 'liquid',
    '稳钱': 'stable',
    '长钱': 'longterm',
}

# ── 通用资产大类标签 ──
# 已收口到 app/core/asset_types.ASSET_CATEGORY_LABELS（本文件顶部 import），勿在此手写。

# ── 桑基图节点名称常量 ──
K_TOTAL = '总资产'
K_NET = '净资产'
K_LIABILITY = '总负债'
K_UNCONFIGURED = '未配置资产'
K_LONGTERM = '长期增值'

# ── 桑基图资产大类元组（名称，颜色键已废弃，保留兼容）──
# 标签与 ASSET_CATEGORY_LABELS 单一来源保持一致；liability 由 summary 单独处理，不进大类分布。
CATEGORY_META = {k: (v, None) for k, v in ASSET_CATEGORY_LABELS.items() if k != 'liability'}

# 同花顺操作类型 → 内部 op_type 映射
THS_OP_TYPE_MAP = {
    # ── 买入类 ──
    '证券买入': 'buy',  # 股票买入
    '基金申购拨出': 'buy',  # 场外基金申购（资金拨出）
    '上证LOF申购': 'buy',  # LOF基金申购
    '开放基金申购': 'buy',  # 开放式基金申购
    '通用回购逆回': 'buy',  # 逆回购买入（T日操作）
    '资管计划实时': 'buy',  # 资管产品申购
    '新股入账': 'buy',  # 新股中签缴款确认
    '配售缴款': 'buy',  # 配股缴款确认
    '股份转入': 'deposit',  # 股份转入账户（非交易，但产生持仓）
    # ── 卖出类 ──
    '证券卖出': 'sell',  # 股票卖出
    '基金赎回拨入': 'sell',  # 场外基金赎回（资金拨入）
    '资管T0取现拨': 'sell',  # 资管产品赎回
    '债券转股回售': 'sell',  # 可转债回售给发行人
    '股份转出': 'withdraw',  # 股份转出账户（持仓减少）
    # ── 分红/收益类 ──
    '基金红利拨入': 'dividend',  # 基金现金分红
    '债券兑息': 'dividend',  # 债券付息
    '红利入账': 'dividend',  # 股票现金分红
    '利息归本': 'dividend',  # 银行存款/理财利息入账
    '配股退款退息': 'dividend',  # 配股退款或利息退还
    '转股零款': 'dividend',  # 转股后零头退款
    # ── 债券兑付（一次性还本付息）──
    '债券兑付': 'bond_redeem',
    # ── 扣税/支出类 ──
    '股息红利差异': 'tax',
    '股息红利差异扣税': 'tax',
    '债券兑息兑付': 'tax',
    # ── 拆分/转换类 ──
    '转股入账': 'split',
    # ── 需用户手动处理 ──
    '证券蓝补': 'other',  # 券商补录历史数据，数据可能不完整
    # ── 资金划转（解析器内部特殊处理，不在映射表中使用）──
    '银行转证券': None,
    '证券转银行': None,
    'OTC资金划出': None,
    'OTC资金划入': None,
    'OTC现金宝交': None,
    'OTC资管转让': None,
    # ── 非交易记录（过滤）──
    '指定交易': None,
    '指定登记': None,
}
# 新增other类型的标签
OP_TYPE_LABEL = {
    'buy': '买入',
    'sell': '卖出',
    'dividend': '分红',
    'dividend_reinvest': '红利再投资',
    'deposit': '存入',
    'withdraw': '取出',
    'split': '送股/拆分',
    'bond_redeem': '债券兑付',
    'tax': '扣税',
    'other': '其他',
}

# ── 投顾组合调仓操作类型（#1167 / #1468）──
# 天天基金 adjustList 的 operationInt 与且慢「快照序列推导」共用同一词表，为单一真相源；
# 禁止在适配器 / job 内各自硬编码一份（历史上 adapter 与 scripts 各存过一份）。
ADVISOR_ADJUST_OP_NAME = {1: '建仓', 2: '加仓', 3: '减仓', 4: '新增', 5: '持平'}


# 批量导入常量定义
CASH_SYMBOL = '__CASH__'
DEFAULT_THS_ACCOUNT = '默认证券账户'
DEFAULT_MARKET_CN = 'CN_A'
DEFAULT_TYPE_CASH = 'cash'
DEFAULT_TYPE_STOCK = 'stock'

# ── 网络请求通用 ──
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
DEFAULT_REQUEST_TIMEOUT = 15

# ── 来源标识（全系统，positions.source / transactions.source / PositionImportMeta.source 共用）──
# 维护入口（唯一真相源）：所有写入来源的代码都必须引用本枚举，禁止在各处硬编码字符串字面量。
# 取值语义见 POSITION_SOURCE_LABELS。前端通过 GET /api/utils/enums 获取 label，禁止前端手抄一份。
# 本枚举为「全系统来源标识」，positions 与 transactions 两表共用（#1232 决策 11），
# 避免「同一个 manual 在两表含义不同」的歧义。


class PositionSource(str, Enum):
    MANUAL = 'manual'  # 用户在持仓/账户页手动录入
    E_ACCOUNT = 'e_account_holding'  # 基金E账户持仓导入
    BROKER_TIANTIAN = 'tiantian_fund'  # 天天基金导出导入
    BROKER_THS = 'ths_stock'  # 同花顺导出导入
    BROKER_STD_FUND = 'standard_fund'  # 标准模板-基金导入
    BROKER_STD_STOCK = 'standard_stock'  # 标准模板-股票导入
    BROKER_ALIPAY = 'alipay_fund'  # 支付宝基金导出导入
    BROKER_ALIPAY_PDF = 'alipay_pdf'  # 支付宝 PDF 导入
    BROKER_STD_TEMPLATE = 'standard_template'  # 通用标准模板导入
    AI_TXN = 'ai_txn'  # AI 交易流水识别（ocr，最终合并进持仓）
    AI_HOLDING = 'ai_holding'  # AI 持仓识别
    EXPLORE = 'explore'  # 探市页面用户录入
    RECONCILIATION_ADJUSTMENT = 'reconciliation_adjustment'  # 对账补录/调整（统一对账工作台，域 B/C）


# 单一真相源：PositionSource.value -> 中文 label，仅在此处维护
POSITION_SOURCE_LABELS: dict[str, str] = {
    PositionSource.MANUAL.value: '手动录入',
    PositionSource.E_ACCOUNT.value: '基金E账户导入',
    PositionSource.BROKER_TIANTIAN.value: '天天基金导入',
    PositionSource.BROKER_THS.value: '同花顺导入',
    PositionSource.BROKER_STD_FUND.value: '标准模板-基金',
    PositionSource.BROKER_STD_STOCK.value: '标准模板-股票',
    PositionSource.BROKER_ALIPAY.value: '支付宝基金导入',
    PositionSource.BROKER_ALIPAY_PDF.value: '支付宝PDF导入',
    PositionSource.BROKER_STD_TEMPLATE.value: '标准模板导入',
    PositionSource.AI_TXN.value: 'AI交易识别',
    PositionSource.AI_HOLDING.value: 'AI持仓识别',
    PositionSource.EXPLORE.value: '探市录入',
    PositionSource.RECONCILIATION_ADJUSTMENT.value: '对账补录',
}


class ValuationMode(str, Enum):
    """持仓计价模式（#1174 / 决策 D1 方案 A）。

    决定一笔持仓的市值如何计算——有公开净值的走份额模型，无净值的走余额模型。
    禁止在各处硬编码 'nav' / 'balance' 字符串字面量。
    """

    NAV = 'nav'  # 份额×净值：基金/证券等有公开净值的标的
    BALANCE = 'balance'  # 直接余额：投顾/银行理财等无公开净值的标的，市值靠人工录入总价


# 单一真相源：ValuationMode.value -> 中文 label，仅在此处维护
VALUATION_MODE_LABELS: dict[str, str] = {
    ValuationMode.NAV.value: '份额×净值',
    ValuationMode.BALANCE.value: '直接余额',
}
