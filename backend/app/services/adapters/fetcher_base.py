# -*- coding: utf-8 -*-
"""抓取器基类（services 共享件，叶子）。

从 ``thermometer.fetchers`` 上提到适配层（#1607 批次 4）。原因：且慢投顾适配器
``adapters/qieman_advisor_adapter`` 复用 ``QiemanFetcher``，而它继承本基类；
基类若留在 thermometer 家族内，就形成 ``adapters → thermometer`` 反向边（R5 违规）。

上提后方向自洽：家族包（thermometer/*）依赖本共享件，共享件**不**反向依赖家族包。
``BaseFetcher`` / ``SingleValueFetcher`` 函数体自 thermometer.fetchers 逐字搬运。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import requests

from app.core.constants import DEFAULT_REQUEST_TIMEOUT, USER_AGENT


class BaseFetcher(ABC):
    """所有数据源的抽象基类。"""

    source: str = ''
    name: str = ''

    def __init__(self, timeout: int = DEFAULT_REQUEST_TIMEOUT):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                'User-Agent': USER_AGENT,
                'Accept': 'application/json, text/html, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
        )

    @abstractmethod
    def fetch(self) -> Optional[Dict[str, Any]]:
        """抓取并返回数据载荷；失败返回 ``None``。"""

    # 通用 HTTP 辅助
    def _get(self, url: str, **kwargs) -> requests.Response:
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        return resp

    def _get_json(self, url: str, **kwargs) -> Dict[str, Any]:
        return self._get(url, **kwargs).json()


class SingleValueFetcher(BaseFetcher, ABC):
    """产出单值 {value,label,unit,updated_at,raw} 的源。"""

    unit: str = ''

    def payload(self, value, label, updated_at: Any = None, raw: Any = None) -> Dict[str, Any]:
        return {
            'value': value,
            'label': label,
            'unit': self.unit,
            'updated_at': updated_at,
            'raw': raw,
        }
