# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/9/2
# File : test_usage_api.py
"""通用用量 API 测试（issue #823）.

覆盖：独立端点 GET /api/usage/<feature> 的首查余量、跨 feature 隔离、重置时间字段。
不依赖真实火山方舟 Key；用量数据走 guards.check_usage（DB 落地）。
"""

from datetime import date, timedelta

from app.services.ai_recognizer import guards as ai_guards


class TestUsageApi:
    def test_get_usage_initial(self, client, db):
        """首查 ocr_import：used=0, remaining=quota，且含 feature 与 reset_at。"""
        quota = ai_guards.OCR_DAILY_QUOTA  # 读实际配置（环境可能覆盖缺省 5）
        resp = client.get('/api/usage/ocr_import')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['feature'] == 'ocr_import'
        assert data['used'] == 0
        assert data['quota'] == quota
        assert data['remaining'] == quota
        assert data['period_date'] == date.today().isoformat()
        assert data['reset_at'] == (date.today() + timedelta(days=1)).isoformat()

    def test_features_independent(self, client, db):
        """不同 feature 的用量互不影响（各自计数行）。"""
        a = client.get('/api/usage/ocr_import').get_json()['data']
        b = client.get('/api/usage/txn_import').get_json()['data']
        assert a['feature'] == 'ocr_import'
        assert b['feature'] == 'txn_import'
        assert a['remaining'] == b['remaining']  # 各自首查都满额

    def test_unknown_feature_passthrough(self, client, db):
        """未知 feature 透传 guards（不 400），返回 0 用量占位。"""
        resp = client.get('/api/usage/scheduled_sync')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['feature'] == 'scheduled_sync'
        assert data['used'] == 0

    def test_ocr_usage_alias_removed(self, client, db):
        """历史别名 /api/ocr/usage 已收敛到 /api/usage/<feature>，应返回 404。"""
        resp = client.get('/api/ocr/usage')
        assert resp.status_code == 404
