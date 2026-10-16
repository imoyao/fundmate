# -*- coding: utf-8 -*-
"""用**真实抓到的上游响应**验证解析逻辑（#2037）。

为什么要有这个文件：单测里的响应是我手写的，形状可能与上游不符；而每次真连上游做
冒烟又不稳定（本机多次实测在 60~250s 不等，另见下方"真连实测记录"）。两者之间缺一环：
**手写 fixture 保不住形状，真连又不可复现**。

这里的 4 条样本是 2026-10-11 真实抓取的原样 JSON（含真实字段名与真实候选集），
逐条钉住解析口径。上游改字段名时本文件会红——那正是要的效果（静默降级为 None
比报错更坏）。

## 真连实测记录（2026-10-11，供后续排障对照）

| 场景 | 结果 |
|---|---|
| 12 只各类基金（股票/混合/指数联接/QDII/LOF） | 12/12 全部返回 `{name, code}`，公司与库内已知归属一致 |
| 复用连接后单次耗时 | 43~87ms |
| 首次请求（含 TLS 握手 + DNS） | 1.8~2.8s（故必须长连接 Session） |
| 空 code / 不存在的 code / 纯前缀 key | 均返回 None（不误配） |

## 已知的上游事实

- `Datas` 是**候选列表**，长度可 >1（模糊搜索），必须按 `CODE` 精确回选；
- `FundBaseInfo` 可能为 `null`（命中但无资料）；
- `JJGS` 是**简称**（如「易方达基金」），与 `jjjz_gs.js` 名录的 `name` 同一形态，
  故可直接交给 `company_resolver` 解析权威 code，不必自己比对。
"""

import json

from app.services.adapters.eastmoney_adapter import fetch_fund_company_of


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return json.loads(self._payload)


# 样本 1：标准命中（真实抓取，110022 易方达消费行业股票）
_R_110022 = """{"ErrCode":0,"ErrMsg":"fromcache","Datas":[{"_id":"110022","CODE":"110022",
"NAME":"易方达消费行业股票","CATEGORY":700,"CATEGORYDESC":"基金",
"FundBaseInfo":{"_id":"110022","DWJZ":2.788,"FCODE":"110022","FSRQ":"2026-10-09","FTYPE":"股票型",
"JJGS":"易方达基金","JJGSBID":4.0,"JJGSID":"80000229","JJJL":"萧楠","MINSG":10.0,
"SHORTNAME":"易方达消费行业股票"},"StockHolder":null,
"ZTJJInfo":[{"TTYPE":"BK000390","TTYPENAME":"消费"}],"SEARCHWEIGHT":0.0,"NEWTEXCH":""}]}"""

# 样本 2：模糊命中多只 —— key「001」会带出一串 001xxx（这是「必须精确回选」的由来）
_R_FUZZY_001 = """{"ErrCode":0,"ErrMsg":"fromcache","Datas":[
{"_id":"001102","CODE":"001102","NAME":"前海开源国家比较优势混合A","CATEGORY":700,"CATEGORYDESC":"基金",
 "FundBaseInfo":{"_id":"001102","FCODE":"001102","JJGS":"前海开源基金","JJGSID":"80280038"}},
{"_id":"001594","CODE":"001594","NAME":"天弘中证银行ETF联接A","CATEGORY":700,"CATEGORYDESC":"基金",
 "FundBaseInfo":{"_id":"001594","FCODE":"001594","JJGS":"天弘基金","JJGSID":"80041198"}}]}"""

# 样本 3：命中但 FundBaseInfo 为 null
_R_NO_BASEINFO = """{"ErrCode":0,"ErrMsg":"fromcache","Datas":[
{"_id":"519674","CODE":"519674","NAME":"银河创新成长混合A","CATEGORY":700,"CATEGORYDESC":"基金",
 "FundBaseInfo":null}]}"""

# 样本 4：查无此只 —— Datas 为空数组（真连「ZZZZZZ」实测就是这个形态）
_R_EMPTY = """{"ErrCode":0,"ErrMsg":"fromcache","Datas":[]}"""


def _patch(monkeypatch, raw):
    from app.services.adapters import eastmoney_adapter as em

    session = em._get_suggest_session()
    monkeypatch.setattr(session, 'get', lambda *a, **k: _Resp(raw))


def test_real_payload_single_hit(monkeypatch):
    _patch(monkeypatch, _R_110022)
    assert fetch_fund_company_of('110022') == {'name': '易方达基金', 'code': '80000229'}


def test_real_payload_fuzzy_picks_exact(monkeypatch):
    """真实模糊响应：本只在候选列表里排第 2。取 `Datas[0]` 就会答错公司。"""
    _patch(monkeypatch, _R_FUZZY_001)
    assert fetch_fund_company_of('001594') == {'name': '天弘基金', 'code': '80041198'}


def test_real_payload_prefix_only_returns_none(monkeypatch):
    """纯前缀 key「001」：候选里有 001102 / 001594，但**没有一只 CODE 恰为 001**。

    返回 None 而非随便挑一只——这是「宁可留白，不可错配」的具体体现。
    """
    _patch(monkeypatch, _R_FUZZY_001)
    assert fetch_fund_company_of('001') is None


def test_real_payload_null_baseinfo_returns_none(monkeypatch):
    _patch(monkeypatch, _R_NO_BASEINFO)
    assert fetch_fund_company_of('519674') is None


def test_real_payload_empty_datas_returns_none(monkeypatch):
    _patch(monkeypatch, _R_EMPTY)
    assert fetch_fund_company_of('ZZZZZZ') is None


def test_real_payload_jjgs_is_short_form_not_legal_name(monkeypatch):
    """`JJGS` 是**简称**（「易方达基金」），不是法人全称。

    这一条决定了下游能不能直接把它交给 `company_resolver.resolve_company_identity`：
    若是全称就得在业务层再做一次归一化，那会让公司身份解析出现第二个实现。
    """
    _patch(monkeypatch, _R_110022)
    name = fetch_fund_company_of('110022')['name']
    assert name == '易方达基金'
    assert '有限公司' not in name
