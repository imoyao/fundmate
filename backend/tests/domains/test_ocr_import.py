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
        """首次查询用量：used=0, remaining=quota（读环境配置，默认 5）。"""
        quota = ocr_service.OCR_DAILY_QUOTA
        resp = client.get('/api/ocr/usage')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['used'] == 0
        assert data['quota'] == quota
        assert data['remaining'] == quota

    def test_usage_consume_increments(self, client, db):
        """消费一次后 remaining 减 1。"""
        quota = ocr_service.OCR_DAILY_QUOTA
        resp = client.post('/api/ocr/parse', json={'text': '110011 易方达中小盘'})
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['usage']['used'] == 1
        assert data['usage']['remaining'] == quota - 1

    def test_usage_quota_exceeded(self, client, db, monkeypatch):
        """用量超限返回 429，且不再调用 LLM。"""
        # 直接写入超限记录
        from app.core.database import SessionLocal

        quota = ocr_service.OCR_DAILY_QUOTA
        with SessionLocal() as s:
            s.add(
                UserUsage(
                    user_id=1,
                    feature='ocr_import',
                    period_date=date.today(),
                    count=quota,
                    quota=quota,
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
        assert data['usage']['remaining'] == ocr_service.OCR_DAILY_QUOTA - 1

    def test_recognize_failure_refunds_usage(self, client, db, monkeypatch):
        """识别失败（服务 503）返还本次配额：失败不白耗次数（用户反馈测试期痛点）。"""
        import base64

        from app.core.exceptions import ErrorCode, SBException

        def _fail(image_bytes):
            raise SBException(
                code=ErrorCode.OCR_SERVICE_UNAVAILABLE.code,
                message='OCR 识别服务暂时不可用，请稍后重试',
                status_code=ErrorCode.OCR_SERVICE_UNAVAILABLE.http_status,
            )

        monkeypatch.setattr(ocr_service, 'recognize', _fail)
        img_b64 = base64.b64encode(b'fake-image-bytes').decode('ascii')
        resp = _post(client, '/api/ocr/recognize', {'image_base64': img_b64})
        assert resp.status_code == 503
        # 失败后用量回到初始（0 次），下一次仍可正常识别
        data = client.get('/api/ocr/usage').get_json()['data']
        assert data['used'] == 0
        assert data['remaining'] == ocr_service.OCR_DAILY_QUOTA


class TestEnrichItems:
    """识别结果类型反查：Securities(场内) → Funds(场外) → 兜底。

    回归自选导入失败：股票/深市 ETF 被前端按 code 前缀误判为场外基金导入，
    导致 type/venue/symbol 全错、与持仓断裂。
    """

    def test_enrich_stock_uses_securities(self, db):
        """股票 600519：命中 Securities → type=stock / venue=EXCHANGE / symbol=SH600519。"""
        from app.domains.securities.models import Security

        db.add(Security(symbol='SH600519', name='贵州茅台', market='SH', type='stock'))
        db.commit()

        items = ocr_service._enrich_items([{'code': '600519', 'name': '贵州茅台'}])
        assert items[0] == {
            'code': '600519',
            'name': '贵州茅台',
            'symbol': 'SH600519',
            'type': 'stock',
            'market': 'SH',
            'venue': 'EXCHANGE',
        }

    def test_enrich_etf_uses_securities(self, db):
        """ETF 510300：命中 Securities → type=etf / venue=EXCHANGE。"""
        from app.domains.securities.models import Security

        db.add(Security(symbol='SH510300', name='300ETF', market='SH', type='etf'))
        db.commit()

        items = ocr_service._enrich_items([{'code': '510300', 'name': '300ETF'}])
        assert items[0]['type'] == 'etf'
        assert items[0]['venue'] == 'EXCHANGE'
        assert items[0]['symbol'] == 'SH510300'

    def test_enrich_otc_fund_uses_funds(self, db):
        """场外基金 110011：命中 Funds → type=fund / venue=OTC / symbol=裸代码。"""
        from app.domains.funds.models import Fund

        db.add(Fund(fund_code='110011', name='易方达中小盘混合'))
        db.commit()

        items = ocr_service._enrich_items([{'code': '110011', 'name': '易方达中小盘'}])
        assert items[0] == {
            'code': '110011',
            'name': '易方达中小盘混合',
            'symbol': '110011',
            'type': 'fund',
            'market': 'CN_A',
            'venue': 'OTC',
        }

    def test_enrich_sh_etf_by_code_rule(self, db):
        """沪市 ETF 510300：Securities 未收录但 5 开头 → etf / EXCHANGE / 标准化 symbol。"""
        items = ocr_service._enrich_items([{'code': '510300', 'name': '300ETF'}])
        assert items[0]['type'] == 'etf'
        assert items[0]['venue'] == 'EXCHANGE'
        assert items[0]['symbol'] == 'SH510300'
        assert items[0]['market'] == 'SH'

    def test_enrich_sz_etf_by_code_rule(self, db):
        """深市 ETF 159915：159 开头 → etf / EXCHANGE / SZ159915。"""
        items = ocr_service._enrich_items([{'code': '159915', 'name': '创业板ETF'}])
        assert items[0]['type'] == 'etf'
        assert items[0]['venue'] == 'EXCHANGE'
        assert items[0]['symbol'] == 'SZ159915'

    def test_enrich_lof_by_code_rule(self, db):
        """深市 LOF 161725：16x 开头 → fund / EXCHANGE（可场内交易）。"""
        items = ocr_service._enrich_items([{'code': '161725', 'name': '招商中证白酒'}])
        assert items[0]['type'] == 'fund'
        assert items[0]['venue'] == 'EXCHANGE'
        assert items[0]['symbol'] == 'SZ161725'

    def test_enrich_fallback_default_otc(self, db):
        """两表都未命中且非场内模式 → 兜底 type=fund / venue=OTC（6 位代码大概率场外基金）。"""
        items = ocr_service._enrich_items([{'code': '999999', 'name': '未知'}])
        assert items[0]['type'] == 'fund'
        assert items[0]['venue'] == 'OTC'
        assert items[0]['symbol'] == '999999'

    def test_enrich_keeps_ocr_name_when_table_missing(self, db):
        """表内未命中时保留 OCR 识别出的名称。"""
        items = ocr_service._enrich_items([{'code': '888888', 'name': '某基金'}])
        assert items[0]['name'] == '某基金'
