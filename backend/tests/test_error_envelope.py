# -*- coding: utf-8 -*-
"""错误信封契约测试（SPEC：所有异常统一返回 {data, message, error_code}）。

背景：此前 register_error_handlers 只挂在模块级 app 上，而测试 fixture
直接调用 create_app() 得到的是另一个实例，导致错误处理器在测试环境根本未挂载，
且 abort() 的 400/409 等状态码走框架默认响应、绕过信封契约。

本文件验证：
1. create_app() 返回的 app 已挂载错误处理器（修复核心）。
2. abort(400/404/409/500) 均返回 {data, message, error_code} 信封。
3. SBException 返回信封且 error_code 与状态码正确。
"""

import pytest
from flask import abort

from app.core.exceptions import ErrorCode, SBException
from app.main import create_app


@pytest.fixture
def envelope_app():
    """构造一个挂载了错误处理器的 app，并关闭异常传播以便测试处理器本身。"""
    app = create_app()
    app.config['TESTING'] = True
    # 关闭异常传播，使错误处理器真正接管响应（与测试环境默认 PROPAGATE=True 相反，
    # 这里模拟生产行为，验证处理器逻辑）。
    app.config['PROPAGATE_EXCEPTIONS'] = False

    @app.get('/_probe/abort400')
    def _p400():
        abort(400, '探针：参数错误')

    @app.get('/_probe/abort404')
    def _p404():
        abort(404, '探针：资源不存在')

    @app.get('/_probe/abort409')
    def _p409():
        abort(409, '探针：数据冲突')

    @app.get('/_probe/abort500')
    def _p500():
        abort(500, '探针：内部错误')

    @app.get('/_probe/sb')
    def _psb():
        raise SBException(
            code=ErrorCode.RESOURCE_NOT_FOUND.code,
            message='探针：业务异常',
            status_code=404,
        )

    return app


@pytest.fixture
def envelope_client(envelope_app):
    return envelope_app.test_client()


def test_abort_400_envelope(envelope_client):
    resp = envelope_client.get('/_probe/abort400')
    assert resp.status_code == 400
    body = resp.get_json()
    assert body['message'] == '探针：参数错误'
    assert body['error_code'] == ErrorCode.INVALID_PARAMS.code  # 1001
    assert 'data' in body


def test_abort_404_envelope(envelope_client):
    resp = envelope_client.get('/_probe/abort404')
    assert resp.status_code == 404
    body = resp.get_json()
    assert body['message'] == '探针：资源不存在'
    assert body['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code  # 1002


def test_abort_409_envelope(envelope_client):
    resp = envelope_client.get('/_probe/abort409')
    assert resp.status_code == 409
    body = resp.get_json()
    assert body['message'] == '探针：数据冲突'
    assert body['error_code'] == ErrorCode.DUPLICATE_ENTRY.code  # 1003


def test_abort_500_envelope(envelope_client):
    resp = envelope_client.get('/_probe/abort500')
    assert resp.status_code == 500
    body = resp.get_json()
    assert body['message'] == '探针：内部错误'
    assert body['error_code'] == ErrorCode.INTERNAL_ERROR.code  # 5004


def test_sbexception_envelope(envelope_client):
    resp = envelope_client.get('/_probe/sb')
    assert resp.status_code == 404
    body = resp.get_json()
    assert body['message'] == '探针：业务异常'
    assert body['error_code'] == ErrorCode.RESOURCE_NOT_FOUND.code  # 1002
    assert body['data'] is None


def test_envelope_shape_keys(envelope_client):
    """所有错误响应必须含 data/message/error_code 三个键（SPEC 信封不变量）。"""
    for path in ['/__probe__']:  # 未注册路由 -> 404
        resp = envelope_client.get(path)
        body = resp.get_json()
        assert set(['data', 'message', 'error_code']).issubset(body.keys())
