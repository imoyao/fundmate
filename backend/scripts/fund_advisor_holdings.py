#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天天基金 · 基金投顾组合「持仓」自动抓取器
=====================================================

背景
----
用户要获取「越海」(国联证券/国联民生证券 投顾组合) 在天天基金的 *组合持仓*
(即该投顾组合当前持有哪些基金、各自占比)，并接入「组合持仓」独立看板，
实现每日自动化推送。

数据来源（均已实测，公开可达，无需登录/签名/浏览器）
--------------------------------------------------
经逆向 App bundle 与实测，投顾数据真实后端有两个公开 host：

1) `https://uni-fundts.1234567.com.cn`（投顾交易/持仓明细）
   - `/combine/investAdviserInfo/getTGQuoteByFavor`  业绩/净值（需 tgCodeWithDateStr=TGCODE_YYYY-MM-DD）
   - `/combine/investAdviserInfo/getHoldWarehouseIndustryRatio`  持仓行业配置（仅需 tgCode）
   - `/combine/investAdviserInfo/getAdjustWarehouse`  调仓/持仓明细
        tag=0 -> latestAdjust（最新一次调仓 = 当前基金级持仓快照）
        tag=1 -> adjustHistory（历史调仓列表，含每次调仓的基金级前后占比）
   注：bundle 里静态默认写的是 combine-gold.tiantianfunds.com，但运行时经远程 host
   配置解析到 uni-fundts；combine-gold 公网不可达（网关 404），故直连一律走 uni-fundts。

2) `https://dataapi.1234567.com.cn`（投顾概览，字段最全）
   - `/dataapi/IAAGGR/FundIATGInfoAggr`（GET，FIELDS + TGCODE）
       返回 TGNAME/LOGO_NAME/RISKLEVEL/STRATEGY_RATE/SYL_*/BENCHSYL_*/STGCONCEPT 等。
       注意响应键是小写 data + errorCode/success（与 uni-fundts 的 Data/ErrCode 不同）。

因此本脚本**默认**走上述公开接口直连（免登录/签名/浏览器）；
`--playwright` 可切换回无头浏览器渲染 H5 页作为兜底（需本机可跑 Chromium）。
前端 bundle 名、host、API 方法名会随 App 发版变化，故内置 `healthcheck` 子命令，
在每日推送前主动验证链路（H1 bundle 可达 / H2 未轮换 / H3-H6 各接口可达可解析）。

用法要点：
  - 输入：投顾组合的 tgCode（天天基金分享链接里 `tgCode=` 的值）
  - 输出：结构化 JSON（overview / quote / industry_holdings / fund_holdings / history）
  - 可 cron 每日调度，无需任何二维码/人工登录
  - 支持 --all 遍历「关注列表」，免手动逐个维护
  - 加 --history 可额外抓取历次调仓的基金级前后占比（历史持仓）

依赖安装（在能正常运行 Chromium 的机器上，本沙箱因命令时长限制无法跑浏览器）
  pip install playwright
  playwright install chromium

用法
----
  # 抓单个（公开接口直连，默认路径，无需任何 flag）
  python fund_advisor_holdings.py --tgcode XCOVSEX
  # 抓单个并额外带历史调仓（基金级前后占比）
  python fund_advisor_holdings.py --tgcode XCOVSEX --history
  # 贴完整分享链接自动提取 tgCode=（同样走公开接口；--playwright 才能切回浏览器兜底）
  python fund_advisor_holdings.py --url "https://tradeh5.tiantianfunds.cn/tradeh5/funda91a99886abf7e/detailindex?tgCode=XCOVSEX&showKycPopup=1&reHome=1"

  # 遍历关注列表（advisor_watchlist.json），一次抓取全部投顾（公开接口）
  python fund_advisor_holdings.py --all --out all_holdings.json
  # 同上并附带历史持仓
  python fund_advisor_holdings.py --all --history --out all_holdings.json

  # 每日模式（输出到文件，便于微信推送读取）
  python fund_advisor_holdings.py --all --out holdings.json --daily

  # 兜底：改用无头浏览器渲染 H5 页（仅在公开接口因发版失效时手动启用）
  python fund_advisor_holdings.py --playwright --tgcode XCOVSEX

  # health 接口：盘前/推送前验证链路（H1 bundle / H2 轮换 / H3-H6 各接口）
  python fund_advisor_holdings.py --healthcheck

关注列表 advisor_watchlist.json 结构（tgcode 稳定，新增只需加一行）：
  [
    {"tgcode": "XCOVSEX", "name": "越海"},
    {"tgcode": "JY48YPE", "name": "万家非凡新质驱动"}
  ]

产出 JSON 结构（--public 模式）
-----------------------------
{
  "tgcode": "XCOVSEX",
  "date": "2026-07-22",
  "fetched_at": "2026-07-22T...",
  "overview": {...},                  // FundIATGInfoAggr：TGNAME/RISKLEVEL/SYL_*/BENCHSYL_*/STGCONCEPT...
  "quote": {...},                     // getTGQuoteByFavor：业绩/净值
  "industry_holdings": [              // 行业配置 [{industryName, ratio, date, ...}]
    {"industryName": "电子", "ratio": 9.16, ...}, ...
  ],
  "industry_count": 8,
  "fund_holdings": [                  // 当前基金级持仓（最新调仓后占比）
    {"code": "012153", "name": "博时研究慧选混合A", "pre_ratio": 15.77,
     "after_ratio": 16.0, "op": 5, "op_name": "持平"}, ...
  ],
  "fund_count": 11,
  "history": [                        // 仅 --history：历次调仓快照（基金级前后占比）
    {"date": "2026-04-01", "reason": "...", "fund_count": 11,
     "total_after_ratio": 100.0, "funds": [{...}, ...]}, ...
  ]
}
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

# 投顾模块 H5 bundle（交易/理财域；用户实抓链接：
# https://tradeh5.tiantianfunds.cn/tradeh5/funda91a99886abf7e/detailindex?tgCode=XXXX）
ADVISOR_BUNDLE = 'funda91a99886abf7e'
H5_DETAIL_TMPL = 'https://tradeh5.tiantianfunds.cn/tradeh5/{bundle}/detailindex?tgCode={tgcode}'

# 投顾数据真实后端（公开可达，无需登录/签名）：
# 注意 bundle 里写的是 combine-gold.tiantianfunds.com（静态默认值），但运行时经远程
# host 配置解析到 uni-fundts.1234567.com.cn，且后者对外公开路由 /combine/investAdviserInfo/*。
# combine-gold 本身公网不可达（网关 404），所以直连一律走 uni-fundts。
COMBINE_PUBLIC_HOST = 'https://uni-fundts.1234567.com.cn'
# 投顾概览信息在独立 host dataapi.1234567.com.cn（GET，无需登录）
DATAPI_HOST = 'https://dataapi.1234567.com.cn'

# 业绩/净值（需 tgCodeWithDateStr=TGCODE_YYYY-MM-DD，缺则 Data:null）
API_TG_QUOTE = COMBINE_PUBLIC_HOST + '/combine/investAdviserInfo/getTGQuoteByFavor'
# 持仓行业配置（仅需 tgCode）
API_HOLD_INDUSTRY = COMBINE_PUBLIC_HOST + '/combine/investAdviserInfo/getHoldWarehouseIndustryRatio'
# 调仓/持仓明细（仅需 tgCode；tag=0 取最新一次调仓=当前基金级持仓，tag=1 取历史调仓列表）
API_ADJUST_WAREHOUSE = COMBINE_PUBLIC_HOST + '/combine/investAdviserInfo/getAdjustWarehouse'
# 投顾信息概览（GET，FIELDS 逗号列表 + TGCODE；字段比 getTGQuoteByFavor 更全）
API_TG_AGGR = DATAPI_HOST + '/dataapi/IAAGGR/FundIATGInfoAggr'
# 通用表单参数（来自 App 抓包；mobileKey 可任意占位）
COMBINE_COMMON_FORM = {
    'product': 'EFund',
    'mobileKey': '123',
    'version': '6.5.9',
    'plat': 'Android',
}
# 调仓操作类型（adjustWarehouse fundList.operationInt）
ADJUST_OP_NAME = {1: '建仓', 2: '加仓', 3: '减仓', 4: '新增', 5: '持平'}


def extract_tgcode_from_url(url: str) -> str:
    # 兼容两种形态：H5 详情用 tgCode=；旧 weex 形态用 id=
    m = re.search(r'[?&](?:tgCode|id)=([^&]+)', url, re.IGNORECASE)
    return m.group(1) if m else ''


def parse_holdings(text: str):
    """
    从页面全文抽取持仓基金。
    天天基金投顾详情页「持仓」区每行大致为：基金名称 + 6位代码 + 占比%。
    这里用宽松正则尽量兜住，同时返回原始文本供人工核对。
    """
    holdings = []
    # 基金名(中文/字母/数字/括号/·/-) + 空格 + 6位代码 + 空格 + 百分比
    pat = re.compile(r'([\u4e00-\u9fa5A-Za-z0-9()·\-（）、]{2,30})\s*(\d{6})\s*([\d.]+)\s*%')
    seen = set()
    for m in pat.finditer(text):
        name, code, ratio = m.group(1).strip(), m.group(2), float(m.group(3))
        key = (name, code)
        if key in seen:
            continue
        seen.add(key)
        holdings.append({'name': name, 'code': code, 'ratio': ratio})
    return holdings


def fetch_holdings(tgcode: str) -> dict:
    """用 Playwright 无头 Chromium 加载 H5 详情页并抽取持仓。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit('缺少依赖 playwright。请先执行:\n  pip install playwright && playwright install chromium\n')

    url = H5_DETAIL_TMPL.format(bundle=ADVISOR_BUNDLE, tgcode=tgcode)
    print(f'[*] 打开: {url}', file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=[
                '--no-sandbox',
                '--disable-dev-shm-usage',
                # 若运行环境走代理且证书被拦截，可取消下一行注释
                # "--ignore-certificate-errors",
            ]
        )
        page = browser.new_page(
            user_agent=(
                'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) '
                'AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'
            )
        )
        # 数据网关(combine-gold)偶发 502，重试 3 次；用 domcontentloaded
        # 而非 networkidle，避免页面长轮询导致一直不 idle 而卡死。
        last_err = None
        for attempt in range(1, 4):
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
                page.wait_for_function(
                    "() => document.body && document.body.innerText.includes('持仓')",
                    timeout=20000,
                )
                break
            except Exception as e:
                last_err = e
                print(f'[!] 第{attempt}次渲染等待失败: {e}', file=sys.stderr)
                page.wait_for_timeout(2000)
        else:
            print(f'[!] 多次尝试仍未渲染持仓区: {last_err}', file=sys.stderr)

        # 给最后一帧渲染一点时间
        page.wait_for_timeout(1500)
        text = page.evaluate('() => document.body.innerText')
        title = page.title()

        # 尝试从页面读取组合名/管理人（宽松提取）
        name = ''
        m = re.search(r'([\u4e00-\u9fa5A-Za-z0-9·]{2,12})\s*(投顾|组合)', text)
        if m:
            name = m.group(1)
        browser.close()

    holdings = parse_holdings(text)
    return {
        'tgcode': tgcode,
        'name': name,
        'title': title,
        'fetched_at': datetime.now().isoformat(timespec='seconds'),
        'holdings': holdings,
        'holdings_count': len(holdings),
        'raw_text': text,
    }


# 关注列表（watchlist）默认文件：每行一个 {tgcode, name}
WATCHLIST_FILE = 'advisor_watchlist.json'


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_aggr(tgcode: str) -> dict:
    """投顾信息概览（dataapi.1234567.com.cn，GET，无需登录/签名）。

    字段比 getTGQuoteByFavor 更全：TGNAME/LOGO_NAME/RISKLEVEL/STRATEGY_RATE/
    SYL_*/BENCHSYL_*（各区间收益与基准收益）/STGCONCEPT（策略说明）/ESTABDATE/STATUS...
    注意响应键为小写 data + errorCode/success（不同于 uni-fundts 的 Data/ErrCode）。
    """
    params = {
        'FIELDS': (
            'PARTNER,TGNAME,LOGO_NAME,RISKLEVEL,STRATEGY_RATE,'
            'SYL_Z,SYL_Y,SYL_1N,SYL_2N,SYL_3N,SYL_JN,SYL_LN,'
            'STGCONCEPT,ESTABDATE,STATUS,RUN_STATUS'
        ),
        'TGCODE': tgcode,
    }
    r = _http_get(API_TG_AGGR, params=params)
    if r.status_code == 200 and r.text.strip().startswith('{'):
        try:
            j = json.loads(r.text)
            if j.get('success') and j.get('data'):
                d = j['data']
                return d[0] if isinstance(d, list) else d
        except Exception:
            pass
    return {}


def _fetch_adjust(tgcode: str, tag: int = 0) -> dict:
    """调仓/持仓明细（uni-fundts，POST，无需登录/签名）。

    tag=0 -> latestAdjust（最新一次调仓，其 fundList.afterRatio 即当前基金级持仓）
    tag=1 -> adjustHistory（历史调仓列表，含每次调仓的基金级前后占比；条数因投顾而异，
            实测越海 6 条 / 万家 20 条 / 省心投 14 条，并非固定上限）
    """
    form = dict(COMBINE_COMMON_FORM)
    form['tgCode'] = tgcode
    form['tag'] = str(tag)
    form['useNewFundType'] = 'true'
    r = _http_post(API_ADJUST_WAREHOUSE, data=form)
    if r.status_code == 200 and r.text.strip().startswith('{'):
        try:
            j = json.loads(r.text)
            if j.get('Succeed') and j.get('Data'):
                return j['Data']
        except Exception:
            pass
    return {}


def _flatten_adjust_funds(node: dict) -> list:
    """把 latestAdjust / 单个历史节点的 adjustList[].fundList 摊平为基金级列表。"""
    funds = []
    for grp in (node or {}).get('adjustList') or []:
        for f in grp.get('fundList') or []:
            op = f.get('operationInt')
            funds.append(
                {
                    'code': f.get('fundCode'),
                    'name': f.get('fundName'),
                    'pre_ratio': _to_float(f.get('preRatio')),
                    'after_ratio': _to_float(f.get('afterRatio')),
                    'op': op,
                    'op_name': ADJUST_OP_NAME.get(op, str(op)),
                }
            )
    return funds


def _build_history(adjust_history: list) -> list:
    """把 adjustHistory 列表整理为按调仓日期排列的历史持仓快照。"""
    out = []
    for node in adjust_history or []:
        funds = _flatten_adjust_funds(node)
        out.append(
            {
                'date': node.get('dateStr'),
                'reason': node.get('reason'),
                'fund_count': len(funds),
                'total_after_ratio': round(sum((f['after_ratio'] or 0) for f in funds), 2),
                'funds': funds,
            }
        )
    return out


def fetch_advisor_public(
    tgcode: str, date: str = None, with_history: bool = False, with_fund: bool = True, with_overview: bool = True
) -> dict:
    """通过公开 host 获取投顾全量数据（免登录/签名/浏览器）：

      - 概览 overview : GET  dataapi.../FundIATGInfoAggr            （字段最全）
      - 业绩/净值 quote: POST  uni-fundts.../getTGQuoteByFavor       （需 tgCodeWithDateStr）
      - 行业配置 industry: POST uni-fundts.../getHoldWarehouseIndustryRatio（仅需 tgCode）
      - 当前基金级持仓 fund_holdings: POST uni-fundts.../getAdjustWarehouse(tag=0)
      - 历史基金级持仓 history: POST uni-fundts.../getAdjustWarehouse(tag=1)  [--history 开启]

    返回结构化 dict。各字段互不依赖，单接口失败不影响其余。
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')

    # 概览（独立 host，最全字段）
    overview = _fetch_aggr(tgcode) if with_overview else {}

    # 业绩/净值
    qform = dict(COMBINE_COMMON_FORM)
    qform['tgCodeWithDateStr'] = f'{tgcode}_{date}'
    qr = _http_post(API_TG_QUOTE, data=qform)
    quote = {}
    if qr.status_code == 200 and qr.text.strip().startswith('{'):
        try:
            j = json.loads(qr.text)
            if j.get('Succeed') and j.get('Data'):
                quote = j['Data'][0]
        except Exception:
            pass

    # 持仓行业配置
    iform = dict(COMBINE_COMMON_FORM)
    iform['tgCode'] = tgcode
    ir = _http_post(API_HOLD_INDUSTRY, data=iform)
    industry = []
    if ir.status_code == 200 and ir.text.strip().startswith('{'):
        try:
            j = json.loads(ir.text)
            industry = j.get('Data') or []
        except Exception:
            pass

    # 当前基金级持仓（最新一次调仓的 afterRatio）
    fund_holdings = []
    if with_fund:
        adj = _fetch_adjust(tgcode, tag=0)
        fund_holdings = _flatten_adjust_funds(adj.get('latestAdjust'))

    # 历史基金级持仓（历次调仓的前后占比）
    history = None
    if with_history:
        adj = _fetch_adjust(tgcode, tag=1)
        history = _build_history(adj.get('adjustHistory'))

    return {
        'tgcode': tgcode,
        'date': date,
        'fetched_at': datetime.now().isoformat(timespec='seconds'),
        'overview': overview,  # FundIATGInfoAggr（最全）
        'quote': quote,  # getTGQuoteByFavor（业绩/净值）
        'industry_holdings': industry,  # 行业配置 [{industryName, ratio,...}]
        'industry_count': len(industry),
        'fund_holdings': fund_holdings,  # 当前基金级持仓 [{code,name,after_ratio,...}]
        'fund_count': len(fund_holdings),
        'history': history,  # 历史调仓快照（--history 时非空）
    }


def load_watchlist(path: str):
    """读取关注列表 JSON。支持两种结构：
    [{"tgcode":"XCOVSEX","name":"越海"}, ...]  或  {"advisors":[...]}。
    """
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict) and 'advisors' in data:
        return data['advisors']
    return data


def fetch_all(advisors: list) -> list:
    """遍历关注列表，逐个抓取持仓，返回结果数组。"""
    results = []
    for a in advisors:
        tg = (a.get('tgcode') or a.get('tgCode') or '').strip()
        if not tg:
            continue
        disp = a.get('name') or tg
        print(f'[*] 抓取 {disp} (tgCode={tg}) ...', file=sys.stderr)
        res = fetch_holdings(tg)
        if a.get('name'):
            res['display_name'] = a['name']
        results.append(res)
    return results


# health 接口：在每日推送前主动验证整条链路，异常即告警
# ---------------------------------------------------------------------------
HEALTH_STATE_FILE = 'advisor_health_state.json'


def _http_get(url: str, headers=None, params=None, timeout=20):
    import requests

    try:
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
        return r
    except Exception as e:  # 网络/超时等
        return type('R', (), {'status_code': 0, 'text': '', 'headers': {}, 'reason': str(e)})()


def _http_post(url: str, data=None, timeout=20):
    import requests

    try:
        # 投顾接口用表单（application/x-www-form-urlencoded）即可，无需 multipart
        r = requests.post(url, data=data or {}, timeout=timeout)
        return r
    except Exception as e:
        return type('R', (), {'status_code': 0, 'text': '', 'headers': {}, 'reason': str(e)})()


def healthcheck(bundle: str = ADVISOR_BUNDLE) -> dict:
    """验证投顾抓取链路的健康度（详见《投顾持仓接口_技术方案与待决问题.md》第 4.2 节）。

    检查项：
      H1  bundle 可达        -> GET tradeh5.../{bundle}/App.js 是否 200
      H2  bundle 未轮换      -> 比对历史记录的 bundle 名（发版即变）
      H3  接口可达(公开)     -> POST uni-fundts.../getTGQuoteByFavor（无需登录/签名）
      H4  数据可解析         -> H3 返回 Succeed=true 且 Data 非空（依赖 H3）
      H5  概览可达(公开)     -> GET dataapi.../FundIATGInfoAggr 返回 TGNAME（最全字段）
      H6  历史持仓可达(公开) -> POST uni-fundts.../getAdjustWarehouse(tag=1) 返回非空列表
      注：H3-H6 均直连公开 host（uni-fundts / dataapi），无需登录/签名/浏览器。
    """
    checks = []

    # H1 + H2：bundle 可达性与轮换检测
    appjs_url = f'https://tradeh5.tiantianfunds.cn/tradeh5/{bundle}/App.js'
    r = _http_get(appjs_url, headers={'User-Agent': 'Mozilla/5.0'})
    if r.status_code == 200:
        checks.append({'id': 'H1_bundle_reachable', 'ok': True, 'detail': f'bundle={bundle} 可达, size={len(r.text)}'})
    else:
        checks.append(
            {
                'id': 'H1_bundle_reachable',
                'ok': False,
                'detail': f'bundle={bundle} HTTP {r.status_code} ({getattr(r, "reason", "")}) -> 可能已发版轮换',
            }
        )

    # H2：与历史记录比对
    last_bundle = ''
    if os.path.exists(HEALTH_STATE_FILE):
        try:
            with open(HEALTH_STATE_FILE, encoding='utf-8') as f:
                last_bundle = json.load(f).get('bundle', '')
        except Exception:
            last_bundle = ''
    if last_bundle and last_bundle != bundle:
        checks.append(
            {
                'id': 'H2_bundle_rotated',
                'ok': False,
                'detail': f'历史 bundle={last_bundle} 与当前 {bundle} 不一致（已发版）',
            }
        )
    else:
        checks.append({'id': 'H2_bundle_rotated', 'ok': True, 'detail': f'bundle 与历史一致={bundle or "(首次运行)"}'})

    # H3 + H4：投顾公开接口（uni-fundts，无需登录/签名）
    # 说明：bundle 里写的是 combine-gold.tiantianfunds.com（静态默认），但运行时经远程
    # host 配置解析到 uni-fundts.1234567.com.cn，且后者对外公开路由 /combine/investAdviserInfo/*。
    # combine-gold 本身公网不可达（网关 404），故直连统一走 uni-fundts。
    # getTGQuoteByFavor 需 tgCodeWithDateStr=TGCODE_YYYY-MM-DD（缺则 Data:null）。
    h3 = {'id': 'H3_endpoint_reachable', 'ok': None, 'detail': 'skipped'}
    h4 = {'id': 'H4_data_parseable', 'ok': None, 'detail': 'skipped: 依赖 H3'}
    today = datetime.now().strftime('%Y-%m-%d')
    form = dict(COMBINE_COMMON_FORM)
    form['tgCodeWithDateStr'] = f'XCOVSEX_{today}'
    r = _http_post(API_TG_QUOTE, data=form)
    if r.status_code == 200 and r.text.strip().startswith('{'):
        try:
            data = json.loads(r.text)
            ok = bool(data.get('Succeed')) and bool(data.get('Data'))
            h3 = {
                'id': 'H3_endpoint_reachable',
                'ok': True,
                'detail': f'uni-fundts 200, Succeed={data.get("Succeed")}, 有Data={bool(data.get("Data"))}',
            }
            h4 = {'id': 'H4_data_parseable', 'ok': ok, 'detail': '返回有效业绩/持仓数据' if ok else '200 但 Data 为空'}
        except Exception as e:
            h3 = {'id': 'H3_endpoint_reachable', 'ok': True, 'detail': f'uni-fundts 200 但 JSON 解析失败: {e}'}
            h4 = {'id': 'H4_data_parseable', 'ok': False, 'detail': 'JSON 解析失败'}
    else:
        h3 = {
            'id': 'H3_endpoint_reachable',
            'ok': False,
            'detail': f'uni-fundts HTTP {r.status_code} -> host/接口变更或无网络',
        }
        h4 = {'id': 'H4_data_parseable', 'ok': False, 'detail': '依赖 H3，H3 失败'}

    # H5：dataapi 概览接口（FundIATGInfoAggr，独立 host，最全字段）
    h5 = {'id': 'H5_aggr_reachable', 'ok': None, 'detail': 'skipped'}
    aggr = _fetch_aggr('XCOVSEX')
    if aggr and aggr.get('TGNAME'):
        h5 = {'id': 'H5_aggr_reachable', 'ok': True, 'detail': f'dataapi 200, TGNAME={aggr.get("TGNAME")}'}
    else:
        h5 = {'id': 'H5_aggr_reachable', 'ok': False, 'detail': 'dataapi 不可达或返回空（host/接口变更或无网络）'}

    # H6：基金级历史持仓接口（getAdjustWarehouse tag=1，历次调仓前后占比）
    h6 = {'id': 'H6_adjust_history', 'ok': None, 'detail': 'skipped'}
    adjh = _fetch_adjust('XCOVSEX', tag=1)
    ah = adjh.get('adjustHistory') if adjh else None
    if isinstance(ah, list) and ah:
        h6 = {'id': 'H6_adjust_history', 'ok': True, 'detail': f'getAdjustWarehouse tag=1 返回 {len(ah)} 条历史调仓'}
    else:
        h6 = {'id': 'H6_adjust_history', 'ok': False, 'detail': '基金级历史持仓接口不可达或返回空'}

    checks.extend([h3, h4, h5, h6])

    # 汇总：ok=True 通过；ok=False 失败；ok=None 跳过
    failed = [c for c in checks if c['ok'] is False]
    skipped = [c for c in checks if c['ok'] is None]
    status = 'healthy' if not failed else ('degraded' if skipped else 'unhealthy')

    # 写回状态（记录当前 bundle 与最近成功时间）
    state = {
        'bundle': bundle,
        'last_check': datetime.now().isoformat(timespec='seconds'),
        'status': status,
    }
    try:
        with open(HEALTH_STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return {'status': status, 'checks': checks, 'failed': len(failed), 'skipped': len(skipped)}


def main():
    ap = argparse.ArgumentParser(description='天天基金投顾组合持仓抓取器')
    ap.add_argument('--tgcode', help='投顾组合 TGCode（分享链接 tgCode= 的值）')
    ap.add_argument('--url', help='完整分享链接，自动提取 tgCode=')
    ap.add_argument('--out', help='输出 JSON 文件路径')
    ap.add_argument('--daily', action='store_true', help='每日模式（仅影响输出提示）')
    ap.add_argument(
        '--watchlist',
        default=WATCHLIST_FILE,
        help=f'关注列表 JSON 路径（默认 {WATCHLIST_FILE}）',
    )
    ap.add_argument(
        '--all',
        action='store_true',
        help='遍历关注列表中的全部投顾并合并输出（免手动逐个维护）',
    )
    ap.add_argument(
        '--history',
        action='store_true',
        help='额外抓取历史基金级持仓（getAdjustWarehouse tag=1，历次调仓前后占比）；默认仅抓当前',
    )
    ap.add_argument(
        '--playwright',
        action='store_true',
        help='（兜底）改用无头浏览器渲染 H5 页抓取（需本机可跑 Chromium）；默认走公开接口直连',
    )
    ap.add_argument(
        '--healthcheck',
        action='store_true',
        help='运行 health 接口：验证 bundle 可达/未轮换、各公开接口(业绩/概览/历史持仓)可达与可解析',
    )
    ap.add_argument(
        '--bundle',
        default=ADVISOR_BUNDLE,
        help=f'前端 bundle 名（默认 {ADVISOR_BUNDLE}，发版后需更新；仅影响 healthcheck H1/H2）',
    )
    args = ap.parse_args()

    # 模式 0：health 接口（每日推送前调用，异常告警）
    if args.healthcheck:
        rep = healthcheck(bundle=args.bundle)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        # 有失败项时以非 0 退出，便于监控系统捕获
        sys.exit(1 if rep['failed'] else 0)

    # 默认主路径：公开接口直连（uni-fundts + dataapi，免登录/签名/浏览器）
    # 仅当显式 --playwright 时回退到无头浏览器渲染 H5 页（需本机可跑 Chromium）
    if not args.playwright:
        if args.all:
            advisors = load_watchlist(args.watchlist)
            if not advisors:
                ap.error(f'关注列表为空或不存在：{args.watchlist}')
            results = []
            for a in advisors:
                tg = (a.get('tgcode') or a.get('tgCode') or '').strip()
                if not tg:
                    continue
                disp = a.get('name') or tg
                print(f'[*] 抓取 {disp} (tgCode={tg}) ...', file=sys.stderr)
                res = fetch_advisor_public(tg, with_history=args.history)
                if a.get('name'):
                    res['display_name'] = a['name']
                results.append(res)
            out = {
                'fetched_at': datetime.now().isoformat(timespec='seconds'),
                'count': len(results),
                'advisors': results,
                'mode': 'public',
            }
        else:
            tgcode = args.tgcode or (extract_tgcode_from_url(args.url) if args.url else '')
            if not tgcode:
                ap.error('必须通过 --tgcode / --url 提供投顾组合标识，或用 --all 遍历关注列表')
            out = fetch_advisor_public(tgcode, with_history=args.history)
            out['mode'] = 'public'
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                json.dump(out, f, ensure_ascii=False, indent=2)
            print(f'[*] 已写入 {args.out}', file=sys.stderr)
        else:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # 兜底：无头浏览器渲染 H5 页（仅 --playwright，需本机可跑 Chromium）
    if args.all:
        advisors = load_watchlist(args.watchlist)
        if not advisors:
            ap.error(f'关注列表为空或不存在：{args.watchlist}')
        results = fetch_all(advisors)
    else:
        tgcode = args.tgcode or (extract_tgcode_from_url(args.url) if args.url else '')
        if not tgcode:
            ap.error('必须通过 --tgcode / --url 提供投顾组合标识，或用 --all 遍历关注列表')
        results = [fetch_holdings(tgcode)]
    out = {
        'fetched_at': datetime.now().isoformat(timespec='seconds'),
        'count': len(results),
        'advisors': results,
        'mode': 'playwright',
    }
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f'[*] 已写入 {args.out}', file=sys.stderr)
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
