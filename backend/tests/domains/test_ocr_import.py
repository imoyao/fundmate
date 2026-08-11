# -*- coding: utf-8 -*-
# Author : imoyao
# Date : 2026/8/12
# File : test_ocr_import.py
"""OCR 导入与用量限次 API 测试.

覆盖：用量查询 / 文本批量导入（mock LLM）/ 用量超限 / 图片空内容校验。
不依赖真实火山方舟 Key——通过 monkeypatch 替换 ocr_service 的底层调用。
"""

from datetime import date

import pytest

from app.domains.usage.models import UserUsage
from app.services import ocr_service


def _post(client, url, data):
    # 注意：/api/ocr/* 无尾斜杠（SPEC 例外清单之外的端点按路由定义），不要自动补 /
    resp = client.post(url, json=data)
    return resp


class TestUsage:
    def test_usage_initial_remaining(self, client, db):
        """首次查询用量：used=0, remaining=quota(5)。"""
        resp = client.get('/api/ocr/usage')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['used'] == 0
        assert data['quota'] == 5
        assert data['remaining'] == 5

    def test_usage_consume_increments(self, client, db):
        """消费一次后 remaining 减 1。"""
        resp = client.post('/api/ocr/parse', json={'text': '110011 易方达中小盘'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['usage']['used'] == 1
        assert data['usage']['remaining'] == 4

    def test_usage_quota_exceeded(self, client, db, monkeypatch):
        """用量超限返回 429，且不再调用 LLM。"""
        # 直接写入超限记录
        from app.core.database import SessionLocal

        with SessionLocal() as s:
            s.add(
                UserUsage(
                    user_id=1,
                    feature='ocr_import',
                    period_date=date.today(),
                    count=5,
                    quota=5,
                )
            )
            s.commit()

        called = {'n': 0}

        def _fake_parse(text):
            called['n'] += 1
            return []

        monkeypatch.setattr(ocr_service, 'parse_text', _fake_parse)
        resp = client.post('/api/ocr/parse', json={'text': '110011'})
        assert resp.status_code == 429
        assert called['n'] == 0  # 超限直接拦截，未触发识别


class TestParseText:
    def test_parse_text_success(self, client, db, monkeypatch):
        """文本批量导入：返回识别条目 + 消耗用量。"""
        monkeypatch.setattr(
            ocr_service,
            'parse_text',
            lambda text: [{'code': '110011', 'name': '易方达中小盘混合'}, {'code': '005827', 'name': '易方达蓝筹精选'}],
        )
        resp = _post(client, '/api/ocr/parse', {'text': '我的持仓：110011 易方达中小盘；005827 易方达蓝筹精选'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert len(data['items']) == 2
        assert data['items'][0]['code'] == '110011'
        assert data['usage']['used'] == 1

    def test_parse_text_empty_rejected(self, client, db, monkeypatch):
        """空文本在 service 层直接 400，不消耗配额。"""
        from app.core.exceptions import SBException

        # 直接调真实 service：空文本在入口即抛 400，不会外呼 LLM（无需网络）
        with pytest.raises(SBException) as exc:
            ocr_service.parse_text('   ')
        assert exc.value.status_code == 400


class TestRecognize:
    def test_recognize_empty_image_rejected(self, client, db, monkeypatch):
        """空图片 base64 解码失败 → 400。"""
        monkeypatch.setattr(ocr_service, 'recognize', lambda b: [])
        resp = _post(client, '/api/ocr/recognize', {'image_base64': 'not-valid-base64!!'})
        assert resp.status_code == 400

    def test_recognize_success(self, client, db, monkeypatch):
        """图片识别成功：返回条目 + 消耗用量。"""
        import base64

        monkeypatch.setattr(
            ocr_service,
            'recognize',
            lambda b: [{'code': '510300', 'name': '沪深300ETF'}],
        )
        img_b64 = base64.b64encode(b'fake-image-bytes').decode('ascii')
        resp = _post(client, '/api/ocr/recognize', {'image_base64': img_b64})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['items'][0]['code'] == '510300'
        assert data['usage']['remaining'] == 4
