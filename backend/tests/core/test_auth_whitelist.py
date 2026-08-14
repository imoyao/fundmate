# -*- coding: utf-8 -*-
"""免登录白名单回归测试（覆盖 #821 P0-1 修复）。

背景：探市页 `/explore` 免登录，搜索框依赖 `/api/securities/search/` 与
`/api/funds/search/`。修复前白名单仅含 `/api/health` 与 `/api/temperature`，
导致生产 `AUTH_ENABLED=true` 时匿名访客搜索必 401 且被前端静默吞掉。

本测试锁定以下不变量，防止后续误改白名单：
1. 两个 search 接口对 GET 免登录；
2. 前缀精确到 `/search` 子路由，不能误放行同蓝图下的写接口（如 `/api/funds/nav`）；
3. 既有 health / temperature 免登录不受影响。
"""

from app.core.auth import _is_public


class TestPublicWhitelist:
    def test_search_endpoints_are_public(self):
        assert _is_public('/api/securities/search/', 'GET') is True
        assert _is_public('/api/funds/search/', 'GET') is True

    def test_search_prefix_does_not_open_sibling_write_routes(self):
        # 同蓝图（/api/funds）下的写接口不得因 search 前缀而免登录
        assert _is_public('/api/funds/nav/', 'POST') is False

    def test_health_and_temperature_still_public(self):
        assert _is_public('/api/health', 'GET') is True
        # temperature 无尾斜杠的子路由同样免登录
        assert _is_public('/api/temperature/overview', 'GET') is True

    def test_platform_config_endpoint_is_public(self):
        # 平台级实时估值总闸（issue #826）：探市页免登录也依赖，匿名访客须可读
        assert _is_public('/api/utils/config/', 'GET') is True

    def test_platform_config_prefix_does_not_open_sibling_routes(self):
        # 前缀精确到 /api/utils/config 子路由，不能误放行同蓝图（/api/utils）下其他接口
        assert _is_public('/api/utils/trading-days/2026-08-14/', 'GET') is False
        assert _is_public('/api/utils/fund-confirm-dates/', 'GET') is False

    def test_options_preflight_always_public(self):
        # CORS 预检必须无条件放行，与本白名单无关
        assert _is_public('/api/securities/search/', 'OPTIONS') is True
        assert _is_public('/api/funds/nav/', 'OPTIONS') is True
