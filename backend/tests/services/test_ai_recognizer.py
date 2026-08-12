# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/13
# File : test_ai_recognizer.py
"""AI 识别域（ai_recognizer）分层架构测试：注册表 / TxnRecognizer / scenario API。

覆盖（ai-recognizer-architecture-2026-08-13.md P3/P4）：
    - 注册表：默认场景回退、txn 场景注册；
    - TxnRecognizer 正则层（「代码 名称 买卖 金额」简单排版零成本）；
    - TxnRecognizer LLM 层（mock llm.call_llm）：买卖归一、日期抢救、无效行丢弃；
    - scenario API：/api/ocr/parse?scenario=txn_import 返回 importer 预览行；
    - 用量按 feature 独立限次（ocr_import / txn_import 互不影响）。
"""

from datetime import date

import pytest

from app.domains.usage.models import UserUsage
from app.services.ai_recognizer import catalog, guards
from app.services.ai_recognizer import llm as llm_module
from app.services.ai_recognizer.recognizers.txn_recognizer import TxnRecognizer
from app.services.ai_recognizer.recognizers.watchlist_recognizer import WatchlistRecognizer
from app.services.ai_recognizer.registry import get_recognizer, get_scenarios


@pytest.fixture(autouse=True)
def _reset_guards(monkeypatch):
    """重置限流/熔断/token 预算状态，避免用例间相互干扰（同 test_ocr_import 口径）。"""
    monkeypatch.setattr(guards, 'OCR_RATE_LIMIT_MAX', 1000)
    monkeypatch.setattr(guards, 'OCR_MELTDOWN_THRESHOLD', 1000)
    guards._RATE_LIMIT_BUCKETS.clear()
    guards._MELTDOWN_STATE.clear()
    guards._token_used_today = 0
    yield
    guards._RATE_LIMIT_BUCKETS.clear()
    guards._MELTDOWN_STATE.clear()
    guards._token_used_today = 0


class TestRegistry:
    """场景注册表（registry.py）."""

    def test_scenarios_registered(self):
        assert set(get_scenarios()) == {'watchlist_import', 'txn_import'}

    def test_default_scenario_fallback(self):
        assert get_recognizer(None) is get_recognizer('watchlist_import')

    def test_unknown_scenario_falls_back(self):
        assert get_recognizer('no_such_scenario').key == 'watchlist_import'

    def test_recognizers_are_singletons_per_key(self):
        assert isinstance(get_recognizer('watchlist_import'), WatchlistRecognizer)
        assert isinstance(get_recognizer('txn_import'), TxnRecognizer)


class TestTxnRegexExtract:
    """持仓场景正则层：简单排版零成本提取（不调 LLM）。"""

    def test_regex_line_with_name(self, db, monkeypatch):
        called = {'n': 0}

        def _fake_llm(content, system_prompt, **kw):
            called['n'] += 1
            return '[]'

        monkeypatch.setattr(llm_module, 'call_llm', _fake_llm)
        recognizer = get_recognizer('txn_import')
        items = recognizer.recognize_text('110011 易方达中小盘 买入 5000')
        assert called['n'] == 0  # 正则层命中，未调 LLM
        assert items[0]['code'] == '110011'
        assert items[0]['business_type'] == 'buy'
        assert items[0]['amount'] == 5000.0
        assert items[0]['type'] == 'fund'  # enrich 反查兜底

    def test_regex_stock_sell_line(self, db, monkeypatch):
        recognizer = get_recognizer('txn_import')
        items = recognizer.recognize_text('600519 贵州茅台 卖出 100股')
        assert items[0]['code'] == '600519'
        assert items[0]['business_type'] == 'sell'

    def test_regex_complex_format_falls_to_llm(self, db, monkeypatch):
        """名称在前/金额带单位等复杂排版：正则不匹配 → LLM 兜底。"""
        monkeypatch.setattr(
            llm_module,
            'call_llm',
            lambda content, system_prompt, **kw: (
                '[{"code":"161725","name":"招商中证白酒","business_type":"买入",'
                '"trade_date":"2026-08-01","amount":1000}]'
            ),
        )
        recognizer = get_recognizer('txn_import')
        items = recognizer.recognize_text('今天买入招商中证白酒 161725，金额 1000 元')
        assert items[0]['code'] == '161725'
        assert items[0]['business_type'] == 'buy'


class TestTxnExtractValidate:
    """TxnRecognizer LLM 输出提取与清洗（mock）。"""

    def _recognize(self, monkeypatch, raw):
        monkeypatch.setattr(llm_module, 'call_llm', lambda content, system_prompt, **kw: raw)
        return get_recognizer('txn_import').recognize_text('今天买入 110011 五千元')

    def test_buy_parsing(self, db, monkeypatch):
        items = self._recognize(
            monkeypatch,
            '[{"code":"110011","name":"易方达中小盘","business_type":"买入",'
            '"trade_date":"2026-08-01","amount":5000,"shares":4526.51,"nav":1.1046}]',
        )
        assert items[0]['business_type'] == 'buy'
        assert items[0]['trade_date'] == '2026-08-01'
        assert items[0]['amount'] == 5000
        assert items[0]['shares'] == 4526.51
        # 反查：Funds 表未收录 → 兜底 type=fund / venue=OTC
        assert items[0]['type'] == 'fund'
        assert items[0]['venue'] == 'OTC'

    def test_sell_parsing_redraw_synonyms(self, db, monkeypatch):
        items = self._recognize(
            monkeypatch,
            '[{"code":"110011","name":"易方达中小盘","business_type":"赎回","trade_date":"2026/08/05","amount":5000}]',
        )
        assert items[0]['business_type'] == 'sell'
        assert items[0]['trade_date'] == '2026-08-05'  # 斜杠日期规范化

    def test_garbage_date_cleared(self, db, monkeypatch):
        items = self._recognize(
            monkeypatch,
            '[{"code":"110011","name":"易方达中小盘","business_type":"买入","trade_date":"不知道","amount":1000}]',
        )
        assert items[0]['trade_date'] == ''

    def test_unknown_business_type_dropped(self, db, monkeypatch):
        items = self._recognize(
            monkeypatch,
            '[{"code":"110011","name":"易方达中小盘","business_type":"转股","trade_date":"2026-08-01","amount":1000}]',
        )
        assert items == []  # 非支持类型整行丢弃

    def test_missing_amount_and_shares_dropped(self, db, monkeypatch):
        """既无金额也无份额 → 不是可入账交易，整行丢弃。"""
        items = self._recognize(
            monkeypatch,
            '[{"code":"110011","name":"易方达中小盘","business_type":"买入","trade_date":"2026-08-01"}]',
        )
        assert items == []

    def test_negative_amount_cleared_to_none_but_kept_with_shares(self, db, monkeypatch):
        """金额识别为负数 → 金额清空；份额有效则行保留（金额/份额至少其一）。"""
        items = self._recognize(
            monkeypatch,
            '[{"code":"110011","name":"易方达中小盘","business_type":"买入",'
            '"trade_date":"2026-08-01","amount":-100,"shares":4526.51}]',
        )
        assert items[0]['amount'] is None
        assert items[0]['shares'] == 4526.51


class TestCatalogPreservesTxnFields:
    """catalog.enrich 透传持仓字段（重构时新增行为，供 txn 下游管线使用）。"""

    def test_extra_fields_survive(self, db):
        from app.domains.funds.models import Fund

        db.add(Fund(fund_code='110011', name='易方达中小盘混合'))
        db.commit()
        items = catalog.enrich(
            [
                {
                    'code': '110011',
                    'name': '易方达中小盘',
                    'business_type': 'buy',
                    'amount': 5000,
                    'shares': 4526.51,
                    'trade_date': '2026-08-01',
                }
            ]
        )
        row = items[0]
        assert row['type'] == 'fund'
        assert row['venue'] == 'OTC'
        assert row['symbol'] == '110011'
        # 持仓字段透传保留
        assert row['business_type'] == 'buy'
        assert row['amount'] == 5000
        assert row['shares'] == 4526.51
        assert row['trade_date'] == '2026-08-01'


class TestTxnScenarioAPI:
    """scenario=txn_import 的 API 闭环（mock LLM）：返回 importer 预览行 + 独立用量。"""

    def test_parse_txn_scenario_returns_rows(self, client, db, monkeypatch):
        monkeypatch.setattr(
            llm_module,
            'call_llm',
            lambda content, system_prompt, **kw: (
                '[{"code":"110011","name":"易方达中小盘","business_type":"买入",'
                '"trade_date":"2026-08-01","amount":5000,"shares":4526.51,"nav":1.1046}]'
            ),
        )
        resp = client.post('/api/ocr/parse', json={'text': '今天买入 5000', 'scenario': 'txn_import'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['scenario'] == 'txn_import'
        rows = data['rows']
        assert len(rows) == 1
        assert rows[0]['symbol'] == '110011'
        assert rows[0]['op_type'] == 'buy'
        assert rows[0]['op_type_label'] == '买入'
        assert rows[0]['trade_date'] == '2026-08-01'
        assert rows[0]['amount'] == 5000
        assert rows[0]['quantity'] == 4526.51
        assert rows[0]['source'] == 'ai_txn'
        assert data['usage']['used'] == 1

    def test_txn_usage_independent_of_watchlist(self, client, db, monkeypatch):
        """txn_import 与 ocr_import 用量独立（user_usage 按 feature 分桶）。"""
        monkeypatch.setattr(
            llm_module,
            'call_llm',
            lambda content, system_prompt, **kw: (
                '[{"code":"110011","name":"易方达中小盘","business_type":"买入","amount":1000}]'
            ),
        )
        client.post('/api/ocr/parse', json={'text': '复杂文本 110011', 'scenario': 'txn_import'})
        watch = client.get('/api/ocr/usage').get_json()['data']  # 默认 feature=ocr_import
        txn = client.get('/api/ocr/usage?feature=txn_import').get_json()['data']
        assert txn['used'] == 1
        assert watch['used'] == 0

    def test_txn_feature_row_created(self, client, db, monkeypatch):
        from app.core.database import SessionLocal

        monkeypatch.setattr(
            llm_module,
            'call_llm',
            lambda content, system_prompt, **kw: (
                '[{"code":"110011","name":"易方达中小盘","business_type":"买入","amount":1000}]'
            ),
        )
        client.post('/api/ocr/parse', json={'text': '复杂文本 110011', 'scenario': 'txn_import'})
        with SessionLocal() as s:
            row = (
                s.query(UserUsage)
                .filter(
                    UserUsage.user_id == 1, UserUsage.feature == 'txn_import', UserUsage.period_date == date.today()
                )
                .first()
            )
            assert row is not None
            assert row.count == 1

    def test_scenario_absent_defaults_watchlist(self, client, db, monkeypatch):
        """不传 scenario → 默认自选场景（旧前端零改动）。"""
        monkeypatch.setattr(
            llm_module,
            'call_llm',
            lambda content, system_prompt, **kw: '[{"code":"110011","name":"易方达中小盘"}]',
        )
        resp = client.post('/api/ocr/parse', json={'text': '名称在前 110011'})
        data = resp.get_json()['data']
        assert 'items' in data  # 自选场景返回 items（非 rows）
        assert data['items'][0]['code'] == '110011'
