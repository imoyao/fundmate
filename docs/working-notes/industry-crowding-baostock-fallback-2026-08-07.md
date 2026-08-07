# 行业拥挤度 · baostock 分母兜底实现方案（2026-08-07）

## 背景与目标

行业拥挤度 `crowding_pct` 的分母 = **全 A 中位 PB**，由 `industry_crowding.py:market_pb_series()` 提供。
原兜底链：

1. `ak.stock_a_all_pb()`（legulegu，2005+ 全历史）
2. 本地缓存 `cache/all_pb.csv`
3. 东财实时 PB 兜底 `push2.eastmoney.com`（**2026-08-05 实测出口 IP 被封，失效**）
4. `unavailable` → 整组标灰

技术债 `tech-debt.md:64`：行业拥挤度侧未闭环，需把 **baostock 从预留提升为可用默认兜底**，
用成分股行情自算全 A 中位 PB，替代失效的东财兜底。

## 实现要点

`market_pb_series()` 第三级改为 baostock 批量兜底（顺序 legulegu → 缓存 → baostock → 东财 → unavailable）。

关键接口：`baostock.query_daily_history_k_AStock(date)` —— **单次调用返回某日全部 A 股 K 线**
（含 `pbMRQ` 字段），无需逐股查询，一次网络往返即可拿到全市场 PB 分布 → 中位数即全 A 中位 PB。

## 1. 数据成本

| 项 | 说明 |
|----|------|
| 数据量 | 单次 `query_daily_history_k_AStock` 返回全市场约 5000~7000 只 A 股当日 K 线，仅取 `pbMRQ` 非空值求中位数 |
| 请求频率 | 仅在 legulegu 不可达 **且** 无本地缓存的降级场景触发一次（每日最多 1 次），正常情况不调用 |
| 免费配额 | baostock 免费开放，无每日 DML 上限（登录体现），仅单连接阻塞风险 |
| 网络 | 走 baostock 自有 socket 服务（`s.baostock.com`），不走 requests，不受 `requests_patch.py` 影响 |

判定：数据成本**低**——降级/冷启动才触发，且单次请求即得全市场分布，无需循环遍历。

## 2. 性能

| 维度 | 评估 |
|------|------|
| 调用次数 | 1 次/触发（vs 逐股方案需 5000+ 次 `query_history_k_data_plus`，完全不可行） |
| 耗时 | 单次批量接口约 1~5s（受服务端负载影响）；重连 bad 状态需重试 |
| 内存 | 一次拉全市场 DataFrame，约数千行，< 10MB，可接受 |
| 阻塞风险 | **最高**：baostock `login()` 与查询均是无超时的阻塞 socket。服务器不可用时调用将**永久挂起**，直接阻塞 `TemperatureJob` 主链路（违反 README 降级设计）。**必须**用线程外包 + 超时（如 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=10)`）隔离 |

性能结论：单次很快，但必须做线程超时保护，否则公共服务不可达时主同步任务会卡死。

## 4. 降级路径

完整兜底顺序（前一级失败自动进下一级）：

1. `ak.stock_a_all_pb()`（legulegu 全历史）→ **hist_ok=True，最优**
2. 本地缓存 `cache/all_pb.csv` → **hist_ok=True**
3. **baostock 批量取当日全 A 中位 PB（本次新增）** → `hist_ok=False`，单点追加缓存，历史随时间自增长
4. 东财实时（保留为最后兜底，目前 IP 被封，实际不可达）
5. 全失败 → `(None, unavailable)` → 上层 `_placeholder()` 标灰，绝不抛异常

baostock 自身也需超时降级：`login` 或批量查询超过阈值（建议 20s）→ 视为不可用，继续走第 4、5 级。

## 5. 关键实现细节（待编码）

- 新增 `_baostock_market_median_pb()`：在线程中执行 `login → query_daily_history_k_AStock → logout`，
  解析 `pbMRQ`，过滤非空/正值，`statistics.median` 返回当日中位 PB。
- 线程超时：`ThreadPoolExecutor.submit(...).result(timeout=20)`；超时或异常 → 返回 `None`。
- `market_pb_series()` 末级判断 baostock 兜底前，需保证 baostock 已安装（`try import baostock`）。
- 成功时复用 `_save_allpb_cache` 落盘缓存，供后续复用。

## 验证

baostock 服务器恢复后实测：
`pdm run python -c "...query_daily_history_k_AStock(今日)...中位数"`，确认字段名与数量级。

## 风险与开放项

- baostock 批量接口字段名未在本机验证（服务器当前不可达，2026-08-07 实测 `login` 挂起）。
- 若 `query_daily_history_k_AStock` 不含 `pbMRQ`，退化为逐股 `query_history_k_data_plus` 采样
  （取 hs300/zz500 指数成分股作样本计算中位 PB，样本量约 300/500 可控）。
- 服务器成本：分母是单次低频调用，无持续订阅，符合"能白嫖就不算"原则。
