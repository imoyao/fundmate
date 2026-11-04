# -*- coding: utf-8 -*-
"""国证指数官网权重直连（`adapters/index_weights`）。**不打真实网络**。

重点覆盖三件事：
1. **attachment 头是口径判据**：国证对不认识的码返回 200 + 「暂无数据」文本（无
   Content-Disposition），必须识别为「不覆盖」而不是解析失败；
2. **附件必须是 xlsx**（PK 头）：否则同样降级，不把 HTML 错误页丢给 pandas；
3. 通道 / 解析真故障一律 warning + 返回 None（best-effort，不阻断详情页）。
"""

import warnings
from io import BytesIO

import pandas as pd

from app.services.adapters import index_weights as iw

CNI_COLUMNS = ['日期', '样本代码', '样本简称', '所属行业', '总市值(亿元)', '权重（%）']


class _FakeResp:
    def __init__(self, content: bytes = b'', headers=None, status: int = 200):
        self.content = content
        self.headers = headers or {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')

    def json(self):
        raise AssertionError('权重接口不是 JSON 通道')


def _xlsx(rows: int = 2) -> bytes:
    """真 xlsx（openpyxl 写出）：让 read_excel 走真实解析路径，不 mock pandas。"""
    df = pd.DataFrame(
        [['2026-10-30', 937 + i, f'样本{i}', '工业', 100.0 + i, round(1.5 - i * 0.5, 2)] for i in range(rows)],
        columns=CNI_COLUMNS,
    )
    buf = BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        df.to_excel(buf, index=False)
    return buf.getvalue()


def _patch_get(monkeypatch, resp: _FakeResp, calls: list):
    def _fake(url, params=None, headers=None, timeout=None, **kwargs):
        calls.append({'url': url, 'params': dict(params or {})})
        return resp

    monkeypatch.setattr(iw.requests, 'get', _fake)


def test_parses_attachment_xlsx(monkeypatch):
    """正常路径：attachment + PK 头 → 返回源侧原列名的 DataFrame（归一由消费方做）。"""
    calls = []
    _patch_get(monkeypatch, _FakeResp(_xlsx(2), {'content-disposition': 'attachment;filename=399001_cons.xlsx'}), calls)

    df = iw.fetch_weights_cni('399001')

    assert list(df.columns) == CNI_COLUMNS
    assert len(df) == 2
    assert df['权重（%）'].iloc[0] == 1.5
    assert calls == [{'url': iw._CNI_WEIGHTS, 'params': {'indexcode': '399001'}}]


def test_missing_attachment_is_scope_miss(monkeypatch):
    """200 + 「暂无数据」且无 attachment → 口径不覆盖，返回 None（不是解析失败）。"""
    calls = []
    _patch_get(monkeypatch, _FakeResp('暂无数据'.encode(), {'content-type': 'text/html;=;charset=utf-8'}), calls)

    assert iw.fetch_weights_cni('899050') is None


def test_attachment_but_not_xlsx_returns_none(monkeypatch):
    """有 attachment 头但内容不是 xlsx（HTML 错误页）→ None，不丢给 pandas。"""
    _patch_get(monkeypatch, _FakeResp(b'<html>404</html>', {'content-disposition': 'attachment;filename=x.xlsx'}), [])

    assert iw.fetch_weights_cni('399001') is None


def test_http_error_returns_none(monkeypatch):
    _patch_get(monkeypatch, _FakeResp(b'', {}, status=500), [])

    assert iw.fetch_weights_cni('399001') is None


def test_network_exception_returns_none(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError('RemoteDisconnected')

    monkeypatch.setattr(iw.requests, 'get', boom)

    assert iw.fetch_weights_cni('399001') is None


def test_corrupt_xlsx_returns_none(monkeypatch):
    """PK 头但内容损坏（截断的 zip）→ 解析失败降级 None，不抛异常。"""
    _patch_get(monkeypatch, _FakeResp(b'PK\x03\x04broken', {'content-disposition': 'attachment;filename=x.xlsx'}), [])

    assert iw.fetch_weights_cni('399001') is None
