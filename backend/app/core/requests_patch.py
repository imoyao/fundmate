# -*- coding: utf-8 -*-
# File : requests_patch.py
# 全局请求补丁：让所有 akshare / requests 调用自动带浏览器头 + 连接复用 + 重试。
#
# 背景与根因（2026-08-01 本机 diag_em.py + akshare 源码实证）：
#   乖离度同步曾大量报 RemoteDisconnected / schannel server closed abruptly。分两层处理：
#   (1) host 重写（尝试性兜底，非已证实主因）：akshare 部分函数用 `80.push2.eastmoney.com`，
#       另有函数用无前缀 `push2.eastmoney.com`。本机 curl 实测两 host 均 schannel 失败，
#       故 host 子域差异并非根因；此处重写保留作保险，不改数据正确性。
#   (2) 重试 + 限速（主要缓解手段）：东财按 IP 动态限流/临时封，裸请求瞬时 RST；
#       → 3 次指数退避重试 + 限速兜底；配合 PriceFetcher 进程内重试与 calculate_batch 限速。
#   曾试 curl_cffi(impersonate=chrome) 模拟 TLS 指纹，但 akshare 多请求链路里偶发 curl:(56) 断连，弃用。
#   真实根因（本机）倾向 DevSidecar 边车代理 TLS 干扰或出口 IP 被封，待退出代理后 diag 验收确认。
#
# 做法（零配置、零手动维护）：
#   进程启动时把 requests 的 get/post（模块级与类级）全局替换为「push2 子域重写 + 浏览器头 + 连接复用 + 重试」会话。
#   用标准 requests（裸请求本就能通，加浏览器头仅防未来东财加 UA 校验），不做 TLS 指纹伪装。
#
# 覆盖范围：只要在 app 进程内（所有 akshare 调用点共用此会话），一处安装，全进程生效。
import logging
import random
import re
import time
from unittest import mock
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


class _EMSession(requests.Session):
    """东财会话（保险性 host 重写）：发送前把 `N.push2.eastmoney.com` 重写为 `push2.eastmoney.com`。

    注：host 重写非断连根因（两 host 本机均 schannel 失败），仅作保险；
    真实的重试/限速在 _build_session 的 Retry 适配器与 PriceFetcher 重试逻辑。
    """

    def request(self, method, url, *args, **kwargs):
        try:
            p = urlparse(url)
            if _PUSH2_HOST_RE.match(p.netloc):
                rewritten = urlunparse(p._replace(netloc='push2.eastmoney.com'))
                logger.debug(f'[requests_patch] 重写 host: {p.netloc} -> push2.eastmoney.com ({method} {rewritten})')
                url = rewritten
        except Exception:
            pass
        return super().request(method, url, *args, **kwargs)


def _build_session():
    """构造全局会话：浏览器头 + 连接复用 + urllib3 重试。

    实证结论（2026-08-01 本机 diag_em.py 验证）：
      - 东财对裸 python requests 放行（无需伪装 TLS 指纹），A 基准裸请求直接 200；
      - 反而 curl_cffi 在 akshare 多请求链路里偶发 curl:(56) Connection closed abruptly。
    故默认用标准 requests + 浏览器头（防未来东财加 UA 检查）+ 重试，不启用 curl_cffi。

    Returns:
        (session, transport_name)
    """
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    s = _EMSession()
    # 不做 proxies 硬编码：跟随环境（有 HTTP_PROXY/HTTPS_PROXY 则走，无则直连）。
    # 云上/本地统一此行为，零配置零维护；若本地 env 代理指向不可用地址，属本地配置问题而非代码问题。
    s.headers.update(_EM_HEADERS)
    s.headers['Cookie'] = _make_nid_cookie()
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
    s.mount('https://', adapter)
    s.mount('http://', adapter)
    return s, 'requests+headers+retry'


def install_requests_patch():
    """全局安装请求补丁（幂等，可重复调用）。

    在 app/__init__ 顶部调用一次即可覆盖整个进程；
    路由模块级与类级的 get/post 到我们的会话，不影响 requests.exceptions 等其它属性。
    """
    global _INSTALLED
    if _INSTALLED:
        return

    session, transport = _build_session()
    # 模块级与类级都替换，确保 akshare 无论是 requests.get 还是自建 Session().get 都走我们的会话
    mock.patch('requests.get', session.get).start()
    mock.patch('requests.post', session.post).start()
    mock.patch('requests.Session.get', session.get).start()
    mock.patch('requests.Session.post', session.post).start()

    _INSTALLED = True
    logger.info(f'[requests_patch] 已全局启用东财友好会话，传输层={transport}')
