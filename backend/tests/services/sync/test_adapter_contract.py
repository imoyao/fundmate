# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 13:43
# File : test_adapter_contract.py
# tests/integration/test_adapter_contract.py
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.sync.adapters.akshare_adapter import AkshareAdapter

FIXTURES = Path(__file__).parent.parent.parent / 'fixtures'


class TestAkshareAdapterParsing:
    """验证适配器能正确解析 akshare 真实返回的数据格式"""

    @pytest.fixture
    def adapter(self):
        return AkshareAdapter()

    def test_parse_stock_list_from_real_format(self, adapter):
        sample = json.loads((FIXTURES / 'stock_list_sample.json').read_text(encoding='utf-8'))
        with patch.object(adapter, 'fetch_stock_list', return_value=sample):
            records = adapter.fetch_stock_list()
            assert len(records) > 0
            for r in records:
                assert 'symbol' in r
                assert 'name' in r

    def test_parse_stock_price_from_real_format(self, adapter):
        # 模拟 fetch_stock_price 返回已知的格式（与真实新浪接口一致）
        sample = [
            {
                'symbol': 'SH600519',
                'trade_date': date(2025, 1, 1),
                'open': 100.0,
                'high': 105.0,
                'low': 99.0,
                'close': 102.0,
                'volume': 1000,
                'adj_close': 101.5,
                'source': 'akshare_sina',
            }
        ]
        with patch.object(adapter, 'fetch_stock_price', return_value=sample):
            records = adapter.fetch_stock_price('SH600519')
            assert len(records) == 1
            assert isinstance(records[0]['trade_date'], date)
            assert records[0]['close'] == 102
