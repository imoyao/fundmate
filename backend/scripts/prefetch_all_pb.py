# -*- coding: utf-8 -*-
"""
一次性脚本：预取全A中位PB历史并落盘缓存，供行业拥挤度分母复用。

背景：行业拥挤度的分母（全A中位PB）默认走 legulegu(ak.stock_a_all_pb())，
沙箱/受限网络下该源不可达且无本地缓存 → 拥挤度整组标灰。
本脚本在本机（网络正常）执行一次，把历史PB序列落盘到
  backend/app/services/thermometer/data/all_pb.csv
之后即便在沙箱环境跑 fetch_industry_crowding，也能命中本地缓存恢复分母。
注意：落盘路径已从 cache/ 迁入 data/（基线数据目录，非运行时缓存）。

用法：
    pdm run python scripts/prefetch_all_pb.py
"""

import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('prefetch_all_pb')

# 确保项目根目录在 sys.path（保证 `app` 可导入）
HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


def main() -> int:
    try:
        from app.services.thermometer.industry_crowding import (
            ALLPB_CACHE,
            market_pb_series,
        )
    except Exception as e:  # noqa: BLE001
        logger.error('导入 industry_crowding 失败: %s', e)
        return 1

    logger.info('开始预取全A中位PB历史…（目标缓存路径: %s）', ALLPB_CACHE)

    # market_pb_series 内部已按 1)legulegu 2)本地缓存 3)东财实时 的优先级尝试，
    # 并把成功结果落盘。第一次运行时若 legulegu 可达即建立完整历史。
    s, meta = market_pb_series()

    if s is None or s.dropna().empty:
        logger.error(
            '分母预取失败（meta=%s）。本机网络可能仍不可达 legulegu/东财，请检查代理或网络连接后重试。',
            meta,
        )
        return 2

    # 确认落盘成功
    if os.path.exists(ALLPB_CACHE):
        logger.info(
            '✅ 全A中位PB历史已落盘: %s 个交易日, 最新=%.2f, 来源=%s',
            len(s),
            s.iloc[-1],
            meta.get('src'),
        )
        return 0

    logger.warning('⚠️ 序列非空但缓存文件未生成（落盘异常被吞），请检查目录写权限。')
    return 3


if __name__ == '__main__':
    raise SystemExit(main())
