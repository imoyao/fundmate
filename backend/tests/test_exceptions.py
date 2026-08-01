# -*- coding: utf-8 -*-
"""V2 业务异常与错误码体系测试（替代已退役的 V1 test_errors.py）。

V1 的 `test_errors.py` 原属遗留 fundmate 包，随 V1 一并删除。
本文件覆盖 V2 `app.core.exceptions` 的 `SBException` 与 `ErrorCode` 不变量。
"""

import pytest

from app.core.exceptions import ErrorCode, SBException


class TestErrorCodeIntegrity:
    """错误码枚举的结构不变量——金融错误码一旦定下不应漂移。"""

    def test_enum_shape(self):
        assert ErrorCode.INVALID_PARAMS.code == 1001
        assert ErrorCode.INVALID_PARAMS.msg == '请求参数无效'
        assert ErrorCode.INVALID_PARAMS.http_status == 400

    def test_codes_are_unique(self):
        """错误码全局唯一，避免前端/调用方按 code 反查时歧义。"""
        codes = [e.code for e in ErrorCode]
        assert len(codes) == len(set(codes)), 'ErrorCode 存在重复 code'

    def test_http_status_in_4xx_or_5xx(self):
        for e in ErrorCode:
            assert 400 <= e.http_status <= 599

    def test_get_by_code_found(self):
        assert ErrorCode.get_by_code(1002) is ErrorCode.RESOURCE_NOT_FOUND

    def test_get_by_code_missing(self):
        assert ErrorCode.get_by_code(999999) is None


class TestSBException:
    def test_defaults(self):
        exc = SBException(code=1001, message='bad')
        assert exc.code == 1001
        assert exc.message == 'bad'
        assert exc.status_code == 400
        assert exc.detail == {}

    def test_custom_status_and_detail(self):
        exc = SBException(code=5001, message='src down', status_code=503, detail={'src': 'eastmoney'})
        assert exc.status_code == 503
        assert exc.detail == {'src': 'eastmoney'}

    def test_is_exception(self):
        with pytest.raises(SBException):
            raise SBException(code=1002, message='nope')
