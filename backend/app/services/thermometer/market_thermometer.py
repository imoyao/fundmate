#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
市场温度聚合器 —— 返回统一 JSON
=================================
聚合多个平台的市场温度/情绪指标，输出统一结构，便于 Web 展示 / 微信推送。

数据源分层：
  · 稳定层（真实接口，基本免维护）
      - 东财市场交易量        : push2.eastmoney.com 公开行情接口（已验证可用）
      - 韭圈儿恐贪 + 中长期温度 : app.jiucaishuo.com 官方页面（Playwright 渲染取值，已验证可用）
      - 集思录可转债温度      : www.jisilu.cn 公开 cb_list_new（无需登录，已验证可用，样本有限）
  · 脆弱层（App 私有 / 无公开接口，单源失败不影响整体）
      - 且慢温度计            : 官方 MCP(stargate.yingmi.com) 的 GetLatestQuotations（用户提供 key，已验证可用）
      - 有知有行温度计        : youzhiyouxing.cn/thermometer 网页 SSR（公开可抓，已验证可用）
      - 富来智投(指数宝)      : api.fulaizhitou.com 需微信 OAuth 登录态(headers.token)，【可选源】
                                未提供 FULAI_TOKEN 时优雅跳过；提供后接 资金/强弱/龙虎榜 增量
  · 自算层（完全自主，无需第三方授权）
      - 股债利差估值分位      : valuation_jiucai.py（沪深300 PE + 10Y国债 + CPI，免费数据，复刻"韭菜投资学"思路）
      - 行业拥挤度(可选源)    : industry_crowding.py（韭菜单行业方法；优先级 Tushare > baostock > legulegu）
                                无可用数据源/网络受限时整组优雅标灰，不影响主链路

每个 fetcher 返回统一结构（或结构列表）：
  {"source","name","value","label","updated_at","stale","note"}
stale=True 表示数据不可用（已标灰），不会阻塞其它源。

用法：
  python3.11 market_thermometer.py            # 输出 JSON 到 stdout + 写 cache_latest.json
  QIEMAN_API_KEY=xxx python3.11 market_thermometer.py   # 且慢真实温度
  FULAI_TOKEN=xxx   python3.11 market_thermometer.py   # 富来智投(指数宝) 增量数据
"""

import json
import os
import re
import time

import requests
from playwright.sync_api import sync_playwright

TIMEOUT = 15
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
HERE = os.path.dirname(os.path.abspath(__file__))

# 韭圈儿标签（恐贪/温度通用）
_FG_LABELS = r'(极度恐惧|恐惧|偏恐惧|中性|偏贪婪|贪婪|极度贪婪|适中|偏冷|偏热|极冷|极热|高温|低温)'


def _now() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


def _label_fear(n):
    """0-100 恐惧贪婪指数 -> 文字标签"""
    if n is None:
        return '未知'
    if n < 10:
        return '极度恐惧'
    if n < 25:
        return '恐惧'
    if n < 45:
        return '偏恐惧'
    if n < 55:
        return '中性'
    if n < 75:
        return '偏贪婪'
    if n < 90:
        return '贪婪'
    return '极度贪婪'


def _label_temp(n):
    """0-100 温度 -> 文字标签（估值/可转债通用）"""
    if n is None:
        return '未知'
    if n < 20:
        return '极冷'
    if n < 40:
        return '偏冷'
    if n < 60:
        return '适中'
    if n < 80:
        return '偏热'
    return '极热'


# ───────────────────────────── 稳定层 ─────────────────────────────
def fetch_eastmoney():
    """全市场成交额（上证 + 深证 + 北证 近似求和），公开接口、零维护。"""
    boards = {
        '上证': '1.000001',  # 上证指数
        '深证': '0.399001',  # 深证成指
        '北证': '0.899050',  # 北证50（注意前缀 0. 而非 1.）
    }
    total = 0.0
    parts = {}
    ok = True
    err = ''
    for name, secid in boards.items():
        try:
            r = requests.get(
                f'https://push2.eastmoney.com/api/qt/stock/get' f'?secid={secid}&fields=f43,f48,f57,f58,f170',
                headers={'User-Agent': UA},
                timeout=TIMEOUT,
            )
            d = r.json().get('data') or {}
            amt = (d.get('f48') or 0) / 1e8  # 元 -> 亿
            chg_raw = d.get('f170')  # 东财涨跌幅为百分点(如 1.25 表示 +1.25%)
            chg = round(chg_raw / 100, 2) if isinstance(chg_raw, (int, float)) else None
            total += amt
            parts[name] = {'amount_yi': round(amt, 1), 'chg_pct': chg}
        except Exception as e:  # noqa
            ok = False
            err = str(e)[:80]
    if not ok or total == 0:
        return {
            'source': '东财',
            'name': '全市场成交额(亿)',
            'value': None,
            'label': '获取失败',
            'updated_at': _now(),
            'stale': True,
            'note': err or '无数据',
        }
    yi = round(total, 1)
    label = '放量' if yi > 12000 else ('缩量' if yi < 8000 else '温和')
    return {
        'source': '东财',
        'name': '全市场成交额(亿)',
        'value': yi,
        'label': label,
        'updated_at': _now(),
        'stale': False,
        'note': json.dumps(parts, ensure_ascii=False),
    }


def fetch_jiucaishuo():
    """
    韭圈儿：恐惧贪婪指数(短期情绪) + 中长期温度(股债性价)。
    方法：用 Playwright 无头渲染官方页面 app.jiucaishuo.com，读取已渲染的公开数值。
          不依赖易随前端发版变化的 AES 密钥，稳健。
    若 Playwright/Chromium 不可用，优雅降级（标灰）。
    """
    base = {'source': '韭圈儿', 'updated_at': _now(), 'stale': True}
    items = [
        dict(base, name='恐惧贪婪指数', value=None, label='待接入', note='渲染失败'),
        dict(base, name='中长期温度(股债性价)', value=None, label='待接入', note='渲染失败'),
    ]
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            pg = b.new_page(user_agent=UA)
            pg.goto('https://app.jiucaishuo.com/', wait_until='networkidle', timeout=30000)
            pg.wait_for_timeout(2500)
            txt = pg.inner_text('body') or ''
            b.close()

            m = re.search(r'短期情绪\s*(\d{1,3})\s*' + _FG_LABELS, txt)
            if m:
                v = int(m.group(1))
                items[0] = dict(
                    base,
                    name='恐惧贪婪指数',
                    value=v,
                    label=m.group(2),
                    stale=False,
                    note='韭圈儿官方页面渲染取值(短期情绪)',
                )
            m = re.search(r'中长期温度\s*(\d{1,3})\s*℃\s*' + _FG_LABELS, txt)
            if m:
                v = int(m.group(1))
                items[1] = dict(
                    base,
                    name='中长期温度(股债性价)',
                    value=v,
                    label=m.group(2),
                    stale=False,
                    note='韭圈儿官方页面渲染取值(股债性价/FED模型)',
                )
            md = re.search(r'择时指标\s*(\d{1,2}-\d{1,2})', txt)
            if md:
                for it in items:
                    if not it['stale']:
                        it['note'] = it['note'] + f'；数据日期~{md.group(1)}'
    except Exception as e:  # noqa
        for it in items:
            it['note'] = '渲染异常: ' + str(e)[:80]
    return items


def fetch_jisilu():
    """
    集思录可转债温度（近似）。
    接口：www.jisilu.cn/data/cbnew/cb_list_new/ 公开可访问（无需登录 cookie）。
    说明：未登录时该接口仅返回 30 只（total=30），为有限样本；
          有集思录会员 cookie 时可获全量，温度更准。
    温度定义：基于全市场可转债「中位价格」与「中位溢价率」的截面代理
          temp = 0.5*价格分位(90~130->0~100) + 0.5*溢价率分位(0~60->0~100)
    """

    def _fnum(v):
        try:
            return float(v)
        except Exception:  # noqa
            return None

    try:
        last = None
        for _ in range(2):  # 偶发空 body，重试一次
            r = requests.get(
                'https://www.jisilu.cn/data/cbnew/cb_list_new/',
                headers={'User-Agent': UA, 'Referer': 'https://www.jisilu.cn/data/cbnew/'},
                timeout=TIMEOUT,
            )
            if r.content:
                last = r
                break
        if not last:
            raise RuntimeError('空响应')
        data = last.json()
        cells = [x['cell'] for x in data.get('rows', [])]
        prices = [x for x in (_fnum(c.get('price')) for c in cells) if x is not None]
        prem = [x for x in (_fnum(c.get('premium_rt')) for c in cells) if x is not None]
        if not prices or not prem:
            raise RuntimeError('无样本')
        import statistics

        mp = statistics.median(prices)  # 中位价格
        mpr = statistics.median(prem)  # 中位溢价率(%)
        temp = 0.5 * max(0, min(100, (mp - 90) / (130 - 90) * 100)) + 0.5 * max(0, min(100, mpr / 60 * 100))
        temp = round(temp, 1)
        return {
            'source': '集思录',
            'name': '可转债温度(近似)',
            'value': temp,
            'label': _label_temp(temp),
            'updated_at': _now(),
            'stale': False,
            'note': f'中位价{mp:.1f} / 中位溢价率{mpr:.1f}% (样本{len(cells)}只；'
            f'未登录仅返回30只，会员cookie可获全量)',
        }
    except Exception as e:  # noqa
        return {
            'source': '集思录',
            'name': '可转债温度(近似)',
            'value': None,
            'label': '获取失败',
            'updated_at': _now(),
            'stale': True,
            'note': '集思录接口异常: ' + str(e)[:80],
        }


# ───────────────────────────── 脆弱层 ─────────────────────────────
def _qieman_get_temperature(api_key):
    """通过且慢官方 MCP(stargate.yingmi.com) 调用 GetLatestQuotations 取市场温度计。
    返回 (temperatureList, updatedOn)。依赖仅 requests + 标准库。
    注意：MCP 响应为带换行符的 pretty JSON，必须用原始字节按 \\n\\n 切分事件、
          再把同事件的多个 data 行拼接，否则会被 iter_lines 截断。"""
    import json as _json
    import threading

    HOST = 'https://stargate.yingmi.com'
    BASE = 'https://stargate.yingmi.com/mcp/sse'
    events, post_url = [], [None]
    _lk = threading.Lock()

    def reader():
        r = requests.get(f'{BASE}?apiKey={api_key}', headers={'Accept': 'text/event-stream'}, stream=True, timeout=60)
        buf = b''
        for chunk in r.iter_content(chunk_size=4096):
            buf += chunk
            while b'\n\n' in buf:
                block, buf = buf.split(b'\n\n', 1)
                evt, dlines = None, []
                for line in block.split(b'\n'):
                    s = line.decode('utf-8', 'ignore')
                    if s.startswith('event:'):
                        evt = s[6:].strip()
                    elif s.startswith('data:'):
                        dlines.append(s[5:].lstrip())
                if dlines:
                    payload = '\n'.join(dlines)
                    with _lk:
                        events.append((evt or 'message', payload))
                    if evt == 'endpoint':
                        post_url[0] = HOST + payload

    threading.Thread(target=reader, daemon=True).start()
    for _ in range(60):
        if post_url[0]:
            break
        time.sleep(0.1)
    if not post_url[0]:
        raise RuntimeError('MCP 连接失败')

    def rpc(method, params=None, rid=1):
        b = {'jsonrpc': '2.0', 'method': method, 'id': rid}
        if params is not None:
            b['params'] = params
        requests.post(post_url[0], json=b, headers={'Content-Type': 'application/json'}, timeout=20)

    def wait(rid, timeout=30):
        t0 = time.time()
        while time.time() - t0 < timeout:
            with _lk:
                for i, (_, pl) in enumerate(events):
                    try:
                        j = _json.loads(pl)
                    except Exception:  # noqa
                        continue
                    if j.get('id') == rid:
                        del events[i]
                        return j
            time.sleep(0.2)
        return None

    rpc(
        'initialize',
        {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'clientInfo': {'name': 'mt', 'version': '1'}},
        1,
    )
    wait(1)
    requests.post(
        post_url[0],
        json={'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        headers={'Content-Type': 'application/json'},
        timeout=20,
    )
    rpc('tools/call', {'name': 'GetLatestQuotations', 'arguments': {}}, 3)
    res = wait(3, 30)
    if not res:
        raise RuntimeError('GetLatestQuotations 无响应')
    content = (res.get('result') or {}).get('content') or []
    text = content[0].get('text', '') if content else ''
    data = _json.loads(text)
    return data.get('temperatureList', []), data.get('updatedOn', '')


def fetch_qieman():
    """
    且慢市场温度计 —— 通过官方 MCP 的 GetLatestQuotations 工具（用户提供的 key）。
    实测：该工具返回 中证全A / 沪深300 / 中证500 三档指数温度（0-100° + 评级文字）。
    说明：公开网页 qieman.com/temperature/temperature 已下线，但 MCP 工具可用，故走 MCP。
    """
    api_key = os.getenv('QIEMAN_API_KEY')
    try:
        temps, updated = _qieman_get_temperature(api_key)
        if not temps:
            raise RuntimeError('温度列表为空')
        main = next((t for t in temps if t.get('temperatureIndexCode') == '000985'), temps[0])
        val = main.get('temperature')
        val = round(float(val), 1) if val is not None else None
        note = f"且慢MCP·GetLatestQuotations；更新:{updated or '—'}"
        for t in temps:
            note += f" {t.get('indexName')}{t.get('temperature')}°({t.get('ratingText')})"
        return {
            'source': '且慢',
            'name': '市场温度计(中证全A)',
            'value': val,
            'label': main.get('ratingText', '—'),
            'updated_at': _now(),
            'stale': False,
            'note': note,
        }
    except Exception as e:  # noqa
        return {
            'source': '且慢',
            'name': '市场温度计(中证全A)',
            'value': None,
            'label': '获取失败',
            'updated_at': _now(),
            'stale': True,
            'note': '且慢MCP调用异常: ' + str(e)[:80],
        }


def fetch_youzhi():
    """
    有知有行「知行温度计」——网页版服务端渲染，公开可直接抓取。
    页面：https://youzhiyouxing.cn/thermometer
    实测：返回全市场温度(0-100°) + 各指数温度(沪深300/中证500/上证50等) + 债市温度。
          "温度下降"字样为该区块独有，可唯一定位全市场温度数值。
    """
    try:
        r = requests.get('https://youzhiyouxing.cn/thermometer', headers={'User-Agent': UA}, timeout=TIMEOUT)
        html = r.text
        m = re.search(r'(\d+)°(?:<[^>]*>|\s)*([一-龥]{2})(?:<[^>]*>|\s)*温度下降', html)
        if not m:
            raise RuntimeError('未匹配到全市场温度')
        temp = int(m.group(1))
        label = m.group(2)  # 低估 / 中估 / 高估
        t = re.search(r'温度更新时间：([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日 [0-9]{1,2}:[0-9]{2})', html)
        updated = t.group(1) if t else ''
        # 补充：沪深300 / 中证500 / 上证50 温度（用指数代码锚定，避免命中 meta 描述）
        idx_codes = {'沪深300': '000300.SH', '中证500': '000905.SH', '上证50': '000016.SH'}
        idx = {}
        for name, code in idx_codes.items():
            im = re.search(re.escape(code) + r'.*?(\d+)°', html, re.S)
            if im:
                idx[name] = int(im.group(1))
        note = f'全市场温度(有知有行网页SSR)；更新:{updated}'
        if idx:
            note += '；' + ' '.join(f'{k}{v}°' for k, v in idx.items())
        return {
            'source': '有知有行',
            'name': '全市场温度',
            'value': temp,
            'label': label,
            'updated_at': _now(),
            'stale': False,
            'note': note,
        }
    except Exception as e:  # noqa
        return {
            'source': '有知有行',
            'name': '全市场温度',
            'value': None,
            'label': '获取失败',
            'updated_at': _now(),
            'stale': True,
            'note': '有知有行网页抓取异常: ' + str(e)[:80],
        }


# ───────────────────────────── 可选源：富来智投(指数宝) ─────────────────────────────
def fetch_fulai():
    """
    富来智投「指数宝」(tools.fulaizhitou.com 手机版 / etf.fulaizhitou.com 电脑版，同源同后端)。
    【鉴权】站点为微信内 H5，接口经微信 OAuth 后后端用 headers.token 校验会话。
           未登录调用任意 /tools/* 返回 {"code":20000,"msg":"请先登录"}；
           成功返回 {"code":10000}（注意：成功码是 10000，不是 20000）。
    【真实接口实测（已用真实 token 验证，2026-07-21）】：
       · /tools/index/money          → yieldList{last:"1.73%", dataList[], timeList[]}
                                        实为「资金利率/货基收益」时间序列(2005起)，非主力净流入。
       · /tools/index/temperature/strong → marketStrong{datetime[], marketStrong[], hsThree[], new:"10.59%"}
                                        板块强弱指数(0~1，new 为百分比最新值)，越低=板块轮动越弱。
       · /tools/out/dlzc             → 当前返回 {"code":10001,"msg":"wrong"}（路径/参数待确认，暂不可用）。
    """
    token = os.getenv('FULAI_TOKEN')
    if not token:
        return [
            {
                'source': '富来智投',
                'name': '资金/强弱/龙虎榜(增量)',
                'value': None,
                'label': '待提供token',
                'updated_at': _now(),
                'stale': True,
                'note': '未设置 FULAI_TOKEN（微信登录后在 localStorage 取 token 配置即可启用）',
            }
        ]

    BASE = 'https://api.fulaizhitou.com'
    headers = {'User-Agent': UA, 'Referer': 'https://tools.fulaizhitou.com/', 'token': token}
    items = []

    def _get(path):
        return requests.get(BASE + path, headers=headers, timeout=TIMEOUT).json()

    def _pf(s):
        """'1.73%' / '10.59' -> float(1.73)"""
        try:
            return float(str(s).replace('%', '').strip())
        except Exception:
            return None

    def _fail(name, why):
        items.append(
            {
                'source': '富来智投',
                'name': name,
                'value': None,
                'label': '获取失败',
                'updated_at': _now(),
                'stale': True,
                'note': why,
            }
        )

    # 1) 资金利率 / 货基收益（index/money）
    try:
        j = _get('/tools/index/money')
        if j.get('code') != 10000:
            _fail('资金利率(货基收益)', f"code={j.get('code')} {j.get('msg')}")
        else:
            yl = j.get('yieldList') or {}
            v = _pf(yl.get('last'))
            lab = '宽松' if (v is not None and v < 1.5) else ('中性' if v < 2.5 else '偏紧')
            items.append(
                {
                    'source': '富来智投',
                    'name': '资金利率(货基收益)',
                    'value': v,
                    'label': lab,
                    'updated_at': _now(),
                    'stale': False,
                    'note': f"最新资金利率/货基收益 {yl.get('last')}；数据自2005起共"
                    f"{len(yl.get('dataList', []))}点（富来智投·index/money）",
                }
            )
    except Exception as e:  # noqa
        _fail('资金利率(货基收益)', f'接口异常: {str(e)[:80]}')

    # 2) 板块强弱（index/temperature/strong）
    try:
        j = _get('/tools/index/temperature/strong')
        if j.get('code') != 10000:
            _fail('板块强弱', f"code={j.get('code')} {j.get('msg')}")
        else:
            ms = j.get('marketStrong') or {}
            new = ms.get('new')  # 如 "10.59%"
            v = _pf(new)
            lab = _label_temp(v) if v is not None else '—'
            hs = None
            try:
                hs = float(ms.get('hsThree')[-1])
            except Exception:
                hs = None
            items.append(
                {
                    'source': '富来智投',
                    'name': '板块强弱',
                    'value': v,
                    'label': lab,
                    'updated_at': _now(),
                    'stale': False,
                    'note': f'板块强弱 {new}（越低=板块轮动越弱）；参考沪深300={hs}（富来智投·temperature/strong）',
                }
            )
    except Exception as e:  # noqa
        _fail('板块强弱', f'接口异常: {str(e)[:80]}')

    # 3) 龙虎榜主力（out/dlzc，当前路径/参数待确认）
    try:
        j = _get('/tools/out/dlzc')
        if j.get('code') != 10000:
            _fail('龙虎榜主力', f"接口暂不可用 code={j.get('code')} {j.get('msg')}（路径/参数待确认）")
        else:
            items.append(
                {
                    'source': '富来智投',
                    'name': '龙虎榜主力',
                    'value': None,
                    'label': '待解析',
                    'updated_at': _now(),
                    'stale': True,
                    'note': '接口可用，字段待解析',
                }
            )
    except Exception as e:  # noqa
        _fail('龙虎榜主力', f'接口异常: {str(e)[:80]}')

    return items


# ───────────────────────────── 可选源：行业拥挤度(自算) ─────────────────────────────
def fetch_industry_crowding():
    """
    行业拥挤度（"韭菜投资学"方法，自算）。【可选源】
    数据源优先级（在 industry_crowding.py 内确定）：
      Tushare(token)  >  baostock(本机回补的本地缓存)  >  legulegu(免费·部分行业)
    市场分母(全A中位PB)：优先 akshare.stock_a_all_pb(2005起)，失败回退本地缓存/东财实时PB。
    鲁棒性：legulegu 限流/宕机或沙箱无网络时，整组优雅标灰并给出恢复指引，不阻塞主链路。
    返回：每个行业一项的列表（统一结构）。
    """
    try:
        from industry_crowding import compute_crowding_rows

        rows = compute_crowding_rows()
    except Exception as e:  # noqa
        return [
            {
                'source': '行业拥挤度',
                'name': '行业拥挤度',
                'value': None,
                'label': '获取失败',
                'updated_at': _now(),
                'stale': True,
                'note': 'industry_crowding 调用异常: ' + str(e)[:80],
            }
        ]
    items = []
    for name, code, pct, note in rows:
        if pct is None:
            items.append(
                {
                    'source': '行业拥挤度',
                    'name': name,
                    'value': None,
                    'label': '无数据',
                    'updated_at': _now(),
                    'stale': True,
                    'note': note,
                }
            )
        else:
            bar = '冷' if pct < 30 else ('热' if pct > 70 else '中')
            items.append(
                {
                    'source': '行业拥挤度',
                    'name': name,
                    'value': pct,
                    'label': bar,
                    'updated_at': _now(),
                    'stale': False,
                    'note': f'拥挤度{pct}% · {note}',
                }
            )
    return items


# ───────────────────────────── 聚合 ─────────────────────────────
def aggregate():
    raw = [
        fetch_eastmoney(),
        fetch_jiucaishuo(),
        fetch_jisilu(),
        fetch_qieman(),
        fetch_youzhi(),
        fetch_fulai(),  # 可选源：无 FULAI_TOKEN 时自动跳过
        fetch_industry_crowding(),  # 可选源：无可用数据源时整组标灰
    ]
    items = []
    for x in raw:
        if isinstance(x, list):
            items.extend(x)
        else:
            items.append(x)
    return {'updated_at': _now(), 'items': items}


def main():
    out = aggregate()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    try:
        with open(os.path.join(HERE, 'cache_latest.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception:  # noqa
        pass
    return out


if __name__ == '__main__':
    main()
