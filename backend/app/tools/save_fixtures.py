"""生成用于测试的真实样本数据（通过适配器封装）"""

import json
from pathlib import Path

from app.services.sync.adapters.akshare_adapter import AkshareAdapter

fixtures = Path('tests/fixtures')
fixtures.mkdir(parents=True, exist_ok=True)

adapter = AkshareAdapter()

# 1. 股票列表样本
stock_list = adapter.fetch_stock_list()
# 只取前 10 条，并转换为可 JSON 序列化的格式
sample_stocks = stock_list[:10]
with open(fixtures / 'stock_list_sample.json', 'w', encoding='utf-8') as f:
    json.dump(sample_stocks, f, ensure_ascii=False, indent=2, default=str)
print(f'股票列表样本已保存 ({len(sample_stocks)} 条)')

# 2. 历史行情样本（使用封装方法，不传日期获取全部历史）
#    注意：这里我们只取一只代表性股票来保存样本
price_records = adapter.fetch_stock_price('SH600519')
# 行情数据量可能很大，只保存前 10 条
sample_prices = price_records[:10]
with open(fixtures / 'stock_price_sample.json', 'w', encoding='utf-8') as f:
    json.dump(sample_prices, f, ensure_ascii=False, indent=2, default=str)
print(f'历史行情样本已保存 ({len(sample_prices)} 条)')

# 3. （可选）基金列表样本，如果接口可用
try:
    fund_list = adapter.fetch_fund_list()
    sample_funds = fund_list[:10]
    with open(fixtures / 'fund_list_sample.json', 'w', encoding='utf-8') as f:
        json.dump(sample_funds, f, ensure_ascii=False, indent=2, default=str)
    print(f'基金列表样本已保存 ({len(sample_funds)} 条)')
except Exception as e:
    print(f'基金列表样本保存失败: {e}')
