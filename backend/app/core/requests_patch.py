# -*- coding: utf-8 -*-
# File : requests_patch.py
# 全局请求补丁：让所有 akshare / requests 调用自动带浏览器头 + 连接复用 + 重试。
#
# 背景与根因（2026-08-05 本机 diag_em.py 实证，已结案）：
#   乖离度/行业同步曾大量报 RemoteDisconnected / ProxyError / schannel server closed abruptly。
#   分三层处理：
#   (1) host 重写（保险，非主因）：akshare 部分函数用 `80.push2.eastmoney.com`，另用无前缀
#       `push2.eastmoney.com`。实测两 host 直连均返回 200，host 子域差异非根因；重写保留作保险。
#   (2) 重试 + 限速（缓解手段）：3 次指数退避重试 + ak.set_option('request_interval', 3) 限速。
#   (3) 关闭系统代理信任 trust_env（**真正根因修复**）：本机残留边车代理（127.0.0.1:31181，
#       代理软件关了但系统代理开关/Winsock 仍解析为 https 代理），requests 默认 trust_env=True
#       继承系统代理，把东财请求甩到已死本地端口 → ProxyError。diag 实测直连均 200、仅 akshare
#       （继承代理）ProxyError，确认根因是代理残留而非东财反爬/IP 封。关 trust_env 后强制直连。
#   曾试 curl_cffi(impersonate=chrome) 模拟 TLS 指纹，但 akshare 多请求链路里偶发 curl:(56) 断连，弃用。
#
# 做法（零配置、零手动维护）：
#   进程启动时给 requests.Session 的 request 方法包一层装饰器（不替换实例，避免丢失
#   调用方在 session 上设置的 headers/cookies），实现：
#     · 仅对 eastmoney 域名注入东财浏览器头 + 伪造 nid cookie（legulegu 等第三方源保持原样，
#       否则带东财专属非法头会让 legulegu 返回空 body/403，导致全A中位PB分母取不到）；
#     · push2 数字前缀子域统一重写到 push2.eastmoney.com（保险）；
#     · 给每个 Session 挂带重试的 HTTPAdapter（连接/读重试）。
#   模块级 requests.get/post 也包装，保证走到同一逻辑。
#
# 覆盖范围：只要在 app 进程内（所有 akshare 调用点共用），一处安装，全进程生效。
import functools
import logging
import random
import re
import time
from urllib.parse import urlparse, urlunparse

import requests

logger = logging.getLogger(__name__)

# 浏览器化请求头：让东财 WAF 把请求当成正常浏览器，而非爬虫/脚本
_EM_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
    ),
    'Referer': 'https://quote.eastmoney.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
}

_INSTALLED = False


def _make_nid_cookie() -> str:
    """进程内随机生成一次 nid，模拟单个浏览器会话（对应 akshare issue #6766 的东财要求）。"""
    nid = ''.join(random.choices('0123456789abcdef', k=32))
    nid_create_time = str(int(time.time() * 1000))
    return f'nid={nid}; nid_create_time={nid_create_time}'


# 东财 push2 接口有多个数字前缀子域（80./88./17./82./33./48.…），akshare 各函数混用。
# 这些子域提供的 `/api/qt/clist|kline/get` 接口数据完全一致（同 API、同数据，仅 CDN 节点不同），
# 故统一重写到无前缀的 `push2.eastmoney.com`（akshare 多数函数本就使用它）。
# 注意：本机 curl 实测 80.push2 与 push2 两 host 均 schannel 失败，host 差异并非根因；
# 此处重写仅作保险（不改数据正确性），真正断连源于网络/代理层，见文件头背景说明。
# 只动「数字前缀的 push2」子域，不影响 push2his / push2delay 等其它服务。
_PUSH2_HOST_RE = re.compile(r'^(\d+)\.push2\.eastmoney\.com$')
# 仅对东财域名注入浏览器头/伪造 cookie；其它域名（legulegu 等）保持调用方原始请求头不动。
_EM_HOST_RE = re.compile(r'eastmoney\.com$', re.I)


def _wrap_request(original):
    """包装 Session.request：保留调用方在 session 上设置的 headers/cookies，
    仅对 eastmoney 域名补充东财头 + nid cookie，并对 push2 数字前缀子域做 host 重写。"""

    @functools.wraps(original)
    def _request(self, method, url, *args, **kwargs):
        try:
            p = urlparse(url)
            if _PUSH2_HOST_RE.match(p.netloc):
                rewritten = urlunparse(p._replace(netloc='push2.eastmoney.com'))
                logger.debug(f'[requests_patch] 重写 host: {p.netloc} -> push2.eastmoney.com ({method})')
                url = rewritten
        except Exception:
            pass

        # 仅东财域名注入浏览器头 + nid；其它域名完全保留调用方（akshare/legulegu）原头，避免污染。
        if _EM_HOST_RE.search(urlparse(url).netloc):
            headers = dict(kwargs.get('headers') or {})
            headers = dict(_EM_HEADERS) | headers  # 东财默认头打底，调用方头覆盖
            headers['Cookie'] = _make_nid_cookie()
            kwargs['headers'] = headers
        return original(self, method, url, *args, **kwargs)

    return _request


def _install_retry_adapter(session):
    """给 session 挂带重试的 HTTPAdapter（连接/读重试），不改动其已有 headers/cookies。"""
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry = Retry(
        total=3,
        backoff_factor=0.5,
        connect=3,
        read=3,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET', 'POST'],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount('https://', adapter)
    session.mount('http://', adapter)


def install_requests_patch():
    """全局安装请求补丁（幂等，可重复调用）。

    在 app/__init__ 顶部调用一次即可覆盖整个进程；包装 Session.request 与模块级
    get/post，保留调用方原有 headers/cookies，仅东财域补充友好头 + 重试。
    """
    global _INSTALLED
    if _INSTALLED:
        return

    # 1) 包装 Session 实例方法（不替换实例，保留 akshare 在 session 上设的 headers/cookies）
    requests.Session.request = _wrap_request(requests.Session.request)
    # 2) 给未来新建的 Session 默认挂重试适配器（monkey-patch __init__）
    _orig_session_init = requests.Session.__init__

    @functools.wraps(_orig_session_init)
    def _session_init(self, *args, **kwargs):
        _orig_session_init(self, *args, **kwargs)
        # 强制直连：双保险屏蔽系统代理残留（如 127.0.0.1:31181 边车代理，代理软件关了但
        # 系统代理开关/Winsock 仍把它解析为 https 代理），否则东财/legulegu 请求会被甩到已死
        # 本地端口 → ProxyError / RemoteDisconnected。
        # 2026-08-05 diag_em.py 实证：裸 requests 仍继承系统代理报 ProxyError；
        #   trust_env=False + proxies=None 双保险后强制直连，根因是代理残留而非东财反爬/IP 封。
        self.trust_env = False
        self.proxies = {'http': None, 'https': None}
        _install_retry_adapter(self)

    requests.Session.__init__ = _session_init
    # 3) 模块级 requests.get/post 也走包装后的 Session.request（requests.get 内部用默认 Session）
    #    通过给默认 Session 已挂重试 + 包装 request，模块级调用自然生效，无需再单独 patch。

    _INSTALLED = True
    logger.info('[requests_patch] 已全局启用东财友好会话（按域名注入头 + 重试），不影响 legulegu 等第三方源')
