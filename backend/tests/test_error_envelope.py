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


# ── 5xx 不得泄漏异常细节（2026-10-30，源一次真实线上报错）──────────────────────
# 事故形态：`summary/views.py` 各端点自建 `except Exception → f'服务器内部错误: {str(e)}'`，
# 一次 SQLite 唯一约束冲突把 INSERT 全文、绑定参数（family_id / ledger_id / 金额）与
# sqlalche.me 链接原样送到浏览器；异常被视图吞掉后 main.py 的全局兜底处理器
# （固定文案 + 堆栈留痕）根本没机会执行 ⇒ 既不脱敏也不留痕。

_SQL_TEXT = "UNIQUE constraint failed: index 'uq_probe' [SQL: INSERT INTO t VALUES (?)] [parameters: (1, 2)]"


def test_internal_error_message_只回固定文案(log_capture):
    """`internal_error_message` 对外只给固定文案，且必须留痕（含堆栈）。"""
    from app.core.exceptions import internal_error_message

    exc = Exception(_SQL_TEXT)
    text = internal_error_message(exc, 'probe')

    assert text == ErrorCode.INTERNAL_ERROR.msg
    assert 'SQL' not in text and 'INSERT' not in text
    # 留痕：sink 里能看到这次异常（旧写法被视图吞掉后一条日志都没有）
    assert any('未捕获的系统异常' in line for line in log_capture)
    assert any('probe' in line for line in log_capture)


def test_global_handler_500_不泄漏异常细节(envelope_app):
    """未捕获异常经全局处理器 -> 固定文案；响应体里不得出现 SQL / 参数。"""
    app = envelope_app
    app.config['PROPAGATE_EXCEPTIONS'] = False

    @app.get('/_probe/boom')
    def _boom():
        raise RuntimeError(_SQL_TEXT)

    resp = app.test_client().get('/_probe/boom')
    assert resp.status_code == 500
    body = resp.get_json()
    assert body['message'] == ErrorCode.INTERNAL_ERROR.msg
    assert body['error_code'] == ErrorCode.INTERNAL_ERROR.code
    raw = resp.get_data(as_text=True)
    for token in ('SQL:', 'INSERT INTO', 'parameters:', 'sqlalche.me'):
        assert token not in raw


@pytest.fixture
def log_capture():
    """把 loguru 的 ERROR 级日志收进列表（只收本用例期间产生的）。"""
    from loguru import logger

    lines: list[str] = []
    sink_id = logger.add(lambda m: lines.append(str(m)), level='ERROR')
    try:
        yield lines
    finally:
        logger.remove(sink_id)


# ── 判据本体（scripts/guard_error_envelope.py 的第二条判据）────────────────────


def _load_guard():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / 'scripts' / 'guard_error_envelope.py'
    spec = importlib.util.spec_from_file_location('guard_error_envelope', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_守卫在真实仓库上通过():
    """仓库当前状态必须干净——否则说明有人在视图里又把 `str(e)` 拼进了 5xx。"""
    assert _load_guard().main([]) == 0


def test_守卫能咬住_5xx_泄漏形态():
    """变异探针：把修复前的写法喂给判据，必须报 `leaks_exception`（防「永远绿」）。"""
    guard = _load_guard()
    from pathlib import Path

    legacy = (
        'def view():\n'
        '    try:\n'
        "        return jsonify({'data': None, 'message': 'ok'})\n"
        '    except Exception as e:\n'
        "        return jsonify({'data': None, 'message': f'服务器内部错误: {str(e)}', "
        "'error_code': 5004}), 500\n"
    )
    violations, parse_error = guard.scan_file_contents(legacy, Path('probe.py'))
    assert parse_error is None
    assert [v['kind'] for v in violations] == ['leaks_exception']


def test_守卫不误伤_4xx_的业务文案():
    """4xx 的 `str(e)` 是正常的参数校验文案，判据必须只盯 5xx。"""
    guard = _load_guard()
    from pathlib import Path

    src = (
        'def view():\n'
        '    try:\n'
        "        return jsonify({'data': None, 'message': 'ok'})\n"
        '    except ValueError as e:\n'
        "        return jsonify({'data': None, 'message': str(e), 'error_code': 1001}), 400\n"
    )
    violations, _ = guard.scan_file_contents(src, Path('probe.py'))
    assert violations == []
