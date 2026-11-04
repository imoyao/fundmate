# -*- coding: utf-8 -*-
"""指数成分股权重直连适配（国证指数官网，绕开 akshare 的固定列序解析）。

为什么单开这一路（2026-11-03 实测）：权重源原本只有 akshare 的中证口径
（``index_stock_cons_weight_csindex``），而它**只发布中证系列**——深证/国证系
（399001 深证成指、399006 创业板指等）在中证官网没有权重文件，返回 HTML 404，
pandas 读它时抛「Excel file format cannot be determined」。名录 4100 只里约
58% 属此类，等于详情页权重区块对大半个市场恒为「—」。

国证官网自带的样本权重下载接口一次给**最新一期全量权重**：

    GET https://www.cnindex.com.cn/sample-detail/download-history?indexcode=399001
    → attachment;filename=399001_cons.xlsx（xlsx 二进制；399001 实测 500 行、
      399006 实测 100 行，日期均为单一期 2026-10-30）

**为什么必须校验 attachment 头**：它是本模块唯一的「口径判定」依据。接口对不认识
的码不报 4xx，而是 200 + 12 字节文本「暂无数据」（``text/html``、无
Content-Disposition）——直接丢给 pandas 会抛 BadZipFile / Excel 格式错，与真实
抓取故障混成一团（与 ``index_metrics._is_weight_scope_miss`` 同一降噪诉求）。故：

- 有 attachment 且内容是 xlsx（PK 头）→ 解析返回；
- 无 attachment → 「该码不在国证口径内」，debug 记录，返回 None；
- 其余（HTTP 错误 / 网络异常 / 附件不是 xlsx / 解析失败）→ 真故障，warning 记录。

依赖方向仍是叶子：仅标准库 / requests / pandas（无 app 内部依赖）。
"""

from __future__ import annotations

import warnings
from io import BytesIO
from typing import Any, Optional

import requests
from loguru import logger

_CNI_WEIGHTS = 'https://www.cnindex.com.cn/sample-detail/download-history'
_HEAD = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
# xlsx = zip 容器。用它判「附件真的是表格」比看 content-type 可靠
# （源侧给的是 application/octet-stream，不带表格语义）。
_XLSX_MAGIC = b'PK\x03\x04'


def fetch_weights_cni(index_code: str, timeout: int = 20) -> Optional[Any]:
    """国证指数官网最新一期成分股权重帧，取不到返回 ``None``（best-effort，不抛）。

    返回帧保持**源侧原列名**：``日期 / 样本代码 / 样本简称 / 所属行业 /
    总市值(亿元) / 权重（%）``——归一交给消费方 ``index_metrics._normalize_weight_columns``，
    适配层不猜业务口径（两套表头映射到同一形状是消费方的职责）。

    ⚠️ 源侧 ``样本代码`` 是 int64（前导零已被吃掉：000937 → 937），
    补齐依赖 ``_pick_weights`` 既有的 zfill 防御。
    """
    try:
        r = requests.get(_CNI_WEIGHTS, params={'indexcode': index_code}, headers=_HEAD, timeout=timeout)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - 外部通道失败不阻断详情页
        logger.warning(f'国证权重通道失败 code={index_code}: {e}')
        return None

    if 'attachment' not in (r.headers.get('content-disposition') or '').lower():
        # 200 + 「暂无数据」：该码不在国证口径内，不是故障（详见模块说明）
        logger.debug(f'权重不适用（非国证口径） code={index_code}')
        return None

    content = r.content or b''
    if not content.startswith(_XLSX_MAGIC):
        logger.warning(f'国证权重附件非 xlsx code={index_code} bytes={len(content)}')
        return None

    try:
        import pandas as pd

        with warnings.catch_warnings():
            # openpyxl 对国证的表格会打一条「no default style」UserWarning，与数据无关
            warnings.simplefilter('ignore', UserWarning)
            return pd.read_excel(BytesIO(content))
    except Exception as e:  # noqa: BLE001
        logger.warning(f'国证权重解析失败 code={index_code}: {e}')
        return None
