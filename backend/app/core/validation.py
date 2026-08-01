# -*- coding: utf-8 -*-
# File : validation.py
"""请求体/查询手动校验助手。

目的：消除对 APIFlask `@bp.input()` 自动范式的依赖（违反 SPEC §1.3
「不依赖自动范式，为未来平滑迁移 FastAPI 预留架构空间」）。

- `parse_body(model)` 等价于 `Body()` + Pydantic 校验；
- `parse_query(model)` 等价于 `Query()` + Pydantic 校验。
两者在 FastAPI 迁移时只需把 `parse_*` 调用替换为对应 `Depends`，
校验模型（Pydantic BaseModel）可直接复用，迁移成本≈0。

校验失败时 `abort(422)`，由 `app/main.py` 的 `HTTPException` 处理器
统一收敛为 `{data, message, error_code}` 信封，与原 `@bp.input` 返回的
422 状态码一致（既有测试 `assert status_code == 422` 不受影响）。
"""

from flask import abort, request
from pydantic import BaseModel, ValidationError


def _format_errors(exc: ValidationError) -> str:
    """把 Pydantic 校验错误拼成单行可读信息。"""
    parts = []
    for err in exc.errors():
        loc = '.'.join(str(p) for p in err.get('loc', ()))
        parts.append(f"{loc}: {err.get('msg', '')}" if loc else err.get('msg', ''))
    return '; '.join(parts)


def parse_body(model: type[BaseModel]) -> BaseModel:
    """校验 JSON 请求体，替代 `@bp.input(model)`。

    失败返回 422 并走统一错误信封。成功返回已校验的 Pydantic 实例。
    """
    # 不使用 silent：非法 JSON 直接抛 400（与原 @bp.input 行为一致，
    # 既有的 test_assign_asset_with_invalid_json 断言 in (400, 422)）。
    payload = request.get_json()
    if not isinstance(payload, dict):
        abort(422, '请求体必须是 JSON 对象')
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        abort(422, f'请求参数校验失败: {_format_errors(e)}')


def parse_query(model: type[BaseModel]) -> BaseModel:
    """校验查询参数，替代 `@bp.input(model, location='query')`。"""
    try:
        return model.model_validate(dict(request.args))
    except ValidationError as e:
        abort(422, f'查询参数校验失败: {_format_errors(e)}')
