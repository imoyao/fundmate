# backend/app/core/constants.py
"""项目级常量定义（汇率、标签映射、桑基图节点名称等）"""

# ── 汇率（MVP 阶段硬编码，后续可迁移到数据库）──
EXCHANGE_RATES = {
    'CNY': 1.0,
    'USD': 7.25,
    'HKD': 0.92,
}

# ── 产品类型标签（交易性资产）──
TYPE_LABELS = {
    'stock': '股票',
    'fund': '基金',
    'bond': '可转债',
    'crypto': '虚拟货币',
    'saving': '银行存款',
    'cash': '现金',
    'static': '其他',
}

# ── 市场标签 ──
MARKET_LABELS = {
    'CN_A': 'A股',
    'CN_HK': '港股',
    'US': '美股',
    'CRYPTO': '虚拟币',
}

# ── 五笔钱 / 配置目标标签 ──
ALLOCATION_LABELS = {
    'liquid': '活钱',
    'stable': '稳健底仓',
    'longterm': '长期增值',
    'speculative': '高风险博弈',
    'security': '保险保障',
}

# ── 通用资产大类标签 ──
ASSET_CATEGORY_LABELS = {
    'cash': '流动资金',
    'fixed': '固定资产',
    'investment': '投资理财',
    'receivable': '应收款',
    'liability': '负债',
    'insurance': '保险项目',
}

# ── 桑基图节点名称常量 ──
K_TOTAL = '总资产'
K_NET = '净资产'
K_LIABILITY = '总负债'
K_UNCONFIGURED = '未配置资产'
K_LONGTERM = '长期增值'

# ── 桑基图资产大类元组（名称，颜色键已废弃，保留兼容）──
CATEGORY_META = {
    'cash': ('流动资金', None),
    'fixed': ('固定资产', None),
    'investment': ('投资理财', None),
    'receivable': ('应收款', None),
    'insurance': ('保险项目', None),
}

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
    'deposit': '存入',
    'withdraw': '取出',
    'split': '拆分',
    'bond_redeem': '债券兑付',
    'tax': '扣税',
    'other': '其他',
}


# 批量导入常量定义
CASH_SYMBOL = '__CASH__'
DEFAULT_THS_ACCOUNT = '默认证券账户'
DEFAULT_MARKET_CN = 'CN_A'
DEFAULT_TYPE_CASH = 'cash'
DEFAULT_TYPE_STOCK = 'stock'
