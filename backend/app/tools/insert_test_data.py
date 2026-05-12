# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2026/5/12 23:03
# File : insert_test_data.py
"""插入标准化的证券和基金测试数据"""

from app.core.database import SessionLocal
from app.core.symbol_utils import get_normalizer
from app.domains.funds.models import Fund
from app.domains.securities.models import Security

normalizer = get_normalizer()
db = SessionLocal()

# 1. 清空证券表（测试环境，直接重建）
db.query(Security).delete()
db.commit()

# 2. 证券测试数据（原始输入 → 标准化）
securities_input = [
    ('00700.HK', '腾讯控股', 'stock'),
    ('600519', '贵州茅台', 'stock'),
    ('000001', '平安银行', 'stock'),  # 深交所
    ('300750', '宁德时代', 'stock'),
    ('510050', '上证50ETF', 'stock'),  # ETF 按 stock 存储
    ('AAPL', '苹果公司', 'stock'),
    ('TSLA', '特斯拉', 'stock'),
    ('110038', '济川转债', 'bond'),
    ('SH688001', '华兴源创', 'stock'),  # 科创板
]

for raw, name, typ in securities_input:
    norm, market = normalizer.normalize(raw)
    if norm:
        # 避免重复插入（基于标准化符号）
        if not db.query(Security).filter_by(symbol=norm).first():
            db.add(Security(symbol=norm, name=name, market=market, type=typ))

# 3. 基金测试数据
funds = [
    {'fund_code': '000001', 'name': '华夏成长混合', 'pinyin_abbr': 'HXCZ'},
    {'fund_code': '000002', 'name': '华夏大盘精选', 'pinyin_abbr': 'HXDP'},
    {'fund_code': '110011', 'name': '易方达中小盘', 'pinyin_abbr': 'YFDZXP'},
    {'fund_code': '001714', 'name': '工银瑞信灵活配置', 'pinyin_abbr': 'GYRX'},
]
for f in funds:
    if not db.query(Fund).filter_by(fund_code=f['fund_code']).first():
        db.add(Fund(**f))

db.commit()
db.close()
print('✅ 标准化测试数据已插入，包含港股、A股、美股、可转债及基金')
