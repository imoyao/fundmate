# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/5/30 13:43
# File : test_adapter_contract.py
# tests/integration/test_adapter_contract.py
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from app.services.sync.adapters.akshare_adapter import AkshareAdapter

FIXTURES = Path(__file__).parent.parent.parent / 'fixtures'


class TestAkshareAdapterParsing:
    """验证适配器能正确解析 akshare 真实返回的数据格式"""

    @pytest.fixture
    def adapter(self):
        return AkshareAdapter()

    def test_parse_stock_list_from_real_format(self, adapter):
        """用真实接口返回的 DataFrame 格式验证解析逻辑"""
        # 加载真实样本
        sample = json.loads((FIXTURES / 'stock_list_sample.json').read_text(encoding='utf-8'))
        df = pd.DataFrame(sample)

        # mock akshare 返回这个真实样本
        with patch.object(adapter, 'fetch_stock_list', wraps=adapter.fetch_stock_list) as mocked:
            # 直接验证我们的 DataFrame → records 转换逻辑
            # 这里不调接口，而是验证 adapter 内部的解析方法
            records = adapter._parse_stock_list_df(df)
            assert len(records) > 0
            for r in records:
                assert 'symbol' in r
                assert 'name' in r
                assert isinstance(r['symbol'], str)

    def test_parse_stock_price_from_real_format(self, adapter):
        """验证行情数据日期类型处理正确"""
        sample = json.loads((FIXTURES / 'stock_price_sample.json').read_text(encoding='utf-8'))
        df = pd.DataFrame(sample)
        # 确保日期列被正确解析为 Timestamp（模拟 akshare 返回）
        df['日期'] = pd.to_datetime(df['日期'])

        records = adapter._parse_stock_price_df('SH600519', df)
        assert len(records) > 0
        for r in records:
            assert isinstance(r['trade_date'], date)
            assert r['close'] is not None
